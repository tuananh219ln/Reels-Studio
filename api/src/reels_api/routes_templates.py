"""Edit templates ("Mẫu dựng"): the app's own and the members', saved from a video; putting one on a video ("Tự dựng"
in the studio); and each member's own one for their new videos. See autoedit.py."""

import unicodedata

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, type_coerce
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from reels_render.effects import SCENE_TRANSITIONS

from . import autoedit, edit_log
from .db import get_db
from .errors import ApiError
from .models import EditTemplate, KnowledgeTopic, Session, User
from .ownership import ensure_owner
from .sessions import current_member
from .videos import ensure_unlocked, lock_video, split_scenes, video_payload

router = APIRouter(prefix="/api/edit-templates")

MAX_NAME = 80


class NewTemplateBody(BaseModel):
    name: str
    video_id: int


class RenameBody(BaseModel):
    name: str


class ApplyBody(BaseModel):
    video_id: int
    template: object  # "app" or a team template's id


class DefaultBody(BaseModel):
    template: object = None  # "app", a team template's id, or null for none


def invalid(message: str) -> ApiError:
    return ApiError(422, "invalid_value", message)


def _name(raw: str) -> str:
    name = " ".join(unicodedata.normalize("NFC", raw).split())
    if not name:
        raise invalid("Hãy đặt tên cho mẫu")
    if len(name) > MAX_NAME:
        raise invalid(f"Tên mẫu dài quá {MAX_NAME} ký tự")
    return name


def _item(
    key: object,
    name: str,
    template: autoedit.Template,
    topics: list[dict],
    created_by_id: int | None = None,
    members_using: int = 0,
) -> dict:
    return {
        "id": key,
        "name": name,
        # Who saved it (None for the app's own): only they delete it.
        "created_by_id": created_by_id,
        "builtin": key == autoedit.APP,
        "data": autoedit.asdict(template),
        "summary": autoedit.summary(template),
        # The topic groups that hold it (part 2): their new videos may take it.
        "topics": topics,
        # How many members put it on their new videos: its maker is told before deleting it (2026-11-09).
        "members_using": members_using,
    }


def topics_by_template(db: DbSession) -> dict[int, list[dict]]:
    held: dict[int, list[dict]] = {}
    for topic in db.scalars(select(KnowledgeTopic).order_by(KnowledgeTopic.name)):
        for template in topic.edit_templates:
            held.setdefault(template.id, []).append({"id": topic.id, "name": topic.name})
    return held


def listing(db: DbSession, user_id: int) -> dict:
    rows = db.scalars(select(EditTemplate).order_by(EditTemplate.name)).all()
    held = topics_by_template(db)
    chosen = [value for value in db.scalars(select(User.edit_template_default)) if isinstance(value, int)]
    templates = [_item(autoedit.APP, autoedit.APP_NAME, autoedit.APP_TEMPLATE, [])]
    templates += [
        _item(row.id, row.name, autoedit.parse(row.data), held.get(row.id, []), row.created_by_id, chosen.count(row.id))
        for row in rows
    ]
    return {"templates": templates, "default": autoedit.member_default(db, user_id)}


def mcp_listing(db: DbSession, user_id: int) -> list[dict]:
    """The templates the member works with through MCP (part 5): the app's own, their own, and those a topic group
    holds, each with its scope and the parts an assistant picks by."""
    groups: dict[int, list[dict]] = {}
    for topic in db.scalars(select(KnowledgeTopic).order_by(KnowledgeTopic.name)):
        for template in topic.edit_templates:
            entry = {"id": topic.id, "name": topic.name, "default": topic.edit_template_default == template.id}
            groups.setdefault(template.id, []).append(entry)
    rows = db.scalars(
        select(EditTemplate)
        .where((EditTemplate.created_by_id == user_id) | EditTemplate.id.in_(list(groups) or [0]))
        .order_by(EditTemplate.name)
    ).all()
    app_groups = [
        {"id": topic.id, "name": topic.name, "default": True}
        for topic in db.scalars(select(KnowledgeTopic).order_by(KnowledgeTopic.name))
        if topic.edit_template_default == autoedit.APP
    ]
    items = [_mcp_item(autoedit.APP, autoedit.APP_NAME, autoedit.APP_TEMPLATE, "app", app_groups)]
    for row in rows:
        scope = "personal" if row.created_by_id == user_id else "group"
        items.append(_mcp_item(row.id, row.name, autoedit.parse(row.data), scope, groups.get(row.id, [])))
    return items


