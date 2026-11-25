"""Affiliate → "Bộ bình luận": a Page's comment sets and settings, the short names, groups and tags of its group's
products, "Tạo tự động từ kho", and a video's planned set comments with its own choice (aff_sets.py)."""

import unicodedata

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from . import aff_sets
from .aff_sets import invalid
from .db import get_db
from .errors import ApiError
from .models import (
    AffCommentSet,
    AffCommentSetItem,
    AffiliateProduct,
    Fanpage,
    KnowledgeTopic,
    Publication,
    Session,
    Video,
)
from .sessions import current_member, now
from .videos import is_published

router = APIRouter(prefix="/api/aff-sets")

MAX_NAME_LENGTH = 120
MAX_LINE_LENGTH = 1000
MAX_GENERATED = 50


class SetBody(BaseModel):
    name: str
    intro_text: str = ""
    outro_text: str = ""
    tags: list[str] = []
    enabled: bool = True
    priority: int = 3
    product_ids: list[int] = []


class NewSetBody(SetBody):
    fanpage_id: int


class GenerateBody(BaseModel):
    fanpage_id: int
    split: str = "by_category"
    per_set: int = aff_sets.MAX_ITEMS
    with_outro: bool = True
    dry_run: bool = True


class LabelsBody(BaseModel):
    short_name: str | None = None
    category: str | None = None
    tags: list[str] = []


class VideoChoiceBody(BaseModel):
    off: bool = False
    set_ids: list[int] | None = None


def _line(value: str | None, limit: int, label: str) -> str:
    value = unicodedata.normalize("NFC", (value or "").replace("\r\n", "\n")).strip()
    if len(value) > limit:
        raise invalid(f"{label} dài quá {limit} ký tự")
    return value


def _page(db: DbSession, fanpage_id: int) -> Fanpage:
    page = db.get(Fanpage, fanpage_id)
    if page is None:
        raise ApiError(404, "fanpage_not_found", "Không tìm thấy Page")
    return page


def _set(db: DbSession, set_id: int) -> AffCommentSet:
    one = db.get(AffCommentSet, set_id)
    if one is None:
        raise ApiError(404, "aff_set_not_found", "Không tìm thấy bộ bình luận")
    return one


def _product_payload(product: AffiliateProduct, set_count: int = 0) -> dict:
    return {
        "id": product.id,
        "name": product.name,
        "short_name": product.short_name,
        "category": product.category,
        "tags": product.tags or [],
        "status": product.status,
        "usable": aff_sets.counts(product),
        "link": product.url or product.page_url,
        "set_count": set_count,
    }


def _set_payload(one: AffCommentSet, settings: dict) -> dict:
    items = [item.product for item in one.items]
    valid = [product for product in items if aff_sets.counts(product)]
    rows = aff_sets.preview_rows(one, set(), settings)
    warnings = []
    if len(valid) < len(items):
        warnings.append(
            f"{len(items) - len(valid)} sản phẩm không dùng được (chưa duyệt, hết hoa hồng hoặc không có link)"
        )
    if len(valid) < aff_sets.MIN_VALID:
        warnings.append(f"Dưới {aff_sets.MIN_VALID} sản phẩm hợp lệ: app không tự chọn bộ này")
    return {
        "id": one.id,
        "fanpage_id": one.fanpage_id,
        "name": one.name,
        "intro_text": one.intro_text,
        "outro_text": one.outro_text,
        "tags": one.tags or [],
        "enabled": one.enabled,
        "priority": one.priority,
        "last_used_at": one.last_used_at.isoformat() if one.last_used_at else None,
        "use_count": one.use_count,
        "products": [
            {"id": product.id, "name": aff_sets.label(product), "usable": aff_sets.counts(product)} for product in items
        ],
        "valid_count": len(valid),
        "warnings": warnings,
        "preview": aff_sets.render(one.intro_text, one.outro_text, rows, settings["line_format"]),
    }


def _products_of(db: DbSession, page: Fanpage) -> list[AffiliateProduct]:
    """The Shopee products of the Page's group: what its sets are made from."""
    if page.knowledge_topic_id is None:
        return []
    return list(
        db.scalars(
            select(AffiliateProduct)
            .where(
                AffiliateProduct.knowledge_topic_id == page.knowledge_topic_id,
                AffiliateProduct.platform == "shopee",
            )
            .order_by(AffiliateProduct.category.nulls_last(), AffiliateProduct.name)
        )
    )


