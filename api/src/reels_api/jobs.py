"""What one job does. Runs inside the per-job child process started by the worker loop (worker.py)."""

import logging
import shutil
import tempfile
import time
import traceback
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import update
from sqlalchemy.orm import Session as DbSession, sessionmaker

from reels_render import RenderError, render_video
from reels_render.errors import FFmpegError
from reels_render.ffmpeg import find_tools, probe
from reels_render.script import parse_script

from . import knowledge
from .claude import (
    ClaudeError,
    GeneratedScript,
    build_clone_prompt,
    build_script_prompt,
    call_claude,
    generate_script,
)
from .models import Job, Scene, Video
from .pixabay import Pixabay, PixabayError
from .sessions import now
from .storage import DirectoryStorage
from .videos import new_key, refresh_thumbnail, render_signature, split_scenes

log = logging.getLogger(__name__)

TITLE_SECONDS = 3
# Auto-assign runs in the worker, not in a request, so each scene's search may take longer.
ASSIGN_SECONDS_PER_SCENE = 30


class JobFailure(Exception):
    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.message = message
        self.detail = detail


def work_dir(job_id: int) -> Path:
    """Fixed per job, so the worker loop can remove it even after killing the child."""
    return Path(tempfile.gettempdir()) / f"reels-job-{job_id}"


def run_job(job_id: int, factory: sessionmaker, storage: DirectoryStorage, pixabay: Pixabay | None = None,
            call: Callable[[str, str], str] = call_claude) -> None:
    with factory() as db:
        job = db.get(Job, job_id)
        if job is None or job.status != "running":
            log.warning("Job %s is not running (%s), skipped", job_id, job.status if job else "deleted")
            return
        log.info("Job %s (%s) for video %s started", job.id, job.kind, job.video_id)
        try:
            if job.kind in ("script", "clone"):
                run_script_job(db, job, storage, pixabay or Pixabay(), call)
            elif job.kind == "render":
                run_render_job(db, job, storage)
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
    db.execute(update(Job).where(Job.id == job_id).values(
        status=status, finished_at=now(), error=error, error_detail=detail or None))
    db.commit()


# --- Script ---

def run_script_job(db: DbSession, job: Job, storage: DirectoryStorage, pixabay: Pixabay,
                   call: Callable[[str, str], str]) -> None:
    video = db.get(Video, job.video_id)
    # A retried job whose script was already saved only fills the missing photos: no new Claude call,
    # and nothing the members edited meanwhile is overwritten.
    if not video.has_script:
        banned = knowledge.banned_words(db)
        if job.kind == "clone":
            # The snapshot from the moment "Nhân bản" was pressed: later edits of the source do not count.
            prompt = build_clone_prompt(knowledge.clone_prompt(db), video.clone_source, banned)
        else:
            prompt = build_script_prompt(knowledge.script_prompt(db), video.topic, banned)

        def count_call() -> None:
            db.execute(update(Job).where(Job.id == job.id).values(claude_calls=Job.claude_calls + 1))
            db.commit()

        try:
            script = generate_script(prompt, f"job {job.id}", count_call, call)
        except ClaudeError as err:
            raise JobFailure(err.message, err.detail) from None
        save_script(db, video, script)
        db.commit()
    assign_images(db, video, storage, pixabay)


def save_script(db: DbSession, video: Video, script: GeneratedScript) -> None:
    video.has_script = True
    video.title_options = script.titles
    video.caption = script.caption
    video.hashtags = script.hashtags
    video.affiliates = script.affiliates
    video.pinned_comment = script.pinned_comment
    video.self_review = script.self_review
    video.music_suggestions = script.music_suggestions
    db.add(Scene(video_id=video.id, is_title=True, position=0, text=script.titles[0], seconds=TITLE_SECONDS,
                 keywords=script.title_keywords, image_prompt=""))
    for position, scene in enumerate(script.scenes, start=1):
        db.add(Scene(video_id=video.id, is_title=False, position=position, text=scene.text, seconds=scene.seconds,
                     keywords=scene.keywords, image_prompt=scene.image_prompt))


def _search_terms(scene: Scene) -> list[str]:
    if scene.keywords:
        return list(scene.keywords)
    # Same rule as the renderer: a content scene without keywords is searched by its first text line.
    first_line = scene.text.split("\n")[0].replace("*", "").strip()
    return [first_line[:100]] if first_line and not scene.is_title else []


def assign_images(db: DbSession, video: Video, storage: DirectoryStorage, pixabay: Pixabay) -> None:
    """Pixabay photo for every scene without one, stored for good so the render uses what was shown."""
    title, scenes = split_scenes(db, video)
    pending = [scene for scene in ([title] if title else []) + scenes if not scene.image_key]
    used = {scene.image_source for scene in ([title] if title else []) + scenes if scene.image_source}
    for index, scene in enumerate(pending):
        terms = _search_terms(scene)
        if not terms:
            scene.image_error = "Chưa có từ khóa tìm ảnh: hãy nhập từ khóa hoặc tải ảnh lên"
            db.commit()
            continue
        try:
            photo = pixabay.find_photo(terms, time.monotonic() + ASSIGN_SECONDS_PER_SCENE, avoid=used)
        except PixabayError as err:
            for rest in pending[index:]:
                rest.image_error = f"Chưa gán được ảnh: {err.message}"
            db.commit()
            raise JobFailure(f"Đã lưu kịch bản nhưng chưa gán được ảnh Pixabay: {err.message}",
                             f"Lỗi Pixabay loại: {err.kind}\n{err.message}") from None
        if photo is None:
            scene.image_error = f"Không tìm thấy ảnh Pixabay cho từ khóa: {', '.join(terms)}"
            db.commit()
            continue
        key = new_key(video.id, f"scene-{scene.id}", photo.extension)
        storage.save_bytes(key, photo.data)
        scene.image_key, scene.image_source, scene.image_error = key, photo.url, None
        used.add(photo.url)
        if scene.is_title:
            refresh_thumbnail(db, storage, video, scene)
        db.commit()


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

def run_render_job(db: DbSession, job: Job, storage: DirectoryStorage) -> None:
    video = db.get(Video, job.video_id)
    title, scenes = split_scenes(db, video)
    if title is None or not scenes:
        raise JobFailure("Video chưa có kịch bản đủ để render")
    folder = work_dir(job.id)
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    try:
        def entry(scene: Scene, index: int) -> dict:
            label = "Cảnh tiêu đề" if scene.is_title else f"Cảnh {index}"
            if not scene.image_key or not storage.exists(scene.image_key):
                raise JobFailure(f"{label} chưa có ảnh trong storage, hãy gán lại ảnh rồi render")
            image = storage.copy_to(scene.image_key, folder / f"image-{index:02d}.{scene.image_key.rsplit('.', 1)[-1]}")
            # No "keywords": every photo is already chosen, the renderer must never search stock itself.
            return {"text": scene.text, "seconds": scene.seconds, "image": image.name}

        data = {"title": entry(title, 0), "scenes": [entry(scene, index) for index, scene in enumerate(scenes, 1)]}
        signature = render_signature(video, title, scenes)
        music = _checked_music(video, storage, folder)
        output = folder / "video.mp4"
        started = time.monotonic()
        try:
            render_video(parse_script(data, base_dir=folder), output, music=music,
                         music_volume=video.music_volume / 100)
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