def _mcp_item(key: object, name: str, template: autoedit.Template, scope: str, groups: list[dict]) -> dict:
    return {
        "id": key,
        "name": name,
        "scope": scope,  # app, personal (the member's own) or group (held by a topic group)
        "groups": groups,
        "transitions": [SCENE_TRANSITIONS[item].label for item in template.transitions],
        "scene_sounds": bool(template.scene_sounds),
        "end_layer": bool(template.end_layers),
        # A template holds no kind of video: it fits slides and "Video xuyên suốt" alike.
        "video_mode": None,
        "summary": autoedit.summary(template),
    }


def _flush_name(db: DbSession) -> None:
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise invalid("Đã có mẫu trùng tên") from None


def _log(db: DbSession, me: Session, row: EditTemplate, action: str, old: str | None, new: str | None) -> None:
    """ "Lịch sử" of Mẫu dựng: a saved template made, renamed or deleted."""
    changes = {"name": {"old": old, "new": new}} if old != new else {}
    edit_log.record(db, edit_log.TEMPLATE, row.id, action, me.user_id, label=new or old or "", changes=changes)


@router.get("")
def get_templates(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    return listing(db, me.user_id)


@router.post("", status_code=201)
def save_template(body: NewTemplateBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)):
    """ "Lưu thành mẫu": the video's look (autoedit.derive) under a name."""
    name = _name(body.name)
    video = lock_video(db, body.video_id)
    template = autoedit.derive(*split_scenes(db, video))
    if template.is_empty():
        raise invalid("Video này chưa có hiệu ứng nào để lưu thành mẫu")
    row = EditTemplate(name=name, data=autoedit.asdict(template), created_by_id=me.user_id)
    db.add(row)
    _flush_name(db)
    _log(db, me, row, "create", None, name)
    db.commit()
    return listing(db, me.user_id)


@router.patch("/{template_id}")
def rename_template(
    template_id: int, body: RenameBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    row = db.get(EditTemplate, template_id)
    if row is None:
        raise ApiError(404, "template_not_found", "Mẫu này đã bị xoá")
    # Only whoever saved it renames it (2026-11-09), as only they delete it.
    ensure_owner(row.created_by_id, me.user_id, "mẫu này", "đổi tên được")
    old, row.name = row.name, _name(body.name)
    _flush_name(db)
    _log(db, me, row, "update", old, row.name)
    db.commit()
    return listing(db, me.user_id)


@router.delete("/{template_id}")
def delete_template(template_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)):
    row = db.get(EditTemplate, template_id)
    if row is None:
        raise ApiError(404, "template_not_found", "Mẫu này đã bị xoá")
    ensure_owner(row.created_by_id, me.user_id, "mẫu này")
    # Members and groups who put it on their new videos then put none, and the groups no longer hold it.
    chose_it = type_coerce(template_id, JSONB)
    for user in db.scalars(select(User).where(User.edit_template_default == chose_it)):
        user.edit_template_default = None
    for topic in db.scalars(select(KnowledgeTopic).where(KnowledgeTopic.edit_templates.any(EditTemplate.id == row.id))):
        topic.edit_templates.remove(row)
        if topic.edit_template_default == template_id:
            topic.edit_template_default = None
    _log(db, me, row, "delete", row.name, None)
    db.delete(row)
    db.commit()
    return listing(db, me.user_id)


@router.put("/default")
def set_default(body: DefaultBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """The signed-in member's own template for their new videos, once its scenes are written; null for none."""
    if body.template is not None and autoedit.find(db, body.template) is None:
        raise invalid("Không có mẫu này")
    db.get(User, me.user_id).edit_template_default = body.template
    db.commit()
    return listing(db, me.user_id)


@router.post("/apply")
def apply_template(body: ApplyBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Tự dựng": puts the template on the video (transitions and colour replaced, sounds and layers added), in place
    of the one it wore."""
    video = lock_video(db, body.video_id)
    ensure_unlocked(db, video)
    found = autoedit.find(db, body.template)
    if found is None:
        raise invalid("Không có mẫu này")
    # Chosen on the video itself: it replaces the template the video wore and wins over its group's and maker's.
    autoedit.put(db, video, {"id": body.template, "name": found[0], "source": "video"}, found[1])
    db.commit()
    return video_payload(db, video)
