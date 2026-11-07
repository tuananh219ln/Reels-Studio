"""The worker service with real processes, real commits and fake Claude/Pixabay over HTTP."""

import json
import os
import re
import shutil
import subprocess
import time

import psutil
import pytest
from alembic import command
from alembic.config import Config
from conftest import API_DIR, first_topic, make_video
from fake_services import OPENAI_KEY, script_json
from sqlalchemy import select
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

from reels_api import crypto, jobs, llm
from reels_api.models import AppSetting, Job, KnowledgeTopic, LlmProvider, Scene, Video
from reels_api.storage import DirectoryStorage
from reels_api.videos import active_job, script_writer


@pytest.fixture
def services(fakes, worker_env):
    worker_env.update(fakes.env())
    return fakes


def new_video(factory, user, topic="xương khớp sau 50 tuổi") -> int:
    with factory() as db:
        video = Video(topic=topic, knowledge_topic_id=first_topic(db).id, has_script=False, created_by_id=user.id)
        db.add(video)
        db.commit()
        return video.id


def load(factory, video_id):
    with factory() as db:
        video = db.get(Video, video_id)
        scenes = db.scalars(select(Scene).where(Scene.video_id == video_id).order_by(Scene.position)).all()
        return video, scenes


# --- Script jobs ---


def photos_job_done(factory, video_id) -> Job:
    """The "Tự tìm ảnh" job the script job queues, once it has run."""

    def finished():
        with factory() as db:
            job = db.scalar(select(Job).where(Job.video_id == video_id, Job.kind == "photos"))
            return job if job is not None and job.status in ("done", "failed") else None

    wait_until(finished, message="the photo search after the script")
    return finished()


def test_script_job_writes_the_script_then_a_photo_search_fills_the_scenes(committed, services, start_worker):
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
    assert title.voice_text == "Mời bạn xem đến cuối nhé" and content[0].voice_text == "Cá nhỏ giàu canxi"
    assert 5 <= len(content) <= 7 and all(scene.keywords for scene in content)
    assert video.caption and len(video.hashtags) == 5 and len(video.affiliates) == 2 and video.pinned_comment
    assert video.self_review and video.music_suggestions
    assert "Chủ đề: xương khớp sau 50 tuổi" in services.claude_prompts[0]
    assert "chữa khỏi" in services.claude_prompts[0]
    assert "công dụng của món" in services.claude_prompts[0], "the fixed voice rule (issue #70)"
    assert "input_tokens=" in worker.output() and "output_tokens=" in worker.output()
    # The script job picks no photo itself; the "Tự tìm ảnh" job queued after it does, marked for a member to check.
    assert photos_job_done(committed, video_id).status == "done"
    video, scenes = load(committed, video_id)
    assert all(scene.image_key and scene.image_auto for scene in scenes) and video.thumbnail_key


def test_edited_prompt_without_placeholder_gets_the_topic_appended(committed, services, start_worker):
    user = add_user(committed)
    with committed() as db:
        topic = KnowledgeTopic(
            name="Tim mạch",
            script_prompt="Viết 5 món dễ tìm.",
            banned_words=["thần dược"],
            photo_hint="món đã bày ra đĩa",
        )
        db.add(topic)
        db.flush()
        video = Video(topic="tim mạch", knowledge_topic_id=topic.id, has_script=False, created_by_id=user.id)
        db.add(video)
        db.commit()
        video_id = video.id
    job_id = add_job(committed, video_id, user.id)
    start_worker()
    assert wait_for_status(committed, job_id).status == "done"
    prompt = services.claude_prompts[0]
    assert prompt.startswith("Viết 5 món dễ tìm.\n\nChủ đề: tim mạch\n\n")
    assert "thần dược" in prompt and "khắc tinh" not in prompt, "only this topic's banned words"
    assert "Ảnh của nhóm chủ đề này: món đã bày ra đĩa" in prompt, "the group's photo hint"


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
    services.claude_replies = [
        "rác",
        json.dumps(
            {
                "titles": ["MỘT", "HAI"],
                "scenes": [{"text": "Cá\n*canxi*", "seconds": 0.5, "keywords": ["k" * 150]}],
            }
        ),
    ]
    video_id = new_video(committed, user)
    job_id = add_job(committed, video_id, user.id)
    start_worker()

    assert wait_for_status(committed, job_id).claude_calls == 2
    video, scenes = load(committed, video_id)
    assert video.title_options == ["MỘT", "HAI"] and video.music_suggestions == []
    assert scenes[0].keywords == [] and scenes[1].seconds == 4 and scenes[1].keywords == ["k" * 100]


