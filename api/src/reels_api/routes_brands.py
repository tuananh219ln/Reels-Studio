"""Brands ("Kênh"): a brand's name, links and logo. Everyone signed in sees every brand (members share videos); only
a brand's owner changes it. See brands.py."""

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from . import brands, remote_media
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
