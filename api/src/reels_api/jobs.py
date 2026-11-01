"""What one job does. Runs inside the per-job child process started by the worker loop (worker.py)."""

import logging
import shutil
import tempfile
import time
import traceback
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

from sqlalchemy import update
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from reels_render import RenderError, render_video
from reels_render.errors import FFmpegError
from reels_render.ffmpeg import audio_seconds, find_tools, probe
from reels_render.script import parse_script

from . import config, facebook, fanpages, knowledge, llm, source_keys
from .claude import (
    ClaudeError,
    GeneratedScript,
    build_clone_prompt,
    build_script_prompt,
    generate_script,
)
from .facebook import FacebookError
from .imagegen import ImageGenError, generate_image
from .models import Job, Publication, Scene, Video
from .sessions import now
from .storage import DirectoryStorage
from .tts import TtsError, synthesize, voice_signature
from .uploads import MAX_IMAGE_BYTES, UploadRejected, image_extension
from .video_options import render_options, voice_id, voice_speed
from .videos import (
    made_voice_seconds,
    new_key,
    publication_of,
    refresh_thumbnail,
    render_signature,
    run_checks,
    split_scenes,
    spoken,
)

log = logging.getLogger(__name__)

TITLE_SECONDS = 3
# Auto-assign runs in the worker, not in a request, so each scene's search may take longer.


class JobFailure(Exception):
    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.message = message
        self.detail = detail


def work_dir(job_id: int) -> Path:
    """Fixed per job, so the worker loop can remove it even after killing the child."""
    return Path(tempfile.gettempdir()) / f"reels-job-{job_id}"


def run_job(
    job_id: int, factory: sessionmaker, storage: DirectoryStorage, call: Callable[[str, str], str] | None = None
) -> None:
    """`call` replaces the team's LLM (see llm.py) in unit tests that run a job in-process."""
    with factory() as db:
        job = db.get(Job, job_id)
        if job is None or job.status != "running":
            log.warning("Job %s is not running (%s), skipped", job_id, job.status if job else "deleted")
            return
        log.info("Job %s (%s) for video %s started", job.id, job.kind, job.video_id)
        try:
            if job.kind in ("script", "clone"):
                run_script_job(db, job, call)
            elif job.kind == "render":
                run_render_job(db, job, storage)
            elif job.kind == "image":
                run_image_job(db, job, storage)
            elif job.kind == "publish":
                run_publish_job(db, job, storage)
            else:
                raise JobFailure(f"Loại job không hỗ trợ: {job.kind}")
        except JobFailure as err:
            db.rollback()
            _finish(db, job_id, "failed", err.message, err.detail)
            log.warning("Job %s failed: %s\n%s", job_id, err.message, err.detail)
            return
        except Exception:
            db.rollback()
            detail = traceback.format_exc()[-4000:]
            _finish(db, job_id, "failed", "Lỗi không mong đợi trong worker", detail)
            log.exception("Job %s crashed", job_id)
            return
        _finish(db, job_id, "done")
        log.info("Job %s done", job_id)


def _finish(db: DbSession, job_id: int, status: str, error: str | None = None, detail: str | None = None) -> None:
    db.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(status=status, finished_at=now(), error=error, error_detail=detail or None)
    )
    db.commit()


# --- Script ---


def run_script_job(db: DbSession, job: Job, call: Callable[[str, str], str] | None) -> None:
    video = db.get(Video, job.video_id)
    # A retried job whose script was already saved has nothing to do: no new Claude call,
    # and nothing the members edited meanwhile is overwritten.
    if not video.has_script:
        topic = knowledge.topic_of(db, video)
        if topic is None:
            raise JobFailure("Video chưa thuộc nhóm chủ đề nào trong Kho kiến thức")
        if job.kind == "clone":
            # The snapshot from the moment "Nhân bản" was pressed: later edits of the source do not count.
            prompt = build_clone_prompt(topic.clone_prompt, video.clone_source, topic.banned_words)
        else:
            prompt = build_script_prompt(topic.script_prompt, video.topic, topic.banned_words)

        if call is None:
            # The provider chosen on /settings/ai when the job starts; the job remembers which one wrote the script.
            target = llm.active_target(db)
            db.execute(update(Job).where(Job.id == job.id).values(llm_provider=target.provider, llm_model=target.model))
            db.commit()

            def call(prompt: str, label: str) -> str:
                return llm.complete(target, prompt, label)

        def count_call() -> None:
            db.execute(update(Job).where(Job.id == job.id).values(claude_calls=Job.claude_calls + 1))
            db.commit()

        try:
            script = generate_script(prompt, f"job {job.id}", count_call, call)
        except ClaudeError as err:
            raise JobFailure(err.message, err.detail) from None
        save_script(db, video, script)
        db.commit()


