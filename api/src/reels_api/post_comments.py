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

How fast the "Bình luận thêm" go up depends on the reel's age (decisions/2026-11-18-comment-pacing.md): in its first
NEW_FOR the Page writes them all in one run, a comment every minute or so; then, until KEEP_FOR, one new comment a day
at a random time of DAY_HOURS (Vietnam time); after that no new one, though a changed text is still edited.

The Page's "Bộ bình luận" comments (aff_sets.py) come last, each kept by its id the same way: the first a random
`first_delay` after the last food comment, the others `delay` apart (the Page's settings, minutes rather than the
food comments' seconds; decisions/2026-11-19-aff-comment-sets.md). The post waits for them with a request dated
ahead, so a restart loses nothing, and the Page writes other reels' comments meanwhile. A set comment Facebook
refuses is tried again by itself AFF_RETRIES later (1, 3, then 10 minutes); after that it waits for "Bình luận ngay".
"""

import logging
import random
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from . import aff_sets, affiliate, facebook, fanpages
from .facebook import FacebookError
from .models import Fanpage, Publication, Video
from .sessions import now
from .shopee import ShopeeError, has_link

log = logging.getLogger("reels_api.post_comments")

# Facebook needs a moment after a reel goes live before it takes comments on it.
DELAY = timedelta(minutes=2)
BATCH = 3
# Pacing, so a run of detailed comments never looks like spam (decisions/2026-11-18-comment-pacing.md): seconds to rest
# after the first comment, between the extras, and after a video's last one before the Page starts another video's;
# and the most comments a Page gets in a day (Vietnam time).
FIRST_GAP = (45, 75)
EXTRA_GAP = (45, 75)
VIDEO_GAP = 60
DAY_CAP = 100
# A reel's age: all its comments at once while new, then one a day in the day's hours, then none.
NEW_FOR = timedelta(hours=24)
KEEP_FOR = timedelta(days=3)
DAY_HOURS = (9, 21)
VIETNAM_TIME = timezone(timedelta(hours=7))
# Seconds after a failed set comment before the worker tries it again by itself, one try each.
AFF_RETRIES = (60, 180, 600)
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


def stage(post: Publication) -> str:
    """ "new" (all its comments in one run), "daily" (one new comment a day) or "stopped" (no new comment)."""
    age = now() - (post.scheduled_at or post.published_at or post.created_at)
    return "new" if age < NEW_FOR else "daily" if age < KEEP_FOR else "stopped"


def in_day_hours(at: datetime) -> bool:
    return DAY_HOURS[0] <= at.astimezone(VIETNAM_TIME).hour < DAY_HOURS[1]


def day_slot(after: datetime, next_day: bool) -> datetime:
    """A random time within DAY_HOURS: on the day after `after`, or else between `after` and the end of the first
    such hours not over yet."""
    local = after.astimezone(VIETNAM_TIME)
    day = local.date() + timedelta(days=1) if next_day else local.date()
    start = datetime.combine(day, time(DAY_HOURS[0]), VIETNAM_TIME)
    end = datetime.combine(day, time(DAY_HOURS[1]), VIETNAM_TIME)
    if not next_day:
        start = max(start, local)
        if start >= end:
            start, end = (
                start.replace(hour=DAY_HOURS[0], minute=0, second=0, microsecond=0) + timedelta(days=1),
                end + timedelta(days=1),
            )
    return start + timedelta(seconds=random.uniform(0, (end - start).total_seconds()))


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
        written = post.comment_id is not None or bool(post.extra_comment_ids) or bool(post.aff_comment_ids)
        resting = post.comment_requested_at is not None and post.comment_requested_at > at
        if live and written and not resting:
            post.comment_requested_at = at
            asked += 1
    return asked


def write(db: DbSession, post: Publication) -> None:
    """Write or edit the post's comment, or, when that is already as it should be, the next of its video's "Bình luận
    thêm", then of its set comments (one Facebook write per call: the Page rests between them, see `_pause`), and
    record what happened. Commits."""
    may_exist = post.comment_sent_at is not None and post.comment_id is None
    tried_before = post.comment_sent_at is not None
    try:
        text = affiliate.comment_text(db, post)
        sets = aff_sets.comments_for(db, post)
    except ShopeeError as err:
        # Stamped like any attempt, so a Shopee that keeps failing is not asked again every round.
        post.comment_sent_at, post.comment_error = now(), f"Không tạo được link Shopee: {err.message}"
        db.commit()
        log.warning("Could not make Shopee links for post %s: %s %s", post.id, err.message, err.detail)
        return
    extras = _extras(db, post)
    affs = [comment for _, comment in sets]
    period = stage(post)
    adds = period != "stopped"
    first_done = not text or (post.comment_id is not None and text == post.comment_text)
    step = _next_step(post, extras, affs, adds)
    if period == "daily" and first_done and _is_new_step(post, step) and not in_day_hours(now()):
        # An older reel's daily comment waits for the day's hours; nothing is stamped, so it is not an attempt.
        post.comment_requested_at = day_slot(now(), next_day=False)
        db.commit()
        return
    post.comment_sent_at = now()
    if not text and not extras and not affs:
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
        after = _next_step(post, extras, affs, adds)
        if after is not None:
            _pause(db, post, row, "first", after)
            return
    elif step is not None:
        kind, place = step
        added = _is_new_step(post, step)
        if kind == "extra":
            done = _write_extra(db, post, page, extras, place, tried_before)
        else:
            done = _write_aff(db, post, page, sets, place, tried_before)
        if not done:
            return
        _count(row)
        after = _next_step(post, extras, affs, adds)
        if after is not None:
            if period == "daily" and added:
                _rest_until(db, post, row, day_slot(now(), next_day=True))
            else:
                _pause(db, post, row, kind, after)
            return
        # The run is over: the Page does not start another video's comments straight away.
        if row is not None:
            row.comments_next_at = now() + timedelta(seconds=VIDEO_GAP)
    post.commented_at, post.comment_error = now(), None
    db.commit()
    log.info("Commented on post %s as %s, %d more, %d set comments", post.id, post.comment_id, len(extras), len(affs))


def _pause(db: DbSession, post: Publication, row: Fanpage | None, wrote: str, after: tuple[str, int]) -> None:
    """The rest before the run's next comment: a new set comment waits the Page's `first_delay` after a food comment
    (or the first) and its `delay` after another set comment, the Page writing other reels' comments meanwhile; any
    other comment waits the food comments' seconds."""
    if after[0] == "aff" and _is_new_step(post, after):
        settings = aff_sets.settings_of(row)
        gap = settings["delay"] if wrote == "aff" else settings["first_delay"]
        _rest_until(db, post, row, now() + timedelta(seconds=random.uniform(*gap)))
    else:
        _rest(db, post, row, FIRST_GAP if wrote == "first" else EXTRA_GAP)


def _extras(db: DbSession, post: Publication) -> list[str]:
    video = db.get(Video, post.video_id) if post.video_id else None
    return [text for text in (video.extra_comments if video else []) if text.strip()]


def _next_place(post: Publication, extras: list[str], adds: bool = True) -> int | None:
    """The first of the video's "Bình luận thêm" still to write (or to edit, its text having changed); without
    `adds`, only one to edit."""
    ids, texts = list(post.extra_comment_ids or []), list(post.extra_comment_texts or [])
    for place, text in enumerate(extras):
        if place >= len(ids):
            return place if adds else None
        if texts[place] != text:
            return place
    return None


def _next_aff(post: Publication, affs: list[str], adds: bool = True) -> int | None:
    """As `_next_place`, for the set comments."""
    ids, texts = list(post.aff_comment_ids or []), list(post.aff_comment_texts or [])
    for place, text in enumerate(affs):
        if place >= len(ids):
            return place if adds else None
        if texts[place] != text:
            return place
    return None


def _next_step(post: Publication, extras: list[str], affs: list[str], adds: bool = True) -> tuple[str, int] | None:
    """The next comment after the first: ("extra", place) while a "Bình luận thêm" is left, then ("aff", place)."""
    place = _next_place(post, extras, adds)
    if place is not None:
        return ("extra", place)
    place = _next_aff(post, affs, adds)
    return ("aff", place) if place is not None else None


def _is_new_step(post: Publication, step: tuple[str, int] | None) -> bool:
    """The step is a comment not on Facebook yet (not an edit)."""
    if step is None:
        return False
    kind, place = step
    return place >= len((post.extra_comment_ids if kind == "extra" else post.aff_comment_ids) or [])


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


def _rest_until(db: DbSession, post: Publication, row: Fanpage | None, until: datetime) -> None:
    """An older reel's run stops until its next day's comment; the Page rests only as after a video."""
    if row is not None:
        row.comments_next_at = now() + timedelta(seconds=VIDEO_GAP)
    post.comment_requested_at = until
    db.commit()
    log.info("Post %s writes its next comment at %s", post.id, until.isoformat())


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


def _write_aff(
    db: DbSession, post: Publication, page, sets: list[tuple[int, str]], place: int, tried_before: bool
) -> bool:
    """One set comment, as `_write_extra` writes a "Bình luận thêm". The first one written keeps the post's sets, and
    each new one counts as a use of its set for the rotation. False when it failed."""
    ids, texts = list(post.aff_comment_ids or []), list(post.aff_comment_texts or [])
    set_id, text = sets[place]
    try:
        if place < len(ids):
            facebook.edit_comment(page, ids[place], text)
            texts[place] = text
        else:
            found = facebook.page_comment(page, post.remote_id, text) if tried_before else None
            ids.append(found or facebook.post_comment(page, post.remote_id, text))
            texts.append(text)
            if post.aff_set_ids is None:
                post.aff_set_ids = [one for one, _ in sets]
            aff_sets.mark_used(db, set_id)
    except FacebookError as err:
        post.comment_error = f"Bình luận aff {place + 1}: {err.message}"
        if post.aff_retries < len(AFF_RETRIES):
            # Asked again for later (a request dated ahead), so the worker's round after it tries once more.
            again = now() + timedelta(seconds=AFF_RETRIES[post.aff_retries])
            post.aff_retries += 1
            post.comment_requested_at = again
            post.comment_error += f" (tự thử lại lúc {again.astimezone(VIETNAM_TIME):%H:%M})"
        db.commit()
        log.warning("Could not write set comment %d on post %s: %s", place + 1, post.id, err.detail)
        return False
    post.aff_comment_ids, post.aff_comment_texts = list(ids), list(texts)
    post.aff_retries = 0
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
        # How many set comments ("Bộ bình luận") are written under it.
        "aff_count": len(post.aff_comment_ids or []),
        "at": post.commented_at.isoformat() if post.commented_at else None,
        "links": link_state(post, state),
    }


def link_state(post: Publication, state: str | None = None) -> str:
    """Whether the Page's comments under the reel hold a Shopee link, from the comments the app wrote and what the
    worker last read on Facebook (`own_comment`, links pasted by hand included): yes; updating (the app is about to
    write or edit its comment); missing (the Page commented, with no link); none (no comment yet); unknown (never read
    and not written by the app); off (not a Facebook post)."""
    if post.platform != "facebook":
        return "off"
    state = state or payload(post)["state"]
    if state == "pending":
        return "updating"
    written = [post.comment_text, *(post.extra_comment_texts or [])] if post.comment_id else []
    written += list(post.aff_comment_texts or [])
    if any(has_link(text) for text in written) or post.own_comment == "link":
        return "yes"
    if post.comment_id or post.own_comment == "no_link":
        return "missing"
    if post.own_comment == "none" or state == "waiting":
        return "none"
    return "unknown"
