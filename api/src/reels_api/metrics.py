"""A post's numbers, read by the worker between jobs: a Facebook reel's views, shares, comments, reactions, watch time,
reach and retention curve (Video Insights), a YouTube Short's views, likes and comments (Data API, `YOUTUBE_API_KEY`).

Not a job: a reading only writes numbers, so it never locks the video, and it is not listed among the jobs. The worker
reads a few due posts per round (`measure_due`); a request never calls Facebook, "Cập nhật view" only asks for a reading.

When a post is due ("Bài đăng" part 2, docs/decisions/2026-11-14-post-readings-schedule.md): as soon as it is live,
then on `next_snapshot_at` (next_reading: hourly in the first 48 hours, every 15 minutes while it is trending, then
every 6 hours, daily, weekly, never after 90 days, each mark read on the dot), or when a member asked. Every reading
adds a `post_metric_snapshots` row and settles the marks it has passed (settle_marks). Facebook's `latest` and `48h`
rows of `post_metrics` are kept as before for the KPIs and medians.

A failed reading is recorded on the post and tried again an hour later, never in a loop.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from . import analytics, facebook, fanpages, youtube
from .facebook import FacebookError
from .models import PostMetrics, PostMetricSnapshot, Publication, Video
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


def _live(post: Publication) -> datetime:
    # videos.live_at, which this module cannot import (videos imports it).
    return post.scheduled_at or post.published_at or post.created_at


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


def readable(at: datetime, youtube_on: bool | None = None):
    """Posts the worker has a reader for: a Facebook reel it knows the id of, a YouTube Short with the team's key."""
    youtube_on = youtube.enabled() if youtube_on is None else youtube_on
    facebook_post = and_(
        Publication.platform == "facebook",
        Publication.remote_id.is_not(None),
        _is_published(at),
        # "Bỏ qua" on "Chưa khớp": hidden and no longer read.
        Publication.match_status != "ignored",
    )
    if not youtube_on:
        return facebook_post
    youtube_post = and_(
        Publication.platform == "youtube",
        Publication.external_id.is_not(None),
        Publication.match_status != "ignored",
        # A removed Short is looked at again for a week, in case it comes back.
        or_(Publication.status == "published", Publication.status == "deleted"),
    )
    return or_(facebook_post, youtube_post)


def due_posts(db: DbSession, limit: int = BATCH, platform: str = "facebook") -> list[Publication]:
    """The posts of `platform` to read now: asked for first, then the most overdue. A post never read is due as soon as
    it is live (within MAX_AGE); after that its `next_snapshot_at` says when (next_reading)."""
    at = now()
    live = _live_at()
    asked = _asked()
    first = and_(
        Publication.next_snapshot_at.is_(None),
        Publication.metrics_tried_at.is_(None),
        Publication.status != "deleted",
        live <= at,
        live > at - MAX_AGE,
    )
    scheduled = and_(Publication.next_snapshot_at.is_not(None), Publication.next_snapshot_at <= at)
    query = (
        select(Publication)
        .where(
            Publication.platform == platform,
            readable(at),
            or_(asked, first, scheduled),
        )
        .order_by(asked.desc(), Publication.next_snapshot_at.asc().nulls_first(), Publication.id)
        .limit(limit)
    )
    return list(db.scalars(query))


# --- The schedule (spec §3.1) and the marks (§3.5) ---

MAX_AGE = timedelta(days=90)
TRENDING_EVERY = timedelta(minutes=15)
TRENDING_GROWTH = 1.5
TRENDING_VIEWS = 2000
RETRY_LATER = timedelta(hours=1)
GONE_CONFIRM = timedelta(hours=1)
REMOVED_EVERY = timedelta(hours=24)
REMOVED_FOLLOW = timedelta(days=7)
# (age up to which it applies, reading every, marks read on the dot within it)
SCHEDULE = (
    (timedelta(hours=48), timedelta(hours=1), (timedelta(hours=1), timedelta(hours=24), timedelta(hours=48))),
    (timedelta(days=7), timedelta(hours=6), (timedelta(days=7),)),
    (timedelta(days=30), timedelta(hours=24), (timedelta(days=30),)),
    (MAX_AGE, timedelta(days=7), ()),
)
# A mark (hours) is the reading within its tolerance after it, else one between the two readings around it.
MARKS = {"1h": (1, 0.5), "24h": (24, 2), "48h": (48, 3), "7d": (168, 12), "30d": (720, 24)}


