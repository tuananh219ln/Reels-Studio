""" "Kiểu video": a slide video (each scene its own photo or clip) or "Video xuyên suốt" (the title scene's photo or
clip under every scene, with "Ảnh món" photo layers), and "Nghỉ sau lời đọc"."""

import io
import json

import pytest
from conftest import first_topic, login, make_user, make_video
from fake_services import script_json
from PIL import Image
from test_text_position import scene_json
from test_voice import first_scene, render
from worker_helpers import add_job, add_user, committed, job_row  # noqa: F401  (fixture)

from reels_api import jobs, render_nodes, video_options
from reels_api.claude import BACKDROP_FORMAT
from reels_api.models import Scene, SceneLayer, Video
from reels_api.storage import DirectoryStorage
from reels_api.tts import voice_signature
from reels_api.videos import _voice, render_signature, split_scenes, spoken


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def single(an, video) -> dict:
    switched = an.patch(f"/api/videos/{video.id}", json={"mode": "single"})
    assert switched.status_code == 200, switched.json()
    return switched.json()


# --- The mode ---


def test_a_new_video_is_a_slide_video_unless_asked(an, db):
    group = first_topic(db).id
    assert an.post("/api/videos", json={"topic": "chuối xanh", "knowledge_topic_id": group}).json()["mode"] == "slides"
    made = an.post("/api/videos", json={"topic": "chuối xanh", "knowledge_topic_id": group, "video_mode": "single"})
    assert made.json()["mode"] == "single"
    wrong = an.post("/api/videos", json={"topic": "chuối xanh", "knowledge_topic_id": group, "video_mode": "film"})
    assert wrong.status_code == 422


def test_switching_keeps_every_photo_and_layer_and_switching_back_renders_as_before(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=2)
    slides = render_signature(video, *split_scenes(db, video))
    payload = single(an, video)
    assert payload["mode"] == "single"
    an.post("/api/layers", json={"scene_id": first_scene(db, video).id, "kind": "photo"})
    db.refresh(video)
    assert render_signature(video, *split_scenes(db, video)) != slides

    back = an.patch(f"/api/videos/{video.id}", json={"mode": "slides"}).json()
    assert back["mode"] == "slides"
    assert all(scene["has_image"] for scene in back["scenes"])
    assert [layer["kind"] for layer in back["scenes"][0]["layers"]] == ["photo"], "kept for switching again"
    db.refresh(video)
    assert render_signature(video, *split_scenes(db, video)) == slides, "a photo layer is not drawn on slides"

    refused = an.patch(f"/api/videos/{video.id}", json={"mode": "film"})
    assert refused.status_code == 422 and "Kiểu video" in refused.json()["message"]


def test_a_backdrop_video_needs_a_picture_only_on_its_title_scene(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=2, images=False)
    assert an.get(f"/api/videos/{video.id}").json()["scenes"][0]["blocking"] == ["Cảnh chưa có ảnh"]
    payload = single(an, video)
    assert payload["scenes"][0]["blocking"] == [] and payload["scenes"][1]["blocking"] == []
    assert payload["title_scene"]["blocking"] == ["Cảnh chưa có ảnh"]
    assert payload["can_render"] is False


def test_a_clone_and_a_tiktok_version_keep_the_mode(an, db, me, storage):
    video = make_video(db, storage, me)
    topic = first_topic(db)
    topic.clone_prompt = "Biến thể"
    db.commit()
    single(an, video)
    for body in ({"request": "đổi sang gừng"}, {"request": "bản TikTok", "platform": "tiktok"}):
        assert an.post(f"/api/videos/{video.id}/clone", json=body).json()["mode"] == "single"


# --- "Ảnh món" ---


