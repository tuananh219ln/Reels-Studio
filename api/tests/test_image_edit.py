""" "Sửa ảnh": erasing drawn boxes (LaMa on the worker, Cloudflare) or editing in words (Gemini), its job and its
endpoints. LaMa is a tiny stand-in model with the real one's inputs and output (tiny_lama.py); Cloudflare and Gemini
are the fake services."""

import io

import pytest
import tiny_lama
from conftest import login, make_user, make_video, photo_bytes
from fake_services import CF_INPAINT_COLOR
from PIL import Image
from sqlalchemy import select
from worker_helpers import add_job, add_user, committed, job_row  # noqa: F401  (fixture)

from reels_api import image_edit, jobs
from reels_api.models import Job, Scene

# A box in the middle of the photo: the middle tenth across, a twentieth down.
BOX = [0.45, 0.475, 0.1, 0.05]


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


@pytest.fixture
def lama(tmp_path, monkeypatch):
    path = tiny_lama.write(tmp_path / "lama.onnx")
    monkeypatch.setenv("LAMA_MODEL_PATH", str(path))
    # The session is kept per worker: a test's model must not be the next test's.
    monkeypatch.setattr(image_edit, "_lama", None)
    return path


def pixel(data: bytes, x: float, y: float) -> tuple[int, int, int]:
    with Image.open(io.BytesIO(data)) as image:
        width, height = image.size
        return image.convert("RGB").getpixel((round(x * (width - 1)), round(y * (height - 1))))


def near(color, expected, slack=12) -> bool:
    return all(abs(a - b) <= slack for a, b in zip(color, expected))


def middle(box) -> tuple[float, float]:
    return box[0] + box[2] / 2, box[1] + box[3] / 2


# --- Boxes and the patch around them ---


def test_boxes_are_kept_inside_the_photo():
    assert image_edit.clean_boxes([[0.1, 0.2, 0.3, 0.4]]) == [[0.1, 0.2, 0.3, 0.4]]
    # A box drawn past an edge is cut at it.
    assert image_edit.clean_boxes([[-0.1, 0.9, 0.3, 0.3]]) == [[0.0, 0.9, 0.2, 0.1]]


@pytest.mark.parametrize(
    ("boxes", "message"),
    [
        ([], "ít nhất một vùng"),
        ("x", "ít nhất một vùng"),
        ([[0.1, 0.1, 0.1]], "không hợp lệ"),
        ([[0.1, 0.1, True, 0.1]], "không hợp lệ"),
        ([[0.1, 0.1, "a", 0.1]], "không hợp lệ"),
        ([[0.1, 0.1, 0.001, 0.1]], "quá nhỏ"),
        ([[1.2, 0.1, 0.1, 0.1]], "quá nhỏ"),
        ([[0.1, 0.1, 0.1, 0.1]] * 11, "tối đa 10"),
    ],
)
def test_bad_boxes_are_refused(boxes, message):
    with pytest.raises(ValueError, match=message):
        image_edit.clean_boxes(boxes)


def test_the_patch_is_a_square_around_the_boxes_inside_the_photo():
    left, top, right, bottom = image_edit.patch_region((1080, 1920), (500, 900, 580, 960))
    assert right - left == bottom - top
    assert left <= 500 and top <= 900 and right >= 580 and bottom >= 960
    # Near an edge it slides inside the photo rather than leaving it.
    left, top, right, bottom = image_edit.patch_region((1080, 1920), (0, 0, 40, 40))
    assert (left, top) == (0, 0) and right - left == bottom - top
    # A photo narrower than the square keeps its own width.
    left, _, right, _ = image_edit.patch_region((300, 1920), (0, 100, 300, 900))
    assert (left, right) == (0, 300)