def next_reading(live: datetime, at: datetime, trending: bool = False) -> datetime | None:
    """When to read a post next: hourly in its first 48 hours (every 15 minutes while trending), then every 6 hours to
    7 days, daily to 30 days, weekly to 90 days, then never; a mark falling before the next reading is read on it."""
    age = at - live
    for until, every, marks in SCHEDULE:
        if age < until:
            step = TRENDING_EVERY if trending and until == SCHEDULE[0][0] else every
            following = at + step
            for mark in marks:
                if at < live + mark < following:
                    following = live + mark
            return following
    return None


def is_trending(live: datetime, at: datetime, before: int | None, views: int | None) -> bool:
    """In its first 48 hours, up 50 % or 2.000 views since the reading before."""
    if at - live >= SCHEDULE[0][0] or before is None or views is None:
        return False
    return views - before >= TRENDING_VIEWS or (before > 0 and views >= before * TRENDING_GROWTH)


def settle_marks(db: DbSession, post: Publication, at: datetime) -> None:
    """Set each mark the post is past and that is not set yet; a mark once set stays (§3.5)."""
    live = _live(post)
    age = (at - live).total_seconds() / 3600
    readings = [
        (float(row.hours_since_publish), row.views)
        for row in db.scalars(
            select(PostMetricSnapshot)
            .where(PostMetricSnapshot.publication_id == post.id)
            .order_by(PostMetricSnapshot.captured_at)
        )
        if row.hours_since_publish is not None and row.views is not None
    ]
    estimated = list(post.marks_estimated or [])
    for name, (hours, tolerance) in MARKS.items():
        if getattr(post, f"views_{name}") is not None or age < hours:
            continue
        near = [(hour, views) for hour, views in readings if hours <= hour <= hours + tolerance]
        if near:
            setattr(post, f"views_{name}", min(near, key=lambda row: row[0] - hours)[1])
            continue
        if age <= hours + tolerance:
            continue  # a reading may still land within the tolerance
        before = [row for row in readings if row[0] < hours]
        after = [row for row in readings if row[0] > hours]
        if before and after:
            (h0, v0), (h1, v1) = before[-1], after[0]
            setattr(post, f"views_{name}", round(v0 + (v1 - v0) * (hours - h0) / (h1 - h0)))
            estimated.append(name)
    post.marks_estimated = estimated


def _record(db: DbSession, post: Publication, numbers: dict, at: datetime, source: str) -> None:
    """A reading that worked: a snapshot, the marks, and when to read next."""
    live = _live(post)
    before = db.scalar(
        select(PostMetricSnapshot.views)
        .where(PostMetricSnapshot.publication_id == post.id)
        .order_by(PostMetricSnapshot.captured_at.desc())
        .limit(1)
    )
    db.add(
        PostMetricSnapshot(
            publication_id=post.id,
            captured_at=at,
            hours_since_publish=hours_since(live, at),
            views=numbers.get("views"),
            likes=numbers.get("likes", numbers.get("reactions")),
            comments=numbers.get("comments"),
            shares=numbers.get("shares"),
            raw={"source": source},
        )
    )
    db.flush()
    settle_marks(db, post, at)
    post.next_snapshot_at = next_reading(live, at, is_trending(live, at, before, numbers.get("views")))


