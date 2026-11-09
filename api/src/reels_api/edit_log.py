"""Edit history ("Lịch sử"): who created, edited, deleted or restored a thing, when, and what it was before and after.

Shown where the thing is edited (docs/decisions/2026-11-09-edit-history.md). Every logged edit keeps whole values, so
any version can be read and put back. Topic groups ("Kho kiến thức") are the first logged; other things follow.
"""

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload

from .models import EditLog, KnowledgeTopic

TOPIC = "knowledge_topic"
ENTITY_TYPES = (TOPIC,)

# What a topic group's history follows: what members edit on Kho kiến thức, including its plan's settings.
TOPIC_FIELDS = (
    "name",
    "script_prompt",
    "clone_prompt",
    "revise_prompt",
    "learn_prompt",
    "analyze_prompt",
    "article_prompt",
    "plan_prompt",
    "banned_words",
    "photo_hint",
    "voice_id",
    "templates",
    "edit_template_default",
    "plan_start_date",
    "plan_per_day",
    "plan_post_times",
    "video_target",
)
# What can be put back from its history: text and lists that were valid when saved and depend on nothing else.
TOPIC_RESTORABLE = (
    "script_prompt",
    "clone_prompt",
    "revise_prompt",
    "learn_prompt",
    "analyze_prompt",
    "article_prompt",
    "plan_prompt",
    "banned_words",
    "photo_hint",
    "voice_id",
)
# Prompts with the app's default as a version of their own ("Bản mặc định của app" in their history).
TOPIC_PROMPTS = TOPIC_RESTORABLE[:7]


def topic_snapshot(topic: KnowledgeTopic) -> dict[str, Any]:
    """The group's followed fields as JSON values."""
    values: dict[str, Any] = {}
    for field in TOPIC_FIELDS:
        if field == "templates":
            values[field] = sorted(template.id for template in topic.edit_templates)
            continue
        value = getattr(topic, field)
        values[field] = value.isoformat() if isinstance(value, date) else value
    return values


def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        field: {"old": before.get(field), "new": after.get(field)}
        for field in after
        if before.get(field) != after.get(field)
    }


def record(
    db: DbSession,
    entity_type: str,
    entity_id: int,
    action: str,
    user_id: int | None,
    *,
    label: str = "",
    changes: dict[str, dict[str, Any]] | None = None,
    restored_from_id: int | None = None,
) -> EditLog | None:
    """Adds one entry, committed with the edit. An edit that changed nothing is not logged."""
    if action in ("update", "restore") and not changes:
        return None
    entry = EditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        label=label[:200],
        changes=changes or {},
        user_id=user_id,
        restored_from_id=restored_from_id,
    )
    db.add(entry)
    return entry


def payload(entry: EditLog) -> dict:
    return {
        "id": entry.id,
        "entity_type": entry.entity_type,
        "entity_id": entry.entity_id,
        "action": entry.action,
        "label": entry.label,
        "changes": entry.changes,
        "source": entry.source,
        "restored_from_id": entry.restored_from_id,
        "user": {"id": entry.user.id, "name": entry.user.name} if entry.user else None,
        "created_at": entry.created_at.isoformat(),
    }


def entries(
    db: DbSession, entity_type: str, entity_id: int | None = None, field: str | None = None, limit: int = 100
) -> list[EditLog]:
    """Newest first. `field`: only the entries that changed it (a topic's "name" gives its creation and deletion)."""
    query = select(EditLog).where(EditLog.entity_type == entity_type)
    if entity_id is not None:
        query = query.where(EditLog.entity_id == entity_id)
    if field is not None:
        query = query.where(EditLog.changes.has_key(field))
    query = query.options(selectinload(EditLog.user)).order_by(EditLog.id.desc()).limit(limit)
    return list(db.scalars(query))


def last_edits(db: DbSession, entity_type: str) -> dict[int, EditLog]:
    """Each thing's latest entry ("sửa lần cuối"), by id."""
    query = (
        select(EditLog)
        .where(EditLog.entity_type == entity_type)
        .ext(distinct_on(EditLog.entity_id))
        .order_by(EditLog.entity_id, EditLog.id.desc())
        .options(selectinload(EditLog.user))
    )
    return {entry.entity_id: entry for entry in db.scalars(query)}
