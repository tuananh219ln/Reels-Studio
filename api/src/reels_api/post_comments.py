"""The affiliate comment under a posted reel: the video's pinned comment, then one link per usable product attached to
it (affiliate.comment_text, which makes the Page owner's Shopee links first when needed), written by the Page once the
reel is live. Members still pin it on Facebook: the API
cannot pin a comment.

Like reading a post's numbers (metrics.py) it is not a job: the worker writes a few due comments between jobs, and a
request never calls Facebook. A post is due when
- it was made with "Tự bình luận" (`auto_comment`), is live for `DELAY`, and has had no attempt yet; or
- a member asked ("Bình luận ngay" / "Cập nhật bình luận") since the last attempt;
and never under a video marked "Đã dán link tay" (`videos.manual_comment`), whose links a member pasted by hand.

Never two comments: the comment's id is kept and a later request edits that comment. The video's "Bình luận thêm"
follow the first, in order, each kept by its id the same way. The attempt is stamped before
Facebook is asked, so an answer lost on the way is not retried by itself; a member's retry first looks for a comment
the Page already wrote with the same text. A failed attempt is recorded on the post and waits for a member.
"""

import logging
import random
from datetime import timedelta, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from . import affiliate, facebook, fanpages
from .facebook import FacebookError
from .models import Fanpage, Publication, Video
from .sessions import now
from .shopee import ShopeeError

log = logging.getLogger("reels_api.post_comments")

# Facebook needs a moment after a reel goes live before it takes comments on it.
DELAY = timedelta(minutes=2)
BATCH = 3
# Pacing, so a run of detailed comments never looks like spam (decisions/2026-11-18-food-comments.md): seconds to rest
# after the first comment, between the extras, and after a video's last one before the Page starts another video's;
# and the most comments a Page gets in a day (Vietnam time).
FIRST_GAP = (30, 60)
EXTRA_GAP = (45, 90)
VIDEO_GAP = 300
DAY_CAP = 100
VIETNAM_TIME = timezone(timedelta(hours=7))
NOTHING_TO_SAY = "Video chưa có bình luận ghim hay sản phẩm affiliate nào để bình luận"


def _live_at():
    # The SQL twin of videos.live_at.
    return func.coalesce(Publication.scheduled_at, Publication.published_at, Publication.created_at)


def _asked(at):
    # A request dated in the future is the worker's own pause before the next comment of a run.
    return and_(
        Publication.comment_requested_at.is_not(None),
        Publication.comment_requested_at <= at,
        or_(Publication.comment_sent_at.is_(None), Publication.comment_sent_at < Publication.comment_requested_at),
    )


def _today():
    return (now().astimezone(VIETNAM_TIME)).date()


def _may_write(at):
    """The Page is not resting and has not had its day's comments."""
    return or_(
        Publication.fanpage_id.is_(None),
        Publication.fanpage_id.in_(
            select(Fanpage.id).where(
                or_(Fanpage.comments_next_at.is_(None), Fanpage.comments_next_at <= at),
                or_(Fanpage.comments_day.is_(None), Fanpage.comments_day != _today(), Fanpage.comments_count < DAY_CAP),
            )
        ),
    )


def due_posts(db: DbSession, limit: int = BATCH) -> list[Publication]:
    at = now()
    asked = _asked(at)
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
            _may_write(at),
            or_(
                Publication.video_id.is_(None),
                Publication.video_id.not_in(select(Video.id).where(Video.manual_comment.is_(True))),
            ),
        )
        .order_by(asked.desc(), Publication.id)
        .limit(limit)
    )
    return list(db.scalars(query))


def ask_after_edit(db: DbSession, video: Video) -> int:
    """A member changed the video's pinned comment or "Bình luận thêm": ask the worker to bring the comments already
    written under its live Facebook posts up to date, as "Cập nhật bình luận" does. A post with no comment yet is left
    to "Tự bình luận" or "Bình luận ngay", a video marked "Đã dán link tay" is left alone, and a post resting before its
    run's next comment keeps that time. Returns how many posts were asked. Does not commit."""
    if video.manual_comment:
        return 0
    at, asked = now(), 0
    posts = db.scalars(
        select(Publication).where(
            Publication.video_id == video.id,
            Publication.platform == "facebook",
            Publication.remote_id.is_not(None),
            Publication.comment_sent_at.is_not(None),
        )
    )
    for post in posts:
        live = post.status == "published" or (
            post.status == "scheduled" and post.scheduled_at is not None and post.scheduled_at <= at
        )
        written = post.comment_id is not None or bool(post.extra_comment_ids)
        resting = post.comment_requested_at is not None and post.comment_requested_at > at
        if live and written and not resting:
            post.comment_requested_at = at
            asked += 1
    return asked


