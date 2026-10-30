import math
import time
import unicodedata

from fastapi import APIRouter, Depends, File, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from . import frames, knowledge
from .db import get_db
from .errors import ApiError
from .models import Job, Scene, Session, Video
from .pixabay import Pixabay, PixabayError
from .script_rules import MAX_SECONDS
from .sessions import current_member, now
from .storage import DirectoryStorage, get_storage
from .uploads import MAX_IMAGE_BYTES, MAX_MUSIC_BYTES, UploadRejected, check_mp3, image_extension, read_limited
from .videos import (
    JOB_KINDS,
    ensure_unlocked,
    list_payload,
    lock_scene,
    lock_video,
    new_key,
    refresh_thumbnail,
    run_checks,
    split_scenes,
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


class NewVideoBody(BaseModel):
    topic: str


class VideoPatchBody(BaseModel):
    caption: str | None = None
    hashtags: list[str] | None = None
    affiliates: list[str] | None = None
    pinned_comment: str | None = None
    music_suggestions: list[str] | None = None
    music_volume: int | None = None
    voice_enabled: bool | None = None


class ScenePatchBody(BaseModel):
    text: str | None = None
    seconds: float | None = None
    keywords: list[str] | None = None
    image_prompt: str | None = None
    voice_text: str | None = None


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
    db.add(Job(video_id=video.id, kind=kind, status="queued", created_by_id=me.user_id,
               retry_of_id=retry_of.id if retry_of else None))
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
    video = Video(topic=topic, has_script=False, created_by_id=me.user_id)
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
    video_id: int, body: VideoPatchBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
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
    video.music_key = new_key(video.id, "music", "mp3")
    # Shown only; the stored file name is always generated by the server.
    name = unicodedata.normalize("NFC", (file.filename or "nhac.mp3").replace("\\", "/").rsplit("/", 1)[-1]).strip()
    video.music_name = name[:200] or "nhac.mp3"
    storage.save_bytes(video.music_key, data)
    payload = _saved(db, video)
    storage.delete(old)
    return payload


@router.delete("/videos/{video_id}/music")
def remove_music(video_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db),
                 storage: DirectoryStorage = Depends(get_storage)) -> dict:
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
    draft = Video(topic=request, has_script=False, created_by_id=me.user_id, music_volume=source.music_volume,
                  clone_source=clone_snapshot(db, source, request))
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
    db.add(Scene(video_id=video.id, is_title=False, position=(last or 0) + 1, text="",
                 seconds=NEW_SCENE_SECONDS, keywords=[], image_prompt=""))
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
    if "image_prompt" in fields and body.image_prompt is not None:
        scene.image_prompt = _clean_text(body.image_prompt, MAX_LONG_TEXT_LENGTH, "Prompt ảnh").strip()
    if "voice_text" in fields and body.voice_text is not None:
        scene.voice_text = _clean_text(body.voice_text, MAX_VOICE_LENGTH, "Lời đọc").strip()
    if scene.is_title and text_changed:
        title, _ = split_scenes(db, video)
        refresh_thumbnail(db, storage, video, title)
    return _saved(db, video)


@router.delete("/scenes/{scene_id}")
def delete_scene(scene_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db),
                 storage: DirectoryStorage = Depends(get_storage)) -> dict:
    video, scene = lock_scene(db, scene_id)
    ensure_unlocked(db, video)
    if scene.is_title:
        raise ApiError(409, "title_scene", "Không xóa được cảnh tiêu đề")
    files = [scene.image_key, scene.voice_key]
    db.delete(scene)
    payload = _saved(db, video)
    for key in files:
        storage.delete(key)
    return payload


def _store_photo(db: DbSession, storage: DirectoryStorage, scene_id: int, data: bytes, extension: str,
                 source: str) -> dict:
    video, scene = lock_scene(db, scene_id)
    ensure_unlocked(db, video)
    old = scene.image_key
    key = new_key(video.id, f"scene-{scene.id}", extension)
    storage.save_bytes(key, data)
    scene.image_key, scene.image_source, scene.image_error = key, source, None
    if scene.is_title:
        title, _ = split_scenes(db, video)
        refresh_thumbnail(db, storage, video, title)
    payload = _saved(db, video)
    storage.delete(old)
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