def test_erase_changes_the_boxes_and_leaves_the_rest_of_the_photo():
    photo = Image.new("RGB", (720, 1280), (190, 120, 60))
    data = image_edit.erase(photo, [BOX], lambda patch, mask: Image.new("RGB", (512, 512), (0, 0, 255)))
    assert Image.open(io.BytesIO(data)).size == (720, 1280)
    assert near(pixel(data, *middle(BOX)), (0, 0, 255))
    assert near(pixel(data, 0.1, 0.1), (190, 120, 60))
    assert near(pixel(data, BOX[0] - 0.05, middle(BOX)[1]), (190, 120, 60))


# --- The job ---


def scene_with_photo(factory, storage, user) -> tuple[int, int, str]:
    with factory() as db:
        video = make_video(db, storage, user, scene_count=2)
        scene = db.scalar(select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)))
        return video.id, scene.id, scene.image_key


def run_edit(factory, storage, video_id, user_id, scene_id, engine, boxes=None, prompt=None) -> Job:
    job_id = add_job(
        factory,
        video_id,
        user_id,
        kind="image_edit",
        status="running",
        scene_id=scene_id,
        image_provider=engine,
        edit_boxes=boxes,
        edit_prompt=prompt,
    )
    jobs.run_job(job_id, factory, storage)
    return job_row(factory, job_id)


def load_scene(factory, scene_id) -> Scene:
    with factory() as db:
        return db.get(Scene, scene_id)


def test_lama_erases_the_box_and_keeps_the_original(committed, storage, lama):  # noqa: F811
    user = add_user(committed)
    video_id, scene_id, original = scene_with_photo(committed, storage, user)
    before = storage.path(original).read_bytes()

    job = run_edit(committed, storage, video_id, user.id, scene_id, "lama", [BOX])

    assert (job.status, job.error, job.image_calls) == ("done", None, 0)
    scene = load_scene(committed, scene_id)
    assert scene.image_key != original and scene.image_original_key == original
    assert storage.path(original).read_bytes() == before
    edited = storage.path(scene.image_key).read_bytes()
    assert near(pixel(edited, *middle(BOX)), (tiny_lama.FILL,) * 3)
    assert near(pixel(edited, 0.1, 0.1), pixel(before, 0.1, 0.1))
    # The photo's credit stays with it.
    assert scene.image_source.startswith("https://cdn.pixabay.com/")


def test_a_second_edit_keeps_the_first_original_and_drops_the_photo_between(committed, storage, lama):  # noqa: F811
    user = add_user(committed)
    video_id, scene_id, original = scene_with_photo(committed, storage, user)
    run_edit(committed, storage, video_id, user.id, scene_id, "lama", [BOX])
    between = load_scene(committed, scene_id).image_key

    job = run_edit(committed, storage, video_id, user.id, scene_id, "lama", [[0.1, 0.1, 0.1, 0.05]])

    assert job.status == "done"
    scene = load_scene(committed, scene_id)
    assert scene.image_original_key == original and storage.exists(original)
    assert scene.image_key != between and not storage.exists(between)


def test_lama_without_its_model_fails_and_the_scene_keeps_its_photo(committed, storage, monkeypatch):  # noqa: F811
    monkeypatch.setattr(image_edit, "_lama", None)
    user = add_user(committed)
    video_id, scene_id, original = scene_with_photo(committed, storage, user)

    job = run_edit(committed, storage, video_id, user.id, scene_id, "lama", [BOX])

    assert job.status == "failed" and "LAMA_MODEL_PATH" in job.error
    scene = load_scene(committed, scene_id)
    assert (scene.image_key, scene.image_original_key) == (original, None)


def test_cloudflare_fills_only_the_patch_around_the_box(committed, storage, fakes):  # noqa: F811
    user = add_user(committed)
    video_id, scene_id, original = scene_with_photo(committed, storage, user)
    before = storage.path(original).read_bytes()

    job = run_edit(committed, storage, video_id, user.id, scene_id, "cloudflare", [BOX])

    assert (job.status, job.error, job.image_calls) == ("done", None, 1)
    [request] = fakes.cf_inpaint_requests
    assert (request["image"], request["mask"]) == ((512, 512), (512, 512))
    assert request["prompt"] == image_edit.CF_FILL_PROMPT
    assert fakes.cf_image_gen_prompts == []
    edited = storage.path(load_scene(committed, scene_id).image_key).read_bytes()
    assert near(pixel(edited, *middle(BOX)), CF_INPAINT_COLOR)
    assert near(pixel(edited, 0.1, 0.1), pixel(before, 0.1, 0.1))


