"""Text and sticker layers over a scene, added and changed from the studio, each saved on its own."""

import io

import pytest
from conftest import login, make_user, make_video
from PIL import Image
from test_text_position import scene_json
from test_voice import first_scene, render
from worker_helpers import add_user, committed  # noqa: F401  (fixture)

from reels_api.models import SceneLayer
from reels_api.storage import DirectoryStorage
from reels_api.videos import render_signature, split_scenes


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def test_a_text_layer_and_a_sticker_are_added_changed_drawn_and_removed(an, db, me, storage):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    signature = render_signature(video, *split_scenes(db, video))

    added = an.post("/api/layers", json={"scene_id": scene.id, "kind": "text", "text": "Giàu *canxi*", "start": 0.5})
    assert added.status_code == 201, added.json()
    (text,) = scene_json(added.json(), scene.id)["layers"]
    assert text | {"id": 0, "image_url": ""} == {
        "id": 0,
        "kind": "text",
        "text": "Giàu *canxi*",
        "sticker": "",
        "start": 0.5,
        "seconds": 2,
        "x": 540,
        "y": 960,
        "size": "medium",
        "style": "outline",
        "animation": "fade",
        "height": 38,
        "image_url": "",
    }
    sticker = scene_json(
        an.post(
            "/api/layers", json={"scene_id": scene.id, "kind": "sticker", "sticker": "star", "size": "large"}
        ).json(),
        scene.id,
    )["layers"][1]
    picture = Image.open(io.BytesIO(an.get(sticker["image_url"]).content))
    assert picture.mode == "RGBA" and picture.size == (340, 340)
    db.refresh(video)
    assert render_signature(video, *split_scenes(db, video)) != signature

    moved = scene_json(
        an.patch(f"/api/layers/{text['id']}", json={"x": 300, "y": 500, "style": "yellow"}).json(), scene.id
    )
    assert (moved["layers"][0]["x"], moved["layers"][0]["style"]) == (300, "yellow")
    assert moved["layers"][0]["image_url"] != text["image_url"], "a new look is a new picture"

    for layer in (text, sticker):
        assert an.delete(f"/api/layers/{layer['id']}").status_code == 200
    assert scene_json(an.get(f"/api/videos/{video.id}").json(), scene.id)["layers"] == []
    db.refresh(video)
    assert render_signature(video, *split_scenes(db, video)) == signature


def test_a_removed_layer_comes_back_from_its_own_fields(an, db, me, storage):
    """ "Hoàn tác" of a removal sends every field of the layer back, the other kind's empty one included."""
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    fields = {"kind": "text", "text": "Giảm *50%*", "sticker": "", "start": 0.3, "seconds": 2, "x": 540, "y": 960}
    fields |= {"size": "medium", "style": "yellow", "animation": "fade"}
    back = an.post("/api/layers", json={"scene_id": scene.id} | fields)
    assert back.status_code == 201, back.json()
    sticker = {"kind": "sticker", "sticker": "hot", "text": ""}
    assert an.post("/api/layers", json={"scene_id": scene.id} | sticker).status_code == 201


def test_each_sticker_has_a_picture_to_pick_it_from(an):
    picture = an.get("/api/layers/stickers/heart.png")
    assert picture.status_code == 200 and picture.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(picture.content)).size == (160, 160)
    assert an.get("/api/layers/stickers/unicorn.png").status_code == 404


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"kind": "gif"}, "Loại lớp"),
        ({"kind": "text", "text": "  "}, "Lớp chữ"),
        ({"kind": "text", "text": "chữ " * 80}, "Chữ của lớp"),
        ({"kind": "sticker", "sticker": "unicorn"}, "Sticker"),
        ({"kind": "sticker", "sticker": "star", "size": "huge"}, "Cỡ"),
        ({"kind": "sticker", "sticker": "star", "animation": "spin"}, "Hiệu ứng vào"),
        ({"kind": "sticker", "sticker": "star", "x": 5000}, "Vị trí"),
        ({"kind": "sticker", "sticker": "star", "seconds": 0}, "Số giây"),
    ],
)
def test_a_bad_layer_is_refused(an, db, me, storage, body, message):
    video = make_video(db, storage, me)
    refused = an.post("/api/layers", json={"scene_id": first_scene(db, video).id} | body)
    assert refused.status_code == 422 and message in refused.json()["message"], refused.json()


def test_the_title_scene_has_no_layers_and_a_locked_video_refuses_them(an, db, me, storage):
    video = make_video(db, storage, me)
    title, _ = split_scenes(db, video)
    refused = an.post("/api/layers", json={"scene_id": title.id, "kind": "sticker", "sticker": "star"})
    assert refused.status_code == 422 and "Cảnh tiêu đề" in refused.json()["message"]
    from test_videos_api import add_job

    add_job(db, video, me)
    locked = an.post("/api/layers", json={"scene_id": first_scene(db, video).id, "kind": "sticker", "sticker": "star"})
    assert locked.status_code == 409 and locked.json()["code"] == "video_locked"


def test_a_split_moves_the_layers_after_the_cut_to_the_new_scene(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    scene = first_scene(db, video)
    for start in (0.5, 2.5):
        an.post("/api/layers", json={"scene_id": scene.id, "kind": "sticker", "sticker": "heart", "start": start})
    first, rest = an.post(f"/api/scenes/{scene.id}/split", json={"at": 2}).json()["scenes"]
    assert [layer["start"] for layer in first["layers"]] == [0.5]
    assert [layer["start"] for layer in rest["layers"]] == [0.5]
    assert an.delete(f"/api/scenes/{rest['id']}").status_code == 200
    assert db.query(SceneLayer).count() == 1, "deleting a scene deletes its layers"


def test_the_render_job_hands_each_scene_its_layers(committed, tmp_path, monkeypatch):  # noqa: F811
    from reels_api import jobs
    from reels_render import RenderError

    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    with committed() as db:
        video = make_video(db, storage, user, scene_count=2, seconds=2)
        video.voice_enabled = False
        db.add(
            SceneLayer(
                scene_id=first_scene(db, video).id, position=1, kind="sticker", sticker="hot", start=1, seconds=1
            )
        )
        db.commit()
        video_id = video.id
    handed = []

    def fake_render(script, output, **_):
        handed.extend([(layer.sticker, layer.start) for layer in scene.layers] for scene in script.all_scenes)
        raise RenderError("dừng trước FFmpeg")

    monkeypatch.setattr(jobs, "render_video", fake_render)
    render(committed, storage, video_id, user.id)
    assert handed == [[], [("hot", 1.0)], []]
