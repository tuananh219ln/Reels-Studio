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

from . import affiliate, analytics, facebook, fanpages, hashtags, knowledge, llm, metrics, plans, post_comments
from .clips import ClipError, frame_at
from .errors import ApiError
from .frames import thumbnail_bytes
from .models import (
    ACTIVE_JOB_STATUSES,
    Fanpage,
    Job,
    KnowledgeTopic,
    PostMetrics,
    Publication,
    Scene,
    SceneLayer,
    SceneSound,
    TopicPlanItem,
    User,
    Video,
    VideoNote,
    VideoReference,
)
from .script_rules import MAX_SECONDS as MAX_SCENE_SECONDS
from .script_rules import MIN_SECONDS as MIN_SCENE_SECONDS
from .script_rules import Checks, SceneInput, check_script, plain_title, text_problem
from .sessions import now
from .storage import DirectoryStorage
from .tts import voice_signature
from .video_options import effective, look_signature, preview_look, render_options, text_size, voice_id, voice_speed

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
    "plan": "Tạo kế hoạch 30 ngày",
    "learn": "Học từ video mẫu",
    "revise": "AI sửa theo góp ý",
    "article_caption": "Viết bài viết",
    "motion": "Cảnh động",
    "tiktok_publish": "Đăng TikTok",
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
    if job.kind == "tiktok_publish":
        raise ApiError(409, "video_locked", "Video đang đăng lên TikTok, chưa lưu")
    if job.kind == "voice":
        raise ApiError(409, "video_locked", "Video đang tạo giọng đọc, chưa lưu")
    if job.kind == "revise":
        raise ApiError(409, "video_locked", "AI đang sửa video theo góp ý, chưa lưu")
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


def scene_name(scene: Scene) -> str:
    """What a content scene is about: the first line of its on-screen text, without its list number or marks
    ("Rau muống" of "Rau muống / Khoảng 3 tuần cắt ngọn")."""
    if scene.is_title:
        return ""
    lines = LIST_NUMBER.sub("", scene.text.replace("*", "")).strip().splitlines()
    return plain_title(lines[0]).rstrip(".,:;!?…").strip() if lines else ""


def pause_after_name(voice: str, name: str) -> str:
    """A voice text that opens with the scene's name gets a comma after it when nothing marks the pause, so the
    narration says "Rau muống, ngâm hạt…" instead of running the name into the sentence."""
    if not name or not voice.casefold().startswith(name.casefold()):
        return voice
    rest = voice[len(name) :]
    if not rest or not rest[0].isspace() or rest.lstrip()[:1] in (*PAUSE_ENDS, "-", "–", "—"):
        return voice
    # The case is kept: the voice reads "Ngâm" and "ngâm" alike, and a name such as "Phú Quốc" must stay as written.
    return f"{voice[: len(name)]}, {rest.lstrip()}"


def spoken(video: Video, scene: Scene) -> str:
    """The narration this scene gets in the next render: its voice text (with a pause after the scene's name), else
    its on-screen text; empty when it has neither or the video's narration is off."""
    if not video.voice_enabled:
        return ""
    if scene.voice_text.strip():
        return pause_after_name(scene.voice_text, scene_name(scene))
    return screen_speech(scene)


def auto_seconds(voice_seconds: float) -> float:
    """A scene's seconds when they follow its narration: the narration and the pauses around it, in tenths, within
    the 1–10 seconds a scene may be set to. A longer narration still lengthens the scene at render (fit_seconds)."""
    return min(MAX_SCENE_SECONDS, max(MIN_SCENE_SECONDS, fit_seconds(0, voice_seconds)))


def made_voice_seconds(video: Video, scene: Scene) -> float | None:
    """Length of the stored narration when it was made from the current voice text, voice and model."""
    text = spoken(video, scene)
    if not text or not scene.voice_key or scene.voice_signature != voice_signature(text, *_voice(video)):
        return None
    return scene.voice_seconds


def scene_marks(video: Video, title: Scene | None, scenes: list[Scene]) -> list[dict]:
    """Where each scene starts and ends in a render of the current scenes, in seconds: each lasts its fitted seconds,
    as in the render's timeline, whose crossfades straddle the boundaries without changing them."""
    marks, start = [], 0.0
    for index, scene in enumerate([title, *scenes] if title else scenes):
        end = start + fit_seconds(scene.seconds, made_voice_seconds(video, scene))
        label = "Tiêu đề" if scene.is_title else f"Cảnh {index if title else index + 1}"
        marks.append({"label": label, "start": round(start, 2), "end": round(end, 2)})
        start = end
    return marks


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