def save_script(db: DbSession, video: Video, script: GeneratedScript) -> None:
    video.has_script = True
    video.title_options = script.titles
    video.caption = script.caption
    video.hashtags = script.hashtags
    video.affiliates = script.affiliates
    video.pinned_comment = script.pinned_comment
    video.self_review = script.self_review
    video.music_suggestions = script.music_suggestions
    db.add(
        Scene(
            video_id=video.id,
            is_title=True,
            position=0,
            text=script.titles[0],
            seconds=TITLE_SECONDS,
            keywords=script.title_keywords,
            keywords_en=script.title_keywords_en,
            image_prompt="",
            voice_text=script.title_voice,
        )
    )
    for position, scene in enumerate(script.scenes, start=1):
        db.add(
            Scene(
                video_id=video.id,
                is_title=False,
                position=position,
                text=scene.text,
                seconds=scene.seconds,
                keywords=scene.keywords,
                keywords_en=scene.keywords_en,
                image_prompt=scene.image_prompt,
                voice_text=scene.voice,
            )
        )


# --- Render ---

MUSIC_UNREADABLE = "File nhạc không đọc được"


def _checked_music(video: Video, storage: DirectoryStorage, folder: Path) -> Path | None:
    """The MP3 for this render, or None for a silent video; a file FFmpeg cannot read fails the job here,
    with a clear reason, instead of as an FFmpeg error in the middle of the render."""
    if not video.music_key:
        return None
    if not storage.exists(video.music_key):
        raise JobFailure(MUSIC_UNREADABLE, "Không thấy file nhạc trong storage, hãy tải nhạc lên lại")
    music = storage.copy_to(video.music_key, folder / "music.mp3")
    try:
        streams = probe(find_tools().ffprobe, music).get("streams", [])
    except FFmpegError as err:
        raise JobFailure(MUSIC_UNREADABLE, err.stderr_tail) from None
    if not any(stream.get("codec_type") == "audio" for stream in streams):
        raise JobFailure(MUSIC_UNREADABLE, "File không có luồng âm thanh")
    return music


def _image_model(provider: str) -> str:
    return config.image_gen_cf_model() if provider == "cloudflare" else config.image_gen_model()


def _scene_label(scene: Scene, index: int) -> str:
    return "Cảnh tiêu đề" if scene.is_title else f"Cảnh {index}"


def make_voices(db: DbSession, video: Video, scenes: list[Scene], storage: DirectoryStorage) -> None:
    """Narration for every scene that has voice text but no MP3 made from it yet. Each MP3 is committed at once,
    so a retry after a failure pays ElevenLabs only for the scenes still missing."""
    for index, scene in enumerate(scenes):
        text = spoken(video, scene)
        if not text or (made_voice_seconds(video, scene) is not None and storage.exists(scene.voice_key)):
            continue
        label = _scene_label(scene, index)
        try:
            data = synthesize(text, voice_id(video), voice_speed(video))
        except TtsError as err:
            raise JobFailure(f"{label}: {err.message}", err.detail) from None
        key = new_key(video.id, f"voice-{scene.id}", "mp3")
        storage.save_bytes(key, data)
        try:
            seconds = audio_seconds(find_tools().ffprobe, storage.path(key))
        except FFmpegError:
            seconds = None
        if seconds is None:
            storage.delete(key)
            raise JobFailure(f"{label}: ElevenLabs trả file lời đọc không đọc được, thử lại sau")
        old = scene.voice_key
        scene.voice_key, scene.voice_signature, scene.voice_seconds = (
            key,
            voice_signature(text, voice_id(video), voice_speed(video)),
            seconds,
        )
        db.commit()
        if old and old != key:
            storage.delete(old)
        log.info("Narration for video %s %s: %.1fs", video.id, label, seconds)


