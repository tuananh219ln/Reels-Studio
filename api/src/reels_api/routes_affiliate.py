"""Affiliate: the team's product list on Shopee and TikTok Shop, added by a pasted Shopee link or Shopee Affiliate's
file (the worker reads the rest), entered by hand, or found through Shopee's API, ranked
by expected commission and approved by a member; the products attached to each video, and Shopee's suggestions for a
video (affiliate_rounds.py finds them)."""

import csv
import io
import unicodedata
from datetime import UTC, datetime, timedelta, timezone
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import case, delete, func, or_, select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import object_session

from . import affiliate, affiliate_rounds, article_posts, facebook, knowledge, post_comments, shopee
from .db import get_db
from .errors import ApiError
from .models import (
    AffiliateAccount,
    AffiliateProduct,
    AffiliateSuggestion,
    Article,
    ArticleAffiliateProduct,
    Fanpage,
    KnowledgeTopic,
    Publication,
    Session,
    User,
    Video,
    VideoAffiliateProduct,
)
from .ownership import ensure_owner
from .routes_music import like_pattern
from .routes_videos import invalid, my_topic_ids
from .sessions import current_member, now
from .videos import is_published, split_scenes, thumbnail_url, video_name

router = APIRouter(prefix="/api/affiliate-products")

MAX_NAME_LENGTH = 300
MAX_SHOP_NAME_LENGTH = 200
MAX_URL_LENGTH = 2000
MAX_COUNT = 1_000_000_000  # keeps price and sold inside the database's integer
VIETNAM_TIME = timezone(timedelta(hours=7))
MAX_LINKS = 50  # links pasted at once
MAX_IMPORT_ROWS = 500
MAX_IMPORT_CHARS = 2_000_000
NO_SHOPEE_ACCOUNT = (
    "Chưa có tài khoản Shopee nào có App ID và Secret để tự lấy thông tin sản phẩm. Thêm ở Cài đặt › Tài khoản "
    "affiliate, hoặc dùng Nhập file từ Shopee Affiliate"
)
# The columns of Shopee Affiliate's "Lấy link hàng loạt" file, in Vietnamese and in English.
IMPORT_COLUMNS = {
    "item_id": ("mã sản phẩm", "item id"),
    "name": ("tên sản phẩm", "item name", "product name"),
    "price": ("giá", "price"),
    "shop_name": ("tên cửa hàng", "tên shop", "shop name"),
    "commission_rate": ("tỉ lệ hoa hồng", "tỷ lệ hoa hồng", "commission rate"),
    "page_url": ("link sản phẩm", "product link"),
    "url": ("link ưu đãi", "offer link"),
}
BOM = "\ufeff"


class ProductBody(BaseModel):
    knowledge_topic_id: int
    platform: str = "shopee"
    name: str
    url: str | None = None
    shop_name: str
    shop_type: str
    rating: float
    sold: int
    price: int
    commission_rate: float


class LinksBody(BaseModel):
    knowledge_topic_id: int
    links: list[str]


class ImportBody(BaseModel):
    knowledge_topic_id: int
    text: str


class VideoProductsBody(BaseModel):
    product_ids: list[int]


class ChooseBody(BaseModel):
    product_id: int


class ProductIdsBody(BaseModel):
    product_ids: list[int]


class VideoLinksBody(BaseModel):
    links: list[str]


def _text(value: str, label: str, limit: int) -> str:
    value = " ".join(unicodedata.normalize("NFC", value).split())
    if not value:
        raise invalid(f"{label} không được để trống")
    if len(value) > limit:
        raise invalid(f"{label} dài quá {limit} ký tự")
    return value


def _url(value: str | None) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
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
    if body.platform not in affiliate.PLATFORMS:
        raise invalid("Nền tảng không có trong danh sách")
    if body.shop_type not in affiliate.SHOP_TYPES[body.platform]:
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
        "platform": body.platform,
        "name": _text(body.name, "Tên sản phẩm", MAX_NAME_LENGTH),
        "url": _url(body.url),
        "shop_name": _text(body.shop_name, "Tên shop", MAX_SHOP_NAME_LENGTH),
        "shop_type": body.shop_type,
        "rating": body.rating,
        "sold": body.sold,
        "price": body.price,
        "commission_rate": body.commission_rate,
    }


def _topic(db: DbSession, topic_id: int) -> KnowledgeTopic:
    topic = db.get(KnowledgeTopic, topic_id)
    if topic is None:
        raise invalid("Nhóm chủ đề không còn tồn tại")
    return topic


def _waiting(product: AffiliateProduct, user_id: int, ask: bool) -> None:
    """Hand the product to the worker's next round (affiliate_rounds.lookup) when there is an account to ask with."""
    product.lookup_requested_at, product.lookup_by_id, product.lookup_error = (now() if ask else None), user_id, None