LAYER_FIELDS = ("kind", "text", "sticker", "start", "seconds", "x", "y", "size", "style", "animation")


def layer_fields(layer: SceneLayer) -> dict:
    """A layer as the render script and the studio read it (reels_render.layers.Layer)."""
    return {field: getattr(layer, field) for field in LAYER_FIELDS}


def layer_payload(layer: SceneLayer) -> dict:
    # Its picture changes only with what is drawn, not with where or when it shows.
    look = _version(layer.kind, layer.text, layer.sticker, layer.size, layer.style)
    return {"id": layer.id, **layer_fields(layer), "image_url": f"/api/layers/{layer.id}/image.png?v={look}"}


def sound_fields(sound: SceneSound) -> dict:
    """A sound effect as the render script reads it (reels_render.sounds.SceneSound)."""
    return {"sound": sound.sound, "start": sound.start, "volume": sound.volume}


def sound_payload(sound: SceneSound) -> dict:
    return {"id": sound.id, **sound_fields(sound), "url": f"/api/sounds/library/{sound.sound}.mp3"}


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
            # The studio's effects join only when set, so MP4s rendered before they existed stay current.
            *([["transition", scene.transition]] if scene.transition else []),
            *([["color", scene.color]] if scene.color else []),
            *([["layers", [layer_fields(layer) for layer in scene.layers]]] if scene.layers else []),
            *([["sounds", [sound_fields(sound) for sound in scene.sounds]]] if scene.sounds else []),
            *([["music_level", scene.music_level]] if scene.music_level else []),
        ]
        for scene in every
    ]
    # Without music or narration the fingerprint keeps the format MP4s rendered before those existed were
    # stored with, so they are not flagged as outdated.
    # The song's start joins only when moved, so MP4s rendered before it existed stay current.
    music = [video.music_key, video.music_volume, *([["music_start", video.music_start]] if video.music_start else [])]
    data = [parts, music] if video.music_key else parts
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
            text_size(video, scene.is_title),
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
            "tiktok_publish": "publishing",
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
        # A render or motion job waiting for a render machine ("ready") or being rendered on one ("taken").
        "node_stage": job.node_stage,
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


def tiktok_posts_of(db: DbSession, video_id: int) -> list[Publication]:
    """The video's TikTok posts, made by hand in TikTok's app or sent through TikTok's API, newest first."""
    return list(
        db.scalars(
            select(Publication)
            .where(Publication.video_id == video_id, Publication.platform == "tiktok")
            .order_by(Publication.id.desc())
        )
    )


def tiktok_post_payload(post: Publication) -> dict:
    return {
        "id": post.id,
        "url": post.post_url,
        "account": post.affiliate_account.name if post.affiliate_account else None,
        "at": live_at(post).isoformat(),
        "created_by": post.created_by.name,
        "created_by_id": post.created_by_id,
        # pending | published | cancelled; one recorded by hand is published.
        "status": post.status,
        # "draft" | "direct" for a post sent through TikTok's API, None for one posted by hand.
        "mode": post.publish_mode,
        "privacy_level": post.privacy_level,
    }


def _video_link(db: DbSession, video: Video | None) -> dict | None:
    if video is None:
        return None
    title, _ = split_scenes(db, video)
    return {"id": video.id, "title": title_of(video, title) or video.topic, "platform": video.platform}


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


REFERENCE_MODE_LABELS = {
    "quick": "Nhanh",
    "twostep": "Hai bước tự động",
    "review": "Duyệt phân tích trước",
    "reuse": "Dùng mẫu đã học",
}


def reference_frames(sample: VideoReference) -> list[dict]:
    return [
        {"second": frame["second"], "note": frame.get("note", ""), "url": f"/api/references/{sample.id}/frames/{n}.jpg"}
        for n, frame in enumerate(sample.frames, start=1)
    ]


def reference_payload(db: DbSession, video: Video) -> dict | None:
    """The sample video a video is learned from ("Từ video mẫu"), for its card on the video page."""
    if not video.reference_mode:
        return None
    sample = db.get(VideoReference, video.reference_id) if video.reference_id else None
    analyzed = bool(sample and sample.analysis.strip())
    return {
        "id": sample.id if sample else None,
        "mode": video.reference_mode,
        "mode_label": REFERENCE_MODE_LABELS.get(video.reference_mode, video.reference_mode),
        "source_name": sample.source_name if sample else None,
        "source_url": sample.source_url if sample else None,
        "seconds": sample.seconds if sample else None,
        "transcript": sample.transcript if sample else "",
        "analysis": sample.analysis if sample else "",
        "frames": reference_frames(sample) if sample else [],
        # The way "review": the analysis is written and waits for a member before the script.
        "awaiting_review": video.reference_mode == "review" and analyzed and not video.has_script,
    }


