"""A post's views, shares, comments, reactions, watch time, reach and retention curve, read from Facebook by the worker between jobs.

Not a job: a reading only writes numbers, so it never locks the video, and it is not listed among the jobs. The worker
reads a few due posts per round (`measure_due`); a request never calls Facebook, "Cập nhật view" only asks for a reading.

When a post is due:
- first an hour after it went live, then once a day for `FOLLOW_DAYS` days, as `latest`;
- the first reading at least 48 hours after it went live, if within `SNAPSHOT_GRACE` of that mark, is also kept as `48h`
  and never rewritten, so posts are compared at the same age;
- when a member asked with "Cập nhật view", even after `FOLLOW_DAYS`.

A failed reading is recorded on the post and tried again a day later (or when asked), never in a loop.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from . import analytics, facebook, fanpages
from .facebook import FacebookError
from .models import PostMetrics, Publication, Video
from .sessions import now

log = logging.getLogger("reels_api.metrics")

FIRST_READING = timedelta(hours=1)
EVERY = timedelta(days=1)
FOLLOW_DAYS = 14
# Opening "Bài đăng" asks for a reading of a followed post whose last one is older than this.
ON_OPEN = timedelta(minutes=15)
SNAPSHOT = timedelta(hours=48)
SNAPSHOT_GRACE = timedelta(hours=24)
# Posts read per round of the worker (every few seconds); with INSIGHTS_TIMEOUT a dead Facebook holds the queue ~30 s.
BATCH = 3


def _live_at():
    # The SQL twin of videos.live_at.
    return func.coalesce(Publication.scheduled_at, Publication.published_at, Publication.created_at)


def _is_published(at: datetime):
    # The SQL twin of videos.is_published.
    return or_(
        Publication.status == "published",
        and_(Publication.status == "scheduled", Publication.scheduled_at <= at),
    )


def _has_snapshot():
    return exists().where(PostMetrics.publication_id == Publication.id, PostMetrics.window == "48h")


def _asked():
    tried = Publication.metrics_tried_at
    return and_(
        Publication.metrics_requested_at.is_not(None),
        or_(tried.is_(None), tried < Publication.metrics_requested_at),
    )


def ask_if_stale(db: DbSession) -> int:
    """Opening "Bài đăng": ask for a reading of each post still followed (an hour to `FOLLOW_DAYS` live) whose last
    reading is older than `ON_OPEN`, unless one is already asked for. Older posts stay on "Cập nhật view". Returns how
    many were asked; the caller commits."""
    at = now()
    live = _live_at()
    tried = Publication.metrics_tried_at
    rows = db.scalars(
        select(Publication).where(
            Publication.platform == "facebook",
            Publication.remote_id.is_not(None),
            _is_published(at),
            live <= at - FIRST_READING,
            live > at - timedelta(days=FOLLOW_DAYS),
            or_(tried.is_(None), tried <= at - ON_OPEN),
            ~_asked(),
        )
    ).all()
    for post in rows:
        post.metrics_requested_at = at
    return len(rows)


def ask_for_topic(db: DbSession, topic_id: int) -> int:
    """ "Cập nhật view" of a topic group: ask for a new reading of each of its posts that are out, whatever their age,
    unless one is already asked for. Returns how many were asked; the caller commits."""
    at = now()
    rows = db.scalars(
        select(Publication)
        .join(Video, Video.id == Publication.video_id)
        .where(
            Video.knowledge_topic_id == topic_id,
            Publication.platform == "facebook",
            Publication.remote_id.is_not(None),
            _is_published(at),
            ~_asked(),
        )
    ).all()
    for post in rows:
        post.metrics_requested_at = at
    return len(rows)


def due_posts(db: DbSession, limit: int = BATCH) -> list[Publication]:
    """The posts to read now: asked for first, then the longest unread."""
    at = now()
    live = _live_at()
    tried = Publication.metrics_tried_at
    asked = _asked()
    snapshot = and_(
        live <= at - SNAPSHOT,
        live > at - SNAPSHOT - SNAPSHOT_GRACE,
        ~_has_snapshot(),
        or_(tried.is_(None), tried < live + SNAPSHOT),
    )
    followed = and_(
        live <= at - FIRST_READING,
        live > at - timedelta(days=FOLLOW_DAYS),
        or_(tried.is_(None), tried <= at - EVERY),
    )
    query = (
        select(Publication)
        .where(
            Publication.platform == "facebook",
            Publication.remote_id.is_not(None),
            _is_published(at),
            or_(asked, snapshot, followed),
        )
        .order_by(asked.desc(), tried.asc().nulls_first(), Publication.id)
        .limit(limit)
    )
    return list(db.scalars(query))


def measure(db: DbSession, post: Publication) -> None:
    """Read the post's numbers once and save them, or what went wrong. Commits."""
    at = now()
    post.metrics_tried_at = at
    try:
        page = fanpages.load_page(db, post.fanpage_id)
        # An article ("Bài viết") is a feed post: reach is its main number, it has no views.
        reader = facebook.article_insights if post.article_id is not None else facebook.reel_insights
        numbers = reader(page, post.remote_id)
    except FacebookError as err:
        post.metrics_error = err.message
        db.commit()
        log.warning("Could not read the numbers of post %s: %s %s", post.id, err.message, err.detail)
        return
    post.metrics_error = None
    windows = {row.window: row for row in post.metrics}
    _save(post, windows.get("latest"), "latest", numbers, at)
    live = post.scheduled_at or post.published_at or post.created_at
    if "48h" not in windows and live + SNAPSHOT <= at <= live + SNAPSHOT + SNAPSHOT_GRACE:
        _save(post, None, "48h", numbers, at)
    db.commit()
    log.info("Read the numbers of post %s: %s", post.id, numbers)