def _known(db: DbSession, item_ids: set[int], urls: set[str]) -> tuple[dict[int, AffiliateProduct], set[str]]:
    rows = list(
        db.scalars(
            select(AffiliateProduct).where(
                or_(
                    AffiliateProduct.shopee_item_id.in_(item_ids),
                    AffiliateProduct.url.in_(urls),
                    AffiliateProduct.page_url.in_(urls),
                )
            )
        )
    )
    links = {row.url for row in rows if row.url} | {row.page_url for row in rows if row.page_url}
    return {row.shopee_item_id: row for row in rows if row.shopee_item_id}, links


def _header(cell: str) -> str:
    return " ".join(unicodedata.normalize("NFC", cell).lstrip(BOM).lower().split())


def _amount(cell: str) -> float | None:
    """A number as Shopee Affiliate's file writes it: "45,0k", "1,2tr", "₫900", "2,5%", "125.000"."""
    value = cell.strip().lower().replace("₫", "").replace("đ", "").replace("%", "").replace(" ", "")
    factor = 1
    for suffix, times in (("tr", 1_000_000), ("m", 1_000_000), ("k", 1_000)):
        if value.endswith(suffix):
            value, factor = value[: -len(suffix)], times
            break
    if factor == 1 and "," not in value and "." in value and len(value.rsplit(".", 1)[1]) == 3:
        value = value.replace(".", "")  # 125.000: dots group the thousands
    try:
        return float(value.replace(",", ".")) * factor
    except ValueError:
        return None


def _imported(row: dict[str, str]) -> dict:
    """One row of the file as the fields of a product; raises ApiError saying what is wrong."""
    try:
        item_id = int(row["item_id"].strip())
    except ValueError:
        raise invalid("Mã sản phẩm không hợp lệ") from None
    price = _amount(row["price"])
    rate = _amount(row["commission_rate"])
    if price is None or not 0 < price <= MAX_COUNT:
        raise invalid("Giá không đọc được")
    if rate is None or not 0 <= rate <= 100:
        raise invalid("Tỉ lệ hoa hồng không đọc được")
    url = _url(row["url"])
    page_url = _url(row["page_url"])
    if not (url or page_url):
        raise invalid("Thiếu link sản phẩm")
    return {
        "shopee_item_id": item_id,
        "name": _text(row["name"], "Tên sản phẩm", MAX_NAME_LENGTH),
        "shop_name": _text(row["shop_name"], "Tên shop", MAX_SHOP_NAME_LENGTH),
        "price": round(price),
        "commission_rate": round(rate, 2),
        "url": url,
        "page_url": page_url,
    }


def _expected_commission(product: AffiliateProduct) -> int:
    return round(product.price * product.commission_rate / 100)


def _video_count(db: DbSession, product_ids: list[int]) -> dict[int, int]:
    """How many videos each product is attached to."""
    if not product_ids:
        return {}
    return dict(
        db.execute(
            select(VideoAffiliateProduct.product_id, func.count())
            .where(VideoAffiliateProduct.product_id.in_(product_ids))
            .group_by(VideoAffiliateProduct.product_id)
        ).all()
    )


def _payload(product: AffiliateProduct, video_count: int | None = None) -> dict:
    if video_count is None:
        session = object_session(product)
        video_count = _video_count(session, [product.id]).get(product.id, 0) if session and product.id else 0
    return {
        "id": product.id,
        "created_by_id": product.created_by_id,  # only they delete it
        # Its saved link (`url`) is theirs: a Page without its own Shopee account puts it in the comment.
        "created_by": product.created_by.name,
        "has_saved_link": product.url is not None,
        "video_count": video_count,
        "knowledge_topic_id": product.knowledge_topic_id,
        "topic": product.topic.name,
        "platform": product.platform,
        "platform_label": affiliate.PLATFORMS[product.platform],
        "name": product.name,
        "url": product.url,
        "page_url": product.page_url,
        "image_url": product.image_url,
        "from_shopee_api": product.shopee_item_id is not None,
        "commission_end_at": product.commission_end_at.isoformat() if product.commission_end_at else None,
        "shop_name": product.shop_name,
        "shop_type": product.shop_type,
        "shop_type_label": affiliate.SHOP_TYPES[product.platform][product.shop_type],
        "rating": product.rating,
        "sold": product.sold,
        "price": product.price,
        "commission_rate": product.commission_rate,
        "expected_commission": _expected_commission(product),
        "status": product.status,
        "checked_at": product.checked_at.isoformat() if product.checked_at else None,
        "checked_by": product.checked_by.name if product.checked_by else None,
        "problems": affiliate.problems(product),
        # Its stars or sales are under the rule, so the list offers to fill them in on the row ("Sửa nhanh").
        "short_on_counts": product.rating < affiliate.MIN_RATING or product.sold < affiliate.MIN_SOLD,
        "lookup": "pending" if product.lookup_requested_at else ("failed" if product.lookup_error else None),
        "lookup_error": product.lookup_error,
    }


def _get(db: DbSession, product_id: int) -> AffiliateProduct:
    product = db.get(AffiliateProduct, product_id)
    if product is None:
        raise ApiError(404, "product_not_found", "Không tìm thấy sản phẩm (có thể đã bị xóa)")
    return product


def _clear_approval(product: AffiliateProduct) -> None:
    product.status, product.checked_at, product.checked_by_id = "draft", None, None


