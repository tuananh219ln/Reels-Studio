"""Brands ("Kênh"): one logo each, laid on the MP4 at render, shared by the brand's Facebook Page, TikTok account and
YouTube channel (docs/decisions/2026-11-13-brand-logo.md; which brand a new video starts on:
docs/decisions/2026-11-20-brand-default.md, which replaces the single-brand fallback of the first).

A video keeps its brand and the logo switch in `video.options` as `brand_id` and `logo_enabled`, outside
`video_options.DEFAULTS` (they are no member's default look). While the logo is on, the brand's `logo_version` is in
the MP4's fingerprint, so changing the brand, the switch or the logo marks the MP4 outdated like any other edit.
"""

import hashlib
import io
import re
import secrets
import unicodedata
from pathlib import Path

from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import object_session

from reels_render.layout import FRAME_HEIGHT, FRAME_WIDTH, LOGO_MAX_SIZE, LOGO_MIN_SIZE
from reels_render.logo import MIN_SOURCE_SIDE, make_badge

from . import photo_logo
from .errors import ApiError
from .models import Brand, Fanpage, Publication, Video
from .storage import DirectoryStorage
from .uploads import UploadRejected, image_extension

MAX_LOGO_BYTES = 5 * 1024 * 1024
MAX_NAME_LENGTH = 120
LOGO_ERRORS = {
    "brand_not_found": "Không tìm thấy kênh",
}


