"""The team's "Kho tư liệu": photos and clips gathered once and used in any scene.

A member drags a whole folder in (the web uploads one file per request, with its folder), or pastes links: a photo's
address (from Google Ảnh, a shop) or a TikTok video, which the api downloads with the same rules as a link pasted
on a scene (remote_media.py: public addresses only, the upload limits). A clip longer than a minute keeps its first
minute. Using an item in a scene copies the file into the video, so deleting it from the library never changes one.
"""

import io
import secrets
import tempfile
import unicodedata
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as DbSession

from . import clips, remote_media
from .db import get_db
from .errors import ApiError
from .models import MediaItem, Session
from .routes_music import like_pattern
from .sessions import current_member
from .storage import DirectoryStorage, get_storage
from .uploads import MAX_IMAGE_BYTES, UploadRejected, file_label, image_extension, read_limited

router = APIRouter(prefix="/api/media")

MAX_LINKS = 10
MAX_FOLDER = 200
MAX_LIST = 500
THUMB_WIDTH = 360
MEDIA_TYPES = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp", "mp4": "video/mp4", "mov": "video/mp4"}
MEDIA_TYPES["webm"] = "video/webm"


class LinksBody(BaseModel):
    urls: list[str]
    folder: str = ""


class MediaPatchBody(BaseModel):
    name: str | None = None
    folder: str | None = None


class UseBody(BaseModel):
    scene_id: int


def invalid(message: str) -> ApiError:
    return ApiError(422, "invalid_value", message)


def clean_folder(raw: str) -> str:
    """A folder as typed or dragged ("Nồi chiên\\cảnh quay/"): NFC, forward slashes, no empty parts."""
    text = unicodedata.normalize("NFC", raw or "").replace("\\", "/")
    parts = [" ".join(part.split()) for part in text.split("/")]
    folder = "/".join(part for part in parts if part and part not in (".", ".."))
    if len(folder) > MAX_FOLDER:
        raise invalid(f"Tên thư mục dài quá {MAX_FOLDER} ký tự")
    return folder


def payload(item: MediaItem) -> dict:
    return {
        "id": item.id,
        "kind": item.kind,
        "name": item.name,
        "folder": item.folder,
        "source_url": item.source_url,
        "seconds": item.seconds,
        "file_url": f"/api/media/{item.id}/file",
        "thumb_url": f"/api/media/{item.id}/thumb.jpg",
        "created_by": item.created_by.name,
        "created_at": item.created_at.isoformat(),
    }


def _new_key(extension: str) -> str:
    return f"media/{secrets.token_hex(8)}.{extension}"


def _add(
    db: DbSession, storage: DirectoryStorage, me: Session, name: str, folder: str, source: str | None, photo=None,
    clip_path: Path | None = None, workdir: Path | None = None,
) -> MediaItem:  # fmt: skip
    """Check and store one photo (bytes, extension) or clip (a file), then add its row."""
    if clip_path is not None:
        try:
            part = clips.first_part(clip_path, workdir)  # the first minute of a longer clip
            clip = clips.check_clip(part)
        except UploadRejected as err:
            raise ApiError(415, "invalid_video", str(err)) from None
        key = _new_key(clip.extension)
        storage.save_file(key, part)
        item = MediaItem(kind="clip", storage_key=key, seconds=round(clip.seconds, 2))
    else:
        data, extension = photo
        key = _new_key(extension)
        storage.save_bytes(key, data)
        item = MediaItem(kind="photo", storage_key=key)
    item.name, item.folder, item.source_url, item.created_by_id = name, folder, source, me.user_id
    db.add(item)
    db.flush()
    return item


@router.get("")
def list_media(
    folder: str | None = None,
    kind: str | None = None,
    q: str | None = None,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
) -> dict:
    """The library newest first (one folder, with its subfolders, when named), and every folder with its count."""
    query = select(MediaItem).order_by(MediaItem.id.desc()).limit(MAX_LIST)
    if folder:
        name = clean_folder(folder)
        query = query.where(or_(MediaItem.folder == name, MediaItem.folder.like(f"{like_pattern(name)}/%", "\\")))
    if kind in ("photo", "clip"):
        query = query.where(MediaItem.kind == kind)
    if q and q.strip():
        pattern = f"%{like_pattern(q.strip())}%"
        query = query.where(or_(MediaItem.name.ilike(pattern, escape="\\"), MediaItem.folder.ilike(pattern, "\\")))
    folders = db.execute(select(MediaItem.folder, func.count()).group_by(MediaItem.folder).order_by(MediaItem.folder))
    return {
        "items": [payload(item) for item in db.scalars(query)],
        "folders": [{"folder": name, "count": count} for name, count in folders if name],
    }


