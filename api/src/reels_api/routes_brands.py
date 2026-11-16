"""Brands ("Kênh"): a brand's name, links and logo. Everyone signed in sees every brand (members share videos); only
a brand's owner changes it. See brands.py."""

import tempfile
from dataclasses import replace
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from . import brands, photo_logo, remote_media
from .db import get_db
from .errors import ApiError
from .models import Brand, Fanpage, Session
from .routes_videos import invalid
from .sessions import current_member
from .storage import DirectoryStorage, get_storage

router = APIRouter(prefix="/api/brands")

LINK_FIELDS = ("tiktok_username", "tiktok_account_id", "youtube_channel_id", "youtube_handle")
LINK_LENGTH = 64


class BrandBody(BaseModel):
    name: str | None = None
    fanpage_id: int | None = None
    tiktok_username: str | None = None
    tiktok_account_id: str | None = None
    youtube_channel_id: str | None = None
    youtube_handle: str | None = None
    logo_default_on: bool | None = None
    # How the logo sits on an article's photos (photo_logo.py); `photo_logo_alt_threshold` null turns the white logo
    # off.
    photo_logo_position: str | None = None
    photo_logo_size: float | None = None
    photo_logo_margin: float | None = None
    photo_logo_opacity: float | None = None
    photo_logo_alt_threshold: float | None = None
    photo_logo_shape: str | None = None
    photo_logo_border: bool | None = None
    photo_logo_border_color: str | None = None
    photo_logo_shadow: bool | None = None


PHOTO_FIELDS = (
    "photo_logo_position",
    "photo_logo_size",
    "photo_logo_margin",
    "photo_logo_opacity",
    "photo_logo_shape",
    "photo_logo_border",
    "photo_logo_border_color",
    "photo_logo_shadow",
)


def _photo_payload(brand: Brand) -> dict:
    return {
        "logo_alt_url": brands.alt_logo_url(brand),
        "photo_logo": {
            "position": brand.photo_logo_position,
            "size": brand.photo_logo_size,
            "margin": brand.photo_logo_margin,
            "opacity": brand.photo_logo_opacity,
            "alt_threshold": brand.photo_logo_alt_threshold,
            "shape": brand.photo_logo_shape,
            "border": brand.photo_logo_border,
            "border_color": brand.photo_logo_border_color,
            "shadow": brand.photo_logo_shadow,
        },
    }


def _payload(db: DbSession, brand: Brand, me: Session) -> dict:
    page = brand.fanpage
    return {
        "id": brand.id,
        "name": brand.name,
        "slug": brand.slug,
        "fanpage": {"id": page.id, "name": page.name, "picture": page.picture_url} if page else None,
        "fanpage_id": brand.fanpage_id,
        "tiktok_username": brand.tiktok_username,
        "tiktok_account_id": brand.tiktok_account_id,
        "youtube_channel_id": brand.youtube_channel_id,
        "youtube_handle": brand.youtube_handle,
        "logo_default_on": brand.logo_default_on,
        "logo_url": brands.logo_url(brand),
        "logo_badge_url": brands.badge_url(brand),
        "logo_version": brand.logo_version,
        **_photo_payload(brand),
        "owner_id": brand.owner_id,
        "owner_name": brand.owner.name,
        "mine": brand.owner_id == me.user_id,
    }


def _clean_name(value: str) -> str:
    name = " ".join(value.split())
    if not name:
        raise invalid("Hãy nhập tên kênh")
    if len(name) > brands.MAX_NAME_LENGTH:
        raise invalid(f"Tên kênh tối đa {brands.MAX_NAME_LENGTH} ký tự")
    return name


def _link(value: str, label: str, strip: str = "") -> str | None:
    text = value.strip().lstrip(strip) if strip else value.strip()
    if len(text) > LINK_LENGTH or any(char.isspace() for char in text):
        raise invalid(f"{label} không hợp lệ")
    return text or None


