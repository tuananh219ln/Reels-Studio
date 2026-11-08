""" "Ảnh chèn nửa khung": a photo layer (style "half") with a photo of its own, as wide as the frame and half as
tall, moved only up and down; the server keeps it centred across and inside the frame whatever it is sent."""

import io

import pytest
from conftest import login, make_user, make_video, photo_bytes
from PIL import Image
from sqlalchemy import select
from test_mcp import call, grant, mcp_client  # noqa: F401  (mcp_client is a fixture)
from test_text_position import scene_json
from test_voice import first_scene, render
from worker_helpers import add_user, committed  # noqa: F401  (fixture)

from reels_api import jobs
from reels_api.models import MediaItem, SceneLayer
from reels_api.storage import DirectoryStorage
from reels_api.videos import render_signature, split_scenes


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def upload(an, scene_id: int, data: bytes | None = None):
    files = {"file": ("anh.jpg", data or photo_bytes(size=(1600, 1200)), "image/jpeg")}
    return an.post("/api/layers/half-photo/upload", data={"scene_id": str(scene_id)}, files=files)


def test_an_uploaded_photo_lands_across_the_top_half_for_the_whole_scene(an, db, me, storage):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    added = upload(an, scene.id)
    assert added.status_code == 201, added.json()
    (layer,) = scene_json(added.json(), scene.id)["layers"]
    assert {key: layer[key] for key in ("kind", "style", "x", "y", "start", "seconds", "animation")} == {
        "kind": "photo",
        "style": "half",
        "x": 540,
        "y": 480,
        "start": 0,
        "seconds": 60,
        "animation": "none",
    }
    picture = Image.open(io.BytesIO(an.get(layer["image_url"]).content))
    assert picture.size == (1080, 960)
    row = db.get(SceneLayer, layer["id"])
    assert row.image_key and storage.exists(row.image_key)


def test_it_moves_only_up_and_down_and_stays_inside_the_frame(an, db, me, storage):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    layer = scene_json(upload(an, scene.id).json(), scene.id)["layers"][0]

    def patch(body: dict) -> dict:
        response = an.patch(f"/api/layers/{layer['id']}", json=body)
        assert response.status_code == 200, response.json()
        return scene_json(response.json(), scene.id)["layers"][0]

    middle = patch({"x": 100, "y": 960})
    assert (middle["x"], middle["y"]) == (540, 960), "sent across: still centred"
    assert patch({"y": 5000})["y"] == 1440, "dragged past the bottom: kept at the bottom half"
    assert patch({"y": -50})["y"] == 480, "dragged past the top: kept at the top half"
    # Its size, look and entrance are fixed; its seconds are its own.
    kept = patch({"size": "large", "style": "circle", "animation": "slide_up", "start": 2, "seconds": 3})
    assert (kept["size"], kept["style"], kept["animation"]) == ("medium", "half", "none")
    assert (kept["start"], kept["seconds"]) == (2, 3)
    refused = an.patch(f"/api/layers/{layer['id']}", json={"y": "giữa"})
    assert refused.status_code == 422 and "Vị trí" in refused.json()["message"]


def test_it_comes_from_the_library_but_not_from_a_clip(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=2)
    first, second = split_scenes(db, video)[1]
    storage.save_bytes("media/anh.png", photo_bytes(kind="PNG"))
    storage.save_bytes("media/clip.mp4", b"not a photo")
    photo = MediaItem(kind="photo", storage_key="media/anh.png", name="anh.png", created_by_id=me.id)
    clip = MediaItem(kind="clip", storage_key="media/clip.mp4", name="clip.mp4", created_by_id=me.id)
    db.add_all([photo, clip])
    db.commit()
    added = an.post("/api/layers/half-photo", json={"scene_id": first.id, "media_id": photo.id})
    assert added.status_code == 201, added.json()
    assert scene_json(added.json(), first.id)["layers"][0]["style"] == "half"
    refused = an.post("/api/layers/half-photo", json={"scene_id": second.id, "media_id": clip.id})
    assert refused.status_code == 422 and "ảnh chèn cần một ảnh" in refused.json()["message"]
    neither = an.post("/api/layers/half-photo", json={"scene_id": second.id})
    assert neither.status_code == 422


