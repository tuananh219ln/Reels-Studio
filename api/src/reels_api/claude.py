"""Script writing with Claude: the prompt, the call and turning the answer into a checked script.

Members edit only the prompt's content on /knowledge. The output format below is fixed in code, so
an edited prompt can never break the JSON every job depends on.
"""

import json
import logging
import math
from collections.abc import Callable
from dataclasses import dataclass, field

import anthropic

from . import config

log = logging.getLogger(__name__)

TOPIC_PLACEHOLDER = "[Chủ đề]"
MAX_KEYWORD_LENGTH = 100
FALLBACK_SECONDS = 4
MAX_TOKENS = 16000
REQUEST_TIMEOUT = 300
# Server-side refusal fallback: only these models accept the "default" form on the Claude API.
FALLBACK_MODELS = {"claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5", "claude-fable-5-1"}

OUTPUT_FORMAT = """\
ĐỊNH DẠNG ĐẦU RA (bắt buộc): chỉ trả về đúng một object JSON, không kèm chữ nào khác, không bọc trong ```.
Các trường:
- "titles": 5 tiêu đề viết hoa, mỗi tiêu đề tối đa 12 từ.
- "title_keywords": từ khóa tiếng Việt để tìm ảnh cho cảnh tiêu đề, cụ thể nhất trước.
- "scenes": 5–7 cảnh nội dung theo thứ tự. Mỗi cảnh có:
  - "text": chữ trên màn hình, tối đa 10 từ; bọc từ khóa cần tô đỏ trong *dấu sao*; xuống dòng bằng \\n
    (không để dòng trống, không kết thúc bằng \\n);
  - "seconds": số giây của cảnh (3–5);
  - "keywords": từ khóa tiếng Việt để tìm ảnh, cụ thể nhất trước (tên món trước), mỗi từ khóa tối đa 100 ký tự;
  - "image_prompt": prompt tạo ảnh 9:16 (ảnh thực, ánh sáng tự nhiên, bàn gỗ).
- "caption": caption 80–120 từ.
- "hashtags": đúng 5 hashtag, mỗi hashtag bắt đầu bằng #.
- "affiliates": 2 sản phẩm affiliate phù hợp, mỗi sản phẩm một chuỗi.
- "pinned_comment": câu bình luận ghim.
- "self_review": danh sách các câu đã sửa khi tự rà soát an toàn (mỗi mục ghi câu cũ → câu mới); để [] nếu không sửa gì.
- "music_suggestions": 2–3 tên bản nhạc không lời hợp chủ đề, có thể tìm trong thư viện nhạc TikTok/Facebook.

Ví dụ đầy đủ:
{
  "titles": [
    "5 MÓN GIÚP XƯƠNG CHẮC KHỎE SAU TUỔI 50",
    "SAU 50 TUỔI ĐỪNG ĐỂ BỮA CƠM THIẾU 5 MÓN NÀY",
    "5 MÓN QUEN THUỘC TỐT CHO XƯƠNG KHỚP NGƯỜI LỚN TUỔI",
    "ĂN GÌ ĐỂ XƯƠNG CHẮC KHỎE SAU TUỔI 50?",
    "5 THỰC PHẨM GIÀU CANXI DỄ TÌM CHO NGƯỜI 50+"
  ],
  "title_keywords": ["cá nhỏ chiên giòn", "sữa chua", "món ăn giàu canxi"],
  "scenes": [
    {"text": "Cá nhỏ ăn cả xương\\nGiàu *canxi*, rẻ, dễ tìm", "seconds": 4,
     "keywords": ["cá cơm chiên", "cá nhỏ", "món cá"],
     "image_prompt": "Đĩa cá cơm chiên giòn trên bàn gỗ, ánh sáng tự nhiên, ảnh thực, khung dọc 9:16"},
    {"text": "Sữa chua\\nBổ sung *canxi* và đạm", "seconds": 4,
     "keywords": ["sữa chua", "sữa chua trái cây"],
     "image_prompt": "Hũ sữa chua trắng trên bàn gỗ, ánh sáng tự nhiên, ảnh thực, khung dọc 9:16"},
    {"text": "Đậu phụ\\nCanxi và *đạm thực vật*", "seconds": 4,
     "keywords": ["đậu phụ rán", "đậu phụ", "đậu hũ"],
     "image_prompt": "Đĩa đậu phụ rán vàng trên bàn gỗ, ánh sáng tự nhiên, ảnh thực, khung dọc 9:16"},
    {"text": "Rau cải xanh\\nCó canxi và *vitamin K*", "seconds": 4,
     "keywords": ["rau cải xanh", "rau cải", "rau xanh"],
     "image_prompt": "Bó rau cải xanh tươi trên bàn gỗ, ánh sáng tự nhiên, ảnh thực, khung dọc 9:16"},
    {"text": "Vừng đen\\nRắc vào cháo, *sữa hạt* mỗi sáng", "seconds": 4,
     "keywords": ["vừng đen", "hạt vừng", "mè đen"],
     "image_prompt": "Bát vừng đen rang trên bàn gỗ, ánh sáng tự nhiên, ảnh thực, khung dọc 9:16"}
  ],
  "caption": "Sau tuổi 50, xương dễ yếu đi ... (80–120 từ, nhắc lại tiêu đề và đủ danh sách món)",
  "hashtags": ["#xuongkhop", "#duongsinh", "#dinhduong", "#nguoicaotuoi", "#canxi"],
  "affiliates": ["Sữa hạt bổ sung canxi cho người lớn tuổi", "Vừng đen rang sẵn đóng hũ"],
  "pinned_comment": "Món nào nhà bạn hay ăn nhất? Link sản phẩm trong bình luận ghim nhé!",
  "self_review": ["\\"chữa khỏi loãng xương\\" → \\"tốt cho xương chắc khỏe\\""],
  "music_suggestions": ["Windy Hill", "Morning Coffee (piano)", "Nhạc không lời thư giãn"]
}"""