def test_cloudflare_takes_the_members_words_for_the_box(committed, storage, fakes):  # noqa: F811
    user = add_user(committed)
    video_id, scene_id, _ = scene_with_photo(committed, storage, user)
    run_edit(committed, storage, video_id, user.id, scene_id, "cloudflare", [BOX], "mặt bàn gỗ")
    assert fakes.cf_inpaint_requests[0]["prompt"] == "mặt bàn gỗ"


def test_cloudflare_out_of_free_neurons_fails_with_the_way_out(committed, storage, fakes):  # noqa: F811
    fakes.cf_inpaint_mode = "quota"
    user = add_user(committed)
    video_id, scene_id, original = scene_with_photo(committed, storage, user)

    job = run_edit(committed, storage, video_id, user.id, scene_id, "cloudflare", [BOX])

    assert job.status == "failed" and "LaMa" in job.error
    assert load_scene(committed, scene_id).image_key == original


def test_gemini_edits_the_whole_photo_as_asked(committed, storage, fakes):  # noqa: F811
    user = add_user(committed)
    video_id, scene_id, original = scene_with_photo(committed, storage, user)

    job = run_edit(committed, storage, video_id, user.id, scene_id, "gemini", prompt="làm nền sáng hơn")

    assert (job.status, job.error, job.image_calls) == ("done", None, 1)
    assert fakes.image_edit_requests == [{"prompt": "làm nền sáng hơn", "size": (720, 1280)}]
    scene = load_scene(committed, scene_id)
    assert scene.image_original_key == original and scene.image_key != original


def test_the_job_fails_when_the_scene_has_a_clip_now(committed, storage, lama):  # noqa: F811
    user = add_user(committed)
    video_id, scene_id, _ = scene_with_photo(committed, storage, user)
    with committed() as db:
        scene = db.get(Scene, scene_id)
        scene.image_key, scene.video_key = None, "videos/x/clip.mp4"
        db.commit()
    job = run_edit(committed, storage, video_id, user.id, scene_id, "lama", [BOX])
    assert job.status == "failed" and "không còn ảnh" in job.error


# --- Endpoints ---


def a_scene(db, storage, me) -> Scene:
    video = make_video(db, storage, me, scene_count=2)
    return db.scalar(select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)))


def test_post_queues_an_edit_job_for_the_scene(an, db, me, storage):
    scene = a_scene(db, storage, me)
    response = an.post(f"/api/scenes/{scene.id}/image-edit", json={"engine": "lama", "boxes": [BOX]})
    assert response.status_code == 200, response.text
    active = response.json()["active_job"]
    assert (active["kind"], active["scene_id"]) == ("image_edit", scene.id)
    assert response.json()["status_label"].startswith("Chờ")
    job = db.scalar(select(Job).where(Job.video_id == scene.video_id))
    assert (job.image_provider, job.edit_boxes, job.edit_prompt) == ("lama", [BOX], None)
    # A second press while it waits is refused, like any other job.
    assert an.post(f"/api/scenes/{scene.id}/image-edit", json={"engine": "lama", "boxes": [BOX]}).status_code == 409


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"engine": "photoshop", "boxes": [BOX]}, "không hợp lệ"),
        ({"engine": "lama", "boxes": []}, "ít nhất một vùng"),
        ({"engine": "gemini", "prompt": "  "}, "điều cần sửa"),
        ({"engine": "gemini", "prompt": "x" * 501}, "tối đa 500"),
        # Neither Cloudflare nor Gemini is set up in these tests.
        ({"engine": "cloudflare", "boxes": [BOX]}, "Chưa cài đặt Cloudflare"),
        ({"engine": "gemini", "prompt": "làm nền sáng hơn"}, "Chưa cài đặt Gemini"),
    ],
)
def test_bad_requests_are_refused_before_a_job(an, db, me, storage, body, message):
    scene = a_scene(db, storage, me)
    response = an.post(f"/api/scenes/{scene.id}/image-edit", json=body)
    assert response.status_code == 422 and message in response.json()["message"], response.text
    assert db.scalar(select(Job).where(Job.video_id == scene.video_id)) is None


