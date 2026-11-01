"""The team's text box styles: named boxes (colour, opacity, text and marked-word colours) every member picks from
on the "Thiết lập" tab and Cài đặt › Thiết lập mặc định.

A video copies a style's colours into its own options (text_style "box"), so editing or deleting a style never
changes how an existing video renders. The list is one team setting; no table of its own is needed.
"""

import secrets

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from reels_render.textbox import is_hex

from .db import get_db
from .errors import ApiError
from .models import AppSetting, Session
from .routes_videos import invalid
from .sessions import current_member

router = APIRouter(prefix="/api/settings/text-styles")

KEY = "text_box_styles"
MAX_NAME_LENGTH = 40
MAX_STYLES = 40
OPACITIES = ("solid", "soft", "clear", "none")  # "none": no background, outlined letters


class StyleBody(BaseModel):
    name: str
    box_color: str
    box_opacity: str = "solid"
    text_color: str
    accent_color: str = "auto"


def _styles(db: DbSession) -> list[dict]:
    setting = db.get(AppSetting, KEY)
    value = setting.value if setting else None
    return [style for style in value if isinstance(style, dict)] if isinstance(value, list) else []


def _save(db: DbSession, styles: list[dict], user_id: int) -> None:
    setting = db.get(AppSetting, KEY)
    if setting is None:
        db.add(AppSetting(key=KEY, value=styles, updated_by_id=user_id))
    else:
        setting.value, setting.updated_by_id = styles, user_id
    db.commit()


def _colour(value: str, label: str, allow_auto: bool = False) -> str:
    if allow_auto and value == "auto":
        return value
    if not is_hex(value):
        raise invalid(f"{label} cần dạng #RRGGBB")
    return value.upper()


def _clean(body: StyleBody, others: list[dict]) -> dict:
    name = body.name.strip()
    if not name:
        raise invalid("Cần đặt tên cho kiểu hộp chữ")
    if len(name) > MAX_NAME_LENGTH:
        raise invalid(f"Tên kiểu tối đa {MAX_NAME_LENGTH} ký tự")
    if any(style.get("name", "").casefold() == name.casefold() for style in others):
        raise invalid(f"Đã có kiểu tên “{name}”")
    if body.box_opacity not in OPACITIES:
        raise invalid("Độ trong của hộp không hợp lệ")
    return {
        "name": name,
        "box_color": _colour(body.box_color, "Màu nền hộp"),
        "box_opacity": body.box_opacity,
        "text_color": _colour(body.text_color, "Màu chữ"),
        "accent_color": _colour(body.accent_color, "Màu chữ đánh dấu", allow_auto=True),
    }


def _not_found() -> ApiError:
    return ApiError(404, "text_style_not_found", "Không còn kiểu hộp chữ này (có thể đã bị xoá)")


@router.get("")
def list_styles(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> list[dict]:
    return _styles(db)


@router.post("")
def create_style(body: StyleBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    styles = _styles(db)
    if len(styles) >= MAX_STYLES:
        raise invalid(f"Tối đa {MAX_STYLES} kiểu hộp chữ; xoá bớt kiểu không dùng")
    style = {"id": secrets.token_hex(4)} | _clean(body, styles)
    _save(db, [*styles, style], me.user_id)
    return style


@router.put("/{style_id}")
def update_style(
    style_id: str, body: StyleBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    styles = _styles(db)
    if not any(style.get("id") == style_id for style in styles):
        raise _not_found()
    style = {"id": style_id} | _clean(body, [style for style in styles if style.get("id") != style_id])
    _save(db, [style if item.get("id") == style_id else item for item in styles], me.user_id)
    return style


@router.delete("/{style_id}")
def delete_style(style_id: str, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    styles = _styles(db)
    kept = [style for style in styles if style.get("id") != style_id]
    if len(kept) == len(styles):
        raise _not_found()
    _save(db, kept, me.user_id)
    return {"ok": True}
