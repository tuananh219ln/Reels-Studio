"""The team's Facebook Pages, connected on /fanpages.

Tokens are encrypted with the storage folder's key (see crypto.py).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import crypto
from .facebook import FacebookError, Page
from .models import Fanpage

TOKEN_TAIL = 4


def save(db: DbSession, page_id: str, name: str, token: str, user_id: int) -> Fanpage:
    """Connect a Page, or give a connected one its new token. Either way it is in use afterwards."""
    row = db.scalar(select(Fanpage).where(Fanpage.page_id == page_id))
    if row is None:
        row = Fanpage(page_id=page_id)
        db.add(row)
    row.name, row.active, row.updated_by_id = name, True, user_id
    row.token_encrypted = crypto.encrypt(token)
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
        return Page(row.page_id, crypto.decrypt(row.token_encrypted))
    except crypto.CannotDecrypt:
        raise FacebookError(f"Không đọc được token của “{row.name}”, hãy dán token mới trong Kết nối Fanpage") from None