def test_one_photo_layer_per_scene_and_none_on_the_title(an, db, me, storage):
    video = make_video(db, storage, me)
    title, scenes = split_scenes(db, video)
    assert upload(an, scenes[0].id).status_code == 201
    again = upload(an, scenes[0].id)
    assert again.status_code == 422 and "đã có ảnh món hoặc ảnh chèn" in again.json()["message"]
    on_title = upload(an, title.id)
    assert on_title.status_code == 422 and "Cảnh tiêu đề" in on_title.json()["message"]
    not_a_photo = upload(an, scenes[1].id if len(scenes) > 1 else scenes[0].id, b"not a photo")
    assert not_a_photo.status_code in (415, 422)


def test_it_shows_on_a_slide_video_and_its_photo_goes_with_it(an, db, me, storage):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    before = render_signature(video, *split_scenes(db, video))
    layer = scene_json(upload(an, scene.id).json(), scene.id)["layers"][0]
    db.refresh(video)
    assert video.mode == "slides" and render_signature(video, *split_scenes(db, video)) != before
    key = db.get(SceneLayer, layer["id"]).image_key
    assert an.delete(f"/api/layers/{layer['id']}").status_code == 200
    assert not storage.exists(key), "its own copy is deleted with it"
    db.refresh(video)
    assert render_signature(video, *split_scenes(db, video)) == before


def test_the_render_job_hands_the_half_frame_photo_its_own_photo(committed, tmp_path, monkeypatch):  # noqa: F811
    from reels_render import RenderError

    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    storage.save_bytes("videos/inset.jpg", photo_bytes(size=(1600, 1200)))
    with committed() as db:
        video = make_video(db, storage, user, scene_count=2, seconds=2)
        video.voice_enabled = False
        layer = SceneLayer(
            scene_id=first_scene(db, video).id,
            position=1,
            kind="photo",
            style="half",
            x=540,
            y=1440,
            seconds=60,
            animation="none",
            image_key="videos/inset.jpg",
        )
        db.add(layer)
        db.commit()
        video_id = video.id
    handed = {}

    def fake_render(script, output, **_):
        handed["layers"] = [[(layer.style, layer.y, layer.image.name) for layer in s.layers] for s in script.scenes]
        raise RenderError("dừng trước FFmpeg")

    monkeypatch.setattr(jobs, "render_video", fake_render)
    render(committed, storage, video_id, user.id)
    assert handed["layers"] == [[("half", 1440, "inset-01.jpg")], []], "drawn on a slide video too"


def test_the_assistant_adds_one_from_the_library_and_cannot_move_it_across(mcp_client, db, storage):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    storage.save_bytes("media/anh.jpg", photo_bytes(size=(900, 1600)))
    item = MediaItem(kind="photo", storage_key="media/anh.jpg", name="anh.jpg", created_by_id=user.id)
    db.add(item)
    db.commit()
    video = make_video(db, storage, user)
    scene = first_scene(db, video)
    assert call(mcp_client, token, "add_layer", scene_id=scene.id, kind="photo")["isError"], "needs an image"
    added = call(mcp_client, token, "add_layer", scene_id=scene.id, kind="photo", image=str(item.id))
    assert not added.get("isError"), added
    row = db.scalar(select(SceneLayer).where(SceneLayer.scene_id == scene.id))
    assert (row.style, row.x, row.y) == ("half", 540, 480)
    moved = call(mcp_client, token, "update_layer", layer_id=row.id, x=100, y=1440)
    assert not moved.get("isError"), moved
    db.refresh(row)
    assert (row.x, row.y) == (540, 1440)


def test_the_scenes_own_photo_becomes_its_half_frame_photo_in_place_of_its_ảnh_món(an, db, me, storage):
    video = make_video(db, storage, me)
    video.mode = "single"
    db.commit()
    scene = first_scene(db, video)
    assert an.post("/api/layers", json={"scene_id": scene.id, "kind": "photo"}).status_code == 201
    moved = an.post("/api/layers/half-photo", json={"scene_id": scene.id, "scene_photo": True})
    assert moved.status_code == 201, moved.json()
    (layer,) = scene_json(moved.json(), scene.id)["layers"]
    assert (layer["style"], layer["x"], layer["y"]) == ("half", 540, 480), "the Ảnh món is replaced"
    own = db.get(SceneLayer, layer["id"]).image_key
    db.refresh(scene)
    assert own != scene.image_key and storage.exists(own) and storage.exists(scene.image_key), "a copy of its own"
    again = an.post("/api/layers/half-photo", json={"scene_id": scene.id, "scene_photo": True})
    assert again.status_code == 422, "a half-frame photo is not replaced by another"
