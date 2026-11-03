"""Video state shared by the api routes and the worker: locking, status, payloads, thumbnail."""

import hashlib
import json
import re
import secrets
from datetime import datetime
from pathlib import Path

from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from reels_render.timeline import fit_seconds

from . import facebook, fanpages, knowledge, llm, metrics
from .clips import ClipError, frame_at
from .errors import ApiError
from .frames import thumbnail_bytes
from .models import ACTIVE_JOB_STATUSES, Job, Publication, Scene, Video
from .script_rules import Checks, SceneInput, check_script, plain_title, text_problem
from .sessions import now
from .storage import DirectoryStorage
from .tts import voice_signature
from .video_options import effective, look_signature, preview_look, render_options, voice_id, voice_speed

STATUS_LABELS = {
    "draft": "Nháp",
    "queued": "Chờ",
    "writing": "Đang viết",
    "imaging": "Đang tạo ảnh",
    "finding": "Đang tìm ảnh",
    "voicing": "Đang tạo giọng",
    "rendering": "Đang render",
    "publishing": "Đang đăng",
    "unpublishing": "Đang gỡ bài",
    "checking": "Đang kiểm tra bài",
    "done": "Xong",
    "failed": "Lỗi",
}
POST_FIELDS = {"caption": "Caption", "pinned_comment": "Bình luận ghim"}
JOB_KINDS = {
    "script": "Viết kịch bản",
    "clone": "Nhân bản",
    "render": "Render",
    "publish": "Đăng Facebook",
    "unpublish": "Gỡ bài Facebook",
    "check": "Kiểm tra bài Facebook",
    "image": "Tạo ảnh AI",
    "photos": "Tự tìm ảnh",
    "voice": "Tạo giọng thật",
}
# What a post can still be cancelled or deleted from; `cancelled` and `deleted` are final.
LIVE_POST_STATUSES = ("scheduled", "published")
OPEN_POST_STATUSES = ("pending", *LIVE_POST_STATUSES)
# A line of on-screen text read aloud already pauses after one of these.
PAUSE_ENDS = (".", "!", "?", "…", ":", ",", ";")
# "2." or "2)" before a scene's text: read as "hai chấm". "2.5 lít" is a quantity, not a number in a list.
LIST_NUMBER = re.compile(r"^\s*\d+[.)](?!\d)\s*")


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
    if job.kind == "publish":
        raise ApiError(409, "video_locked", "Video đang đăng lên Facebook, chưa lưu")
    if job.kind == "unpublish":
        raise ApiError(409, "video_locked", "Video đang gỡ bài trên Facebook, chưa lưu")
    if job.kind == "check":
        raise ApiError(409, "video_locked", "Video đang kiểm tra bài trên Facebook, chưa lưu")
    if job.kind == "voice":
        raise ApiError(409, "video_locked", "Video đang tạo giọng đọc, chưa lưu")
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
        select(Scene)
        .where(Scene.video_id == video.id)
        .order_by(Scene.position, Scene.id)
        .execution_options(populate_existing=True)
    ).all()
    title = next((scene for scene in rows if scene.is_title), None)
    return title, [scene for scene in rows if not scene.is_title]


def screen_speech(scene: Scene) -> str:
    """The on-screen text as it is read when a scene has no voice text: the title whole; a content scene without its
    list number, each line its own sentence, so the dish and its benefit do not run together."""
    if scene.is_title:
        return plain_title(scene.text)
    lines = [plain_title(line) for line in LIST_NUMBER.sub("", scene.text.replace("*", "")).splitlines()]
    return " ".join(line if line.endswith(PAUSE_ENDS) else f"{line}." for line in lines if line)


def spoken(video: Video, scene: Scene) -> str:
    """The narration this scene gets in the next render: its voice text, else its on-screen text; empty when it has
    neither or the video's narration is off."""
    if not video.voice_enabled:
        return ""
    return scene.voice_text if scene.voice_text.strip() else screen_speech(scene)


def made_voice_seconds(video: Video, scene: Scene) -> float | None:
    """Length of the stored narration when it was made from the current voice text, voice and model."""
    text = spoken(video, scene)
    if not text or not scene.voice_key or scene.voice_signature != voice_signature(text, *_voice(video)):
        return None
    return scene.voice_seconds


def _voice(video: Video) -> tuple[str, str]:
    return voice_id(video), voice_speed(video)


