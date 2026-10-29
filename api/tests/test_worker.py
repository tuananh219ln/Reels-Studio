"""The worker service with real processes, real commits and fake Claude/Pixabay over HTTP."""

import json
import os
import time

import psutil
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select

from conftest import API_DIR, make_video
from reels_api import jobs
from reels_api.models import Job, Scene, Video
from reels_api.storage import DirectoryStorage
from reels_api.videos import active_job
from worker_helpers import (  # noqa: F401  (fixtures)
    add_job,
    add_user,
    committed,
    fake_tools,
    job_row,
    start_worker,
    wait_for_status,
    wait_until,
    worker_env,
)


@pytest.fixture
def services(fakes, worker_env):
    worker_env.update(fakes.env())
    return fakes


def new_video(factory, user, topic="xương khớp sau 50 tuổi") -> int:
    with factory() as db:
        video = Video(topic=topic, has_script=False, created_by_id=user.id)
        db.add(video)
        db.commit()
        return video.id


def load(factory, video_id):
    with factory() as db:
        video = db.get(Video, video_id)
        scenes = db.scalars(select(Scene).where(Scene.video_id == video_id).order_by(Scene.position)).all()
        return video, scenes


# --- Script jobs ---

def test_script_job_writes_the_script_and_assigns_pixabay_photos(committed, services, start_worker, tmp_path):
    user = add_user(committed)
    video_id = new_video(committed, user)
    job_id = add_job(committed, video_id, user.id)
    worker = start_worker()

    job = wait_for_status(committed, job_id)
    assert (job.status, job.error, job.claude_calls) == ("done", None, 1)
    video, scenes = load(committed, video_id)
    title, content = scenes[0], scenes[1:]
    assert video.has_script and len(video.title_options) == 5
    assert title.is_title and title.text == video.title_options[0] and title.seconds == 3
    assert 5 <= len(content) <= 7 and all(scene.keywords for scene in content)
    assert video.caption and len(video.hashtags) == 5 and len(video.affiliates) == 2 and video.pinned_comment
    assert video.self_review and video.music_suggestions
    assert all(scene.image_key for scene in scenes) and len({s.image_source for s in scenes}) == len(scenes)
    assert video.thumbnail_key and DirectoryStorage(tmp_path / "storage").exists(video.thumbnail_key)
    assert "Chủ đề: xương khớp sau 50 tuổi" in services.claude_prompts[0]
    assert "chữa khỏi" in services.claude_prompts[0]
    assert "input_tokens=" in worker.output() and "output_tokens=" in worker.output()


def test_edited_prompt_without_placeholder_gets_the_topic_appended(committed, services, start_worker):
    from reels_api import knowledge

    user = add_user(committed)
    with committed() as db:
        knowledge.put(db, knowledge.SCRIPT_PROMPT, "Viết 5 món dễ tìm.", user.id)
        db.commit()
    job_id = add_job(committed, new_video(committed, user, topic="tim mạch"), user.id)
    start_worker()
    assert wait_for_status(committed, job_id).status == "done"
    assert services.claude_prompts[0].startswith("Viết 5 món dễ tìm.\n\nChủ đề: tim mạch\n\n")


def test_a_broken_answer_is_retried_once_then_the_job_fails(committed, services, start_worker):
    user = add_user(committed)
    services.claude_replies = ["không phải JSON", '{"titles": ["A"], "scenes": []}']
    video_id = new_video(committed, user)
    job_id = add_job(committed, video_id, user.id)
    start_worker()

    job = wait_for_status(committed, job_id)
    assert (job.status, job.claude_calls) == ("failed", 2)
    assert "không có cảnh nội dung nào" in job.error
    assert '{"titles": ["A"], "scenes": []}' in job.error_detail
    assert load(committed, video_id)[0].has_script is False


def test_slightly_off_answers_are_repaired_and_saved(committed, services, start_worker):
    user = add_user(committed)
    services.claude_replies = ["rác", json.dumps({
        "titles": ["MỘT", "HAI"],
        "scenes": [{"text": "Cá\n*canxi*", "seconds": 0.5, "keywords": ["k" * 150]}],
    })]
    video_id = new_video(committed, user)
    job_id = add_job(committed, video_id, user.id)
    start_worker()

    assert wait_for_status(committed, job_id).claude_calls == 2
    video, scenes = load(committed, video_id)
    assert video.title_options == ["MỘT", "HAI"] and video.music_suggestions == []
    assert scenes[0].keywords == [] and scenes[1].seconds == 4 and scenes[1].keywords == ["k" * 100]


