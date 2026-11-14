"""The posting queue of each Page ("Hàng chờ"): a member adds a rendered video they have watched, it goes to their own
Page of the video's topic group, and the worker schedules it at the Page's next free posting time (page_queue.py).
Nothing here calls Facebook."""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from . import page_queue, plans
from .db import get_db
from .errors import ApiError
from .models import Fanpage, KnowledgeTopic, PageQueueItem, Session, Video
from .ownership import ensure_page_owner
from .routes_videos import invalid
from .sessions import current_member, now
from .videos import lock_video, split_scenes, thumbnail_url, video_name

router = APIRouter(prefix="/api/queue")


class AddBody(BaseModel):
    video_id: int
    fanpage_id: int | None = None  # None: the member's own Page of the video's topic group
    auto_comment: bool = True


class PageBody(BaseModel):
    knowledge_topic_id: int | None = None
    post_times: list[str] | None = None  # None: the group's times


class OrderBody(BaseModel):
    ids: list[int]


def _iso(at: datetime | None) -> str | None:
    return at.isoformat() if at else None


def _item_payload(db: DbSession, item: PageQueueItem) -> dict:
    title, _ = split_scenes(db, item.video)
    return {
        "id": item.id,
        "fanpage_id": item.fanpage_id,
        "fanpage": item.fanpage.name,
        "video": {
            "id": item.video.id,
            "title": video_name(item.video, title),
            "thumbnail_url": thumbnail_url(item.video),
        },
        "auto_comment": item.auto_comment,
        "added_by": item.added_by.name,
        "added_at": item.added_at.isoformat(),
        "tried_at": _iso(item.tried_at),
        "error": item.error,
    }


def _page_payload(db: DbSession, page: Fanpage, me: Session) -> dict:
    topic = db.get(KnowledgeTopic, page.knowledge_topic_id) if page.knowledge_topic_id else None
    at = now()
    return {
        "id": page.id,
        "name": page.name,
        "owner": {"id": page.owner.id, "name": page.owner.name} if page.owner else None,
        "mine": page.owner_id == me.user_id,
        "topic": {"id": topic.id, "name": topic.name} if topic else None,
        "post_times": page_queue.post_times(db, page),
        "own_times": bool(page.post_times),
        "healthy": page.check_error is None,
        "check_error": page.check_error,
        "free_slots": [
            slot.isoformat()
            for slot in page_queue.free_slots(db, page, at + page_queue.FILL_LEAD, at + page_queue.FILL_AHEAD)
        ],
        "items": [_item_payload(db, item) for item in page_queue.items_of(db, page.id)],
    }


def _active_pages(db: DbSession) -> list[Fanpage]:
    return list(db.scalars(select(Fanpage).where(Fanpage.active).order_by(Fanpage.name, Fanpage.id)))


