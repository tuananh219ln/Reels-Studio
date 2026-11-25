"""Reels posted on a Page outside the app (Meta Business Suite, or Instagram's app for the Page's linked account) imported as posts, matched to videos and followed like
the app's own ("Bài đăng" part 3, spec §4.3; docs/decisions/2026-11-14-meta-suite-sync.md).

The worker, between jobs, imports each Page in use with "Đồng bộ bài ngoài app" on, once an hour or when "Đồng bộ ngay"
asked: the reels created since its last import (less 2 hours, so none is missed; 30 days back the first time). A reel
the app already has (its own, or one imported before) is skipped. Its numbers are read at once, matched or not."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from . import facebook, fanpages, instagram, post_links
from .facebook import FacebookError
from .models import Fanpage, Publication
from .sessions import now

log = logging.getLogger("reels_api.meta_sync")

EVERY = timedelta(minutes=60)
OVERLAP = timedelta(hours=2)
FIRST_BACK = timedelta(days=30)
# Pages imported per round of the worker.
BATCH = 2


def due_pages(db: DbSession, limit: int = BATCH) -> list[Fanpage]:
    at = now()
    asked = and_(
        Fanpage.sync_requested_at.is_not(None),
        or_(Fanpage.sync_tried_at.is_(None), Fanpage.sync_tried_at < Fanpage.sync_requested_at),
    )
    hourly = and_(
        Fanpage.sync_external_posts.is_(True),
        or_(Fanpage.sync_tried_at.is_(None), Fanpage.sync_tried_at <= at - EVERY),
    )
    return list(
        db.scalars(
            select(Fanpage)
            .where(Fanpage.active.is_(True), or_(asked, hourly))
            .order_by(asked.desc(), Fanpage.sync_tried_at.asc().nulls_first(), Fanpage.id)
            .limit(limit)
        )
    )


def known(db: DbSession, reel_id: str) -> bool:
    return (
        db.scalar(
            select(Publication.id)
            .where(
                Publication.platform == "facebook",
                or_(Publication.external_id == reel_id, Publication.remote_id == reel_id),
            )
            .limit(1)
        )
        is not None
    )


def known_instagram(db: DbSession, media_id: str) -> bool:
    return (
        db.scalar(
            select(Publication.id)
            .where(Publication.platform == "instagram", Publication.external_id == media_id)
            .limit(1)
        )
        is not None
    )


def _number(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def import_reel(db: DbSession, row: Fanpage, reel: dict, owner_id: int) -> Publication:
    """One reel as a published `meta_suite` post, matched to a video when it can be: by itself at 85 % and 10 points
    ahead of the next ("confirmed"), else suggested from 50 % or left "unmatched" for "Chưa khớp"."""
    caption = str(reel.get("description") or "")
    published_at: datetime = reel["created_time"]
    duration = _number(reel.get("length"))
    match = post_links.match_video(db, caption, published_at, duration)
    post = Publication(
        video_id=match.video.id if match.confirmed else None,
        platform="facebook",
        fanpage_id=row.id,
        status="published",
        source="meta_suite",
        remote_id=reel["id"],
        external_id=reel["id"],
        post_url=facebook.reel_url(reel["id"]),
        published_at=published_at,
        published_at_source="api",
        caption=caption[:5000],
        duration_sec=duration,
        thumbnail_url=reel.get("picture") or None,
        match_status="confirmed" if match.confirmed else "suggested" if match.suggestions else "unmatched",
        match_score=match.score,
        suggested_video_id=match.suggestions[0][0].id if match.suggestions and not match.confirmed else None,
        created_by_id=owner_id,
    )
    db.add(post)
    db.flush()
    return post


def import_instagram_reel(db: DbSession, row: Fanpage, reel: dict, owner_id: int) -> Publication:
    """One Instagram Reel as a published `meta_suite` post, matched like a Facebook reel (Instagram gives no length)."""
    caption = reel["caption"]
    match = post_links.match_video(db, caption, reel["created_time"], None)
    post = Publication(
        video_id=match.video.id if match.confirmed else None,
        platform="instagram",
        fanpage_id=row.id,
        status="published",
        source="meta_suite",
        external_id=reel["id"],
        post_url=reel["permalink"],
        published_at=reel["created_time"],
        published_at_source="api",
        caption=caption[:5000],
        thumbnail_url=reel["thumbnail_url"],
        match_status="confirmed" if match.confirmed else "suggested" if match.suggestions else "unmatched",
        match_score=match.score,
        suggested_video_id=match.suggestions[0][0].id if match.suggestions and not match.confirmed else None,
        created_by_id=owner_id,
    )
    db.add(post)
    db.flush()
    return post


def _import_facebook(db: DbSession, row: Fanpage, owner_id: int, since: datetime) -> tuple[int, str | None]:
    try:
        reels = facebook.page_reels(fanpages.load_page(db, row.id), since)
    except FacebookError as err:
        log.warning("Could not import the reels of Page %s: %s %s", row.id, err.message, err.detail)
        return 0, err.message
    added = 0
    for reel in reels:
        if known(db, reel["id"]):
            continue
        import_reel(db, row, reel, owner_id)
        added += 1
    return added, None


def _import_instagram(db: DbSession, row: Fanpage, owner_id: int, since: datetime) -> tuple[int, str | None]:
    if not row.instagram_user_id:
        return 0, None
    try:
        reels = instagram.account_reels(fanpages.load_page(db, row.id), row.instagram_user_id, since)
    except FacebookError as err:
        log.warning("Could not import the Instagram reels of Page %s: %s %s", row.id, err.message, err.detail)
        return 0, f"Instagram: {err.message}"
    added = 0
    for reel in reels:
        if known_instagram(db, reel["id"]):
            continue
        import_instagram_reel(db, row, reel, owner_id)
        added += 1
    return added, None


def sync_page(db: DbSession, row: Fanpage) -> int:
    """Import the Page's new reels, and its linked Instagram account's; how many. Records the time and what went wrong
    (the first failure; one platform failing does not stop the other); commits. The window moves on only when both
    read, so a platform that failed is read from the same time next round (what is known is skipped)."""
    at = now()
    row.sync_tried_at = at
    owner_id = row.owner_id or row.updated_by_id
    if owner_id is None:
        row.sync_error = "Page chưa có chủ để ghi bài"
        db.commit()
        return 0
    since = row.last_synced_at - OVERLAP if row.last_synced_at else at - FIRST_BACK
    added, error = _import_facebook(db, row, owner_id, since)
    more, instagram_error = _import_instagram(db, row, owner_id, since)
    added += more
    error = error or instagram_error
    row.sync_error = error
    if error is None:
        row.last_synced_at = at
    db.commit()
    log.info("Imported %s reels of Page %s", added, row.id)
    return added


def run_due(factory: sessionmaker) -> None:
    """One round of the worker; nothing here may stop the queue."""
    try:
        with factory() as db:
            ids = [row.id for row in due_pages(db)]
    except Exception:
        log.exception("Could not look for Pages to import")
        return
    for page_id in ids:
        try:
            with factory() as db:
                row = db.get(Fanpage, page_id)
                if row is not None:
                    sync_page(db, row)
        except Exception:
            log.exception("Could not import the reels of Page %s", page_id)