class ClaudeError(Exception):
    """The call failed or Claude's answer was unusable; `message` is shown to members, `detail` is diagnostic."""

    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.message = message
        self.detail = detail


class ScriptOutputError(ValueError):
    pass


@dataclass(frozen=True)
class GeneratedScene:
    text: str
    seconds: float
    keywords: list[str]
    image_prompt: str


@dataclass(frozen=True)
class GeneratedScript:
    titles: list[str]
    title_keywords: list[str]
    scenes: list[GeneratedScene]
    caption: str = ""
    hashtags: list[str] = field(default_factory=list)
    affiliates: list[str] = field(default_factory=list)
    pinned_comment: str = ""
    self_review: list[str] = field(default_factory=list)
    music_suggestions: list[str] = field(default_factory=list)


def build_script_prompt(template: str, topic: str, banned_words: list[str]) -> str:
    if TOPIC_PLACEHOLDER in template:
        body = template.replace(TOPIC_PLACEHOLDER, topic)
    else:
        body = f"{template.rstrip()}\n\nChủ đề: {topic}"
    parts = [body]
    if banned_words:
        quoted = ", ".join(f"\"{word}\"" for word in banned_words)
        parts.append(f"Từ cấm, không được dùng trong tiêu đề, chữ trên màn hình, caption và bình luận ghim: {quoted}.")
    parts.append(OUTPUT_FORMAT)
    return "\n\n".join(parts)


def parse_output(raw: str) -> GeneratedScript:
    """Claude's JSON as a script. Broken JSON, no title or no scene raise; small slips are repaired."""
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < start:
        raise ScriptOutputError("câu trả lời không có object JSON")
    try:
        data = json.loads(raw[start:end + 1])
    except json.JSONDecodeError as err:
        raise ScriptOutputError(f"JSON lỗi cú pháp: {err.msg} (dòng {err.lineno}, cột {err.colno})") from None
    if not isinstance(data, dict):
        raise ScriptOutputError("JSON không phải object")
    titles = _strings(data.get("titles"))[:5]
    if not titles:
        raise ScriptOutputError("thiếu tiêu đề")
    scenes = [_scene(item) for item in data.get("scenes") or [] if isinstance(item, dict)] \
        if isinstance(data.get("scenes"), list) else []
    if not scenes:
        raise ScriptOutputError("không có cảnh nội dung nào")
    return GeneratedScript(
        titles=titles,
        title_keywords=_keywords(data.get("title_keywords")),
        scenes=scenes,
        caption=_text(data.get("caption")),
        hashtags=_strings(data.get("hashtags")),
        affiliates=_strings(data.get("affiliates")),
        pinned_comment=_text(data.get("pinned_comment")),
        self_review=_strings(data.get("self_review")),
        music_suggestions=_strings(data.get("music_suggestions")),
    )


