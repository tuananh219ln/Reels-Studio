"""The "Bài đăng" board: one row per rendered video, one cell per platform (Facebook, TikTok, YouTube Shorts) saying
where it stands there, the status tabs and their counts, and each video's posts for its opened row
(docs/decisions/2026-11-14-posts-board.md).

A post's state on the board, from its row: `pending` is "publishing" (or "failed" when the video's last publish job
for that platform failed), `deleted` is "removed", a scheduled reel past its time is "published"."""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as DbSession

from . import hashtags, knowledge
from .analytics import VIETNAM
from .models import Job, PostMetrics, PostMetricSnapshot, Publication, Scene, User, Video
from .post_links import normalize, video_ref
from .script_rules import plain_title
from .sessions import now
from .videos import is_published, live_at, thumbnail_url

PLATFORMS = ("facebook", "tiktok", "youtube")
# A cell shows the first of these its posts are in.
STATE_ORDER = ("published", "scheduled", "publishing", "pending_link", "failed", "removed")
ACTIVE_STATES = {"published", "scheduled", "publishing", "pending_link"}
TABS = ("unposted", "pending_link", "scheduled", "published", "failed", "closed", "unmatched", "all")
# "Chưa khớp": reels imported from a Page (meta_sync.py) with no video yet.
UNMATCHED = ("suggested", "unmatched")
SORTS = ("latest", "views", "views_48h", "oldest_render")
PUBLISH_JOBS = {"facebook": "publish", "tiktok": "tiktok_publish"}
STALE_PENDING = timedelta(hours=24)
UNPOSTED_WARNING_DAYS = 3
PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


@dataclass
class PostView:
    post: Publication
    state: str
    channel: str | None
    views: int | None = None
    views_48h: int | None = None
    measured_at: datetime | None = None
    error: str | None = None
    retry_job_id: int | None = None
    # A reading was asked for ("Cập nhật view") and has not run yet.
    refreshing: bool = False


@dataclass
class Row:
    """A video and its posts, or (`video` None) one post followed without a video ("Video ngoài")."""

    video: Video | None
    name: str
    posts: list[PostView] = field(default_factory=list)

    @property
    def rendered_at(self) -> datetime | None:
        return self.video.rendered_at if self.video else None

    @property
    def created_by_id(self) -> int | None:
        return self.video.created_by_id if self.video else None

    @property
    def topic(self) -> str:
        return self.video.topic if self.video else ""

    def on(self, platform: str | None) -> list[PostView]:
        return [view for view in self.posts if platform is None or view.post.platform == platform]


def state_of(post: Publication, failed: bool) -> str:
    if post.status == "pending":
        return "failed" if failed else "publishing"
    if post.status == "deleted":
        return "removed"
    if post.status == "scheduled" and is_published(post):
        return "published"
    return post.status


def channel_of(post: Publication) -> str | None:
    if post.fanpage is not None:
        return post.fanpage.name
    if post.affiliate_account is not None:
        return post.affiliate_account.name
    if post.channel is not None:
        return post.channel.name
    return None


def _failed_jobs(db: DbSession, video_ids: list[int]) -> dict[tuple[int, str], Job]:
    """The last publish job of each video and kind, when it failed."""
    if not video_ids:
        return {}
    last = (
        select(func.max(Job.id))
        .where(Job.video_id.in_(video_ids), Job.kind.in_(PUBLISH_JOBS.values()))
        .group_by(Job.video_id, Job.kind)
    )
    return {
        (job.video_id, job.kind): job for job in db.scalars(select(Job).where(Job.id.in_(last), Job.status == "failed"))
    }


def _readings(db: DbSession, post_ids: list[int]) -> tuple[dict[int, PostMetricSnapshot], dict[int, int | None]]:
    """The latest snapshot of each post, and each Facebook post's 48-hour mark."""
    if not post_ids:
        return {}, {}
    newest = (
        select(PostMetricSnapshot.publication_id, func.max(PostMetricSnapshot.captured_at).label("at"))
        .where(PostMetricSnapshot.publication_id.in_(post_ids))
        .group_by(PostMetricSnapshot.publication_id)
        .subquery()
    )
    latest: dict[int, PostMetricSnapshot] = {}
    for row in db.scalars(
        select(PostMetricSnapshot)
        .join(
            newest,
            (newest.c.publication_id == PostMetricSnapshot.publication_id)
            & (newest.c.at == PostMetricSnapshot.captured_at),
        )
        .order_by(PostMetricSnapshot.id)
    ):
        latest[row.publication_id] = row  # two readings at the same time: the one saved last
    marks = dict(
        db.execute(
            select(PostMetrics.publication_id, PostMetrics.views).where(
                PostMetrics.publication_id.in_(post_ids), PostMetrics.window == "48h"
            )
        ).all()
    )
    return latest, marks


