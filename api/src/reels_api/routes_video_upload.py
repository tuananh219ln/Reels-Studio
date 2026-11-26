"""Videos made from a finished MP4 ("MP4 tải lên"): sent from the web as a file, or by link (Muse, MCP). The checks,
the plan link and the gate live in upload_mp4.py (docs/decisions/2026-11-26-upload-mp4.md)."""

import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession

from . import remote_media, upload_mp4
from .db import get_db
from .errors import ApiError
from .models import Session, Video
from .sessions import current_member
from .storage import DirectoryStorage, get_storage
from .uploads import file_label
from .videos import video_payload

router = APIRouter(prefix="/api/videos")

UNREACHABLE_CODES = {remote_media.TOO_LARGE: ("file_too_large", 413)}


class UploadFields(BaseModel):
    knowledge_topic_id: int
    plan_item_id: int | None = None
    title: str | None = Field(default=None, max_length=300)
    caption: str = Field(default="", max_length=6000)
    hashtags: list[str] = Field(default_factory=list, max_length=60)
    pinned_comment_text: str = Field(default="", max_length=3000)
    title_options: list[str] = Field(default_factory=list, max_length=20)
    thumbnail_at_s: float = Field(default=1, ge=0, le=90)
    upload_note: str | None = Field(default=None, max_length=1500)
    idempotency_key: str | None = Field(default=None, max_length=100)
    replace_existing: bool = False


class FromUrlBody(UploadFields):
    source_url: str = Field(max_length=2000)


class ReplaceUrlBody(BaseModel):
    source_url: str = Field(max_length=2000)
    upload_note: str | None = Field(default=None, max_length=1500)


def result(db: DbSession, video: Video) -> dict:
    return video_payload(db, video) | {"warnings": upload_mp4.warnings(db, video)}


def _tags(raw: str) -> list[str]:
    raw = raw.strip()
    if not raw:
        return []
    if raw.startswith("["):
        try:
            found = json.loads(raw)
        except ValueError:
            raise ApiError(422, "invalid_value", "Hashtag phải là danh sách") from None
        return [str(one) for one in found] if isinstance(found, list) else []
    return raw.replace(",", " ").split()


def download(url: str, folder: Path) -> Path:
    try:
        return remote_media.download_mp4(url, folder)
    except remote_media.RemoteMediaError as err:
        if err.reason in UNREACHABLE_CODES:
            code, status = UNREACHABLE_CODES[err.reason]
            raise ApiError(status, code, str(err)) from None
        raise ApiError(422, "source_url_unreachable", str(err)) from None


def create_from_path(
    db: DbSession,
    storage: DirectoryStorage,
    me: Session,
    path: Path,
    fields: UploadFields,
    via: str = "",
    app: str = "",
) -> Video:
    video = upload_mp4.create(
        db,
        storage,
        me,
        path,
        topic_id=fields.knowledge_topic_id,
        via=via,
        app=app,
        **fields.model_dump(exclude={"knowledge_topic_id"}),
    )
    db.commit()
    return video


def save_upload(file: UploadFile, folder: Path) -> Path:
    data = file.file.read(upload_mp4.MAX_BYTES + 1)
    if len(data) > upload_mp4.MAX_BYTES:
        raise ApiError(413, "file_too_large", "File quá 200 MB, hãy nén nhỏ hơn")
    path = folder / "upload.mp4"
    path.write_bytes(data)
    return path


@router.post("/upload", status_code=201)
def upload(
    file: UploadFile = File(...),
    knowledge_topic_id: int = Form(...),
    plan_item_id: int | None = Form(None),
    title: str | None = Form(None),
    caption: str = Form(""),
    hashtags: str = Form(""),
    pinned_comment_text: str = Form(""),
    thumbnail_at_s: float = Form(1),
    upload_note: str | None = Form(None),
    idempotency_key: str | None = Form(None),
    replace_existing: bool = Form(False),
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    fields = UploadFields(
        knowledge_topic_id=knowledge_topic_id,
        plan_item_id=plan_item_id,
        title=title or Path(file_label(file.filename, "")).stem or None,
        caption=caption,
        hashtags=_tags(hashtags),
        pinned_comment_text=pinned_comment_text,
        thumbnail_at_s=thumbnail_at_s,
        upload_note=upload_note,
        idempotency_key=idempotency_key,
        replace_existing=replace_existing,
    )
    if (again := upload_mp4.existing(db, fields.idempotency_key)) is not None:
        return result(db, again)
    with tempfile.TemporaryDirectory(prefix="reels_upload_") as folder:
        path = save_upload(file, Path(folder))
        video = create_from_path(db, storage, me, path, fields)
    return result(db, video)


@router.post("/upload-from-url", status_code=201)
def upload_from_url(
    body: FromUrlBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    # The download runs in the request (up to ~2 minutes), like "Thêm vào kho từ link": see the decision's notes.
    if (again := upload_mp4.existing(db, body.idempotency_key)) is not None:
        return result(db, again)
    with tempfile.TemporaryDirectory(prefix="reels_upload_") as folder:
        path = download(body.source_url, Path(folder))
        video = create_from_path(db, storage, me, path, body.model_copy(update={"title": body.title}))
    return result(db, video)


@router.put("/{video_id}/source-mp4")
def replace_source(
    video_id: int,
    file: UploadFile | None = File(None),
    source_url: str | None = Form(None),
    upload_note: str | None = Form(None),
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    if file is None and not source_url:
        raise ApiError(422, "invalid_value", "Hãy chọn file MP4 hoặc dán link")
    with tempfile.TemporaryDirectory(prefix="reels_upload_") as folder:
        path = save_upload(file, Path(folder)) if file is not None else download(source_url or "", Path(folder))
        video = upload_mp4.replace(db, storage, me, video_id, path, upload_note)
    return result(db, video)
