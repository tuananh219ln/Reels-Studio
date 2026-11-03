"""Affiliate Shopee: the team's product list, entered by hand, ranked by expected commission and approved by a
member, and the products attached to each posted reel."""

import csv
import io
import unicodedata
from datetime import UTC, datetime, timedelta, timezone
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import case, delete, func, or_, select
from sqlalchemy.orm import Session as DbSession

from . import affiliate, facebook, knowledge
from .db import get_db
from .errors import ApiError
from .models import AffiliateProduct, KnowledgeTopic, Publication, Session, Video, VideoAffiliateProduct
from .routes_music import like_pattern
from .routes_videos import invalid
from .sessions import current_member, now
from .videos import is_published, published_publication, split_scenes, title_of

router = APIRouter(prefix="/api/affiliate-products")

SHOP_TYPES = {
    "mall": "Shopee Mall",
    "preferred_plus": "Shop Yêu Thích+",
    "preferred": "Shop Yêu Thích",
    "other": "Shop thường",
}

MAX_NAME_LENGTH = 300
MAX_SHOP_NAME_LENGTH = 200
MAX_URL_LENGTH = 2000
MAX_COUNT = 1_000_000_000  # keeps price and sold inside the database's integer
VIETNAM_TIME = timezone(timedelta(hours=7))


class ProductBody(BaseModel):
    knowledge_topic_id: int
    name: str
    url: str
    shop_name: str
    shop_type: str
    rating: float
    sold: int
    price: int
    commission_rate: float


class VideoProductsBody(BaseModel):
    product_ids: list[int]


def _text(value: str, label: str, limit: int) -> str:
    value = " ".join(unicodedata.normalize("NFC", value).split())
    if not value:
        raise invalid(f"{label} không được để trống")
    if len(value) > limit:
        raise invalid(f"{label} dài quá {limit} ký tự")
    return value


def _url(value: str) -> str:
    value = value.strip()
    if len(value) > MAX_URL_LENGTH:
        raise invalid(f"Link dài quá {MAX_URL_LENGTH} ký tự")
    # The page renders it as a link, so nothing but a web address may get through.
    try:
        parts = urlsplit(value)
    except ValueError:
        raise invalid("Link phải là địa chỉ web đầy đủ, bắt đầu bằng https://") from None
    if parts.scheme not in ("http", "https") or not parts.netloc or any(char.isspace() for char in value):
        raise invalid("Link phải là địa chỉ web đầy đủ, bắt đầu bằng https://")
    return value


def _fields(db: DbSession, body: ProductBody) -> dict:
    if db.get(KnowledgeTopic, body.knowledge_topic_id) is None:
        raise invalid("Nhóm chủ đề không còn tồn tại")
    if body.shop_type not in SHOP_TYPES:
        raise invalid("Loại shop không có trong danh sách")
    if not 0 <= body.rating <= 5:
        raise invalid("Số sao phải từ 0 đến 5")
    if not 0 <= body.commission_rate <= 100:
        raise invalid("Hoa hồng phải từ 0 đến 100%")
    if not 0 < body.price <= MAX_COUNT:
        raise invalid("Giá phải lớn hơn 0 và không quá 1 tỷ đồng")
    if not 0 <= body.sold <= MAX_COUNT:
        raise invalid("Lượt bán không hợp lệ")
    return {
        "knowledge_topic_id": body.knowledge_topic_id,
        "name": _text(body.name, "Tên sản phẩm", MAX_NAME_LENGTH),
        "url": _url(body.url),
        "shop_name": _text(body.shop_name, "Tên shop", MAX_SHOP_NAME_LENGTH),
        "shop_type": body.shop_type,
        "rating": body.rating,
        "sold": body.sold,
        "price": body.price,
        "commission_rate": body.commission_rate,
    }


def _expected_commission(product: AffiliateProduct) -> int:
    return round(product.price * product.commission_rate / 100)


