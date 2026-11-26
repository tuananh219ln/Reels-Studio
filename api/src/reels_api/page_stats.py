"""The "Thống kê" page (`GET /api/stats`): the same numbers as each Page's dashboard, side by side, one row per Page.
Nothing here is new or stored: every figure comes from `page_dashboard` (dashboard, gate, content, best_times and the
Instagram dashboard), so a Page's row always agrees with its own dashboard. Pages are compared, never added up: there
is no grand total. A number a Page does not have is None, never 0."""

import statistics

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import analytics, page_dashboard, page_queue
from .models import Fanpage, Video

PLATFORMS = ("facebook", "instagram")
# "Thời lượng nào hiệu quả nhất": a video's length (the MP4's own, `Video.mp4_seconds`) falls in the first bucket whose
# upper bound it is under, so 45.0 s is "45–60s" and 60.0 s is ">60s".
DURATION_BUCKETS = (("<45s", 45), ("45–60s", 60), (">60s", None))


def _total(values: list[int | float | None]) -> int | float | None:
    known = [value for value in values if value is not None]
    return sum(known) if known else None


def _owner(page: Fanpage) -> dict | None:
    return {"id": page.owner.id, "name": page.owner.name} if page.owner else None


def _bucket(seconds: float) -> str:
    for name, upper in DURATION_BUCKETS:
        if upper is None or seconds < upper:
            return name
    raise AssertionError("unreachable")


def duration_buckets(db: DbSession, posts: list[dict]) -> list[dict]:
    """The Page's median views at 48 hours by video length. Only live posts read at 48 hours count (a deleted reel
    measures the fault, not the content: analytics.py); a video without an MP4 length is left out. A bucket under
    `analytics.MIN_SAMPLES` posts has no median, and `best` marks the highest median (all of a tie) only when two buckets
    have one. The period is the one chosen, unlike the Page's 60-day median."""
    measured = [post for post in posts if post["status"] == "published" and post["views_48h"] is not None]
    ids = {post["video"]["id"] for post in measured}
    lengths = dict(db.execute(select(Video.id, Video.mp4_seconds).where(Video.id.in_(ids))).all()) if ids else {}
    views: dict[str, list[int]] = {name: [] for name, _ in DURATION_BUCKETS}
    for post in measured:
        seconds = lengths.get(post["video"]["id"])
        if seconds:
            views[_bucket(seconds)].append(post["views_48h"])
    medians = {
        name: int(statistics.median(values)) if len(values) >= analytics.MIN_SAMPLES else None
        for name, values in views.items()
    }
    known = [value for value in medians.values() if value is not None]
    top = max(known) if len(known) >= 2 else None
    return [
        {
            "bucket": name,
            "videos": len(views[name]),
            "median_views_48h": medians[name],
            "best": top is not None and medians[name] == top,
        }
        for name, _ in DURATION_BUCKETS
    ]


def _facebook_row(db: DbSession, page: Fanpage, days: int) -> dict:
    dashboard = page_dashboard.dashboard(db, page, days)
    gate = page_dashboard.gate(db, page)
    posts = page_dashboard.content(db, page, days)["posts"]
    numbers = [post["numbers"] for post in posts if post["numbers"]]
    views = _total([row["views"] for row in numbers])
    shares = _total([row["shares"] for row in numbers])
    return {
        "page": {"id": page.id, "name": page.name, "owner": _owner(page)},
        "totals": dashboard["totals"],
        "post_numbers": dashboard["post_numbers"],
        "series": [
            {"day": row["day"], "views": row["views"], "engagements": row["engagements"]} for row in dashboard["series"]
        ],
        # Shares per view over the period's posts (their latest readings); None until a post has views.
        "share_per_view": round(shares / views, 4) if views and shares is not None else None,
        "view_time_seconds": _total([row["view_time_seconds"] for row in numbers]),
        "gate": {
            "state": gate["state"],
            "label": gate["state_label"],
            "median_views": gate["median_views"],
            "measured": gate["measured"],
            "first": gate["first"],
            "last": gate["last"],
            "top_views": gate["top_views"],
        },
        "winners": gate["winners"],
        # Posted in the period and not yet read at 48 hours.
        "measuring": [
            {"post_id": post["id"], "video": post["video"], "live_at": post["live_at"]}
            for post in posts
            if post["views_48h"] is None and post["status"] == "published"
        ],
        "best_times": page_dashboard.best_times(db, page)["facebook"],
        "best_times_zone": page_queue.timezone_of(db, page),
        "duration_buckets": duration_buckets(db, posts),
    }


def _instagram_row(db: DbSession, page: Fanpage, days: int) -> dict:
    dashboard = page_dashboard.instagram_dashboard(db, page, days)
    posts = page_dashboard.instagram_content(db, page, days)["posts"]
    numbers = [post["numbers"] for post in posts if post["numbers"]]
    return {
        "page": {"id": page.id, "name": page.name, "owner": _owner(page)},
        "account": dashboard["account"],
        "totals": dashboard["totals"],
        "audience": dashboard["audience"],
        "series": [
            {"day": row["day"], "views": row["views"], "engagements": row["interactions"]}
            for row in dashboard["series"]
        ],
        "post_numbers": {
            key: _total([row[key] for row in numbers]) for key in ("comments", "shares", "saves", "likes")
        },
        "best_times": page_dashboard.best_times(db, page)["instagram"],
        "best_times_zone": page_queue.timezone_of(db, page),
    }


def stats(db: DbSession, days: int, platform: str, page_ids: list[int] | None) -> dict:
    """One row per Page (the ids asked for, or every Page), for the last `days` days on `platform`. On Instagram only
    the Pages with a linked account have a row."""
    query = select(Fanpage).order_by(Fanpage.name, Fanpage.id)
    if page_ids is not None:
        query = query.where(Fanpage.id.in_(page_ids))
    pages = list(db.scalars(query))
    if platform == "instagram":
        pages = [page for page in pages if page.instagram_user_id]
    build = _instagram_row if platform == "instagram" else _facebook_row
    current, _ = page_dashboard.periods(days, page_dashboard._local_day(page_dashboard.now()))
    return {
        "days": days,
        "platform": platform,
        "start": current.start.isoformat(),
        "end": current.end.isoformat(),
        "rows": [build(db, page, days) for page in pages],
    }
