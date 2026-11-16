"""Cutting a library clip into a new library item ("Cắt thành file mới trong kho", POST /api/media/{id}/cut), and
the MCP tools that cut and delete library items (docs/specs/trim-clip-to-library/brief.md)."""

import pytest
from conftest import clip_bytes, login, make_user, make_video, needs_ffmpeg, photo_bytes
from sqlalchemy import func, select
from test_mcp import call, grant, mcp_client, payload  # noqa: F401  (mcp_client is a fixture)

from reels_api import clips
from reels_api.models import MediaItem, Scene

SOURCE = "https://www.tiktok.com/@bep/video/123"


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def stored_clip(db, storage, owner, tmp_path, seconds=12.0, name="trung.mp4") -> MediaItem:
    key = f"media/test-{seconds}-{name}"
    (tmp_path / "src").mkdir(exist_ok=True)
    source = tmp_path / "src" / name
    source.write_bytes(clip_bytes(tmp_path, seconds=seconds, size="720x1280"))
    storage.save_file(key, source)
    item = MediaItem(
        kind="clip",
        storage_key=key,
        name=name,
        folder="Tải về",
        source_url=SOURCE,
        seconds=seconds,
        created_by_id=owner.id,
        tags=["goc"],
    )
    db.add(item)
    db.commit()
    return item


def count(db) -> int:
    return db.scalar(select(func.count(MediaItem.id)))


@needs_ffmpeg
def test_a_cut_is_a_new_tagged_item_and_the_original_stays(an, db, me, storage, tmp_path):
    original = stored_clip(db, storage, me, tmp_path)
    made = an.post(
        f"/api/media/{original.id}/cut",
        json={"start": 4, "length": 5, "folder": "Ăn Lành/16-11", "tags": ["189 Cảnh1 Trứng lá đinh lăng"]},
    )
    assert made.status_code == 201, made.text
    cut = made.json()
    assert cut["id"] != original.id and cut["kind"] == "clip"
    assert cut["seconds"] == pytest.approx(5, abs=0.2)
    assert cut["folder"] == "Ăn Lành/16-11" and cut["tags"] == ["189-canh1-trung-la-dinh-lang"]
    assert cut["source_url"] == SOURCE and cut["name"] == "trung.mp4 (4–9s)"
    row = db.get(MediaItem, cut["id"])
    sample = clips.probe_sample(storage.path(row.storage_key))
    assert sample.seconds == pytest.approx(5, abs=0.2) and not sample.has_audio  # scene clips come without sound
    db.refresh(original)
    assert storage.exists(original.storage_key) and original.tags == ["goc"]  # never deleted or changed


@needs_ffmpeg
def test_a_cut_goes_into_a_scene_like_any_library_clip(an, db, me, storage, tmp_path):
    original = stored_clip(db, storage, me, tmp_path)
    cut = an.post(f"/api/media/{original.id}/cut", json={"start": 2, "length": 3, "tags": ["canh"], "name": "Đoạn"})
    assert cut.status_code == 201, cut.text
    assert cut.json()["name"] == "Đoạn" and cut.json()["folder"] == ""
    video = make_video(db, storage, me)
    scene = db.scalar(select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)).limit(1))
    used = an.post(f"/api/media/{cut.json()['id']}/use", json={"scene_id": scene.id})
    assert used.status_code == 200, used.text
    db.refresh(scene)
    assert scene.video_key and storage.exists(scene.video_key)


@needs_ffmpeg
def test_a_wrong_cut_is_refused_and_leaves_nothing(an, db, me, storage, tmp_path):
    original = stored_clip(db, storage, me, tmp_path, seconds=6)
    before, files = count(db), sorted(path.name for path in storage.path("media").iterdir())
    for body, status, code in (
        ({"start": 4, "length": 5, "tags": ["a"]}, 422, "invalid_value"),  # past the clip's end
        ({"start": -1, "length": 3, "tags": ["a"]}, 422, "invalid_value"),
        ({"start": 0, "length": 0.5, "tags": ["a"]}, 422, "invalid_value"),  # under a clip's 1 second
        ({"start": 0, "length": 61, "tags": ["a"]}, 422, "invalid_value"),
        ({"start": 0, "length": 3, "tags": []}, 422, "invalid_value"),  # untagged
        ({"start": 0, "length": 3, "tags": ["   "]}, 422, "invalid_value"),
    ):
        refused = an.post(f"/api/media/{original.id}/cut", json=body)
        assert (refused.status_code, refused.json()["code"]) == (status, code), (body, refused.text)
    assert (
        "6.0 giây"
        in an.post(f"/api/media/{original.id}/cut", json={"start": 4, "length": 5, "tags": ["a"]}).json()["message"]
    )
    storage.delete(original.storage_key)
    gone = an.post(f"/api/media/{original.id}/cut", json={"start": 0, "length": 3, "tags": ["a"]})
    assert (gone.status_code, gone.json()["code"]) == (404, "media_not_found")
    missing = an.post("/api/media/999999/cut", json={"start": 0, "length": 3, "tags": ["a"]})
    assert missing.status_code == 404
    assert count(db) == before
    assert sorted(path.name for path in storage.path("media").iterdir()) == [
        name for name in files if name != original.storage_key.split("/")[1]
    ]


def test_a_photo_cannot_be_cut(an, db, me, storage):
    key = "media/test-photo.jpg"
    storage.save_bytes(key, photo_bytes())
    item = MediaItem(kind="photo", storage_key=key, name="anh.jpg", folder="", created_by_id=me.id)
    db.add(item)
    db.commit()
    refused = an.post(f"/api/media/{item.id}/cut", json={"start": 0, "length": 3, "tags": ["a"]})
    assert refused.status_code == 422 and "clip" in refused.json()["message"]


@needs_ffmpeg
def test_the_assistant_cuts_a_clip_and_deletes_its_own_items(mcp_client, db, storage, tmp_path):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    original = stored_clip(db, storage, user, tmp_path)
    cut = call(
        mcp_client, token, "cut_clip_to_library", media_id=original.id, start=3, length=4, folder="Ăn Lành", tags=["x"]
    )
    assert not cut.get("isError"), cut
    made = payload(cut)
    assert made["seconds"] == pytest.approx(4, abs=0.2) and made["folder"] == "Ăn Lành" and made["tags"] == ["x"]
    assert made["source_url"] == SOURCE and storage.exists(original.storage_key)
    refused = call(mcp_client, token, "cut_clip_to_library", media_id=original.id, start=10, length=5, tags=["x"])
    assert refused["isError"]

    teammate = make_user(db, email="ban@example.com")
    theirs = stored_clip(db, storage, teammate, tmp_path, name="cua-ban.mp4")
    assert call(mcp_client, token, "delete_media", media_id=theirs.id)["isError"]  # only its maker deletes it
    assert db.get(MediaItem, theirs.id) is not None
    key = original.storage_key
    deleted = call(mcp_client, token, "delete_media", media_id=original.id)
    assert not deleted.get("isError"), deleted
    db.expire_all()
    assert db.get(MediaItem, original.id) is None and not storage.exists(key)
    assert db.get(MediaItem, made["id"]) is not None  # the cut stays
