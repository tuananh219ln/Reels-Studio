"""What the posts' numbers mean: the median views of each Page, how far a post is from it, and the weekly KPIs.

All of it comes from the `48h` readings (metrics.py), so posts are compared at the same age, and is worked out when asked:
nothing here is stored or calls Facebook. The share/view goal is the team's (docs/content.md): 0.2 %. There is no "Video
thắng" flag: it was dropped on 2026-11-03 (docs/decisions.md).

- The median is per Page, over its posts that went live in the last `MEDIAN_DAYS` days: a growing Page would make every
  new video look far above its first weeks, and a large Page would do the same to a small one.
- Under `MIN_SAMPLES` measured posts a Page's median means little, so no post is compared with it.
- A week runs Monday to Sunday in Vietnam time, like everything the app shows.
- A post taken down (deleted or cancelled) counts in neither: its numbers stay with it as history, but a reel Facebook
  hid or that came down early measures the fault, not the content.
"""

import statistics
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from .models import PostMetrics, Publication
from .sessions import now

MEDIAN_DAYS = 60
# Statuses whose 48-hour numbers stay with the post but feed no median or KPI.
TAKEN_DOWN = ("deleted", "cancelled")
MIN_SAMPLES = 5
SHARE_GOAL = 0.002
# Vietnam has no daylight saving time, so a fixed offset needs no time zone database in the images.
VIETNAM = timezone(timedelta(hours=7), "Asia/Ho_Chi_Minh")


@dataclass(frozen=True)
class Median:
    views: float | None
    samples: int


@dataclass(frozen=True)
class Mark:
    """A post's `48h` reading, with what the analysis needs to know about the post."""

    publication_id: int
    fanpage_id: int | None
    live_at: datetime
    views: int
    shares: int | None


def _marks(db: DbSession, since: datetime | None = None) -> list[Mark]:
    live = func.coalesce(Publication.scheduled_at, Publication.published_at, Publication.created_at)
    query = (
        select(Publication.id, Publication.fanpage_id, live, PostMetrics.views, PostMetrics.shares)
        .join(PostMetrics, PostMetrics.publication_id == Publication.id)
        .where(
            PostMetrics.window == "48h",
            PostMetrics.views.is_not(None),
            Publication.platform == "facebook",
            Publication.video_id.is_not(None),
            Publication.status.not_in(TAKEN_DOWN),
        )
    )
    if since is not None:
        query = query.where(live > since)
    return [Mark(*row) for row in db.execute(query)]


def medians(db: DbSession) -> dict[int | None, Median]:
    """Each Page's median views at 48 hours over its posts of the last `MEDIAN_DAYS` days, by fanpage_id."""
    views: dict[int | None, list[int]] = {}
    for mark in _marks(db, now() - timedelta(days=MEDIAN_DAYS)):
        views.setdefault(mark.fanpage_id, []).append(mark.views)
    return {page: Median(statistics.median(values), len(values)) for page, values in views.items()}


def share_rate(views: int | None, shares: int | None) -> float | None:
    if views is None or shares is None or views <= 0:
        return None
    return shares / views


def times_median(views: int, median: Median | None) -> float | None:
    """How many times its Page's median a post's views are; None while the median is not meaningful."""
    if median is None or median.samples < MIN_SAMPLES or not median.views:
        return None
    return views / median.views


def of_post(post: Publication, mark_views: int | None, mark_shares: int | None, by_page: dict) -> dict:
    """The analysis shown with a post. Its Page's median and sample count are given even before the post's own mark,
    so the page can say "chưa đủ dữ liệu" or how far the post is."""
    median = by_page.get(post.fanpage_id)
    times = times_median(mark_views, median) if mark_views is not None else None
    return {
        "median_views": median.views if median else None,
        "samples": median.samples if median else 0,
        "times_median": round(times, 1) if times is not None else None,
        "share_rate": share_rate(mark_views, mark_shares),
    }