def test_a_scene_without_a_photo_has_nothing_to_edit(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1, images=False)
    scene = db.scalar(select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)))
    response = an.post(f"/api/scenes/{scene.id}/image-edit", json={"engine": "lama", "boxes": [BOX]})
    assert response.status_code == 409


def edited(db, storage, scene) -> str:
    """The scene as after one edit: an edited photo, the original kept."""
    key = f"videos/{scene.video_id}/scene-{scene.id}-edited.jpg"
    storage.save_bytes(key, photo_bytes((0, 0, 0)))
    scene.image_original_key, scene.image_key = scene.image_key, key
    db.commit()
    return key


def test_restoring_brings_back_the_original_and_deletes_the_edit(an, db, me, storage):
    scene = a_scene(db, storage, me)
    original = scene.image_key
    edit = edited(db, storage, scene)
    shown = next(item for item in an.get(f"/api/videos/{scene.video_id}").json()["scenes"] if item["id"] == scene.id)
    assert shown["image_edited"] is True

    response = an.post(f"/api/scenes/{scene.id}/image-original")

    assert response.status_code == 200, response.text
    db.refresh(scene)
    assert (scene.image_key, scene.image_original_key) == (original, None)
    assert not storage.exists(edit) and storage.exists(original)
    restored = next(item for item in response.json()["scenes"] if item["id"] == scene.id)
    assert restored["image_edited"] is False
    assert an.post(f"/api/scenes/{scene.id}/image-original").status_code == 409


def test_a_new_photo_forgets_the_original_but_a_crop_keeps_it(an, db, me, storage):
    scene = a_scene(db, storage, me)
    original = scene.image_key
    edited(db, storage, scene)

    cropped = an.post(
        f"/api/scenes/{scene.id}/image/crop", files={"file": ("crop.jpg", photo_bytes(size=(1080, 1920)))}
    )
    assert cropped.status_code == 200, cropped.text
    db.refresh(scene)
    assert scene.image_original_key == original

    uploaded = an.post(f"/api/scenes/{scene.id}/image", files={"file": ("new.jpg", photo_bytes())})
    assert uploaded.status_code == 200, uploaded.text
    db.refresh(scene)
    assert scene.image_original_key is None and not storage.exists(original)


def test_retrying_an_edit_keeps_what_was_asked_and_the_log_names_it(an, db, me, storage):
    scene = a_scene(db, storage, me)
    failed = Job(
        video_id=scene.video_id,
        kind="image_edit",
        status="failed",
        created_by_id=me.id,
        scene_id=scene.id,
        image_provider="cloudflare",
        edit_boxes=[BOX],
        edit_prompt="mặt bàn gỗ",
    )
    db.add(failed)
    db.commit()
    assert an.post(f"/api/jobs/{failed.id}/retry").status_code == 200
    retry = db.scalar(select(Job).where(Job.retry_of_id == failed.id))
    assert (retry.scene_id, retry.image_provider, retry.edit_boxes, retry.edit_prompt) == (
        scene.id,
        "cloudflare",
        [BOX],
        "mặt bàn gỗ",
    )
    row = next(row for row in an.get("/api/jobs").json() if row["id"] == failed.id)
    assert (row["kind_label"], row["llm"]) == ("Sửa ảnh (1 cảnh)", "Cloudflare")