@router.post("/scenes/{scene_id}/find-image")
def find_other_image(
    scene_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    video, scene = lock_scene(db, scene_id)
    ensure_unlocked(db, video)
    keywords, current = list(scene.keywords), scene.image_source
    if not keywords:
        raise invalid("Hãy nhập từ khóa tìm ảnh trước")
    # No row lock may be held while Pixabay answers; the save below locks and re-checks everything.
    db.rollback()
    client = Pixabay()
    try:
        photo = client.find_photo(keywords, time.monotonic() + FIND_IMAGE_SECONDS, after=current)
    except PixabayError as err:
        raise ApiError(502, "pixabay_error", f"Không tìm được ảnh: {err.message}") from None
    if photo is None:
        raise ApiError(404, "no_other_image", "Không tìm thấy ảnh khác, hãy đổi từ khóa")
    return _store_photo(db, storage, scene_id, photo.data, photo.extension, photo.url)


def _pixabay_failed(err: PixabayError) -> ApiError:
    return ApiError(502, "pixabay_error", f"Không tìm được ảnh: {err.message}")


@router.get("/scenes/{scene_id}/pixabay")
def search_pixabay(scene_id: int, q: str = "", me: Session = Depends(current_member),
                   db: DbSession = Depends(get_db)) -> dict:
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
        hits = Pixabay().search_hits(keyword, time.monotonic() + FIND_IMAGE_SECONDS)
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
    client = Pixabay()
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


# --- Jobs ---

JOB_LIST_LIMIT = 300


@router.get("/jobs")
def list_jobs(before: int | None = None, me: Session = Depends(current_member),
              db: DbSession = Depends(get_db)) -> list[dict]:
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
        rows.append({
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
            if job.started_at and ended else None,
            "claude_calls": job.claude_calls,
            "error": job.error,
        })
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
    return FileResponse(storage.path(key), media_type=media_type, filename=filename,
                        content_disposition_type="attachment", headers={"Cache-Control": "private, max-age=3600"})


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
def scene_image(scene_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db),
                storage: DirectoryStorage = Depends(get_storage)) -> FileResponse:
    scene = _scene(db, scene_id)
    extension = (scene.image_key or "").rsplit(".", 1)[-1]
    return _inline(storage, scene.image_key, IMAGE_TYPES.get(extension, "application/octet-stream"))


@router.get("/scenes/{scene_id}/preview.jpg")
def scene_preview(scene_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db),
                  storage: DirectoryStorage = Depends(get_storage)) -> Response:
    scene = _scene(db, scene_id)
    if not scene.image_key or not storage.exists(scene.image_key):
        raise ApiError(404, "file_not_found", "Cảnh chưa có ảnh")
    frame = frames.compose_frame(storage.path(scene.image_key), scene.text, scene.is_title)
    return Response(frames.jpeg_bytes(frame), media_type="image/jpeg",
                    headers={"Cache-Control": "private, max-age=3600"})


@router.get("/scenes/{scene_id}/voice.mp3")
def scene_voice(scene_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db),
                storage: DirectoryStorage = Depends(get_storage)) -> FileResponse:
    return _inline(storage, _scene(db, scene_id).voice_key, "audio/mpeg")


@router.get("/videos/{video_id}/thumbnail.jpg")
def thumbnail(video_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db),
              storage: DirectoryStorage = Depends(get_storage)) -> FileResponse:
    video = db.get(Video, video_id)
    if video is None:
        raise video_not_found()
    return _inline(storage, video.thumbnail_key, "image/jpeg")


@router.get("/videos/{video_id}/music.mp3")
def music_file(video_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db),
               storage: DirectoryStorage = Depends(get_storage)) -> FileResponse:
    video = db.get(Video, video_id)
    if video is None:
        raise video_not_found()
    return _inline(storage, video.music_key, "audio/mpeg")


@router.get("/videos/{video_id}/video.mp4")
def video_file(video_id: int, download: bool = False, me: Session = Depends(current_member),
               db: DbSession = Depends(get_db), storage: DirectoryStorage = Depends(get_storage)) -> FileResponse:
    video = db.get(Video, video_id)
    if video is None:
        raise video_not_found()
    if download:
        return _file(storage, video.mp4_key, "video/mp4", f"reels-video-{video.id}.mp4")
    return _inline(storage, video.mp4_key, "video/mp4")


# --- Knowledge ---

class PromptBody(BaseModel):
    value: str


class BannedWordsBody(BaseModel):
    words: list[str]


def _knowledge_payload(db: DbSession) -> dict:
    defaults = knowledge.defaults()
    return {
        "script_prompt": knowledge.script_prompt(db),
        "clone_prompt": knowledge.clone_prompt(db),
        "banned_words": knowledge.banned_words(db),
        "default_script_prompt": defaults[knowledge.SCRIPT_PROMPT],
        "default_clone_prompt": defaults[knowledge.CLONE_PROMPT],
        "default_banned_words": defaults[knowledge.BANNED_WORDS],
    }


@router.get("/knowledge")
def get_knowledge(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    return _knowledge_payload(db)


def _save_prompt(db: DbSession, key: str, raw: str, me: Session) -> dict:
    value = unicodedata.normalize("NFC", raw.replace("\r\n", "\n")).strip()
    if not value:
        raise invalid("Prompt không được để trống")
    if len(value) > 20000:
        raise invalid("Prompt dài quá 20000 ký tự")
    knowledge.put(db, key, value, me.user_id)
    db.commit()
    return _knowledge_payload(db)


@router.put("/knowledge/script-prompt")
def put_script_prompt(body: PromptBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    return _save_prompt(db, knowledge.SCRIPT_PROMPT, body.value, me)


@router.put("/knowledge/clone-prompt")
def put_clone_prompt(body: PromptBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    return _save_prompt(db, knowledge.CLONE_PROMPT, body.value, me)


@router.put("/knowledge/banned-words")
def put_banned_words(body: BannedWordsBody, me: Session = Depends(current_member),
                     db: DbSession = Depends(get_db)) -> dict:
    words = list(dict.fromkeys(_clean_list(body.words, MAX_KEYWORD_LENGTH, "Từ cấm", max_items=500)))
    knowledge.put(db, knowledge.BANNED_WORDS, words, me.user_id)
    db.commit()
    return _knowledge_payload(db)