def measure(db: DbSession, post: Publication) -> None:
    """Read a Facebook post's numbers once and save them, or what went wrong. Commits."""
    at = now()
    post.metrics_tried_at = at
    try:
        page = fanpages.load_page(db, post.fanpage_id)
        # An article ("Bài viết") is a feed post: reach is its main number, it has no views.
        reader = facebook.article_insights if post.article_id is not None else facebook.reel_insights
        numbers = reader(page, post.remote_id)
    except FacebookError as err:
        post.metrics_error = err.message
        # Tried again in an hour. A reel Facebook does not read is never taken for removed here: only a check
        # decides that (2026-11-13-unreadable-is-not-deleted).
        post.next_snapshot_at = at + RETRY_LATER
        db.commit()
        log.warning("Could not read the numbers of post %s: %s %s", post.id, err.message, err.detail)
        return
    post.metrics_error = None
    windows = {row.window: row for row in post.metrics}
    _save(post, windows.get("latest"), "latest", numbers, at)
    live = post.scheduled_at or post.published_at or post.created_at
    if "48h" not in windows and live + SNAPSHOT <= at <= live + SNAPSHOT + SNAPSHOT_GRACE:
        _save(post, None, "48h", numbers, at)
    _record(db, post, numbers, at, "facebook")
    db.commit()
    log.info("Read the numbers of post %s: %s", post.id, numbers)


def measure_youtube(db: DbSession, posts: list[Publication]) -> None:
    """Read YouTube Shorts in one call. A Short missing twice, an hour apart, is removed (§3.6); one found again is
    published again. A call that fails reads nothing and tries again in an hour. Commits."""
    if not posts:
        return
    at = now()
    for post in posts:
        post.metrics_tried_at = at
    try:
        items = youtube.videos([post.external_id for post in posts])
    except youtube.YouTubeError as err:
        for post in posts:
            post.metrics_error, post.next_snapshot_at = str(err), at + RETRY_LATER
        db.commit()
        log.warning("Could not read YouTube: %s", err)
        return
    for post in posts:
        item = items.get(post.external_id)
        if item is None:
            _missing(post, at)
            continue
        post.metrics_error, post.gone_since = None, None
        if post.status == "deleted" and post.closed_by_id is None:
            post.status, post.closed_at = "published", None
        published = youtube.published_at(item)
        if published is not None and post.published_at_source != "user":
            post.published_at, post.published_at_source = published, "api"
        _record(db, post, youtube.numbers(item), at, "youtube")
    db.commit()


def _missing(post: Publication, at: datetime) -> None:
    if post.status == "deleted":
        follow = post.closed_at is not None and at - post.closed_at < REMOVED_FOLLOW
        post.next_snapshot_at = at + REMOVED_EVERY if follow else None
        return
    if post.gone_since is None:
        post.gone_since, post.next_snapshot_at = at, at + GONE_CONFIRM
        return
    if at - post.gone_since < GONE_CONFIRM:
        post.next_snapshot_at = post.gone_since + GONE_CONFIRM
        return
    post.status, post.closed_at, post.closed_by_id = "deleted", at, None
    post.metrics_error = "YouTube không còn hiện video (đã xóa hoặc để riêng tư)"
    post.next_snapshot_at = at + REMOVED_EVERY


def hours_since(live: datetime | None, at: datetime) -> float | None:
    """How old the post was at a reading, in hours, two decimals; None before it has a time."""
    if live is None:
        return None
    return round(max(0.0, (at - live).total_seconds() / 3600), 2)


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
    """One round of the worker: a few Facebook posts one by one, and the due YouTube Shorts in one call. Nothing here
    may stop the queue: a failure is logged and the next round goes on."""
    try:
        with factory() as db:
            ids = [post.id for post in due_posts(db)]
            shorts = [post.id for post in due_posts(db, youtube.BATCH, "youtube")] if youtube.enabled() else []
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
    if shorts:
        try:
            with factory() as db:
                measure_youtube(db, [db.get(Publication, post_id) for post_id in shorts])
        except Exception:
            log.exception("Could not read the numbers of YouTube posts %s", shorts)


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
