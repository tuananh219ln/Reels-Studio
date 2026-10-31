"""The team's Facebook Pages, connected on /fanpages.

Tokens are encrypted with a key generated in the storage folder, which the api and the worker share and which is
not in the database, so a database dump alone does not reveal them. Losing the key only means pasting them again.
"""

import os
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import config
from .facebook import FacebookError, Page
from .models import Fanpage

KEY_FILE = ".settings-key"
TOKEN_TAIL = 4


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


def save(db: DbSession, page_id: str, name: str, token: str, user_id: int) -> Fanpage:
    """Connect a Page, or give a connected one its new token. Either way it is in use afterwards."""
    row = db.scalar(select(Fanpage).where(Fanpage.page_id == page_id))
    if row is None:
        row = Fanpage(page_id=page_id)
        db.add(row)
    row.name, row.active, row.updated_by_id = name, True, user_id
    row.token_encrypted = _fernet().encrypt(token.encode()).decode()
    row.token_tail = token[-TOKEN_TAIL:]
    return row


def in_use(db: DbSession) -> list[Fanpage]:
    return list(db.scalars(select(Fanpage).where(Fanpage.active.is_(True)).order_by(Fanpage.name, Fanpage.id)))


def load_page(db: DbSession, fanpage_id: int | None) -> Page:
    row = db.get(Fanpage, fanpage_id) if fanpage_id is not None else None
    if row is None:
        raise FacebookError("Video chưa chọn Fanpage, hãy chọn Fanpage rồi đăng lại")
    if not row.active:
        raise FacebookError(f"Fanpage “{row.name}” đang ngừng dùng, hãy dùng lại trong Kết nối Fanpage")
    try:
        return Page(row.page_id, _fernet().decrypt(row.token_encrypted.encode()).decode())
    except InvalidToken:
        raise FacebookError(f"Không đọc được token của “{row.name}”, hãy dán token mới trong Kết nối Fanpage") from None