def _apply(db: DbSession, brand: Brand, me: Session, body: BrandBody) -> None:
    fields = body.model_fields_set
    if "name" in fields and body.name is not None:
        name = _clean_name(body.name)
        taken = db.scalar(select(Brand).where(Brand.slug == brands.slug_of(name), Brand.id != (brand.id or 0)))
        if taken is not None or db.scalar(select(Brand).where(Brand.name == name, Brand.id != (brand.id or 0))):
            raise ApiError(409, "brand_exists", f"Đã có kênh tên “{name}”")
        brand.name, brand.slug = name, brands.slug_of(name)
    if "fanpage_id" in fields:
        if body.fanpage_id is None:
            brand.fanpage_id = None
        else:
            page = db.get(Fanpage, body.fanpage_id)
            if page is None or not page.active:
                raise invalid("Hãy chọn một Fanpage đang dùng")
            if page.owner_id != me.user_id:
                raise ApiError(403, "not_page_owner", f"Chỉ chủ Page “{page.name}” mới gắn Page này vào kênh được")
            if brands.fanpage_taken(db, page.id, brand.id):
                raise ApiError(409, "fanpage_taken", f"Page “{page.name}” đã thuộc một kênh khác")
            brand.fanpage_id = page.id
    for name, label, strip in (
        ("tiktok_username", "TikTok username", "@"),
        ("tiktok_account_id", "Mã tài khoản TikTok", ""),
        ("youtube_channel_id", "Mã kênh YouTube", ""),
        ("youtube_handle", "Tên kênh YouTube", ""),
    ):
        if name in fields:
            value = getattr(body, name)
            setattr(brand, name, _link(value, label, strip) if value is not None else None)
    if "logo_default_on" in fields and body.logo_default_on is not None:
        brand.logo_default_on = body.logo_default_on
    _apply_photo_look(brand, body)


def _apply_photo_look(brand: Brand, body: BrandBody) -> None:
    fields = body.model_fields_set
    look = photo_logo.look_of(brand)
    changes = {
        name.removeprefix("photo_logo_"): getattr(body, name)
        for name in PHOTO_FIELDS
        if name in fields and getattr(body, name) is not None
    }
    if "photo_logo_alt_threshold" in fields:
        changes["alt_threshold"] = body.photo_logo_alt_threshold
    if not changes:
        return
    try:
        look = photo_logo.checked(replace(look, **changes))
    except photo_logo.LogoSettingsError as err:
        raise invalid(str(err)) from None
    brand.photo_logo_position, brand.photo_logo_size = look.position, look.size
    brand.photo_logo_margin, brand.photo_logo_opacity = look.margin, look.opacity
    brand.photo_logo_alt_threshold = look.alt_threshold
    brand.photo_logo_shape, brand.photo_logo_border = look.shape, look.border
    brand.photo_logo_border_color, brand.photo_logo_shadow = look.border_color.upper(), look.shadow


def _commit(db: DbSession) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "brand_exists", "Tên kênh hoặc Page đã được kênh khác dùng") from None


