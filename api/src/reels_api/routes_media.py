"""The team's "Kho tư liệu": photos and clips gathered once and used in any scene.

A member drags a whole folder in (the web uploads one file per request, with its folder), or pastes links: a photo's
address (from Google Ảnh, a shop) or a TikTok video, which the api downloads with the same rules as a link pasted
on a scene (remote_media.py: public addresses only, the upload limits). A clip longer than a minute keeps its first
minute. Using an item in a scene copies the file into the video, so deleting it from the library never changes one.

Folders are labels on the items (`media_items.folder`), not rows of their own: moving items, renaming a folder or
clearing it changes only labels, never an item's id or file, so what the MCP assistant or a scene points at by id still
holds. A topic group may link one folder ("Tư liệu" on /knowledge, `knowledge_topics.media_folder`); renaming the
folder takes the link along, clearing it unlinks (docs/decisions/2026-11-11-media-folders.md).

Tags (media_tags.py) say what an item shows, apart from its folder: set on one item or added to and taken from a
chosen batch, filtered on (an item must carry every tag asked) and matched by the search, here and over MCP.
"""

import functools
import io
import re
import secrets
import tempfile
import unicodedata
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel
from sqlalchemy import Text, func, or_, select
from sqlalchemy.orm import Session as DbSession

from . import clips, edit_log, media_tags, remote_media
from .db import get_db
from .errors import ApiError
from .models import KnowledgeTopic, MediaItem, Session
from .ownership import ensure_owner
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
    tags: list[str] = []


class MediaPatchBody(BaseModel):
    name: str | None = None
    folder: str | None = None
    tags: list[str] | None = None  # the item's whole set of tags, cleaned (media_tags.clean_tags)


class UseBody(BaseModel):
    scene_id: int


class MoveBody(BaseModel):
    ids: list[int]
    folder: str = ""  # "" for "Không thư mục"


class FolderBody(BaseModel):
    folder: str


class RenameBody(BaseModel):
    folder: str
    to: str


class TagsBody(BaseModel):
    ids: list[int]
    add: list[str] = []
    remove: list[str] = []


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


def tags_of(raw) -> list[str]:
    """Tags as typed (a list, or one line with commas), cleaned; a tag empty once cleaned is refused."""
    try:
        return media_tags.split_tags(raw) if isinstance(raw, str) or raw is None else media_tags.clean_tags(raw)
    except media_tags.TagError as err:
        raise invalid(str(err)) from None


def tag_list(db: DbSession) -> list[dict]:
    """Every tag in the library with how many items carry it, for suggesting a tag that is there over a new one."""
    tag = func.jsonb_array_elements_text(MediaItem.tags).label("tag")
    rows = db.execute(select(tag, func.count()).group_by("tag").order_by("tag"))
    return [{"tag": name, "count": count} for name, count in rows]


def in_folder(name: str):
    """The items of a folder with its subfolders, as the library's filter shows them."""
    return or_(MediaItem.folder == name, MediaItem.folder.like(f"{like_pattern(name)}/%", "\\"))


def _relabel(value: str, old: str, new: str) -> str | None:
    """`value` with folder `old` (or a subfolder of it) renamed `new`; None when it is not in `old`."""
    if value == old or value.startswith(f"{old}/"):
        return new + value[len(old) :]
    return None


def linked_topics(db: DbSession) -> list[KnowledgeTopic]:
    return list(db.scalars(select(KnowledgeTopic).where(KnowledgeTopic.media_folder.is_not(None))))


def folder_list(db: DbSession) -> list[dict]:
    """Every folder with its count of items, and the group linking it; a linked folder with nothing in it yet too."""
    counts = dict(db.execute(select(MediaItem.folder, func.count()).group_by(MediaItem.folder)).all())
    links = {topic.media_folder: topic for topic in linked_topics(db)}
    names = sorted({name for name in counts if name} | set(links), key=lambda name: (name.casefold(), name))
    return [
        {
            "folder": name,
            "count": counts.get(name, 0),
            "topic_id": links[name].id if name in links else None,
            "topic": links[name].name if name in links else None,
        }
        for name in names
    ]


