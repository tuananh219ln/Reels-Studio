"""Wikimedia Commons and Unsplash in the stock picker, "Tìm ảnh" and "Tự tìm ảnh", and each topic group's source order
(brief docs/specs/them-nguon-anh-stock)."""

import pytest
from conftest import first_topic, login, make_user, make_video
from fake_services import UNSPLASH_KEY
from sqlalchemy import select

from reels_api import auto_photos, source_keys
from reels_api.models import Job, Scene


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def scenes_of(db, video) -> list[Scene]:
    return db.scalars(
        select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)).order_by(Scene.position)
    ).all()


def search(an, scene_id, source, q="canh chua", **params):
    return an.get(f"/api/scenes/{scene_id}/stock", params={"q": q, "source": source, **params})


def choose(an, scene_id, source, url, q="canh chua", orientation="vertical"):
    return an.post(
        f"/api/scenes/{scene_id}/stock", json={"source": source, "keyword": q, "url": url, "orientation": orientation}
    )


def scene_payload(an, video, scene_id) -> dict:
    data = an.get(f"/api/videos/{video.id}").json()
    return next(scene for scene in [data["title_scene"], *data["scenes"]] if scene and scene["id"] == scene_id)


# --- Wikimedia ---


def test_wikimedia_searches_the_vietnamese_words_for_photos_only_and_says_who_asks(an, db, me, storage, fakes):
    video = make_video(db, storage, me)
    found = search(an, scenes_of(db, video)[0].id, "wikimedia")
    assert found.status_code == 200, found.text
    assert len(found.json()["hits"]) == 3
    assert fakes.wikimedia_queries == ["canh chua filetype:bitmap"]
    # Wikimedia's policy: a User-Agent that names the app and a way to reach its owners.
    assert "ReelsStudio" in fakes.wikimedia_agents[0] and "https://" in fakes.wikimedia_agents[0]


def test_wikimedia_keeps_the_search_order_and_leaves_out_what_is_not_a_photo(an, db, me, storage, fakes):
    video = make_video(db, storage, me)
    fakes.wikimedia_results["canh chua"] = [
        {"name": "first"},
        {"name": "drawing", "mime": "image/svg+xml"},
        {"name": "scan", "mime": "image/tiff"},
        {"name": "wide", "width": 1600, "height": 900},
        {"name": "second"},
    ]
    hits = search(an, scenes_of(db, video)[0].id, "wikimedia").json()["hits"]
    assert [hit["url"] for hit in hits] == [fakes.image_url("first"), fakes.image_url("second")]
    every = search(an, scenes_of(db, video)[0].id, "wikimedia", orientation="all").json()["hits"]
    assert fakes.image_url("wide") in [hit["url"] for hit in every]


def test_a_wikimedia_photo_that_needs_credit_is_flagged_on_the_scene(an, db, me, storage, fakes):
    video = make_video(db, storage, me, images=False)
    scene_id = scenes_of(db, video)[0].id
    fakes.wikimedia_results["canh chua"] = [
        {"name": "byphoto", "license": "CC BY-SA 4.0", "artist": "<a href='x'>Nguyễn Văn A</a>", "attribution": "true"}
    ]
    chosen = choose(an, scene_id, "wikimedia", fakes.image_url("byphoto"))
    assert chosen.status_code == 200, chosen.text
    scene = scene_payload(an, video, scene_id)
    assert scene["image_credit"] == {
        "license": "CC BY-SA 4.0",
        "author": "Nguyễn Văn A",
        "page": f"{fakes.url}/wikimedia/wiki/File:byphoto.jpg",
        "source": "Wikimedia Commons",
        "line": "Ảnh: Nguyễn Văn A, CC BY-SA 4.0 (Wikimedia Commons)",
    }
    warning = next(text for text in scene["warnings"] if "ghi nguồn" in text)
    assert "Nguyễn Văn A, CC BY-SA 4.0" in warning and "chia sẻ lại" in warning