def test_pixabay_failure_keeps_the_script_and_a_retry_only_fills_photos(committed, services, start_worker):
    user = add_user(committed)
    services.pixabay_mode = "error500"
    video_id = new_video(committed, user)
    job_id = add_job(committed, video_id, user.id)
    worker = start_worker()

    job = wait_for_status(committed, job_id)
    assert job.status == "failed" and "chưa gán được ảnh Pixabay" in job.error and "server" in job.error_detail
    video, scenes = load(committed, video_id)
    assert video.has_script and all(not s.image_key and "Pixabay đang lỗi" in s.image_error for s in scenes)

    # Meanwhile a member edits a text and uploads a photo for scene 2.
    with committed() as db:
        edited = db.get(Scene, scenes[1].id)
        edited.text = "Chữ đã sửa tay"
        uploaded = db.get(Scene, scenes[2].id)
        uploaded.image_key, uploaded.image_source, uploaded.image_error = "videos/x/uploaded.jpg", "upload", None
        db.commit()
    services.pixabay_mode = "ok"
    retry_id = add_job(committed, video_id, user.id, retry_of_id=job_id)
    assert wait_for_status(committed, retry_id).status == "done"
    _, scenes = load(committed, video_id)
    assert all(s.image_key and s.image_error is None for s in scenes)
    assert scenes[1].text == "Chữ đã sửa tay"
    assert (scenes[2].image_key, scenes[2].image_source) == ("videos/x/uploaded.jpg", "upload")
    assert len(services.claude_prompts) == 1, "the retry must not call Claude again"
    assert job_row(committed, job_id).status == "failed"
    worker.stop()


def test_scenes_without_pixabay_results_are_marked_and_the_job_finishes(committed, services, start_worker):
    user = add_user(committed)
    services.pixabay_mode = "empty"
    video_id = new_video(committed, user)
    job_id = add_job(committed, video_id, user.id)
    start_worker()
    assert wait_for_status(committed, job_id).status == "done"
    _, scenes = load(committed, video_id)
    assert all("Không tìm thấy ảnh Pixabay" in scene.image_error for scene in scenes)


# --- The loop ---

def test_jobs_run_one_after_another_in_queue_order(committed, services, start_worker):
    user = add_user(committed)
    ids = [add_job(committed, new_video(committed, user, topic=f"chủ đề {n}"), user.id) for n in range(3)]
    start_worker()
    finished = [wait_for_status(committed, job_id) for job_id in ids]
    assert all(job.status == "done" for job in finished)
    for earlier, later in zip(finished, finished[1:]):
        assert later.started_at >= earlier.finished_at


def test_a_job_over_the_time_limit_is_killed_with_its_ffmpeg(committed, services, start_worker, worker_env, tmp_path):
    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    with committed() as db:
        video = make_video(db, storage, user)
    pid_file = tmp_path / "ffmpeg.pid"
    tools = fake_tools(tmp_path / "hanging-tools", "hang")
    render_id = add_job(committed, video.id, user.id, kind="render")
    next_id = add_job(committed, new_video(committed, user), user.id)
    start_worker(JOB_TIMEOUT_SECONDS="20", FAKE_FFMPEG_PID=str(pid_file),
                 PATH=f"{tools}{os.pathsep}{worker_env['PATH']}")

    pid = int(wait_until(lambda: pid_file.exists() and pid_file.read_text(), 30, message="fake ffmpeg"))
    job = wait_for_status(committed, render_id, timeout=60)
    assert job.status == "failed" and "quá" in job.error and job.error_detail
    wait_until(lambda: not psutil.pid_exists(pid) or psutil.Process(pid).status() == psutil.STATUS_ZOMBIE,
               10, message="ffmpeg to die")
    with committed() as db:
        assert db.get(Video, video.id).mp4_key is None
        assert active_job(db, video.id) is None
    assert wait_for_status(committed, next_id).status == "done", "the next job runs without a restart"


def test_a_restarted_worker_fails_the_interrupted_job_and_does_not_rerun_it(committed, services, start_worker):
    user = add_user(committed)
    video_id = new_video(committed, user)
    job_id = add_job(committed, video_id, user.id, status="running")
    start_worker()
    job = wait_for_status(committed, job_id, statuses=("failed",))
    assert job.error == "Worker khởi động lại giữa chừng"
    time.sleep(2)
    with committed() as db:
        assert active_job(db, video_id) is None
        assert [j.status for j in db.scalars(select(Job).where(Job.video_id == video_id))] == ["failed"]
    assert services.claude_prompts == []


