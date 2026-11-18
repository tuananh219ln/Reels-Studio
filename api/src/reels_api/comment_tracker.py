"""The "Bình luận" view of "Bài đăng": every reel live on Facebook within post_comments.KEEP_FOR and where the Page's
comments under it stand (the first comment and the video's "Bình luận thêm", post_comments.py), in the order the worker takes them,
with a rough time each run should end. Read only: it never asks the worker for anything and never calls Facebook.

A new reel's estimate walks the queue as post_comments.due_posts orders it (asked first, then by post), one comment per
worker turn with the average rest between them, VIDEO_GAP between videos, and the Page's DAY_CAP a day in Vietnam
time, so a run past the cap ends the next day. An older reel gets one comment a day, so its last is that many days on;
past KEEP_FOR it gets no new one."""

from datetime import datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import post_comments
from .models import Fanpage, Publication, Video
from .sessions import now
from .videos import is_published, live_at, split_scenes, video_name

# The average rest between two comments of a run (post_comments.FIRST_GAP / EXTRA_GAP).
AVERAGE_GAP = timedelta(
    seconds=(sum(post_comments.FIRST_GAP) / 2 + sum(post_comments.EXTRA_GAP) / 2) / 2,
)


def _edits(post: Publication, extras: list[str]) -> int:
    """Comments already on Facebook whose text has changed since."""
    ids, texts = list(post.extra_comment_ids or []), list(post.extra_comment_texts or [])
    return sum(1 for place, text in enumerate(extras) if place < len(ids) and texts[place] != text)


def _written(post: Publication, extras: list[str]) -> int:
    """How many of the video's "Bình luận thêm" are on Facebook as they read now."""
    ids, texts = list(post.extra_comment_ids or []), list(post.extra_comment_texts or [])
    return sum(1 for place, text in enumerate(extras) if place < len(ids) and texts[place] == text)


def _asked(post: Publication) -> bool:
    return post.comment_requested_at is not None and (
        post.comment_sent_at is None or post.comment_sent_at < post.comment_requested_at
    )


def _queued(post: Publication) -> bool:
    """The worker will take the post by itself: a member or a change asked, or "Tự bình luận" has not run yet."""
    return _asked(post) or (post.auto_comment and post.comment_sent_at is None)


def _next_day(at: datetime) -> datetime:
    local = at.astimezone(post_comments.VIETNAM_TIME)
    return datetime.combine(local.date() + timedelta(days=1), time(0, 0), post_comments.VIETNAM_TIME)


def tracker(db: DbSession) -> dict:
    at = now()
    since = at - post_comments.KEEP_FOR
    posts = [
        post
        for post in db.scalars(
            select(Publication).where(
                Publication.platform == "facebook",
                Publication.remote_id.is_not(None),
                Publication.video_id.is_not(None),
            )
        )
        if is_published(post) and live_at(post) >= since
    ]
    pages = {page.id: page for page in db.scalars(select(Fanpage).where(Fanpage.id.in_({p.fanpage_id for p in posts})))}
    today = post_comments._today()
    rows = []
    for post in posts:
        video = db.get(Video, post.video_id)
        title, scenes = split_scenes(db, video)
        extras = [text for text in video.extra_comments if text.strip()]
        written = _written(post, extras)
        period = post_comments.stage(post)
        first_missing = post.comment_id is None and bool(video.pinned_comment.strip())
        new_ones = len(extras) - written - _edits(post, extras) if period != "stopped" else 0
        left = new_ones + _edits(post, extras) + (1 if first_missing else 0)
        if video.manual_comment:
            state = "manual"
        elif not extras:
            state = "no_extras"
        elif left == 0:
            state = "done" if written == len(extras) else "stopped"
        elif post.comment_error and not _queued(post):
            state = "failed"
        elif period == "daily" and new_ones > 0 and (_queued(post) or post.comment_requested_at):
            state = "daily"
        elif _queued(post) or (post.comment_requested_at and post.comment_requested_at > at):
            state = "queued"
        else:
            state = "not_asked"
        resting = post.comment_requested_at if post.comment_requested_at and post.comment_requested_at > at else None
        rows.append(
            {
                "post_id": post.id,
                "video_id": video.id,
                "title": video_name(video, title),
                "fanpage_id": post.fanpage_id,
                "fanpage": pages[post.fanpage_id].name if post.fanpage_id in pages else None,
                "live_at": live_at(post).isoformat(),
                "url": f"https://www.facebook.com/reel/{post.remote_id}",
                "scenes": len(scenes),
                "saved": len(extras),
                "written": written,
                "left": 0 if state in ("manual", "done") else left,
                "first": post_comments.payload(post)["state"],
                "stage": period,
                "state": state,
                "error": post.comment_error,
                "resting_until": resting.isoformat() if resting else None,
                "position": None,
                "eta": None,
            }
        )
    _estimate(rows, posts, pages, at, today)
    rows.sort(key=lambda row: row["live_at"], reverse=True)
    return {
        "day_cap": post_comments.DAY_CAP,
        "pages": [
            {
                "id": page.id,
                "name": page.name,
                "today": page.comments_count if page.comments_day == today else 0,
                "resting_until": page.comments_next_at.isoformat()
                if page.comments_next_at and page.comments_next_at > at
                else None,
            }
            for page in pages.values()
        ],
        "posts": rows,
    }


def _estimate(rows: list[dict], posts: list[Publication], pages: dict, at: datetime, today) -> None:
    """Number the queued posts in the worker's order and give each a rough time its last comment goes up."""
    by_id = {post.id: post for post in posts}
    for row in rows:
        if row["state"] == "daily":
            # One new comment a day, the first at its set time (or within today's hours).
            post = by_id[row["post_id"]]
            first = post.comment_requested_at if post.comment_requested_at and post.comment_requested_at > at else None
            first = first or (at if post_comments.in_day_hours(at) else post_comments.day_slot(at, next_day=False))
            row["eta"] = (first + timedelta(days=max(row["left"] - 1, 0))).isoformat()
    queued = [row for row in rows if row["state"] == "queued"]
    # post_comments.due_posts: the posts asked for come before the ones "Tự bình luận" has not run on, then by post.
    queued.sort(key=lambda row: (not _asked(by_id[row["post_id"]]), row["post_id"]))
    clock: dict[int | None, datetime] = {}
    count: dict[int | None, int] = {}
    for position, row in enumerate(queued, start=1):
        row["position"] = position
        page_id = row["fanpage_id"]
        page = pages.get(page_id)
        if page_id not in clock:
            start = max(at, page.comments_next_at) if page and page.comments_next_at else at
            clock[page_id] = start
            count[page_id] = page.comments_count if page and page.comments_day == today else 0
        resting = by_id[row["post_id"]].comment_requested_at
        if resting and resting > clock[page_id]:
            clock[page_id] = resting
        for _ in range(row["left"]):
            if count[page_id] >= post_comments.DAY_CAP:
                clock[page_id], count[page_id] = _next_day(clock[page_id]), 0
            count[page_id] += 1
            clock[page_id] += AVERAGE_GAP
        row["eta"] = clock[page_id].isoformat()
        clock[page_id] += timedelta(seconds=post_comments.VIDEO_GAP)