def post_views(db: DbSession, posts: list[Publication]) -> list[PostView]:
    failed = _failed_jobs(db, sorted({post.video_id for post in posts if post.status == "pending"}))
    latest, marks = _readings(db, [post.id for post in posts])
    views = []
    for post in posts:
        job = failed.get((post.video_id, PUBLISH_JOBS.get(post.platform, "")))
        reading = latest.get(post.id)
        views.append(
            PostView(
                post=post,
                state=state_of(post, job is not None and post.status == "pending"),
                channel=channel_of(post),
                views=reading.views if reading else None,
                views_48h=post.views_48h if post.views_48h is not None else marks.get(post.id),
                refreshing=post.metrics_requested_at is not None
                and (post.metrics_tried_at is None or post.metrics_tried_at < post.metrics_requested_at),
                measured_at=reading.captured_at if reading else None,
                error=job.error if job is not None and post.status == "pending" else None,
                retry_job_id=job.id if job is not None and post.status == "pending" else None,
            )
        )
    return views


def _names(db: DbSession, videos: list[Video]) -> dict[int, str]:
    titles = dict(
        db.execute(
            select(Scene.video_id, Scene.text).where(
                Scene.video_id.in_([video.id for video in videos]), Scene.is_title.is_(True)
            )
        ).all()
    )
    return {
        video.id: video.name
        or (plain_title(titles[video.id]) if titles.get(video.id, "").strip() else "")
        or video.topic
        for video in videos
    }


def rows(db: DbSession) -> list[Row]:
    """Every rendered video, and any video with a post, each with its posts on the board's platforms."""
    posted = select(Publication.video_id).where(Publication.video_id.is_not(None))
    videos = list(
        db.scalars(
            select(Video).where(or_(Video.mp4_key.is_not(None), Video.rendered_at.is_not(None), Video.id.in_(posted)))
        )
    )
    if not videos:
        return external_rows(db)
    names = _names(db, videos)
    posts = list(
        db.scalars(
            select(Publication)
            .where(Publication.video_id.in_([video.id for video in videos]), Publication.platform.in_(PLATFORMS))
            .order_by(Publication.id)
        )
    )
    by_video: dict[int, Row] = {video.id: Row(video, names[video.id]) for video in videos}
    for view in post_views(db, posts):
        by_video[view.post.video_id].posts.append(view)
    return list(by_video.values()) + external_rows(db)


def external_name(post: Publication) -> str:
    first = (post.caption or "").strip().split("\n")[0][:120]
    return first or "Video ngoài"


def external_rows(db: DbSession) -> list[Row]:
    """ "Video ngoài": posts followed without a video, a row each."""
    posts = list(
        db.scalars(
            select(Publication)
            .where(
                Publication.video_id.is_(None),
                Publication.article_id.is_(None),
                Publication.match_status == "external",
                Publication.platform.in_(PLATFORMS),
            )
            .order_by(Publication.id)
        )
    )
    return [Row(None, external_name(view.post), [view]) for view in post_views(db, posts)]


# --- What a row says ---


def _channel_label(views: list[PostView], platform: str) -> str | None:
    if len(views) > 1:
        return f"{len(views)} Page" if platform == "facebook" else f"{len(views)} kênh"
    return views[0].channel if views else None


def _iso(at: datetime | None) -> str | None:
    return at.isoformat() if at else None