def text_position(video: Video, scene: Scene) -> list[int] | None:
    """Where the scene's text box goes (its centre): its own place, else for a content scene the video's place,
    else None (where the template puts it)."""
    if scene.text_x is not None and scene.text_y is not None:
        return [scene.text_x, scene.text_y]
    if scene.is_title:
        return None
    return effective(video)["text_position"]


def render_signature(video: Video, title: Scene | None, scenes: list[Scene]) -> str:
    """Fingerprint of what changes the MP4 (text, seconds, photo, order, music, volume, narration); captions and
    keywords are left out."""
    every = ([title] if title else []) + scenes
    # A clip joins its scene's part only when there is one, so MP4s rendered before clips existed stay current.
    # So does a clip speed other than 1×, and a moved text box, so a box in the template's place keeps the fingerprint from before.
    parts = [
        [
            scene.text,
            scene.seconds,
            scene.image_key,
            *([scene.video_key, scene.video_start] if scene.video_key else []),
            *([["video_speed", scene.video_speed]] if scene.video_speed not in (None, 1) else []),
            *([["text_position", *position]] if (position := text_position(video, scene)) else []),
        ]
        for scene in every
    ]
    # Without music or narration the fingerprint keeps the format MP4s rendered before those existed were
    # stored with, so they are not flagged as outdated.
    data = [parts, [video.music_key, video.music_volume]] if video.music_key else parts
    voices = [
        voice_signature(spoken(video, scene), *_voice(video)) if spoken(video, scene) else None for scene in every
    ]
    if any(voices):
        data = [data, voices]
    look = look_signature(video)
    if look is not None:
        data = [data, look]
    return hashlib.sha256(json.dumps(data, ensure_ascii=False).encode()).hexdigest()


def scene_still(storage: DirectoryStorage, scene: Scene) -> Path | Image.Image | None:
    """What the scene's first frame is drawn from: the clip's frame at its start time, or the photo."""
    if scene.video_key:
        if not storage.exists(scene.video_key):
            return None
        try:
            return frame_at(storage.path(scene.video_key), scene.video_start)
        except ClipError:
            return None
    if scene.image_key and storage.exists(scene.image_key):
        return storage.path(scene.image_key)
    return None


def refresh_thumbnail(db: DbSession, storage: DirectoryStorage, video: Video, title: Scene | None) -> None:
    """The thumbnail is the title scene's preview; it follows every change of that photo, clip or text."""
    old = video.thumbnail_key
    still = scene_still(storage, title) if title is not None else None
    if still is None:
        video.thumbnail_key = None
    else:
        key = new_key(video.id, "thumb", "jpg")
        storage.save_bytes(key, thumbnail_bytes(still, title.text, render_options(video), text_position(video, title)))
        video.thumbnail_key = key
    if old and old != video.thumbnail_key:
        storage.delete(old)


def scene_inputs(video: Video, title: Scene | None, scenes: list[Scene]) -> tuple[SceneInput | None, list[SceneInput]]:
    def to_input(scene: Scene) -> SceneInput:
        clip_seconds = scene.video_seconds - scene.video_start if scene.video_key and scene.video_seconds else None
        return SceneInput(
            scene.id,
            scene.is_title,
            scene.text,
            scene.seconds,
            bool(scene.image_key or scene.video_key),
            scene.voice_text if spoken(video, scene) else "",
            made_voice_seconds(video, scene),
            clip_seconds,
            bool(scene.keywords or scene.keywords_en),
            scene.video_speed,
        )

    return (to_input(title) if title else None), [to_input(scene) for scene in scenes]


def run_checks(db: DbSession, video: Video, title: Scene | None, scenes: list[Scene]) -> Checks:
    title_input, scene_input = scene_inputs(video, title, scenes)
    posts = {name: getattr(video, name) for name in POST_FIELDS}
    return check_script(title_input, scene_input, posts, knowledge.banned_words(db, video))


def _last_failed(db: DbSession, video_id: int) -> Job | None:
    """The latest finished job when it failed; cancelled jobs leave the video as it was before them."""
    job = db.scalar(
        select(Job).where(Job.video_id == video_id, Job.status.in_(("done", "failed"))).order_by(Job.id.desc()).limit(1)
    )
    return job if job is not None and job.status == "failed" else None


def queue_position(db: DbSession, job: Job) -> int:
    return db.scalar(select(func.count()).select_from(Job).where(Job.status == "queued", Job.id <= job.id))


