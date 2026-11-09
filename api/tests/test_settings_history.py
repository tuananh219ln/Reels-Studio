"""The team's shared settings (Mô hình AI, Nguồn tư liệu, Mẫu dựng, Máy render) log every change in "Lịch sử", with
who made it and when, and never a key's value: only its last four characters (2026-11-09, Part 6)."""

import json

import pytest
from conftest import login, make_user, make_video
from fake_services import OPENAI_KEY
from sqlalchemy import select

from reels_api.models import EditLog, SceneSound
from reels_api.videos import split_scenes

LLM = "/api/settings/llm"
PEXELS_KEY = "pexels-key-abcdef-1234"


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def history(an, entity_type: str, entity_id: int | None = None) -> list[dict]:
    params = f"entity_type={entity_type}" + (f"&entity_id={entity_id}" if entity_id is not None else "")
    response = an.get(f"/api/edit-logs?{params}")
    assert response.status_code == 200, response.text
    return response.json()["entries"]


def latest(an, entity_type: str) -> dict:
    response = an.get(f"/api/edit-logs/latest?entity_type={entity_type}")
    assert response.status_code == 200, response.text
    return response.json()["latest"]


def no_secret_anywhere(db, *secrets: str) -> None:
    logged = json.dumps([row.changes for row in db.scalars(select(EditLog))], ensure_ascii=False)
    for secret in secrets:
        assert secret not in logged


def test_the_ai_settings_log_model_url_and_key_changes_but_never_the_key(an, db, fakes):
    body = {"base_url": f"{fakes.url}/openai/v1", "model": "fake-gpt-mini", "api_key": OPENAI_KEY}
    assert an.patch(f"{LLM}/openai", json=body).status_code == 200
    assert an.put(f"{LLM}/active", json={"provider": "openai"}).status_code == 200
    assert an.patch(f"{LLM}/openai", json={"remove_key": True, "model": "fake-gpt-mini"}).status_code == 422  # in use
    assert an.put(f"{LLM}/active", json={"provider": "anthropic"}).status_code == 200
    assert an.patch(f"{LLM}/openai", json={"remove_key": True}).status_code == 200
    entries = history(an, "settings_ai", 1)
    assert [entry["user"]["name"] for entry in entries] == ["Nguyễn Văn An"] * 4
    # Newest first: the key removed, back to Claude, OpenAI put in use, OpenAI set up.
    assert entries[0]["changes"] == {"openai.key": {"old": "…-key", "new": None}}
    assert entries[1]["changes"] == {"active": {"old": "OpenAI", "new": "Claude (Anthropic)"}}
    assert entries[2]["changes"] == {"active": {"old": "Claude (Anthropic)", "new": "OpenAI"}}
    assert entries[3]["changes"] == {
        "openai.base_url": {"old": "", "new": f"{fakes.url}/openai/v1"},
        "openai.model": {"old": "", "new": "fake-gpt-mini"},
        "openai.key": {"old": None, "new": "…-key"},
    }
    assert all(entry["label"] == "AI viết kịch bản" for entry in entries)
    no_secret_anywhere(db, OPENAI_KEY)
    assert latest(an, "settings_ai")["1"]["id"] == entries[0]["id"]


def test_a_save_that_changes_nothing_logs_nothing(an, fakes):
    assert an.patch(f"{LLM}/anthropic", json={"model": ""}).status_code == 200
    assert history(an, "settings_ai") == []


def test_the_sources_page_logs_each_card_on_its_own(an, db):
    assert an.put("/api/settings/sources/pexels/key", json={"api_key": PEXELS_KEY}).status_code == 200
    assert an.put("/api/settings/sources/openverse", json={"enabled": False}).status_code == 200
    assert an.put("/api/settings/image-provider", json={"provider": "cloudflare"}).status_code == 200
    assert an.put("/api/settings/image-style", json={"style": "soft light"}).status_code == 200
    assert an.put("/api/settings/auto-photos", json={"enabled": False}).status_code == 200
    assert an.put("/api/settings/sources/elevenlabs/key", json={"api_key": "eleven-key-zz-9876"}).status_code == 200
    assert an.put("/api/settings/sources/vieneu/key", json={"api_key": "vieneu-key-yy-5555"}).status_code == 200
    assert an.put("/api/settings/sources/pexels/key", json={"api_key": ""}).status_code == 200

    stock = history(an, "settings_sources", 1)
    assert [entry["changes"] for entry in stock] == [
        {"pexels.key": {"old": "…1234", "new": None}},
        {"auto_photos": {"old": True, "new": False}},
        {"openverse.enabled": {"old": True, "new": False}},
        {"pexels.key": {"old": None, "new": "…1234"}},
    ]
    services = history(an, "settings_sources", 2)
    assert [list(entry["changes"]) for entry in services] == [["elevenlabs.key"], ["ai_style"], ["ai_provider"]]
    assert services[0]["changes"]["elevenlabs.key"] == {"old": None, "new": "…9876"}
    assert services[1]["changes"]["ai_style"]["new"] == "soft light"
    assert {entry["label"] for entry in services} == {"Dịch vụ AI"}
    # VieNeu's key is pasted on Mô hình AI, so it is logged there.
    assert [entry["changes"] for entry in history(an, "settings_ai", 2)] == [
        {"vieneu.key": {"old": None, "new": "…5555"}}
    ]
    no_secret_anywhere(db, PEXELS_KEY, "eleven-key-zz-9876", "vieneu-key-yy-5555")
    assert set(latest(an, "settings_sources")) == {"1", "2"}


def test_render_machines_and_their_mode_are_logged(an, db):
    assert an.put("/api/render-nodes/setting", json={"enabled": True}).status_code == 200
    node = an.post("/api/render-nodes", json={"name": "Máy nhà An"}).json()["node"]
    assert an.delete(f"/api/render-nodes/{node['id']}").status_code == 200
    entries = history(an, "render_settings")
    assert [(entry["action"], entry["changes"]) for entry in entries] == [
        ("delete", {"machine": {"old": "Máy nhà An", "new": None}}),
        ("create", {"machine": {"old": None, "new": "Máy nhà An"}}),
        ("update", {"enabled": {"old": False, "new": True}}),
    ]
    raw = json.dumps([row.changes for row in db.scalars(select(EditLog))])
    assert "token" not in raw


def test_saved_templates_are_logged_when_made_renamed_and_deleted(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=2)
    _, scenes = split_scenes(db, video)
    scenes[0].transition = "flash"
    db.add(SceneSound(scene_id=scenes[0].id, sound="pop", start=0.4, volume="loud"))
    db.commit()
    made = an.post("/api/edit-templates", json={"name": "Vườn nhà", "video_id": video.id}).json()
    template = next(item for item in made["templates"] if item["name"] == "Vườn nhà")
    an.patch(f"/api/edit-templates/{template['id']}", json={"name": "Vườn ấm"})
    an.delete(f"/api/edit-templates/{template['id']}")
    entries = history(an, "edit_template", template["id"])
    assert [(entry["action"], entry["label"], entry["changes"]) for entry in entries] == [
        ("delete", "Vườn ấm", {"name": {"old": "Vườn ấm", "new": None}}),
        ("update", "Vườn ấm", {"name": {"old": "Vườn nhà", "new": "Vườn ấm"}}),
        ("create", "Vườn nhà", {"name": {"old": None, "new": "Vườn nhà"}}),
    ]