def cell(views: list[PostView], platform: str) -> dict | None:
    """A platform's cell: the state first in STATE_ORDER among its posts, and what those posts add up to. None with no
    post, or only cancelled ones."""
    top = next((state for state in STATE_ORDER if any(view.state == state for view in views)), None)
    if top is None:
        return None
    chosen = [view for view in views if view.state == top]
    read = [view for view in chosen if view.views is not None]
    marked = [view for view in chosen if view.views_48h is not None]
    loudest = max(chosen, key=lambda view: view.views or -1)
    pending_since = min((view.post.mp4_downloaded_at or view.post.created_at for view in chosen), default=None)
    return {
        "state": top,
        "views": sum(view.views for view in read) if top == "published" and read else None,
        "views_48h": sum(view.views_48h for view in marked) if top == "published" and marked else None,
        "post_count": len(chosen),
        "channel_label": _channel_label(chosen, platform),
        "source": loudest.post.source,
        "published_at": _iso(max((live_at(view.post) for view in chosen), default=None))
        if top == "published"
        else None,
        "scheduled_at": _iso(min((view.post.scheduled_at for view in chosen if view.post.scheduled_at), default=None)),
        "pending_since": _iso(pending_since) if top == "pending_link" else None,
        "pending_stale": top == "pending_link" and pending_since is not None and now() - pending_since > STALE_PENDING,
        "error": next((view.error for view in chosen if view.error), None),
        "retry_job_id": next((view.retry_job_id for view in chosen if view.retry_job_id), None),
        "closed_at": _iso(max((view.post.closed_at for view in chosen if view.post.closed_at), default=None)),
        "metrics_updated_at": _iso(max((view.measured_at for view in chosen if view.measured_at), default=None)),
        "refreshing": any(view.refreshing for view in chosen),
    }


def total_views(row: Row, platform: str | None = None) -> int | None:
    read = [view.views for view in row.on(platform) if view.state == "published" and view.views is not None]
    return sum(read) if read else None


def views_48h(row: Row, platform: str | None = None) -> int | None:
    read = [view.views_48h for view in row.on(platform) if view.state == "published" and view.views_48h is not None]
    return sum(read) if read else None


def latest_at(row: Row, platform: str | None = None) -> datetime | None:
    times = [live_at(view.post) for view in row.on(platform) if view.state in ("published", "scheduled")]
    return max(times, default=None)


def in_tab(row: Row, tab: str, platform: str | None) -> bool:
    states = {view.state for view in row.on(platform)}
    match tab:
        case "unposted":
            return not states & ACTIVE_STATES
        case "pending_link" | "scheduled" | "published" | "failed":
            return tab in states
        case "closed":
            return bool(states & {"removed", "cancelled"})
        case "unmatched":
            return False  # imported reels, listed by unmatched_posts
    return True


def unposted_days(row: Row) -> int | None:
    rendered = row.rendered_at
    if rendered is None or in_tab(row, "unposted", None) is False:
        return None
    days = (now() - rendered).days
    return days if days > UNPOSTED_WARNING_DAYS else None


def item(row: Row, users: dict[int, str], platform: str | None) -> dict:
    video = row.video
    if video is None:
        post = row.posts[0].post
        return {
            "video": {
                "id": None,
                "post_id": post.id,
                "external": True,
                "name": row.name,
                "topic": "",
                "thumbnail_url": post.thumbnail_url,
                "created_by": "",
                "created_by_id": None,
                "rendered_at": None,
                "has_mp4": False,
                "unposted_days": None,
                "url": post.post_url,
            },
            "cells": {name: cell(row.on(name), name) for name in PLATFORMS},
            "total_views": total_views(row, platform),
            "views_48h": views_48h(row, platform),
            "latest_at": _iso(latest_at(row, platform)),
        }
    return {
        "video": {
            "id": video.id,
            "name": row.name,
            "topic": video.topic,
            "thumbnail_url": thumbnail_url(video),
            "created_by": users.get(video.created_by_id, ""),
            "created_by_id": video.created_by_id,
            "rendered_at": _iso(video.rendered_at),
            "has_mp4": video.mp4_key is not None,
            "unposted_days": unposted_days(row),
        },
        "cells": {name: cell(row.on(name), name) for name in PLATFORMS},
        "total_views": total_views(row, platform),
        "views_48h": views_48h(row, platform),
        "latest_at": _iso(latest_at(row, platform)),
    }


# --- The board ---


@dataclass
class Filters:
    tab: str = "all"
    platform: str | None = None
    channels: set[str] = field(default_factory=set)  # "fanpage:1", "tiktok:2", "youtube:3"
    missing_on: str | None = None
    owner_id: int | None = None
    date_from: date | None = None
    date_to: date | None = None
    sort: str | None = None
    query: str = ""


