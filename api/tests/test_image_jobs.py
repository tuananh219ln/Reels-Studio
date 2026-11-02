"""The image job: AI photos (fake Gemini) for the scenes that have none, plus its endpoint."""

import pytest
from conftest import first_topic, login, make_user, make_video
from fake_services import IMAGE_GEN_KEY
from sqlalchemy import select
from worker_helpers import add_job, add_user, committed, job_row  # noqa: F401  (fixtures)

from reels_api import image_style, jobs, source_keys
from reels_api.models import Job, Scene, Video


@pytest.fixture(autouse=True)
def gemini(monkeypatch):
    """These tests use Gemini; with both fake providers set up the team's default would be Cloudflare."""
    monkeypatch.setenv("IMAGE_GEN_PROVIDER", "gemini")


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


# --- The job itself, in process on committed rows (the test_voice pattern) ---


def run_image_job(factory, storage, video_id, user_id) -> Job:
    job_id = add_job(factory, video_id, user_id, kind="image", status="running")
    jobs.run_job(job_id, factory, storage)
    return job_row(factory, job_id)


def build(factory, storage, user, scene_count=3, images=False, prompts=True) -> int:
    """A scripted video; content scenes carry an image prompt, the title scene never does."""
    with factory() as db:
        video = make_video(db, storage, user, scene_count=scene_count, images=images)
        if prompts:
            for scene in db.scalars(select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False))):
                scene.image_prompt = f"Ảnh món {scene.position} trên bàn gỗ"
            db.commit()
        return video.id


def load_scenes(factory, video_id) -> list[Scene]:
    with factory() as db:
        return db.scalars(select(Scene).where(Scene.video_id == video_id).order_by(Scene.position)).all()


def test_image_job_fills_every_missing_scene(committed, fakes, storage):
    user = add_user(committed)
    video_id = build(committed, storage, user)

    job = run_image_job(committed, storage, video_id, user.id)

    assert (job.status, job.error, job.image_calls) == ("done", None, 4)  # title + 3 scenes
    scenes = load_scenes(committed, video_id)
    assert all(scene.image_key and storage.exists(scene.image_key) for scene in scenes)
    assert all(scene.image_source == "ai:gemini-2.5-flash-image" for scene in scenes)
    assert all(scene.image_error is None for scene in scenes)
    # The title scene has no image prompt: its first line of text is the prompt. The team's style follows each.
    assert fakes.image_gen_prompts[0] == f"5 MÓN GIÚP. {image_style.DEFAULT}"
    assert fakes.image_gen_prompts[1:] == [f"Ảnh món {n} trên bàn gỗ. {image_style.DEFAULT}" for n in (1, 2, 3)]
    with committed() as db:
        assert db.get(Video, video_id).thumbnail_key is not None


def test_image_job_skips_scenes_with_a_photo_or_a_clip(committed, fakes, storage):
    user = add_user(committed)
    video_id = build(committed, storage, user, images=True)
    with committed() as db:
        clip_scene = db.scalar(
            select(Scene).where(Scene.video_id == video_id, Scene.is_title.is_(False)).order_by(Scene.position)
        )
        clip_scene.image_key, clip_scene.image_source = None, None
        clip_scene.video_key = f"videos/{video_id}/clip-seed.mp4"
        db.commit()

    job = run_image_job(committed, storage, video_id, user.id)

    assert (job.status, job.image_calls) == ("done", 0)
    assert fakes.image_gen_prompts == []
    scenes = load_scenes(committed, video_id)
    assert all(scene.image_source and "pixabay" in scene.image_source for scene in scenes if scene.image_key)
    assert scenes[1].video_key and scenes[1].image_key is None


def test_a_second_run_with_every_scene_filled_calls_the_provider_zero_times(committed, fakes, storage):
    user = add_user(committed)
    video_id = build(committed, storage, user)
    assert run_image_job(committed, storage, video_id, user.id).status == "done"

    job = run_image_job(committed, storage, video_id, user.id)

    assert (job.status, job.image_calls) == ("done", 0)
    assert len(fakes.image_gen_prompts) == 4


def test_a_refused_prompt_fails_only_its_scene(committed, fakes, storage):
    user = add_user(committed)
    video_id = build(committed, storage, user)
    fakes.image_gen_refused = ["món 2"]

    job = run_image_job(committed, storage, video_id, user.id)

    assert (job.status, job.image_calls) == ("done", 4)
    scenes = load_scenes(committed, video_id)
    refused = scenes[2]  # title, scene 1, scene 2, scene 3
    assert refused.image_key is None and "từ chối" in (refused.image_error or "")
    assert all(scene.image_key for scene in scenes if scene.id != refused.id)