def thumbnail_url(video: Video) -> str | None:
    """The title-scene frame of the last render, versioned so a new render is not served from the cache."""
    return f"/api/videos/{video.id}/thumbnail.jpg?v={_version(video.thumbnail_key)}" if video.thumbnail_key else None


def publication_payload(post: Publication | None, by_page: dict[int | None, analytics.Median]) -> dict | None:
    """`by_page`: analytics.medians, read once per request."""
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
        "metrics": metrics.payload(post, by_page),
        "comment": post_comments.payload(post),
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


def motion_payload(scene: Scene) -> dict | None:
    """A scene's motion while its clip is the one the motion made, or while that clip is being made; else None
    (another photo or clip took its place, or its job failed)."""
    motion = scene.motion
    if not motion or not (motion.get("pending") or (motion.get("clip_key") and motion["clip_key"] == scene.video_key)):
        return None
    return {"html": motion["html"], "seconds": motion["seconds"], "pending": bool(motion.get("pending"))}


def scene_payload(video: Video, scene: Scene, checks: Checks) -> dict:
    image = f"/api/scenes/{scene.id}"
    size = text_size(video, scene.is_title)
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
        "seconds_auto": scene.seconds_auto,
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
            if scene.text.strip() and text_problem(scene.text, scene.is_title, size) is None
            else None
        ),
        "text_problem": text_problem(scene.text, scene.is_title, size),
        "transition": scene.transition,
        "color": scene.color,
        "layers": [layer_payload(layer) for layer in scene.layers],
        "sounds": [sound_payload(sound) for sound in scene.sounds],
        "music_level": scene.music_level,
        # A "Cảnh động" (motion.py): its markup and seconds while the scene shows its clip or it is being made.
        "motion": motion_payload(scene),
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
        .where(Job.video_id == video_id, Job.kind.in_(("script", "clone", "learn")), Job.status == "done")
        .order_by(Job.id.desc())
        .limit(1)
    )
    return llm.label(job.llm_provider, job.llm_model) if job else None


def title_of(video: Video, title: Scene | None) -> str:
    return plain_title(title.text) if title is not None and title.text.strip() else ""


def notes_payload(db: DbSession, video: Video, title: Scene | None, scenes: list[Scene]) -> list[dict]:
    """The studio's notes in the order of the video, each with the scene playing at its second now."""
    every = ([title] if title else []) + scenes
    ends, end = [], 0.0
    for scene in every:
        end += fit_seconds(scene.seconds, made_voice_seconds(video, scene))
        ends.append(end)
    rows = db.execute(
        select(VideoNote, User.name)
        .join(User, User.id == VideoNote.created_by_id)
        .where(VideoNote.video_id == video.id)
        .order_by(VideoNote.at, VideoNote.id)
    ).all()
    payload = []
    for note, author in rows:
        index = next((number for number, value in enumerate(ends) if note.at < value), len(every) - 1)
        payload.append(
            {
                "id": note.id,
                "at": note.at,
                "scene_id": every[index].id if every else None,
                "text": note.text,
                "status": note.status,
                "reply": note.reply,
                "created_by": author,
                "created_at": note.created_at.isoformat(),
            }
        )
    return payload