def _status(db: DbSession, video: Video, job: Job | None, failed: Job | None) -> dict:
    if job is not None and job.status == "queued":
        code, label = "queued", f"Chờ thứ {queue_position(db, job)}"
    elif job is not None:
        code = {
            "render": "rendering",
            "publish": "publishing",
            "unpublish": "unpublishing",
            "check": "checking",
            "image": "imaging",
            "photos": "finding",
            "voice": "voicing",
        }.get(job.kind, "writing")
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
        # The one scene an image job makes a photo for; None for every other job.
        "scene_id": job.scene_id,
        "image_provider": job.image_provider,
        "status": job.status,
        "error": job.error,
        "error_detail": job.error_detail,
        "created_by": job.created_by.name if job.created_by else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


def publications_of(db: DbSession, video_id: int) -> list[Publication]:
    """Every post of the video, newest first, cancelled and deleted ones included."""
    return list(
        db.scalars(
            select(Publication)
            .where(Publication.video_id == video_id, Publication.platform == "facebook")
            .order_by(Publication.id.desc())
        )
    )


def publication_of(db: DbSession, video_id: int) -> Publication | None:
    """The newest post still on its way or on the platform."""
    return next((post for post in publications_of(db, video_id) if post.status in OPEN_POST_STATUSES), None)


def pending_publication(db: DbSession, video_id: int) -> Publication | None:
    """The post the publish job works on; at most one, by the partial unique index."""
    return next((post for post in publications_of(db, video_id) if post.status == "pending"), None)


def published_publication(db: DbSession, video_id: int) -> Publication | None:
    return next((post for post in publications_of(db, video_id) if is_published(post)), None)


def is_published(post: Publication) -> bool:
    # Facebook publishes a scheduled reel by itself, so nothing here changes when the time comes.
    return post.status == "published" or (
        post.status == "scheduled" and post.scheduled_at is not None and post.scheduled_at <= now()
    )


def live_at(post: Publication) -> datetime:
    # The publish job stamps published_at when the upload ends, which for a scheduled reel is before it goes live.
    # A post cancelled before its upload has neither.
    return post.scheduled_at or post.published_at or post.created_at


def thumbnail_url(video: Video) -> str | None:
    """The title-scene frame of the last render, versioned so a new render is not served from the cache."""
    return f"/api/videos/{video.id}/thumbnail.jpg?v={_version(video.thumbnail_key)}" if video.thumbnail_key else None


def publication_payload(post: Publication | None) -> dict | None:
    if post is None:
        return None
    published = is_published(post)
    return {
        "id": post.id,
        "status": "published" if published else post.status,
        "fanpage": post.fanpage.name if post.fanpage else None,
        "scheduled_at": post.scheduled_at.isoformat() if post.scheduled_at else None,
        "at": live_at(post).isoformat(),
        "url": facebook.reel_url(post.remote_id) if published and post.remote_id else None,
        "created_by": post.created_by.name,
        "closed_at": post.closed_at.isoformat() if post.closed_at else None,
        "closed_by": post.closed_by.name if post.closed_by else None,
        "metrics": metrics.payload(post),
    }


def posted_fanpage_ids(video: Video, posts: list[Publication]) -> list[int]:
    """The Pages that hold the current MP4, so the same file is not posted to them again."""
    return [
        post.fanpage_id
        for post in posts
        if post.status in LIVE_POST_STATUSES and post.remote_mp4_key == video.mp4_key and post.fanpage_id is not None
    ]


def _version(*parts: object) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()[:12]


