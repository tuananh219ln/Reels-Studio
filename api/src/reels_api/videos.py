"""Video state shared by the api routes and the worker: locking, status, payloads, thumbnail."""

import hashlib
import json
import secrets

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from . import knowledge
from .errors import ApiError
from .frames import thumbnail_bytes
from .models import ACTIVE_JOB_STATUSES, Job, Scene, Video
from .script_rules import Checks, SceneInput, check_script, plain_title, text_problem
from .storage import DirectoryStorage

STATUS_LABELS = {
    "draft": "Nháp",
    "queued": "Chờ",
    "writing": "Đang viết",
    "rendering": "Đang render",
    "done": "Xong",
    "failed": "Lỗi",
}
POST_FIELDS = {"caption": "Caption", "pinned_comment": "Bình luận ghim"}


def new_key(video_id: int, name: str, extension: str) -> str:
    """Server-generated, unique per version, so browsers never show a cached old file."""
    return f"videos/{video_id}/{name}-{secrets.token_hex(6)}.{extension}"


def video_not_found() -> ApiError:
    return ApiError(404, "video_not_found", "Không tìm thấy video (có thể đã bị xóa)")


def scene_deleted() -> ApiError:
    return ApiError(404, "scene_deleted", "Cảnh này đã bị xóa")


def active_job(db: DbSession, video_id: int) -> Job | None:
    return db.scalar(select(Job).where(Job.video_id == video_id, Job.status.in_(ACTIVE_JOB_STATUSES)))


def lock_video(db: DbSession, video_id: int) -> Video:
    """Row-lock the video: every change and every new job for one video happens one after another."""
    video = db.scalar(
        select(Video).where(Video.id == video_id).with_for_update().execution_options(populate_existing=True)
    )
    if video is None:
        raise video_not_found()
    return video


def ensure_unlocked(db: DbSession, video: Video) -> None:
    job = active_job(db, video.id)
    if job is None:
        return
    if job.kind == "render":
        raise ApiError(409, "video_locked", "Video đang render, chưa lưu")
    raise ApiError(409, "video_locked", "Video đang viết kịch bản, chưa lưu")


def lock_scene(db: DbSession, scene_id: int) -> tuple[Video, Scene]:
    """Lock the scene's video, then re-read the scene: a teammate may have deleted it meanwhile."""
    video_id = db.scalar(select(Scene.video_id).where(Scene.id == scene_id))
    if video_id is None:
        raise scene_deleted()
    video = lock_video(db, video_id)
    scene = db.scalar(select(Scene).where(Scene.id == scene_id).execution_options(populate_existing=True))
    if scene is None:
        raise scene_deleted()
    return video, scene


def split_scenes(db: DbSession, video: Video) -> tuple[Scene | None, list[Scene]]:
    rows = db.scalars(
        select(Scene).where(Scene.video_id == video.id).order_by(Scene.position, Scene.id)
        .execution_options(populate_existing=True)
    ).all()
    title = next((scene for scene in rows if scene.is_title), None)
    return title, [scene for scene in rows if not scene.is_title]


def render_signature(title: Scene | None, scenes: list[Scene]) -> str:
    """Fingerprint of what changes the MP4 (text, seconds, photo, order); captions and keywords are left out."""
    parts = [[scene.text, scene.seconds, scene.image_key] for scene in ([title] if title else []) + scenes]
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()


def refresh_thumbnail(db: DbSession, storage: DirectoryStorage, video: Video, title: Scene | None) -> None:
    """The thumbnail is the title scene's preview; it follows every change of that photo or text."""
    old = video.thumbnail_key
    if title is None or not title.image_key or not storage.exists(title.image_key):
        video.thumbnail_key = None
    else:
        key = new_key(video.id, "thumb", "jpg")
        storage.save_bytes(key, thumbnail_bytes(storage.path(title.image_key), title.text))
        video.thumbnail_key = key
    if old and old != video.thumbnail_key:
        storage.delete(old)


def scene_inputs(title: Scene | None, scenes: list[Scene]) -> tuple[SceneInput | None, list[SceneInput]]:
    def to_input(scene: Scene) -> SceneInput:
        return SceneInput(scene.id, scene.is_title, scene.text, scene.seconds, bool(scene.image_key))
    return (to_input(title) if title else None), [to_input(scene) for scene in scenes]


def run_checks(db: DbSession, video: Video, title: Scene | None, scenes: list[Scene]) -> Checks:
    title_input, scene_input = scene_inputs(title, scenes)
    posts = {name: getattr(video, name) for name in POST_FIELDS}
    return check_script(title_input, scene_input, posts, knowledge.banned_words(db))


def _last_failed(db: DbSession, video_id: int) -> Job | None:
    """The latest finished job when it failed; cancelled jobs leave the video as it was before them."""
    job = db.scalar(
        select(Job).where(Job.video_id == video_id, Job.status.in_(("done", "failed")))
        .order_by(Job.id.desc()).limit(1)
    )
    return job if job is not None and job.status == "failed" else None


