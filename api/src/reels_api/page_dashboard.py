"""One Page's dashboard on "Quản lý Page" (`/fanpages/{id}`), shaped like Facebook's Professional Dashboard but built only
from what the app already keeps: the daily Page Insights (`fanpage_insights`), the daily followers (`fanpage_followers`)
and the numbers of the posts the app made (`post_metrics`). Nothing here calls Facebook or is stored.

A period is the last 7, 28 or 90 days in Vietnam time, today included, like the 7 days on the Page's card. Each figure
is compared with the period of the same length just before it. Numbers Facebook does not give (followers against
non-followers, traffic sources, unfollows, 3-second views) are left out rather than guessed.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session as DbSession

from . import analytics, facebook, fanpages, page_queue
from .models import Fanpage, FanpageFollowers, FanpageInsights, PostMetrics, Publication, Video
from .sessions import now
from .videos import LIVE_POST_STATUSES, is_published, live_at, split_scenes, thumbnail_url, video_name

PERIODS = (7, 28, 90)
# How far ahead the "Đã lên lịch" strip and the "Lịch đăng" tab look.
AHEAD = timedelta(days=7)


@dataclass(frozen=True)
class Period:
    start: date
    end: date  # included

    def days(self) -> list[date]:
        return [self.start + timedelta(days=n) for n in range((self.end - self.start).days + 1)]


def periods(days: int, today: date) -> tuple[Period, Period]:
    current = Period(today - timedelta(days=days - 1), today)
    return current, Period(current.start - timedelta(days=days), current.start - timedelta(days=1))


def change(value: float | None, previous: float | None) -> float | None:
    """The change against the previous period as a fraction (0.25 is +25 %); None when there is nothing to compare."""
    if value is None or previous is None or previous <= 0:
        return None
    return round((value - previous) / previous, 4)


def figure(value: float | None, previous: float | None) -> dict:
    return {"value": value, "previous": previous, "change": change(value, previous)}


def _sum(values: list[int | None]) -> int | None:
    known = [value for value in values if value is not None]
    return sum(known) if known else None


def _insights(db: DbSession, page_id: int, start: date, end: date) -> dict[date, FanpageInsights]:
    rows = db.scalars(
        select(FanpageInsights).where(
            FanpageInsights.fanpage_id == page_id, FanpageInsights.day >= start, FanpageInsights.day <= end
        )
    )
    return {row.day: row for row in rows}


def _followers(db: DbSession, page_id: int, end: date) -> dict[date, int]:
    rows = db.execute(
        select(FanpageFollowers.day, FanpageFollowers.followers).where(
            FanpageFollowers.fanpage_id == page_id, FanpageFollowers.day <= end
        )
    )
    return dict(rows.all())


def _last_on_or_before(followers: dict[date, int], day: date) -> int | None:
    days = [known for known in followers if known <= day]
    return followers[max(days)] if days else None


def _gain(followers: dict[date, int], period: Period) -> int | None:
    """Followers won in the period: the last number read in it less the last one read before it."""
    before = _last_on_or_before(followers, period.start - timedelta(days=1))
    after = _last_on_or_before(followers, period.end)
    if before is None or after is None:
        return None
    return after - before


def _posts(db: DbSession, page_id: int, since: datetime | None = None, limit: int | None = None) -> list[Publication]:
    """The Page's Facebook posts that went live (since `since`), newest first, with their numbers."""
    at = func.coalesce(Publication.scheduled_at, Publication.published_at, Publication.created_at)
    query = (
        select(Publication)
        .where(
            Publication.fanpage_id == page_id,
            Publication.platform == "facebook",
            # Reels only: an article ("Bài viết") has no video to show and no views.
            Publication.video_id.is_not(None),
            Publication.status.in_(LIVE_POST_STATUSES),
            at <= now(),
        )
        .order_by(at.desc(), Publication.id.desc())
    )
    if since is not None:
        query = query.where(at >= since)
    if limit is not None:
        query = query.limit(limit)
    return [post for post in db.scalars(query) if is_published(post)]


def _local_day(at: datetime) -> date:
    return at.astimezone(analytics.VIETNAM).date()


