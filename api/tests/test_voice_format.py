"""A topic group's "Giọng đọc theo vai" (voice_format.py) and the MCP tools a build reads and uploads voices with."""

import subprocess

import pytest
from alembic import command
from alembic.config import Config
from conftest import API_DIR, first_topic, login, make_user, make_video
from sqlalchemy import insert, select
from sqlalchemy.orm import Session
from test_mcp import call, grant, mcp_client, payload  # noqa: F401  (mcp_client is a fixture)
from test_voice import needs_ffmpeg

from reels_api import remote_media, voice_format
from reels_api.models import KnowledgeTopic, Scene
from reels_api.video_options import OptionError

CHI = "5yEPTrA0uAhZsBEhHjfi"
THREADS = {
    "mode": "multi",
    "roles": [
        {"role": "op", "voices": [CHI, "pNInz6obpgDQGcFmaJgB"], "note": "  Theo   vibe "},
        {"role": "comment", "source": "provider", "voices": ["gemini:Puck", "gemini:Puck", "gemini:Leda"]},
        {"role": "cta", "source": "custom"},
    ],
    "rules": {"max_gemini_scenes": 2, "excited_tag": "Chỉ ElevenLabs, 1 lần mỗi video"},
}


def test_a_format_is_cleaned():
    assert voice_format.clean(None) == {} and voice_format.clean({}) == {}
    single = voice_format.clean({"mode": "single", "roles": [{"role": "all", "voice": CHI, "volume": 100}]})
    assert single == {"mode": "single", "roles": [{"role": "all", "source": "provider", "voice": CHI, "volume": 100}]}
    multi = voice_format.clean(THREADS)
    assert multi["roles"][0] == {
        "role": "op",
        "source": "provider",
        "voices": [CHI, "pNInz6obpgDQGcFmaJgB"],
        "note": "Theo vibe",
    }
    assert multi["roles"][1]["voices"] == ["gemini:Puck", "gemini:Leda"], "a voice is rotated once"
    assert multi["roles"][2] == {"role": "cta", "source": "custom"}
    assert multi["rules"] == THREADS["rules"]


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ({"mode": "both", "roles": [{"role": "all", "voice": CHI}]}, "Kiểu giọng"),
        ({"mode": "single", "roles": []}, "ít nhất một vai"),
        ({"mode": "single", "roles": [{"role": "narrator", "voice": CHI}]}, "Vai “narrator”"),
        ({"mode": "single", "roles": [{"role": "all", "voice": CHI, "source": "tts"}]}, "Nguồn giọng “tts”"),
        ({"mode": "single", "roles": [{"role": "op", "voice": CHI}]}, "một vai “all”"),
        ({"mode": "single", "roles": [{"role": "all", "voices": [CHI]}]}, "không xoay vòng"),
        ({"mode": "multi", "roles": [{"role": "all", "voice": CHI}]}, "không dùng vai “all”"),
        ({"mode": "multi", "roles": [{"role": "op", "voice": CHI}, {"role": "op", "voice": CHI}]}, "một lần"),
        ({"mode": "single", "roles": [{"role": "all"}]}, "chưa có giọng"),
        ({"mode": "single", "roles": [{"role": "all", "source": "custom", "voice": CHI}]}, "file tải lên"),
        ({"mode": "single", "roles": [{"role": "all", "voice": "hai từ"}]}, "Mã giọng"),
        ({"mode": "single", "roles": [{"role": "all", "voice": CHI, "volume": 101}]}, "Âm lượng"),
        ({"mode": "single", "roles": [{"role": "all", "voice": CHI, "speed": 1}]}, "Vai đọc không hợp lệ"),
        ({"mode": "multi", "roles": [{"role": "op", "voice": CHI}], "rules": {"max_gemini_scenes": -1}}, "Gemini"),
        ({"mode": "multi", "roles": [{"role": "op", "voice": CHI}], "rules": {"other": 1}}, "Luật"),
        ({"mode": "single", "roles": [{"role": "all", "voice": CHI}], "extra": 1}, "không hợp lệ"),
    ],
)
def test_a_wrong_format_is_refused_with_a_reason(value, message):
    with pytest.raises(OptionError, match=message):
        voice_format.clean(value)


def test_a_group_saves_its_format_and_it_is_in_the_history(client, db):
    make_user(db)
    login(client)
    group = first_topic(db)
    saved = client.patch(f"/api/knowledge/topics/{group.id}", json={"voice_format": THREADS})
    assert saved.status_code == 200, saved.text
    shown = next(row for row in saved.json()["topics"] if row["id"] == group.id)
    assert shown["voice_format"] == voice_format.clean(THREADS)
    # The group's voice and backup are not touched by it.
    assert shown["voice_id"] == "" and shown["voice_backup_id"] == ""
    history = client.get(f"/api/edit-logs?entity_type=knowledge_topic&entity_id={group.id}").json()["entries"]
    assert history[0]["changes"]["voice_format"]["new"] == voice_format.clean(THREADS)
    wrong = client.patch(f"/api/knowledge/topics/{group.id}", json={"voice_format": {"mode": "single", "roles": []}})
    assert wrong.status_code == 422 and "ít nhất một vai" in wrong.json()["message"]
    cleared = client.patch(f"/api/knowledge/topics/{group.id}", json={"voice_format": {}})
    assert next(row for row in cleared.json()["topics"] if row["id"] == group.id)["voice_format"] == {}


