"""Shopee's API in the worker's rounds, between jobs, like reading a post's numbers (metrics.py): a request never calls
Shopee, a failure is recorded where members see it and waits for the next round or a member, and nothing loops.

- Suggestions: a video's product ideas (`videos.affiliates`, written by the script) searched with the asking member's
  own Shopee account; the products that meet the rules, best first, become drafts of the team's list.
- The daily check: an approved product found through the API is read again once a day; one Shopee no longer offers, or
  that stopped meeting the rules, goes back to draft.
- Orders: each Shopee account's orders of the last days, read once a day, with the video and Page their link named.
"""

import logging
import math
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from . import affiliate, knowledge, shopee
from .models import (
    AffiliateAccount,
    AffiliateConversion,
    AffiliateProduct,
    AffiliateSuggestion,
    Fanpage,
    Video,
)
from .sessions import now

log = logging.getLogger("reels_api.affiliate_rounds")

SUGGEST_BATCH = 1
MAX_KEYWORDS = 5
PER_KEYWORD = 5
SEARCH_RESULTS = 20
CHECK_EVERY = timedelta(days=1)
CHECK_BATCH = 5
REPORT_EVERY = timedelta(days=1)
REPORT_BATCH = 2
REPORT_DAYS = 30  # orders change status for a while (pending, completed, cancelled), so the month is read again
SUB_ID = re.compile(r"^([vp])(\d+)$")


def _usable_account(db: DbSession, user_id: int | None) -> AffiliateAccount | None:
    if user_id is None:
        return None
    accounts = db.scalars(
        select(AffiliateAccount)
        .where(AffiliateAccount.owner_id == user_id, AffiliateAccount.platform == "shopee")
        .order_by(AffiliateAccount.id)
    )
    return next((account for account in accounts if affiliate.credentials(account)), None)


def ask_after_script(db: DbSession, video: Video, user_id: int) -> None:
    """A Facebook video's new script asks for suggestions when its writer has a Shopee account to search with."""
    if video.platform == "facebook" and video.affiliates and _usable_account(db, user_id):
        video.suggest_requested_at, video.suggest_by_id, video.suggest_error = now(), user_id, None


def _score(product: AffiliateProduct) -> float:
    # Money per sale first; sales and stars weigh in so a rare high-commission product does not always win.
    return product.price * product.commission_rate / 100 * product.rating * math.log10(product.sold + 10)


def _fill(product: AffiliateProduct, offer: shopee.Offer) -> None:
    product.name, product.shop_name, product.shop_type = offer.name, offer.shop_name, offer.shop_type
    product.rating, product.sold, product.price = offer.rating, offer.sold, max(offer.price, 1)
    product.commission_rate, product.commission_end_at = offer.commission_rate, offer.commission_end_at
    product.page_url, product.image_url = offer.page_url or product.page_url, offer.image_url or product.image_url
    product.offer_checked_at = now()


def suggest(db: DbSession, video: Video) -> None:
    """Search Shopee for the video's ideas and keep the best products meeting the rules. Commits."""
    keywords = [keyword.strip() for keyword in video.affiliates if keyword.strip()][:MAX_KEYWORDS]
    video.suggest_requested_at = None
    account = _usable_account(db, video.suggest_by_id)
    topic = knowledge.topic_of(db, video)
    if account is None or topic is None or not keywords:
        video.suggest_error = (
            "Người tìm không còn tài khoản Shopee đang dùng"
            if account is None
            else "Video chưa thuộc nhóm chủ đề nào"
            if topic is None
            else "Video chưa có gợi ý sản phẩm nào để tìm"
        )
        db.commit()
        return
    credentials = affiliate.credentials(account)
    found: list[tuple[str, list[AffiliateProduct]]] = []
    try:
        for keyword in keywords:
            offers = shopee.search(credentials, keyword, SEARCH_RESULTS)
            known = {
                product.shopee_item_id: product
                for product in db.scalars(
                    select(AffiliateProduct).where(
                        AffiliateProduct.shopee_item_id.in_([offer.item_id for offer in offers])
                    )
                )
            }
            candidates = []
            for offer in offers:
                product = known.get(offer.item_id) or AffiliateProduct(
                    platform="shopee",
                    shopee_item_id=offer.item_id,
                    knowledge_topic_id=topic.id,
                    topic=topic,
                    status="draft",
                    created_by_id=video.suggest_by_id,
                )
                if product.id is None:
                    _fill(product, offer)
                if not affiliate.problems(product):
                    candidates.append((product, offer))
            candidates.sort(key=lambda pair: _score(pair[0]), reverse=True)
            kept = []
            for product, offer in candidates[:PER_KEYWORD]:
                if product.id is None:
                    db.add(product)
                elif product.status != "approved":
                    # A draft takes Shopee's latest figures; an approved product changes only through the daily check.
                    _fill(product, offer)
                kept.append(product)
            found.append((keyword, kept))
    except shopee.ShopeeError as err:
        db.rollback()
        video = db.get(Video, video.id)
        video.suggest_requested_at, video.suggest_error = None, err.message
        db.commit()
        log.warning("Could not search Shopee for video %s: %s %s", video.id, err.message, err.detail)
        return
    db.flush()
    db.query(AffiliateSuggestion).filter(AffiliateSuggestion.video_id == video.id).delete()
    for keyword, products in found:
        for rank, product in enumerate(products, start=1):
            db.add(AffiliateSuggestion(video_id=video.id, keyword=keyword[:200], product_id=product.id, rank=rank))
    video.suggested_at, video.suggest_error = now(), None
    db.commit()
    log.info("Suggested %d products for video %s", sum(len(products) for _, products in found), video.id)