def _latest(post: Publication) -> PostMetrics | None:
    return next((row for row in post.metrics if row.window == "latest"), None)


def _post_sums(posts: list[Publication], period: Period) -> dict:
    """The reactions, comments and shares of the period's posts, and their average watch time weighted by views, from
    each post's latest reading. A post's numbers grow after its day, so this is close to, not the same as, what the
    Page earned in the period."""
    rows = [_latest(post) for post in posts if period.start <= _local_day(live_at(post)) <= period.end]
    rows = [row for row in rows if row is not None]
    watched = [(row.avg_watch_ms, row.views) for row in rows if row.avg_watch_ms is not None and row.views]
    weight = sum(views for _, views in watched)
    return {
        "reactions": _sum([row.reactions for row in rows]),
        "comments": _sum([row.comments for row in rows]),
        "shares": _sum([row.shares for row in rows]),
        "avg_watch_seconds": round(sum(ms * views for ms, views in watched) / weight / 1000, 1) if weight else None,
    }


def _video(db: DbSession, video: Video) -> dict:
    title, _ = split_scenes(db, video)
    return {"id": video.id, "title": video_name(video, title), "thumbnail_url": thumbnail_url(video)}


def _latest_post(db: DbSession, posts: list[Publication]) -> dict | None:
    if not posts:
        return None
    post = posts[0]
    row = _latest(post)
    return {
        "id": post.id,
        "remote_id": post.remote_id,
        "live_at": live_at(post).isoformat(),
        "video": _video(db, db.get(Video, post.video_id)),
        "numbers": {
            "views": row.views,
            "reach": row.reach,
            "reactions": row.reactions,
            "comments": row.comments,
            "shares": row.shares,
            "avg_watch_seconds": round(row.avg_watch_ms / 1000, 1) if row.avg_watch_ms is not None else None,
            "measured_at": row.measured_at.isoformat(),
        }
        if row
        else None,
    }


def _upcoming(db: DbSession, page: Fanpage, at: datetime) -> dict:
    """The Page's posts waiting for their time in the next week, and its free posting times then."""
    posts = db.scalars(
        select(Publication)
        .where(
            Publication.fanpage_id == page.id,
            Publication.platform == "facebook",
            # Reels only: an article ("Bài viết") has no video to show and no views.
            Publication.video_id.is_not(None),
            Publication.status.in_(("pending", "scheduled")),
            and_(Publication.scheduled_at > at, Publication.scheduled_at <= at + AHEAD),
        )
        .order_by(Publication.scheduled_at, Publication.id)
    ).all()
    return {
        "posts": [
            {
                "id": post.id,
                "status": post.status,
                "scheduled_at": post.scheduled_at.isoformat(),
                "video": _video(db, db.get(Video, post.video_id)),
            }
            for post in posts
        ],
        "free_slots": [
            slot.isoformat() for slot in page_queue.free_slots(db, page, at + page_queue.FILL_LEAD, at + AHEAD)
        ],
        "post_times": page_queue.post_times(db, page),
    }


def _content_row(db: DbSession, post: Publication, median: analytics.Median | None) -> dict:
    windows = {row.window: row for row in post.metrics}
    latest, mark = windows.get("latest"), windows.get("48h")
    published = is_published(post)
    asked, tried = post.metrics_requested_at, post.metrics_tried_at
    views_48h = mark.views if mark else None
    times = analytics.times_median(views_48h, median) if views_48h is not None else None
    return {
        "id": post.id,
        "status": "published" if published else post.status,
        "live_at": live_at(post).isoformat(),
        "closed_at": post.closed_at.isoformat() if post.closed_at else None,
        "url": facebook.reel_url(post.remote_id) if published and post.remote_id else None,
        "video": _video(db, db.get(Video, post.video_id)),
        "numbers": {
            "views": latest.views,
            "reach": latest.reach,
            "reactions": latest.reactions,
            "comments": latest.comments,
            "shares": latest.shares,
            "avg_watch_seconds": round(latest.avg_watch_ms / 1000, 1) if latest.avg_watch_ms is not None else None,
            "followers": latest.followers,
            "measured_at": latest.measured_at.isoformat(),
        }
        if latest
        else None,
        "views_48h": views_48h,
        "times_median": round(times, 1) if times is not None else None,
        # "Cập nhật view" (POST /api/posts/{id}/metrics) takes only a reel that is on Facebook.
        "can_refresh": published and post.remote_id is not None,
        "pending": asked is not None and (tried is None or tried < asked),
        "error": post.metrics_error,
    }