def _log_link(db: DbSession, topic: KnowledgeTopic, old: str | None, me: Session) -> None:
    changes = {"media_folder": {"old": old, "new": topic.media_folder}}
    edit_log.record(db, edit_log.TOPIC, topic.id, "update", me.user_id, label=topic.name, changes=changes)


def link_folder(db: DbSession, topic: KnowledgeTopic, raw: str | None) -> str | None:
    """The folder a group's "Tư liệu" is to show ("" or None: unlinked); one already another group's is refused."""
    name = clean_folder(raw or "")
    if not name:
        return None
    holder = db.scalar(select(KnowledgeTopic).where(KnowledgeTopic.media_folder == name, KnowledgeTopic.id != topic.id))
    if holder is not None:
        raise ApiError(
            409,
            "folder_linked",
            f"Thư mục “{name}” đã là thư mục tư liệu của nhóm “{holder.name}”, hãy chọn thư mục khác",
        )
    return name


@functools.lru_cache(maxsize=4096)
def _specs(path: str, kind: str) -> tuple[int | None, int | None, int | None]:
    """A stored file's (size in bytes, width, height): a photo's pixels come from its header alone, a clip's size only
    (its length is `seconds`). A file that is gone reads as nothing. Files never change once stored, so this is kept."""
    try:
        size = Path(path).stat().st_size
        if kind != "photo":
            return size, None, None
        with Image.open(path) as photo:
            return size, photo.width, photo.height
    except OSError:
        return None, None, None


def payload(item: MediaItem, storage: DirectoryStorage | None = None) -> dict:
    size, width, height = _specs(str(storage.path(item.storage_key)), item.kind) if storage else (None, None, None)
    return {
        "id": item.id,
        "kind": item.kind,
        "name": item.name,
        "folder": item.folder,
        "source_url": item.source_url,
        "seconds": item.seconds,
        "size_bytes": size,
        "width": width,
        "height": height,
        "tags": list(item.tags or []),
        "file_url": f"/api/media/{item.id}/file",
        "thumb_url": f"/api/media/{item.id}/thumb.jpg",
        "created_by": item.created_by.name,
        "created_by_id": item.created_by_id,
        "created_at": item.created_at.isoformat(),
    }


def _new_key(extension: str) -> str:
    return f"media/{secrets.token_hex(8)}.{extension}"


def _add(
    db: DbSession, storage: DirectoryStorage, me: Session, name: str, folder: str, source: str | None, photo=None,
    clip_path: Path | None = None, workdir: Path | None = None, tags: list[str] | None = None,
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
    item.tags = tags or []
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
    storage: DirectoryStorage = Depends(get_storage),
    tags: str | None = None,
) -> dict:
    """The library newest first (one folder, with its subfolders, when named; only items carrying every tag in
    `tags`, "xoay-co,sofa"), with every folder and every tag and their counts. The search matches names, folders and
    tags ("phòng ngủ" finds `phong-ngu`)."""
    query = select(MediaItem).order_by(MediaItem.id.desc()).limit(MAX_LIST)
    wanted = tags_of(tags)
    if wanted:
        query = query.where(MediaItem.tags.contains(wanted))
    if folder:
        query = query.where(in_folder(clean_folder(folder)))
    if kind in ("photo", "clip"):
        query = query.where(MediaItem.kind == kind)
    if q and q.strip():
        pattern = f"%{like_pattern(q.strip())}%"
        matches = [MediaItem.name.ilike(pattern, escape="\\"), MediaItem.folder.ilike(pattern, "\\")]
        as_tag = re.sub(r"[^a-z0-9]+", "-", media_tags.plain(q)).strip("-")
        if as_tag:
            matches.append(MediaItem.tags.cast(Text).like(f"%{like_pattern(as_tag)}%", "\\"))
        query = query.where(or_(*matches))
    return {
        "items": [payload(item, storage) for item in db.scalars(query)],
        # The whole library's count, whatever the filters: the page's "N tư liệu".
        "total": db.scalar(select(func.count()).select_from(MediaItem)),
        "folders": folder_list(db),
        "tags": tag_list(db),
    }


