"""Edit history ("Lịch sử"): reading a thing's history, and putting one of its versions back (edit_log.py)."""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import edit_log, knowledge
from .db import get_db
from .errors import ApiError
from .models import EditLog, KnowledgeTopic, Session
from .routes_videos import invalid
from .sessions import current_member

router = APIRouter(prefix="/api/edit-logs")


@router.get("")
def list_entries(
    entity_type: str,
    entity_id: int | None = None,
    field: str | None = None,
    limit: int = Query(100, ge=1, le=200),
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
) -> dict:
    if entity_type not in edit_log.ENTITY_TYPES:
        raise invalid("Không có lịch sử cho loại này")
    return {
        "entries": [edit_log.payload(entry) for entry in edit_log.entries(db, entity_type, entity_id, field, limit)]
    }


@router.get("/latest")
def latest(entity_type: str, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """Each thing's (or settings card's) latest entry, by id: the "Sửa lần cuối" line of the settings pages."""
    if entity_type not in edit_log.ENTITY_TYPES:
        raise invalid("Không có lịch sử cho loại này")
    return {
        "latest": {str(key): edit_log.payload(entry) for key, entry in edit_log.last_edits(db, entity_type).items()}
    }


class RestoreBody(BaseModel):
    entity_type: str
    entity_id: int
    field: str
    # The entry whose version is put back; None: the app's default prompt ("Bản mặc định của app").
    log_id: int | None = None
    # "new": the version that entry saved; "old": the one before it (the version from before the history began).
    side: Literal["old", "new"] = "new"


def _default(field: str) -> str:
    """The app's default of a prompt as stored: the text for the two that must not be empty, else empty."""
    if field == "script_prompt":
        return knowledge.default_script_prompt()
    if field == "clone_prompt":
        return knowledge.default_clone_prompt()
    return ""


@router.post("/restore")
def restore(body: RestoreBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """Puts a version back as a new edit of its own ("restore"); nothing in the history is removed."""
    if body.entity_type != edit_log.TOPIC or body.field not in edit_log.TOPIC_RESTORABLE:
        raise invalid("Mục này không khôi phục được")
    topic = db.scalar(select(KnowledgeTopic).where(KnowledgeTopic.id == body.entity_id).with_for_update())
    if topic is None:
        raise ApiError(404, "topic_not_found", "Không tìm thấy nhóm chủ đề")
    if body.log_id is None:
        if body.field not in edit_log.TOPIC_PROMPTS:
            raise invalid("Mục này không có bản mặc định")
        value = _default(body.field)
    else:
        entry = db.get(EditLog, body.log_id)
        if (
            entry is None
            or entry.entity_type != body.entity_type
            or entry.entity_id != topic.id
            or body.field not in entry.changes
        ):
            raise ApiError(404, "edit_log_not_found", "Không tìm thấy bản này trong lịch sử")
        value = entry.changes[body.field][body.side]
        if value is None:
            raise invalid("Bản này không có nội dung để khôi phục")
    before = edit_log.topic_snapshot(topic)
    setattr(topic, body.field, value)
    topic.updated_by_id = me.user_id
    changes = edit_log.diff(before, edit_log.topic_snapshot(topic))
    if not changes:
        raise invalid("Nội dung đang dùng đã giống bản này")
    edit_log.record(
        db,
        edit_log.TOPIC,
        topic.id,
        "restore",
        me.user_id,
        label=topic.name,
        changes=changes,
        restored_from_id=body.log_id,
    )
    db.commit()
    return {"field": body.field, "value": getattr(topic, body.field)}
