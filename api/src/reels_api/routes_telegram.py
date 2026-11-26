"""Cài đặt › Thông báo Telegram: a member links their own Telegram chat, picks what they hear about, sends a test; and
the bot's webhook, which Telegram calls (telegram.py, docs/decisions/2026-11-26-telegram-private.md)."""

import hmac
import html

from fastapi import APIRouter, Body, Depends, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from . import telegram
from .db import get_db
from .errors import ApiError
from .models import Session, User
from .sessions import current_member

router = APIRouter(prefix="/api/telegram")


class MutedBody(BaseModel):
    muted: list[str]


def _me(db: DbSession, me: Session) -> User:
    return db.get(User, me.user_id)


@router.get("")
def status(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    return telegram.status(_me(db, me))


@router.post("/link")
def start_link(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    user = _me(db, me)
    url = telegram.start_link(user)
    db.commit()
    return {"url": url}


@router.delete("/link")
def unlink(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    user = _me(db, me)
    telegram.unlink(user)
    db.commit()
    return telegram.status(user)


@router.put("/muted")
def set_muted(body: MutedBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    user = _me(db, me)
    user.telegram_muted = [kind for kind in telegram.KINDS if kind in set(body.muted)]
    db.commit()
    return telegram.status(user)


@router.post("/test")
def send_test(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    user = _me(db, me)
    if not telegram.configured():
        raise ApiError(409, "telegram_off", telegram.OFF)
    if user.telegram_chat_id is None:
        raise ApiError(409, "telegram_not_linked", "Bạn chưa kết nối Telegram")
    try:
        telegram.send_text(
            user.telegram_chat_id,
            f"🔔 Tin thử từ Reels Studio cho <b>{html.escape(user.name)}</b>. Bot nhắn được cho bạn rồi.",
        )
    except telegram.TelegramError as err:
        raise ApiError(502, "telegram_unreachable", f"Telegram chưa nhận tin: {err}") from None
    return {"ok": True}


@router.post(telegram.WEBHOOK_PATH.removeprefix("/api/telegram"))
def webhook(
    update: dict = Body(default_factory=dict),
    x_telegram_bot_api_secret_token: str = Header(""),
    db: DbSession = Depends(get_db),
) -> dict:
    """Telegram's updates. Only Telegram knows the secret (we gave it with setWebhook); anything else is a 403.
    Always 200 for a real update, even one we could not use, or Telegram sends it again and again."""
    if not telegram.configured() or not hmac.compare_digest(x_telegram_bot_api_secret_token, telegram.webhook_secret()):
        raise ApiError(403, "forbidden", "Không phải Telegram")
    telegram.handle_update(db, update)
    return {"ok": True}