def _queue(db: DbSession, me: Session) -> dict:
    topics = db.scalars(select(KnowledgeTopic).order_by(KnowledgeTopic.name)).all()
    return {
        "pages": [_page_payload(db, page, me) for page in _active_pages(db)],
        "topics": [{"id": topic.id, "name": topic.name} for topic in topics],
        "fill_ahead_hours": int(page_queue.FILL_AHEAD.total_seconds() // 3600),
    }


def _owned_page(db: DbSession, page_id: int, me: Session) -> Fanpage:
    page = db.scalar(select(Fanpage).where(Fanpage.id == page_id).with_for_update())
    if page is None or not page.active:
        raise ApiError(404, "fanpage_not_found", "Không tìm thấy Fanpage đang dùng")
    if page.owner_id != me.user_id:
        raise ApiError(403, "not_page_owner", "Chỉ chủ của Fanpage mới đổi được hàng chờ của Page")
    return page


def _page_for(db: DbSession, video: Video, body: AddBody, me: Session) -> Fanpage:
    if body.fanpage_id is not None:
        page = db.get(Fanpage, body.fanpage_id)
        if page is None or not page.active:
            raise invalid("Hãy chọn một Fanpage đang dùng")
        ensure_page_owner(page, me.user_id)
        return page
    topic = db.get(KnowledgeTopic, video.knowledge_topic_id) if video.knowledge_topic_id else None
    if topic is None:
        raise ApiError(409, "no_topic", "Video chưa thuộc nhóm chủ đề nào, hãy chọn Page")
    mine = db.scalars(
        select(Fanpage)
        .where(Fanpage.active, Fanpage.owner_id == me.user_id, Fanpage.knowledge_topic_id == topic.id)
        .order_by(Fanpage.id)
    ).all()
    if not mine:
        raise ApiError(409, "no_page_for_topic", f"Bạn chưa có Page cho nhóm “{topic.name}”, hãy chọn Page")
    # Two Pages of one group: the one with the shorter queue.
    return min(mine, key=lambda page: len(page_queue.items_of(db, page.id)))


@router.get("")
def queue(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    return _queue(db, me)


@router.get("/videos/{video_id}")
def video_item(video_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """The queue the video waits in, for its "Xuất bản" area; `item` is null when it waits in none."""
    item = db.scalar(select(PageQueueItem).where(PageQueueItem.video_id == video_id))
    return {"item": _item_payload(db, item) if item else None}


@router.post("")
def add(body: AddBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Thêm vào hàng chờ", pressed after watching the MP4."""
    video = lock_video(db, body.video_id)
    reason = page_queue.problem(db, video)
    if reason is not None:
        raise ApiError(409, "not_queueable", reason)
    page = _page_for(db, video, body, me)
    reason = page_queue.problem(db, video, page)
    if reason is not None:
        raise ApiError(409, "not_queueable", reason)
    if db.scalar(select(PageQueueItem.id).where(PageQueueItem.video_id == video.id)) is not None:
        raise ApiError(409, "already_queued", "Video đã ở trong một hàng chờ")
    if len(page_queue.items_of(db, page.id)) >= page_queue.MAX_ITEMS:
        raise ApiError(409, "queue_full", f"Hàng chờ của “{page.name}” đã đủ {page_queue.MAX_ITEMS} video")
    item = PageQueueItem(
        fanpage_id=page.id,
        video_id=video.id,
        position=page_queue.next_position(db, page.id),
        auto_comment=body.auto_comment,
        added_by_id=me.user_id,
    )
    db.add(item)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "already_queued", "Video đã ở trong một hàng chờ") from None
    db.refresh(item)
    payload = _item_payload(db, item)
    db.commit()
    return {"item": payload}


@router.delete("/items/{item_id}")
def remove(item_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Bỏ khỏi hàng chờ": the Page's owner, or the member who added it. A post already made stays."""
    item = db.get(PageQueueItem, item_id)
    if item is None:
        raise ApiError(404, "queue_item_not_found", "Video không còn trong hàng chờ, có thể đã được lên lịch")
    if me.user_id not in (item.added_by_id, item.fanpage.owner_id):
        raise ApiError(403, "not_queue_owner", "Chỉ người thêm video hoặc chủ Fanpage mới bỏ được video khỏi hàng chờ")
    db.delete(item)
    db.commit()
    return _queue(db, me)


@router.post("/pages/{page_id}/order")
def reorder(
    page_id: int, body: OrderBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """Dragging the queue: `ids` is the Page's whole queue in its new order."""
    page = _owned_page(db, page_id, me)
    items = page_queue.items_of(db, page.id)
    if sorted(body.ids) != sorted(item.id for item in items):
        raise ApiError(409, "queue_changed", "Hàng chờ vừa thay đổi, hãy tải lại trang")
    by_id = {item.id: item for item in items}
    for position, item_id in enumerate(body.ids, start=1):
        by_id[item_id].position = position
    db.commit()
    return _queue(db, me)


@router.patch("/pages/{page_id}")
def update_page(
    page_id: int, body: PageBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """The Page's topic group and posting times. An absent field is left as it is; a null `post_times` goes back to
    the group's times. Posts already scheduled keep their time."""
    page = _owned_page(db, page_id, me)
    fields = body.model_fields_set
    if "knowledge_topic_id" in fields:
        if body.knowledge_topic_id is not None and db.get(KnowledgeTopic, body.knowledge_topic_id) is None:
            raise invalid("Không tìm thấy nhóm chủ đề")
        page.knowledge_topic_id = body.knowledge_topic_id
    if "post_times" in fields:
        try:
            page.post_times = plans.check_post_times(body.post_times) if body.post_times is not None else None
        except plans.PlanError as err:
            raise invalid(str(err)) from None
    page.updated_by_id = me.user_id
    db.commit()
    return _queue(db, me)
