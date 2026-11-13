"""Brands ("Kênh"): one logo each, laid on the MP4 at render, shared by the brand's Facebook Page, TikTok account and
YouTube channel (docs/decisions/2026-11-13-brand-logo.md).

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

from reels_render.logo import MIN_SOURCE_SIDE, make_badge

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


def save_logo(db: DbSession, storage: DirectoryStorage, brand: Brand, data: bytes) -> None:
    """Checks the picture, keeps the original, makes the badge and bumps `logo_version`. Refused with 400 and a
    reason: PNG, JPG or WebP, at most 5 MB, the shorter side at least 256 px."""
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
    storage.delete(brand.logo_path)
    storage.delete(brand.logo_badge_path)


def clear_logo(storage: DirectoryStorage, brand: Brand) -> None:
    drop_logo_files(storage, brand)
    brand.logo_path = brand.logo_badge_path = brand.logo_version = None


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
    """What the logo adds to the MP4's fingerprint; None while there is none, so MP4s rendered before stay current."""
    db = object_session(video)
    brand = brand_of(db, video) if db is not None else None
    return ["logo", brand.id, brand.logo_version] if brand is not None and logo_on(video, brand) else None


def badge_path(db: DbSession, storage: DirectoryStorage, video: Video) -> Path | None:
    """The brand's badge file for the render, or None when no logo is wanted."""
    brand = brand_of(db, video)
    if not logo_on(video, brand):
        return None
    if not storage.exists(brand.logo_badge_path):
        raise ApiError(409, "logo_missing", f"Không thấy file logo của kênh “{brand.name}”, hãy tải logo lên lại")
    return storage.path(brand.logo_badge_path)


def has_posts(db: DbSession, video_id: int) -> bool:
    return (
        db.scalar(
            select(func.count())
            .select_from(Publication)
            .where(
                Publication.video_id == video_id,
                Publication.status.in_(("pending", "scheduled", "published")),
            )
        )
        > 0
    )


def apply_video_options(db: DbSession, video: Video, user_id: int, options: dict) -> dict:
    """Takes `brand_id` and `logo_enabled` out of a video's PATCH options, checks and saves them on the video, and
    returns the rest for `video_options.clean`. Raises ApiError (403 not a brand of the member, 400
    `brand_has_no_logo`, 409 `video_already_posted`)."""
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
