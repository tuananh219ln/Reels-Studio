"""The image job: AI photos (fake Gemini) for the scenes that have none, plus its endpoint."""

import pytest
from conftest import first_topic, login, make_user, make_video
from sqlalchemy import select
from worker_helpers import add_job, add_user, committed, job_row  # noqa: F401  (fixtures)

from reels_api import jobs
from reels_api.models import Job, Scene, Video


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
    # The title scene has no image prompt: its first line of text is the prompt.
    assert fakes.image_gen_prompts[0] == "5 MÓN GIÚP"
    assert fakes.image_gen_prompts[1:] == [f"Ảnh món {n} trên bàn gỗ" for n in (1, 2, 3)]
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


def test_no_key_configured_fails_with_a_clear_message(committed, fakes, storage, monkeypatch):
    user = add_user(committed)
    video_id = build(committed, storage, user)
    monkeypatch.setenv("IMAGE_GEN_API_KEY", "")

    job = run_image_job(committed, storage, video_id, user.id)

    assert job.status == "failed" and "Chưa cấu hình IMAGE_GEN_API_KEY" in (job.error or "")
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
