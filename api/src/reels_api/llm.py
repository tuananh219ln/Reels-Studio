"""The LLM that writes scripts: which providers exist, which one the team uses, and the call itself.

Members set each provider's API key, base URL and model on /settings/ai and pick one for the whole team. Two
connectors cover every provider: Anthropic's Messages API (Claude) and the OpenAI-compatible
`/chat/completions` most other providers offer. Only Claude needs its own SDK.

With nothing set on /settings/ai the team uses Claude from the environment (ANTHROPIC_API_KEY, CLAUDE_MODEL), as
before this page existed; ANTHROPIC_BASE_URL is also how tests reach a local fake Claude.
"""

import logging
from dataclasses import dataclass
from urllib.parse import urlsplit

import anthropic
import httpx
from sqlalchemy.orm import Session as DbSession

from . import config, crypto
from .claude import ClaudeError
from .models import AppSetting, LlmProvider

log = logging.getLogger(__name__)

ANTHROPIC = "anthropic"
OPENAI = "openai"
ACTIVE_KEY = "llm_provider"
KEY_TAIL = 4
MAX_TOKENS = 16000
REQUEST_TIMEOUT = 300
LIST_TIMEOUT = 20
# Server-side refusal fallback: only these models accept the "default" form on the Claude API.
FALLBACK_MODELS = {"claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5", "claude-fable-5-1"}


@dataclass(frozen=True)
class Preset:
    id: str
    name: str
    kind: str  # ANTHROPIC | OPENAI
    base_url: str  # empty: the member must give one
    models: tuple[str, ...] = ()  # suggestions only; any model name is accepted
    needs_key: bool = True