def content(db: DbSession, page: Fanpage, days: int) -> dict:
    """The "Nội dung" tab, like Facebook's content library: every post the app made to the Page that went live in the
    period, newest first, with its latest reading and its 48-hour views against the Page's median (analytics.py).
    A reel taken down after going live stays, as "deleted"; posts made outside the app are not known."""
    at = now()
    current, _ = periods(days, _local_day(at))
    since = datetime(current.start.year, current.start.month, current.start.day, tzinfo=analytics.VIETNAM)
    live = func.coalesce(Publication.scheduled_at, Publication.published_at, Publication.created_at)
    rows = db.scalars(
        select(Publication)
        .where(
            Publication.fanpage_id == page.id,
            Publication.platform == "facebook",
            # Reels only: an article ("Bài viết") has no video to show and no views.
            Publication.video_id.is_not(None),
            Publication.status.in_((*LIVE_POST_STATUSES, "deleted")),
            live >= since,
            live <= at,
        )
        .order_by(live.desc(), Publication.id.desc())
    )
    posts = [post for post in rows if post.status == "deleted" or is_published(post)]
    median = analytics.medians(db).get(page.id)
    return {
        "days": days,
        "start": current.start.isoformat(),
        "end": current.end.isoformat(),
        "median": {
            "views": median.views if median else None,
            "samples": median.samples if median else 0,
            "min_samples": analytics.MIN_SAMPLES,
        },
        "posts": [_content_row(db, post, median) for post in posts],
    }


def dashboard(db: DbSession, page: Fanpage, days: int) -> dict:
    at = now()
    current, previous = periods(days, _local_day(at))
    insights = _insights(db, page.id, previous.start, current.end)
    followers = _followers(db, page.id, current.end)
    since = datetime(previous.start.year, previous.start.month, previous.start.day, tzinfo=analytics.VIETNAM)
    posts = _posts(db, page.id, since)
    posted_days: dict[date, int] = {}
    for post in posts:
        day = _local_day(live_at(post))
        posted_days[day] = posted_days.get(day, 0) + 1

    def total(period: Period, metric: str) -> int | None:
        return _sum([getattr(insights[day], metric) for day in period.days() if day in insights])

    now_sums, before_sums = _post_sums(posts, current), _post_sums(posts, previous)
    check = fanpages.check_payload(db, [page])[page.id]
    return {
        "page": {
            "id": page.id,
            "page_id": page.page_id,
            "name": page.name,
            "active": page.active,
            "owner": {"id": page.owner.id, "name": page.owner.name} if page.owner else None,
            "token_tail": page.token_tail,
            "check": check,
            "insights_error": page.insights_error,
        },
        "days": days,
        "start": current.start.isoformat(),
        "end": current.end.isoformat(),
        "series": [
            {
                "day": day.isoformat(),
                "views": insights[day].views if day in insights else None,
                "reach": insights[day].reach if day in insights else None,
                "engagements": insights[day].engagements if day in insights else None,
                "followers": followers.get(day),
                "posts": posted_days.get(day, 0),
            }
            for day in current.days()
        ],
        "totals": {
            metric: figure(total(current, metric), total(previous, metric))
            for metric in ("views", "reach", "engagements")
        }
        | {
            "followers_gain": figure(_gain(followers, current), _gain(followers, previous)),
            "posts": figure(
                sum(posted_days.get(day, 0) for day in current.days()),
                sum(posted_days.get(day, 0) for day in previous.days()),
            ),
        },
        "followers": page.followers_count,
        "post_numbers": {key: figure(now_sums[key], before_sums[key]) for key in now_sums},
        # The newest post, even one older than both periods.
        "latest_post": _latest_post(db, posts or _posts(db, page.id, limit=1)),
        "upcoming": _upcoming(db, page, at),
    }
