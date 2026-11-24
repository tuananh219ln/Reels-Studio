"""The "Tiêu đề động" of a title scene (title_motion.py): build it, and switch between it and the classic title."""

import tempfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession

from . import remote_media, title_motion
from .db import get_db
from .errors import ApiError
from .models import MediaItem, Scene, Session
from .sessions import current_member
from .storage import DirectoryStorage, get_storage
from .uploads import MAX_IMAGE_BYTES, UploadRejected, image_extension, read_limited

router = APIRouter(prefix="/api/title-motion")


class SlotBody(BaseModel):
    from_scene: int | None = None
    label: str | None = Field(default=None, max_length=30)
    focus: list[float] | None = Field(default=None, min_length=2, max_length=2)


class BuildBody(BaseModel):
    layout: Literal["auto", "grid", "ring", "strip", "warn"] = "auto"
    labels: list[str] | None = Field(default=None, min_length=2, max_length=10)
    hidden_label: str | None = Field(default=None, max_length=30)
    count: int | None = Field(default=None, ge=2, le=10)
    write_hook: bool = False
    slots: list[SlotBody] | None = Field(default=None, max_length=10)


class ModeBody(BaseModel):
    mode: Literal["classic", "motion"]


@router.post("/{scene_id}")
def build(
    scene_id: int,
    body: BuildBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """Queues the motion job of the title scene; `warnings` lists banned words of the hook."""
    video, warnings = title_motion.build(
        db,
        storage,
        scene_id,
        me,
        layout=body.layout,
        labels=body.labels,
        hidden_label=body.hidden_label,
        count=body.count,
        write_hook=body.write_hook,
        slots=None if body.slots is None else [slot.model_dump(exclude_none=True) for slot in body.slots],
    )
    return {"video": video, "warnings": warnings}


@router.post("/{scene_id}/mode")
def set_mode(
    scene_id: int,
    body: ModeBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    return title_motion.set_mode(db, storage, scene_id, body.mode)


class LinkBody(BaseModel):
    url: str = Field(max_length=2000)


class LibraryBody(BaseModel):
    media_id: int


def _photo(db: DbSession, storage: DirectoryStorage, scene_id: int, index: int, data: bytes) -> dict:
    try:
        extension = image_extension(data)
    except UploadRejected as err:
        raise ApiError(415, "invalid_image", str(err)) from None
    return title_motion.set_slot_photo(db, storage, scene_id, index, data, extension)


@router.get("/{scene_id}/slots/{index}/photo")
def slot_photo_file(
    scene_id: int,
    index: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> FileResponse:
    """A slot's own photo, for its thumbnail in the list of slots."""
    scene = db.get(Scene, scene_id)
    slots = ((scene.motion or {}).get("title") or {}).get("slots") or [] if scene else []
    key = slots[index].get("image_key") if 0 <= index < len(slots) else None
    if not key or not storage.exists(key):
        raise ApiError(404, "file_not_found", "Ô này chưa có ảnh riêng")
    types = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
    return FileResponse(
        storage.path(key),
        media_type=types.get(key.rsplit(".", 1)[-1], "application/octet-stream"),
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.delete("/{scene_id}/slots/{index}/photo")
def slot_photo_remove(
    scene_id: int,
    index: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """ "Xóa ảnh": the slot goes back to its scene's photo the next time the title is built."""
    return title_motion.remove_slot_photo(db, storage, scene_id, index)


@router.post("/{scene_id}/slots/{index}/photo")
def slot_photo_upload(
    scene_id: int,
    index: int,
    file: UploadFile = File(...),
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """An uploaded photo for one slot; it shows from the next "Dựng lại tiêu đề"."""
    return _photo(
        db, storage, scene_id, index, read_limited(file, MAX_IMAGE_BYTES, "Ảnh quá 15 MB, hãy chọn ảnh nhỏ hơn")
    )


@router.post("/{scene_id}/slots/{index}/photo-link")
def slot_photo_link(
    scene_id: int,
    index: int,
    body: LinkBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """A photo pasted as a link, downloaded here (no row lock is held while the other site answers)."""
    with tempfile.TemporaryDirectory(prefix="reels_slot_") as folder:
        try:
            media = remote_media.download(body.url, Path(folder))
        except remote_media.RemoteMediaError as err:
            raise ApiError(422, "invalid_media", str(err)) from None
        if media.photo is None:
            raise ApiError(422, "not_a_photo", "Link này là video, không phải ảnh")
        return _photo(db, storage, scene_id, index, media.photo[0])


@router.post("/{scene_id}/slots/{index}/photo-library")
def slot_photo_library(
    scene_id: int,
    index: int,
    body: LibraryBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """A photo of the "Kho tư liệu" (copied, so deleting it from the library changes nothing here)."""
    item = db.get(MediaItem, body.media_id)
    if item is None or item.kind != "photo" or not storage.exists(item.storage_key):
        raise ApiError(404, "media_not_found", "Không tìm thấy ảnh trong kho tư liệu")
    return _photo(db, storage, scene_id, index, storage.path(item.storage_key).read_bytes())
