"""The 30-day topic plan of each topic group ("Kế hoạch 30 ngày" on /knowledge), its Backlog, and today's ideas for
"Tạo video"."""

from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import edit_log, plans
from .db import get_db
from .errors import ApiError
from .models import KnowledgeTopic, Session, TopicPlanItem
from .ownership import ensure_owner
from .plans import MAX_PER_DAY, PLAN_DAYS, Idea, PlanError
from .routes_videos import invalid, my_topic_ids
from .sessions import current_member
from .uploads import read_limited

router = APIRouter(prefix="/api/plans")

MAX_PROMPT_LENGTH = 20000


class PlanPatchBody(BaseModel):
    start_date: date | None = None  # null clears it
    per_day: int | None = None
    prompt: str | None = None
    post_times: list[str] | None = None  # "HH:MM", 1 to plans.MAX_POST_TIMES
    video_target: int | None = None  # null clears it


class IdeaBody(BaseModel):
    day: int | None = None  # None: the Backlog
    topic: str
    pain_group: str = ""
    pain: str = ""
    hook: str = ""


class IdeaPatchBody(BaseModel):
    day: int | None = None  # sent as null: into the Backlog
    position: int | None = None  # 1-based place within the day; the end of the day when moved without one
    topic: str | None = None
    pain_group: str | None = None
    pain: str | None = None
    hook: str | None = None


class ReplaceBody(BaseModel):
    ideas: list[IdeaBody]


class BacklogBody(BaseModel):
    ideas: list[IdeaBody]


def _topic(db: DbSession, topic_id: int) -> KnowledgeTopic:
    """Locked: changes to one plan happen one after another, so the MAX_PER_DAY-a-day limit holds."""
    topic = db.scalar(select(KnowledgeTopic).where(KnowledgeTopic.id == topic_id).with_for_update())
    if topic is None:
        raise ApiError(404, "topic_not_found", "Không tìm thấy nhóm chủ đề")
    return topic


def _item(db: DbSession, item_id: int) -> tuple[KnowledgeTopic, TopicPlanItem]:
    topic_id = db.scalar(select(TopicPlanItem.knowledge_topic_id).where(TopicPlanItem.id == item_id))
    if topic_id is None:
        raise _item_not_found()
    topic = _topic(db, topic_id)
    item = db.get(TopicPlanItem, item_id, populate_existing=True)
    if item is None:
        raise _item_not_found()
    return topic, item


def _item_not_found() -> ApiError:
    return ApiError(404, "plan_item_not_found", "Không tìm thấy ý tưởng (có thể đã bị xoá)")


def _idea(body: IdeaBody) -> Idea:
    try:
        return plans.make_idea(body.day, body.topic, body.pain_group, body.pain, body.hook)
    except PlanError as err:
        raise invalid(str(err)) from None


def _check_day(day: int | None) -> None:
    if day is not None and not 1 <= day <= PLAN_DAYS:
        raise invalid(f"Ngày phải từ 1 đến {PLAN_DAYS}")


def _room(db: DbSession, topic_id: int, day: int | None) -> None:
    """At most 5 ideas a day; the Backlog has a far higher limit."""
    if day is None:
        if plans.day_count(db, topic_id, None) >= plans.MAX_BACKLOG:
            raise ApiError(409, "plan_backlog_full", f"Backlog đã đủ {plans.MAX_BACKLOG} ý tưởng")
    elif plans.day_count(db, topic_id, day) >= MAX_PER_DAY:
        raise ApiError(409, "plan_day_full", f"Ngày {day} đã đủ {MAX_PER_DAY} ý tưởng")


def _unique(db: DbSession, topic_id: int, topic: str, own_id: int | None = None) -> None:
    key = plans.topic_key(topic)
    for item in plans.items_of(db, topic_id):
        if item.id != own_id and plans.topic_key(item.topic) == key:
            where = f"ngày {item.day}" if item.day is not None else "trong Backlog"
            raise ApiError(409, "plan_topic_taken", f"Kế hoạch đã có chủ đề này ({where})")


def _saved(db: DbSession, topic: KnowledgeTopic) -> dict:
    db.commit()
    return plans.plan_payload(db, topic)


# Fixed paths first: "/today" and "/items/..." must not be read as a topic id.


