"""One Page's dashboard on "Quản lý kênh" (`/fanpages/{id}`), shaped like Facebook's Professional Dashboard but built only
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
from .models import (
    Fanpage,
    FanpageFollowers,
    FanpageInsights,
    InstagramInsights,
    PostMetrics,
    PostMetricSnapshot,
    Publication,
    Video,
)
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
    # What Instagram does with each of them: its own post when there is one (not cancelled), "auto" when the Page's switch
    # will send it a minute after Facebook, nothing for a Page without a linked account.
    on_instagram = dict(
        db.execute(
            select(Publication.video_id, Publication.status).where(
                Publication.video_id.in_([post.video_id for post in posts]),
                Publication.platform == "instagram",
                Publication.fanpage_id == page.id,
                Publication.status.in_(("pending", "scheduled", "published")),
            )
        ).all()
    )

    def instagram_of(post: Publication) -> str | None:
        if not page.instagram_user_id:
            return None
        return on_instagram.get(post.video_id) or ("auto" if page.instagram_auto else None)

    return {
        "posts": [
            {
                "id": post.id,
                "status": post.status,
                "scheduled_at": post.scheduled_at.isoformat(),
                "video": _video(db, db.get(Video, post.video_id)),
                # The Page's Instagram for this post: "pending", "scheduled", "published", "auto" or None.
                "instagram": instagram_of(post),
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
            # The linked Instagram account: the dashboard's "Facebook | Instagram" switch shows only when there is one.
            "instagram": {"id": page.instagram_user_id, "username": page.instagram_username}
            if page.instagram_user_id
            else None,
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


def _audience(shares: dict | None) -> dict | None:
    """The stored shares as lists, the biggest first (a JSON column does not keep the order)."""
    if not shares:
        return None
    return {
        breakdown: [
            {"key": key, "share": share} for key, share in sorted(rows.items(), key=lambda item: item[1], reverse=True)
        ]
        for breakdown, rows in shares.items()
    }


def instagram_dashboard(db: DbSession, page: Fanpage, days: int) -> dict:
    """The Page's Instagram account for the last `days` days (7, 28 or 90), each figure against the period before it:
    views, accounts reached, interactions and the follows of each day, read at the Page's check with
    `instagram_manage_insights` (`instagram_insights_error` says when the token lacks it). Like the Facebook dashboard,
    a day with no stored number is None, never 0."""
    at = now()
    current, previous = periods(days, _local_day(at))
    rows = {
        row.day: row
        for row in db.scalars(
            select(InstagramInsights).where(
                InstagramInsights.fanpage_id == page.id,
                InstagramInsights.day >= previous.start,
                InstagramInsights.day <= current.end,
            )
        )
    }

    def total(period: Period, metric: str) -> int | None:
        return _sum([getattr(rows[day], metric) for day in period.days() if day in rows])

    return {
        "page": {
            "id": page.id,
            "name": page.name,
            "owner": {"id": page.owner.id, "name": page.owner.name} if page.owner else None,
        },
        "account": {"id": page.instagram_user_id, "username": page.instagram_username},
        "days": days,
        "start": current.start.isoformat(),
        "end": current.end.isoformat(),
        "series": [
            {
                "day": day.isoformat(),
                "views": rows[day].views if day in rows else None,
                "reach": rows[day].reach if day in rows else None,
                "interactions": rows[day].interactions if day in rows else None,
                "follows": rows[day].follows if day in rows else None,
            }
            for day in current.days()
        ],
        "totals": {
            metric: figure(total(current, metric), total(previous, metric))
            for metric in ("views", "reach", "interactions", "follows")
        },
        "followers": page.instagram_followers_count,
        "audience": _audience(page.instagram_audience),
        "audience_error": page.instagram_audience_error,
        "insights_error": page.instagram_insights_error,
    }


def _instagram_numbers(db: DbSession, post: Publication) -> dict | None:
    """The newest reading of an Instagram Reel (its snapshot's `numbers`), or None before the first."""
    snap = db.scalars(
        select(PostMetricSnapshot)
        .where(PostMetricSnapshot.publication_id == post.id)
        .order_by(PostMetricSnapshot.captured_at.desc())
        .limit(1)
    ).first()
    if snap is None:
        return None
    numbers = dict((snap.raw or {}).get("numbers") or {})
    watch = numbers.pop("avg_watch_ms", None)
    return {
        "views": numbers.get("views", snap.views),
        "reach": numbers.get("reach"),
        "likes": numbers.get("likes", snap.likes),
        "comments": numbers.get("comments", snap.comments),
        "shares": numbers.get("shares", snap.shares),
        "saves": numbers.get("saves"),
        "interactions": numbers.get("interactions"),
        "avg_watch_seconds": round(watch / 1000, 1) if watch is not None else None,
        "measured_at": snap.captured_at.isoformat(),
    }


def _instagram_posts(db: DbSession, page_id: int, since: datetime) -> list[Publication]:
    at = func.coalesce(Publication.scheduled_at, Publication.published_at, Publication.created_at)
    return list(
        db.scalars(
            select(Publication)
            .where(
                Publication.fanpage_id == page_id,
                Publication.platform == "instagram",
                Publication.video_id.is_not(None),
                Publication.status == "published",
                at >= since,
                at <= now(),
            )
            .order_by(at.desc(), Publication.id.desc())
        )
    )


def instagram_content(db: DbSession, page: Fanpage, days: int) -> dict:
    """The Instagram "Nội dung" tab: every Reel the app posted to the Page's Instagram in the period, newest first, with
    its latest reading (views, reach, likes, comments, shares, saves, watch time). A Reel posted outside the app is not
    known."""
    at = now()
    current, _ = periods(days, _local_day(at))
    since = datetime(current.start.year, current.start.month, current.start.day, tzinfo=analytics.VIETNAM)
    rows = []
    for post in _instagram_posts(db, page.id, since):
        rows.append(
            {
                "id": post.id,
                "live_at": live_at(post).isoformat(),
                "url": post.post_url,
                "video": _video(db, db.get(Video, post.video_id)),
                "numbers": _instagram_numbers(db, post),
                "pending": post.metrics_requested_at is not None
                and (post.metrics_tried_at is None or post.metrics_tried_at < post.metrics_requested_at),
                "error": post.metrics_error,
            }
        )
    return {"days": days, "start": current.start.isoformat(), "end": current.end.isoformat(), "posts": rows}


def compare(db: DbSession, page: Fanpage, days: int) -> dict:
    """The same video on Facebook and on Instagram, side by side: every video the app posted to the Page on both in the
    period (or on one of them), with each platform's views, reach and interactions, newest first."""
    at = now()
    current, _ = periods(days, _local_day(at))
    since = datetime(current.start.year, current.start.month, current.start.day, tzinfo=analytics.VIETNAM)
    facebook_by_video: dict[int, Publication] = {}
    for post in _posts(db, page.id, since):
        facebook_by_video.setdefault(post.video_id, post)
    instagram_by_video: dict[int, Publication] = {}
    for post in _instagram_posts(db, page.id, since):
        instagram_by_video.setdefault(post.video_id, post)
    rows = []
    for video_id in {*facebook_by_video, *instagram_by_video}:
        fb, ig = facebook_by_video.get(video_id), instagram_by_video.get(video_id)
        latest = next((row for row in (fb.metrics if fb else []) if row.window == "latest"), None)
        ig_numbers = _instagram_numbers(db, ig) if ig else None
        rows.append(
            {
                "video": _video(db, db.get(Video, video_id)),
                "facebook": None
                if fb is None
                else {
                    "live_at": live_at(fb).isoformat(),
                    "url": facebook.reel_url(fb.remote_id) if fb.remote_id else None,
                    "views": latest.views if latest else None,
                    "reach": latest.reach if latest else None,
                    "interactions": (
                        sum(value for value in (latest.reactions, latest.comments, latest.shares) if value is not None)
                        if latest
                        and any(value is not None for value in (latest.reactions, latest.comments, latest.shares))
                        else None
                    ),
                },
                "instagram": None
                if ig is None
                else {
                    "live_at": live_at(ig).isoformat(),
                    "url": ig.post_url,
                    "views": ig_numbers["views"] if ig_numbers else None,
                    "reach": ig_numbers["reach"] if ig_numbers else None,
                    "interactions": ig_numbers["interactions"] if ig_numbers else None,
                },
                "_at": max(live_at(post) for post in (fb, ig) if post is not None),
            }
        )
    rows.sort(key=lambda row: row["_at"], reverse=True)
    for row in rows:
        del row["_at"]
    return {"days": days, "start": current.start.isoformat(), "end": current.end.isoformat(), "videos": rows}


# Posting hours: at least this many posts with a reading on a platform before it says which hours work best, and this
# many on an hour before that hour counts.
BEST_MIN_POSTS = 6
BEST_MIN_PER_HOUR = 2
BEST_SHOWN = 3


def _best_hours(samples: list[tuple[int, int]]) -> dict:
    """Which hours (Vietnam time) the Page's posts were watched most: [(hour, views)] of posts with a reading, grouped by
    the hour they went live, the average of each hour with enough posts, the best BEST_SHOWN. Too few posts say nothing."""
    if len(samples) < BEST_MIN_POSTS:
        return {"posts": len(samples), "hours": [], "enough": False}
    by_hour: dict[int, list[int]] = {}
    for hour, views in samples:
        by_hour.setdefault(hour, []).append(views)
    ranked = sorted(
        (
            {"hour": hour, "average_views": round(sum(values) / len(values)), "posts": len(values)}
            for hour, values in by_hour.items()
            if len(values) >= BEST_MIN_PER_HOUR
        ),
        key=lambda row: row["average_views"],
        reverse=True,
    )
    return {"posts": len(samples), "hours": ranked[:BEST_SHOWN], "enough": True}


def best_times(db: DbSession, page: Fanpage) -> dict:
    """The hours the Page's Facebook reels and Instagram Reels (the app's posts of the last 90 days) were watched most,
    to help choose the Page's posting times; each platform on its own, since their audiences differ."""
    since = now() - timedelta(days=90)
    facebook_samples = []
    for post in _posts(db, page.id, since):
        latest = next((row for row in post.metrics if row.window == "latest"), None)
        if latest is not None and latest.views is not None:
            facebook_samples.append((live_at(post).astimezone(analytics.VIETNAM).hour, latest.views))
    instagram_samples = []
    for post in _instagram_posts(db, page.id, since):
        numbers = _instagram_numbers(db, post)
        if numbers is not None and numbers["views"] is not None:
            instagram_samples.append((live_at(post).astimezone(analytics.VIETNAM).hour, numbers["views"]))
    return {
        "days": 90,
        "min_posts": BEST_MIN_POSTS,
        "facebook": _best_hours(facebook_samples),
        "instagram": _best_hours(instagram_samples) if page.instagram_user_id else None,
    }