def test_a_photo_layer_is_only_for_a_backdrop_video_one_per_scene(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=2)
    first, second = split_scenes(db, video)[1]
    refused = an.post("/api/layers", json={"scene_id": first.id, "kind": "photo"})
    assert refused.status_code == 422 and "Video xuyên suốt" in refused.json()["message"]

    single(an, video)
    added = an.post("/api/layers", json={"scene_id": first.id, "kind": "photo"})
    assert added.status_code == 201, added.json()
    (layer,) = scene_json(added.json(), first.id)["layers"]
    assert {key: layer[key] for key in ("kind", "x", "y", "size", "style", "animation", "start", "seconds")} == {
        "kind": "photo",
        "x": 367,
        "y": 835,
        "size": "medium",
        "style": "rounded",
        "animation": "slide_up",
        "start": 0,
        "seconds": 60,
    }
    other = scene_json(an.post("/api/layers", json={"scene_id": second.id, "kind": "photo"}).json(), second.id)
    assert other["layers"][0]["x"] == 713, "the next scene's photo goes on the other side"
    again = an.post("/api/layers", json={"scene_id": first.id, "kind": "photo"})
    assert again.status_code == 422 and "đã có ảnh món" in again.json()["message"]

    picture = Image.open(io.BytesIO(an.get(layer["image_url"]).content))
    assert picture.mode == "RGBA" and picture.width == 520 + 72
    circle = scene_json(an.patch(f"/api/layers/{layer['id']}", json={"style": "circle"}).json(), first.id)
    assert circle["layers"][0]["image_url"] != layer["image_url"]
    wrong = an.patch(f"/api/layers/{layer['id']}", json={"style": "yellow"})
    assert wrong.status_code == 422 and "Khung ảnh" in wrong.json()["message"]


