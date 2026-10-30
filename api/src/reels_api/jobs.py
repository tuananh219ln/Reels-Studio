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
from reels_render.ffmpeg import audio_seconds, find_tools, probe
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
from .sessions import now
from .storage import DirectoryStorage
from .tts import TtsError, synthesize, voice_signature
from .videos import made_voice_seconds, new_key, render_signature, run_checks, spoken, split_scenes

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


def run_job(job_id: int, factory: sessionmaker, storage: DirectoryStorage,
            call: Callable[[str, str], str] = call_claude) -> None:
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

def run_script_job(db: DbSession, job: Job, call: Callable[[str, str], str]) -> None:
    video = db.get(Video, job.video_id)
    # A retried job whose script was already saved has nothing to do: no new Claude call,
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
                 keywords=script.title_keywords, image_prompt="", voice_text=script.title_voice))
    for position, scene in enumerate(script.scenes, start=1):
        db.add(Scene(video_id=video.id, is_title=False, position=position, text=scene.text, seconds=scene.seconds,
                     keywords=scene.keywords, image_prompt=scene.image_prompt, voice_text=scene.voice))


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
            data = synthesize(text)
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
        scene.voice_key, scene.voice_signature, scene.voice_seconds = key, voice_signature(text), seconds
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
            raise JobFailure(f"Chưa render được: {blocking[0].message}",
                             "Lời đọc làm cảnh dài thêm: hãy rút gọn lời đọc hoặc bớt cảnh")

        def entry(scene: Scene, index: int) -> dict:
            label = _scene_label(scene, index)
            # No "keywords": every photo or clip is already chosen, the renderer must never search stock itself.
            if scene.video_key:
                if not storage.exists(scene.video_key):
                    raise JobFailure(f"{label} chưa có video trong storage, hãy tải video lên lại rồi render")
                extension = scene.video_key.rsplit(".", 1)[-1]
                clip = storage.copy_to(scene.video_key, folder / f"clip-{index:02d}.{extension}")
                data = {"text": scene.text, "seconds": scene.seconds, "video": clip.name,
                        "video_start": scene.video_start}
            else:
                if not scene.image_key or not storage.exists(scene.image_key):
                    raise JobFailure(f"{label} chưa có ảnh trong storage, hãy gán lại ảnh rồi render")
                image = storage.copy_to(scene.image_key,
                                        folder / f"image-{index:02d}.{scene.image_key.rsplit('.', 1)[-1]}")
                data = {"text": scene.text, "seconds": scene.seconds, "image": image.name}
            if spoken(video, scene):
                data["voice"] = storage.copy_to(scene.voice_key, folder / f"voice-{index:02d}.mp3").name
            return data

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