@router.post("/move")
def move_media(body: MoveBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Chuyển thư mục" for one item or a chosen batch: only the label changes, never the id or the file."""
    ids = list(dict.fromkeys(body.ids))
    if not ids:
        raise invalid("Hãy chọn ít nhất một tư liệu")
    if len(ids) > MAX_LIST:
        raise invalid(f"Mỗi lần chuyển tối đa {MAX_LIST} tư liệu")
    where = clean_folder(body.folder)
    items = db.scalars(select(MediaItem).where(MediaItem.id.in_(ids)).with_for_update()).all()
    if len(items) != len(ids):
        raise ApiError(404, "media_not_found", "Có tư liệu không còn trong kho (có thể đã bị xoá), hãy tải lại trang")
    for item in items:
        item.folder = where
    db.commit()
    return {"moved": len(items), "folders": folder_list(db)}


@router.post("/tags")
def tag_media(body: TagsBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Thêm thẻ" and "Gỡ thẻ" on the chosen items; an item already so tagged is left as it is."""
    ids = list(dict.fromkeys(body.ids))
    add, remove = tags_of(body.add), tags_of(body.remove)
    if not ids:
        raise invalid("Hãy chọn ít nhất một tư liệu")
    if not add and not remove:
        raise invalid("Hãy chọn ít nhất một thẻ")
    if len(ids) > MAX_LIST:
        raise invalid(f"Mỗi lần sửa thẻ tối đa {MAX_LIST} tư liệu")
    items = db.scalars(select(MediaItem).where(MediaItem.id.in_(ids)).with_for_update()).all()
    if len(items) != len(ids):
        raise ApiError(404, "media_not_found", "Có tư liệu không còn trong kho (có thể đã bị xoá), hãy tải lại trang")
    changed = 0
    for item in items:
        before = list(item.tags or [])
        after = [tag for tag in dict.fromkeys([*before, *add]) if tag not in remove]
        if len(after) > media_tags.MAX_TAGS:
            raise invalid(f"“{item.name}” sẽ có quá {media_tags.MAX_TAGS} thẻ")
        if after != before:
            item.tags, changed = after, changed + 1
    db.commit()
    return {"changed": changed, "tags": tag_list(db)}


@router.post("/folders/rename")
def rename_folder(body: RenameBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """Every item of the folder and its subfolders takes the new name (merging into a folder of that name), and the
    group linking it follows; refused when two groups would end up on one folder."""
    old, new = clean_folder(body.folder), clean_folder(body.to)
    if not old:
        raise invalid("Hãy chọn thư mục cần đổi tên")
    if not new:
        raise invalid("Hãy nhập tên mới cho thư mục")
    items = db.scalars(select(MediaItem).where(in_folder(old)).with_for_update()).all()
    topics = linked_topics(db)
    moving = {topic.id: _relabel(topic.media_folder, old, new) for topic in topics}
    moving = {topic_id: name for topic_id, name in moving.items() if name is not None}
    if not items and not moving:
        raise ApiError(404, "folder_not_found", f"Không tìm thấy thư mục “{old}” (có thể vừa được đổi tên)")
    if old == new:
        return {"moved": 0, "folders": folder_list(db)}
    renamed = {item.id: _relabel(item.folder, old, new) for item in items}
    if any(len(name) > MAX_FOLDER for name in [*renamed.values(), *moving.values()]):
        raise invalid(f"Tên thư mục dài quá {MAX_FOLDER} ký tự")
    holders = {topic.media_folder: topic for topic in topics if topic.id not in moving}
    for topic in topics:
        held = holders.get(moving.get(topic.id, ""))
        if held is not None:
            raise ApiError(
                409,
                "folder_linked",
                f"Thư mục “{held.media_folder}” đã là thư mục tư liệu của nhóm “{held.name}”, còn “{topic.media_folder}”"
                f" thuộc nhóm “{topic.name}”: hãy bỏ liên kết ở một nhóm trước khi đổi tên",
            )
    for item in items:
        item.folder = renamed[item.id]
    changed = [(topic, topic.media_folder) for topic in topics if topic.id in moving]
    # Unlinked first, so a rename into its own subfolder never meets the unique folder on the way.
    for topic, _ in changed:
        topic.media_folder = None
    db.flush()
    for topic, before in changed:
        topic.media_folder = moving[topic.id]
        _log_link(db, topic, before, me)
    db.commit()
    return {"moved": len(items), "folders": folder_list(db)}


@router.post("/folders/clear")
def clear_folder(body: FolderBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Xoá thư mục": its items and its subfolders' go to "Không thư mục" (none is deleted), and a group linking it
    or a subfolder of it is unlinked."""
    name = clean_folder(body.folder)
    if not name:
        raise invalid("Hãy chọn thư mục cần xoá")
    items = db.scalars(select(MediaItem).where(in_folder(name)).with_for_update()).all()
    topics = [topic for topic in linked_topics(db) if _relabel(topic.media_folder, name, name) is not None]
    if not items and not topics:
        raise ApiError(404, "folder_not_found", f"Không tìm thấy thư mục “{name}” (có thể vừa được xoá)")
    for item in items:
        item.folder = ""
    for topic in topics:
        before, topic.media_folder = topic.media_folder, None
        _log_link(db, topic, before, me)
    db.commit()
    return {"cleared": len(items), "unlinked": [topic.name for topic in topics], "folders": folder_list(db)}


@router.post("", status_code=201)
def upload_media(
    file: UploadFile = File(...),
    folder: str = Form(default=""),
    tags: str = Form(default=""),  # "xoay-co, sofa"
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """One file of a dragged folder or a picked set: a photo (jpg, png, webp) or a clip (mp4, mov, webm)."""
    # The folder a dragged file came with is the path before its name ("Nồi chiên/cảnh 1/a.mp4").
    path = clean_folder(f"{folder}/{file.filename or ''}")
    where, _, filename = path.rpartition("/")
    name = file_label(filename, "Không tên")
    chosen = tags_of(tags)
    head = file.file.read(16)
    file.file.seek(0)
    if clips.looks_like_clip(head):
        from .routes_videos import _spool_clip

        with tempfile.TemporaryDirectory(prefix="reels_media_") as raw:
            spooled = Path(raw) / "clip"
            _spool_clip(file, spooled)
            item = _add(db, storage, me, name, where, None, clip_path=spooled, workdir=Path(raw), tags=chosen)
    else:
        data = read_limited(file, MAX_IMAGE_BYTES, "Ảnh quá 15 MB, hãy chọn ảnh nhỏ hơn")
        try:
            photo = (data, image_extension(data))
        except UploadRejected:
            raise ApiError(
                415, "invalid_media", f"“{name}” không phải ảnh (jpg, png, webp) hay video (mp4, mov, webm)"
            ) from None
        item = _add(db, storage, me, name, where, None, photo=photo, tags=chosen)
    db.commit()
    return payload(item)


def add_links(
    db: DbSession, storage: DirectoryStorage, me: Session, urls: list[str], folder: str, tags: list[str] | None = None
) -> dict:
    """Download each link into the library; a link that fails is reported and the others still come in."""
    links = [url.strip() for url in urls if url and url.strip()]
    if not links:
        raise invalid("Hãy dán ít nhất một link")
    if len(links) > MAX_LINKS:
        raise invalid(f"Mỗi lần thêm tối đa {MAX_LINKS} link")
    where = clean_folder(folder)
    chosen = tags_of(tags or [])
    added, failed = [], []
    for url in links:
        with tempfile.TemporaryDirectory(prefix="reels_media_") as raw:
            try:
                media = remote_media.download(url, Path(raw))
                name = file_label(Path(url.split("?")[0]).name, "Từ link")
                if media.photo is not None:
                    item = _add(db, storage, me, name, where, url, photo=media.photo, tags=chosen)
                else:
                    item = _add(db, storage, me, name, where, url, clip_path=media.clip, workdir=Path(raw), tags=chosen)
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
    return add_links(db, storage, me, body.urls, body.folder, body.tags)


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
    if body.tags is not None:
        item.tags = tags_of(body.tags)
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
    ensure_owner(item.created_by_id, me.user_id, "tư liệu này")
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