def _fill(db: DbSession, one: AffCommentSet, body: SetBody) -> None:
    name = _line(body.name, MAX_NAME_LENGTH, "Tên bộ")
    if not name:
        raise invalid("Tên bộ không được để trống")
    if not 1 <= body.priority <= 5:
        raise invalid("Ưu tiên phải từ 1 đến 5")
    ids = list(body.product_ids)
    if len(set(ids)) != len(ids):
        raise invalid("Một sản phẩm chỉ có một lần trong bộ")
    if len(ids) > aff_sets.MAX_ITEMS:
        raise invalid(f"Mỗi bộ tối đa {aff_sets.MAX_ITEMS} sản phẩm")
    found = {
        product.id: product
        for product in db.scalars(select(AffiliateProduct).where(AffiliateProduct.id.in_(ids or [0])))
    }
    if len(found) != len(ids):
        raise invalid("Có sản phẩm không còn trong kho")
    if any(product.platform != "shopee" for product in found.values()):
        raise invalid("Bộ bình luận chỉ nhận sản phẩm Shopee")
    one.name = name
    one.intro_text = _line(body.intro_text, MAX_LINE_LENGTH, "Câu mở đầu")
    one.outro_text = _line(body.outro_text, MAX_LINE_LENGTH, "Câu kết")
    one.tags = aff_sets.clean_tags(body.tags)
    one.enabled = body.enabled
    one.priority = body.priority
    one.items = [AffCommentSetItem(product_id=product_id, position=place) for place, product_id in enumerate(ids, 1)]