def test_an_assistant_reads_the_groups_voices(mcp_client, db):  # noqa: F811
    _, _, tokens, _ = grant(mcp_client, db)
    group = first_topic(db)
    group.voice_id, group.voice_backup_id = CHI, "vieneu:Huyền My"
    group.voice_format = voice_format.clean(THREADS)
    db.commit()
    groups = payload(call(mcp_client, tokens["access_token"], "list_topic_groups"))["topics"]
    row = next(row for row in groups if row["id"] == group.id)
    assert (row["voice_id"], row["voice_backup_id"]) == (CHI, "vieneu:Huyền My")
    assert row["voice_format"] == voice_format.clean(THREADS)


@needs_ffmpeg
def test_an_assistant_uploads_a_scene_voice_from_a_link(mcp_client, db, storage, tmp_path, monkeypatch):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    video = make_video(db, storage, user, scene_count=1)
    scene = db.scalar(select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)))
    path = tmp_path / "voice.mp3"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=duration=1.5", "-c:a", "libmp3lame", str(path)],
        check=True,
    )
    asked = []
    monkeypatch.setattr(remote_media, "download_music", lambda url, folder: asked.append(url) or path.read_bytes())
    url = "https://drive.google.com/uc?export=download&id=abc"
    answer = call(mcp_client, tokens["access_token"], "upload_scene_voice", scene_id=scene.id, url=url)
    assert not answer.get("isError"), answer
    shown = next(row for row in payload(answer)["scenes"] if row["id"] == scene.id)
    assert shown["voice_custom"] is True and shown["voice_name"] == "uc"
    assert asked == [url]
    db.expire_all()
    assert db.get(Scene, scene.id).voice_seconds == pytest.approx(1.5, abs=0.1)
    # A link that is not an MP3 says so.
    monkeypatch.setattr(remote_media, "download_music", lambda url, folder: b"<html>")
    assert call(mcp_client, tokens["access_token"], "upload_scene_voice", scene_id=scene.id, url=url)["isError"]


def test_the_seeded_groups_have_valid_formats():
    """The formats migration 0127 starts the team's groups with pass the same checks as an edit."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0127_voice_format.py"
    spec = importlib.util.spec_from_file_location("migration_0127", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name, value in module.SEED.items():
        assert voice_format.clean(value) == value, name
    assert KnowledgeTopic.voice_format is not None


def _load_migration(file_name: str):
    import importlib.util

    path = API_DIR / "migrations" / "versions" / file_name
    spec = importlib.util.spec_from_file_location(file_name.removesuffix(".py"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_0128_moves_groups_6_7_and_10_to_huyen_my(engine):
    """Migration 0128: the three groups 0127 seeded with Chi read with VieNeu Huyền My; a group a member already edited
    keeps its format; going back restores 0127's seed."""
    seed = _load_migration("0127_voice_format.py").SEED
    changes = _load_migration("0128_group_voice_huyen_my.py").CHANGES
    for name, (old, new) in changes.items():
        assert seed[name] == old, name
        assert voice_format.clean(new) == new, name
    gia, an_lanh, test_group = "Già Mà Khỏe – Dưỡng sinh sau 50", "Ăn Lành Sống Khỏe – Sức khỏe", "Nhóm test"
    edited = {"mode": "single", "roles": [{"role": "all", "source": "custom"}]}
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", engine.url.render_as_string(hide_password=False))
    config.attributes["configure_logger"] = False

    def formats() -> dict:
        with Session(engine) as session:
            # Two columns, not whole rows: the database is at revision 0127 here, before later columns existed.
            rows = session.execute(
                select(KnowledgeTopic.name, KnowledgeTopic.voice_format).where(
                    KnowledgeTopic.name.in_([gia, an_lanh, test_group])
                )
            )
            return {name: voice_format for name, voice_format in rows}

    command.downgrade(config, "0127")
    try:
        with Session(engine) as session:
            # Core inserts: the ORM would read back columns that do not exist yet at revision 0127.
            session.execute(
                insert(KnowledgeTopic.__table__),
                [
                    {"name": gia, "voice_format": seed[gia]},
                    {"name": an_lanh, "voice_format": edited},
                    {"name": test_group, "voice_format": seed[test_group]},
                ],
            )
            session.commit()
        command.upgrade(config, "head")
        after = formats()
        assert after[gia]["roles"] == [{"role": "all", "source": "provider", "voice": "vieneu:Huyền My"}]
        assert after[an_lanh] == edited
        assert after[test_group]["roles"][0]["voice"] == "vieneu:Huyền My"
        assert after[test_group]["roles"][0]["note"].startswith("Giữ nguyên giọng gốc")
        command.downgrade(config, "0127")
        assert formats() == {gia: seed[gia], an_lanh: edited, test_group: seed[test_group]}
    finally:
        command.upgrade(config, "head")
        with Session(engine) as session:
            for row in session.scalars(
                select(KnowledgeTopic).where(KnowledgeTopic.name.in_([gia, an_lanh, test_group]))
            ):
                session.delete(row)
            session.commit()