def _scene(item: dict) -> GeneratedScene:
    seconds = item.get("seconds")
    valid = isinstance(seconds, (int, float)) and not isinstance(seconds, bool) and math.isfinite(seconds)
    return GeneratedScene(
        text=_text(item.get("text")),
        seconds=float(seconds) if valid and seconds >= 1 else FALLBACK_SECONDS,
        keywords=_keywords(item.get("keywords")),
        image_prompt=_text(item.get("image_prompt")),
    )


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    items = []
    for item in value:
        if isinstance(item, dict):
            item = " — ".join(str(part) for part in item.values() if isinstance(part, (str, int, float)))
        if isinstance(item, (str, int, float)) and not isinstance(item, bool) and str(item).strip():
            items.append(str(item).strip())
    return items


def _keywords(value: object) -> list[str]:
    return [keyword[:MAX_KEYWORD_LENGTH].strip() for keyword in _strings(value)]


def call_claude(prompt: str, label: str) -> str:
    """One Messages API call; the token counts of every call go to the worker log."""
    key = config.read_env("ANTHROPIC_API_KEY")
    if not key:
        raise ClaudeError("Chưa cấu hình ANTHROPIC_API_KEY nên không gọi được Claude")
    model = config.claude_model()
    client = anthropic.Anthropic(
        api_key=key,
        # Only tests and E2E set it, to reach a local fake Claude.
        base_url=config.read_env("ANTHROPIC_BASE_URL") or None,
        timeout=REQUEST_TIMEOUT,
        max_retries=1,
    )
    extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"} if model in FALLBACK_MODELS else {}
    try:
        response = client.beta.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
            **extra,
        )
    except anthropic.AuthenticationError:
        raise ClaudeError("Key Claude (ANTHROPIC_API_KEY) không hợp lệ") from None
    except anthropic.PermissionDeniedError as err:
        raise ClaudeError("Key Claude không có quyền gọi model này", str(err)) from None
    except anthropic.RateLimitError as err:
        raise ClaudeError("Claude đang giới hạn lượt gọi hoặc đã hết hạn mức, thử lại sau", str(err)) from None
    except anthropic.BadRequestError as err:
        if "credit" in str(err).lower():
            raise ClaudeError("Tài khoản Claude đã hết hạn mức (credit), cần nạp thêm", str(err)) from None
        raise ClaudeError("Claude từ chối yêu cầu", str(err)) from None
    except anthropic.APIStatusError as err:
        raise ClaudeError(f"Claude đang lỗi hoặc quá tải (HTTP {err.status_code}), thử lại sau", str(err)) from None
    except anthropic.APITimeoutError:
        raise ClaudeError("Claude không trả lời kịp, thử lại sau") from None
    except anthropic.APIConnectionError as err:
        raise ClaudeError("Không kết nối được Claude, kiểm tra mạng rồi thử lại", str(err)) from None

    usage = response.usage
    log.info("Claude call %s: model=%s input_tokens=%s output_tokens=%s stop_reason=%s",
             label, response.model, usage.input_tokens, usage.output_tokens, response.stop_reason)
    if response.stop_reason == "refusal":
        details = getattr(response, "stop_details", None)
        raise ClaudeError("Claude từ chối viết kịch bản cho chủ đề này, hãy đổi cách diễn đạt", str(details or ""))
    return "".join(block.text for block in response.content if block.type == "text")


def generate_script(prompt: str, label: str, on_call: Callable[[], None],
                    call: Callable[[str, str], str] = call_claude) -> GeneratedScript:
    """Ask once more when the answer is unusable, then give up with the raw answer as the detail."""
    for attempt in (1, 2):
        raw = call(prompt, label)
        on_call()
        try:
            return parse_output(raw)
        except ScriptOutputError as err:
            log.warning("Claude answer unusable for %s (attempt %d): %s\n%s", label, attempt, err, raw[:4000])
            problem = err
    raise ClaudeError(
        f"Claude trả kịch bản không đúng định dạng ({problem}), đã thử lại 1 lần",
        f"Câu trả lời thô của Claude:\n{raw[:8000]}",
    )