def test_a_second_worker_waits_for_the_lock_before_cleaning_or_claiming(committed, services, start_worker):
    user = add_user(committed)
    first = start_worker()
    wait_until(lambda: "Worker lock acquired" in first.output(), 30, message="first worker lock")
    # Looks like the first worker's job in progress: the second one must leave it alone.
    running_id = add_job(committed, new_video(committed, user), user.id, status="running")
    second = start_worker()
    wait_until(lambda: "Another worker is active" in second.output(), 30, message="second worker waiting")
    time.sleep(2)
    assert job_row(committed, running_id).status == "running"

    first.stop()
    assert wait_for_status(committed, running_id, statuses=("failed",), timeout=30).error == \
        "Worker khởi động lại giữa chừng"
    queued_id = add_job(committed, new_video(committed, user), user.id)
    assert wait_for_status(committed, queued_id).status == "done"
    assert second.process.poll() is None


def test_the_worker_waits_while_the_jobs_table_is_missing(committed, engine, services, start_worker):
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", engine.url.render_as_string(hide_password=False))
    config.attributes["configure_logger"] = False
    command.downgrade(config, "0001")
    try:
        worker = start_worker()
        wait_until(lambda: "Table jobs does not exist yet" in worker.output(), 30, message="waiting log")
        assert worker.process.poll() is None
    finally:
        command.upgrade(config, "head")
    user = add_user(committed)
    job_id = add_job(committed, new_video(committed, user), user.id)
    assert wait_for_status(committed, job_id, timeout=60).status == "done"


# --- Render jobs, in process ---

def run_render(factory, storage, video_id, user_id) -> Job:
    job_id = add_job(factory, video_id, user_id, kind="render", status="running")
    jobs.run_job(job_id, factory, storage)
    return job_row(factory, job_id)


def test_ffmpeg_failure_stores_its_stderr_and_keeps_the_old_mp4(committed, tmp_path, monkeypatch):
    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    with committed() as db:
        video = make_video(db, storage, user)
        video.mp4_key = f"videos/{video.id}/video-old.mp4"
        storage.save_bytes(video.mp4_key, b"old mp4")
        db.commit()
    tools = fake_tools(tmp_path / "failing-tools", "fail")
    monkeypatch.setenv("PATH", f"{tools}{os.pathsep}{os.environ['PATH']}")

    job = run_render(committed, storage, video.id, user.id)
    assert (job.status, job.error) == ("failed", "FFmpeg lỗi khi render video")
    assert "boom from fake ffmpeg" in job.error_detail
    with committed() as db:
        assert db.get(Video, video.id).mp4_key == video.mp4_key
    assert storage.path(video.mp4_key).read_bytes() == b"old mp4"
    assert not jobs.work_dir(job.id).exists()


# --- Cancel racing the claim ---

def test_cancel_waits_for_a_claim_in_progress_and_then_refuses(committed, monkeypatch):
    import threading

    from conftest import PASSWORD, WEB_ORIGIN, client_for, login
    from reels_api.db import get_db
    from reels_api.main import create_app

    user = add_user(committed)
    job_id = add_job(committed, new_video(committed, user), user.id)
    monkeypatch.setenv("ALLOWED_ORIGINS", WEB_ORIGIN)
    app = create_app()

    def real_db():
        with committed() as session:
            yield session

    app.dependency_overrides[get_db] = real_db
    client = client_for(app)
    login(client, password=PASSWORD)

    # The worker's claim transaction: the row is locked and marked running, not yet committed.
    with committed() as worker_db:
        job = worker_db.scalar(select(Job).where(Job.id == job_id).with_for_update(skip_locked=True))
        job.status = "running"
        worker_db.flush()
        result = {}
        cancel = threading.Thread(target=lambda: result.update(response=client.post(f"/api/jobs/{job_id}/cancel")))
        cancel.start()
        cancel.join(timeout=2)
        assert cancel.is_alive(), "cancel must wait for the claim's row lock"
        worker_db.commit()
    cancel.join(timeout=10)
    assert result["response"].status_code == 409
    assert job_row(committed, job_id).status == "running"


def test_a_job_being_cancelled_is_skipped_by_the_claim_and_never_runs(committed):
    from reels_api.worker import claim_next

    user = add_user(committed)
    job_id = add_job(committed, new_video(committed, user), user.id)
    import threading

    with committed() as cancel_db:
        job = cancel_db.scalar(select(Job).where(Job.id == job_id).with_for_update())
        # In a thread: a claim that waited for the lock would otherwise hang this test instead of failing it.
        claimed = []
        claim = threading.Thread(target=lambda: claimed.append(claim_next(committed)), daemon=True)
        claim.start()
        claim.join(timeout=5)
        assert not claim.is_alive() and claimed == [None], "a row locked by a cancel is skipped, not waited for"
        job.status = "cancelled"
        cancel_db.commit()
    assert claim_next(committed) is None
    assert job_row(committed, job_id).status == "cancelled"
