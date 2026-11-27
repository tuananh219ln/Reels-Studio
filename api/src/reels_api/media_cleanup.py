"""Deleting a posted video's media files after `config.media_cleanup_days()` days, keeping the video, its numbers and
its MP4s (docs/decisions/2026-11-27-media-cleanup.md, brief in docs/specs/video-media-retention).

`choose` says which videos are due and when; `clean_video` deletes one video's files; `run_round` is the worker's round
and the `media-cleanup` command's body. Files only: no database row is deleted."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from . import analytics, config
from .errors import ApiError
from .models import ACTIVE_JOB_STATUSES, Job, PageQueueItem, Publication, Video, VideoPresence
from .sessions import now
from .storage import DirectoryStorage, get_storage

log = logging.getLogger(__name__)

# A post still to go out: its video keeps everything. "private" (a YouTube upload nobody made public) is not here, see
# the decision.
OPEN_POSTS = ("pending", "scheduled", "pending_link")
# A video this many times its Page's median 48-hour views is a winner whose files stay, so it can be copied.
KEEP_TIMES = 3
# At most this many videos per round, and only in these Vietnam hours, so the work is spread over the quiet night.
BATCH = 25
NIGHT_HOURS = range(2, 6)
PRESENCE = timedelta(minutes=2)
MESSAGE = "Media của video này đã được dọn ngày {day} (đăng quá {days} ngày), không còn ảnh, clip và lời đọc để {what}"


@dataclass
class Due:
    video_id: int
    due_at: datetime


def message(video: Video, what: str) -> str:
    when = video.media_cleaned_at.astimezone(analytics.VIETNAM).strftime("%d/%m/%Y") if video.media_cleaned_at else ""
    return MESSAGE.format(day=when, days=config.media_cleanup_days(), what=what)


def ensure_media(video: Video, what: str) -> None:
    """Refuse what needs a video's cleaned files (render, copy, shuffle) with the reason."""
    if video.media_cleaned_at is not None:
        raise ApiError(409, "media_cleaned", message(video, what))


def _winners(db: DbSession) -> set[int]:
    by_page = analytics.medians(db)
    posts = {
        mark.publication_id
        for mark in analytics.marks(db)
        if (times := analytics.times_median(mark.views, by_page.get(mark.fanpage_id))) is not None
        and times >= KEEP_TIMES
    }
    if not posts:
        return set()
    return set(db.scalars(select(Publication.video_id).where(Publication.id.in_(posts))))


def _copy_sources(db: DbSession, since: datetime) -> set[int]:
    """Videos a recent copy was made from: shuffles and TikTok versions say which."""
    rows = db.execute(select(Video.shuffled_from_id, Video.variant_of_id).where(Video.created_at > since))
    return {video_id for pair in rows for video_id in pair if video_id is not None}


def choose(
    db: DbSession, at: datetime, days: int | None = None, limit: int | None = None, video_id: int | None = None
) -> list[Due]:
    """The videos whose media is due at `at`, oldest post first (`video_id`: that one only)."""
    days = days or config.media_cleanup_days()
    cutoff = at - timedelta(days=days)
    last = func.max(Publication.published_at)
    query = (
        select(Video.id, last)
        .join(Publication, Publication.video_id == Video.id)
        .where(
            Video.review_status == "approved",
            Video.keep_media.is_(False),
            Video.media_cleaned_at.is_(None),
            Publication.status == "published",
        )
        .group_by(Video.id)
        .having(last <= cutoff)
        .order_by(last)
    )
    rows = db.execute(query.where(Video.id == video_id) if video_id is not None else query).all()
    if not rows:
        return []
    ids = [row[0] for row in rows]
    blocked = set(
        db.scalars(
            select(Publication.video_id).where(Publication.video_id.in_(ids), Publication.status.in_(OPEN_POSTS))
        )
    )
    blocked |= set(db.scalars(select(PageQueueItem.video_id).where(PageQueueItem.video_id.in_(ids))))
    blocked |= set(db.scalars(select(Job.video_id).where(Job.video_id.in_(ids), Job.status.in_(ACTIVE_JOB_STATUSES))))
    blocked |= set(
        db.scalars(
            select(VideoPresence.video_id).where(VideoPresence.video_id.in_(ids), VideoPresence.seen_at > at - PRESENCE)
        )
    )
    blocked |= _winners(db) | _copy_sources(db, at - timedelta(days=days))
    due = [Due(video_id, when + timedelta(days=days)) for video_id, when in rows if video_id not in blocked]
    return due[:limit] if limit else due


WARN = timedelta(days=3)


def soon(db: DbSession, at: datetime, video_id: int | None = None) -> list[Due]:
    """Videos that will be due within `WARN` (for the warning), with the time each falls due; none while the cleanup
    is off, since nothing then deletes anything."""
    if not config.media_cleanup_enabled():
        return []
    return choose(db, at + WARN, video_id=video_id)


def kept_keys(db: DbSession, video: Video) -> set[str]:
    """The files that stay: the video's MP4s (its own, the sent one, the ones posts were made from) and its thumbnail."""
    keys = {video.mp4_key, video.thumbnail_key}
    if video.source_mp4:
        keys.add(video.source_mp4.get("storage_key"))
    keys |= set(db.scalars(select(Publication.remote_mp4_key).where(Publication.video_id == video.id)))
    return {key for key in keys if key}


def clean_video(db: DbSession, storage: DirectoryStorage, video: Video, dry_run: bool = False) -> int:
    """Delete every file of the video's folder except `kept_keys`; the bytes freed (or that would be)."""
    folder = storage.path(f"videos/{video.id}")
    if not folder.is_dir():
        freed = 0
    else:
        keep = {storage.path(key) for key in kept_keys(db, video)}
        freed = 0
        for path in folder.iterdir():
            if not path.is_file() or path in keep:
                continue
            freed += path.stat().st_size
            if not dry_run:
                path.unlink(missing_ok=True)
    if not dry_run:
        video.media_cleaned_at, video.media_freed_bytes = now(), freed
    return freed


def run_round(factory: sessionmaker, dry_run: bool = False, limit: int = BATCH) -> list[str]:
    """One round: the first `limit` videos that are due. Each is committed alone, so a failure leaves the rest."""
    lines: list[str] = []
    storage = get_storage()
    with factory() as db:
        due = choose(db, now(), limit=limit)
    for item in due:
        try:
            with factory() as db:
                video = db.scalar(select(Video).where(Video.id == item.video_id).with_for_update())
                if video is None or video.media_cleaned_at is not None:
                    continue
                freed = clean_video(db, storage, video, dry_run)
                db.commit()
            lines.append(
                f"video {item.video_id}: {'sẽ giải phóng' if dry_run else 'đã giải phóng'} {freed / 1024**2:.1f} MB"
            )
        except Exception:
            log.exception("Could not clean the media of video %s", item.video_id)
    return lines


def run_due(factory: sessionmaker) -> None:
    """The worker's round: only when the owner turned it on, and only at night (Vietnam time)."""
    if not config.media_cleanup_enabled() or now().astimezone(analytics.VIETNAM).hour not in NIGHT_HOURS:
        return
    try:
        for line in run_round(factory):
            log.info("Media cleanup: %s", line)
    except Exception:
        log.exception("Could not run the media cleanup")


__all__ = ["Due", "choose", "clean_video", "ensure_media", "run_due", "run_round", "soon"]
