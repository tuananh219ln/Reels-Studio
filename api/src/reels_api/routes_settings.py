"""Settings members enter in the app. The token only ever goes in: no response carries it."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from . import facebook, page_settings
from .db import get_db
from .errors import ApiError
from .models import Session
from .routes_videos import invalid
from .sessions import current_member

router = APIRouter(prefix="/api/settings")

MAX_TOKEN_LENGTH = 1000


class FacebookBody(BaseModel):
    page_id: str
    token: str = ""


def _payload(db: DbSession) -> dict:
    return {"page_id": page_settings.page_id(db), "has_token": page_settings.has_token(db)}


@router.get("/facebook")
def read_facebook(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    return _payload(db)


@router.put("/facebook")
def save_facebook(body: FacebookBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    page_id, token = body.page_id.strip(), body.token.strip()
    if not page_id.isascii() or not page_id.isdigit():
        raise invalid("Page ID chỉ gồm chữ số")
    if len(token) > MAX_TOKEN_LENGTH or len(token.split()) > 1:
        raise invalid("Token không hợp lệ, hãy chép lại đúng một dòng token")
    if not token and not page_settings.has_token(db):
        raise invalid("Hãy nhập token")
    page_settings.save(db, page_id, token, me.user_id)
    db.commit()
    return _payload(db)


@router.post("/facebook/test")
def test_facebook(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """Reads the Page's name with the saved token; nothing is posted."""
    try:
        return {"page_name": facebook.page_name(page_settings.load_page(db))}
    except facebook.FacebookError as err:
        raise ApiError(422, "facebook_refused", err.message) from None