def queue_position(db: DbSession, job: Job) -> int:
    return db.scalar(select(func.count()).select_from(Job).where(Job.status == "queued", Job.id <= job.id))


def _status(db: DbSession, video: Video, job: Job | None, failed: Job | None) -> dict:
    if job is not None and job.status == "queued":
        code, label = "queued", f"Chờ thứ {queue_position(db, job)}"
    elif job is not None:
        code = "rendering" if job.kind == "render" else "writing"
        label = STATUS_LABELS[code]
    elif video.mp4_key:
        code, label = "done", STATUS_LABELS["done"]
    elif failed is not None:
        code, label = "failed", STATUS_LABELS["failed"]
    else:
        code, label = "draft", STATUS_LABELS["draft"]
    return {"status": code, "status_label": label}


def _job_payload(job: Job | None) -> dict | None:
    if job is None:
        return None
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "error": job.error,
        "error_detail": job.error_detail,
        "created_by": job.created_by.name if job.created_by else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


def _version(*parts: object) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()[:12]


def scene_payload(scene: Scene, checks: Checks) -> dict:
    image = f"/api/scenes/{scene.id}"
    return {
        "id": scene.id,
        "is_title": scene.is_title,
        "text": scene.text,
        "seconds": scene.seconds,
        "keywords": scene.keywords,
        "image_prompt": scene.image_prompt,
        "has_image": bool(scene.image_key),
        "image_error": scene.image_error,
        "image_url": f"{image}/image?v={_version(scene.image_key)}" if scene.image_key else None,
        "preview_url": f"{image}/preview.jpg?v={_version(scene.image_key, scene.text)}" if scene.image_key else None,
        "text_problem": text_problem(scene.text, scene.is_title),
        "blocking": [issue.message for issue in checks.blocking if issue.scene_id == scene.id],
        "warnings": [issue.message for issue in checks.warnings if issue.scene_id == scene.id],
    }


def _labels(video: Video, title: Scene | None, scenes: list[Scene], job: Job | None, failed: Job | None) -> dict:
    return {
        "mp4_outdated": bool(video.mp4_key) and video.rendered_signature != render_signature(title, scenes),
        # A failed re-render keeps the old MP4 and the "Xong" status, with this extra label.
        "rerender_failed": job is None and bool(video.mp4_key) and failed is not None,
    }


def title_of(video: Video, title: Scene | None) -> str:
    return plain_title(title.text) if title is not None and title.text.strip() else ""


def video_payload(db: DbSession, video: Video) -> dict:
    title, scenes = split_scenes(db, video)
    job = active_job(db, video.id)
    failed = _last_failed(db, video.id)
    checks = run_checks(db, video, title, scenes) if video.has_script else Checks()
    payload = {
        "id": video.id,
        "topic": video.topic,
        "title": title_of(video, title),
        "has_script": video.has_script,
        "title_options": video.title_options,
        "caption": video.caption,
        "hashtags": video.hashtags,
        "affiliates": video.affiliates,
        "pinned_comment": video.pinned_comment,
        "self_review": video.self_review,
        "music_suggestions": video.music_suggestions,
        "created_by": video.created_by.name,
        "created_at": video.created_at.isoformat(),
        **_status(db, video, job, failed),
        **_labels(video, title, scenes, job, failed),
        "locked": job is not None,
        "active_job": _job_payload(job),
        "failed_job": _job_payload(failed) if job is None else None,
        "mp4": {
            "url": f"/api/videos/{video.id}/video.mp4?v={_version(video.mp4_key)}",
            "download_url": f"/api/videos/{video.id}/video.mp4?download=1&v={_version(video.mp4_key)}",
            "seconds": video.mp4_seconds,
            "render_seconds": video.render_seconds,
            "rendered_at": video.rendered_at.isoformat() if video.rendered_at else None,
        } if video.mp4_key else None,
        "thumbnail_url": (
            f"/api/videos/{video.id}/thumbnail.jpg?v={_version(video.thumbnail_key)}" if video.thumbnail_key else None
        ),
        "title_scene": scene_payload(title, checks) if title else None,
        "scenes": [scene_payload(scene, checks) for scene in scenes],
        "video_blocking": [issue.message for issue in checks.blocking if issue.scene_id is None],
        "video_warnings": [
            {"field": issue.field, "message": issue.message} for issue in checks.warnings if issue.scene_id is None
        ],
        "can_render": video.has_script and not checks.blocking and job is None,
    }
    return payload


def list_payload(db: DbSession, video: Video) -> dict:
    title, scenes = split_scenes(db, video)
    job = active_job(db, video.id)
    failed = _last_failed(db, video.id)
    return {
        "id": video.id,
        "topic": video.topic,
        "title": title_of(video, title),
        "created_by": video.created_by.name,
        "created_at": video.created_at.isoformat(),
        **_status(db, video, job, failed),
        **_labels(video, title, scenes, job, failed),
        "thumbnail_url": (
            f"/api/videos/{video.id}/thumbnail.jpg?v={_version(video.thumbnail_key)}" if video.thumbnail_key else None
        ),
    }
