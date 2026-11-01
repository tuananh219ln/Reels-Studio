"""API keys of the stock libraries (Pixabay, Pexels) and of both AI image providers (Gemini, Cloudflare Workers AI),
pasted on Cài đặt › Nguồn tư liệu.

A key saved there is stored encrypted (crypto) and wins over the server's .env; with none saved, the .env key is
used, so a server set up before this page keeps working. A saved key is never sent back to the browser.
"""

from sqlalchemy.orm import Session as DbSession

from . import config, crypto
from .models import AppSetting

SETTING_KEY = "source_keys"  # app_settings value: {name: encrypted key}
ENV_NAMES = {
    "pixabay": "PIXABAY_API_KEY",
    "pexels": "PEXELS_API_KEY",
    "gemini": "IMAGE_GEN_API_KEY",
    "cloudflare": "IMAGE_GEN_CF_API_KEY",
}
MAX_KEY_LENGTH = 300


class SourceKeyError(ValueError):
    """The message is shown to members."""


def _stored(db: DbSession) -> dict:
    setting = db.get(AppSetting, SETTING_KEY)
    return dict(setting.value) if setting and isinstance(setting.value, dict) else {}


def _saved(db: DbSession, name: str) -> str | None:
    """The saved key; None when none is saved or the storage folder's key cannot read it."""
    encrypted = _stored(db).get(name)
    if not isinstance(encrypted, str) or not encrypted:
        return None
    try:
        return crypto.decrypt(encrypted)
    except crypto.CannotDecrypt:
        return None


def get(db: DbSession, name: str) -> str:
    """The key in use; "" for a name that takes no key."""
    if name not in ENV_NAMES:
        return ""
    return _saved(db, name) or config.read_env(ENV_NAMES[name])


def origin(db: DbSession, name: str) -> str | None:
    """Where the key in use comes from: "saved" (this page), "unreadable" (saved, but must be pasted again),
    "env" (the server's .env) or None (no key)."""
    if name in _stored(db):
        return "saved" if _saved(db, name) else "unreadable"
    return "env" if config.read_env(ENV_NAMES[name]) else None


def save(db: DbSession, name: str, key: str, user_id: int) -> None:
    """Save a pasted key, or remove the saved one when `key` is empty (the .env key, if any, applies again)."""
    key = key.strip()
    if len(key) > MAX_KEY_LENGTH or len(key.split()) > 1:
        raise SourceKeyError("Key không hợp lệ: dán đúng một chuỗi key, không có khoảng trắng")
    stored = _stored(db)
    if key:
        stored[name] = crypto.encrypt(key)
    else:
        stored.pop(name, None)
    setting = db.get(AppSetting, SETTING_KEY)
    if setting is None:
        db.add(AppSetting(key=SETTING_KEY, value=stored, updated_by_id=user_id))
    else:
        setting.value, setting.updated_by_id = stored, user_id
