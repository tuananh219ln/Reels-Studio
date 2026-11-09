"""Stock video clips from Pexels and Pixabay in the picker's "Video" mode, and turning sources off."""

import shutil

import pytest
from conftest import login, make_user, make_video
from fake_services import PEXELS_KEY as FAKE_PEXELS_KEY
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
        "pexels": False,
        "unsplash": True,
        "pixabay": True,
        "wikimedia": True,
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


def test_the_sources_page_says_which_keys_are_missing(an, fakes, monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "")
    monkeypatch.setenv("IMAGE_GEN_API_KEY", "")
    payload = an.get("/api/settings/sources").json()
    pexels = next(item for item in payload["sources"] if item["id"] == "pexels")
    assert (pexels["configured"], pexels["key"]["origin"]) == (False, None)
    assert payload["ai_images"]["configured"] is False
    pixabay = next(item for item in payload["sources"] if item["id"] == "pixabay")
    assert (pixabay["configured"], pixabay["key"]["origin"]) == (True, "env")


def test_a_key_pasted_on_the_sources_page_is_used_and_never_sent_back(an, db, me, storage, fakes, monkeypatch):
    scene = scene_of(db, make_video(db, storage, me))
    monkeypatch.setenv("PEXELS_API_KEY", "")
    search = {"q": "cá", "source": "pexels"}
    assert an.get(f"/api/scenes/{scene.id}/stock-clips", params=search).status_code == 502

    saved = an.put("/api/settings/sources/pexels/key", json={"api_key": f"  {FAKE_PEXELS_KEY} "})
    assert saved.status_code == 200 and FAKE_PEXELS_KEY not in saved.text
    pexels = next(item for item in saved.json()["sources"] if item["id"] == "pexels")
    assert (pexels["configured"], pexels["key"]["origin"], pexels["key"]["hint"]) == (True, "saved", "-key")
    assert an.get(f"/api/scenes/{scene.id}/stock-clips", params=search).status_code == 200
    assert an.get("/api/stock/sources").json()[0] == {
        "id": "pexels",
        "label": "Pexels",
        "available": True,
        "missing_key": False,
        "clips": True,
    }

    # A saved key wins over the server's .env one; removing it brings the .env key back.
    monkeypatch.setenv("PEXELS_API_KEY", "an-old-env-key")
    an.put("/api/settings/sources/pexels/key", json={"api_key": "a-wrong-saved-key"})
    assert an.get(f"/api/scenes/{scene.id}/stock-clips", params=search).status_code == 502
    removed = an.put("/api/settings/sources/pexels/key", json={"api_key": ""}).json()
    assert next(item for item in removed["sources"] if item["id"] == "pexels")["key"]["origin"] == "env"


def test_the_cloudflare_token_is_pasted_beside_gemini(an, fakes, monkeypatch):
    monkeypatch.setenv("IMAGE_GEN_CF_API_KEY", "")
    payload = an.get("/api/settings/sources").json()
    assert payload["ai_provider"] == "gemini"
    assert (payload["ai_images_cloudflare"]["configured"], payload["ai_images_cloudflare"]["key"]["origin"]) == (
        False,
        None,
    )
    monkeypatch.setenv("IMAGE_GEN_PROVIDER", "cloudflare")
    saved = an.put("/api/settings/sources/cloudflare/key", json={"api_key": "a-cloudflare-api-token"})
    assert saved.status_code == 200 and "a-cloudflare-api-token" not in saved.text
    cloudflare = saved.json()["ai_images_cloudflare"]
    assert (cloudflare["configured"], cloudflare["key"]["origin"], cloudflare["key"]["hint"]) == (True, "saved", "oken")
    assert cloudflare["model"] == "@cf/black-forest-labs/flux-1-schnell" and saved.json()["ai_provider"] == "cloudflare"


def test_bad_keys_and_keyless_sources_are_refused(an):
    refused = an.put("/api/settings/sources/pixabay/key", json={"api_key": "two words"})
    assert refused.status_code == 422 and "khoảng trắng" in refused.json()["message"]
    assert an.put("/api/settings/sources/openverse/key", json={"api_key": "abc"}).status_code == 404