def channel_key(post: Publication) -> str | None:
    if post.fanpage_id is not None:
        return f"fanpage:{post.fanpage_id}"
    if post.affiliate_account_id is not None:
        return f"tiktok:{post.affiliate_account_id}"
    if post.channel_id is not None:
        return f"youtube:{post.channel_id}"
    return None


def _local_day(at: datetime | None) -> date | None:
    return at.astimezone(VIETNAM).date() if at else None


def _matches(row: Row, filters: Filters) -> bool:
    """Every filter but the tab, so the tabs' counts follow the other filters."""
    if filters.owner_id is not None and row.created_by_id != filters.owner_id:
        return False
    if filters.query and normalize(filters.query) not in normalize(f"{row.name} {row.topic}"):
        return False
    if filters.channels and not any(
        channel_key(view.post) in filters.channels for view in row.posts if view.state != "cancelled"
    ):
        return False
    if filters.missing_on and any(
        view.state in ("published", "scheduled", "pending_link") for view in row.on(filters.missing_on)
    ):
        return False
    if filters.date_from or filters.date_to:
        at = row.rendered_at if filters.tab == "unposted" else latest_at(row, filters.platform)
        day = _local_day(at)
        if day is None:
            return False
        if (filters.date_from and day < filters.date_from) or (filters.date_to and day > filters.date_to):
            return False
    return True


def _sort_key(sort: str, platform: str | None):
    oldest = datetime.min.replace(tzinfo=VIETNAM)
    match sort:
        case "views":
            return lambda row: (total_views(row, platform) or -1, latest_at(row, platform) or oldest)
        case "views_48h":
            return lambda row: (views_48h(row, platform) or -1, latest_at(row, platform) or oldest)
        case "oldest_render":
            return lambda row: row.rendered_at or oldest
    return lambda row: latest_at(row, platform) or row.rendered_at or oldest


def board(db: DbSession, filters: Filters, offset: int = 0, limit: int = PAGE_SIZE) -> dict:
    every = [row for row in rows(db) if _matches(row, filters)]
    counts = {tab: sum(1 for row in every if in_tab(row, tab, filters.platform)) for tab in TABS}
    counts["unmatched"] = len(_unmatched(db, filters.platform))
    shown = [row for row in every if in_tab(row, filters.tab, filters.platform)]
    sort = filters.sort or ("oldest_render" if filters.tab == "unposted" else "latest")
    shown.sort(key=_sort_key(sort, filters.platform), reverse=sort != "oldest_render")
    page = shown[offset : offset + limit]
    users = dict(db.execute(select(User.id, User.name)).all())
    return {
        "items": [item(row, users, filters.platform) for row in page],
        "counts": counts,
        "total": len(shown),
        "next_cursor": str(offset + limit) if offset + limit < len(shown) else None,
        "sort": sort,
    }


# --- "Chưa khớp" ---


def _unmatched(db: DbSession, platform: str | None = None) -> list[Publication]:
    query = select(Publication).where(
        Publication.video_id.is_(None),
        Publication.article_id.is_(None),
        Publication.match_status.in_(UNMATCHED),
    )
    if platform is not None:
        query = query.where(Publication.platform == platform)
    return list(db.scalars(query.order_by(Publication.published_at.desc().nulls_last(), Publication.id.desc())))


def unmatched_posts(db: DbSession, platform: str | None = None) -> list[dict]:
    """The reels imported from a Page with no video yet, newest first, each with its best guess."""
    posts = _unmatched(db, platform)
    views = {view.post.id: view for view in post_views(db, posts)}
    suggested = {
        video.id: video
        for video in db.scalars(
            select(Video).where(Video.id.in_({p.suggested_video_id for p in posts if p.suggested_video_id}))
        )
    }
    return [
        {
            "id": post.id,
            "platform": post.platform,
            "url": post.post_url,
            "caption": post.caption or "",
            "thumbnail_url": post.thumbnail_url,
            "channel": channel_of(post),
            "published_at": _iso(post.published_at),
            "views": views[post.id].views,
            "match_status": post.match_status,
            "suggested": video_ref(db, suggested[post.suggested_video_id], post.match_score)
            if post.suggested_video_id in suggested
            else None,
        }
        for post in posts
    ]