def _ranked(
    db: DbSession, topic_id: int | None, status: str | None, q: str | None, platform: str | None = None
) -> list[AffiliateProduct]:
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
    if platform:
        query = query.where(AffiliateProduct.platform == platform)
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


def _name(db: DbSession, user_id: int | None) -> str | None:
    user = db.get(User, user_id) if user_id else None
    return user.name if user else None


def _post_payload(db: DbSession, post: Publication) -> dict:
    """Where a live post went and whose it is: a Facebook Page and its owner, or a TikTok account and its owner."""
    page = db.get(Fanpage, post.fanpage_id) if post.fanpage_id else None
    account = db.get(AffiliateAccount, post.affiliate_account_id) if post.affiliate_account_id else None
    owner_id = page.owner_id if page else account.owner_id if account else None
    return {
        "platform": post.platform,
        "fanpage_id": page.id if page else None,
        "name": page.name if page else account.name if account else None,
        "fanpage_name": page.name if page else None,
        "owner_id": owner_id,
        "owner_name": _name(db, owner_id),
        "has_shopee_account": affiliate.page_account(db, page) is not None,
        # How the post's comment stands (post_comments.payload): off, waiting, pending, done or failed.
        "comment": post_comments.payload(post)["state"] if post.platform == "facebook" else "off",
        "comment_error": post.comment_error if post.platform == "facebook" else None,
    }


def _commission(db: DbSession, product: AffiliateProduct, posts: list[Publication]) -> list[dict]:
    """Per Page the video is live on, whose commission the product's link in its comment earns (affiliate.link_for)."""
    if product.platform != "shopee":
        return []
    found = []
    for post in posts:
        page = db.get(Fanpage, post.fanpage_id) if post.platform == "facebook" and post.fanpage_id else None
        if page is None:
            continue
        account = affiliate.page_account(db, page)
        kind = affiliate.commission_to(account, product)
        user_id = {"page_account": account.owner_id if account else None, "saved_link": product.created_by_id}.get(kind)
        found.append(
            {
                "fanpage_id": page.id,
                "fanpage_name": page.name,
                "kind": kind,
                "user_id": user_id,
                "user_name": _name(db, user_id),
            }
        )
    return found


def _live_posts(db: DbSession, video_id: int) -> list[Publication]:
    """The video's live Facebook and TikTok posts, newest first."""
    posts = db.scalars(
        select(Publication).where(Publication.video_id == video_id, Publication.platform.in_(("facebook", "tiktok")))
    )
    return sorted((post for post in posts if is_published(post)), key=_live_at, reverse=True)


def _video_payload(db: DbSession, video: Video, posts: list[Publication], user_id: int) -> dict:
    """`posts`: its live posts, newest first; the newest gives the reel's link and time."""
    post = posts[0]
    title, _ = split_scenes(db, video)
    products = db.scalars(
        select(AffiliateProduct)
        .join(VideoAffiliateProduct)
        .where(VideoAffiliateProduct.video_id == video.id)
        .order_by(AffiliateProduct.id)
    )
    where = [_post_payload(db, one) for one in posts]
    if video.manual_comment:
        # Nothing waits for the worker under a video pasted by hand; a comment it already wrote still shows.
        for one in where:
            one["comment"] = "off" if one["comment"] in ("waiting", "pending") else one["comment"]
    return {
        "id": video.id,
        "title": video_name(video, title),
        "thumbnail_url": thumbnail_url(video),
        # Its group's products come first in "+ Gắn sản phẩm".
        "knowledge_topic_id": video.knowledge_topic_id,
        "platform": video.platform,
        # "Đã dán link tay": the app writes and edits none of its comments; its products are only a record.
        "manual_comment": video.manual_comment,
        "reel_url": post.post_url if post.platform == "tiktok" else facebook.reel_url(post.remote_id),
        "published_at": _live_at(post).isoformat(),
        # Mine when I posted it or it is live on a Page or account of mine (decisions 2026-11-08, "Của tôi").
        "mine": any(one.created_by_id == user_id for one in posts) or any(one["owner_id"] == user_id for one in where),
        "posts": where,
        "suggestions": video.affiliates,
        "pinned_comment": video.pinned_comment,
        "products": [
            {
                "id": product.id,
                "name": product.name,
                "url": product.url,
                "status": product.status,
                "problems": affiliate.problems(product),
                "created_by_id": product.created_by_id,
                "created_by": product.created_by.name,
                "has_saved_link": product.url is not None,
                "commission": _commission(db, product, posts),
            }
            for product in products
        ],
    }