def test_a_retry_after_the_script_was_saved_keeps_the_edits_and_calls_claude_once(committed, services, start_worker):
    user = add_user(committed)
    video_id = new_video(committed, user)
    job_id = add_job(committed, video_id, user.id)
    worker = start_worker()
    assert wait_for_status(committed, job_id).status == "done"
    photos_job_done(committed, video_id)  # one active job per video: the retry waits for the photo search
    _, scenes = load(committed, video_id)
    with committed() as db:
        db.get(Scene, scenes[1].id).text = "Chữ đã sửa tay"
        db.commit()

    retry_id = add_job(committed, video_id, user.id, retry_of_id=job_id)
    assert wait_for_status(committed, retry_id).status == "done"
    _, scenes = load(committed, video_id)
    assert scenes[1].text == "Chữ đã sửa tay"
    assert len(services.claude_prompts) == 1, "the retry must not call Claude again"
    worker.stop()


def test_a_script_job_writes_with_the_provider_the_team_chose(committed, services, start_worker):
    """An OpenAI-compatible provider set up on /settings/ai, reached through the base URL a member gave."""
    user = add_user(committed)
    with committed() as db:
        db.add(
            LlmProvider(
                id="deepseek",
                base_url=f"{services.url}/openai/v1",
                model="fake-gpt-mini",
                key_encrypted=crypto.encrypt(OPENAI_KEY),
                key_tail="-key",
            )
        )
        db.add(AppSetting(key=llm.ACTIVE_KEY, value="deepseek"))
        db.commit()
    video_id = new_video(committed, user)
    job_id = add_job(committed, video_id, user.id)
    worker = start_worker()

    job = wait_for_status(committed, job_id)
    assert (job.status, job.error, job.claude_calls) == ("done", None, 1)
    assert (job.llm_provider, job.llm_model) == ("deepseek", "fake-gpt-mini")
    assert services.chat_requests == [{"model": "fake-gpt-mini", "authorization": f"Bearer {OPENAI_KEY}"}]
    assert "Chủ đề: xương khớp sau 50 tuổi" in services.claude_prompts[0]
    video, scenes = load(committed, video_id)
    assert video.has_script and len(scenes) >= 6
    with committed() as db:
        assert script_writer(db, db.get(Video, video_id)) == "DeepSeek · fake-gpt-mini"
    assert "provider=deepseek model=fake-gpt-mini" in worker.output()


def test_a_cut_off_answer_fails_at_once_with_the_reason(committed, services, start_worker):
    user = add_user(committed)
    services.chat_finish_reason = "length"
    with committed() as db:
        db.add(
            LlmProvider(
                id="custom",
                base_url=f"{services.url}/openai/v1",
                model="fake-gpt-mini",
                key_encrypted=crypto.encrypt(OPENAI_KEY),
                key_tail="-key",
            )
        )
        db.add(AppSetting(key=llm.ACTIVE_KEY, value="custom"))
        db.commit()
    job_id = add_job(committed, new_video(committed, user), user.id)
    start_worker()

    job = wait_for_status(committed, job_id)
    # One request only: asking again would be cut at the same place. (claude_calls counts the answers that came back.)
    assert job.status == "failed" and len(services.chat_requests) == 1
    assert job.error.startswith("Câu trả lời của Tùy chỉnh (chuẩn OpenAI) bị cắt giữa chừng")