def _save(post: Publication, row: PostMetrics | None, window: str, numbers: dict, at: datetime) -> None:
    if row is None:
        row = PostMetrics(window=window)
        post.metrics.append(row)
    row.views, row.shares = numbers["views"], numbers["shares"]
    row.comments, row.reactions = numbers["comments"], numbers["reactions"]
    for key in facebook.REEL_NUMBERS:
        setattr(row, key, numbers.get(key))
    row.retention = numbers.get("retention")
    row.measured_at = at


def measure_due(factory: sessionmaker) -> None:
    """One round of the worker. Nothing here may stop the queue: a failure is logged and the next round goes on."""
    try:
        with factory() as db:
            ids = [post.id for post in due_posts(db)]
    except Exception:
        log.exception("Could not look for posts to read the numbers of")
        return
    for post_id in ids:
        try:
            with factory() as db:
                post = db.get(Publication, post_id)
                if post is not None:
                    measure(db, post)
        except Exception:
            log.exception("Could not read the numbers of post %s", post_id)


def payload(post: Publication, by_page: dict[int | None, analytics.Median]) -> dict:
    """The numbers shown with a post: `latest` and `48h` (each null until read), the last error, `pending` while a
    reading asked for has not run yet, and what its 48-hour numbers mean against its Page's median (analytics.py)."""
    windows = {row.window: row for row in post.metrics}
    scenes = post.scene_marks or []
    length = scenes[-1]["end"] if scenes else None

    def numbers(row: PostMetrics | None) -> dict | None:
        if row is None:
            return None
        watched = row.avg_watch_ms / 1000 if row.avg_watch_ms is not None else None
        return {
            "views": row.views,
            "shares": row.shares,
            "comments": row.comments,
            "reactions": row.reactions,
            "plays": row.plays,
            "replays": row.replays,
            "reach": row.reach,
            "followers": row.followers,
            "avg_watch_seconds": round(watched, 2) if watched is not None else None,
            "view_time_seconds": round(row.view_time_ms / 1000) if row.view_time_ms is not None else None,
            # Replays count in the average, so it can pass the reel's length.
            "watch_ratio": round(watched / length, 3) if watched is not None and length else None,
            "retention": row.retention,
            "measured_at": row.measured_at.isoformat(),
        }

    asked = post.metrics_requested_at
    tried = post.metrics_tried_at
    mark = windows.get("48h")
    return {
        "latest": numbers(windows.get("latest")),
        "at_48h": numbers(windows.get("48h")),
        "error": post.metrics_error,
        "pending": asked is not None and (tried is None or tried < asked),
        # The posted MP4's length and scenes, for the retention curve; empty for a post made before they were kept.
        "length_seconds": length,
        "scenes": scenes,
        "analysis": analytics.of_post(post, mark.views if mark else None, mark.shares if mark else None, by_page),
    }
