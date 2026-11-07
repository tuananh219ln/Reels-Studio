"""A Page's posting queue: rendered videos wait in order, and the worker gives the first one the Page's next free
posting time and schedules it on Facebook through the usual `publish` job.

A Page posts one topic group (`fanpages.knowledge_topic_id`) at its own times (`fanpages.post_times`), or at the group's
posting times when it has none. The worker fills only the next 48 hours: Facebook keeps the MP4 sent when a reel is
scheduled, so a video edited after that would go out as it was. Nothing here calls Facebook; the publish job does.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from .analytics import VIETNAM
from .models import Fanpage, Job, KnowledgeTopic, PageQueueItem, Publication, Video
from .sessions import now
from .videos import (
    OPEN_POST_STATUSES,
    active_job,
    lock_video,
    pending_publication,
    posted_fanpage_ids,
    publications_of,
    render_signature,
    split_scenes,
)

log = logging.getLogger(__name__)

FILL_AHEAD = timedelta(hours=48)
# The publish endpoint asks for 15 minutes and the job for 10; the rest is room for the job to wait in the queue.
FILL_LEAD = timedelta(minutes=30)
# A post of the Page this close to a posting time, scheduled by hand or not, takes that time.
SLOT_GAP = timedelta(minutes=30)
MAX_ITEMS = 100


def post_times(db: DbSession, page: Fanpage) -> list[str]:
    """The Page's own times, else its group's; none without either."""
    if page.post_times:
        return list(page.post_times)
    topic = db.get(KnowledgeTopic, page.knowledge_topic_id) if page.knowledge_topic_id else None
    return list(topic.plan_post_times) if topic and topic.plan_post_times else []


def _slots(times: list[str], start: datetime, until: datetime) -> list[datetime]:
    day, last = start.astimezone(VIETNAM).date(), until.astimezone(VIETNAM).date()
    found = []
    while day <= last:
        for value in times:
            hour, minute = (int(part) for part in value.split(":"))
            at = datetime(day.year, day.month, day.day, hour, minute, tzinfo=VIETNAM)
            if start <= at <= until:
                found.append(at)
        day += timedelta(days=1)
    return sorted(found)


def free_slots(db: DbSession, page: Fanpage, start: datetime, until: datetime) -> list[datetime]:
    """The Page's posting times between the two moments that no post of the Page already takes."""
    slots = _slots(post_times(db, page), start, until)
    if not slots:
        return []
    at = func.coalesce(Publication.scheduled_at, Publication.published_at, Publication.created_at)
    taken = db.scalars(
        select(at).where(
            Publication.fanpage_id == page.id,
            Publication.platform == "facebook",
            Publication.status.in_(OPEN_POST_STATUSES),
            at >= start - SLOT_GAP,
            at <= until + SLOT_GAP,
        )
    ).all()
    return [slot for slot in slots if all(abs(slot - post) >= SLOT_GAP for post in taken)]


def problem(db: DbSession, video: Video, page: Fanpage | None = None) -> str | None:
    """Why the video cannot be posted from the queue now, shown to members; None when it can."""
    if not video.mp4_key:
        return "Video chưa có MP4, hãy render trước"
    title, scenes = split_scenes(db, video)
    if video.rendered_signature != render_signature(video, title, scenes):
        return "MP4 chưa cập nhật theo bản sửa, hãy render lại"
    if page is not None and page.id in posted_fanpage_ids(video, publications_of(db, video.id)):
        return f"Bản MP4 này đã có trên Fanpage “{page.name}”, hãy render bản mới"
    return None


def _busy(db: DbSession, video: Video) -> str | None:
    if active_job(db, video.id) is not None:
        return "Video đang có job chạy, sẽ thử lại khi xong"
    if pending_publication(db, video.id) is not None:
        return "Video đang được đăng, sẽ thử lại khi xong"
    return None


def items_of(db: DbSession, page_id: int) -> list[PageQueueItem]:
    return list(
        db.scalars(
            select(PageQueueItem)
            .where(PageQueueItem.fanpage_id == page_id)
            .order_by(PageQueueItem.position, PageQueueItem.id)
        )
    )


def next_position(db: DbSession, page_id: int) -> int:
    last = db.scalar(select(func.max(PageQueueItem.position)).where(PageQueueItem.fanpage_id == page_id))
    return (last or 0) + 1


def fill(db: DbSession, at: datetime | None = None) -> int:
    """Schedules at most one video per Page, the first one in its queue that can go, at the Page's next free time.
    Commits each Page on its own. Returns how many posts it made."""
    at = at or now()
    page_ids = db.scalars(
        select(Fanpage.id)
        .where(
            Fanpage.active,
            Fanpage.check_error.is_(None),
            Fanpage.id.in_(select(PageQueueItem.fanpage_id)),
        )
        .order_by(Fanpage.id)
    ).all()
    made = 0
    for page_id in page_ids:
        page = db.get(Fanpage, page_id)
        slots = free_slots(db, page, at + FILL_LEAD, at + FILL_AHEAD)
        if slots:
            made += _fill_page(db, page, slots[0], at)
        db.commit()
    return made


def _fill_page(db: DbSession, page: Fanpage, slot: datetime, at: datetime) -> int:
    for item in items_of(db, page.id):
        video = lock_video(db, item.video_id)
        reason = problem(db, video, page) or _busy(db, video)
        if reason is not None:
            if item.error != reason:
                item.error = reason
            item.tried_at = at
            continue
        db.add(
            Publication(
                video_id=video.id,
                platform="facebook",
                fanpage_id=page.id,
                scheduled_at=slot,
                created_by_id=item.added_by_id,
                auto_comment=item.auto_comment,
            )
        )
        db.add(Job(video_id=video.id, kind="publish", status="queued", created_by_id=item.added_by_id))
        db.delete(item)
        db.flush()
        log.info("Queue of Page %s: video %s scheduled at %s", page.id, video.id, slot.isoformat())
        return 1
    return 0


def fill_due(factory: sessionmaker) -> None:
    """Called by the worker between jobs. A database hiccup here must not stop the queue: the next round tries again."""
    try:
        with factory() as db:
            fill(db)
    except Exception:
        log.exception("Could not fill the Page queues")