@router.get("/videos")
def list_videos(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(Video, Publication)
        .join(Publication)
        .where(Publication.platform.in_(("facebook", "tiktok")))
        .order_by(Publication.id)
    )
    # A video posted again has one comment to pin per reel in time, so it shows once, with its newest live post.
    videos: dict[int, Video] = {}
    posts: dict[int, list[Publication]] = {}
    for video, post in rows:
        if is_published(post):
            videos[video.id] = video
            posts.setdefault(video.id, []).append(post)
    for live in posts.values():
        live.sort(key=_live_at, reverse=True)
    posted = sorted(videos.values(), key=lambda video: _live_at(posts[video.id][0]), reverse=True)
    return [_video_payload(db, video, posts[video.id], me.user_id) for video in posted]


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
    wanted = affiliate.PRODUCT_PLATFORM[video.platform]
    if any(product.platform != wanted and product.id not in attached for product in products):
        raise ApiError(
            409,
            "wrong_platform",
            f"Video {'TikTok' if video.platform == 'tiktok' else 'Facebook'} chỉ gắn được sản phẩm "
            f"{affiliate.PLATFORMS[wanted]}",
        )
    # A product that stopped qualifying stays until a member removes it, so saving another change is not refused.
    if any(not affiliate.usable(product) and product.id not in attached for product in products):
        raise ApiError(409, "product_not_approved", "Chỉ gắn được sản phẩm đã duyệt và còn đạt tiêu chí")
    db.execute(
        delete(VideoAffiliateProduct).where(
            VideoAffiliateProduct.video_id == video_id, VideoAffiliateProduct.product_id.not_in(chosen)
        )
    )
    db.add_all(VideoAffiliateProduct(video_id=video_id, product_id=product_id) for product_id in chosen - attached)
    if chosen != attached and not video.manual_comment:
        for post in db.scalars(
            select(Publication).where(Publication.video_id == video_id, Publication.comment_id.is_not(None))
        ):
            if is_published(post):
                post.comment_requested_at = now()
    db.commit()
    posts = _live_posts(db, video_id)
    return _video_payload(db, video, posts, me.user_id) if posts else {"id": video.id, "product_ids": sorted(chosen)}


class ManualBody(BaseModel):
    manual: bool


