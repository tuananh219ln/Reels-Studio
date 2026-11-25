"""The "Thống kê" page (`GET /api/stats`): the same numbers as each Page's dashboard, side by side, one row per Page.
Nothing here is new or stored: every figure comes from `page_dashboard` (dashboard, gate, content, best_times and the
Instagram dashboard), so a Page's row always agrees with its own dashboard. Pages are compared, never added up: there
is no grand total. A number a Page does not have is None, never 0."""

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import page_dashboard
from .models import Fanpage

PLATFORMS = ("facebook", "instagram")


def _total(values: list[int | float | None]) -> int | float | None:
    known = [value for value in values if value is not None]
    return sum(known) if known else None


def _owner(page: Fanpage) -> dict | None:
    return {"id": page.owner.id, "name": page.owner.name} if page.owner else None


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
