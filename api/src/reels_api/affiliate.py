"""Affiliate rules shared by the routes and the worker: which products may be approved on each platform, and the
comment a reel gets under it (the script's pinned comment, then one link per usable Shopee product attached to the
video, made with the Page's own Shopee account when it has one)."""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import crypto, shopee
from .models import (
    AffiliateAccount,
    AffiliateLink,
    AffiliateProduct,
    Article,
    ArticleAffiliateProduct,
    Fanpage,
    Publication,
    Video,
    VideoAffiliateProduct,
)
from .script_rules import banned_hits

log = logging.getLogger("reels_api.affiliate")

PLATFORMS = {"shopee": "Shopee", "tiktok_shop": "TikTok Shop"}
# The products a video takes: a Facebook reel carries Shopee links, a TikTok video TikTok Shop's cart.
PRODUCT_PLATFORM = {"facebook": "shopee", "tiktok": "tiktok_shop"}
SHOP_TYPES = {
    "shopee": {
        "mall": "Shopee Mall",
        "preferred_plus": "Shop Yêu Thích+",
        "preferred": "Shop Yêu Thích",
        "other": "Shop thường",
    },
    # Proposed in issue #47 and waiting for the owner: TikTok Shop's own Mall, or a shop scoring at least 4.0.
    "tiktok_shop": {"mall": "TikTok Shop Mall", "trusted": "Điểm shop từ 4.0", "other": "Shop thường"},
}
# A high commission does not make up for a poor shop: below these a product cannot be approved. Shopee has no such
# floor since 2026-11-05 (decisions.md): any shop type passes, its stars and sales still have to; Mall still ranks
# first among equal commissions.
TRUSTED_SHOP_TYPES = {"tiktok_shop": {"mall", "trusted"}}
TRUSTED_SHOPS_TEXT = {"tiktok_shop": "Shop phải là TikTok Shop Mall hoặc có điểm shop từ 4.0"}
MIN_RATING = 4.7
MIN_SOLD = 100
# Facebook's limit for a comment is 8000 characters; a comment is cut well before it.
MAX_COMMENT_LENGTH = 8000


def problems(product: AffiliateProduct) -> list[str]:
    """Why a member may not approve this product."""
    found = []
    trusted = TRUSTED_SHOP_TYPES.get(product.platform)
    if trusted is not None and product.shop_type not in trusted:
        found.append(TRUSTED_SHOPS_TEXT[product.platform])
    if product.rating < MIN_RATING:
        found.append(f"Đánh giá dưới {MIN_RATING} sao")
    if product.sold < MIN_SOLD:
        found.append(f"Lượt bán dưới {MIN_SOLD}")
    if product.platform == "tiktok_shop" and product.commission_rate <= 0:
        found.append("Hoa hồng phải lớn hơn 0")
    if product.commission_end_at is not None and product.commission_end_at <= datetime.now(UTC):
        found.append("Hoa hồng đã hết hạn")
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


def credentials(account: AffiliateAccount) -> shopee.Credentials | None:
    """The account's Open API keys, when it is a Shopee account in use that has them."""
    if account.platform != "shopee" or not account.active or not account.app_id or not account.secret_encrypted:
        return None
    return shopee.Credentials(account.app_id, crypto.decrypt(account.secret_encrypted))


def page_account(db: DbSession, page: Fanpage | None) -> AffiliateAccount | None:
    """The Page's Shopee account, only while it still belongs to the Page's owner and is in use."""
    if page is None or page.shopee_account_id is None:
        return None
    account = db.get(AffiliateAccount, page.shopee_account_id)
    if account is None or account.owner_id != page.owner_id or credentials(account) is None:
        return None
    return account


def sub_ids(video_id: int, fanpage_id: int) -> list[str]:
    """What a link carries so an order names its video and Page (read back by affiliate_rounds.read_orders)."""
    return [f"v{video_id}", f"p{fanpage_id}"]


def article_sub_ids(article_id: int, fanpage_id: int) -> list[str]:
    """An article's link: "bv" so an order is never taken for the video with the same number."""
    return [f"bv{article_id}", f"p{fanpage_id}"]


def link_for(
    db: DbSession, product: AffiliateProduct, post: Publication, account: AffiliateAccount | None
) -> str | None:
    """The product's link under this post (a video's or an article's): the Page's account makes its own (once, then
    kept); without one, the link a member pasted. Raises ShopeeError when Shopee cannot make it."""
    if account is None:
        return product.url
    origin = product.page_url or product.url
    if not origin:
        return None
    target = {"article_id": post.article_id} if post.article_id else {"video_id": post.video_id}
    key = {"product_id": product.id, "account_id": account.id, **target, "fanpage_id": post.fanpage_id}
    kept = db.scalar(select(AffiliateLink).filter_by(**key))
    if kept is not None:
        return kept.url
    marks = (
        article_sub_ids(post.article_id, post.fanpage_id)
        if post.article_id
        else sub_ids(post.video_id, post.fanpage_id)
    )
    url = shopee.short_link(credentials(account), origin, marks)
    db.add(AffiliateLink(**key, url=url))
    db.flush()
    log.info("Made a Shopee link for product %s on Page %s", product.id, post.fanpage_id)
    return url


def article_products(db: DbSession, article_id: int) -> list[AffiliateProduct]:
    return list(
        db.scalars(
            select(AffiliateProduct)
            .join(ArticleAffiliateProduct)
            .where(ArticleAffiliateProduct.article_id == article_id)
            .order_by(AffiliateProduct.id)
        )
    )


def comment_text(db: DbSession, post: Publication) -> str:
    """The comment under the post: the video's pinned comment, then "name: link" per usable attached Shopee product
    that has a link for the post's Page. Raises ShopeeError when a link cannot be made."""
    account = page_account(db, db.get(Fanpage, post.fanpage_id) if post.fanpage_id else None)
    if post.article_id is not None:
        article = db.get(Article, post.article_id)
        products, opening = article_products(db, article.id), article.pinned_comment.strip()
    else:
        video = db.get(Video, post.video_id)
        products, opening = products_of(db, video.id), video.pinned_comment.strip()
    lines = []
    for product in products:
        if product.platform != "shopee" or not usable(product):
            continue
        link = link_for(db, product, post, account)
        if link:
            lines.append(f"{product.name}: {link}")
    return "\n".join(part for part in [opening, *lines] if part)[:MAX_COMMENT_LENGTH]