def video_payload(db: DbSession, video: Video) -> dict:
    title, scenes = split_scenes(db, video)
    job = active_job(db, video.id)
    failed = _last_failed(db, video.id)
    checks = run_checks(db, video, title, scenes) if video.has_script else Checks()
    topic = knowledge.topic_of(db, video)
    posts = publications_of(db, video.id)
    # One small query, and only for a video that has posts: this payload answers every save and poll of the editor.
    by_page = analytics.medians(db) if posts else {}
    payload = {
        "id": video.id,
        "topic": video.topic,
        "title": title_of(video, title),
        "has_script": video.has_script,
        "hand_written": video.hand_written,
        "title_options": video.title_options,
        "caption": video.caption,
        "hashtags": video.hashtags,
        # What a post sends: the caption, then the hashtags it does not already hold.
        "post_text": hashtags.post_text(video.caption, video.hashtags),
        "affiliates": video.affiliates,
        "platform": video.platform,
        "variant_of": _video_link(db, db.get(Video, video.variant_of_id)) if video.variant_of_id else None,
        "variants": [
            _video_link(db, variant)
            for variant in db.scalars(select(Video).where(Video.variant_of_id == video.id).order_by(Video.id))
        ],
        "tiktok_posts": [tiktok_post_payload(post) for post in tiktok_posts_of(db, video.id)],
        "suggest": {
            "state": "pending" if video.suggest_requested_at else ("failed" if video.suggest_error else "idle"),
            "error": video.suggest_error,
            "at": video.suggested_at.isoformat() if video.suggested_at else None,
        },
        # The products whose links go in the comment under the video's reels (post_comments.py).
        "affiliate_product_ids": [product.id for product in affiliate.products_of(db, video.id)],
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
            # Automatic QC of this MP4 (qc.py); None for an MP4 rendered before QC existed.
            "qc": video.qc,
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
        "music_start": video.music_start,
        "ai_effects": video.ai_effects,
        "notes": notes_payload(db, video, title, scenes),
        "voice_enabled": video.voice_enabled,
        "options": effective(video),
        "publication": publication_payload(publication_of(db, video.id), by_page),
        "publications": [publication_payload(post, by_page) for post in posts],
        "posted_fanpage_ids": posted_fanpage_ids(video, posts),
        "fanpages": [
            {
                "id": page.id,
                "name": page.name,
                "owner": page.owner.name if page.owner else None,
                "error": page.check_error,
            }
            for page in fanpages.in_use(db)
        ],
        "knowledge_topic": topic.name if topic else None,
        "plan_idea": _plan_idea(db, video),
        "script_by": script_writer(db, video.id) if video.has_script else None,
        "clone_of": {
            "title": video.clone_source["title"],
            "request": video.clone_source["request"],
        }
        if video.clone_source
        else None,
        "reference": reference_payload(db, video),
        "title_scene": scene_payload(video, title, checks) if title else None,
        "scenes": [scene_payload(video, scene, checks) for scene in scenes],
        "video_blocking": [issue.message for issue in checks.blocking if issue.scene_id is None],
        "video_warnings": [
            {"field": issue.field, "message": issue.message} for issue in checks.warnings if issue.scene_id is None
        ],
        "can_render": video.has_script and not checks.blocking and job is None,
    }
    return payload


def _plan_idea(db: DbSession, video: Video) -> dict | None:
    """The 30-day plan idea the video was made from, to compare against while editing, and when the plan means the
    video to go out ("Đăng" starts with that time)."""
    idea = db.scalar(select(TopicPlanItem).where(TopicPlanItem.video_id == video.id))
    if idea is None:
        return None
    post_at = plans.suggested_post_at(db.get(KnowledgeTopic, idea.knowledge_topic_id), idea)
    return {
        "id": idea.id,
        "knowledge_topic_id": idea.knowledge_topic_id,
        "day": idea.day,
        "topic": idea.topic,
        "pain_group": idea.pain_group,
        "pain": idea.pain,
        "hook": idea.hook,
        "suggested_post_at": post_at.isoformat() if post_at else None,
    }


def made_from(db: DbSession) -> tuple[set[int], set[int]]:
    """The videos that have a TikTok version, and those a Facebook clone was made from ("Nhân bản", a version for
    another Page), for the list's suggestions on "Bài đăng"; read once per list."""
    tiktok = set(db.scalars(select(Video.variant_of_id).where(Video.variant_of_id.is_not(None))))
    sources = db.scalars(
        select(Video.clone_source["video_id"].as_integer()).where(
            Video.clone_source.is_not(None), Video.platform == "facebook"
        )
    )
    return tiktok, {source for source in sources if source is not None}


