"""Connecting Facebook Pages. A token only ever goes in: no response carries it, and every token is checked with
Facebook before it is kept."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import joinedload

from . import facebook, fanpages
from .db import get_db
from .errors import ApiError
from .models import Fanpage, Session
from .routes_videos import invalid
from .sessions import current_member

router = APIRouter(prefix="/api/fanpages")

MAX_TOKEN_LENGTH = 1000


class TokenBody(BaseModel):
    token: str


class AddBody(TokenBody):
    page_ids: list[str]


class ActiveBody(BaseModel):
    active: bool


def _clean_token(token: str) -> str:
    token = token.strip()
    if not token:
        raise invalid("Hãy dán token")
    if len(token) > MAX_TOKEN_LENGTH or len(token.split()) > 1:
        raise invalid("Token không hợp lệ, hãy chép lại đúng một dòng token")
    return token


def _pages_of(token: str) -> list[dict]:
    try:
        pages = facebook.managed_pages(token)
    except facebook.FacebookError as err:
        raise ApiError(422, "facebook_refused", err.message) from None
    if not pages:
        raise ApiError(
            422,
            "no_pages",
            "Token không quản lý Page nào: hãy gán Page cho tài khoản tạo token và cấp quyền pages_show_list",
        )
    return pages


def _rows(db: DbSession) -> list[dict]:
    rows = list(db.scalars(select(Fanpage).options(joinedload(Fanpage.updated_by)).order_by(Fanpage.name, Fanpage.id)))
    checks = fanpages.check_payload(db, rows)
    scheduled = fanpages.scheduled_counts(db)
    return [
        {
            "id": row.id,
            "page_id": row.page_id,
            "name": row.name,
            "token_tail": row.token_tail,
            "active": row.active,
            "updated_at": row.updated_at.isoformat(),
            "updated_by": row.updated_by.email if row.updated_by else None,
            "check": checks[row.id],
            "scheduled_posts": scheduled.get(row.id, 0),
        }
        for row in rows
    ]


def _fanpage(db: DbSession, fanpage_id: int) -> Fanpage:
    row = db.scalar(select(Fanpage).where(Fanpage.id == fanpage_id).with_for_update())
    if row is None:
        raise ApiError(404, "fanpage_not_found", "Không tìm thấy Fanpage")
    return row


@router.get("")
def list_fanpages(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> list[dict]:
    return _rows(db)


@router.post("/lookup")
def lookup(body: TokenBody, me: Session = Depends(current_member)) -> dict:
    """The Pages a pasted token manages, to choose from. Nothing is saved here."""
    pages = _pages_of(_clean_token(body.token))
    return {"pages": [{"page_id": page["id"], "name": page["name"], "can_post": page["can_post"]} for page in pages]}


@router.post("", status_code=201)
def add(body: AddBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> list[dict]:
    token = _clean_token(body.token)
    if not body.page_ids:
        raise invalid("Hãy chọn ít nhất một Page")
    usable = {page["id"]: page for page in _pages_of(token) if page["can_post"]}
    if not set(body.page_ids) <= set(usable):
        raise invalid("Token không có quyền đăng lên Page đã chọn")
    for page_id in dict.fromkeys(body.page_ids):
        fanpages.save(db, page_id, usable[page_id]["name"], usable[page_id]["token"], me.user_id)
    db.commit()
    return _rows(db)


@router.put("/{fanpage_id}/token")
def replace_token(
    fanpage_id: int, body: TokenBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> list[dict]:
    token = _clean_token(body.token)
    row = _fanpage(db, fanpage_id)
    page = next((page for page in _pages_of(token) if page["id"] == row.page_id and page["can_post"]), None)
    if page is None:
        raise invalid(f"Token mới không có quyền đăng lên Page “{row.name}”")
    fanpages.save(db, row.page_id, page["name"], page["token"], me.user_id)
    db.commit()
    return _rows(db)


@router.patch("/{fanpage_id}")
def set_active(
    fanpage_id: int, body: ActiveBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> list[dict]:
    row = _fanpage(db, fanpage_id)
    row.active, row.updated_by_id = body.active, me.user_id
    db.commit()
    return _rows(db)


@router.post("/{fanpage_id}/check")
def check_now(fanpage_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> list[dict]:
    """ "Kiểm tra ngay": the worker checks the Page within seconds; a request never calls Facebook."""
    row = _fanpage(db, fanpage_id)
    if not row.active:
        raise invalid(f"Fanpage “{row.name}” đang ngừng dùng, hãy dùng lại trước khi kiểm tra")
    fanpages.request_check(row)
    db.commit()
    return _rows(db)
