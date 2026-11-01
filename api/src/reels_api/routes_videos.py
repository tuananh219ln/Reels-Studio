import io
import math
import tempfile
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from reels_render.textbox import FRAME_WIDTH

from . import clips, frames, knowledge, llm, source_keys, stock_clips, video_options
from .db import get_db
from .errors import ApiError
from .models import (
    AffiliateProduct,
    AppSetting,
    Fanpage,
    Job,
    KnowledgeTopic,
    MusicTrack,
    Publication,
    Scene,
    Session,
    Video,
)
from .openverse import Openverse, OpenverseError
from .pexels import Pexels, PexelsError
from .pixabay import Pixabay, PixabayError
from .script_rules import CROSSFADE_SIDE_SECONDS, MAX_SECONDS, MIN_SECONDS, text_problem
from .sessions import current_member, now
from .storage import DirectoryStorage, get_storage
from .uploads import (
    MAX_IMAGE_BYTES,
    MAX_MUSIC_BYTES,
    UploadRejected,
    check_mp3,
    file_label,
    image_extension,
    read_limited,
)
from .videos import (
    JOB_KINDS,
    ensure_unlocked,
    list_payload,
    lock_scene,
    lock_video,
    new_key,
    publication_of,
    refresh_thumbnail,
    render_signature,
    run_checks,
    scene_still,
    split_scenes,
    text_position,
    title_of,
    video_not_found,
    video_payload,
)

router = APIRouter(prefix="/api")

MAX_TOPIC_LENGTH = 300
MAX_TEXT_LENGTH = 500
MAX_VOICE_LENGTH = 1000
MAX_LONG_TEXT_LENGTH = 5000
MAX_KEYWORDS = 10
MAX_KEYWORD_LENGTH = 100
MAX_LIST_ITEMS = 20
NEW_SCENE_SECONDS = 4
# "Tìm lại ảnh" runs inside the request, so Pixabay gets about 10 seconds in total.
FIND_IMAGE_SECONDS = 10
IMAGE_TYPES = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
CLIP_TYPES = {"mp4": "video/mp4", "webm": "video/webm"}
# Scene length a new clip sets, so the whole clip plays without being longer than a scene may be.
MAX_CLIP_SCENE_SECONDS = 10
MAX_TOPIC_NAME_LENGTH = 100
# The upload takes a few minutes, and Facebook wants the time at least 10 minutes after it and within 29 days.
MIN_SCHEDULE_DELAY = timedelta(minutes=15)
MAX_SCHEDULE_DELAY = timedelta(days=29)


class NewVideoBody(BaseModel):
    topic: str
    knowledge_topic_id: int | None = None


class VideoPatchBody(BaseModel):
    caption: str | None = None
    hashtags: list[str] | None = None
    affiliates: list[str] | None = None
    pinned_comment: str | None = None
    music_suggestions: list[str] | None = None
    music_volume: int | None = None
    voice_enabled: bool | None = None
    options: dict | None = None  # some of video_options.DEFAULTS
    reset_options: bool = False  # "Lấy theo mặc định nhóm": the team's defaults replace every setting


class ScenePatchBody(BaseModel):
    text: str | None = None
    seconds: float | None = None
    keywords: list[str] | None = None
    keywords_en: list[str] | None = None
    image_prompt: str | None = None
    voice_text: str | None = None
    video_start: float | None = None
    text_position: object = None  # the text box centre [x, y]; null: back to the video's (or template's)


class PublishBody(BaseModel):
    fanpage_id: int
    scheduled_at: datetime | None = None


class SceneOrderBody(BaseModel):
    ids: list[int]


def invalid(message: str) -> ApiError:
    return ApiError(422, "invalid_value", message)


def _clean_text(value: str, limit: int, label: str) -> str:
    value = unicodedata.normalize("NFC", value.replace("\r\n", "\n"))
    if len(value) > limit:
        raise invalid(f"{label} dài quá {limit} ký tự")
    return value


def _clean_list(values: list[str], limit: int, label: str, max_items: int = MAX_LIST_ITEMS) -> list[str]:
    items = [unicodedata.normalize("NFC", value).strip() for value in values]
    items = [item for item in items if item]
    if len(items) > max_items or any(len(item) > limit for item in items):
        raise invalid(f"{label}: tối đa {max_items} mục, mỗi mục tối đa {limit} ký tự")
    return items


def _saved(db: DbSession, video: Video) -> dict:
    db.commit()
    return video_payload(db, video)


def _enqueue(db: DbSession, video: Video, kind: str, me: Session, retry_of: Job | None = None) -> None:
    """Callers hold the video lock; the partial unique index is the last guard against a second job."""
    ensure_unlocked(db, video)
    db.add(
        Job(
            video_id=video.id,
            kind=kind,
            status="queued",
            created_by_id=me.user_id,
            retry_of_id=retry_of.id if retry_of else None,
        )
    )
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "video_locked", "Video đang có job chờ hoặc đang chạy") from None


def _ensure_renderable(db: DbSession, video: Video) -> None:
    if not video.has_script:
        raise ApiError(409, "no_script", "Video chưa có kịch bản")
    title, scenes = split_scenes(db, video)
    checks = run_checks(db, video, title, scenes)
    if checks.blocking:
        raise ApiError(409, "render_blocked", f"Chưa render được: {checks.blocking[0].message}")


# --- Videos ---


