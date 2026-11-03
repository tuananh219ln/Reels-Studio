"""Affiliate Shopee rules shared by the routes and the worker: which products may be approved, and the comment a reel
gets under it (the script's pinned comment, then one link per usable product attached to the video)."""

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .models import AffiliateProduct, Video, VideoAffiliateProduct
from .script_rules import banned_hits

# A high commission does not make up for a poor shop: below these a product cannot be approved.
TRUSTED_SHOP_TYPES = {"mall", "preferred_plus", "preferred"}
MIN_RATING = 4.7
MIN_SOLD = 100
# Facebook's limit for a comment is 8000 characters; a comment is cut well before it.
MAX_COMMENT_LENGTH = 8000


def problems(product: AffiliateProduct) -> list[str]:
    """Why a member may not approve this product."""
    found = []
    if product.shop_type not in TRUSTED_SHOP_TYPES:
        found.append("Shop phải là Shopee Mall, Yêu Thích hoặc Yêu Thích+")
    if product.rating < MIN_RATING:
        found.append(f"Đánh giá dưới {MIN_RATING} sao")
    if product.sold < MIN_SOLD:
        found.append(f"Lượt bán dưới {MIN_SOLD}")
    hits = banned_hits(product.name, product.topic.banned_words)
    if hits:
        found.append(f"Tên có từ cấm: {', '.join(hits)}")
    return found


def usable(product: AffiliateProduct) -> bool:
    """A product whose link may go in a comment: approved and still meeting the rules."""
    return product.status == "approved" and not problems(product)


def products_of(db: DbSession, video_id: int) -> list[AffiliateProduct]:
    return list(
        db.scalars(
            select(AffiliateProduct)
            .join(VideoAffiliateProduct)
            .where(VideoAffiliateProduct.video_id == video_id)
            .order_by(AffiliateProduct.id)
        )
    )


def comment_text(db: DbSession, video: Video) -> str:
    """The comment under the video's reels: its pinned comment, then "name: link" per usable attached product."""
    links = [f"{product.name}: {product.url}" for product in products_of(db, video.id) if usable(product)]
    return "\n".join(part for part in [video.pinned_comment.strip(), *links] if part)[:MAX_COMMENT_LENGTH]