def _payload(product: AffiliateProduct) -> dict:
    return {
        "id": product.id,
        "knowledge_topic_id": product.knowledge_topic_id,
        "topic": product.topic.name,
        "name": product.name,
        "url": product.url,
        "shop_name": product.shop_name,
        "shop_type": product.shop_type,
        "shop_type_label": SHOP_TYPES[product.shop_type],
        "rating": product.rating,
        "sold": product.sold,
        "price": product.price,
        "commission_rate": product.commission_rate,
        "expected_commission": _expected_commission(product),
        "status": product.status,
        "checked_at": product.checked_at.isoformat() if product.checked_at else None,
        "checked_by": product.checked_by.name if product.checked_by else None,
        "problems": affiliate.problems(product),
    }


def _get(db: DbSession, product_id: int) -> AffiliateProduct:
    product = db.get(AffiliateProduct, product_id)
    if product is None:
        raise ApiError(404, "product_not_found", "Không tìm thấy sản phẩm (có thể đã bị xóa)")
    return product


def _clear_approval(product: AffiliateProduct) -> None:
    product.status, product.checked_at, product.checked_by_id = "draft", None, None


def _ranked(db: DbSession, topic_id: int | None, status: str | None, q: str | None) -> list[AffiliateProduct]:
    query = select(AffiliateProduct).order_by(
        # Rounded like the amount on the page: two products showing the same money must reach the tie-break.
        func.round(AffiliateProduct.price * AffiliateProduct.commission_rate / 100).desc(),
        case((AffiliateProduct.shop_type == "mall", 0), else_=1),
        AffiliateProduct.sold.desc(),
        AffiliateProduct.id.desc(),
    )
    if topic_id is not None:
        query = query.where(AffiliateProduct.knowledge_topic_id == topic_id)
    if status:
        query = query.where(AffiliateProduct.status == status)
    if q and q.strip():
        pattern = f"%{like_pattern(q)}%"
        query = query.where(
            or_(
                AffiliateProduct.name.ilike(pattern, escape="\\"),
                AffiliateProduct.shop_name.ilike(pattern, escape="\\"),
            )
        )
    return list(db.scalars(query))


def _csv_cell(value: str) -> str:
    # Spreadsheets run a cell starting with one of these as a formula, and names are copied from public listings.
    return f"'{value}" if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def _live_at(post: Publication) -> datetime:
    # The publish job stamps published_at when the upload ends, which for a scheduled reel is before it goes live.
    return post.scheduled_at or post.published_at


def _video_payload(db: DbSession, video: Video, post: Publication) -> dict:
    title, _ = split_scenes(db, video)
    products = db.scalars(
        select(AffiliateProduct)
        .join(VideoAffiliateProduct)
        .where(VideoAffiliateProduct.video_id == video.id)
        .order_by(AffiliateProduct.id)
    )
    return {
        "id": video.id,
        "title": title_of(video, title) or video.topic,
        "reel_url": facebook.reel_url(post.remote_id) if post.remote_id else None,
        "published_at": _live_at(post).isoformat(),
        "suggestions": video.affiliates,
        "pinned_comment": video.pinned_comment,
        "products": [
            {
                "id": product.id,
                "name": product.name,
                "url": product.url,
                "status": product.status,
                "problems": affiliate.problems(product),
            }
            for product in products
        ],
    }


@router.get("/videos")
def list_videos(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(Video, Publication).join(Publication).where(Publication.platform == "facebook").order_by(Publication.id)
    )
    # A video posted again has one comment to pin per reel in time, so it shows once, with its newest live post.
    latest = {video.id: (video, post) for video, post in rows if is_published(post)}
    posted = sorted(latest.values(), key=lambda row: _live_at(row[1]), reverse=True)
    return [_video_payload(db, video, post) for video, post in posted]