PRESETS = (
    Preset(
        ANTHROPIC,
        "Claude (Anthropic)",
        ANTHROPIC,
        "https://api.anthropic.com",
        ("claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5"),
    ),
    Preset("openai", "OpenAI", OPENAI, "https://api.openai.com/v1"),
    Preset("gemini", "Google Gemini", OPENAI, "https://generativelanguage.googleapis.com/v1beta/openai"),
    Preset("deepseek", "DeepSeek", OPENAI, "https://api.deepseek.com/v1", ("deepseek-chat", "deepseek-reasoner")),
    Preset("openrouter", "OpenRouter", OPENAI, "https://openrouter.ai/api/v1"),
    Preset("groq", "Groq", OPENAI, "https://api.groq.com/openai/v1"),
    Preset("xai", "xAI Grok", OPENAI, "https://api.x.ai/v1"),
    Preset("qwen", "Qwen (Alibaba Cloud)", OPENAI, "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
    Preset("ollama", "Ollama (máy chủ riêng)", OPENAI, "http://localhost:11434/v1", needs_key=False),
    Preset("custom", "Tùy chỉnh (chuẩn OpenAI)", OPENAI, ""),
)
BY_ID = {preset.id: preset for preset in PRESETS}


@dataclass(frozen=True)
class Target:
    """Everything one call needs, resolved from /settings/ai and the environment."""

    provider: str
    name: str
    kind: str
    base_url: str
    model: str
    key: str


def stored_key(row: LlmProvider | None) -> str:
    if row is None or not row.key_encrypted:
        return ""
    try:
        return crypto.decrypt(row.key_encrypted)
    except crypto.CannotDecrypt:
        # The storage folder's key changed: the member must paste the API key again.
        return ""


def active_id(db: DbSession) -> str:
    setting = db.get(AppSetting, ACTIVE_KEY)
    value = setting.value if setting else None
    return value if isinstance(value, str) and value in BY_ID else ANTHROPIC


def target(db: DbSession, provider_id: str) -> Target:
    """A provider's settings with the defaults filled in; Claude also falls back to the environment."""
    preset = BY_ID[provider_id]
    row = db.get(LlmProvider, provider_id)
    base_url, model, key = (row.base_url, row.model, stored_key(row)) if row else ("", "", "")
    if preset.kind == ANTHROPIC:
        key = key or config.read_env("ANTHROPIC_API_KEY")
        base_url = base_url or config.read_env("ANTHROPIC_BASE_URL")
        model = model or config.claude_model()
    return Target(
        provider=preset.id,
        name=preset.name,
        kind=preset.kind,
        base_url=(base_url or preset.base_url).rstrip("/"),
        model=model or (preset.models[0] if preset.models else ""),
        key=key,
    )


def active_target(db: DbSession) -> Target:
    return target(db, active_id(db))


def problem(target: Target) -> str | None:
    """Why this provider cannot be called yet, in the words members see; None when it can."""
    preset = BY_ID[target.provider]
    if preset.needs_key and not target.key:
        return f"Chưa có API key cho {target.name}: nhập trong Cài đặt › Mô hình AI"
    if not target.base_url:
        return f"Chưa có Base URL cho {target.name}: nhập trong Cài đặt › Mô hình AI"
    if not target.model:
        return f"Chưa chọn model cho {target.name}: nhập trong Cài đặt › Mô hình AI"
    return None


def valid_base_url(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme in ("http", "https") and bool(parts.netloc) and not parts.query and not parts.fragment


def label(provider: str | None, model: str | None) -> str | None:
    """ "DeepSeek · deepseek-chat" for a job that recorded its provider; None for jobs from before /settings/ai."""
    if not provider:
        return None
    preset = BY_ID.get(provider)
    return f"{preset.name if preset else provider} · {model}" if model else (preset.name if preset else provider)


# --- Calls ---


def complete(target: Target, prompt: str, label: str) -> str:
    """One request with one user message; the answer's text. Failures raise ClaudeError with a member message."""
    reason = problem(target)
    if reason:
        raise ClaudeError(reason)
    if target.kind == ANTHROPIC:
        return _anthropic(target, prompt, label)
    return _openai(target, prompt, label)


def list_models(target: Target) -> list[str]:
    """The provider's model names; used by "Kiểm tra kết nối", which costs no tokens."""
    preset = BY_ID[target.provider]
    if preset.needs_key and not target.key:
        raise ClaudeError(f"Chưa có API key cho {target.name}")
    if not target.base_url:
        raise ClaudeError(f"Chưa có Base URL cho {target.name}")
    if target.kind == ANTHROPIC:
        try:
            page = _anthropic_client(target, LIST_TIMEOUT).models.list(limit=100)
        except anthropic.APIError as err:
            raise _anthropic_error(target, err) from None
        return sorted(model.id for model in page.data)
    response = _openai_request(target, "GET", "/models", LIST_TIMEOUT)
    try:
        items = response.json()["data"]
        return sorted({str(item["id"]).removeprefix("models/") for item in items})
    except (ValueError, KeyError, TypeError):
        raise ClaudeError(
            f"{target.name} trả danh sách model không đúng dạng chuẩn OpenAI, kiểm tra Base URL",
            response.text[:2000],
        ) from None


def _anthropic_client(target: Target, timeout: float) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=target.key, base_url=target.base_url, timeout=timeout, max_retries=1)


def _anthropic_error(target: Target, err: anthropic.APIError) -> ClaudeError:
    name = target.name
    if isinstance(err, anthropic.AuthenticationError):
        return ClaudeError(f"API key của {name} không hợp lệ, kiểm tra trong Cài đặt › Mô hình AI")
    if isinstance(err, anthropic.PermissionDeniedError):
        return ClaudeError(f"API key của {name} không có quyền gọi model này", str(err))
    if isinstance(err, anthropic.NotFoundError):
        return ClaudeError(f"{name} không có model “{target.model}”, chọn model khác", str(err))
    if isinstance(err, anthropic.RateLimitError):
        return ClaudeError(f"{name} đang giới hạn lượt gọi hoặc đã hết hạn mức, thử lại sau", str(err))
    if isinstance(err, anthropic.BadRequestError):
        if "credit" in str(err).lower():
            return ClaudeError(f"Tài khoản {name} đã hết hạn mức (credit), cần nạp thêm", str(err))
        return ClaudeError(f"{name} từ chối yêu cầu", str(err))
    if isinstance(err, anthropic.APIStatusError):
        return ClaudeError(f"{name} đang lỗi hoặc quá tải (HTTP {err.status_code}), thử lại sau", str(err))
    if isinstance(err, anthropic.APITimeoutError):
        return ClaudeError(f"{name} không trả lời kịp, thử lại sau")
    return ClaudeError(f"Không kết nối được {name}, kiểm tra mạng và Base URL rồi thử lại", str(err))


def _anthropic(target: Target, prompt: str, label: str) -> str:
    client = _anthropic_client(target, REQUEST_TIMEOUT)
    extra = (
        {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
        if target.model in FALLBACK_MODELS
        else {}
    )
    try:
        response = client.beta.messages.create(
            model=target.model,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
            **extra,
        )
    except anthropic.APIError as err:
        raise _anthropic_error(target, err) from None

    usage = response.usage
    log.info(
        "LLM call %s: provider=%s model=%s input_tokens=%s output_tokens=%s stop_reason=%s",
        label,
        target.provider,
        response.model,
        usage.input_tokens,
        usage.output_tokens,
        response.stop_reason,
    )
    if response.stop_reason == "refusal":
        details = getattr(response, "stop_details", None)
        raise ClaudeError("Claude từ chối viết kịch bản cho chủ đề này, hãy đổi cách diễn đạt", str(details or ""))
    return "".join(block.text for block in response.content if block.type == "text")


def _openai_request(target: Target, method: str, path: str, timeout: float, body: dict | None = None):
    headers = {"Authorization": f"Bearer {target.key}"} if target.key else {}
    name = target.name
    try:
        response = httpx.request(method, target.base_url + path, json=body, headers=headers, timeout=timeout)
    except httpx.TimeoutException:
        raise ClaudeError(f"{name} không trả lời kịp, thử lại sau") from None
    except httpx.HTTPError as err:
        raise ClaudeError(f"Không kết nối được {name}, kiểm tra mạng và Base URL rồi thử lại", str(err)) from None
    status, detail = response.status_code, response.text[:2000]
    if status in (401, 403):
        raise ClaudeError(
            f"API key của {name} không hợp lệ hoặc không có quyền, kiểm tra trong Cài đặt › Mô hình AI", detail
        )
    if status == 404:
        raise ClaudeError(f"{name} báo không tìm thấy (HTTP 404): kiểm tra Base URL và tên model", detail)
    if status == 402:
        raise ClaudeError(f"Tài khoản {name} đã hết hạn mức, cần nạp thêm", detail)
    if status == 429:
        raise ClaudeError(f"{name} đang giới hạn lượt gọi hoặc đã hết hạn mức, thử lại sau", detail)
    if 400 <= status < 500:
        raise ClaudeError(f"{name} từ chối yêu cầu (HTTP {status})", detail)
    if status >= 500:
        raise ClaudeError(f"{name} đang lỗi hoặc quá tải (HTTP {status}), thử lại sau", detail)
    return response


def _openai(target: Target, prompt: str, label: str) -> str:
    # No max_tokens: the providers' limits differ, and a value above one's limit is refused outright.
    body = {"model": target.model, "messages": [{"role": "user", "content": prompt}]}
    response = _openai_request(target, "POST", "/chat/completions", REQUEST_TIMEOUT, body)
    try:
        data = response.json()
        choice = data["choices"][0]
        text = choice["message"].get("content") or ""
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        raise ClaudeError(
            f"{target.name} trả lời không đúng dạng chuẩn OpenAI, kiểm tra Base URL", response.text[:2000]
        ) from None
    usage = data.get("usage") or {}
    finish = choice.get("finish_reason")
    log.info(
        "LLM call %s: provider=%s model=%s input_tokens=%s output_tokens=%s stop_reason=%s",
        label,
        target.provider,
        data.get("model", target.model),
        usage.get("prompt_tokens"),
        usage.get("completion_tokens"),
        finish,
    )
    if finish == "length":
        # Asking again would be cut at the same place and cost the same.
        raise ClaudeError(
            f"Câu trả lời của {target.name} bị cắt giữa chừng vì vượt giới hạn độ dài của model, hãy chọn model khác",
            text[:8000],
        )
    if finish == "content_filter":
        raise ClaudeError(f"{target.name} từ chối viết kịch bản cho chủ đề này, hãy đổi cách diễn đạt")
    return text
