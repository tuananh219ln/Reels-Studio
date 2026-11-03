""" "Bình luận": visitors' comments under the reels the app posted, read by the worker, answered and hidden by members.

Like reading a post's numbers (metrics.py) none of this is a job: between jobs the worker
- sends what members asked for: a reply (`reply_text`) or a hide, up to `BATCH` a round; and
- reads the comments of up to `BATCH` live posts due a reading: each post of the last `FOLLOW_DAYS` days, every
  `READ_EVERY`, or at once after "Tải bình luận mới".
A request never calls Facebook.

A reply or a hide is stamped before Facebook is asked and never sent again by itself: a failure is recorded on the
comment and waits for a member. A member's retry of a reply whose answer was lost first looks for the Page's reply with
the same text, as the affiliate comment does (post_comments.py). Replies are written by members; nothing here writes
words of its own.
"""

import logging
from datetime import timedelta

from sqlalchemy import and_, func, or_, select, update
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


def ask_for_reading(db: DbSession) -> None:
    """ "Tải bình luận mới": every followed post is due at once."""
    db.execute(
        update(Publication)
        .where(_followed(now()))
        .values(comments_read_at=None)
        .execution_options(synchronize_session=False)
    )


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


def _reply_due():
    return and_(
        PageComment.reply_requested_at.is_not(None),
        PageComment.reply_id.is_(None),
        or_(PageComment.reply_sent_at.is_(None), PageComment.reply_sent_at < PageComment.reply_requested_at),
    )


def _hide_due():
    return and_(
        PageComment.hide_requested_at.is_not(None),
        PageComment.hidden.is_(False),
        or_(PageComment.hide_sent_at.is_(None), PageComment.hide_sent_at < PageComment.hide_requested_at),
    )


def due_sends(db: DbSession, limit: int = BATCH) -> list[PageComment]:
    query = select(PageComment).where(or_(_reply_due(), _hide_due())).order_by(PageComment.id).limit(limit)
    return list(db.scalars(query))


def send(db: DbSession, comment: PageComment) -> None:
    """Send the reply or the hide a member asked for, once. Commits."""
    post = db.get(Publication, comment.publication_id)
    # A hide goes first: a reply under a comment that is being hidden can wait for the next round.
    hiding = comment.hide_requested_at is not None and not comment.hidden
    hiding = hiding and (comment.hide_sent_at is None or comment.hide_sent_at < comment.hide_requested_at)
    may_exist = comment.reply_sent_at is not None
    if hiding:
        comment.hide_sent_at = now()
    else:
        comment.reply_sent_at = now()
    db.commit()
    try:
        page = fanpages.load_page(db, post.fanpage_id)
        if hiding:
            facebook.hide_comment(page, comment.remote_id)
            comment.hidden = True
        else:
            text = comment.reply_text or ""
            found = facebook.page_comment(page, comment.remote_id, text) if may_exist else None
            comment.reply_id = found or facebook.post_comment(page, comment.remote_id, text)
            comment.answered = True
    except FacebookError as err:
        comment.error = err.message
        db.commit()
        log.warning("Could not answer comment %s: %s %s", comment.id, err.message, err.detail)
        return
    comment.error = None
    db.commit()


def run_round(factory: sessionmaker) -> None:
    """One round of the worker. Nothing here may stop the queue: a failure is logged and the next round goes on."""
    for find, act, what in ((due_sends, send, "answer comment"), (due_reads, read, "read the comments of post")):
        try:
            with factory() as db:
                ids = [row.id for row in find(db)]
        except Exception:
            log.exception("Could not look for work to %s", what)
            continue
        model = PageComment if act is send else Publication
        for row_id in ids:
            try:
                with factory() as db:
                    row = db.get(model, row_id)
                    if row is not None:
                        act(db, row)
            except Exception:
                log.exception("Could not %s %s", what, row_id)


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