@router.put("/videos/{video_id}/manual")
def set_manual_comment(
    video_id: int, body: ManualBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Đã dán link tay": a member pasted the video's affiliate links on Facebook, so the worker keeps out of its
    posts' comments; unmarked, it writes them again as usual (a post never commented is due as before)."""
    video = _video(db, video_id)
    video.manual_comment = body.manual
    db.commit()
    posts = _live_posts(db, video_id)
    return _video_payload(db, video, posts, me.user_id) if posts else {"id": video.id, "manual_comment": body.manual}


def _video(db: DbSession, video_id: int) -> Video:
    video = db.get(Video, video_id)
    if video is None:
        raise ApiError(404, "video_not_found", "Không tìm thấy video")
    return video


def _suggestions(db: DbSession, video: Video | Article) -> dict:
    """The Shopee suggestions of a video, or of an article ("Bài viết"), by product idea, and what is attached."""
    article = isinstance(video, Article)
    column = AffiliateSuggestion.article_id if article else AffiliateSuggestion.video_id
    rows = db.scalars(select(AffiliateSuggestion).where(column == video.id).order_by(AffiliateSuggestion.id))
    keywords: dict[str, list[dict]] = {}
    for row in rows:
        keywords.setdefault(row.keyword, []).append(_payload(row.product))
    return {
        "state": "pending" if video.suggest_requested_at else ("failed" if video.suggest_error else "idle"),
        "error": video.suggest_error,
        "at": video.suggested_at.isoformat() if video.suggested_at else None,
        "keywords": [
            {"keyword": keyword, "products": products, "pasted": keyword == affiliate_rounds.PASTED}
            for keyword, products in keywords.items()
        ],
        "attached_ids": [
            product.id for product in (affiliate.article_products if article else affiliate.products_of)(db, video.id)
        ],
    }


@router.get("/videos/{video_id}/suggestions")
def video_suggestions(video_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    return _suggestions(db, _video(db, video_id))


@router.post("/videos/{video_id}/suggestions")
def request_suggestions(video_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Tìm sản phẩm": the worker searches Shopee for the video's product ideas with the member's own account, within
    seconds. The request itself never calls Shopee."""
    video = _video(db, video_id)
    if video.platform != "facebook":
        raise invalid("Chỉ video Facebook mới tìm sản phẩm Shopee; video TikTok gắn giỏ TikTok Shop trong app TikTok")
    if not [keyword for keyword in video.affiliates if keyword.strip()]:
        raise invalid("Video chưa có gợi ý sản phẩm nào để tìm, hãy thêm ở mục Affiliate")
    accounts = db.scalars(
        select(AffiliateAccount).where(AffiliateAccount.owner_id == me.user_id, AffiliateAccount.platform == "shopee")
    )
    if not any(affiliate.credentials(account) for account in accounts):
        raise invalid("Bạn chưa có tài khoản Shopee đang dùng với App ID và Secret (Cài đặt › Tài khoản affiliate)")
    video.suggest_requested_at, video.suggest_by_id, video.suggest_error = now(), me.user_id, None
    db.commit()
    return _suggestions(db, video)


@router.post("/videos/{video_id}/choose")
def choose_suggestion(
    video_id: int, body: ChooseBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Chọn" a product: approve it when it meets the rules, and attach it to the video. The link of each Page is made
    by the worker when it writes that Page's comment."""
    video = _video(db, video_id)
    product = _get(db, body.product_id)
    if product.platform != affiliate.PRODUCT_PLATFORM[video.platform]:
        raise ApiError(409, "wrong_platform", "Sản phẩm không cùng nền tảng với video")
    if product.status != "approved":
        problems = affiliate.problems(product)
        if problems:
            raise ApiError(409, "product_not_approvable", f"Chưa chọn được: {'; '.join(problems)}")
        product.status, product.checked_at, product.checked_by_id = "approved", datetime.now(UTC), me.user_id
    elif not affiliate.usable(product):
        raise ApiError(409, "product_not_approved", "Sản phẩm không còn đạt tiêu chí")
    if db.get(VideoAffiliateProduct, (video.id, product.id)) is None:
        db.add(VideoAffiliateProduct(video_id=video.id, product_id=product.id))
        for post in db.scalars(
            select(Publication).where(Publication.video_id == video.id, Publication.comment_id.is_not(None))
        ):
            if is_published(post):
                post.comment_requested_at = now()
    db.commit()
    return _suggestions(db, video)


@router.post("/videos/{video_id}/links")
def paste_video_links(
    video_id: int, body: VideoLinksBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Dán link aff" on the video: each Shopee link becomes a product of the video's topic group, listed with the
    video's suggestions for "Chọn". With a Shopee account with App ID in the team the worker reads the rest; without
    one, the draft holds only the link and a member fills in the rest by hand. The request never calls Shopee."""
    video = _video(db, video_id)
    if video.platform != "facebook":
        raise invalid("Chỉ video Facebook mới gắn sản phẩm Shopee; video TikTok gắn giỏ TikTok Shop trong app TikTok")
    if video.knowledge_topic_id is None:
        raise invalid("Video chưa thuộc nhóm chủ đề nào, hãy thêm sản phẩm ở trang Affiliate")
    topic = _topic(db, video.knowledge_topic_id)
    links = _shopee_links(body.links)
    ask = affiliate_rounds.team_account(db, me.user_id) is not None
    products = [product for product, _ in _from_links(db, topic, links, me.user_id, ask).values()]
    listed = set(
        db.scalars(
            select(AffiliateSuggestion.product_id).where(
                AffiliateSuggestion.video_id == video.id, AffiliateSuggestion.keyword == affiliate_rounds.PASTED
            )
        )
    )
    rank = len(listed)
    for product in dict.fromkeys(products):
        if product.id not in listed:
            rank += 1
            db.add(
                AffiliateSuggestion(
                    video_id=video.id, keyword=affiliate_rounds.PASTED, product_id=product.id, rank=rank
                )
            )
    db.commit()
    return _suggestions(db, video)


# --- An article's suggestions ("Bài viết"): the same search, choice and pasted links as a video's ---


def _article(db: DbSession, article_id: int) -> Article:
    article = db.get(Article, article_id)
    if article is None:
        raise ApiError(404, "article_not_found", "Không tìm thấy bài viết (có thể đã bị xoá)")
    return article


def _ask_comments(db: DbSession, article: Article) -> None:
    """A change of products edits the comments already written under the article's live posts."""
    for post in db.scalars(
        select(Publication).where(Publication.article_id == article.id, Publication.comment_id.is_not(None))
    ):
        if is_published(post):
            post.comment_requested_at = now()


@router.get("/articles/{article_id}/suggestions")
def article_suggestions(
    article_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    return _suggestions(db, _article(db, article_id))


@router.post("/articles/{article_id}/suggestions")
def request_article_suggestions(
    article_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Tìm sản phẩm" on an article: the worker searches Shopee for its product ideas with the member's own account."""
    article = _article(db, article_id)
    if not [keyword for keyword in article.affiliates if keyword.strip()]:
        raise invalid("Bài chưa có gợi ý sản phẩm nào để tìm, hãy thêm ở ô Gợi ý sản phẩm")
    accounts = db.scalars(
        select(AffiliateAccount).where(AffiliateAccount.owner_id == me.user_id, AffiliateAccount.platform == "shopee")
    )
    if not any(affiliate.credentials(account) for account in accounts):
        raise invalid("Bạn chưa có tài khoản Shopee đang dùng với App ID và Secret (Cài đặt › Tài khoản affiliate)")
    article.suggest_requested_at, article.suggest_by_id, article.suggest_error = now(), me.user_id, None
    db.commit()
    return _suggestions(db, article)


@router.post("/articles/{article_id}/choose")
def choose_for_article(
    article_id: int, body: ChooseBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Chọn" a product for an article: approved when it meets the rules, and attached; at most MAX_PRODUCTS."""
    article = _article(db, article_id)
    product = _get(db, body.product_id)
    if product.platform != "shopee":
        raise ApiError(409, "wrong_platform", "Bài viết chỉ gắn sản phẩm Shopee")
    attached = {row.id for row in affiliate.article_products(db, article.id)}
    if product.id not in attached and len(attached) >= article_posts.MAX_PRODUCTS:
        raise ApiError(409, "too_many_products", f"Bài viết gắn tối đa {article_posts.MAX_PRODUCTS} sản phẩm")
    if product.status != "approved":
        problems = affiliate.problems(product)
        if problems:
            raise ApiError(409, "product_not_approvable", f"Chưa chọn được: {'; '.join(problems)}")
        product.status, product.checked_at, product.checked_by_id = "approved", datetime.now(UTC), me.user_id
    elif not affiliate.usable(product):
        raise ApiError(409, "product_not_approved", "Sản phẩm không còn đạt tiêu chí")
    if product.id not in attached:
        db.add(ArticleAffiliateProduct(article_id=article.id, product_id=product.id))
        _ask_comments(db, article)
    db.commit()
    return _suggestions(db, article)


@router.post("/articles/{article_id}/links")
def paste_article_links(
    article_id: int, body: VideoLinksBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Thêm link" on an article: each Shopee link becomes a product of its topic group, listed for "Chọn"."""
    article = _article(db, article_id)
    if article.knowledge_topic_id is None:
        raise invalid("Bài chưa thuộc nhóm chủ đề nào, hãy thêm sản phẩm ở trang Affiliate")
    topic = _topic(db, article.knowledge_topic_id)
    links = _shopee_links(body.links)
    ask = affiliate_rounds.team_account(db, me.user_id) is not None
    products = [product for product, _ in _from_links(db, topic, links, me.user_id, ask).values()]
    listed = set(
        db.scalars(
            select(AffiliateSuggestion.product_id).where(
                AffiliateSuggestion.article_id == article.id, AffiliateSuggestion.keyword == affiliate_rounds.PASTED
            )
        )
    )
    rank = len(listed)
    for product in dict.fromkeys(products):
        if product.id not in listed:
            rank += 1
            db.add(
                AffiliateSuggestion(
                    article_id=article.id, keyword=affiliate_rounds.PASTED, product_id=product.id, rank=rank
                )
            )
    db.commit()
    return _suggestions(db, article)


@router.get("")
def list_products(
    topic_id: int | None = None,
    status: str | None = None,
    q: str | None = None,
    platform: str | None = None,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
) -> list[dict]:
    products = _ranked(db, topic_id, status, q, platform)
    counts = _video_count(db, [product.id for product in products])
    return [_payload(product, counts.get(product.id, 0)) for product in products]


@router.get("/options")
def options(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    mine = my_topic_ids(db, me.user_id)
    products = dict(
        db.execute(
            select(AffiliateProduct.knowledge_topic_id, func.count()).group_by(AffiliateProduct.knowledge_topic_id)
        ).all()
    )
    return {
        "platforms": [{"value": value, "label": label} for value, label in affiliate.PLATFORMS.items()],
        "shop_types": {
            platform: [{"value": value, "label": label} for value, label in types.items()]
            for platform, types in affiliate.SHOP_TYPES.items()
        },
        # "mine": a group a Page I own and use posts (decisions 2026-11-08), listed first in the filter.
        "topics": [
            {"id": topic.id, "name": topic.name, "mine": topic.id in mine, "product_count": products.get(topic.id, 0)}
            for topic in knowledge.all_topics(db)
        ],
        # The Pages in use and the group each posts, so a file can be imported "for a Page" into its group.
        "pages": [
            {
                "id": page.id,
                "name": page.name,
                "mine": page.owner_id == me.user_id,
                "owner_name": _name(db, page.owner_id),
                "knowledge_topic_id": page.knowledge_topic_id,
            }
            for page in db.scalars(select(Fanpage).where(Fanpage.active.is_(True)).order_by(Fanpage.name))
        ],
        # Whether a pasted Shopee link can be read: some member has a Shopee account with App ID and Secret.
        "shopee_lookup": affiliate_rounds.team_account(db, me.user_id) is not None,
    }


@router.get("/export.csv")
def export_products(
    topic_id: int | None = None,
    status: str | None = None,
    q: str | None = None,
    platform: str | None = None,
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
            "Nền tảng",
        ]
    )
    for product in _ranked(db, topic_id, status, q, platform):
        checked = product.checked_at.astimezone(VIETNAM_TIME).strftime("%d/%m/%Y %H:%M") if product.checked_at else ""
        writer.writerow(
            [
                _csv_cell(product.topic.name),
                _csv_cell(product.name),
                _csv_cell(product.shop_name),
                affiliate.SHOP_TYPES[product.platform][product.shop_type],
                product.rating,
                product.sold,
                product.price,
                product.commission_rate,
                _expected_commission(product),
                product.url or product.page_url or "",
                "Đã duyệt" if product.status == "approved" else "Nháp",
                checked,
                _csv_cell(product.checked_by.name) if product.checked_by else "",
                affiliate.PLATFORMS[product.platform],
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


@router.post("/links", status_code=201)
def add_links(body: LinksBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Thêm sản phẩm": a member pastes Shopee links and the worker reads each product within seconds (name, shop,
    stars, sales, price, commission); the request itself never calls Shopee."""
    topic = _topic(db, body.knowledge_topic_id)
    links = _shopee_links(body.links)
    if affiliate_rounds.team_account(db, me.user_id) is None:
        raise invalid(NO_SHOPEE_ACCOUNT)
    added, skipped = 0, []
    for link, (_, new) in _from_links(db, topic, links, me.user_id, ask=True).items():
        if new:
            added += 1
        else:
            skipped.append(link)
    db.commit()
    return {"added": added, "skipped": skipped}


def _shopee_links(raw: list[str]) -> list[str]:
    links = list(dict.fromkeys(link.strip() for link in raw if link.strip()))
    if not links:
        raise invalid("Dán ít nhất một link sản phẩm Shopee")
    if len(links) > MAX_LINKS:
        raise invalid(f"Mỗi lần dán tối đa {MAX_LINKS} link")
    for link in links:
        if not shopee.is_shopee_link(_url(link)):
            raise invalid(f"Không phải link Shopee: {link[:80]}")
    return links


def _from_links(
    db: DbSession, topic: KnowledgeTopic, links: list[str], user_id: int, ask: bool
) -> dict[str, tuple[AffiliateProduct, bool]]:
    """The product of each link: the one already listed (False), else a new draft named by its link (True), which the
    worker reads when `ask`; without, a member fills it in by hand."""
    items = {link: shopee.item_id_of(link) for link in links}
    known_items, _ = _known(db, {item for item in items.values() if item}, set())
    by_link = {
        link: row
        for row in db.scalars(
            select(AffiliateProduct).where(or_(AffiliateProduct.url.in_(links), AffiliateProduct.page_url.in_(links)))
        )
        for link in (row.url, row.page_url)
        if link
    }
    found: dict[str, tuple[AffiliateProduct, bool]] = {}
    for link, item_id in items.items():
        known = by_link.get(link) or (known_items.get(item_id) if item_id else None)
        if known is not None:
            found[link] = (known, False)
            continue
        product = AffiliateProduct(
            knowledge_topic_id=topic.id,
            platform="shopee",
            # Named by its link until the worker reads it; the page shows "Đang lấy thông tin" meanwhile.
            name=link[:MAX_NAME_LENGTH],
            # A short link is the member's own affiliate link; a product page's link is not one.
            url=None if item_id else link,
            page_url=link if item_id else None,
            shopee_item_id=item_id,
            shop_name="",
            shop_type="other",
            rating=0,
            sold=0,
            price=0,
            commission_rate=0,
            created_by_id=user_id,
        )
        _waiting(product, user_id, ask)
        db.add(product)
        if item_id:
            known_items[item_id] = product
        found[link] = (product, True)
    db.flush()
    return found


def _parsed_file(text_in: str) -> tuple[list[tuple[int, dict]], list[dict]]:
    """The file's rows as (row number, product fields), and the rows left out with why."""
    if len(text_in) > MAX_IMPORT_CHARS:
        raise invalid("File quá lớn, hãy chia nhỏ")
    text = text_in.lstrip(BOM)
    try:
        dialect = csv.Sniffer().sniff(text.split("\n", 1)[0], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    if not rows:
        raise invalid("File trống")
    headers = [_header(cell) for cell in rows[0]]
    columns = {
        field: next((index for index, header in enumerate(headers) if header in names), None)
        for field, names in IMPORT_COLUMNS.items()
    }
    missing = [IMPORT_COLUMNS[field][0] for field, index in columns.items() if index is None and field != "url"]
    if missing:
        raise invalid(
            f"File thiếu cột: {', '.join(missing)}. Hãy dùng file tải từ Shopee Affiliate › Lấy link hàng loạt"
        )
    data = [(number, row) for number, row in enumerate(rows[1:], start=2) if any(cell.strip() for cell in row)]
    if not data:
        raise invalid("File không có sản phẩm nào")
    if len(data) > MAX_IMPORT_ROWS:
        raise invalid(f"Mỗi lần nhập tối đa {MAX_IMPORT_ROWS} sản phẩm")
    parsed: list[tuple[int, dict]] = []
    errors = []
    for number, row in data:
        cells = {
            field: row[index] if index is not None and index < len(row) else "" for field, index in columns.items()
        }
        try:
            parsed.append((number, _imported(cells)))
        except ApiError as err:
            errors.append({"row": number, "message": err.message})
    return parsed, errors


def _sorted_rows(
    db: DbSession, parsed: list[tuple[int, dict]], user_id: int
) -> tuple[dict[int, AffiliateProduct], list[dict]]:
    """Each row as new, mine (a product of mine already listed: its figures and link are updated) or others (a
    teammate's: kept as it is, so their link and commission never change hands)."""
    known, _ = _known(db, {fields["shopee_item_id"] for _, fields in parsed}, set())
    rows = []
    for number, fields in parsed:
        product = known.get(fields["shopee_item_id"])
        state = "new" if product is None else "mine" if product.created_by_id == user_id else "others"
        rows.append(
            {
                "row": number,
                "name": fields["name"],
                "state": state,
                "by": product.created_by.name if product is not None else None,
                "topic": product.topic.name if product is not None else None,
            }
        )
    return known, rows


@router.post("/import/preview")
def preview_import(body: ImportBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """What "Nhập" would do with the file, row by row; writes nothing."""
    _topic(db, body.knowledge_topic_id)
    parsed, errors = _parsed_file(body.text)
    _, rows = _sorted_rows(db, parsed, me.user_id)
    return {"rows": rows, "errors": errors}


@router.post("/import", status_code=201)
def import_products(body: ImportBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Nhập file": the CSV of Shopee Affiliate's "Lấy link hàng loạt" (item id, name, price, shop, commission,
    product link, affiliate link). Stars, sales and the shop's type are not in it: the worker reads them when a member
    has a Shopee account with App ID, otherwise a member fills them in before approving. A product of mine already in
    the list takes the file's link and figures (an approved one keeps its approval unless it no longer meets the
    rules); a teammate's is left as it is and listed in `others`, so their link is never replaced by mine."""
    topic = _topic(db, body.knowledge_topic_id)
    parsed, errors = _parsed_file(body.text)
    known, rows = _sorted_rows(db, parsed, me.user_id)
    ask = affiliate_rounds.team_account(db, me.user_id) is not None
    added = updated = 0
    for (_, fields), row in zip(parsed, rows, strict=True):
        if row["state"] == "others":
            continue
        product = known.get(fields["shopee_item_id"])
        if product is None:
            product = AffiliateProduct(
                **fields,
                knowledge_topic_id=topic.id,
                platform="shopee",
                shop_type="other",
                rating=0,
                sold=0,
                created_by_id=me.user_id,
            )
            _waiting(product, me.user_id, ask)
            db.add(product)
            known[fields["shopee_item_id"]] = product
            added += 1
            continue
        for name, value in fields.items():
            if value is not None:
                setattr(product, name, value)
        if product.status == "approved" and affiliate.problems(product):
            _clear_approval(product)
        updated += 1
    db.commit()
    others = [
        {"row": row["row"], "name": row["name"], "by": row["by"], "topic": row["topic"]}
        for row in rows
        if row["state"] == "others"
    ]
    return {"added": added, "updated": updated, "kept": len(others), "others": others, "errors": errors, "lookup": ask}


@router.post("/{product_id}/lookup")
def request_lookup(product_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Lấy lại thông tin" from Shopee, in the worker's next round."""
    product = _get(db, product_id)
    if product.platform != "shopee" or not (product.shopee_item_id or product.url or product.page_url):
        raise invalid("Chỉ lấy được thông tin của sản phẩm Shopee có link")
    if affiliate_rounds.team_account(db, me.user_id) is None:
        raise invalid(NO_SHOPEE_ACCOUNT)
    _waiting(product, me.user_id, ask=True)
    db.commit()
    db.refresh(product)
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
    product.lookup_error = None  # filled in by hand
    db.commit()
    db.refresh(product)
    return _payload(product)


@router.post("/{product_id}/approve")
def approve_product(product_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    product = _get(db, product_id)
    if product.lookup_requested_at is not None:
        raise ApiError(409, "product_not_approvable", "Đang lấy thông tin từ Shopee, chờ vài giây rồi duyệt")
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


@router.post("/approve")
def approve_products(
    body: ProductIdsBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Duyệt" several products at once, ticked in the list: those meeting the rules are approved, the others (and
    those Shopee is still being read for) stay drafts and are counted; one already approved is left as it is."""
    ids = set(body.product_ids)
    if not ids:
        raise invalid("Chọn ít nhất một sản phẩm để duyệt")
    if len(ids) > MAX_IMPORT_ROWS:
        raise invalid(f"Mỗi lần duyệt tối đa {MAX_IMPORT_ROWS} sản phẩm")
    approved = skipped = 0
    at = datetime.now(UTC)
    for product in db.scalars(select(AffiliateProduct).where(AffiliateProduct.id.in_(ids))):
        if product.status == "approved":
            continue
        if product.lookup_requested_at is not None or affiliate.problems(product):
            skipped += 1
            continue
        product.status, product.checked_at, product.checked_by_id = "approved", at, me.user_id
        approved += 1
    db.commit()
    return {"approved": approved, "skipped": skipped}


@router.post("/delete")
def delete_products(
    body: ProductIdsBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Xoá" several products at once, ticked in the list; one already gone is passed over."""
    ids = set(body.product_ids)
    if not ids:
        raise invalid("Chọn ít nhất một sản phẩm để xoá")
    if len(ids) > MAX_IMPORT_ROWS:
        raise invalid(f"Mỗi lần xoá tối đa {MAX_IMPORT_ROWS} sản phẩm")
    products = list(db.scalars(select(AffiliateProduct).where(AffiliateProduct.id.in_(ids))))
    for product in products:
        db.delete(product)
    db.commit()
    return {"deleted": len(products)}


@router.delete("/{product_id}")
def delete_product(product_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    product = _get(db, product_id)
    ensure_owner(product.created_by_id, me.user_id, "sản phẩm này")
    db.delete(product)
    db.commit()
    return {"ok": True}


@router.get("/{product_id}")
def get_product(product_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    product = db.get(AffiliateProduct, product_id)
    if product is None:
        raise ApiError(404, "product_not_found", "Không tìm thấy sản phẩm")
    return _payload(product, _video_count(db, [product_id]).get(product_id, 0))