@router.get("/videos")
def list_videos(q: str = "", me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> list[dict]:
    query = select(Video).order_by(Video.created_at.desc(), Video.id.desc())
    if q.strip():
        literal = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{unicodedata.normalize('NFC', literal)}%"
        plain = func.replace(func.replace(Scene.text, "*", ""), "\n", " ")
        title_match = select(Scene.video_id).where(Scene.is_title, plain.ilike(pattern, escape="\\"))
        query = query.where(or_(Video.topic.ilike(pattern, escape="\\"), Video.id.in_(title_match)))
    return [list_payload(db, video) for video in db.scalars(query).all()]


@router.post("/videos", status_code=201)
def create_video(body: NewVideoBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    topic = " ".join(unicodedata.normalize("NFC", body.topic).split())
    if not topic:
        raise invalid("Hãy nhập chủ đề")
    if len(topic) > MAX_TOPIC_LENGTH:
        raise invalid(f"Chủ đề dài quá {MAX_TOPIC_LENGTH} ký tự")
    group = db.get(KnowledgeTopic, body.knowledge_topic_id) if body.knowledge_topic_id else None
    if group is None:
        raise invalid("Hãy chọn nhóm chủ đề")
    if not group.script_prompt:
        raise invalid(f"Nhóm chủ đề “{group.name}” chưa có prompt viết kịch bản")
    video = Video(topic=topic, knowledge_topic_id=group.id, has_script=False, created_by_id=me.user_id)
    video_options.apply_team_defaults(db, video)
    db.add(video)
    db.flush()
    _enqueue(db, video, "script", me)
    return _saved(db, video)


@router.get("/videos/{video_id}")
def get_video(video_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    video = db.get(Video, video_id)
    if video is None:
        raise video_not_found()
    return video_payload(db, video)


@router.patch("/videos/{video_id}")
def patch_video(
    video_id: int,
    body: VideoPatchBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    video = lock_video(db, video_id)
    ensure_unlocked(db, video)
    fields = body.model_fields_set
    if "caption" in fields and body.caption is not None:
        video.caption = _clean_text(body.caption, MAX_LONG_TEXT_LENGTH, "Caption").strip()
    if "pinned_comment" in fields and body.pinned_comment is not None:
        video.pinned_comment = _clean_text(body.pinned_comment, MAX_LONG_TEXT_LENGTH, "Bình luận ghim").strip()
    if "hashtags" in fields and body.hashtags is not None:
        video.hashtags = _clean_list(body.hashtags, MAX_KEYWORD_LENGTH, "Hashtag")
    if "affiliates" in fields and body.affiliates is not None:
        video.affiliates = _clean_list(body.affiliates, MAX_TEXT_LENGTH, "Affiliate")
    if "music_suggestions" in fields and body.music_suggestions is not None:
        video.music_suggestions = _clean_list(body.music_suggestions, MAX_TEXT_LENGTH, "Gợi ý nhạc")
    if "music_volume" in fields and body.music_volume is not None:
        if not 0 <= body.music_volume <= 100:
            raise invalid("Âm lượng phải từ 0 đến 100%")
        video.music_volume = body.music_volume
    if "voice_enabled" in fields and body.voice_enabled is not None:
        video.voice_enabled = body.voice_enabled
    look = video_options.text_look(video)
    if body.reset_options:
        video_options.apply_team_defaults(db, video)
    if body.options:
        try:
            changes = video_options.clean(body.options)
        except video_options.OptionError as err:
            raise invalid(str(err)) from None
        video.options = video_options.effective(video) | changes
    if video_options.text_look(video) != look:
        # The thumbnail is the title scene's first frame, drawn in the text box style.
        title, _ = split_scenes(db, video)
        refresh_thumbnail(db, storage, video, title)
    return _saved(db, video)


@router.delete("/videos/{video_id}")
def delete_video(
    video_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    video = lock_video(db, video_id)
    ensure_unlocked(db, video)
    db.execute(delete(Video).where(Video.id == video_id))
    db.commit()
    # Files only go after the rows: a failed commit must not leave a video whose photos are gone.
    storage.delete_prefix(f"videos/{video_id}")
    return {"ok": True}


@router.post("/videos/{video_id}/script")
def write_script(video_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    video = lock_video(db, video_id)
    if video.has_script:
        raise ApiError(409, "script_exists", "Video đã có kịch bản")
    # A cancelled clone draft reruns the clone with the snapshot and change request it was made with.
    _enqueue(db, video, "clone" if video.clone_source else "script", me)
    return _saved(db, video)


@router.post("/videos/{video_id}/render")
def render(video_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    video = lock_video(db, video_id)
    ensure_unlocked(db, video)
    _ensure_renderable(db, video)
    _enqueue(db, video, "render", me)
    return _saved(db, video)


@router.post("/videos/{video_id}/image")
def generate_images(video_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    video = lock_video(db, video_id)
    if not video.has_script:
        raise ApiError(409, "no_script", "Video chưa có kịch bản")
    # Scenes that already have a photo or a clip are skipped by the job, so pressing this
    # again after a partial run only pays for the scenes still missing a photo.
    _enqueue(db, video, "image", me)
    return _saved(db, video)


@router.post("/videos/{video_id}/publish")
def publish(
    video_id: int, body: PublishBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    video = lock_video(db, video_id)
    ensure_unlocked(db, video)
    if not video.mp4_key:
        raise ApiError(409, "no_mp4", "Video chưa có MP4, hãy render trước")
    title, scenes = split_scenes(db, video)
    if video.rendered_signature != render_signature(video, title, scenes):
        raise ApiError(409, "mp4_outdated", "MP4 chưa cập nhật theo bản sửa, hãy render lại rồi đăng")
    post = publication_of(db, video.id)
    if post is not None and post.status != "pending":
        raise ApiError(409, "already_published", "Video này đã đăng hoặc đã hẹn giờ trên Facebook")
    when = body.scheduled_at
    if when is not None:
        if when.tzinfo is None:
            raise invalid("Giờ đăng phải kèm múi giờ")
        if not now() + MIN_SCHEDULE_DELAY <= when <= now() + MAX_SCHEDULE_DELAY:
            raise invalid("Giờ hẹn phải sau ít nhất 15 phút và trong vòng 29 ngày tới")
    fanpage = db.get(Fanpage, body.fanpage_id)
    if fanpage is None or not fanpage.active:
        raise invalid("Hãy chọn một Fanpage đang dùng")
    if post is None:
        post = Publication(video_id=video.id, platform="facebook", created_by_id=me.user_id)
        db.add(post)
    # A reel belongs to its Page: moving the post would leave the first reel to go live by itself.
    elif post.remote_id and post.fanpage_id != fanpage.id:
        raise ApiError(409, "other_fanpage", "Video đã tải lên Fanpage khác, hãy đăng lại trên Fanpage đó")
    post.fanpage_id, post.scheduled_at, post.created_by_id = fanpage.id, when, me.user_id
    _enqueue(db, video, "publish", me)
    return _saved(db, video)


@router.post("/videos/{video_id}/music")
def upload_music(
    video_id: int,
    file: UploadFile = File(...),
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    data = read_limited(file, MAX_MUSIC_BYTES, "File nhạc quá 20 MB, hãy chọn file nhỏ hơn")
    try:
        check_mp3(data)
    except UploadRejected as err:
        raise ApiError(415, "invalid_music", str(err)) from None
    video = lock_video(db, video_id)
    ensure_unlocked(db, video)
    old = video.music_key
    video.music_key, video.music_name = new_key(video.id, "music", "mp3"), file_label(file.filename, "nhac.mp3")
    storage.save_bytes(video.music_key, data)
    payload = _saved(db, video)
    storage.delete(old)
    return payload


class LibraryMusicBody(BaseModel):
    track_id: int


@router.post("/videos/{video_id}/music/from-library")
def music_from_library(
    video_id: int,
    body: LibraryMusicBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    video = lock_video(db, video_id)
    ensure_unlocked(db, video)
    track = db.get(MusicTrack, body.track_id)
    if track is None or not storage.exists(track.storage_key):
        raise ApiError(404, "track_not_found", "Không tìm thấy bài nhạc (có thể đã bị xóa)")
    old = video.music_key
    # A copy of its own, like a clone's music: editing or deleting the track never changes this video.
    video.music_key, video.music_name = new_key(video.id, "music", "mp3"), track.name
    storage.save_file(video.music_key, storage.path(track.storage_key))
    payload = _saved(db, video)
    storage.delete(old)
    return payload


@router.delete("/videos/{video_id}/music")
def remove_music(
    video_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    video = lock_video(db, video_id)
    ensure_unlocked(db, video)
    old, video.music_key, video.music_name = video.music_key, None, None
    payload = _saved(db, video)
    storage.delete(old)
    return payload


class CloneBody(BaseModel):
    request: str


def _one_line(text: str) -> str:
    return " / ".join(line.strip() for line in text.split("\n") if line.strip())


def clone_snapshot(db: DbSession, video: Video, request: str) -> dict:
    """What the clone prompt sees: the source exactly as edited at the moment "Nhân bản" was pressed."""
    title, scenes = split_scenes(db, video)
    lines = []

    def voice(scene: Scene) -> str:
        return f" — lời đọc: {_one_line(scene.voice_text)}" if scene.voice_text.strip() else ""

    if title is not None:
        lines.append(f"Cảnh tiêu đề ({title.seconds:g} giây): {_one_line(title.text)}{voice(title)}")
    for number, scene in enumerate(scenes, start=1):
        keywords = f" — từ khóa ảnh: {', '.join(scene.keywords)}" if scene.keywords else ""
        lines.append(f"Cảnh {number} ({scene.seconds:g} giây): {_one_line(scene.text)}{voice(scene)}{keywords}")
    if video.caption:
        lines.append(f"Caption: {video.caption}")
    if video.hashtags:
        lines.append(f"Hashtag: {' '.join(video.hashtags)}")
    if video.affiliates:
        lines.append(f"Affiliate: {'; '.join(video.affiliates)}")
    if video.pinned_comment:
        lines.append(f"Bình luận ghim: {video.pinned_comment}")
    return {
        "video_id": video.id,
        "title": title_of(video, title) or video.topic,
        "topic": video.topic,
        "script": "\n".join(lines),
        "request": request,
    }


@router.post("/videos/{video_id}/clone", status_code=201)
def clone_video(
    video_id: int,
    body: CloneBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    request = " ".join(unicodedata.normalize("NFC", body.request).split())
    if not request:
        raise invalid("Hãy nhập yêu cầu đổi, ví dụ: đổi sang mốc 45 tuổi, tim mạch")
    if len(request) > MAX_TOPIC_LENGTH:
        raise invalid(f"Yêu cầu đổi dài quá {MAX_TOPIC_LENGTH} ký tự")
    # The source is only read, never locked for editing: a teammate may keep working on it.
    source = db.get(Video, video_id)
    if source is None:
        raise video_not_found()
    if not source.has_script:
        raise ApiError(409, "no_script", "Video gốc chưa có kịch bản để nhân bản")
    group = knowledge.topic_of(db, source)
    if group is None or not group.clone_prompt:
        raise invalid(f"Nhóm chủ đề “{group.name if group else ''}” chưa có prompt nhân bản")
    draft = Video(
        topic=request,
        knowledge_topic_id=group.id,
        has_script=False,
        created_by_id=me.user_id,
        music_volume=source.music_volume,
        voice_enabled=source.voice_enabled,
        options=video_options.effective(source),
        clone_source=clone_snapshot(db, source, request),
    )
    db.add(draft)
    db.flush()
    if source.music_key and storage.exists(source.music_key):
        # A copy of its own, so deleting or changing the source never takes the draft's music away.
        draft.music_key, draft.music_name = new_key(draft.id, "music", "mp3"), source.music_name
        storage.save_file(draft.music_key, storage.path(source.music_key))
    _enqueue(db, draft, "clone", me)
    return _saved(db, draft)


# --- Scenes ---


@router.post("/videos/{video_id}/scenes", status_code=201)
def add_scene(video_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    video = lock_video(db, video_id)
    ensure_unlocked(db, video)
    if not video.has_script:
        raise ApiError(409, "no_script", "Video chưa có kịch bản")
    last = db.scalar(select(func.max(Scene.position)).where(Scene.video_id == video.id, Scene.is_title.is_(False)))
    db.add(
        Scene(
            video_id=video.id,
            is_title=False,
            position=(last or 0) + 1,
            text="",
            seconds=NEW_SCENE_SECONDS,
            keywords=[],
            keywords_en=[],
            image_prompt="",
        )
    )
    return _saved(db, video)


@router.put("/videos/{video_id}/scene-order")
def reorder_scenes(
    video_id: int, body: SceneOrderBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    video = lock_video(db, video_id)
    ensure_unlocked(db, video)
    _, scenes = split_scenes(db, video)
    by_id = {scene.id: scene for scene in scenes}
    # The last order saved wins; scenes a teammate added meanwhile keep their place at the end.
    ordered = [by_id[scene_id] for scene_id in dict.fromkeys(body.ids) if scene_id in by_id]
    ordered += [scene for scene in scenes if scene not in ordered]
    for position, scene in enumerate(ordered, start=1):
        scene.position = position
    return _saved(db, video)


@router.patch("/scenes/{scene_id}")
def patch_scene(
    scene_id: int,
    body: ScenePatchBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    video, scene = lock_scene(db, scene_id)
    ensure_unlocked(db, video)
    fields = body.model_fields_set
    text_changed = False
    if "text" in fields and body.text is not None:
        text = _clean_text(body.text, MAX_TEXT_LENGTH, "Chữ")
        text_changed = text != scene.text
        scene.text = text
    if "seconds" in fields and body.seconds is not None:
        if not math.isfinite(body.seconds) or not 0 <= body.seconds <= 100 * MAX_SECONDS:
            raise invalid("Số giây không hợp lệ")
        scene.seconds = round(body.seconds, 2)
    if "keywords" in fields and body.keywords is not None:
        keywords = _clean_list(body.keywords, MAX_KEYWORD_LENGTH, "Từ khóa")
        if len(keywords) > MAX_KEYWORDS:
            raise invalid(f"Tối đa {MAX_KEYWORDS} từ khóa")
        scene.keywords = keywords
    if "keywords_en" in fields and body.keywords_en is not None:
        keywords_en = _clean_list(body.keywords_en, MAX_KEYWORD_LENGTH, "Từ khóa tiếng Anh")
        if len(keywords_en) > MAX_KEYWORDS:
            raise invalid(f"Tối đa {MAX_KEYWORDS} từ khóa")
        scene.keywords_en = keywords_en
    if "image_prompt" in fields and body.image_prompt is not None:
        scene.image_prompt = _clean_text(body.image_prompt, MAX_LONG_TEXT_LENGTH, "Prompt ảnh").strip()
    if "voice_text" in fields and body.voice_text is not None:
        scene.voice_text = _clean_text(body.voice_text, MAX_VOICE_LENGTH, "Lời đọc").strip()
    start_changed = False
    if "video_start" in fields and body.video_start is not None:
        if not scene.video_key:
            raise invalid("Cảnh này chưa có video")
        # At least the shortest scene's worth of clip is left after the start.
        latest = max(0.0, (scene.video_seconds or 0) - MIN_SECONDS)
        if not math.isfinite(body.video_start) or not 0 <= body.video_start <= latest:
            raise invalid(f"Giây bắt đầu phải từ 0 đến {latest:g}")
        start = round(body.video_start, 2)
        start_changed = start != scene.video_start
        scene.video_start = start
    moved = False
    if "text_position" in fields:
        try:
            position = video_options.clean_position(body.text_position)
        except video_options.OptionError as err:
            raise invalid(str(err)) from None
        # The title moves only up and down (place_box): its x is kept at the centre.
        if position and scene.is_title:
            position[0] = FRAME_WIDTH // 2
        new_x, new_y = position if position else (None, None)
        moved = (new_x, new_y) != (scene.text_x, scene.text_y)
        scene.text_x, scene.text_y = new_x, new_y
    if scene.is_title and (text_changed or start_changed or moved):
        title, _ = split_scenes(db, video)
        refresh_thumbnail(db, storage, video, title)
    return _saved(db, video)


@router.delete("/scenes/{scene_id}")
def delete_scene(
    scene_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    video, scene = lock_scene(db, scene_id)
    ensure_unlocked(db, video)
    if scene.is_title:
        raise ApiError(409, "title_scene", "Không xóa được cảnh tiêu đề")
    files = [scene.image_key, scene.voice_key, scene.video_key]
    db.delete(scene)
    payload = _saved(db, video)
    for key in files:
        storage.delete(key)
    return payload


def _store_photo(
    db: DbSession, storage: DirectoryStorage, scene_id: int, data: bytes, extension: str, source: str
) -> dict:
    video, scene = lock_scene(db, scene_id)
    ensure_unlocked(db, video)
    old = [scene.image_key, scene.video_key]
    key = new_key(video.id, f"scene-{scene.id}", extension)
    storage.save_bytes(key, data)
    scene.image_key, scene.image_source, scene.image_error = key, source, None
    # A photo replaces the scene's clip: a scene shows one or the other.
    scene.video_key, scene.video_seconds, scene.video_start = None, None, 0
    if scene.is_title:
        title, _ = split_scenes(db, video)
        refresh_thumbnail(db, storage, video, title)
    payload = _saved(db, video)
    for key in old:
        storage.delete(key)
    return payload


@router.post("/scenes/{scene_id}/image")
def upload_scene_image(
    scene_id: int,
    file: UploadFile = File(...),
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    data = read_limited(file, MAX_IMAGE_BYTES, "Ảnh quá 15 MB, hãy chọn ảnh nhỏ hơn")
    try:
        extension = image_extension(data)
    except UploadRejected as err:
        raise ApiError(415, "invalid_image", str(err)) from None
    return _store_photo(db, storage, scene_id, data, extension, "upload")


def _spool_clip(upload: UploadFile, target: Path) -> None:
    """Copy the upload to a file of its own, refusing it once it passes the limit: clips are too big for memory."""
    with open(target, "wb") as file:
        copied = 0
        while chunk := upload.file.read(1024 * 1024):
            copied += len(chunk)
            if copied > clips.MAX_CLIP_BYTES:
                raise ApiError(413, "file_too_large", "Video quá 50 MB, hãy chọn video ngắn hơn hoặc nén nhỏ lại")
            file.write(chunk)


@router.post("/scenes/{scene_id}/video")
def upload_scene_video(
    scene_id: int,
    file: UploadFile = File(...),
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    with tempfile.TemporaryDirectory(prefix="reels_clip_") as folder:
        upload = Path(folder) / "clip"
        _spool_clip(file, upload)
        return _attach_clip(db, storage, scene_id, upload)


def _attach_clip(db: DbSession, storage: DirectoryStorage, scene_id: int, upload: Path) -> dict:
    """A clip file in place of the scene's photo or clip, whether uploaded or downloaded from a stock source."""
    # ffprobe runs before any row is locked; the save below locks and re-checks everything.
    try:
        clip = clips.check_clip(upload)
    except UploadRejected as err:
        raise ApiError(415, "invalid_video", str(err)) from None
    video, scene = lock_scene(db, scene_id)
    ensure_unlocked(db, video)
    old = [scene.image_key, scene.video_key]
    key = new_key(video.id, f"clip-{scene.id}", clip.extension)
    storage.save_file(key, upload)
    scene.video_key, scene.video_seconds, scene.video_start = key, round(clip.seconds, 3), 0
    # A clip replaces the scene's photo, and the scene lasts as long as the clip minus the crossfades around it
    # (one for the title, at most two for a content scene), in tenths, so the clip never ends on a held frame.
    scene.image_key, scene.image_source, scene.image_error = None, None, None
    playable = clip.seconds - (1 if scene.is_title else 2) * CROSSFADE_SIDE_SECONDS
    scene.seconds = max(MIN_SECONDS, min(MAX_CLIP_SCENE_SECONDS, math.floor(round(playable * 10, 6)) / 10))
    if scene.is_title:
        title, _ = split_scenes(db, video)
        refresh_thumbnail(db, storage, video, title)
    payload = _saved(db, video)
    for old_key in old:
        storage.delete(old_key)
    return payload


@router.delete("/scenes/{scene_id}/video")
def remove_scene_video(
    scene_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    video, scene = lock_scene(db, scene_id)
    ensure_unlocked(db, video)
    old, scene.video_key, scene.video_seconds, scene.video_start = scene.video_key, None, None, 0
    if scene.is_title:
        title, _ = split_scenes(db, video)
        refresh_thumbnail(db, storage, video, title)
    payload = _saved(db, video)
    storage.delete(old)
    return payload


@router.post("/scenes/{scene_id}/find-image")
def find_other_image(
    scene_id: int,
    source: str = "pixabay",
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    client, error_type = _stock_client(source, db)
    video, scene = lock_scene(db, scene_id)
    ensure_unlocked(db, video)
    if source in stock_turned_off(db):
        raise invalid("Nguồn này đang tắt trong Cài đặt › Nguồn tư liệu")
    # Each source is searched in the language it indexes: Openverse in Vietnamese, Pixabay and Pexels
    # in English; the other list is the fallback (scenes scripted before English keywords existed).
    vietnamese, english = list(scene.keywords), list(scene.keywords_en)
    keywords = (vietnamese or english) if source == "openverse" else (english or vietnamese)
    current = scene.image_source
    if not keywords:
        raise invalid("Hãy nhập từ khóa tìm ảnh trước")
    # No row lock may be held while the source answers; the save below locks and re-checks everything.
    db.rollback()
    try:
        photo = client.find_photo(keywords, time.monotonic() + FIND_IMAGE_SECONDS, after=current)
    except error_type as err:
        code = "pixabay_error" if source == "pixabay" else "stock_error"
        raise ApiError(502, code, f"Không tìm được ảnh: {err.message}") from None
    if photo is None:
        raise ApiError(404, "no_other_image", "Không tìm thấy ảnh khác, hãy đổi từ khóa")
    return _store_photo(db, storage, scene_id, photo.data, photo.extension, photo.url)


def _pixabay_failed(err: PixabayError) -> ApiError:
    return ApiError(502, "pixabay_error", f"Không tìm được ảnh: {err.message}")


@router.get("/scenes/{scene_id}/pixabay")
def search_pixabay(
    scene_id: int, q: str = "", me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """Results for the "Chọn từ Pixabay" grid; thumbnails are shown from Pixabay and never stored."""
    if db.get(Scene, scene_id) is None:
        raise ApiError(404, "scene_deleted", "Cảnh này đã bị xóa")
    keyword = " ".join(q.split())
    if not keyword:
        raise invalid("Hãy nhập từ khóa tìm ảnh")
    if len(keyword) > MAX_KEYWORD_LENGTH:
        raise invalid(f"Từ khóa dài quá {MAX_KEYWORD_LENGTH} ký tự")
    db.rollback()
    try:
        hits = Pixabay(source_keys.get(db, "pixabay")).search_hits(keyword, time.monotonic() + FIND_IMAGE_SECONDS)
    except PixabayError as err:
        raise _pixabay_failed(err) from None
    return {"keyword": keyword, "hits": [{"url": hit.url, "preview": hit.preview} for hit in hits]}


class PixabayChoiceBody(BaseModel):
    keyword: str
    url: str


@router.post("/scenes/{scene_id}/pixabay")
def choose_pixabay(
    scene_id: int,
    body: PixabayChoiceBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """Download the chosen photo into storage; it must be one of Pixabay's results for that keyword."""
    video, _ = lock_scene(db, scene_id)
    ensure_unlocked(db, video)
    db.rollback()
    client = Pixabay(source_keys.get(db, "pixabay"))
    deadline = time.monotonic() + FIND_IMAGE_SECONDS
    try:
        # The address comes from the browser: only a result Pixabay itself returned may be fetched.
        if body.url not in client.search(" ".join(body.keyword.split()), deadline):
            raise invalid("Ảnh này không có trong kết quả Pixabay, hãy tìm lại")
        photo = client.download(body.url, deadline)
    except PixabayError as err:
        raise _pixabay_failed(err) from None
    if photo is None:
        raise ApiError(422, "unusable_image", "Ảnh này không tải được, hãy chọn ảnh khác")
    return _store_photo(db, storage, scene_id, photo.data, photo.extension, photo.url)


# --- Stock sources for the picker ---

STOCK_SOURCES = ("pixabay", "pexels", "openverse")
STOCK_LABELS = {"pixabay": "Pixabay", "pexels": "Pexels", "openverse": "Openverse"}
STOCK_OFF_KEY = "stock_sources_off"
CLIP_DOWNLOAD_SECONDS = 60


def _stock_client(source: str, db: DbSession):
    """The picker client for a source and its error type; an unknown source is a bad request."""
    if source == "pixabay":
        return Pixabay(source_keys.get(db, "pixabay")), PixabayError
    if source == "pexels":
        return Pexels(source_keys.get(db, "pexels")), PexelsError
    if source == "openverse":
        return Openverse(), OpenverseError
    raise invalid("Nguồn ảnh không hợp lệ")


def stock_configured(source: str, db: DbSession) -> bool:
    if source in ("pixabay", "pexels"):
        return bool(source_keys.get(db, source))
    return True  # Openverse answers anonymous calls.


def stock_turned_off(db: DbSession) -> set[str]:
    """The sources the team turned off on Cài đặt › Nguồn tư liệu."""
    setting = db.get(AppSetting, STOCK_OFF_KEY)
    return (
        {item for item in setting.value if item in STOCK_SOURCES}
        if setting and isinstance(setting.value, list)
        else set()
    )


def _stock_available(source: str, db: DbSession) -> bool:
    return stock_configured(source, db) and source not in stock_turned_off(db)


@router.get("/stock/sources")
def stock_sources(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> list[dict]:
    """The picker's sources; `clips` says which also offer video clips."""
    return [
        {
            "id": source,
            "label": STOCK_LABELS[source],
            "available": _stock_available(source, db),
            "clips": source in stock_clips.SOURCES and _stock_available(source, db),
        }
        for source in STOCK_SOURCES
    ]


@router.get("/scenes/{scene_id}/stock-clips")
def search_stock_clips(
    scene_id: int,
    q: str = "",
    source: str = "pexels",
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
) -> dict:
    """Video clips for the picker's "Video" mode: a still and the length of each, shown straight from the source."""
    if db.get(Scene, scene_id) is None:
        raise ApiError(404, "scene_deleted", "Cảnh này đã bị xóa")
    keyword = " ".join(q.split())
    if not keyword:
        raise invalid("Hãy nhập từ khóa tìm video")
    if len(keyword) > MAX_KEYWORD_LENGTH:
        raise invalid(f"Từ khóa dài quá {MAX_KEYWORD_LENGTH} ký tự")
    if source in stock_turned_off(db):
        raise invalid("Nguồn này đang tắt trong Cài đặt › Nguồn tư liệu")
    db.rollback()
    try:
        hits = stock_clips.search(source, keyword, FIND_IMAGE_SECONDS, source_keys.get(db, source))
    except stock_clips.ClipSearchError as err:
        raise ApiError(502, "stock_error", f"Không tìm được video: {err.message}") from None
    return {
        "keyword": keyword,
        "source": source,
        "hits": [{"id": hit.id, "preview": hit.preview, "url": hit.url, "seconds": hit.seconds} for hit in hits],
    }


class StockClipBody(BaseModel):
    source: str
    keyword: str
    id: str


@router.post("/scenes/{scene_id}/stock-clips")
def choose_stock_clip(
    scene_id: int,
    body: StockClipBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """Download the chosen clip and store it with the scene like an upload; it must be in the source's results."""
    video, _ = lock_scene(db, scene_id)
    ensure_unlocked(db, video)
    if body.source in stock_turned_off(db):
        raise invalid("Nguồn này đang tắt trong Cài đặt › Nguồn tư liệu")
    db.rollback()
    try:
        hit = next(
            (
                hit
                for hit in stock_clips.search(
                    body.source,
                    " ".join(body.keyword.split()),
                    FIND_IMAGE_SECONDS,
                    source_keys.get(db, body.source),
                )
                if hit.id == body.id
            ),
            None,
        )
        if hit is None:
            raise invalid("Video này không có trong kết quả tìm, hãy tìm lại")
        data = stock_clips.download(hit, CLIP_DOWNLOAD_SECONDS)
    except stock_clips.ClipSearchError as err:
        raise ApiError(502, "stock_error", err.message) from None
    with tempfile.TemporaryDirectory(prefix="reels_clip_") as folder:
        path = Path(folder) / "clip"
        path.write_bytes(data)
        return _attach_clip(db, storage, scene_id, path)


@router.get("/scenes/{scene_id}/stock")
def search_stock(
    scene_id: int,
    q: str = "",
    source: str = "pixabay",
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
) -> dict:
    """Results for the picker's source switch; the same contract as the Pixabay-only search."""
    if db.get(Scene, scene_id) is None:
        raise ApiError(404, "scene_deleted", "Cảnh này đã bị xóa")
    keyword = " ".join(q.split())
    if not keyword:
        raise invalid("Hãy nhập từ khóa tìm ảnh")
    if len(keyword) > MAX_KEYWORD_LENGTH:
        raise invalid(f"Từ khóa dài quá {MAX_KEYWORD_LENGTH} ký tự")
    if source in stock_turned_off(db):
        raise invalid("Nguồn này đang tắt trong Cài đặt › Nguồn tư liệu")
    client, error_type = _stock_client(source, db)
    db.rollback()
    try:
        hits = client.search_hits(keyword, time.monotonic() + FIND_IMAGE_SECONDS)
    except error_type as err:
        raise ApiError(502, "stock_error", f"Không tìm được ảnh: {err.message}") from None
    return {"keyword": keyword, "source": source, "hits": [{"url": hit.url, "preview": hit.preview} for hit in hits]}


class StockChoiceBody(BaseModel):
    source: str
    keyword: str
    url: str


@router.post("/scenes/{scene_id}/stock")
def choose_stock(
    scene_id: int,
    body: StockChoiceBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """Download the chosen photo from its source; it must be one of that source's results for the keyword."""
    video, _ = lock_scene(db, scene_id)
    ensure_unlocked(db, video)
    if body.source in stock_turned_off(db):
        raise invalid("Nguồn này đang tắt trong Cài đặt › Nguồn tư liệu")
    client, error_type = _stock_client(body.source, db)
    db.rollback()
    deadline = time.monotonic() + FIND_IMAGE_SECONDS
    try:
        # The address comes from the browser: only a result the source itself returned may be fetched.
        if body.url not in client.search(" ".join(body.keyword.split()), deadline):
            raise invalid("Ảnh này không có trong kết quả tìm, hãy tìm lại")
        photo = client.download(body.url, deadline)
    except error_type as err:
        raise ApiError(502, "stock_error", f"Không tìm được ảnh: {err.message}") from None
    if photo is None:
        raise ApiError(422, "unusable_image", "Ảnh này không tải được, hãy chọn ảnh khác")
    return _store_photo(db, storage, scene_id, photo.data, photo.extension, photo.url)


# --- Jobs ---

JOB_LIST_LIMIT = 300


@router.get("/jobs")
def list_jobs(
    before: int | None = None, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> list[dict]:
    """The job log: newest first, including cancelled jobs and every retry. One page per call; `before`
    (the oldest job id shown) gives the next, older page."""
    query = select(Job).order_by(Job.id.desc()).limit(JOB_LIST_LIMIT)
    if before is not None:
        query = query.where(Job.id < before)
    jobs = db.scalars(query).all()
    titles = {}
    rows = []
    for job in jobs:
        if job.video_id not in titles:
            video = db.get(Video, job.video_id)
            title, _ = split_scenes(db, video)
            titles[job.video_id] = title_of(video, title) or video.topic
        ended = job.finished_at
        rows.append(
            {
                "id": job.id,
                "video_id": job.video_id,
                "video_title": titles[job.video_id],
                "kind": job.kind,
                "kind_label": JOB_KINDS.get(job.kind, job.kind),
                "status": job.status,
                "created_by": job.created_by.name,
                "created_at": job.created_at.isoformat(),
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "duration_seconds": round((ended - job.started_at).total_seconds(), 1)
                if job.started_at and ended
                else None,
                "claude_calls": job.claude_calls,
                "image_calls": job.image_calls,
                "llm": llm.label(job.llm_provider, job.llm_model),
                "error": job.error,
            }
        )
    return rows


def _lock_job(db: DbSession, job_id: int) -> Job:
    job = db.scalar(select(Job).where(Job.id == job_id).with_for_update().execution_options(populate_existing=True))
    if job is None:
        raise ApiError(404, "job_not_found", "Không tìm thấy job")
    return job


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    # Waits for the worker while it is claiming this very job (its row lock), then sees the real status.
    job = _lock_job(db, job_id)
    if job.status != "queued":
        raise ApiError(409, "job_not_queued", "Job đã bắt đầu chạy hoặc đã xong, không hủy được")
    job.status, job.finished_at = "cancelled", now()
    db.commit()
    return video_payload(db, db.get(Video, job.video_id))


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    video_id = db.scalar(select(Job.video_id).where(Job.id == job_id))
    if video_id is None:
        raise ApiError(404, "job_not_found", "Không tìm thấy job")
    video = lock_video(db, video_id)
    job = db.get(Job, job_id)
    if job.status != "failed":
        raise ApiError(409, "job_not_failed", "Chỉ thử lại được job bị lỗi")
    ensure_unlocked(db, video)
    if job.kind == "render":
        _ensure_renderable(db, video)
    _enqueue(db, video, job.kind, me, retry_of=job)
    return _saved(db, video)


# --- Files (all behind login) ---


def _file(storage: DirectoryStorage, key: str | None, media_type: str, filename: str | None = None) -> FileResponse:
    if not key or not storage.exists(key):
        raise ApiError(404, "file_not_found", "Không tìm thấy file")
    return FileResponse(
        storage.path(key),
        media_type=media_type,
        filename=filename,
        content_disposition_type="attachment",
        headers={"Cache-Control": "private, max-age=3600"},
    )


def _inline(storage: DirectoryStorage, key: str | None, media_type: str) -> FileResponse:
    if not key or not storage.exists(key):
        raise ApiError(404, "file_not_found", "Không tìm thấy file")
    return FileResponse(storage.path(key), media_type=media_type, headers={"Cache-Control": "private, max-age=3600"})


def _scene(db: DbSession, scene_id: int) -> Scene:
    scene = db.get(Scene, scene_id)
    if scene is None:
        raise ApiError(404, "scene_deleted", "Cảnh này đã bị xóa")
    return scene


@router.get("/scenes/{scene_id}/image")
def scene_image(
    scene_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> FileResponse:
    scene = _scene(db, scene_id)
    extension = (scene.image_key or "").rsplit(".", 1)[-1]
    return _inline(storage, scene.image_key, IMAGE_TYPES.get(extension, "application/octet-stream"))


@router.get("/scenes/{scene_id}/preview.jpg")
def scene_preview(
    scene_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> Response:
    scene = _scene(db, scene_id)
    still = scene_still(storage, scene)
    if still is None:
        raise ApiError(404, "file_not_found", "Cảnh chưa có ảnh hoặc không lấy được khung hình từ video")
    video = db.get(Video, scene.video_id)
    frame = frames.compose_frame(
        still, scene.text, scene.is_title, video_options.render_options(video), text_position(video, scene)
    )
    return Response(
        frames.jpeg_bytes(frame), media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"}
    )


@router.get("/scenes/{scene_id}/frame.jpg")
def scene_frame(
    scene_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> Response:
    """The scene's first frame without its text box, which the text box is dragged over."""
    still = scene_still(storage, _scene(db, scene_id))
    if still is None:
        raise ApiError(404, "file_not_found", "Cảnh chưa có ảnh hoặc không lấy được khung hình từ video")
    frame = frames.compose_frame(still, "", is_title=False)
    return Response(
        frames.jpeg_bytes(frame), media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"}
    )


@router.get("/scenes/{scene_id}/textbox.png")
def scene_textbox(scene_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> Response:
    """The exact box image the renderer overlays on this scene (transparent around it)."""
    scene = _scene(db, scene_id)
    if not scene.text.strip() or text_problem(scene.text, scene.is_title) is not None:
        raise ApiError(404, "no_text_box", "Cảnh này không có chữ để đặt vị trí")
    box, _ = frames.text_box(scene.text, scene.is_title, video_options.render_options(db.get(Video, scene.video_id)))
    buffer = io.BytesIO()
    box.save(buffer, "PNG")
    return Response(buffer.getvalue(), media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/scenes/{scene_id}/video")
def scene_video(
    scene_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> FileResponse:
    scene = _scene(db, scene_id)
    extension = (scene.video_key or "").rsplit(".", 1)[-1]
    return _inline(storage, scene.video_key, CLIP_TYPES.get(extension, "application/octet-stream"))


@router.get("/scenes/{scene_id}/voice.mp3")
def scene_voice(
    scene_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> FileResponse:
    return _inline(storage, _scene(db, scene_id).voice_key, "audio/mpeg")


@router.get("/videos/{video_id}/thumbnail.jpg")
def thumbnail(
    video_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> FileResponse:
    video = db.get(Video, video_id)
    if video is None:
        raise video_not_found()
    return _inline(storage, video.thumbnail_key, "image/jpeg")


@router.get("/videos/{video_id}/music.mp3")
def music_file(
    video_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> FileResponse:
    video = db.get(Video, video_id)
    if video is None:
        raise video_not_found()
    return _inline(storage, video.music_key, "audio/mpeg")


@router.get("/videos/{video_id}/video.mp4")
def video_file(
    video_id: int,
    download: bool = False,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> FileResponse:
    video = db.get(Video, video_id)
    if video is None:
        raise video_not_found()
    if download:
        return _file(storage, video.mp4_key, "video/mp4", f"reels-video-{video.id}.mp4")
    return _inline(storage, video.mp4_key, "video/mp4")


# --- Knowledge ---


class NewTopicBody(BaseModel):
    name: str


class TopicPatchBody(BaseModel):
    name: str | None = None
    script_prompt: str | None = None
    clone_prompt: str | None = None
    banned_words: list[str] | None = None


def _knowledge_payload(db: DbSession) -> dict:
    counts = dict(db.execute(select(Video.knowledge_topic_id, func.count()).group_by(Video.knowledge_topic_id)).all())
    return {
        "topics": [
            {
                "id": topic.id,
                "name": topic.name,
                "script_prompt": topic.script_prompt,
                "clone_prompt": topic.clone_prompt,
                "banned_words": topic.banned_words,
                "video_count": counts.get(topic.id, 0),
            }
            for topic in knowledge.all_topics(db)
        ],
        "default_script_prompt": knowledge.default_script_prompt(),
        "default_clone_prompt": knowledge.default_clone_prompt(),
    }


def _topic_name(db: DbSession, raw: str, own_id: int | None = None) -> str:
    name = " ".join(unicodedata.normalize("NFC", raw).split())
    if not name:
        raise invalid("Hãy nhập tên nhóm chủ đề")
    if len(name) > MAX_TOPIC_NAME_LENGTH:
        raise invalid(f"Tên nhóm chủ đề dài quá {MAX_TOPIC_NAME_LENGTH} ký tự")
    if any(topic.id != own_id and topic.name.casefold() == name.casefold() for topic in knowledge.all_topics(db)):
        raise invalid(f"Đã có nhóm chủ đề “{name}”")
    return name


def _prompt(raw: str) -> str:
    value = unicodedata.normalize("NFC", raw.replace("\r\n", "\n")).strip()
    if not value:
        raise invalid("Prompt không được để trống")
    if len(value) > 20000:
        raise invalid("Prompt dài quá 20000 ký tự")
    return value


def _topic(db: DbSession, topic_id: int) -> KnowledgeTopic:
    topic = db.get(KnowledgeTopic, topic_id)
    if topic is None:
        raise ApiError(404, "topic_not_found", "Không tìm thấy nhóm chủ đề")
    return topic


@router.get("/knowledge")
def get_knowledge(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    return _knowledge_payload(db)


@router.post("/knowledge/topics", status_code=201)
def create_topic(body: NewTopicBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    db.add(KnowledgeTopic(name=_topic_name(db, body.name), updated_by_id=me.user_id))
    db.commit()
    return _knowledge_payload(db)


@router.patch("/knowledge/topics/{topic_id}")
def patch_topic(
    topic_id: int, body: TopicPatchBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    topic = _topic(db, topic_id)
    if body.name is not None:
        topic.name = _topic_name(db, body.name, topic.id)
    if body.script_prompt is not None:
        topic.script_prompt = _prompt(body.script_prompt)
    if body.clone_prompt is not None:
        topic.clone_prompt = _prompt(body.clone_prompt)
    if body.banned_words is not None:
        topic.banned_words = list(
            dict.fromkeys(_clean_list(body.banned_words, MAX_KEYWORD_LENGTH, "Từ cấm", max_items=500))
        )
    topic.updated_by_id = me.user_id
    db.commit()
    return _knowledge_payload(db)


@router.delete("/knowledge/topics/{topic_id}")
def delete_topic(topic_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    topic = _topic(db, topic_id)
    videos = db.scalar(select(func.count()).select_from(Video).where(Video.knowledge_topic_id == topic.id))
    if videos:
        raise ApiError(409, "topic_in_use", f"Nhóm chủ đề còn {videos} video nên chưa xoá được")
    products = db.scalar(
        select(func.count()).select_from(AffiliateProduct).where(AffiliateProduct.knowledge_topic_id == topic.id)
    )
    if products:
        raise ApiError(409, "topic_in_use", f"Nhóm chủ đề còn {products} sản phẩm affiliate nên chưa xoá được")
    db.delete(topic)
    db.commit()
    return _knowledge_payload(db)