def write(db: DbSession, post: Publication) -> None:
    """Write or edit the post's comment, or, when that is already as it should be, the next of its video's "Bình luận
    thêm" (one Facebook write per call: the Page rests between them, see `_rest`), and record what happened. Commits."""
    may_exist = post.comment_sent_at is not None and post.comment_id is None
    tried_before = post.comment_sent_at is not None
    try:
        text = affiliate.comment_text(db, post)
    except ShopeeError as err:
        # Stamped like any attempt, so a Shopee that keeps failing is not asked again every round.
        post.comment_sent_at, post.comment_error = now(), f"Không tạo được link Shopee: {err.message}"
        db.commit()
        log.warning("Could not make Shopee links for post %s: %s %s", post.id, err.message, err.detail)
        return
    extras = _extras(db, post)
    post.comment_sent_at = now()
    if not text and not extras:
        post.comment_error = NOTHING_TO_SAY
        db.commit()
        return
    db.commit()
    spent = False
    try:
        page = fanpages.load_page(db, post.fanpage_id)
        if text:
            if post.comment_id:
                if text != post.comment_text:
                    facebook.edit_comment(page, post.comment_id, text)
                    spent = True
            else:
                found = facebook.page_comment(page, post.remote_id, text) if may_exist else None
                post.comment_id = found or facebook.post_comment(page, post.remote_id, text)
                spent = True
            post.comment_text = text
            db.commit()
    except FacebookError as err:
        post.comment_error = err.message
        db.commit()
        log.warning("Could not comment on post %s: %s %s", post.id, err.message, err.detail)
        return
    row = db.get(Fanpage, post.fanpage_id)
    if spent:
        _count(row)
        if _next_place(post, extras) is not None:
            _rest(db, post, row, FIRST_GAP)
            return
    elif _next_place(post, extras) is not None:
        place = _next_place(post, extras)
        if not _write_extra(db, post, page, extras, place, tried_before):
            return
        _count(row)
        if _next_place(post, extras) is not None:
            _rest(db, post, row, EXTRA_GAP)
            return
        # The run is over: the Page does not start another video's comments straight away.
        if row is not None:
            row.comments_next_at = now() + timedelta(seconds=VIDEO_GAP)
    post.commented_at, post.comment_error = now(), None
    db.commit()
    log.info("Commented on post %s as %s, %d more", post.id, post.comment_id, len(extras))


def _extras(db: DbSession, post: Publication) -> list[str]:
    video = db.get(Video, post.video_id) if post.video_id else None
    return [text for text in (video.extra_comments if video else []) if text.strip()]


def _next_place(post: Publication, extras: list[str]) -> int | None:
    """The first of the video's "Bình luận thêm" still to write (or to edit, its text having changed)."""
    ids, texts = list(post.extra_comment_ids or []), list(post.extra_comment_texts or [])
    for place, text in enumerate(extras):
        if place >= len(ids) or texts[place] != text:
            return place
    return None


def _count(row: Fanpage | None) -> None:
    """One more comment written by the Page today (Vietnam time)."""
    if row is None:
        return
    day = _today()
    row.comments_count = (row.comments_count + 1) if row.comments_day == day else 1
    row.comments_day = day


def _rest(db: DbSession, post: Publication, row: Fanpage | None, gap: tuple[int, int]) -> None:
    """Stop for a random while before the run's next comment: the Page writes nothing until then, and the post is asked
    again for that time (a request dated ahead), so the worker's next round after it carries on."""
    until = now() + timedelta(seconds=random.uniform(*gap))
    if row is not None:
        row.comments_next_at = until
    post.comment_requested_at = until
    db.commit()
    log.info("Post %s rests until %s before its next comment", post.id, until.isoformat())


def _write_extra(db: DbSession, post: Publication, page, extras: list[str], place: int, tried_before: bool) -> bool:
    """One "Bình luận thêm": an earlier one edited when its text changed, a new one written (or, after an attempt whose
    answer may have been lost, found first). It is recorded as soon as Facebook takes it, so a later failure never
    writes it twice. One removed from the video is left on Facebook. False when it failed."""
    ids, texts = list(post.extra_comment_ids or []), list(post.extra_comment_texts or [])
    text = extras[place]
    try:
        if place < len(ids):
            facebook.edit_comment(page, ids[place], text)
            texts[place] = text
        else:
            found = facebook.page_comment(page, post.remote_id, text) if tried_before else None
            ids.append(found or facebook.post_comment(page, post.remote_id, text))
            texts.append(text)
    except FacebookError as err:
        post.comment_error = f"Bình luận thêm {place + 1}: {err.message}"
        db.commit()
        log.warning("Could not write extra comment %d on post %s: %s", place + 1, post.id, err.detail)
        return False
    post.extra_comment_ids, post.extra_comment_texts = list(ids), list(texts)
    db.commit()
    return True


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
        # How many of the video's "Bình luận thêm" are written under the post.
        "extra_count": len(post.extra_comment_ids or []),
        "at": post.commented_at.isoformat() if post.commented_at else None,
    }