def test_quota_partway_fails_the_job_and_keeps_the_finished_scenes(committed, fakes, storage):
    user = add_user(committed)
    video_id = build(committed, storage, user)
    fakes.image_gen_ok_count = 2

    job = run_image_job(committed, storage, video_id, user.id)

    assert job.status == "failed" and "hạn mức" in (job.error or "")
    assert job.image_calls == 3  # two paid for, the third hit the quota
    scenes = load_scenes(committed, video_id)
    assert [bool(scene.image_key) for scene in scenes] == [True, True, False, False]


def test_a_wrong_key_fails_the_job_at_once(committed, fakes, storage, monkeypatch):
    user = add_user(committed)
    video_id = build(committed, storage, user)
    monkeypatch.setenv("IMAGE_GEN_API_KEY", "not-the-fake-key")

    job = run_image_job(committed, storage, video_id, user.id)

    assert job.status == "failed" and "không hợp lệ" in (job.error or "")
    assert not any(scene.image_key for scene in load_scenes(committed, video_id))


def test_a_key_saved_on_the_sources_page_makes_the_photos(committed, fakes, storage, monkeypatch):
    user = add_user(committed)
    video_id = build(committed, storage, user)
    monkeypatch.setenv("IMAGE_GEN_API_KEY", "")
    with committed() as db:
        source_keys.save(db, "gemini", IMAGE_GEN_KEY, user.id)
        db.commit()

    job = run_image_job(committed, storage, video_id, user.id)

    assert job.status == "done", job.error
    assert len(fakes.image_gen_prompts) == 4


def test_no_key_configured_fails_with_a_clear_message(committed, fakes, storage, monkeypatch):
    user = add_user(committed)
    video_id = build(committed, storage, user)
    monkeypatch.setenv("IMAGE_GEN_API_KEY", "")

    job = run_image_job(committed, storage, video_id, user.id)

    assert job.status == "failed" and "Chưa có key Gemini nên không tạo được ảnh AI" in (job.error or "")
    assert fakes.image_gen_prompts == []


# --- The endpoint ---


def test_post_image_queues_an_image_job(an, db, me, storage):
    video = make_video(db, storage, me, images=False)
    response = an.post(f"/api/videos/{video.id}/image")
    assert response.status_code == 200
    payload = response.json()
    assert payload["active_job"]["kind"] == "image" and payload["locked"] is True


def test_post_image_needs_a_script_first(an, db, me):
    video = Video(topic="chưa viết", knowledge_topic_id=first_topic(db).id, has_script=False, created_by_id=me.id)
    db.add(video)
    db.commit()
    response = an.post(f"/api/videos/{video.id}/image")
    assert response.status_code == 409
    assert response.json()["message"] == "Video chưa có kịch bản"


def test_post_image_is_refused_while_another_job_runs(an, db, me, storage):
    video = make_video(db, storage, me, images=False)
    db.add(Job(video_id=video.id, kind="render", status="queued", created_by_id=me.id))
    db.commit()
    assert an.post(f"/api/videos/{video.id}/image").status_code == 409


def test_the_job_log_counts_image_calls(an, db, me, storage):
    video = make_video(db, storage, me, images=False)
    db.add(Job(video_id=video.id, kind="image", status="done", created_by_id=me.id, image_calls=3))
    db.commit()
    row = next(row for row in an.get("/api/jobs").json() if row["kind"] == "image")
    assert (row["kind_label"], row["image_calls"], row["claude_calls"]) == ("Tạo ảnh AI", 3, 0)


# --- One scene ("Tạo ảnh AI" / "Tạo lại ảnh AI" on its card) ---


def content_scene_ids(factory, video_id) -> list[int]:
    return [scene.id for scene in load_scenes(factory, video_id) if not scene.is_title]