@router.post("", status_code=201)
def upload_media(
    file: UploadFile = File(...),
    folder: str = Form(default=""),
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """One file of a dragged folder or a picked set: a photo (jpg, png, webp) or a clip (mp4, mov, webm)."""
    # The folder a dragged file came with is the path before its name ("Nồi chiên/cảnh 1/a.mp4").
    path = clean_folder(f"{folder}/{file.filename or ''}")
    where, _, filename = path.rpartition("/")
    name = file_label(filename, "Không tên")
    head = file.file.read(16)
    file.file.seek(0)
    if clips.looks_like_clip(head):
        from .routes_videos import _spool_clip

        with tempfile.TemporaryDirectory(prefix="reels_media_") as raw:
            spooled = Path(raw) / "clip"
            _spool_clip(file, spooled)
            item = _add(db, storage, me, name, where, None, clip_path=spooled, workdir=Path(raw))
    else:
        data = read_limited(file, MAX_IMAGE_BYTES, "Ảnh quá 15 MB, hãy chọn ảnh nhỏ hơn")
        try:
            photo = (data, image_extension(data))
        except UploadRejected:
            raise ApiError(
                415, "invalid_media", f"“{name}” không phải ảnh (jpg, png, webp) hay video (mp4, mov, webm)"
            ) from None
        item = _add(db, storage, me, name, where, None, photo=photo)
    db.commit()
    return payload(item)


def add_links(db: DbSession, storage: DirectoryStorage, me: Session, urls: list[str], folder: str) -> dict:
    """Download each link into the library; a link that fails is reported and the others still come in."""
    links = [url.strip() for url in urls if url and url.strip()]
    if not links:
        raise invalid("Hãy dán ít nhất một link")
    if len(links) > MAX_LINKS:
        raise invalid(f"Mỗi lần thêm tối đa {MAX_LINKS} link")
    where = clean_folder(folder)
    added, failed = [], []
    for url in links:
        with tempfile.TemporaryDirectory(prefix="reels_media_") as raw:
            try:
                media = remote_media.download(url, Path(raw))
                name = file_label(Path(url.split("?")[0]).name, "Từ link")
                if media.photo is not None:
                    item = _add(db, storage, me, name, where, url, photo=media.photo)
                else:
                    item = _add(db, storage, me, name, where, url, clip_path=media.clip, workdir=Path(raw))
                db.commit()
                added.append(payload(item))
            except remote_media.RemoteMediaError as err:
                db.rollback()
                failed.append({"url": url, "error": str(err)})
            except ApiError as err:
                db.rollback()
                failed.append({"url": url, "error": err.message})
    return {"added": added, "failed": failed}


@router.post("/links", status_code=201)
def add_media_links(
    body: LinksBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    return add_links(db, storage, me, body.urls, body.folder)


def _item(db: DbSession, media_id: int) -> MediaItem:
    item = db.get(MediaItem, media_id)
    if item is None:
        raise ApiError(404, "media_not_found", "Không tìm thấy tư liệu (có thể đã bị xoá)")
    return item


@router.patch("/{media_id}")
def patch_media(
    media_id: int, body: MediaPatchBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    item = _item(db, media_id)
    if body.name is not None:
        name = " ".join(unicodedata.normalize("NFC", body.name).split())
        if not name or len(name) > 200:
            raise invalid("Tên từ 1 đến 200 ký tự")
        item.name = name
    if body.folder is not None:
        item.folder = clean_folder(body.folder)
    db.commit()
    return payload(item)


@router.delete("/{media_id}")
def delete_media(
    media_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    item = _item(db, media_id)
    key = item.storage_key
    db.delete(item)
    db.commit()
    storage.delete(key)
    return {"ok": True}


def use_in_scene(db: DbSession, storage: DirectoryStorage, media_id: int, scene_id: int) -> dict:
    """The item becomes the scene's photo or clip, as a copy of its own."""
    from .routes_videos import _attach_clip, _store_photo

    item = _item(db, media_id)
    if not storage.exists(item.storage_key):
        raise ApiError(404, "media_not_found", "File của tư liệu không còn trên máy chủ")
    if item.kind == "photo":
        data = storage.path(item.storage_key).read_bytes()
        return _store_photo(db, storage, scene_id, data, item.storage_key.rsplit(".", 1)[-1], item.source_url or "kho")
    with tempfile.TemporaryDirectory(prefix="reels_media_") as raw:
        copy = storage.copy_to(item.storage_key, Path(raw) / "clip")
        return _attach_clip(db, storage, scene_id, copy)


@router.post("/{media_id}/use")
def use_media(
    media_id: int,
    body: UseBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    return use_in_scene(db, storage, media_id, body.scene_id)


@router.get("/{media_id}/file")
def media_file(
    media_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> FileResponse:
    item = _item(db, media_id)
    if not storage.exists(item.storage_key):
        raise ApiError(404, "file_not_found", "File không còn trên máy chủ")
    extension = item.storage_key.rsplit(".", 1)[-1]
    return FileResponse(
        storage.path(item.storage_key),
        media_type=MEDIA_TYPES.get(extension, "application/octet-stream"),
        headers={"Cache-Control": "private, max-age=86400"},
    )


def thumb_image(storage: DirectoryStorage, item: MediaItem, width: int = THUMB_WIDTH) -> Image.Image:
    """A photo, or a clip's frame at one second (or its middle when shorter), at most `width` wide."""
    path = storage.path(item.storage_key)
    if item.kind == "clip":
        frame = clips.frame_at(path, min(1.0, (item.seconds or 2) / 2))
    else:
        with Image.open(path) as photo:
            frame = photo.convert("RGB")
    frame.thumbnail((width, width * 2))
    return frame


@router.get("/{media_id}/thumb.jpg")
def media_thumb(
    media_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> Response:
    item = _item(db, media_id)
    try:
        frame = thumb_image(storage, item)
    except (OSError, clips.ClipError):
        raise ApiError(404, "file_not_found", "Không lấy được hình xem trước") from None
    buffer = io.BytesIO()
    frame.save(buffer, "JPEG", quality=82)
    return Response(buffer.getvalue(), media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})