def test_a_photo_layer_without_its_scenes_photo_blocks_the_render(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    single(an, video)
    scene = first_scene(db, video)
    an.post("/api/layers", json={"scene_id": scene.id, "kind": "photo"})
    scene.image_key = None
    db.commit()
    payload = an.get(f"/api/videos/{video.id}").json()
    assert payload["scenes"][0]["blocking"] == ["Cảnh có ảnh món nhưng chưa có ảnh: chọn ảnh cho cảnh hoặc tắt ảnh món"]
    assert payload["can_render"] is False
    layer = payload["scenes"][0]["layers"][0]
    assert an.get(layer["image_url"]).status_code == 404


def test_the_render_job_lays_the_backdrop_and_hands_the_photo_layers_their_photo(committed, tmp_path, monkeypatch):  # noqa: F811
    from reels_render import RenderError

    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    with committed() as db:
        video = make_video(db, storage, user, scene_count=2, seconds=2)
        video.voice_enabled = False
        video.mode = "single"
        db.add(SceneLayer(scene_id=first_scene(db, video).id, position=1, kind="photo", seconds=60, style="circle"))
        db.commit()
        video_id = video.id
    handed = {}

    def fake_render(script, output, options, **_):
        handed["options"] = options
        handed["pictures"] = [(scene.image is not None, scene.video is not None) for scene in script.all_scenes]
        handed["layers"] = [[(layer.kind, layer.style, layer.image.name) for layer in s.layers] for s in script.scenes]
        raise RenderError("dừng trước FFmpeg")

    monkeypatch.setattr(jobs, "render_video", fake_render)
    render(committed, storage, video_id, user.id)
    assert handed["options"].backdrop is True
    # Only the title scene brings a picture: the render core lays it under the others.
    assert handed["pictures"] == [(True, False), (False, False), (False, False)]
    assert handed["layers"] == [[("photo", "circle", "photo-01.jpg")], []]

    with committed() as db:
        db.get(Video, video_id).mode = "slides"
        db.commit()
    render(committed, storage, video_id, user.id)
    assert handed["options"].backdrop is False
    assert handed["pictures"] == [(True, False)] * 3
    assert handed["layers"] == [[], []], "a slide video keeps its photo layers out of the render"


def test_a_template_saved_from_a_backdrop_video_leaves_its_photo_layers_out():
    from reels_api import autoedit

    last = Scene(is_title=False, position=1, text="", seconds=3)
    last.layers = [
        SceneLayer(
            kind="photo",
            text="",
            sticker="",
            start=0,
            seconds=60,
            x=367,
            y=835,
            size="medium",
            style="rounded",
            animation="slide_up",
        ),
        SceneLayer(
            kind="sticker",
            text="",
            sticker="hot",
            start=1,
            seconds=1,
            x=540,
            y=960,
            size="medium",
            style="outline",
            animation="fade",
        ),
    ]
    assert [layer["kind"] for layer in autoedit.derive(None, [last]).end_layers] == ["sticker"]


def test_a_render_machine_hears_of_a_backdrop_only_when_there_is_one():
    plain = render_nodes.options_dict(video_options.RenderOptions())
    assert "backdrop" not in plain, "a machine on older code still renders slide videos"
    assert render_nodes.options_dict(video_options.RenderOptions(backdrop=True))["backdrop"] is True


# --- "Nghỉ sau lời đọc" ---


def test_the_pause_after_narration_sets_the_seconds_that_follow_it(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    scene = first_scene(db, video)
    scene.voice_text, scene.seconds_auto = "Chuối xanh giàu tinh bột kháng", True
    scene.voice_key, scene.voice_seconds = "videos/x/voice.mp3", 3.0
    scene.voice_signature = voice_signature(spoken(video, scene), *_voice(video))
    db.commit()
    assert an.get(f"/api/videos/{video.id}").json()["options"]["voice_pause"] == 0.4

    for pause, seconds in ((1.0, 4.2), (0.7, 3.9), (0.4, 3.6)):
        payload = an.patch(f"/api/videos/{video.id}", json={"options": {"voice_pause": pause}}).json()
        assert payload["options"]["voice_pause"] == pause
        assert payload["scenes"][0]["seconds"] == seconds
    refused = an.patch(f"/api/videos/{video.id}", json={"options": {"voice_pause": 2}})
    assert refused.status_code == 422 and "Nghỉ sau lời đọc" in refused.json()["message"]


def test_the_pause_leaves_the_mp4_fingerprint_to_the_seconds(db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    before = render_signature(video, *split_scenes(db, video))
    video.options = video_options.effective(video) | {"voice_pause": 1.0}
    assert render_signature(video, *split_scenes(db, video)) == before


# --- The script ---


def write_backdrop_script(factory, storage, user, reply: dict) -> tuple[int, list[str]]:
    with factory() as db:
        video = Video(
            topic="chuối xanh",
            knowledge_topic_id=first_topic(db).id,
            has_script=False,
            created_by_id=user.id,
            mode="single",
        )
        db.add(video)
        db.commit()
        video_id = video.id
    prompts = []

    def call(prompt: str, label: str) -> str:
        prompts.append(prompt)
        return json.dumps(reply, ensure_ascii=False)

    job_id = add_job(factory, video_id, user.id, kind="script", status="running")
    jobs.run_job(job_id, factory, storage, call)
    assert job_row(factory, job_id).status == "done"
    return video_id, prompts


def test_a_backdrop_script_names_a_dish_only_where_it_shows_one(committed, tmp_path):  # noqa: F811
    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    reply = script_json("chuối xanh", scene_count=3)
    reply["scenes"][1] |= {"keywords": [], "keywords_en": [], "image_prompt": ""}
    video_id, prompts = write_backdrop_script(committed, storage, user, reply)
    assert BACKDROP_FORMAT in prompts[0]
    with committed() as db:
        _, scenes = split_scenes(db, db.get(Video, video_id))
        kinds = [[(layer.kind, layer.style, layer.x, layer.y, layer.image_key) for layer in s.layers] for s in scenes]
    # Such a video uses only half-frame photos (2026-11-09), showing the scene's photo until it has its own.
    half = ("photo", "half", 540, 1613, None)
    assert kinds == [[half], [], [half]], "a half-frame photo where the scene names a dish"


def test_a_slide_script_gets_no_backdrop_rules_and_no_photo_layers(committed, tmp_path):  # noqa: F811
    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    with committed() as db:
        video = Video(topic="canh", knowledge_topic_id=first_topic(db).id, has_script=False, created_by_id=user.id)
        db.add(video)
        db.commit()
        video_id = video.id
    prompts = []

    def call(prompt: str, label: str) -> str:
        prompts.append(prompt)
        return json.dumps(script_json("canh", scene_count=2), ensure_ascii=False)

    job_id = add_job(committed, video_id, user.id, kind="script", status="running")
    jobs.run_job(job_id, committed, storage, call)
    assert BACKDROP_FORMAT not in prompts[0]
    with committed() as db:
        assert db.query(SceneLayer).join(Scene).filter(Scene.video_id == video_id).count() == 0
