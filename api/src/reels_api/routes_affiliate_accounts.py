"""A member's own affiliate accounts (Shopee with its Open API keys, TikTok) and the orders Shopee credited to them.

Unlike the rest of the app, these belong to one member: every query is narrowed to the signed-in member, and an
account of someone else answers as if it did not exist. A Secret only ever goes in: no response carries it.
"""

import unicodedata
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from . import affiliate, crypto, shopee
from .db import get_db
from .errors import ApiError
from .models import AffiliateAccount, AffiliateConversion, Fanpage, Publication, Session, Video
from .routes_videos import invalid
from .sessions import current_member
from .videos import split_scenes, title_of

router = APIRouter(prefix="/api/affiliate-accounts")

PLATFORMS = {"shopee": "Shopee", "tiktok": "TikTok"}
MAX_NAME_LENGTH = 200
MAX_APP_ID_LENGTH = 64
MAX_SECRET_LENGTH = 300
MAX_URL_LENGTH = 500
SECRET_TAIL = 4
REVENUE_DAYS = (7, 30, 90)


class AccountBody(BaseModel):
    platform: str
    name: str
    app_id: str | None = None
    secret: str | None = None  # empty when editing: keep the saved one
    profile_url: str | None = None
    active: bool = True


def _name(value: str) -> str:
    value = " ".join(unicodedata.normalize("NFC", value).split())
    if not value:
        raise invalid("Tên tài khoản không được để trống")
    if len(value) > MAX_NAME_LENGTH:
        raise invalid(f"Tên tài khoản dài quá {MAX_NAME_LENGTH} ký tự")
    return value


def _one_word(value: str | None, label: str, limit: int) -> str:
    value = (value or "").strip()
    if not value:
        raise invalid(f"Hãy nhập {label}")
    if len(value) > limit or len(value.split()) > 1:
        raise invalid(f"{label} không hợp lệ, hãy chép lại đúng một dòng")
    return value


def _profile_url(value: str | None) -> str:
    value = (value or "").strip()
    try:
        parts = urlsplit(value)
    except ValueError:
        parts = None
    host = (parts.hostname or "") if parts else ""
    if (
        not parts
        or parts.scheme != "https"
        or not (host == "tiktok.com" or host.endswith(".tiktok.com"))
        or not parts.path.startswith("/@")
        or len(value) > MAX_URL_LENGTH
    ):
        raise invalid("Link kênh TikTok phải có dạng https://www.tiktok.com/@ten-kenh")
    return value


def _payload(account: AffiliateAccount) -> dict:
    return {
        "id": account.id,
        "platform": account.platform,
        "platform_label": PLATFORMS[account.platform],
        "name": account.name,
        "app_id": account.app_id,
        "secret_tail": account.secret_tail,
        "profile_url": account.profile_url,
        "active": account.active,
        "report_read_at": account.report_read_at.isoformat() if account.report_read_at else None,
        "report_error": account.report_error,
    }


def _mine(db: DbSession, me: Session) -> list[AffiliateAccount]:
    query = select(AffiliateAccount).where(AffiliateAccount.owner_id == me.user_id)
    return list(db.scalars(query.order_by(AffiliateAccount.platform, AffiliateAccount.name, AffiliateAccount.id)))


def _own(db: DbSession, account_id: int, me: Session) -> AffiliateAccount:
    account = db.get(AffiliateAccount, account_id)
    if account is None or account.owner_id != me.user_id:
        raise ApiError(404, "account_not_found", "Không tìm thấy tài khoản")
    return account


def _apply(account: AffiliateAccount, body: AccountBody) -> None:
    account.name, account.active = _name(body.name), body.active
    if account.platform == "shopee":
        account.app_id = _one_word(body.app_id, "App ID", MAX_APP_ID_LENGTH)
        if body.secret and body.secret.strip() or account.secret_encrypted is None:
            secret = _one_word(body.secret, "Secret", MAX_SECRET_LENGTH)
            account.secret_encrypted, account.secret_tail = crypto.encrypt(secret), secret[-SECRET_TAIL:]
            account.report_error = None
    else:
        account.profile_url = _profile_url(body.profile_url)


@router.get("")
def list_accounts(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> list[dict]:
    return [_payload(account) for account in _mine(db, me)]


@router.post("", status_code=201)
def add_account(body: AccountBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    if body.platform not in PLATFORMS:
        raise invalid("Nền tảng không có trong danh sách")
    account = AffiliateAccount(platform=body.platform, owner_id=me.user_id)
    _apply(account, body)
    db.add(account)
    db.commit()
    return _payload(account)


@router.put("/{account_id}")
def update_account(
    account_id: int, body: AccountBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    account = _own(db, account_id, me)
    _apply(account, body)
    db.commit()
    return _payload(account)


@router.delete("/{account_id}")
def delete_account(account_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """Remove an account added by mistake. One with posts or orders is kept for its history: stop using it instead."""
    account = _own(db, account_id, me)
    used = db.scalar(
        select(func.count()).select_from(Publication).where(Publication.affiliate_account_id == account.id)
    )
    orders = db.scalar(
        select(func.count()).select_from(AffiliateConversion).where(AffiliateConversion.account_id == account.id)
    )
    if used or orders:
        raise ApiError(409, "account_in_use", "Tài khoản đã có bài đăng hoặc đơn hàng nên được giữ lại; hãy ngừng dùng")
    db.delete(account)
    db.commit()
    return {"ok": True}


@router.post("/{account_id}/check")
def check_account(account_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Kiểm tra kết nối": one small product search with the account's keys (no link, no cost), like the AI
    providers' check on /settings/ai."""
    credentials = affiliate.credentials(_own(db, account_id, me))
    if credentials is None:
        raise invalid("Chỉ kiểm tra được tài khoản Shopee đang dùng, có App ID và Secret")
    try:
        shopee.search(credentials, "sữa", limit=1)
    except shopee.ShopeeError as err:
        return {"ok": False, "error": err.message}
    return {"ok": True, "error": None}


@router.get("/revenue")
def revenue(days: int = 30, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """The member's own Shopee orders of the last `days`, by video and Page (from the sub ids of its links)."""
    if days not in REVENUE_DAYS:
        raise invalid("Khoảng thời gian không hợp lệ")
    since = datetime.now(UTC) - timedelta(days=days)
    rows = list(
        db.scalars(
            select(AffiliateConversion)
            .join(AffiliateAccount, AffiliateAccount.id == AffiliateConversion.account_id)
            .where(AffiliateAccount.owner_id == me.user_id, AffiliateConversion.purchased_at >= since)
            .order_by(AffiliateConversion.purchased_at.desc())
        )
    )
    groups: dict[tuple[int | None, int | None], dict] = defaultdict(lambda: {"orders": 0, "commission": 0})
    for row in rows:
        group = groups[(row.video_id, row.fanpage_id)]
        group["orders"] += 1
        group["commission"] += row.commission
    lines = []
    for (video_id, fanpage_id), totals in groups.items():
        video = db.get(Video, video_id) if video_id else None
        page = db.get(Fanpage, fanpage_id) if fanpage_id else None
        title = (title_of(video, split_scenes(db, video)[0]) or video.topic) if video else None
        lines.append(
            {
                "video_id": video_id,
                "title": title,
                "fanpage": page.name if page else None,
                **totals,
            }
        )
    lines.sort(key=lambda line: line["commission"], reverse=True)
    return {
        "days": days,
        "orders": len(rows),
        "commission": sum(row.commission for row in rows),
        "lines": lines,
        "accounts": [_payload(account) for account in _mine(db, me) if account.platform == "shopee"],
    }
