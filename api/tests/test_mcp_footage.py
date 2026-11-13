"""The assistant (MCP) fills scenes with footage by looking at frames itself: no LLM call of the team's."""

import json

import pytest
from conftest import clip_bytes, make_video, needs_ffmpeg
from sqlalchemy import select
from test_mcp import call, grant, mcp_client, payload  # noqa: F401  (mcp_client is a fixture)

from reels_api import footage_tools, youtube_footage
from reels_api.models import Job, Scene

URL = "https://www.youtube.com/watch?v=abcdefghijk"


@pytest.fixture
def source(tmp_path, monkeypatch):
    monkeypatch.setattr(footage_tools, "CACHE", tmp_path / "cache")
    path = tmp_path / "source.mp4"
    path.write_bytes(clip_bytes(tmp_path, seconds=8, size="576x1024"))
    monkeypatch.setattr(youtube_footage, "search", lambda keyword: [URL])
    monkeypatch.setattr(youtube_footage, "download", lambda url, folder: _copy(path, folder))
    return path


def _copy(path, folder):
    target = folder / "source.mp4"
    target.write_bytes(path.read_bytes())
    return target


def bare_scene(db, storage, user, keywords=("múc canh bí đỏ",)):
    video = make_video(db, storage, user, scene_count=1, images=False)
    scene = db.scalar(select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)))
    scene.seconds, scene.keywords, scene.keywords_en = 2, list(keywords), ["serving pumpkin soup"]
    db.commit()
    return video, scene


def test_scenes_without_media_are_listed_for_the_member_only(mcp_client, db, storage):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    video, scene = bare_scene(db, storage, user)
    listed = payload(call(mcp_client, token, "list_scenes_missing_media"))
    assert [(row["video_id"], row["scene_id"]) for row in listed["scenes"] if row["scene_id"] == scene.id] == [
        (video.id, scene.id)
    ]
    row = next(row for row in listed["scenes"] if row["scene_id"] == scene.id)
    assert row["keywords"] == ["múc canh bí đỏ"] and row["has_photo"] is False
    scene.image_key = "x.jpg"
    scene.image_auto = True
    db.commit()
    assert scene.id not in [
        r["scene_id"] for r in payload(call(mcp_client, token, "list_scenes_missing_media"))["scenes"]
    ]
    upgraded = payload(call(mcp_client, token, "list_scenes_missing_media", upgrade_photos=True))
    assert scene.id in [r["scene_id"] for r in upgraded["scenes"]]


@needs_ffmpeg
def test_the_assistant_finds_looks_at_and_uses_a_clip_without_any_llm_call(
    mcp_client,
    db,
    storage,
    source,  # noqa: F811
):
    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    video, scene = bare_scene(db, storage, user)
    found = call(mcp_client, token, "find_scene_footage", scene_id=scene.id, keyword="múc canh bí đỏ")
    assert not found.get("isError"), found
    listing = json.loads(found["content"][0]["text"])["candidates"]
    assert len(listing) == 1 and listing[0]["url"] == URL
    windows = listing[0]["windows"]
    assert 2 <= len(windows) <= 6
    assert [item["type"] for item in found["content"][1:]] == ["text", "image"] * len(windows)

    used = call(mcp_client, token, "use_scene_footage", scene_id=scene.id, candidate=listing[0]["candidate"], window=1)
    assert not used.get("isError"), used
    db.refresh(scene)
    assert scene.video_key and storage.exists(scene.video_key) and scene.image_key is None
    assert scene.image_source == URL and scene.image_auto is True and scene.video_sound is False
    assert scene.video_seconds >= scene.seconds + 0.39
    assert not db.scalars(select(Job).where(Job.video_id == video.id)).all(), "no job, no paid call"
    # The candidate is consumed, and another scene's id never matches it.
    again = call(mcp_client, token, "use_scene_footage", scene_id=scene.id, candidate=listing[0]["candidate"], window=0)
    assert again["isError"]


@needs_ffmpeg
def test_a_candidate_belongs_to_its_scene_and_bad_inputs_are_refused(mcp_client, db, storage, source):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    _, scene = bare_scene(db, storage, user)
    _, other = bare_scene(db, storage, user)
    listing = json.loads(
        call(mcp_client, token, "find_scene_footage", scene_id=scene.id, keyword="canh")["content"][0]["text"]
    )["candidates"]
    code = listing[0]["candidate"]
    assert call(mcp_client, token, "use_scene_footage", scene_id=other.id, candidate=code, window=0)["isError"]
    assert call(mcp_client, token, "use_scene_footage", scene_id=scene.id, candidate=code, window=99)["isError"]
    assert call(mcp_client, token, "use_scene_footage", scene_id=scene.id, candidate="../../etc", window=0)["isError"]
    assert call(mcp_client, token, "use_scene_footage", scene_id=scene.id, candidate="0" * 16, window=0)["isError"]
    db.refresh(scene)
    assert scene.video_key is None
    # A single-backdrop video's content scenes take photos, not clips.
    scene.video.mode = "single"
    db.commit()
    assert call(mcp_client, token, "find_scene_footage", scene_id=scene.id, keyword="canh")["isError"]


def test_a_stock_source_without_a_key_says_so(mcp_client, db, storage, source, monkeypatch):  # noqa: F811
    from reels_api import source_keys

    user, _, tokens, _ = grant(mcp_client, db)
    _, scene = bare_scene(db, storage, user)
    monkeypatch.setattr(source_keys, "get", lambda db, name: "")
    result = call(
        mcp_client, tokens["access_token"], "find_scene_footage", scene_id=scene.id, keyword="canh", source="pexels"
    )
    assert result["isError"] and "key" in result["content"][0]["text"]


def test_no_usable_clip_tells_the_assistant_to_try_other_words(mcp_client, db, storage, source, monkeypatch):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    _, scene = bare_scene(db, storage, user)
    monkeypatch.setattr(youtube_footage, "search", lambda keyword: [])
    result = call(mcp_client, tokens["access_token"], "find_scene_footage", scene_id=scene.id, keyword="zzz")
    assert not result.get("isError") and "thử từ khóa khác" in result["content"][0]["text"]
