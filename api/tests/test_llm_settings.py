"""/settings/ai: each LLM provider's key, base URL and model, and the provider the team writes scripts with."""

import pytest
from conftest import login, make_user
from fake_services import OPENAI_KEY
from sqlalchemy import select

from reels_api import config, crypto, llm
from reels_api.models import LlmProvider

URL = "/api/settings/llm"


@pytest.fixture
def an(client, db):
    make_user(db)
    login(client)
    return client


def provider(payload: dict, provider_id: str) -> dict:
    return next(item for item in payload["providers"] if item["id"] == provider_id)


def setup_openai(an, fakes, **extra):
    body = {"base_url": f"{fakes.url}/openai/v1", "model": "fake-gpt-mini", "api_key": f" {OPENAI_KEY} "} | extra
    return an.patch(f"{URL}/openai", json=body)


def test_settings_need_a_login(client):
    assert client.get(URL).status_code == 401
    assert client.patch(f"{URL}/openai", json={"model": "x"}).status_code == 401


def test_with_nothing_set_the_team_writes_with_claude_from_the_environment(an, fakes):
    payload = an.get(URL).json()
    assert payload["active"] == "anthropic"
    claude = provider(payload, "anthropic")
    assert (claude["key_source"], claude["key_tail"], claude["problem"]) == ("env", None, None)
    assert claude["effective_base_url"] == fakes.url and claude["effective_model"] == config.claude_model()
    openai = provider(payload, "openai")
    assert openai["key_source"] is None and openai["problem"].startswith("Chưa có API key cho OpenAI")
    # A local Ollama needs no key, only a model.
    assert provider(payload, "ollama")["problem"].startswith("Chưa chọn model cho Ollama")
    assert an.get(f"{URL}/active").json()["provider"] == "anthropic"


def test_a_saved_key_is_encrypted_and_never_sent_back(an, db, fakes):
    response = setup_openai(an, fakes)
    assert response.status_code == 200, response.text
    assert OPENAI_KEY not in response.text and OPENAI_KEY not in an.get(URL).text
    openai = provider(response.json(), "openai")
    assert (openai["key_source"], openai["key_tail"], openai["problem"]) == ("saved", "-key", None)
    assert openai["effective_model"] == "fake-gpt-mini" and openai["updated_by"] == "Nguyễn Văn An"
    row = db.scalar(select(LlmProvider).where(LlmProvider.id == "openai"))
    assert OPENAI_KEY not in row.key_encrypted and crypto.decrypt(row.key_encrypted) == OPENAI_KEY

    # Changing only the model keeps the key.
    changed = an.patch(f"{URL}/openai", json={"model": "fake-gpt-large"}).json()
    assert provider(changed, "openai")["key_source"] == "saved"
    # An empty base URL brings the provider's own back.
    restored = an.patch(f"{URL}/openai", json={"base_url": ""}).json()
    assert provider(restored, "openai")["effective_base_url"] == "https://api.openai.com/v1"


def test_bad_values_are_refused_with_a_reason(an):
    for body, message in (
        ({"base_url": "api.openai.com"}, "Base URL phải là một địa chỉ http:// hoặc https://"),
        ({"base_url": "ftp://x.vn/v1"}, "Base URL phải là một địa chỉ http:// hoặc https://"),
        ({"model": "gpt 4"}, "Tên model không hợp lệ"),
        ({"api_key": "  "}, "Hãy dán API key"),
        ({"api_key": "two words"}, "API key không hợp lệ"),
    ):
        refused = an.patch(f"{URL}/openai", json=body)
        assert refused.status_code == 422 and refused.json()["message"].startswith(message), body
    assert an.patch(f"{URL}/nope", json={"model": "x"}).status_code == 404


def test_only_a_ready_provider_can_be_put_in_use(an, fakes):
    refused = an.put(f"{URL}/active", json={"provider": "openai"})
    assert (refused.status_code, refused.json()["message"]) == (
        422,
        "Chưa có API key cho OpenAI: nhập trong Cài đặt › Mô hình AI",
    )
    refused = an.put(f"{URL}/active", json={"provider": "custom"})
    assert refused.json()["message"].startswith("Chưa có API key cho Tùy chỉnh")

    setup_openai(an, fakes)
    payload = an.put(f"{URL}/active", json={"provider": "openai"}).json()
    assert payload["active"] == "openai" and provider(payload, "openai")["active"] is True
    assert an.get(f"{URL}/active").json() == {
        "provider": "openai",
        "name": "OpenAI",
        "model": "fake-gpt-mini",
        "problem": None,
    }

    # The provider in use cannot lose its key or model: the next script job would fail.
    refused = an.patch(f"{URL}/openai", json={"remove_key": True})
    assert refused.status_code == 422 and "OpenAI đang được dùng để viết kịch bản" in refused.json()["message"]
    assert provider(an.get(URL).json(), "openai")["key_source"] == "saved"
    # Another provider's key can go.
    an.patch(f"{URL}/deepseek", json={"api_key": "sk-deepseek-1234"})
    removed = an.patch(f"{URL}/deepseek", json={"remove_key": True}).json()
    assert provider(removed, "deepseek")["key_source"] is None


def test_check_connection_lists_the_models_without_spending_tokens(an, fakes):
    setup_openai(an, fakes)
    assert an.post(f"{URL}/openai/models").json() == {"models": ["fake-gemini-flash", "fake-gpt-mini"]}
    assert fakes.chat_requests == [] and fakes.claude_prompts == []

    claude = an.post(f"{URL}/anthropic/models")
    assert claude.json() == {"models": ["claude-haiku-5-5", "claude-sonnet-5-5"]}

    an.patch(f"{URL}/openai", json={"api_key": "sai-key"})
    refused = an.post(f"{URL}/openai/models")
    assert refused.status_code == 422 and refused.json()["message"].startswith("API key của OpenAI không hợp lệ")

    refused = an.post(f"{URL}/groq/models")
    assert refused.json()["message"] == "Chưa có API key cho Groq"


def test_an_unreadable_key_asks_to_be_pasted_again(an, fakes):
    setup_openai(an, fakes)
    (config.storage_dir() / crypto.KEY_FILE).unlink()
    openai = provider(an.get(URL).json(), "openai")
    assert (openai["key_source"], openai["key_unreadable"]) == (None, True)
    assert openai["problem"].startswith("Chưa có API key cho OpenAI")


def test_labels_name_the_provider_and_model():
    assert llm.label("deepseek", "deepseek-chat") == "DeepSeek · deepseek-chat"
    assert llm.label(None, None) is None