def run_render_job(db: DbSession, job: Job, storage: DirectoryStorage) -> None:
    video = db.get(Video, job.video_id)
    title, scenes = split_scenes(db, video)
    if title is None or not scenes:
        raise JobFailure("Video chưa có kịch bản đủ để render")
    folder = work_dir(job.id)
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    try:
        make_voices(db, video, [title, *scenes], storage)
        # Narration lengthens its scene, so the total is only known now.
        blocking = run_checks(db, video, title, scenes).blocking
        if blocking:
            raise JobFailure(
                f"Chưa render được: {blocking[0].message}",
                "Lời đọc làm cảnh dài thêm: hãy rút gọn lời đọc hoặc bớt cảnh",
            )

        def entry(scene: Scene, index: int) -> dict:
            label = _scene_label(scene, index)
            # No "keywords": every photo or clip is already chosen, the renderer must never search stock itself.
            if scene.video_key:
                if not storage.exists(scene.video_key):
                    raise JobFailure(f"{label} chưa có video trong storage, hãy tải video lên lại rồi render")
                extension = scene.video_key.rsplit(".", 1)[-1]
                clip = storage.copy_to(scene.video_key, folder / f"clip-{index:02d}.{extension}")
                data = {
                    "text": scene.text,
                    "seconds": scene.seconds,
                    "video": clip.name,
                    "video_start": scene.video_start,
                }
            else:
                if not scene.image_key or not storage.exists(scene.image_key):
                    raise JobFailure(f"{label} chưa có ảnh trong storage, hãy gán lại ảnh rồi render")
                image = storage.copy_to(
                    scene.image_key, folder / f"image-{index:02d}.{scene.image_key.rsplit('.', 1)[-1]}"
                )
                data = {"text": scene.text, "seconds": scene.seconds, "image": image.name}
            if spoken(video, scene):
                data["voice"] = storage.copy_to(scene.voice_key, folder / f"voice-{index:02d}.mp3").name
                data["voice_text"] = spoken(video, scene)
            return data

        data = {"title": entry(title, 0), "scenes": [entry(scene, index) for index, scene in enumerate(scenes, 1)]}
        signature = render_signature(video, title, scenes)
        music = _checked_music(video, storage, folder)
        output = folder / "video.mp4"
        started = time.monotonic()
        try:
            render_video(
                parse_script(data, base_dir=folder),
                output,
                music=music,
                music_volume=video.music_volume / 100,
                options=render_options(video),
            )
            seconds = float(probe(find_tools().ffprobe, output)["format"]["duration"])
        except FFmpegError as err:
            raise JobFailure("FFmpeg lỗi khi render video", err.stderr_tail) from None
        except RenderError as err:
            raise JobFailure(str(err)) from None
        elapsed = time.monotonic() - started

        key = new_key(video.id, "video", "mp4")
        storage.save_file(key, output)
        old = video.mp4_key
        video.mp4_key, video.mp4_seconds, video.render_seconds = key, seconds, round(elapsed, 1)
        video.rendered_signature, video.rendered_at = signature, now()
        db.commit()
        # The old MP4 stays playable until the new one is committed.
        if old and old != key:
            storage.delete(old)
        log.info("Job %s rendered %.1fs of video in %.1fs", job.id, seconds, elapsed)
    finally:
        shutil.rmtree(folder, ignore_errors=True)


# --- Publish ---

# Facebook refuses a scheduled time less than 10 minutes away.
MIN_SCHEDULE_LEAD = timedelta(minutes=10)
# After this long, a reel Facebook was asked to publish and still has not is taken as dropped.
SETTLE_TIME = timedelta(minutes=30)


def run_publish_job(db: DbSession, job: Job, storage: DirectoryStorage) -> None:
    video = db.get(Video, job.video_id)
    post = publication_of(db, video.id)
    if post is None or post.status != "pending":
        return
    try:
        # An attempt before this one may have reached Facebook whatever it reported, so its reel decides first.
        page = fanpages.load_page(db, post.fanpage_id)
        status = facebook.reel_status(page, post.remote_id) if post.remote_id else None
        asked = status is not None and post.finish_sent_at is not None and not facebook.is_failed(status)
        if asked and facebook.is_busy(status):
            status = facebook.wait_until_live(page, post.remote_id)
        if status is None or not facebook.is_live(status):
            _check_publishable(db, video, post, storage)
            # A reel is finished again only if it holds this very MP4; a new render gets a reel of its own.
            if status is None or not facebook.is_uploaded(status) or post.remote_mp4_key != video.mp4_key:
                # Facebook may still publish a reel it was asked to, and a new one would then be a second post.
                if asked and now() - post.finish_sent_at < SETTLE_TIME:
                    raise JobFailure("Facebook có thể vẫn đang đăng bản trước, hãy xem Page, đợi 30 phút rồi Thử lại")
                post.remote_id, upload_url = facebook.start_upload(page)
                post.remote_mp4_key, post.finish_sent_at = video.mp4_key, None
                db.commit()
                facebook.upload(page, upload_url, storage.path(video.mp4_key))
            post.finish_sent_at = now()
            db.commit()
            _finish_reel(db, page, video, post)
            status = facebook.wait_until_live(page, post.remote_id)
    except FacebookError as err:
        raise JobFailure(err.message, err.detail) from None
    # What Facebook says counts: after a lost answer it can differ from what the member asked for last.
    post.status = "scheduled" if facebook.is_scheduled(status) else "published"
    post.scheduled_at = (facebook.scheduled_time(status) or post.scheduled_at) if post.status == "scheduled" else None
    post.published_at = now()
    db.commit()
    log.info("Job %s posted video %s to Facebook as %s", job.id, video.id, post.remote_id)