def test_a_provider_without_a_key_fails_the_job_without_a_call(committed, services, start_worker):
    user = add_user(committed)
    with committed() as db:
        # Put in use directly: the settings page would refuse it, but a key can still become unreadable.
        db.add(AppSetting(key=llm.ACTIVE_KEY, value="openai"))
        db.commit()
    job_id = add_job(committed, new_video(committed, user), user.id)
    start_worker()

    job = wait_for_status(committed, job_id)
    assert (job.status, job.claude_calls) == ("failed", 0)
    assert job.error == "Chưa có API key cho OpenAI: nhập trong Cài đặt › Mô hình AI"
    assert services.chat_requests == [] and services.claude_prompts == []


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
    start_worker(
        JOB_TIMEOUT_SECONDS="20", FAKE_FFMPEG_PID=str(pid_file), PATH=f"{tools}{os.pathsep}{worker_env['PATH']}"
    )

    pid = int(wait_until(lambda: pid_file.exists() and pid_file.read_text(), 30, message="fake ffmpeg"))
    job = wait_for_status(committed, render_id, timeout=60)
    assert job.status == "failed" and "quá" in job.error and job.error_detail
    wait_until(
        lambda: not psutil.pid_exists(pid) or psutil.Process(pid).status() == psutil.STATUS_ZOMBIE,
        10,
        message="ffmpeg to die",
    )
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
    # The lock is logged before the worker fails interrupted jobs: a job it has served proves that step is over,
    # otherwise the first worker itself could fail the job added below.
    assert wait_for_status(committed, add_job(committed, new_video(committed, user), user.id)).status == "done"
    # Looks like the first worker's job in progress: the second one must leave it alone.
    running_id = add_job(committed, new_video(committed, user), user.id, status="running")
    second = start_worker()
    wait_until(lambda: "Another worker is active" in second.output(), 30, message="second worker waiting")
    time.sleep(2)
    assert job_row(committed, running_id).status == "running"

    first.stop()
    assert (
        wait_for_status(committed, running_id, statuses=("failed",), timeout=30).error
        == "Worker khởi động lại giữa chừng"
    )
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
        video.voice_enabled = False
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


# --- Part 2: clone jobs and music ---


def test_clone_job_writes_a_new_script_from_the_snapshot(committed, services, start_worker):
    user = add_user(committed)
    snapshot = {
        "video_id": 1,
        "title": "5 MÓN BỔ XƯƠNG",
        "topic": "xương khớp",
        "script": "Cảnh 1 (4 giây): Cá nhỏ / Giàu *canxi*",
        "request": "đổi sang mốc 45 tuổi, tim mạch",
    }
    with committed() as db:
        draft = Video(
            topic=snapshot["request"],
            knowledge_topic_id=first_topic(db).id,
            has_script=False,
            created_by_id=user.id,
            clone_source=snapshot,
        )
        db.add(draft)
        db.commit()
    reply = {**script_json("tim mạch"), "music_suggestions": ["River Flows In You"]}
    reply["scenes"][0]["voice"] = "Cá nhỏ có canxi ngay trong phần xương, hỗ trợ xương chắc, nhớ nhai kỹ."
    services.claude_replies = [reply]
    job_id = add_job(committed, draft.id, user.id, kind="clone")
    start_worker()

    assert wait_for_status(committed, job_id).status == "done"
    prompt = services.claude_prompts[0]
    assert prompt.startswith('Video gốc: "5 MÓN BỔ XƯƠNG" — chủ đề: xương khớp.')
    assert "Cảnh 1 (4 giây): Cá nhỏ / Giàu *canxi*" in prompt and "đổi sang mốc 45 tuổi, tim mạch" in prompt
    assert "công dụng của món" in prompt and "không mô tả cách nấu" in prompt, "clones share the voice rule"
    video, scenes = load(committed, draft.id)
    assert video.has_script and video.music_suggestions == ["River Flows In You"]
    assert scenes[1].voice_text == "Cá nhỏ có canxi ngay trong phần xương, hỗ trợ xương chắc, nhớ nhai kỹ."
    assert not any(scene.image_key for scene in scenes)


def test_clone_job_uses_the_edited_clone_prompt(committed, services, start_worker):
    user = add_user(committed)
    with committed() as db:
        topic = KnowledgeTopic(name="Tim mạch", clone_prompt="Viết biến thể của [tiêu đề] theo: [yêu cầu đổi]")
        db.add(topic)
        db.flush()
        draft = Video(
            topic="tim mạch",
            knowledge_topic_id=topic.id,
            has_script=False,
            created_by_id=user.id,
            clone_source={
                "video_id": 1,
                "title": "5 MÓN BỔ XƯƠNG",
                "topic": "xương khớp",
                "script": "Cảnh 1 (4 giây): Cá",
                "request": "tim mạch",
            },
        )
        db.add(draft)
        db.commit()
    job_id = add_job(committed, draft.id, user.id, kind="clone")
    start_worker()

    assert wait_for_status(committed, job_id).status == "done"
    assert services.claude_prompts[0].startswith(
        "Viết biến thể của 5 MÓN BỔ XƯƠNG theo: tim mạch\n\n"
        "Chủ đề video gốc: xương khớp\n\n"
        "Kịch bản đã sửa của video gốc: Cảnh 1 (4 giây): Cá\n\n"
    )


needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg/ffprobe không có trên PATH")


def make_mp3(path, seconds=4):
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds}",
            "-ac",
            "2",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "128k",
            str(path),
        ],
        check=True,
    )
    return path.read_bytes()


def mean_volume(media) -> float:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(media), "-vn", "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    value = re.search(r"mean_volume: (-?[\d.]+|-inf) dB", result.stderr).group(1)
    return float("-inf") if value == "-inf" else float(value)


@pytest.fixture
def short_video(committed, tmp_path):
    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    with committed() as db:
        video = make_video(db, storage, user, scene_count=1, seconds=2)
        video.voice_enabled = False
        db.commit()
    return user, storage, video.id


def set_music(factory, storage, video_id, data, volume):
    with factory() as db:
        video = db.get(Video, video_id)
        video.music_key, video.music_volume = f"videos/{video_id}/music-test.mp3", volume
        storage.save_bytes(video.music_key, data)
        db.commit()


def rendered_mp4(factory, storage, video_id, user_id):
    job = run_render(factory, storage, video_id, user_id)
    assert job.status == "done", (job.error, job.error_detail)
    with factory() as db:
        return storage.path(db.get(Video, video_id).mp4_key)


@needs_ffmpeg
def test_music_and_volume_reach_the_mp4_and_removing_it_renders_silence(committed, short_video, tmp_path):
    user, storage, video_id = short_video
    tone = make_mp3(tmp_path / "tone.mp3")
    set_music(committed, storage, video_id, tone, 100)
    loud = mean_volume(rendered_mp4(committed, storage, video_id, user.id))
    set_music(committed, storage, video_id, tone, 25)
    soft = mean_volume(rendered_mp4(committed, storage, video_id, user.id))
    # 25% of the amplitude is about 12 dB quieter.
    assert loud - soft == pytest.approx(12, abs=2)

    with committed() as db:
        db.get(Video, video_id).music_key = None
        db.commit()
    assert mean_volume(rendered_mp4(committed, storage, video_id, user.id)) < -80


@needs_ffmpeg
def test_a_broken_mp3_fails_the_render_with_a_clear_reason(committed, short_video):
    user, storage, video_id = short_video
    set_music(committed, storage, video_id, b"ID3\x04\x00\x00\x00\x00\x00\x00" + bytes(range(256)) * 40, 25)
    job = run_render(committed, storage, video_id, user.id)
    assert (job.status, job.error) == ("failed", "File nhạc không đọc được")
    with committed() as db:
        assert db.get(Video, video_id).mp4_key is None


@needs_ffmpeg
def test_a_title_clip_renders_from_its_start_and_matches_the_thumbnail(committed, short_video, tmp_path):
    from conftest import clip_bytes
    from PIL import Image, ImageChops, ImageStat

    from reels_api.videos import refresh_thumbnail, split_scenes

    user, storage, video_id = short_video
    with committed() as db:
        video = db.get(Video, video_id)
        title, _ = split_scenes(db, video)
        title.video_key, title.video_seconds, title.video_start = f"videos/{video_id}/clip-t.mp4", 3.0, 1.0
        title.image_key = None
        storage.save_bytes(title.video_key, clip_bytes(tmp_path, seconds=3))
        refresh_thumbnail(db, storage, video, title)
        db.commit()
        thumbnail = Image.open(storage.path(video.thumbnail_key)).convert("RGB")

    mp4 = rendered_mp4(committed, storage, video_id, user.id)
    first = tmp_path / "first.png"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(mp4), "-frames:v", "1", "-s", "540x960", str(first)], check=True
    )
    difference = ImageStat.Stat(ImageChops.difference(Image.open(first).convert("RGB"), thumbnail)).mean
    assert sum(difference) / 3 <= 4, "the MP4 opens on the clip frame the thumbnail shows"
    assert mean_volume(mp4) < -80, "the clip's own sound never reaches the MP4"
