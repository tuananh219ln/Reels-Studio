"""The team's "Kho tư liệu" (routes_media.py): folders uploaded file by file, links downloaded into it, items copied
into scenes, and the MCP tools the assistant chooses with."""

import pytest
from conftest import clip_bytes, login, make_user, make_video, needs_ffmpeg, photo_bytes
from sqlalchemy import select
from test_mcp import call, grant, mcp_client, payload  # noqa: F401  (mcp_client is a fixture)

from reels_api import remote_media
from reels_api.models import MediaItem, Scene


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def first_scene(db, video) -> Scene:
    return db.scalar(
        select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)).order_by(Scene.position).limit(1)
    )


def send_photo(client, name="noi.jpg", folder="", data=None):
    return client.post(
        "/api/media", files={"file": (name, data or photo_bytes(), "image/jpeg")}, data={"folder": folder}
    )


def test_a_dragged_folder_keeps_its_path_and_lists_by_folder(an, db, storage):
    for name, folder in (("a.jpg", "Nồi chiên 5L/cảnh quay"), ("b.jpg", "Nồi chiên 5L"), ("c.jpg", "Máy xay")):
        made = send_photo(an, name, folder)
        assert made.status_code == 201, made.text
    assert made.json()["folder"] == "Máy xay" and made.json()["kind"] == "photo"
    listed = an.get("/api/media", params={"folder": "Nồi chiên 5L"}).json()
    assert sorted(item["name"] for item in listed["items"]) == ["a.jpg", "b.jpg"]  # the subfolder too
    assert {row["folder"]: row["count"] for row in listed["folders"]} == {
        "Máy xay": 1,
        "Nồi chiên 5L": 1,
        "Nồi chiên 5L/cảnh quay": 1,
    }
    assert an.get("/api/media", params={"q": "c.jpg"}).json()["items"][0]["name"] == "c.jpg"
    thumb = an.get(listed["items"][0]["thumb_url"])
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/jpeg"


def test_a_file_that_is_neither_photo_nor_clip_is_refused(an, db):
    refused = send_photo(an, "ghi-chu.txt", data=b"not a photo at all")
    assert refused.status_code == 415 and "ghi-chu.txt" in refused.json()["message"]
    assert db.scalar(select(MediaItem.id)) is None


@needs_ffmpeg
def test_a_clip_is_kept_with_its_length_and_used_in_a_scene_as_a_copy(an, db, me, storage, tmp_path):
    made = an.post(
        "/api/media",
        files={"file": ("quay.mp4", clip_bytes(tmp_path, seconds=3, size="720x1280"), "video/mp4")},
        data={"folder": "Nồi chiên"},
    )
    assert made.status_code == 201, made.text
    item = made.json()
    assert item["kind"] == "clip" and item["seconds"] == pytest.approx(3, abs=0.2)
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    used = an.post(f"/api/media/{item['id']}/use", json={"scene_id": scene.id})
    assert used.status_code == 200, used.text
    db.refresh(scene)
    stored = db.get(MediaItem, item["id"])
    assert scene.video_key and scene.video_key != stored.storage_key and scene.image_key is None
    assert an.delete(f"/api/media/{item['id']}").status_code == 200
    assert storage.exists(scene.video_key) and not storage.exists(stored.storage_key)


def test_pasted_links_come_in_and_a_bad_one_is_reported_alone(an, db, me, storage, fakes, monkeypatch):
    monkeypatch.setattr(remote_media, "is_public", lambda address: True)
    good = fakes.image_url("noi-chien-khong-nen")
    result = an.post(
        "/api/media/links", json={"urls": [good, "http://127.0.0.1:9/khong-co.jpg"], "folder": "Nồi chiên"}
    )
    assert result.status_code == 201, result.text
    body = result.json()
    assert [item["source_url"] for item in body["added"]] == [good]
    assert body["added"][0]["folder"] == "Nồi chiên" and len(body["failed"]) == 1
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    used = an.post(f"/api/media/{body['added'][0]['id']}/use", json={"scene_id": scene.id})
    assert used.status_code == 200, used.text
    db.refresh(scene)
    assert scene.image_source == good and scene.video_key is None
    assert an.post("/api/media/links", json={"urls": ["x"] * 11}).status_code == 422


def test_the_assistant_lists_looks_at_and_uses_library_items(mcp_client, db, storage):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    key = "media/test-photo.jpg"
    storage.save_bytes(key, photo_bytes())
    item = MediaItem(kind="photo", storage_key=key, name="noi.jpg", folder="Nồi chiên", created_by_id=user.id)
    db.add(item)
    db.commit()
    listed = payload(call(mcp_client, token, "list_media", folder="Nồi chiên"))
    assert [row["id"] for row in listed["items"]] == [item.id] and listed["folders"][0]["folder"] == "Nồi chiên"
    seen = call(mcp_client, token, "view_media", media_ids=[item.id])
    assert not seen.get("isError"), seen
    assert [block["type"] for block in seen["content"]] == ["text", "image"]
    assert call(mcp_client, token, "view_media", media_ids=[999999])["isError"]
    video = make_video(db, storage, user)
    scene = first_scene(db, video)
    used = call(mcp_client, token, "set_scene_media_from_library", scene_id=scene.id, media_id=item.id)
    assert not used.get("isError"), used
    db.refresh(scene)
    assert scene.image_key and scene.image_key != key and storage.exists(scene.image_key)