def scene_payload(video: Video, scene: Scene, checks: Checks) -> dict:
    image = f"/api/scenes/{scene.id}"
    voice_seconds = made_voice_seconds(video, scene)
    style = preview_look(video, scene.is_title)
    position = text_position(video, scene)
    if position:
        style = [*style, "text_position", *position]
    still = scene.video_key or scene.image_key
    return {
        "id": scene.id,
        "video_id": scene.video_id,
        "is_title": scene.is_title,
        "text": scene.text,
        "seconds": scene.seconds,
        "keywords": scene.keywords,
        "keywords_en": scene.keywords_en,
        "image_prompt": scene.image_prompt,
        "voice_text": scene.voice_text,
        "spoken_text": spoken(video, scene),
        # Known once a render has made the narration for the current text; None until then.
        "voice_seconds": voice_seconds,
        "voice_url": f"{image}/voice.mp3?v={_version(scene.voice_key)}" if voice_seconds is not None else None,
        "fitted_seconds": fit_seconds(scene.seconds, voice_seconds),
        "has_image": bool(scene.image_key),
        # An AI photo: the card offers "Tạo lại ảnh AI" instead of "Tạo ảnh AI".
        "image_ai": bool(scene.image_key) and (scene.image_source or "").startswith("ai:"),
        # Picked by "Tự tìm ảnh" and not yet changed by a member: the card says "Tự chọn, kiểm tra lại".
        "image_auto": bool(scene.image_key) and scene.image_auto,
        "image_error": scene.image_error,
        "image_url": f"{image}/image?v={_version(scene.image_key)}" if scene.image_key else None,
        "video": {
            "url": f"{image}/video?v={_version(scene.video_key)}",
            "seconds": scene.video_seconds,
            "start": scene.video_start,
            "speed": scene.video_speed,
        }
        if scene.video_key
        else None,
        "preview_url": (
            f"{image}/preview.jpg?v={_version(scene.video_key, scene.video_start, scene.text, *style)}"
            if scene.video_key
            else f"{image}/preview.jpg?v={_version(scene.image_key, scene.text, *style)}"
            if scene.image_key
            else None
        ),
        # Where a member dragged this scene's box; None: the video's place (content scenes) or the template's.
        "text_position": [scene.text_x, scene.text_y] if scene.text_x is not None else None,
        "placed_at": position,  # where it goes after all: its own place, the video's, or None (the template's)
        # The drag is drawn from the frame without text and the exact box image the renderer overlays.
        "frame_url": f"{image}/frame.jpg?v={_version(still, scene.video_start)}" if still else None,
        "textbox_url": (
            f"{image}/textbox.png?v={_version(scene.text, *preview_look(video, scene.is_title))}"
            if scene.text.strip() and text_problem(scene.text, scene.is_title) is None
            else None
        ),
        "text_problem": text_problem(scene.text, scene.is_title),
        "blocking": [issue.message for issue in checks.blocking if issue.scene_id == scene.id],
        "warnings": [issue.message for issue in checks.warnings if issue.scene_id == scene.id],
    }


def _labels(video: Video, title: Scene | None, scenes: list[Scene], job: Job | None, failed: Job | None) -> dict:
    return {
        "mp4_outdated": bool(video.mp4_key) and video.rendered_signature != render_signature(video, title, scenes),
        # A failed re-render keeps the old MP4 and the "Xong" status, with this extra label.
        "rerender_failed": job is None and bool(video.mp4_key) and failed is not None and failed.kind == "render",
    }


def script_writer(db: DbSession, video_id: int) -> str | None:
    """The provider and model of the job that wrote the video's script, so reviewers know what they read."""
    job = db.scalar(
        select(Job)
        .where(Job.video_id == video_id, Job.kind.in_(("script", "clone")), Job.status == "done")
        .order_by(Job.id.desc())
        .limit(1)
    )
    return llm.label(job.llm_provider, job.llm_model) if job else None


def title_of(video: Video, title: Scene | None) -> str:
    return plain_title(title.text) if title is not None and title.text.strip() else ""


def video_payload(db: DbSession, video: Video) -> dict:
    title, scenes = split_scenes(db, video)
    job = active_job(db, video.id)
    failed = _last_failed(db, video.id)
    checks = run_checks(db, video, title, scenes) if video.has_script else Checks()
    topic = knowledge.topic_of(db, video)
    posts = publications_of(db, video.id)
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
        }
        if video.mp4_key
        else None,
        "thumbnail_url": thumbnail_url(video),
        "music": {
            "url": f"/api/videos/{video.id}/music.mp3?v={_version(video.music_key)}",
            "name": video.music_name,
        }
        if video.music_key
        else None,
        "music_volume": video.music_volume,
        "voice_enabled": video.voice_enabled,
        "options": effective(video),
        "publication": publication_payload(publication_of(db, video.id)),
        "publications": [publication_payload(post) for post in posts],
        "posted_fanpage_ids": posted_fanpage_ids(video, posts),
        "fanpages": [{"id": page.id, "name": page.name} for page in fanpages.in_use(db)],
        "knowledge_topic": topic.name if topic else None,
        "script_by": script_writer(db, video.id) if video.has_script else None,
        "clone_of": {
            "title": video.clone_source["title"],
            "request": video.clone_source["request"],
        }
        if video.clone_source
        else None,
        "title_scene": scene_payload(video, title, checks) if title else None,
        "scenes": [scene_payload(video, scene, checks) for scene in scenes],
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
        "thumbnail_url": thumbnail_url(video),
    }