def test_a_public_domain_wikimedia_photo_needs_no_credit(an, db, me, storage, fakes):
    video = make_video(db, storage, me, images=False)
    scene_id = scenes_of(db, video)[0].id
    fakes.wikimedia_results["canh chua"] = [{"name": "pd", "license": "Public domain"}]
    assert choose(an, scene_id, "wikimedia", fakes.image_url("pd")).status_code == 200
    scene = scene_payload(an, video, scene_id)
    assert scene["image_credit"] is None
    assert not [text for text in scene["warnings"] if "ghi nguồn" in text]


def test_the_credit_goes_when_another_photo_replaces_it(an, db, me, storage, fakes):
    video = make_video(db, storage, me, images=False)
    scene_id = scenes_of(db, video)[0].id
    fakes.wikimedia_results["canh chua"] = [{"name": "by", "license": "CC BY 2.0", "attribution": "true"}]
    assert choose(an, scene_id, "wikimedia", fakes.image_url("by")).status_code == 200
    first_pexels = search(an, scene_id, "pexels", q="soup").json()["hits"][0]["url"]
    assert choose(an, scene_id, "pexels", first_pexels, q="soup").status_code == 200
    scene = scene_payload(an, video, scene_id)
    assert scene["image_credit"] is None
    assert not [text for text in scene["warnings"] if "ghi nguồn" in text]


def test_wikimedia_busy_says_to_wait(an, db, me, storage, fakes):
    video = make_video(db, storage, me)
    fakes.wikimedia_mode = "rate_limit"
    refused = search(an, scenes_of(db, video)[0].id, "wikimedia")
    assert refused.status_code == 502 and "Wikimedia" in refused.json()["message"]


# --- Unsplash ---


def test_unsplash_searches_with_the_key_in_a_header(an, db, me, storage, fakes):
    video = make_video(db, storage, me)
    found = search(an, scenes_of(db, video)[0].id, "unsplash", q="vegetable soup")
    assert found.status_code == 200, found.text
    assert len(found.json()["hits"]) == 3
    asked = [query for name, query in fakes.stock_searches if name == "unsplash"][-1]
    assert asked["orientation"] == "portrait" and "client_id" not in asked


def test_without_a_key_unsplash_says_it_is_not_set_up(an, db, me, storage, fakes, monkeypatch):
    monkeypatch.setenv("UNSPLASH_ACCESS_KEY", "")
    video = make_video(db, storage, me)
    refused = search(an, scenes_of(db, video)[0].id, "unsplash", q="vegetable soup")
    assert refused.status_code == 502
    assert "Chưa cấu hình key Unsplash" in refused.json()["message"]
    sources = {source["id"]: source for source in an.get("/api/stock/sources").json()}
    assert sources["unsplash"]["available"] is False and sources["unsplash"]["missing_key"] is True
    assert sources["wikimedia"]["available"] is True and sources["wikimedia"]["missing_key"] is False


def test_a_key_pasted_on_the_settings_page_is_used(an, db, me, storage, fakes, monkeypatch):
    monkeypatch.setenv("UNSPLASH_ACCESS_KEY", "")
    source_keys.save(db, "unsplash", UNSPLASH_KEY, me.id)
    db.commit()
    video = make_video(db, storage, me)
    assert search(an, scenes_of(db, video)[0].id, "unsplash", q="vegetable soup").status_code == 200


def test_unsplash_out_of_calls_is_not_mistaken_for_a_bad_key(an, db, me, storage, fakes):
    video = make_video(db, storage, me)
    fakes.unsplash_mode = "rate_limit"
    refused = search(an, scenes_of(db, video)[0].id, "unsplash", q="vegetable soup")
    assert refused.status_code == 502
    message = refused.json()["message"]
    assert "Hết lượt Unsplash" in message and "không hợp lệ" not in message


def test_a_wrong_unsplash_key_says_so(an, db, me, storage, fakes, monkeypatch):
    monkeypatch.setenv("UNSPLASH_ACCESS_KEY", "wrong")
    video = make_video(db, storage, me)
    refused = search(an, scenes_of(db, video)[0].id, "unsplash", q="vegetable soup")
    assert refused.status_code == 502 and "Key Unsplash không hợp lệ" in refused.json()["message"]


