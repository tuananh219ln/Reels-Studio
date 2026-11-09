"""Visitors' comments under the reels and articles the app posted, read by the worker so an article can answer one
("Trả lời bình luận", routes_comments.py).

Like reading a post's numbers (metrics.py) this is not a job: between jobs the worker reads the comments of up to
`BATCH` live posts due a reading, each post of the last `FOLLOW_DAYS` days every `READ_EVERY`. A request never calls
Facebook. The "Bình luận" page that answered and hid comments is gone (decisions 2026-11-10): nothing here writes to
Facebook, and a reply or hide asked for before it went is never sent.
"""

import logging
from datetime import timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from . import facebook, fanpages
from .facebook import FacebookError
from .models import PageComment, Publication
from .sessions import now

log = logging.getLogger("reels_api.comments_inbox")

READ_EVERY = timedelta(minutes=30)
FOLLOW_DAYS = 14
BATCH = 3


def _live_at():
    # The SQL twin of videos.live_at.
    return func.coalesce(Publication.scheduled_at, Publication.published_at, Publication.created_at)


def _followed(at):
    return and_(
        Publication.platform == "facebook",
        Publication.remote_id.is_not(None),
        or_(
            Publication.status == "published",
            and_(Publication.status == "scheduled", Publication.scheduled_at <= at),
        ),
        _live_at() > at - timedelta(days=FOLLOW_DAYS),
    )


def due_reads(db: DbSession, limit: int = BATCH) -> list[Publication]:
    at = now()
    read = Publication.comments_read_at
    query = (
        select(Publication)
        .where(_followed(at), or_(read.is_(None), read <= at - READ_EVERY))
        .order_by(read.asc().nulls_first(), Publication.id)
        .limit(limit)
    )
    return list(db.scalars(query))


def read(db: DbSession, post: Publication) -> None:
    """Read the post's comments once and keep them. Commits."""
    post.comments_read_at = now()
    try:
        found = facebook.visitor_comments(fanpages.load_page(db, post.fanpage_id), post.remote_id)
    except FacebookError as err:
        post.comments_error = err.message
        db.commit()
        log.warning("Could not read the comments of post %s: %s %s", post.id, err.message, err.detail)
        return
    post.comments_error = None
    known = {
        row.remote_id: row
        for row in db.scalars(select(PageComment).where(PageComment.remote_id.in_([item["id"] for item in found])))
    }
    for item in found:
        row = known.get(item["id"])
        if row is None:
            row = PageComment(publication_id=post.id, remote_id=item["id"], created_at=item["created"])
            db.add(row)
        row.author_name, row.message = item["author"][:200], item["message"]
        row.hidden = row.hidden or item["hidden"]
        row.answered = row.answered or item["answered"]
    db.commit()


def run_round(factory: sessionmaker) -> None:
    """One round of the worker. Nothing here may stop the queue: a failure is logged and the next round goes on."""
    try:
        with factory() as db:
            ids = [post.id for post in due_reads(db)]
    except Exception:
        log.exception("Could not look for posts whose comments are due a reading")
        return
    for post_id in ids:
        try:
            with factory() as db:
                post = db.get(Publication, post_id)
                if post is not None:
                    read(db, post)
        except Exception:
            log.exception("Could not read the comments of post %s", post_id)


def state(comment: PageComment) -> str:
    """open (waiting for an answer), sending (a reply or hide waits for the worker), answered, hidden, dismissed."""
    if comment.hidden:
        return "hidden"
    if comment.answered:
        return "answered"
    if comment.error is None and (
        (comment.reply_requested_at and comment.reply_id is None) or (comment.hide_requested_at and not comment.hidden)
    ):
        return "sending"
    if comment.dismissed_at:
        return "dismissed"
    return "open"