# --- One video's posts, for its opened row ---

SPARKLINE_POINTS = 30
# The marks shown in an opened row: (column, hours, tolerance), as metrics.MARKS.
SHOWN_MARKS = (("24h", 24, 2), ("48h", 48, 3), ("7d", 168, 12))


def missed_marks(view: PostView) -> list[str]:
    """Marks the post is past (with their tolerance) and has no value for: "n/a", not "—"."""
    if view.state not in ("published", "removed"):
        return []
    age = (now() - live_at(view.post)).total_seconds() / 3600
    values = {"24h": view.post.views_24h, "48h": view.views_48h, "7d": view.post.views_7d}
    return [name for name, hours, tolerance in SHOWN_MARKS if values[name] is None and age > hours + tolerance]


def sparklines(db: DbSession, post_ids: list[int]) -> dict[int, list[int]]:
    """Each post's views over time, its last SPARKLINE_POINTS readings, oldest first."""
    if not post_ids:
        return {}
    ranked = (
        select(
            PostMetricSnapshot.publication_id,
            PostMetricSnapshot.views,
            PostMetricSnapshot.captured_at,
            func.row_number()
            .over(partition_by=PostMetricSnapshot.publication_id, order_by=PostMetricSnapshot.captured_at.desc())
            .label("rank"),
        )
        .where(PostMetricSnapshot.publication_id.in_(post_ids), PostMetricSnapshot.views.is_not(None))
        .subquery()
    )
    lines: dict[int, list[int]] = {}
    for post_id, views, _ in db.execute(
        select(ranked.c.publication_id, ranked.c.views, ranked.c.captured_at)
        .where(ranked.c.rank <= SPARKLINE_POINTS)
        .order_by(ranked.c.publication_id, ranked.c.captured_at)
    ):
        lines.setdefault(post_id, []).append(views)
    return lines


def video_posts(db: DbSession, video: Video, fb_payload) -> dict:
    """`fb_payload(post)`: the "Bài đăng" payload of a Facebook post, whose actions (check, cancel, take down,
    comment) stay those of routes_posts."""
    posts = list(
        db.scalars(
            select(Publication)
            .where(Publication.video_id == video.id, Publication.platform.in_(PLATFORMS))
            .order_by(Publication.id.desc())
        )
    )
    views = post_views(db, posts)
    trends = sparklines(db, [post.id for post in posts])
    topic = knowledge.topic_of(db, video)
    post_text = hashtags.post_text(video.caption, video.hashtags)
    active = {view.post.platform for view in views if view.state in ACTIVE_STATES}
    return {
        "posts": [
            {
                "id": view.post.id,
                "platform": view.post.platform,
                "state": view.state,
                "source": view.post.source,
                "channel": view.channel,
                "url": view.post.post_url,
                "published_at": _iso(live_at(view.post)) if view.state in ("published", "removed") else None,
                "published_at_source": view.post.published_at_source,
                "scheduled_at": _iso(view.post.scheduled_at),
                "pending_since": _iso(view.post.mp4_downloaded_at or view.post.created_at)
                if view.state == "pending_link"
                else None,
                "views": view.views,
                "views_24h": view.post.views_24h,
                "views_48h": view.views_48h,
                "views_7d": view.post.views_7d,
                "marks_estimated": list(view.post.marks_estimated or []),
                "marks_missed": missed_marks(view),
                "sparkline": trends.get(view.post.id, []),
                "refreshing": view.refreshing,
                "metrics_updated_at": _iso(view.measured_at),
                "error": view.error,
                "retry_job_id": view.retry_job_id,
                "created_by": view.post.created_by.name,
                "created_by_id": view.post.created_by_id,
                "fb": fb_payload(view.post)
                if view.post.platform == "facebook" and view.post.status not in ("pending_link",)
                else None,
            }
            for view in views
        ],
        "missing": [platform for platform in PLATFORMS if platform not in active],
        "captions": {
            "facebook": post_text,
            "tiktok": hashtags.tiktok_caption(video.caption, topic.name if topic else None),
            "youtube": post_text,
        },
        "mp4_download_url": f"/api/videos/{video.id}/video.mp4?download=1" if video.mp4_key else None,
    }