def check_offer(db: DbSession, product: AffiliateProduct) -> None:
    """Read an approved product again; it goes back to draft when Shopee no longer offers it or it fails the rules.
    Commits."""
    product.offer_checked_at = now()
    account = _usable_account(db, product.created_by_id) or next(
        (
            account
            for account in db.scalars(
                select(AffiliateAccount).where(AffiliateAccount.platform == "shopee").order_by(AffiliateAccount.id)
            )
            if affiliate.credentials(account)
        ),
        None,
    )
    if account is None:
        db.commit()
        return
    try:
        offer = shopee.offer(affiliate.credentials(account), product.shopee_item_id)
    except shopee.ShopeeError as err:
        db.commit()
        log.warning("Could not check product %s: %s %s", product.id, err.message, err.detail)
        return
    if offer is None:
        product.status, product.checked_at, product.checked_by_id = "draft", None, None
        log.info("Product %s is no longer offered, back to draft", product.id)
    else:
        _fill(product, offer)
        if affiliate.problems(product):
            product.status, product.checked_at, product.checked_by_id = "draft", None, None
            log.info("Product %s no longer meets the rules, back to draft", product.id)
    db.commit()


def _target(db: DbSession, sub_ids: list[str]) -> tuple[int | None, int | None]:
    found = {}
    for sub_id in sub_ids:
        match = SUB_ID.match(sub_id)
        if match:
            found[match.group(1)] = int(match.group(2))
    video_id = found.get("v") if found.get("v") and db.get(Video, found["v"]) else None
    fanpage_id = found.get("p") if found.get("p") and db.get(Fanpage, found["p"]) else None
    return video_id, fanpage_id


def read_orders(db: DbSession, account: AffiliateAccount) -> None:
    """Keep the account's orders of the last REPORT_DAYS. Commits."""
    account.report_read_at = now()
    credentials = affiliate.credentials(account)
    if credentials is None:
        db.commit()
        return
    end = datetime.now(UTC)
    try:
        orders = shopee.conversions(credentials, end - timedelta(days=REPORT_DAYS), end)
    except shopee.ShopeeError as err:
        account.report_error = err.message
        db.commit()
        log.warning("Could not read orders of account %s: %s %s", account.id, err.message, err.detail)
        return
    kept = {
        row.external_id: row
        for row in db.scalars(
            select(AffiliateConversion).where(
                AffiliateConversion.account_id == account.id,
                AffiliateConversion.external_id.in_([order.external_id for order in orders]),
            )
        )
    }
    for order in orders:
        row = kept.get(order.external_id)
        if row is None:
            row = AffiliateConversion(account_id=account.id, external_id=order.external_id)
            db.add(row)
            kept[order.external_id] = row
        row.video_id, row.fanpage_id = _target(db, order.sub_ids)
        row.purchased_at, row.item_name = order.purchased_at, order.item_name or "Sản phẩm"
        row.commission, row.status, row.read_at = order.commission, order.status, now()
    account.report_error = None
    db.commit()
    log.info("Read %d orders of account %s", len(orders), account.id)


def _each(factory: sessionmaker, label: str, find, work) -> None:
    try:
        with factory() as db:
            ids = find(db)
    except Exception:
        log.exception("Could not look for %s", label)
        return
    for row_id in ids:
        try:
            with factory() as db:
                work(db, row_id)
        except Exception:
            log.exception("Could not do %s %s", label, row_id)


def run_round(factory: sessionmaker) -> None:
    """One round of the worker. Nothing here may stop the queue: a failure is logged and the next round goes on."""
    at = now()
    _each(
        factory,
        "suggestions",
        lambda db: list(
            db.scalars(
                select(Video.id)
                .where(Video.suggest_requested_at.is_not(None))
                .order_by(Video.suggest_requested_at)
                .limit(SUGGEST_BATCH)
            )
        ),
        lambda db, video_id: suggest(db, db.get(Video, video_id)),
    )
    _each(
        factory,
        "product checks",
        lambda db: list(
            db.scalars(
                select(AffiliateProduct.id)
                .where(
                    AffiliateProduct.status == "approved",
                    AffiliateProduct.shopee_item_id.is_not(None),
                    or_(
                        AffiliateProduct.offer_checked_at.is_(None),
                        AffiliateProduct.offer_checked_at <= at - CHECK_EVERY,
                    ),
                )
                .order_by(AffiliateProduct.offer_checked_at.nulls_first(), AffiliateProduct.id)
                .limit(CHECK_BATCH)
            )
        ),
        lambda db, product_id: check_offer(db, db.get(AffiliateProduct, product_id)),
    )
    _each(
        factory,
        "orders",
        lambda db: list(
            db.scalars(
                select(AffiliateAccount.id)
                .where(
                    AffiliateAccount.platform == "shopee",
                    AffiliateAccount.active.is_(True),
                    AffiliateAccount.secret_encrypted.is_not(None),
                    or_(
                        AffiliateAccount.report_read_at.is_(None),
                        AffiliateAccount.report_read_at <= at - REPORT_EVERY,
                    ),
                )
                .order_by(AffiliateAccount.report_read_at.nulls_first(), AffiliateAccount.id)
                .limit(REPORT_BATCH)
            )
        ),
        lambda db, account_id: read_orders(db, db.get(AffiliateAccount, account_id)),
    )
