"""Stock video clips from Pexels and Pixabay in the picker's "Video" mode, and turning sources off."""

import shutil

import pytest
from conftest import login, make_user, make_video
from sqlalchemy import select

from reels_api.models import Scene

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffmpeg/ffprobe không có trên PATH")


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def scene_of(db, video, title=False) -> Scene:
    return db.scalar(
        select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(title)).order_by(Scene.position).limit(1)
    )


def test_sources_say_which_offer_clips(an, fakes):
    sources = {item["id"]: item for item in an.get("/api/stock/sources").json()}
    assert sources["pexels"]["clips"] and sources["pixabay"]["clips"] and not sources["openverse"]["clips"]


@pytest.mark.parametrize("source", ["pexels", "pixabay"])
def test_clip_search_lists_stills_and_lengths(an, db, me, storage, fakes, source):
    scene = scene_of(db, make_video(db, storage, me))
    result = an.get(f"/api/scenes/{scene.id}/stock-clips", params={"q": " cá  cơm ", "source": source}).json()
    assert result["keyword"] == "cá cơm" and len(result["hits"]) == 3
    hit = result["hits"][0]
    assert hit["seconds"] == 3 and hit["preview"].endswith(".jpg")
    # The file closest to the 1080 px frame is the one offered, not the small one.
    assert not hit["url"].endswith("-sd.mp4")
    assert fakes.clip_queries == [(source, "cá cơm")]


@needs_ffmpeg
def test_a_chosen_clip_is_stored_with_the_scene_like_an_upload(an, db, me, storage, fakes):
    video = make_video(db, storage, me)
    scene = scene_of(db, video)
    hit = an.get(f"/api/scenes/{scene.id}/stock-clips", params={"q": "cá cơm", "source": "pexels"}).json()["hits"][1]
    payload = an.post(
        f"/api/scenes/{scene.id}/stock-clips", json={"source": "pexels", "keyword": "cá cơm", "id": hit["id"]}
    ).json()
    saved = payload["scenes"][0]
    assert saved["video"]["seconds"] == pytest.approx(3, abs=0.05) and saved["has_image"] is False
    # 3 s of clip minus the two 0.2 s crossfade halves around a content scene.
    assert saved["seconds"] == 2.6
    db.refresh(scene)
    assert storage.exists(scene.video_key) and len(fakes.clip_downloads) == 1


def test_a_clip_not_in_the_results_is_refused(an, db, me, storage, fakes):
    scene = scene_of(db, make_video(db, storage, me))
    refused = an.post(f"/api/scenes/{scene.id}/stock-clips", json={"source": "pixabay", "keyword": "cá", "id": "999"})
    assert refused.status_code == 422 and refused.json()["message"].startswith("Video này không có trong kết quả")
    assert fakes.clip_downloads == []


def test_a_source_turned_off_disappears_from_the_picker(an, db, me, storage, fakes):
    scene = scene_of(db, make_video(db, storage, me))
    payload = an.put("/api/settings/sources/pexels", json={"enabled": False}).json()
    assert {item["id"]: item["enabled"] for item in payload["sources"]} == {
        "pixabay": True,
        "pexels": False,
        "openverse": True,
    }
    sources = {item["id"]: item for item in an.get("/api/stock/sources").json()}
    assert not sources["pexels"]["available"] and not sources["pexels"]["clips"]
    refused = an.get(f"/api/scenes/{scene.id}/stock-clips", params={"q": "cá", "source": "pexels"})
    assert refused.status_code == 422
    refused = an.get(f"/api/scenes/{scene.id}/stock", params={"q": "cá", "source": "pexels"})
    assert refused.status_code == 422 and "đang tắt" in refused.json()["message"]
    an.put("/api/settings/sources/pexels", json={"enabled": True})
    assert an.get(f"/api/scenes/{scene.id}/stock-clips", params={"q": "cá", "source": "pexels"}).status_code == 200


def test_the_sources_page_says_which_keys_are_missing(an, monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "")
    payload = an.get("/api/settings/sources").json()
    pexels = next(item for item in payload["sources"] if item["id"] == "pexels")
    assert (pexels["configured"], pexels["key_name"]) == (False, "PEXELS_API_KEY")
    assert payload["ai_images"]["configured"] is False
