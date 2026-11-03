"""The affiliate comment under a posted reel: the video's pinned comment, then one link per usable product attached to
it (affiliate.comment_text, which makes the Page owner's Shopee links first when needed), written by the Page once the
reel is live. Members still pin it on Facebook: the API
cannot pin a comment.

Like reading a post's numbers (metrics.py) it is not a job: the worker writes a few due comments between jobs, and a
request never calls Facebook. A post is due when
- it was made with "Tự bình luận" (`auto_comment`), is live for `DELAY`, and has had no attempt yet; or
- a member asked ("Bình luận ngay" / "Cập nhật bình luận") since the last attempt.

Never two comments: the comment's id is kept and a later request edits that comment. The attempt is stamped before
Facebook is asked, so an answer lost on the way is not retried by itself; a member's retry first looks for a comment
the Page already wrote with the same text. A failed attempt is recorded on the post and waits for a member.
"""

import logging
from datetime import timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from . import affiliate, facebook, fanpages
from .facebook import FacebookError
from .models import Publication
from .sessions import now
from .shopee import ShopeeError

log = logging.getLogger("reels_api.post_comments")

# Facebook needs a moment after a reel goes live before it takes comments on it.
DELAY = timedelta(minutes=2)
BATCH = 3
NOTHING_TO_SAY = "Video chưa có bình luận ghim hay sản phẩm affiliate nào để bình luận"


def _live_at():
    # The SQL twin of videos.live_at.
    return func.coalesce(Publication.scheduled_at, Publication.published_at, Publication.created_at)


def _asked():
    return and_(
        Publication.comment_requested_at.is_not(None),
        or_(Publication.comment_sent_at.is_(None), Publication.comment_sent_at < Publication.comment_requested_at),
    )


def due_posts(db: DbSession, limit: int = BATCH) -> list[Publication]:
    at = now()
    asked = _asked()
    automatic = and_(
        Publication.auto_comment.is_(True), Publication.comment_sent_at.is_(None), _live_at() <= at - DELAY
    )
    query = (
        select(Publication)
        .where(
            Publication.platform == "facebook",
            Publication.remote_id.is_not(None),
            or_(
                Publication.status == "published",
                and_(Publication.status == "scheduled", Publication.scheduled_at <= at),
            ),
            or_(asked, automatic),
        )
        .order_by(asked.desc(), Publication.id)
        .limit(limit)
    )
    return list(db.scalars(query))


def write(db: DbSession, post: Publication) -> None:
    """Write or edit the post's comment once and record what happened. Commits."""
    may_exist = post.comment_sent_at is not None and post.comment_id is None
    try:
        text = affiliate.comment_text(db, post)
    except ShopeeError as err:
        # Stamped like any attempt, so a Shopee that keeps failing is not asked again every round.
        post.comment_sent_at, post.comment_error = now(), f"Không tạo được link Shopee: {err.message}"
        db.commit()
        log.warning("Could not make Shopee links for post %s: %s %s", post.id, err.message, err.detail)
        return
    post.comment_sent_at = now()
    if not text:
        post.comment_error = NOTHING_TO_SAY
        db.commit()
        return
    db.commit()
    try:
        page = fanpages.load_page(db, post.fanpage_id)
        if post.comment_id:
            if text != post.comment_text:
                facebook.edit_comment(page, post.comment_id, text)
        else:
            found = facebook.page_comment(page, post.remote_id, text) if may_exist else None
            post.comment_id = found or facebook.post_comment(page, post.remote_id, text)
    except FacebookError as err:
        post.comment_error = err.message
        db.commit()
        log.warning("Could not comment on post %s: %s %s", post.id, err.message, err.detail)
        return
    post.comment_text, post.commented_at, post.comment_error = text, now(), None
    db.commit()
    log.info("Commented on post %s as %s", post.id, post.comment_id)


def write_due(factory: sessionmaker) -> None:
    """One round of the worker. Nothing here may stop the queue: a failure is logged and the next round goes on."""
    try:
        with factory() as db:
            ids = [post.id for post in due_posts(db)]
    except Exception:
        log.exception("Could not look for comments to write")
        return
    for post_id in ids:
        try:
            with factory() as db:
                post = db.get(Publication, post_id)
                if post is not None:
                    write(db, post)
        except Exception:
            log.exception("Could not comment on post %s", post_id)


def payload(post: Publication) -> dict:
    """The comment as a post shows it. `state`: off (no comment asked), waiting (will be written once live), pending
    (the worker will write it within seconds), done, failed."""
    asked = post.comment_requested_at is not None and (
        post.comment_sent_at is None or post.comment_sent_at < post.comment_requested_at
    )
    if asked:
        state = "pending"
    elif post.comment_error:
        state = "failed"
    elif post.comment_id:
        state = "done"
    elif post.auto_comment and post.comment_sent_at is None:
        state = "waiting" if post.status in ("pending", "scheduled", "published") else "off"
    else:
        state = "off"
    return {
        "state": state,
        "auto": post.auto_comment,
        "error": post.comment_error,
        "text": post.comment_text,
        "at": post.commented_at.isoformat() if post.commented_at else None,
    }