@router.get("")
def list_brands(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> list[dict]:
    return [_payload(db, brand, me) for brand in db.scalars(select(Brand).order_by(Brand.name))]


@router.post("", status_code=201)
def create_brand(body: BrandBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    if not body.name:
        raise invalid("Hãy nhập tên kênh")
    brand = Brand(name="", slug="", owner_id=me.user_id)
    _apply(db, brand, me, body)
    db.add(brand)
    _commit(db)
    return _payload(db, brand, me)


@router.get("/{brand_id}")
def get_brand(brand_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    brand = db.get(Brand, brand_id)
    if brand is None:
        raise brands.not_found()
    return _payload(db, brand, me)


@router.patch("/{brand_id}")
def patch_brand(
    brand_id: int, body: BrandBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    brand = brands.get_owned(db, brand_id, me.user_id)
    _apply(db, brand, me, body)
    _commit(db)
    return _payload(db, brand, me)


@router.delete("/{brand_id}", status_code=204)
def delete_brand(
    brand_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> None:
    brand = brands.get_owned(db, brand_id, me.user_id)
    using = brands.videos_using(db, brand)
    if using:
        raise ApiError(409, "brand_in_use", f"Kênh còn {len(using)} video đang dùng nên không xoá được")
    brands.drop_logo_files(storage, brand)
    brands.clear_alt_logo(storage, brand)
    db.delete(brand)
    db.commit()


def _logo_answer(db: DbSession, brand: Brand) -> dict:
    return {
        "logo_url": brands.logo_url(brand),
        "logo_badge_url": brands.badge_url(brand),
        "logo_version": brand.logo_version,
        # Videos with an MP4 and the logo on that are not posted yet: they need a render with the new logo.
        "videos_outdated": brands.outdated_count(db, brand),
    }


@router.post("/{brand_id}/logo")
def upload_logo(
    brand_id: int,
    file: UploadFile = File(...),
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    brand = brands.get_owned(db, brand_id, me.user_id)
    data = file.file.read(brands.MAX_LOGO_BYTES + 1)  # brands.save_logo refuses a file over the limit with a 400
    brands.save_logo(db, storage, brand, data)
    db.commit()
    return _logo_answer(db, brand)


@router.post("/{brand_id}/logo/from-fanpage")
def logo_from_fanpage(
    brand_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    brand = brands.get_owned(db, brand_id, me.user_id)
    page = brand.fanpage
    if page is None or not page.picture_url:
        raise ApiError(409, "no_page_picture", "Kênh chưa gắn Fanpage hoặc Fanpage chưa có ảnh đại diện")
    with tempfile.TemporaryDirectory(prefix="brand_logo_") as folder:
        try:
            media = remote_media.download(page.picture_url, Path(folder))
        except remote_media.RemoteMediaError as err:
            raise ApiError(409, "page_picture_failed", f"Không lấy được ảnh đại diện Fanpage: {err}") from None
    if media.photo is None:
        raise ApiError(409, "page_picture_failed", "Ảnh đại diện Fanpage không đọc được")
    brands.save_logo(db, storage, brand, media.photo[0])
    db.commit()
    return _logo_answer(db, brand)


@router.delete("/{brand_id}/logo")
def delete_logo(
    brand_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    brand = brands.get_owned(db, brand_id, me.user_id)
    outdated = brands.outdated_count(db, brand)
    brands.clear_logo(storage, brand)
    db.commit()
    return {**_logo_answer(db, brand), "videos_outdated": outdated}


@router.get("/{brand_id}/logo/badge.png")
def badge(
    brand_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> FileResponse:
    brand = db.get(Brand, brand_id)
    if brand is None or not brand.logo_badge_path or not storage.exists(brand.logo_badge_path):
        raise ApiError(404, "no_logo", "Kênh chưa có logo")
    # The address carries the logo's version, so a browser may keep it for good.
    return FileResponse(
        storage.path(brand.logo_badge_path),
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


@router.get("/{brand_id}/logo/original")
def original(
    brand_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> FileResponse:
    brand = db.get(Brand, brand_id)
    if brand is None or not brand.logo_path or not storage.exists(brand.logo_path):
        raise ApiError(404, "no_logo", "Kênh chưa có logo")
    return FileResponse(
        storage.path(brand.logo_path), headers={"Cache-Control": "private, max-age=31536000, immutable"}
    )


# --- The logo on articles' photos ---


@router.post("/{brand_id}/logo-alt")
def upload_alt_logo(
    brand_id: int,
    file: UploadFile = File(...),
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """ "Logo phụ (bản trắng)": used on a dark photo when the brightness threshold is on."""
    brand = brands.get_owned(db, brand_id, me.user_id)
    brands.save_alt_logo(storage, brand, file.file.read(brands.MAX_LOGO_BYTES + 1))
    db.commit()
    return _photo_payload(brand)


@router.delete("/{brand_id}/logo-alt")
def delete_alt_logo(
    brand_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    brand = brands.get_owned(db, brand_id, me.user_id)
    brands.clear_alt_logo(storage, brand)
    db.commit()
    return _photo_payload(brand)


@router.get("/{brand_id}/logo-alt")
def alt_logo(
    brand_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> FileResponse:
    brand = db.get(Brand, brand_id)
    if brand is None or not brand.logo_alt_path or not storage.exists(brand.logo_alt_path):
        raise ApiError(404, "no_logo", "Kênh chưa có logo phụ")
    return FileResponse(
        storage.path(brand.logo_alt_path), headers={"Cache-Control": "private, max-age=31536000, immutable"}
    )


@router.get("/{brand_id}/photo-sample")
def photo_sample(
    brand_id: int,
    ratio: str = "1:1",
    position: str | None = None,
    size: float | None = None,
    margin: float | None = None,
    opacity: float | None = None,
    alt_threshold: float | None = None,
    no_alt: bool = False,
    shape: str | None = None,
    border: bool | None = None,
    border_color: str | None = None,
    shadow: bool | None = None,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> Response:
    """A sample photo of `ratio` (1:1 light, 4:5 soft, 1.91:1 dark) with the logo, drawn exactly as a posted photo is;
    the settings being dragged are passed in the query before they are saved (`no_alt`: the white logo turned
    off)."""
    brand = db.get(Brand, brand_id)
    if brand is None:
        raise brands.not_found()
    if ratio not in photo_logo.SAMPLE_RATIOS:
        raise invalid("Tỉ lệ ảnh mẫu không hợp lệ")
    logo = brands.brand_logo(storage, brand)
    if logo is not None:
        changes = {
            name: value
            for name, value in (
                ("position", position),
                ("size", size),
                ("margin", margin),
                ("opacity", opacity),
                ("shape", shape),
                ("border", border),
                ("border_color", border_color),
                ("shadow", shadow),
            )
            if value is not None
        }
        if alt_threshold is not None or no_alt:
            changes["alt_threshold"] = None if no_alt else alt_threshold
        try:
            logo = replace(logo, look=photo_logo.checked(replace(logo.look, **changes)))
        except photo_logo.LogoSettingsError as err:
            raise invalid(str(err)) from None
    return Response(
        photo_logo.sample(ratio, logo), media_type="image/jpeg", headers={"Cache-Control": "private, max-age=60"}
    )