def slug_of(name: str) -> str:
    plain = unicodedata.normalize("NFD", name.replace("đ", "d").replace("Đ", "D"))
    plain = "".join(char for char in plain if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")[:120] or "kenh"


def not_found() -> ApiError:
    return ApiError(404, "brand_not_found", LOGO_ERRORS["brand_not_found"])


def get_owned(db: DbSession, brand_id: int, user_id: int) -> Brand:
    """A brand its owner may change; anyone may read one (the team shares videos), only the owner edits."""
    brand = db.get(Brand, brand_id)
    if brand is None:
        raise not_found()
    if brand.owner_id != user_id:
        raise ApiError(
            403, "not_brand_owner", f"Chỉ chủ kênh “{brand.name}” ({brand.owner.name}) mới sửa được kênh này"
        )
    return brand


def badge_url(brand: Brand) -> str | None:
    if not brand.logo_badge_path:
        return None
    return f"/api/brands/{brand.id}/logo/badge.png?v={brand.logo_version}"


def logo_url(brand: Brand) -> str | None:
    if not brand.logo_path:
        return None
    return f"/api/brands/{brand.id}/logo/original?v={brand.logo_version}"


# --- Logo file ---


def _checked_logo(data: bytes) -> str:
    """The picture's extension, or a 400 with the reason: PNG, JPG or WebP, at most 5 MB, the shorter side at least
    256 px."""
    if len(data) > MAX_LOGO_BYTES:
        raise ApiError(400, "logo_too_large", "Logo tối đa 5 MB")
    try:
        extension = image_extension(data)
    except UploadRejected as err:
        raise ApiError(400, "logo_invalid", str(err)) from None
    with Image.open(io.BytesIO(data)) as image:
        if min(image.size) < MIN_SOURCE_SIDE:
            raise ApiError(
                400,
                "logo_too_small",
                f"Logo quá nhỏ: cạnh ngắn phải từ {MIN_SOURCE_SIDE}px (ảnh này {min(image.size)}px)",
            )
    return extension


def save_logo(db: DbSession, storage: DirectoryStorage, brand: Brand, data: bytes) -> None:
    """Checks the picture (`_checked_logo`), keeps the original, makes the badge and bumps `logo_version`."""
    extension = _checked_logo(data)
    tag = secrets.token_hex(6)
    original, badge = f"brands/{brand.id}/logo-{tag}.{extension}", f"brands/{brand.id}/badge-{tag}.png"
    storage.save_bytes(original, data)
    try:
        make_badge(storage.path(original), _badge_target(storage, badge))
    except Exception:
        storage.delete(original)
        raise
    drop_logo_files(storage, brand)
    brand.logo_path, brand.logo_badge_path = original, badge
    brand.logo_version = hashlib.sha256(data).hexdigest()[:6]


def _badge_target(storage: DirectoryStorage, key: str) -> Path:
    target = storage.path(key)
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def drop_logo_files(storage: DirectoryStorage, brand: Brand) -> None:
    """The logo and its badge; the white logo goes only with the brand (`clear_alt_logo`)."""
    storage.delete(brand.logo_path)
    storage.delete(brand.logo_badge_path)


def clear_logo(storage: DirectoryStorage, brand: Brand) -> None:
    drop_logo_files(storage, brand)
    brand.logo_path = brand.logo_badge_path = brand.logo_version = None


# --- The logo on articles' photos (photo_logo.py) ---


def save_alt_logo(storage: DirectoryStorage, brand: Brand, data: bytes) -> None:
    """The white logo used on dark photos; the same checks as the logo, no badge (videos never use it)."""
    extension = _checked_logo(data)
    key = f"brands/{brand.id}/logo-alt-{secrets.token_hex(6)}.{extension}"
    storage.save_bytes(key, data)
    storage.delete(brand.logo_alt_path)
    brand.logo_alt_path, brand.logo_alt_version = key, hashlib.sha256(data).hexdigest()[:6]


def clear_alt_logo(storage: DirectoryStorage, brand: Brand) -> None:
    storage.delete(brand.logo_alt_path)
    brand.logo_alt_path = brand.logo_alt_version = None


def alt_logo_url(brand: Brand) -> str | None:
    if not brand.logo_alt_path:
        return None
    return f"/api/brands/{brand.id}/logo-alt?v={brand.logo_alt_version}"


def brand_logo(storage: DirectoryStorage, brand: Brand | None) -> photo_logo.BrandLogo | None:
    """The brand's logo files and photo settings, or None when it has no logo (or its file is gone)."""
    if brand is None or not brand.logo_path or not storage.exists(brand.logo_path):
        return None
    alt = brand.logo_alt_path if brand.logo_alt_path and storage.exists(brand.logo_alt_path) else None
    return photo_logo.BrandLogo(
        storage.path(brand.logo_path), storage.path(alt) if alt else None, photo_logo.look_of(brand)
    )


def page_logo(db: DbSession, storage: DirectoryStorage, fanpage_id: int | None) -> photo_logo.BrandLogo | None:
    """The logo a photo posted to this Page gets: its brand's, or None."""
    if fanpage_id is None:
        return None
    return brand_logo(storage, db.scalar(select(Brand).where(Brand.fanpage_id == fanpage_id)))


# --- Videos ---


def options_of(video: Video) -> tuple[int | None, bool | None]:
    options = video.options or {}
    return options.get("brand_id"), options.get("logo_enabled")


def brand_of(db: DbSession, video: Video) -> Brand | None:
    brand_id, _ = options_of(video)
    return db.get(Brand, brand_id) if brand_id else None


def logo_on(video: Video, brand: Brand | None) -> bool:
    """The logo is laid on the MP4: a brand with a logo, and the switch on (the brand's default until it is set)."""
    if brand is None or not brand.logo_badge_path:
        return False
    _, enabled = options_of(video)
    return brand.logo_default_on if enabled is None else bool(enabled)


def logo_signature(video: Video) -> list | None:
    """What the logo adds to the MP4's fingerprint; None while there is none, so MP4s rendered before stay current. Its
    own place and size join only when set."""
    db = object_session(video)
    brand = brand_of(db, video) if db is not None else None
    if brand is None or not logo_on(video, brand):
        return None
    own = [(video.options or {}).get(name) for name in LOGO_PLACE]
    return ["logo", brand.id, brand.logo_version, *(["at", *own] if any(own) else [])]


def badge_path(db: DbSession, storage: DirectoryStorage, video: Video) -> Path | None:
    """The brand's badge file for the render, or None when no logo is wanted."""
    brand = brand_of(db, video)
    if not logo_on(video, brand):
        return None
    if not storage.exists(brand.logo_badge_path):
        raise ApiError(409, "logo_missing", f"Không thấy file logo của kênh “{brand.name}”, hãy tải logo lên lại")
    return storage.path(brand.logo_badge_path)


def default_for(db: DbSession, user_id: int, knowledge_topic_id: int | None) -> Brand | None:
    """The channel a member's new video starts on, so they need not pick it on every video: among their own brands
    with a logo, the one whose active Page is in the video's topic group; None otherwise — a lone brand is never
    the default for a group its Page is not in, so a logo stays only on its own Page's videos. The logo switch is
    left unset, so the brand's "Video của Page tự gắn logo" (`logo_default_on`) decides it."""
    if knowledge_topic_id is None:
        return None
    mine = db.scalars(
        select(Brand).where(Brand.owner_id == user_id, Brand.logo_badge_path.is_not(None)).order_by(Brand.id)
    )
    for brand in mine:
        page = brand.fanpage
        if page is not None and page.active and page.knowledge_topic_id == knowledge_topic_id:
            return brand
    return None


def has_posts(db: DbSession, video_id: int) -> bool:
    return (
        db.scalar(
            select(func.count())
            .select_from(Publication)
            .where(
                Publication.video_id == video_id,
                Publication.status.in_(("pending", "scheduled", "private", "published")),
            )
        )
        > 0
    )


# The logo's own place on a video (its ring's top-left corner, [x, y]) and diameter; unset: the layout profile's.
LOGO_PLACE = ("logo_position", "logo_size")


def _save_logo_place(video: Video, options: dict) -> None:
    """Saves the logo place and size given (null: back to the profile's). The render keeps them inside the profile's
    edges (reels_render.layout.logo_box), so a later change of profile never leaves the logo outside."""
    stored = dict(video.options or {})
    for name in LOGO_PLACE:
        if name not in options:
            continue
        value = options[name]
        if value is None:
            stored.pop(name, None)
            continue
        if name == "logo_position":
            if (
                not isinstance(value, list)
                or len(value) != 2
                or not all(type(number) is int for number in value)
                or not (0 <= value[0] <= FRAME_WIDTH and 0 <= value[1] <= FRAME_HEIGHT)
            ):
                raise ApiError(400, "invalid", f"Vị trí logo phải là [x, y] trong khung {FRAME_WIDTH}×{FRAME_HEIGHT}")
        elif type(value) is not int or not LOGO_MIN_SIZE <= value <= LOGO_MAX_SIZE:
            raise ApiError(400, "invalid", f"Cỡ logo phải từ {LOGO_MIN_SIZE} đến {LOGO_MAX_SIZE} px")
        stored[name] = value
    video.options = stored


def apply_video_options(db: DbSession, video: Video, user_id: int, options: dict) -> dict:
    """Takes the channel and logo fields (`brand_id`, `logo_enabled`, LOGO_PLACE) out of a video's PATCH options, checks
    and saves them on the video, and returns the rest for `video_options.clean`. Raises ApiError (403 not a brand of the
    member, 400 `brand_has_no_logo`, 409 `video_already_posted`)."""
    if any(name in options for name in LOGO_PLACE):
        _save_logo_place(video, options)
        options = {name: value for name, value in options.items() if name not in LOGO_PLACE}
    rest = {name: value for name, value in options.items() if name not in ("brand_id", "logo_enabled")}
    if len(rest) == len(options):
        return rest
    current_id, current_on = options_of(video)
    brand_id = options.get("brand_id", current_id)
    enabled = options.get("logo_enabled", current_on)
    if brand_id is not None and (isinstance(brand_id, bool) or not isinstance(brand_id, int)):
        raise ApiError(400, "invalid", "Kênh không hợp lệ")
    if enabled is not None and not isinstance(enabled, bool):
        raise ApiError(400, "invalid", "“Gắn logo” chỉ nhận bật hoặc tắt")
    brand = None
    if brand_id is not None:
        brand = db.get(Brand, brand_id)
        if brand is None or (brand_id != current_id and brand.owner_id != user_id):
            raise ApiError(403, "not_brand_owner", "Bạn không có quyền dùng kênh này")
    if brand_id != current_id and has_posts(db, video.id):
        raise ApiError(
            409,
            "video_already_posted",
            "Video đã đăng nên không đổi kênh được: hãy tạo bản cho kênh khác",
        )
    if enabled and (brand is None or not brand.logo_badge_path):
        raise ApiError(400, "brand_has_no_logo", "Kênh chưa có logo: hãy tải logo lên ở Quản lý kênh")
    if brand_id != current_id and "logo_enabled" not in options:
        enabled = None  # a new brand: its own default switch applies
    stored = dict(video.options or {})
    stored["brand_id"] = brand_id
    if enabled is None:
        stored.pop("logo_enabled", None)
    else:
        stored["logo_enabled"] = enabled
    video.options = stored
    return rest


def payload_of(db: DbSession, video: Video) -> dict:
    """What a video's page shows of its channel and logo."""
    brand = brand_of(db, video)
    return {
        "brand": {"id": brand.id, "name": brand.name, "logo_badge_url": badge_url(brand)} if brand else None,
        "logo_enabled": logo_on(video, brand),
    }


def videos_using(db: DbSession, brand: Brand) -> list[Video]:
    return list(db.scalars(select(Video).where(Video.options["brand_id"].as_integer() == brand.id)))


def outdated_count(db: DbSession, brand: Brand) -> int:
    """Videos with the logo on, an MP4 and no post yet: they need a new render once the logo changes."""
    return sum(
        1
        for video in videos_using(db, brand)
        if video.mp4_key and logo_on(video, brand) and not has_posts(db, video.id)
    )


def fanpage_taken(db: DbSession, fanpage_id: int, brand_id: int | None) -> bool:
    other = db.scalar(select(Brand).where(Brand.fanpage_id == fanpage_id))
    return other is not None and other.id != brand_id


def mismatch(db: DbSession, video: Video, fanpage: Fanpage) -> str | None:
    """Why a video with the logo on may not go to this Page (409 `brand_mismatch`); None when it may. Without the
    logo a video goes anywhere, as before."""
    brand = brand_of(db, video)
    if not logo_on(video, brand) or brand.fanpage_id == fanpage.id:
        return None
    return (
        f"Video mang logo “{brand.name}” nên chỉ đăng được lên Page của kênh đó: "
        "hãy tạo bản cho kênh khác, hoặc tắt “Gắn logo” rồi render lại"
    )