def week_start(at: datetime) -> datetime:
    """Monday 00:00 in Vietnam of the week holding `at`, as a UTC time."""
    local = at.astimezone(VIETNAM)
    monday = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return monday.astimezone(UTC)


def _week(marks: list[Mark], start: datetime) -> dict:
    """The posts that went live in the week starting at `start` and have their 48-hour numbers."""
    end = start + timedelta(days=7)
    week = [mark for mark in marks if start <= mark.live_at < end]
    rates = [share_rate(mark.views, mark.shares) for mark in week]
    rated = [rate for rate in rates if rate is not None]
    met = sum(1 for rate in rated if rate >= SHARE_GOAL)
    return {
        "start": start.astimezone(VIETNAM).date().isoformat(),
        "measured": len(week),
        "median_views": statistics.median([mark.views for mark in week]) if week else None,
        "share_goal_met": met,
        "share_goal_rate": met / len(rated) if rated else None,
    }


def kpis(db: DbSession) -> dict:
    """This week's and last week's KPIs, and the rules they follow, for the strip on "Bài đăng"."""
    this_week = week_start(now())
    by_page = medians(db)
    marks = _marks(db, this_week - timedelta(days=9))  # a little more than last week: posts live before it start
    return {
        "this_week": _week(marks, this_week),
        "last_week": _week(marks, this_week - timedelta(days=7)),
        "rules": {
            "median_days": MEDIAN_DAYS,
            "min_samples": MIN_SAMPLES,
            "share_goal": SHARE_GOAL,
        },
        "enough_data": any(median.samples >= MIN_SAMPLES for median in by_page.values()),
    }


# --- Articles ("Bài viết") ---
# A feed post has no views: its reach is the main number. Its median is its Page's, over articles only (a reel's views
# and an article's reach are not the same count). With a small reach one share is a large share, so the share/reach
# rate is read only from MIN_RATED_REACH people.
MIN_RATED_REACH = 50
WINNER_TIMES = 10


def _article_marks(db: DbSession, since: datetime) -> list[tuple[int | None, int]]:
    live = func.coalesce(Publication.scheduled_at, Publication.published_at, Publication.created_at)
    query = (
        select(Publication.fanpage_id, PostMetrics.reach)
        .join(PostMetrics, PostMetrics.publication_id == Publication.id)
        .where(
            PostMetrics.window == "48h",
            PostMetrics.reach.is_not(None),
            Publication.platform == "facebook",
            Publication.article_id.is_not(None),
            Publication.status.not_in(TAKEN_DOWN),
            live > since,
        )
    )
    return [(page, reach) for page, reach in db.execute(query)]


def article_medians(db: DbSession) -> dict[int | None, Median]:
    """Each Page's median reach at 48 hours over its articles of the last `MEDIAN_DAYS` days (`Median.views` holds it)."""
    reach: dict[int | None, list[int]] = {}
    for page, value in _article_marks(db, now() - timedelta(days=MEDIAN_DAYS)):
        reach.setdefault(page, []).append(value)
    return {page: Median(statistics.median(values), len(values)) for page, values in reach.items()}


def article_rate(reach: int | None, shares: int | None) -> float | None:
    if reach is None or reach < MIN_RATED_REACH:
        return None
    return share_rate(reach, shares)


def of_article_post(post: Publication, mark_reach: int | None, mark_shares: int | None, by_page: dict) -> dict:
    median = by_page.get(post.fanpage_id)
    times = times_median(mark_reach, median) if mark_reach is not None else None
    return {
        "median_reach": median.views if median else None,
        "samples": median.samples if median else 0,
        "times_median": round(times, 1) if times is not None else None,
        "share_rate": article_rate(mark_reach, mark_shares),
        # Drawn bold when shown; never stored (decisions 2026-11-03).
        "standout": times is not None and times >= WINNER_TIMES,
    }
