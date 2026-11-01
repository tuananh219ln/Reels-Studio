"""Text boxes dragged on a scene (its own place) or for the whole video, and the images the drag is drawn with."""

import io

import pytest
from conftest import login, make_user, make_video
from PIL import Image
from test_voice import first_scene, needs_ffmpeg, render
from worker_helpers import add_user, committed  # noqa: F401  (fixture)

from reels_api import videos
from reels_api.models import Video
from reels_api.storage import DirectoryStorage
from reels_api.videos import render_signature, split_scenes


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def scene_json(payload: dict, scene_id: int) -> dict:
    return next(scene for scene in [payload["title_scene"], *payload["scenes"]] if scene["id"] == scene_id)


def test_a_scene_keeps_its_own_text_place_and_can_give_it_back(an, db, me, storage):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    before = an.get(f"/api/videos/{video.id}").json()
    signature = render_signature(video, *split_scenes(db, video))
    assert scene_json(before, scene.id)["text_position"] is None

    payload = an.patch(f"/api/scenes/{scene.id}", json={"text_position": [500, 700]}).json()
    moved = scene_json(payload, scene.id)
    assert moved["text_position"] == [500, 700]
    assert moved["preview_url"] != scene_json(before, scene.id)["preview_url"]
    db.refresh(video)
    assert render_signature(video, *split_scenes(db, video)) != signature
    db.refresh(scene)
    assert videos.text_position(video, scene) == [500, 700]

    back = an.patch(f"/api/scenes/{scene.id}", json={"text_position": None}).json()
    assert scene_json(back, scene.id)["text_position"] is None
    assert scene_json(back, scene.id)["preview_url"] == scene_json(before, scene.id)["preview_url"]
    db.refresh(video)
    # Back where the template puts it, the MP4 made before still counts as current.
    assert render_signature(video, *split_scenes(db, video)) == signature

    for bad in ([1, 2, 3], [-5, 10], [10, 5000], ["a", 1], "540,600"):
        refused = an.patch(f"/api/scenes/{scene.id}", json={"text_position": bad})
        assert refused.status_code == 422 and "Vị trí chữ" in refused.json()["message"], bad


def test_the_whole_video_takes_one_place_and_a_scene_of_its_own_wins(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=2)
    first, second = split_scenes(db, video)[1]
    an.patch(f"/api/scenes/{first.id}", json={"text_position": [300, 900]})
    payload = an.patch(f"/api/videos/{video.id}", json={"options": {"text_position": [540, 500]}}).json()
    assert payload["options"]["text_position"] == [540, 500]
    assert [scene["placed_at"] for scene in payload["scenes"]] == [[300, 900], [540, 500]]
    assert payload["title_scene"]["placed_at"] is None
    db.refresh(video)
    db.refresh(first)
    db.refresh(second)
    assert videos.text_position(video, first) == [300, 900]
    assert videos.text_position(video, second) == [540, 500]
    # The title is not a content scene: it keeps its own place (the centre) whatever the scenes use.
    title, _ = split_scenes(db, video)
    assert videos.text_position(video, title) is None
    refused = an.patch(f"/api/videos/{video.id}", json={"options": {"text_position": [1, 2, 3]}})
    assert refused.status_code == 422 and "Vị trí chữ" in refused.json()["message"]


def test_moving_the_title_redraws_the_thumbnail(an, db, me, storage):
    video = make_video(db, storage, me)
    title, _ = split_scenes(db, video)
    an.patch(f"/api/scenes/{title.id}", json={"text": "TIÊU ĐỀ MỚI"})
    db.refresh(video)
    thumbnail = video.thumbnail_key
    an.patch(f"/api/scenes/{title.id}", json={"text_position": [540, 500]})
    db.refresh(video)
    assert video.thumbnail_key not in (None, thumbnail)


def test_the_drag_is_drawn_from_the_bare_frame_and_the_exact_text_box(an, db, me, storage):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    payload = scene_json(an.get(f"/api/videos/{video.id}").json(), scene.id)
    frame = Image.open(io.BytesIO(an.get(payload["frame_url"]).content))
    assert frame.size == (1080, 1920)
    box = an.get(payload["textbox_url"])
    assert box.headers["content-type"] == "image/png"
    image = Image.open(io.BytesIO(box.content))
    assert image.mode == "RGBA" and 200 < image.width <= 960
    # A scene without text has no box to drag.
    empty = an.patch(f"/api/scenes/{scene.id}", json={"text": ""}).json()
    assert scene_json(empty, scene.id)["textbox_url"] is None
    assert an.get(f"/api/scenes/{scene.id}/textbox.png").status_code == 404


def yellow_pixels(image: Image.Image) -> int:
    return sum(r > 220 and g > 180 and b < 60 for r, g, b in image.convert("RGB").getdata())


@needs_ffmpeg
def test_the_render_puts_a_moved_box_where_it_was_dragged(committed, tmp_path, fakes):  # noqa: F811
    import subprocess

    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    with committed() as db:
        video = make_video(db, storage, user, scene_count=1, seconds=2)
        scene = first_scene(db, video)
        scene.text_x, scene.text_y = 540, 450
        db.commit()
        video_id = video.id
    job = render(committed, storage, video_id, user.id)
    assert job.status == "done", (job.error, job.error_detail)
    with committed() as db:
        path = storage.path(db.get(Video, video_id).mp4_key)
    still = tmp_path / "scene.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "4.5", "-i", str(path), "-frames:v", "1", str(still)])
    frame = Image.open(still)
    assert yellow_pixels(frame.crop((0, 300, 1080, 600))) > 10_000
    assert yellow_pixels(frame.crop((0, 1240, 1080, 1440))) == 0