def _finish_reel(db: DbSession, page: facebook.Page, video: Video, post: Publication) -> None:
    description = f"{video.caption}\n\n{' '.join(video.hashtags)}".strip()
    try:
        facebook.finish(page, post.remote_id, description, post.scheduled_at)
    except FacebookError as err:
        # Only a refusal proves Facebook will not publish it; a lost or 5xx answer proves nothing.
        if 400 <= err.status < 500:
            post.finish_sent_at = None
            db.commit()
        raise


def _check_publishable(db: DbSession, video: Video, post: Publication, storage: DirectoryStorage) -> None:
    """Also covers "Thử lại", which does not pass through the publish endpoint."""
    title, scenes = split_scenes(db, video)
    if video.rendered_signature != render_signature(video, title, scenes):
        raise JobFailure("MP4 chưa cập nhật theo bản sửa, hãy render lại rồi đăng")
    if post.scheduled_at is not None and post.scheduled_at < now() + MIN_SCHEDULE_LEAD:
        raise JobFailure("Giờ hẹn đã qua hoặc còn dưới 10 phút, hãy chọn giờ khác rồi bấm đăng lại")
    if not video.mp4_key or not storage.exists(video.mp4_key):
        raise JobFailure("Không thấy file MP4 trong storage, hãy render lại rồi đăng")


# --- Images ---


def run_image_job(db: DbSession, job: Job, storage: DirectoryStorage) -> None:
    """AI photos for the scenes that have neither a photo nor a clip yet.

    Every finished scene is committed at once, so a cancelled job (or a dead worker) keeps
    the photos already paid for, and pressing the button again only pays for the scenes
    still missing one. A prompt Gemini refuses fails only its scene: the reason stays on
    the scene's `image_error`, where members see it. Only a provider-wide failure (no key,
    quota) fails the job, after the scenes already done.
    """
    video = db.get(Video, job.video_id)
    title, scenes = split_scenes(db, video)
    if title is None:
        raise JobFailure("Video chưa có kịch bản đủ để tạo ảnh")
    for index, scene in enumerate([title, *scenes]):
        if scene.image_key or scene.video_key:
            continue
        label = _scene_label(scene, index)
        prompt = scene.image_prompt.strip() or (scene.text.strip().splitlines() or [""])[0].strip()
        if not prompt:
            scene.image_error = "Cảnh chưa có prompt ảnh, cũng chưa có chữ để tạo ảnh"
            db.commit()
            continue
        # Counted before the call, like the script job counts Claude: a killed job keeps the count.
        db.execute(update(Job).where(Job.id == job.id).values(image_calls=Job.image_calls + 1))
        db.commit()
        try:
            provider = config.image_gen_provider()
            data = generate_image(prompt, source_keys.get(db, provider), provider)
        except ImageGenError as err:
            if err.fatal:
                raise JobFailure(err.message, err.detail) from None
            scene.image_error = err.message
            db.commit()
            log.warning("Image job %s: %s failed: %s", job.id, label, err.message)
            continue
        if len(data) > MAX_IMAGE_BYTES:
            scene.image_error = "Ảnh Gemini trả về quá 15 MB, hãy bấm tạo lại"
            db.commit()
            continue
        try:
            extension = image_extension(data)
        except UploadRejected as err:
            scene.image_error = str(err)
            db.commit()
            continue
        key = new_key(video.id, f"scene-{scene.id}", extension)
        storage.save_bytes(key, data)
        scene.image_key, scene.image_source, scene.image_error = key, f"ai:{_image_model(provider)}", None
        if scene.is_title:
            refresh_thumbnail(db, storage, video, scene)
        db.commit()
        log.info("Image job %s: %s stored", job.id, label)