@router.put("/videos/{video_id}")
def set_video_products(
    video_id: int, body: VideoProductsBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """The products whose links go in the video's comment. Set on the video page before posting, so the first comment
    already holds them, or on /affiliate afterwards; a comment the worker already wrote is then edited to match."""
    video = db.get(Video, video_id)
    if video is None:
        raise ApiError(404, "video_not_found", "Không tìm thấy video")
    chosen = set(body.product_ids)
    attached = set(
        db.scalars(select(VideoAffiliateProduct.product_id).where(VideoAffiliateProduct.video_id == video_id))
    )
    products = list(db.scalars(select(AffiliateProduct).where(AffiliateProduct.id.in_(chosen))))
    if len(products) != len(chosen):
        raise ApiError(404, "product_not_found", "Không tìm thấy sản phẩm (có thể đã bị xóa)")
    # A product that stopped qualifying stays until a member removes it, so saving another change is not refused.
    if any(not affiliate.usable(product) and product.id not in attached for product in products):
        raise ApiError(409, "product_not_approved", "Chỉ gắn được sản phẩm đã duyệt và còn đạt tiêu chí")
    db.execute(
        delete(VideoAffiliateProduct).where(
            VideoAffiliateProduct.video_id == video_id, VideoAffiliateProduct.product_id.not_in(chosen)
        )
    )
    db.add_all(VideoAffiliateProduct(video_id=video_id, product_id=product_id) for product_id in chosen - attached)
    if chosen != attached:
        for post in db.scalars(
            select(Publication).where(Publication.video_id == video_id, Publication.comment_id.is_not(None))
        ):
            if is_published(post):
                post.comment_requested_at = now()
    db.commit()
    post = published_publication(db, video_id)
    return _video_payload(db, video, post) if post else {"id": video.id, "product_ids": sorted(chosen)}


@router.get("")
def list_products(
    topic_id: int | None = None,
    status: str | None = None,
    q: str | None = None,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
) -> list[dict]:
    return [_payload(product) for product in _ranked(db, topic_id, status, q)]


@router.get("/options")
def options(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    return {
        "shop_types": [{"value": value, "label": label} for value, label in SHOP_TYPES.items()],
        "topics": [{"id": topic.id, "name": topic.name} for topic in knowledge.all_topics(db)],
    }


@router.get("/export.csv")
def export_products(
    topic_id: int | None = None,
    status: str | None = None,
    q: str | None = None,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
) -> Response:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
            "Nhóm chủ đề",
            "Sản phẩm",
            "Shop",
            "Loại shop",
            "Sao",
            "Đã bán",
            "Giá (đ)",
            "Hoa hồng (%)",
            "Hoa hồng ước tính (đ)",
            "Link",
            "Trạng thái",
            "Ngày kiểm tra",
            "Người duyệt",
        ]
    )
    for product in _ranked(db, topic_id, status, q):
        checked = product.checked_at.astimezone(VIETNAM_TIME).strftime("%d/%m/%Y %H:%M") if product.checked_at else ""
        writer.writerow(
            [
                _csv_cell(product.topic.name),
                _csv_cell(product.name),
                _csv_cell(product.shop_name),
                SHOP_TYPES[product.shop_type],
                product.rating,
                product.sold,
                product.price,
                product.commission_rate,
                _expected_commission(product),
                product.url,
                "Đã duyệt" if product.status == "approved" else "Nháp",
                checked,
                _csv_cell(product.checked_by.name) if product.checked_by else "",
            ]
        )
    # The byte order mark tells Excel the file is UTF-8, otherwise Vietnamese comes out garbled.
    return Response(
        f"﻿{out.getvalue()}".encode(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="san-pham-affiliate.csv"'},
    )


@router.post("", status_code=201)
def add_product(body: ProductBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    product = AffiliateProduct(**_fields(db, body), created_by_id=me.user_id)
    db.add(product)
    db.commit()
    return _payload(product)


@router.put("/{product_id}")
def update_product(
    product_id: int, body: ProductBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    product = _get(db, product_id)
    fields = _fields(db, body)
    if any(getattr(product, name) != value for name, value in fields.items()):
        _clear_approval(product)
    for name, value in fields.items():
        setattr(product, name, value)
    db.commit()
    db.refresh(product)
    return _payload(product)


@router.post("/{product_id}/approve")
def approve_product(product_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    product = _get(db, product_id)
    problems = affiliate.problems(product)
    if problems:
        raise ApiError(409, "product_not_approvable", f"Chưa duyệt được: {'; '.join(problems)}")
    product.status, product.checked_at, product.checked_by_id = "approved", datetime.now(UTC), me.user_id
    db.commit()
    db.refresh(product)
    return _payload(product)


@router.post("/{product_id}/unapprove")
def unapprove_product(product_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    product = _get(db, product_id)
    _clear_approval(product)
    db.commit()
    db.refresh(product)
    return _payload(product)


@router.delete("/{product_id}")
def delete_product(product_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    db.delete(_get(db, product_id))
    db.commit()
    return {"ok": True}
