"""Edit templates ("Mẫu dựng"): the app's own and the team's, saved from a video; putting one on a video ("Tự dựng"
in the studio); and the one put on every new video. See autoedit.py."""

import unicodedata

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from . import autoedit
from .db import get_db
from .errors import ApiError
from .models import AppSetting, EditTemplate, Session
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


def _item(key: object, name: str, template: autoedit.Template) -> dict:
    return {
        "id": key,
        "name": name,
        "builtin": key == autoedit.APP,
        "data": autoedit.asdict(template),
        "summary": autoedit.summary(template),
    }


def listing(db: DbSession) -> dict:
    rows = db.scalars(select(EditTemplate).order_by(EditTemplate.name)).all()
    templates = [_item(autoedit.APP, autoedit.APP_NAME, autoedit.APP_TEMPLATE)]
    templates += [_item(row.id, row.name, autoedit.parse(row.data)) for row in rows]
    return {"templates": templates, "default": autoedit.default_key(db)}


def _commit_name(db: DbSession) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise invalid("Đã có mẫu trùng tên") from None


@router.get("")
def get_templates(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    return listing(db)


@router.post("", status_code=201)
def save_template(body: NewTemplateBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)):
    """ "Lưu thành mẫu": the video's look (autoedit.derive) under a name."""
    name = _name(body.name)
    video = lock_video(db, body.video_id)
    template = autoedit.derive(*split_scenes(db, video))
    if template.is_empty():
        raise invalid("Video này chưa có hiệu ứng nào để lưu thành mẫu")
    db.add(EditTemplate(name=name, data=autoedit.asdict(template), created_by_id=me.user_id))
    _commit_name(db)
    return listing(db)


@router.patch("/{template_id}")
def rename_template(
    template_id: int, body: RenameBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    row = db.get(EditTemplate, template_id)
    if row is None:
        raise ApiError(404, "template_not_found", "Mẫu này đã bị xoá")
    row.name = _name(body.name)
    _commit_name(db)
    return listing(db)


@router.delete("/{template_id}")
def delete_template(template_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)):
    row = db.get(EditTemplate, template_id)
    if row is None:
        raise ApiError(404, "template_not_found", "Mẫu này đã bị xoá")
    # The template new videos took goes too: new videos then take none.
    if autoedit.default_key(db) == template_id:
        db.get(AppSetting, autoedit.DEFAULT_KEY).value = None
    db.delete(row)
    db.commit()
    return listing(db)


@router.put("/default")
def set_default(body: DefaultBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """The template put on every new video once its scenes are written; null for none."""
    if body.template is not None and autoedit.find(db, body.template) is None:
        raise invalid("Không có mẫu này")
    setting = db.get(AppSetting, autoedit.DEFAULT_KEY)
    if setting is None:
        db.add(AppSetting(key=autoedit.DEFAULT_KEY, value=body.template, updated_by_id=me.user_id))
    else:
        setting.value, setting.updated_by_id = body.template, me.user_id
    db.commit()
    return listing(db)


@router.post("/apply")
def apply_template(body: ApplyBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Tự dựng": puts the template on the video (transitions and colour replaced, sounds and layers added)."""
    video = lock_video(db, body.video_id)
    ensure_unlocked(db, video)
    found = autoedit.find(db, body.template)
    if found is None:
        raise invalid("Không có mẫu này")
    title, scenes = split_scenes(db, video)
    autoedit.apply(db, title, scenes, found[1])
    db.commit()
    return video_payload(db, video)
