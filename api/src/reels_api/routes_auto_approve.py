"""The member's own "Tự duyệt" switch (auto_approve.py)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from .db import get_db
from .models import Session, User
from .sessions import current_member

router = APIRouter(prefix="/api/me/auto-approve")


class SwitchBody(BaseModel):
    enabled: bool


@router.get("")
def read(session: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    return {"enabled": db.get(User, session.user_id).auto_approve}


@router.put("")
def save(body: SwitchBody, session: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    db.get(User, session.user_id).auto_approve = body.enabled
    db.commit()
    return {"enabled": body.enabled}