@router.get("")
def list_sets(fanpage_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    page = _page(db, fanpage_id)
    settings = aff_sets.settings_of(page)
    sets = aff_sets.page_sets(db, page.id)
    products = _products_of(db, page)
    used = dict(
        db.execute(
            select(AffCommentSetItem.product_id, func.count())
            .join(AffCommentSet)
            .where(AffCommentSet.fanpage_id == page.id)
            .group_by(AffCommentSetItem.product_id)
        ).all()
    )
    topic = db.get(KnowledgeTopic, page.knowledge_topic_id) if page.knowledge_topic_id else None
    return {
        "page": {"id": page.id, "name": page.name, "topic": topic.name if topic else None},
        "settings": settings,
        "strategies": [{"value": value, "label": label} for value, label in aff_sets.STRATEGIES.items()],
        "splits": [{"value": value, "label": label} for value, label in aff_sets.SPLITS.items()],
        "sets": [_set_payload(one, settings) for one in sets],
        "products": [_product_payload(product, used.get(product.id, 0)) for product in products],
    }


@router.put("/settings/{fanpage_id}")
def save_settings(
    fanpage_id: int, body: dict, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    page = _page(db, fanpage_id)
    page.aff_settings = aff_sets.clean_settings(body)
    db.commit()
    return aff_sets.settings_of(page)


@router.post("", status_code=201)
def create_set(body: NewSetBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    page = _page(db, body.fanpage_id)
    one = AffCommentSet(fanpage_id=page.id, created_by_id=me.user_id, items=[])
    _fill(db, one, body)
    db.add(one)
    db.commit()
    db.refresh(one)
    return _set_payload(one, aff_sets.settings_of(page))


@router.put("/{set_id}")
def update_set(
    set_id: int, body: SetBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    one = _set(db, set_id)
    one.items = []
    db.flush()
    _fill(db, one, body)
    # Comments already written from it under live reels follow the change.
    aff_sets.ask_set_refresh(db, [one.id])
    db.commit()
    db.refresh(one)
    return _set_payload(one, aff_sets.settings_of(db.get(Fanpage, one.fanpage_id)))


@router.post("/{set_id}/duplicate", status_code=201)
def duplicate_set(set_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    source = _set(db, set_id)
    copy = AffCommentSet(
        fanpage_id=source.fanpage_id,
        name=f"{source.name} (copy)"[:MAX_NAME_LENGTH],
        intro_text=source.intro_text,
        outro_text=source.outro_text,
        tags=list(source.tags or []),
        enabled=source.enabled,
        priority=source.priority,
        created_by_id=me.user_id,
        items=[AffCommentSetItem(product_id=item.product_id, position=item.position) for item in source.items],
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return _set_payload(copy, aff_sets.settings_of(db.get(Fanpage, copy.fanpage_id)))


@router.delete("/{set_id}")
def delete_set(set_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """A deleted set's comments stay on Facebook (the app cannot delete a comment); posts that used it write no more
    of it."""
    db.delete(_set(db, set_id))
    db.commit()
    return {"ok": True}


@router.post("/generate")
def generate_sets(body: GenerateBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Tạo tự động từ kho": the usable products of the Page's group cut into sets (aff_sets.split), each with its
    own opening line. `dry_run` only shows them."""
    page = _page(db, body.fanpage_id)
    if not 1 <= body.per_set <= aff_sets.MAX_ITEMS:
        raise invalid(f"Số sản phẩm mỗi bộ phải từ 1 đến {aff_sets.MAX_ITEMS}")
    products = [product for product in _products_of(db, page) if aff_sets.counts(product)]
    if not products:
        raise invalid("Nhóm của Page chưa có sản phẩm Shopee nào đã duyệt và có link")
    groups = aff_sets.split(products, body.split, body.per_set, seed=page.id)[:MAX_GENERATED]
    start = len(aff_sets.page_sets(db, page.id))
    planned = []
    for number, group in enumerate(groups, start=start + 1):
        planned.append(
            {
                "name": aff_sets.set_name(number, group, body.split),
                "intro_text": aff_sets.INTROS[(number - 1) % len(aff_sets.INTROS)],
                "outro_text": aff_sets.OUTRO if body.with_outro else "",
                "tags": aff_sets.clean_tags(sorted({product.category for product in group if product.category})),
                "products": group,
            }
        )
    if not body.dry_run:
        for plan in planned:
            db.add(
                AffCommentSet(
                    fanpage_id=page.id,
                    name=plan["name"],
                    intro_text=plan["intro_text"],
                    outro_text=plan["outro_text"],
                    tags=plan["tags"],
                    created_by_id=me.user_id,
                    items=[
                        AffCommentSetItem(product_id=product.id, position=place)
                        for place, product in enumerate(plan["products"], 1)
                    ],
                )
            )
        db.commit()
    return {
        "created": 0 if body.dry_run else len(planned),
        "sets": [{**plan, "products": [aff_sets.label(product) for product in plan["products"]]} for plan in planned],
    }


@router.patch("/products/{product_id}")
def label_product(
    product_id: int, body: LabelsBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """A product's short name, group and tags: what the set comments call it and match it by. Its approval stays."""
    product = db.get(AffiliateProduct, product_id)
    if product is None:
        raise ApiError(404, "product_not_found", "Không tìm thấy sản phẩm")
    short, category, tags = aff_sets.clean_labels(body.short_name, body.category, body.tags)
    renamed = short != product.short_name
    product.short_name, product.category, product.tags = short, category, tags
    if renamed:
        aff_sets.ask_set_refresh(db, aff_sets.sets_of_products(db, [product.id]))
    db.commit()
    return _product_payload(product)


def _video(db: DbSession, video_id: int) -> Video:
    video = db.get(Video, video_id)
    if video is None:
        raise ApiError(404, "video_not_found", "Không tìm thấy video")
    return video


def _video_pages(db: DbSession, video: Video) -> list[Fanpage]:
    """The Pages the video is or may be posted on: those of its Facebook posts, then the Pages of its group."""
    posted = select(Publication.fanpage_id).where(
        Publication.video_id == video.id,
        Publication.platform == "facebook",
        Publication.fanpage_id.is_not(None),
        Publication.status.not_in(("cancelled", "deleted")),
    )
    of_group = (
        select(Fanpage.id).where(Fanpage.active.is_(True), Fanpage.knowledge_topic_id == video.knowledge_topic_id)
        if video.knowledge_topic_id
        else None
    )
    ids = set(db.scalars(posted))
    if of_group is not None:
        ids |= set(db.scalars(of_group))
    return list(db.scalars(select(Fanpage).where(Fanpage.id.in_(ids or {0})).order_by(Fanpage.name)))


def _post_payload(post: Publication, planned: int) -> dict:
    """A live post's set comments: how many are up of how many, when the worker writes its next comment if it is
    waiting (the Page's pause, or a retry), and the last error."""
    at = now()
    waiting = post.comment_requested_at is not None and post.comment_requested_at > at
    return {
        "post_id": post.id,
        "count": len(post.aff_comment_ids or []),
        "total": len(post.aff_set_ids) if post.aff_set_ids is not None else planned,
        "next_at": post.comment_requested_at.isoformat() if waiting else None,
        "error": post.comment_error,
    }


def _video_payload(db: DbSession, video: Video) -> dict:
    pages = []
    for page in _video_pages(db, video):
        settings = aff_sets.settings_of(page)
        posts = db.scalars(
            select(Publication).where(
                Publication.video_id == video.id,
                Publication.fanpage_id == page.id,
                Publication.platform == "facebook",
                Publication.status.in_(("published", "scheduled")),
            )
        ).all()
        planned = aff_sets.preview(db, video, page)
        pages.append(
            {
                "fanpage_id": page.id,
                "name": page.name,
                "enabled": settings["enabled"],
                "sets_per_post": settings["sets_per_post"],
                "first_delay": settings["first_delay"],
                "delay": settings["delay"],
                "sets": [
                    {"id": one.id, "name": one.name, "enabled": one.enabled} for one in aff_sets.page_sets(db, page.id)
                ],
                "planned": planned,
                # Its live posts on this Page: what is already up under each and what comes next.
                "posts": [
                    _post_payload(post, len(planned))
                    for post in posts
                    if is_published(post) and (post.aff_comment_ids or planned)
                ],
            }
        )
    return {
        "off": video.aff_comments_off,
        "manual_comment": video.manual_comment,
        "set_ids": video.aff_set_ids,
        "pages": pages,
    }


@router.get("/videos/{video_id}")
def video_plan(video_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    return _video_payload(db, _video(db, video_id))


@router.put("/videos/{video_id}")
def choose_for_video(
    video_id: int, body: VideoChoiceBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """The video's own choice: no set comment at all, or these sets on their Page instead of the app's. A post that
    already wrote a set comment keeps its sets."""
    video = _video(db, video_id)
    ids = body.set_ids
    if ids is not None:
        if len(set(ids)) != len(ids):
            raise invalid("Một bộ chỉ chọn một lần")
        found = set(db.scalars(select(AffCommentSet.id).where(AffCommentSet.id.in_(ids or [0]))))
        if found != set(ids):
            raise invalid("Có bộ bình luận không còn")
        per_page: dict[int, int] = {}
        for page_id in db.scalars(select(AffCommentSet.fanpage_id).where(AffCommentSet.id.in_(ids or [0]))):
            per_page[page_id] = per_page.get(page_id, 0) + 1
        if any(count > aff_sets.MAX_SETS_PER_POST for count in per_page.values()):
            raise invalid(f"Mỗi Page chọn tối đa {aff_sets.MAX_SETS_PER_POST} bộ")
    video.aff_comments_off = body.off
    video.aff_set_ids = ids or None
    db.commit()
    return _video_payload(db, video)


@router.post("/posts/{post_id}/now")
def write_now(post_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Đăng aff ngay, bỏ chờ": the post's next comment goes up in the worker's next round rather than after the
    Page's wait or a retry's, and a failed one gets its automatic retries back. The Page's own minute between videos
    and its day's limit still hold. The request itself never calls Facebook."""
    post = db.get(Publication, post_id, with_for_update=True)
    if post is None or post.video_id is None or post.platform != "facebook":
        raise ApiError(404, "post_not_found", "Không tìm thấy bài đăng")
    if post.remote_id is None or not is_published(post):
        raise ApiError(409, "post_not_live", "Chỉ đăng bình luận aff dưới bài đã lên Facebook")
    video = _video(db, post.video_id)
    if not aff_sets.wants_sets(video):
        raise ApiError(409, "aff_comments_off", "Video này không đăng bình luận aff")
    post.comment_requested_at = now()
    post.aff_retries = 0
    db.commit()
    return _video_payload(db, video)
