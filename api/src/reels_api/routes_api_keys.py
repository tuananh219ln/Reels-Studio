"""Backup narration keys of the team (source_keys.py, api_keys), under the main key of ElevenLabs, Gemini and VieNeu
on Cài đặt. A key only ever goes in; the answers carry its name, last four characters and why a narration last could
not use it (`error`, `error_at`), as for the main key (`main`). Every change is logged like the main key's."""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from . import settings_log, source_keys
from .db import get_db
from .errors import ApiError
from .models import ApiKey, Session
from .routes_videos import invalid
from .sessions import current_member

router = APIRouter(prefix="/api/api-keys")


class AddBody(BaseModel):
    service: str
    api_key: str
    label: str = ""


class ChangeBody(BaseModel):
    label: str | None = None
    move: Literal[-1, 1] | None = None  # one place earlier (-1) or later (1)


def _payload(db: DbSession) -> dict:
    return {
        "services": {
            service: {
                "main": source_keys.main_error(db, service),
                "keys": [
                    {
                        "id": row.id,
                        "label": row.label,
                        "hint": row.tail,
                        "readable": source_keys.readable(row),
                        "error": row.error,
                        "error_at": row.error_at.isoformat() if row.error_at else None,
                    }
                    for row in source_keys.rows(db, service)
                ],
            }
            for service in source_keys.TTS_SERVICES
        },
    }


def _row(db: DbSession, key_id: int) -> ApiKey:
    row = db.get(ApiKey, key_id)
    if row is None:
        raise ApiError(404, "api_key_not_found", "Không có key này")
    return row


def _saved(db: DbSession, me: Session, before: dict) -> dict:
    settings_log.record(db, before, me.user_id)
    db.commit()
    return _payload(db)


@router.get("")
def list_keys(_: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    return _payload(db)


@router.post("")
def add_key(body: AddBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    if body.service not in source_keys.TTS_SERVICES:
        raise ApiError(404, "service_not_found", "Dịch vụ này chỉ có một key")
    before = settings_log.snapshot(db)
    try:
        source_keys.add(db, body.service, body.label, body.api_key, me.user_id)
    except source_keys.SourceKeyError as err:
        raise invalid(str(err)) from None
    return _saved(db, me, before)


@router.patch("/{key_id}")
def change_key(
    key_id: int, body: ChangeBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    row = _row(db, key_id)
    before = settings_log.snapshot(db)
    try:
        if body.label is not None:
            source_keys.rename(row, body.label)
        if body.move is not None:
            source_keys.move(db, row, body.move)
    except source_keys.SourceKeyError as err:
        raise invalid(str(err)) from None
    return _saved(db, me, before)


@router.delete("/{key_id}")
def delete_key(key_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    row = _row(db, key_id)
    before = settings_log.snapshot(db)
    db.delete(row)
    db.flush()
    return _saved(db, me, before)