def test_choosing_an_unsplash_photo_tells_unsplash_it_was_downloaded(an, db, me, storage, fakes):
    video = make_video(db, storage, me, images=False)
    scene_id = scenes_of(db, video)[0].id
    fakes.unsplash_results["vegetable soup"] = ["soup1", "soup2"]
    assert choose(an, scene_id, "unsplash", fakes.image_url("soup2"), q="vegetable soup").status_code == 200
    assert fakes.unsplash_downloads == ["soup2"]


# --- Order: the app's, and each topic group's ---


def test_the_sources_come_in_the_app_order(an, db, me, storage, fakes):
    ids = [source["id"] for source in an.get("/api/stock/sources").json()]
    assert ids == ["pexels", "unsplash", "pixabay", "wikimedia", "openverse"]


def test_a_group_sets_its_own_order_and_its_videos_follow_it(an, db, me, storage, fakes):
    topic = first_topic(db)
    saved = an.patch(f"/api/knowledge/topics/{topic.id}", json={"stock_order": ["wikimedia", "pexels"]})
    assert saved.status_code == 200, saved.text
    group = next(item for item in saved.json()["topics"] if item["id"] == topic.id)
    # Sources left out follow in the app's order, so none is ever lost.
    assert group["stock_order"] == ["wikimedia", "pexels", "unsplash", "pixabay", "openverse"]
    video = make_video(db, storage, me)
    ids = [source["id"] for source in an.get("/api/stock/sources", params={"video_id": video.id}).json()]
    assert ids[0] == "wikimedia"
    # "Tìm ảnh" without a source asks the group's first.
    found = an.post(f"/api/scenes/{scenes_of(db, video)[0].id}/find-image")
    assert found.status_code == 200, found.text
    assert fakes.wikimedia_queries and not fakes.pexels_queries


def test_a_new_group_starts_on_the_app_order(an, db, me, storage, fakes):
    created = an.post("/api/knowledge/topics", json={"name": "Món Việt"})
    group = next(item for item in created.json()["topics"] if item["name"] == "Món Việt")
    assert group["stock_order"] == ["pexels", "unsplash", "pixabay", "wikimedia", "openverse"]
    assert group["stock_order_custom"] is False


def test_an_unknown_source_in_a_group_order_is_refused(an, db, me, storage, fakes):
    topic = first_topic(db)
    refused = an.patch(f"/api/knowledge/topics/{topic.id}", json={"stock_order": ["google"]})
    assert refused.status_code == 422 and "google" in refused.json()["message"]
    # An empty list goes back to the app's order.
    an.patch(f"/api/knowledge/topics/{topic.id}", json={"stock_order": ["wikimedia"]})
    reset = an.patch(f"/api/knowledge/topics/{topic.id}", json={"stock_order": []})
    group = next(item for item in reset.json()["topics"] if item["id"] == topic.id)
    assert group["stock_order_custom"] is False and group["stock_order"][0] == "pexels"


def test_auto_photos_ask_the_group_first_source_and_note_its_credit(an, db, me, storage, fakes):
    topic = first_topic(db)
    topic.stock_order = ["wikimedia"]
    db.commit()
    video = make_video(db, storage, me, images=False)
    for keywords in ("canh chua",):
        for scene in db.scalars(select(Scene).where(Scene.video_id == video.id)):
            scene.keywords = [keywords]
    db.commit()
    fakes.wikimedia_results["canh chua"] = [
        {"name": f"by{n}", "license": "CC BY 4.0", "attribution": "true"} for n in range(10)
    ]
    job = Job(video_id=video.id, kind="photos", status="running", created_by_id=me.id)
    db.add(job)
    db.commit()
    auto_photos.run(db, job, storage)
    assert fakes.wikimedia_queries and not fakes.pexels_queries
    scene = scenes_of(db, video)[0]
    assert scene.image_auto and scene.image_credit["license"] == "CC BY 4.0"
    assert any("ghi nguồn" in text for text in scene_payload(an, video, scene.id)["warnings"])
