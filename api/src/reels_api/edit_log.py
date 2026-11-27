"""Edit history ("Lịch sử"): who created, edited, deleted or restored a thing, when, and what it was before and after.

Shown where the thing is edited (docs/decisions/2026-11-09-edit-history.md). Every logged edit keeps whole values, so
any version can be read and put back. Topic groups ("Kho kiến thức") are the first logged; other things follow.
"""

from contextvars import ContextVar
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload

from .models import EditLog, KnowledgeTopic, Scene, Video

TOPIC = "knowledge_topic"
# A member on Quản lý người dùng: disabled, enabled, given a temporary password (never its value), their things handed on.
USER = "user"
# The team's shared settings, one history per tab of Cài đặt (settings_log.py, routes_render_nodes.py,
# routes_templates.py): a card's id on the two settings pages, a template's id, 1 for the render machines.
SETTINGS_AI = "settings_ai"
SETTINGS_SOURCES = "settings_sources"
RENDER = "render_settings"
TEMPLATE = "edit_template"
# A video and its scenes ("Lịch sử sửa" on the video page, docs/decisions/2026-11-26-per-group-qc.md): one history per
# video, a scene's fields keyed "scene:<id>:<field>" so the history outlives a deleted scene.
VIDEO = "video"
ENTITY_TYPES = (TOPIC, USER, SETTINGS_AI, SETTINGS_SOURCES, RENDER, TEMPLATE, VIDEO)

# Where the edits of the running request come from: "mcp" while an MCP tool runs (mcp_server.invoke), else "web".
SOURCE: ContextVar[str] = ContextVar("edit_source", default="web")
# The entry being undone while its values are put back (routes_video_story.undo): what is recorded is a "restore".
RESTORING: ContextVar[int | None] = ContextVar("edit_restoring", default=None)

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
    "voice_backup_id",
    "voice_format",
    "video_mode",
    "text_look",
    "text_ai",
    "no_people",
    "outro_cta",
    "youtube_meta",
    "qc_config",
    "stock_order",
    "media_folder",
    "templates",
    "edit_template_default",
    "plan_start_date",
    "plan_per_day",
    "plan_post_times",
    "schedule_timezone",
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
    "voice_backup_id",
)
# Prompts with the app's default as a version of their own ("Bản mặc định của app" in their history).
TOPIC_PROMPTS = TOPIC_RESTORABLE[:7]


# What a video's history follows: what members edit on its page or through MCP (routes_videos.patch_video).
VIDEO_FIELDS = (
    "name",
    "caption",
    "hashtags",
    "affiliates",
    "pinned_survey",
    "extra_comments",
    "music_suggestions",
    "music_volume",
    "music_start",
    "voice_enabled",
    "options",
    "mode",
    "content_type",
    "no_title",
)
# And of each scene (routes_videos.patch_scene).
SCENE_FIELDS = (
    "text",
    "voice_text",
    "seconds",
    "seconds_auto",
    "keywords",
    "keywords_en",
    "image_prompt",
    "voice_id",
    "video_start",
    "video_speed",
    "video_sound",
    "video_loop",
    "text_x",
    "text_y",
    "transition",
    "color",
    "music_level",
    "image_fit",
    "image_crop_offset",
    "text_hold_sec",
    "text_zone",
)
# What "Hoàn tác" puts back: the fields that the same edit routes take back as they were saved. A video's options and a
# text box's place are followed but not put back (they are saved through other shapes).
VIDEO_RESTORABLE = tuple(field for field in VIDEO_FIELDS if field not in ("options",))
SCENE_RESTORABLE = tuple(field for field in SCENE_FIELDS if field not in ("text_x", "text_y"))


def scene_key(scene_id: int, field: str) -> str:
    return f"scene:{scene_id}:{field}"


def parse_scene_key(key: str) -> tuple[int, str] | None:
    """(scene id, field) of a "scene:<id>:<field>" key; None for a field of the video itself."""
    kind, _, rest = key.partition(":")
    scene_id, _, field = rest.partition(":")
    return (int(scene_id), field) if kind == "scene" and scene_id.isdigit() and field else None


def video_snapshot(video: Video, *scenes: Scene | None) -> dict[str, Any]:
    """The video's followed fields, and those of `scenes`, as JSON values."""
    values: dict[str, Any] = {field: getattr(video, field) for field in VIDEO_FIELDS}
    for scene in scenes:
        if scene is not None:
            values |= {scene_key(scene.id, field): getattr(scene, field) for field in SCENE_FIELDS}
    return values


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
    restoring = RESTORING.get()
    if restoring is not None and action == "update":
        action, restored_from_id = "restore", restoring
    entry = EditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        label=label[:200],
        changes=changes or {},
        source=SOURCE.get(),
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