@router.get("/today")
def get_today(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> list[dict]:
    """Only the member's own groups (of the Pages they own and use): a teammate's plan is not theirs to make."""
    return plans.today_payload(db, my_topic_ids(db, me.user_id))


@router.get("/items/{item_id}")
def get_item(item_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    item = db.get(TopicPlanItem, item_id)
    if item is None:
        raise _item_not_found()
    return plans.payloads(db, [item])[0]


@router.patch("/items/{item_id}")
def patch_item(
    item_id: int, body: IdeaPatchBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    topic, item = _item(db, item_id)
    # Everything is checked before anything changes: a refused edit leaves the idea as it was.
    limits = {
        "topic": (plans.MAX_TOPIC_LENGTH, "Chủ đề"),
        "pain_group": (plans.MAX_PAIN_GROUP_LENGTH, "Nhóm nỗi đau"),
        "pain": (plans.MAX_PAIN_LENGTH, "Nỗi đau"),
        "hook": (plans.MAX_HOOK_LENGTH, "Góc hook"),
    }
    changes = {}
    try:
        for field, (limit, label) in limits.items():
            value = getattr(body, field)
            if value is not None:
                changes[field] = plans.clean(value, limit, label)
        if "topic" in changes and not changes["topic"]:
            raise PlanError("Thiếu chủ đề")
    except PlanError as err:
        raise invalid(str(err)) from None
    if "topic" in changes:
        _unique(db, topic.id, changes["topic"], item.id)
    for field, value in changes.items():
        setattr(item, field, value)
    if "day" in body.model_fields_set or body.position is not None:
        _move(db, topic, item, body.day if "day" in body.model_fields_set else item.day, body.position)
    item.updated_by_id = me.user_id
    return _saved(db, topic)


def _move(db: DbSession, topic: KnowledgeTopic, item: TopicPlanItem, day: int | None, position: int | None) -> None:
    _check_day(day)
    old_day = item.day
    if day != old_day:
        _room(db, topic.id, day)
    others = [row for row in plans.items_of(db, topic.id) if row.day == day and row.id != item.id]
    place = len(others) if position is None else max(0, min(position - 1, len(others)))
    others.insert(place, item)
    item.day = day
    for number, row in enumerate(others, start=1):
        row.position = number
    if day != old_day:
        plans.renumber(db, topic.id, old_day)


@router.delete("/items/{item_id}")
def delete_item(item_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """The idea only: a video made from it stays."""
    topic, item = _item(db, item_id)
    ensure_owner(item.created_by_id, me.user_id, "ý tưởng này")
    db.delete(item)
    plans.renumber(db, topic.id, item.day)
    return _saved(db, topic)


@router.get("/{topic_id}")
def get_plan(topic_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    topic = db.get(KnowledgeTopic, topic_id)
    if topic is None:
        raise ApiError(404, "topic_not_found", "Không tìm thấy nhóm chủ đề")
    return plans.plan_payload(db, topic)


@router.patch("/{topic_id}")
def patch_plan(
    topic_id: int, body: PlanPatchBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    topic = _topic(db, topic_id)
    before = edit_log.topic_snapshot(topic)
    if "start_date" in body.model_fields_set:
        topic.plan_start_date = body.start_date
    if body.per_day is not None:
        if not plans.MIN_PER_DAY <= body.per_day <= MAX_PER_DAY:
            raise invalid(f"Số ý tưởng mỗi ngày phải từ {plans.MIN_PER_DAY} đến {MAX_PER_DAY}")
        topic.plan_per_day = body.per_day
    if "video_target" in body.model_fields_set:
        if body.video_target is not None and body.video_target < 1:
            raise invalid("Số video mục tiêu phải từ 1 trở lên")
        topic.video_target = body.video_target
    if body.post_times is not None:
        try:
            topic.plan_post_times = plans.check_post_times(body.post_times)
        except PlanError as err:
            raise invalid(str(err)) from None
    if body.prompt is not None:
        prompt = body.prompt.replace("\r\n", "\n").strip()
        if not prompt:
            raise invalid("Prompt không được để trống")
        if len(prompt) > MAX_PROMPT_LENGTH:
            raise invalid(f"Prompt dài quá {MAX_PROMPT_LENGTH} ký tự")
        # The default text is stored as empty, so a later change of the default reaches this group too.
        topic.plan_prompt = "" if prompt == plans.default_prompt() else prompt
    topic.updated_by_id = me.user_id
    changes = edit_log.diff(before, edit_log.topic_snapshot(topic))
    edit_log.record(db, edit_log.TOPIC, topic.id, "update", me.user_id, label=topic.name, changes=changes)
    return _saved(db, topic)


@router.post("/{topic_id}/items", status_code=201)
def add_item(
    topic_id: int, body: IdeaBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    topic = _topic(db, topic_id)
    idea = _idea(body)
    _room(db, topic.id, idea.day)
    _unique(db, topic.id, idea.topic)
    position = plans.day_count(db, topic.id, idea.day) + 1
    db.add(
        TopicPlanItem(
            knowledge_topic_id=topic.id,
            position=position,
            created_by_id=me.user_id,
            updated_by_id=me.user_id,
            day=idea.day,
            topic=idea.topic,
            pain_group=idea.pain_group,
            pain=idea.pain,
            hook=idea.hook,
        )
    )
    return _saved(db, topic)


@router.post("/{topic_id}/backlog")
def add_backlog(
    topic_id: int, body: BacklogBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """Ideas of a previewed file into the Backlog, whatever their day; topics already in the plan are skipped."""
    topic = _topic(db, topic_id)
    ideas = [_idea(IdeaBody(**{**idea.model_dump(), "day": None})) for idea in body.ideas]
    if not ideas:
        raise invalid("Không có ý tưởng nào")
    if plans.day_count(db, topic.id, None) + len(ideas) > plans.MAX_BACKLOG:
        raise ApiError(409, "plan_backlog_full", f"Backlog tối đa {plans.MAX_BACKLOG} ý tưởng")
    added, skipped = plans.add_to_backlog(db, topic, ideas, me.user_id)
    return {**_saved(db, topic), "added": added, "skipped": skipped}


@router.put("/{topic_id}/items")
def replace_items(
    topic_id: int, body: ReplaceBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """Save an imported file or the AI's draft as the 30 days, after a member looked at it; the Backlog stays."""
    topic = _topic(db, topic_id)
    if len(body.ideas) > plans.MAX_IDEAS:
        raise invalid(f"Tối đa {plans.MAX_IDEAS} ý tưởng")
    ideas = [_idea(idea) for idea in body.ideas]
    errors, _ = plans.check_plan(ideas)
    if errors:
        raise invalid(errors[0])
    plans.replace_plan(db, topic, ideas, me.user_id)
    return _saved(db, topic)


@router.post("/{topic_id}/import")
def preview_import(
    topic_id: int,
    file: UploadFile = File(...),
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
) -> dict:
    """What the file holds, without saving anything: the plan is replaced only by "Lưu kế hoạch" (PUT .../items)."""
    if db.get(KnowledgeTopic, topic_id) is None:
        raise ApiError(404, "topic_not_found", "Không tìm thấy nhóm chủ đề")
    data = read_limited(file, plans.MAX_FILE_BYTES, "File lớn quá 1 MB")
    try:
        ideas, row_errors = plans.parse_file(file.filename or "", data)
    except PlanError as err:
        raise invalid(str(err)) from None
    errors, warnings = plans.check_plan(ideas)
    return {
        "ideas": [asdict(idea) for idea in ideas],
        "errors": row_errors + errors,
        "warnings": warnings,
        # Only rows that could not be read stop "Thêm vào Backlog": days and repeats do not matter there.
        "can_backlog": bool(ideas) and not row_errors,
    }


@router.post("/{topic_id}/generate")
def generate(topic_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Tạo bằng AI": a plan job; what it writes waits as a draft and never replaces the plan by itself."""
    topic = _topic(db, topic_id)
    if not plans.enqueue(db, topic.id, me.user_id):
        raise ApiError(409, "plan_busy", "Nhóm chủ đề đang có kế hoạch chờ hoặc đang tạo")
    db.commit()
    return plans.plan_payload(db, db.get(KnowledgeTopic, topic_id))


@router.delete("/{topic_id}/draft")
def drop_draft(topic_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    topic = _topic(db, topic_id)
    topic.plan_draft = None
    return _saved(db, topic)