def test_a_scene_job_remakes_only_that_scene_even_when_it_has_a_photo(committed, fakes, storage):
    user = add_user(committed)
    video_id = build(committed, storage, user, images=True)
    target = content_scene_ids(committed, video_id)[1]
    before = {scene.id: scene.image_key for scene in load_scenes(committed, video_id)}

    job_id = add_job(committed, video_id, user.id, kind="image", status="running", scene_id=target)
    jobs.run_job(job_id, committed, storage)
    job = job_row(committed, job_id)

    assert (job.status, job.error, job.image_calls) == ("done", None, 1)
    assert fakes.image_gen_prompts == [f"Ảnh món 2 trên bàn gỗ. {image_style.DEFAULT}"]
    after = {scene.id: scene for scene in load_scenes(committed, video_id)}
    assert after[target].image_key != before[target] and after[target].image_source == "ai:gemini-2.5-flash-image"
    assert storage.exists(after[target].image_key) and not storage.exists(before[target])
    assert all(after[scene_id].image_key == key for scene_id, key in before.items() if scene_id != target)


def test_a_scene_job_replaces_the_scene_clip(committed, fakes, storage):
    user = add_user(committed)
    video_id = build(committed, storage, user, images=True)
    target = content_scene_ids(committed, video_id)[0]
    with committed() as db:
        scene = db.get(Scene, target)
        old_photo, scene.video_key, scene.video_seconds = scene.image_key, f"videos/{video_id}/clip-seed.mp4", 3.0
        scene.image_key = None
        storage.save_bytes(scene.video_key, b"clip")
        db.commit()

    job_id = add_job(committed, video_id, user.id, kind="image", status="running", scene_id=target)
    jobs.run_job(job_id, committed, storage)

    with committed() as db:
        scene = db.get(Scene, target)
        assert scene.image_key and scene.video_key is None and scene.video_seconds is None
    assert not storage.exists(f"videos/{video_id}/clip-seed.mp4") and old_photo != scene.image_key


def test_a_refused_prompt_on_a_scene_job_fails_the_job_and_keeps_the_photo(committed, fakes, storage):
    user = add_user(committed)
    video_id = build(committed, storage, user, images=True)
    target = content_scene_ids(committed, video_id)[1]
    before = {scene.id: scene.image_key for scene in load_scenes(committed, video_id)}[target]
    fakes.image_gen_refused = ["món 2"]

    job_id = add_job(committed, video_id, user.id, kind="image", status="running", scene_id=target)
    jobs.run_job(job_id, committed, storage)
    job = job_row(committed, job_id)

    assert job.status == "failed" and job.error.startswith("Cảnh 2: ") and "từ chối" in job.error
    with committed() as db:
        assert db.get(Scene, target).image_key == before and storage.exists(before)


def test_a_scene_job_for_a_deleted_scene_fails_clearly(committed, fakes, storage):
    user = add_user(committed)
    video_id = build(committed, storage, user)
    job_id = add_job(committed, video_id, user.id, kind="image", status="running", scene_id=999_999)
    jobs.run_job(job_id, committed, storage)
    job = job_row(committed, job_id)
    assert job.status == "failed" and "không còn" in job.error and fakes.image_gen_prompts == []


def test_post_scene_image_queues_a_job_for_that_scene(an, db, me, storage):
    video = make_video(db, storage, me, images=True)
    scene = db.scalar(select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)))
    response = an.post(f"/api/scenes/{scene.id}/image-ai")
    assert response.status_code == 200, response.text
    active = response.json()["active_job"]
    assert (active["kind"], active["scene_id"]) == ("image", scene.id)
    job = db.scalar(select(Job).where(Job.video_id == video.id))
    assert job.scene_id == scene.id
    # A second press while it runs is refused, like any other job.
    assert an.post(f"/api/scenes/{scene.id}/image-ai").status_code == 409


def test_retrying_a_scene_job_keeps_its_scene(an, db, me, storage):
    video = make_video(db, storage, me, images=True)
    scene = db.scalar(select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)))
    failed = Job(video_id=video.id, kind="image", status="failed", created_by_id=me.id, scene_id=scene.id)
    db.add(failed)
    db.commit()
    assert an.post(f"/api/jobs/{failed.id}/retry").status_code == 200
    retry = db.scalar(select(Job).where(Job.retry_of_id == failed.id))
    assert retry.scene_id == scene.id


def test_the_job_log_tells_a_scene_job_apart(an, db, me, storage):
    video = make_video(db, storage, me, images=False)
    scene_id = db.scalar(select(Scene.id).where(Scene.video_id == video.id, Scene.is_title.is_(False)))
    db.add(Job(video_id=video.id, kind="image", status="done", created_by_id=me.id, image_calls=1, scene_id=scene_id))
    db.commit()
    row = next(row for row in an.get("/api/jobs").json() if row["kind"] == "image")
    assert row["kind_label"] == "Tạo ảnh AI (1 cảnh)"
