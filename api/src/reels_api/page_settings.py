"""The Facebook Page id and token, entered on /settings and kept in the `settings` table.

The token is encrypted with a key generated in the storage folder, which the api and the worker share and which
is not in the database, so a database dump alone does not reveal it. Losing the key only means entering the
token again.
"""

import os
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session as DbSession

from . import config
from .facebook import FacebookError, Page
from .models import Setting

PAGE_ID = "facebook_page_id"
TOKEN = "facebook_page_token"
KEY_FILE = ".settings-key"


def _fernet() -> Fernet:
    path = config.storage_dir() / KEY_FILE
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temp = tempfile.mkstemp(dir=path.parent, prefix=".settings-key-")
        try:
            with os.fdopen(handle, "wb") as file:
                file.write(Fernet.generate_key())
            # A link never replaces a key made a moment earlier by the other process.
            try:
                os.link(temp, path)
            except FileExistsError:
                pass
        finally:
            Path(temp).unlink(missing_ok=True)
    return Fernet(path.read_bytes().strip())


def _set(db: DbSession, key: str, value: str, user_id: int) -> None:
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=value, updated_by_id=user_id))
    else:
        row.value, row.updated_by_id = value, user_id


def _value(db: DbSession, key: str) -> str:
    row = db.get(Setting, key)
    return row.value if row is not None else ""


def page_id(db: DbSession) -> str:
    return _value(db, PAGE_ID)


def has_token(db: DbSession) -> bool:
    return bool(_value(db, TOKEN))


def save(db: DbSession, new_page_id: str, new_token: str, user_id: int) -> None:
    """An empty token keeps the saved one, because the page never gets it back to fill in."""
    _set(db, PAGE_ID, new_page_id, user_id)
    if new_token:
        _set(db, TOKEN, _fernet().encrypt(new_token.encode()).decode(), user_id)


def load_page(db: DbSession) -> Page:
    saved_id, encrypted = page_id(db), _value(db, TOKEN)
    if not saved_id or not encrypted:
        raise FacebookError("Chưa nhập Page ID và token, hãy vào Cài đặt")
    try:
        return Page(saved_id, _fernet().decrypt(encrypted.encode()).decode())
    except InvalidToken:
        raise FacebookError("Không đọc được token đã lưu, hãy nhập lại trong Cài đặt") from None