def list_extras(db: DbSession, videos: list[Video]) -> dict[int, dict]:
    """What a video's card on /videos shows besides itself, by video id: its topic group, its 30-day plan day, and
    its Facebook posts: whether one is out or set for later, its views and how its best post did at 48 hours.
    Everything is read in a few queries for the whole list, and the Page medians once."""
    ids = [video.id for video in videos]
    if not ids:
        return {}
    groups = dict(db.execute(select(KnowledgeTopic.id, KnowledgeTopic.name)).all())
    days = dict(
        db.execute(select(TopicPlanItem.video_id, TopicPlanItem.day).where(TopicPlanItem.video_id.in_(ids))).all()
    )
    posts = db.execute(
        select(Publication, Fanpage.name)
        .outerjoin(Fanpage, Fanpage.id == Publication.fanpage_id)
        .where(
            Publication.video_id.in_(ids),
            Publication.platform == "facebook",
            Publication.status.in_(LIVE_POST_STATUSES),
        )
    ).all()
    readings: dict[tuple[int, str], PostMetrics] = {}
    if posts:
        for row in db.scalars(select(PostMetrics).where(PostMetrics.publication_id.in_([p.id for p, _ in posts]))):
            readings[(row.publication_id, row.window)] = row
    by_page = analytics.medians(db) if posts else {}
    on_tiktok = set(
        db.scalars(select(Publication.video_id).where(Publication.video_id.in_(ids), Publication.platform == "tiktok"))
    )
    by_video: dict[int, list[tuple[Publication, str]]] = {}
    for post, page in posts:
        by_video.setdefault(post.video_id, []).append((post, page or ""))
    extras = {}
    for video in videos:
        live = [(post, page) for post, page in by_video.get(video.id, []) if is_published(post)]
        later = sorted(
            ((post, page) for post, page in by_video.get(video.id, []) if not is_published(post)),
            key=lambda item: item[0].scheduled_at or item[0].created_at,
        )
        extras[video.id] = {
            "knowledge_topic": groups.get(video.knowledge_topic_id),
            "plan_day": days.get(video.id),
            "post": _post_summary(live, later, readings, by_page),
            # A TikTok version posted by hand: the card it sits on says "Đã đăng" for it.
            "tiktok_posted": video.id in on_tiktok,
        }
    return extras


def _post_summary(
    live: list[tuple[Publication, str]],
    later: list[tuple[Publication, str]],
    readings: dict[tuple[int, str], PostMetrics],
    by_page: dict,
) -> dict | None:
    """The card's post line. Views are each live post's `latest` reading added up; the 48-hour line is of the post
    with the most views, and only its `48h` reading, so posts are compared at the same age."""
    if not live and not later:
        return None
    if not live:
        post, page = later[0]
        return {
            "state": "scheduled",
            "fanpage": page,
            "fanpages": sorted({name for _, name in later if name}),
            "pages": len(later),
            "at": live_at(post).isoformat(),
            "views": None,
            "shares": None,
            "share_rate": None,
            "share_met": None,
            "times_median": None,
        }

    def latest_views(item: tuple[Publication, str]) -> int:
        row = readings.get((item[0].id, "latest"))
        return row.views if row is not None and row.views is not None else -1

    counted = [latest_views(item) for item in live if latest_views(item) >= 0]
    post, page = max(live, key=latest_views)
    mark = readings.get((post.id, "48h"))
    views_48h, shares_48h = (mark.views, mark.shares) if mark is not None else (None, None)
    analysis = analytics.of_post(post, views_48h, shares_48h, by_page)
    return {
        "state": "posted",
        "fanpage": page,
        # Every Page it is out on or set for, for the list's Fanpage filter.
        "fanpages": sorted({name for _, name in [*live, *later] if name}),
        "pages": len(live),
        "at": live_at(post).isoformat(),
        "views": sum(counted) if counted else None,
        "shares": shares_48h,
        "share_rate": analysis["share_rate"],
        "share_met": analysis["share_rate"] >= analytics.SHARE_GOAL if analysis["share_rate"] is not None else None,
        "times_median": analysis["times_median"],
    }


def list_payload(
    db: DbSession, video: Video, family: tuple[set[int], set[int]] = (set(), set()), extras: dict | None = None
) -> dict:
    """`family`: made_from, and `extras`: this video's list_extras, both read once per list."""
    title, scenes = split_scenes(db, video)
    job = active_job(db, video.id)
    failed = _last_failed(db, video.id)
    return {
        "id": video.id,
        "topic": video.topic,
        "title": title_of(video, title),
        "platform": video.platform,
        # The video a TikTok version was made from: the list shows the version on its source's card.
        "variant_of_id": video.variant_of_id,
        "has_tiktok_version": video.id in family[0],
        "cloned": video.id in family[1],
        "created_by": video.created_by.name,
        "created_at": video.created_at.isoformat(),
        **_status(db, video, job, failed),
        **_labels(video, title, scenes, job, failed),
        "thumbnail_url": thumbnail_url(video),
        **(extras or {"knowledge_topic": None, "plan_day": None, "post": None, "tiktok_posted": False}),
    }
