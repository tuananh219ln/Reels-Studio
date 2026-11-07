"""A member's own TikTok connection (TikTok's Login Kit), on their TikTok AffiliateAccount: made from TikTok's answer to
"Kết nối TikTok", its tokens kept fresh before each use, and what the web may see of it (never a token, nor any part
of one).

One TikTok account (open_id) belongs to one member: a member can only ever post to the TikTok accounts they connected
themselves.
"""

import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from . import crypto, tiktok
from .models import AffiliateAccount, TikTokConnection, TikTokOAuthState
from .sessions import now

STATE_LIFETIME = timedelta(minutes=10)
# A token this close to its end is refreshed before it is used.
REFRESH_MARGIN = timedelta(minutes=5)
RECONNECT = "Kết nối TikTok đã hết hạn, hãy kết nối lại TikTok trong Cài đặt › Tài khoản affiliate"


class ConnectError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _hash(state: str) -> str:
    return hashlib.sha256(state.encode()).hexdigest()


def new_state(db: DbSession, user_id: int) -> str:
    """A one-use state for TikTok's authorize page; only its hash is kept."""
    db.execute(delete(TikTokOAuthState).where(TikTokOAuthState.expires_at <= now()))
    state = secrets.token_urlsafe(32)
    db.add(TikTokOAuthState(state_hash=_hash(state), user_id=user_id, expires_at=now() + STATE_LIFETIME))
    return state


def take_state(db: DbSession, state: str, user_id: int) -> bool:
    """The state was made for this member and is still valid; it is used up either way."""
    if not state:
        return False
    row = db.get(TikTokOAuthState, _hash(state), with_for_update=True)
    if row is None:
        return False
    db.delete(row)
    return row.user_id == user_id and row.expires_at > now()


def profile_url(username: str) -> str:
    return f"https://www.tiktok.com/@{username}"


def _username_of(url: str | None) -> str:
    try:
        path = urlsplit(url or "").path
    except ValueError:
        return ""
    return path.strip("/").removeprefix("@").split("/")[0].lower() if path.startswith("/@") else ""


def _store(connection: TikTokConnection, tokens: tiktok.Tokens) -> None:
    connection.access_token_encrypted = crypto.encrypt(tokens.access_token)
    connection.refresh_token_encrypted = crypto.encrypt(tokens.refresh_token)
    connection.access_expires_at, connection.refresh_expires_at = tokens.access_expires_at, tokens.refresh_expires_at
    connection.scopes = tokens.scope[:200]
    connection.last_error = None


def connect(db: DbSession, user_id: int, tokens: tiktok.Tokens, user: tiktok.User) -> TikTokConnection:
    """Save the connection TikTok just granted, on the member's TikTok account of that username (made when missing).
    Raises ConnectError when the TikTok account is another member's."""
    connection = db.scalar(select(TikTokConnection).where(TikTokConnection.open_id == user.open_id))
    if connection is not None and connection.owner_id != user_id:
        raise ConnectError(f"Tài khoản TikTok @{user.username} đã được một thành viên khác kết nối")
    account = db.get(AffiliateAccount, connection.affiliate_account_id) if connection else None
    if account is None:
        mine = db.scalars(
            select(AffiliateAccount)
            .where(AffiliateAccount.owner_id == user_id, AffiliateAccount.platform == "tiktok")
            .order_by(AffiliateAccount.id)
        )
        account = next(
            (one for one in mine if user.username and _username_of(one.profile_url) == user.username.lower()), None
        )
    if account is None:
        account = AffiliateAccount(
            platform="tiktok",
            owner_id=user_id,
            name=user.display_name or f"@{user.username}",
            profile_url=profile_url(user.username),
            active=True,
        )
        db.add(account)
        db.flush()
    if connection is None:
        # The account was connected before to a TikTok account that is no longer this username's: replaced.
        db.execute(delete(TikTokConnection).where(TikTokConnection.affiliate_account_id == account.id))
        connection = TikTokConnection(owner_id=user_id, affiliate_account_id=account.id, open_id=user.open_id)
        db.add(connection)
    connection.username, connection.display_name = user.username, user.display_name
    connection.avatar_url = user.avatar_url
    _store(connection, tokens)
    db.flush()
    return connection


def of_account(db: DbSession, account_id: int) -> TikTokConnection | None:
    return db.scalar(select(TikTokConnection).where(TikTokConnection.affiliate_account_id == account_id))


def needs_reconnect(connection: TikTokConnection) -> bool:
    return connection.last_error is not None or connection.refresh_expires_at <= now()


def access_token(db: DbSession, connection: TikTokConnection) -> str:
    """A usable access token, refreshed first when it ends within REFRESH_MARGIN; both new tokens are saved (and
    committed) at once, since TikTok has already spent the old refresh token. Raises tiktok.TikTokError."""
    if connection.last_error is not None:
        raise tiktok.TikTokError(RECONNECT, connection.last_error)
    try:
        if connection.access_expires_at - now() > REFRESH_MARGIN:
            return crypto.decrypt(connection.access_token_encrypted)
        refresh_token = crypto.decrypt(connection.refresh_token_encrypted)
    except crypto.CannotDecrypt:
        connection.last_error = "Không đọc được token TikTok đã lưu"
        db.commit()
        raise tiktok.TikTokError("Không đọc được token TikTok đã lưu, hãy kết nối lại TikTok") from None
    try:
        tokens = tiktok.refresh(refresh_token)
    except tiktok.TikTokError as err:
        if err.expired:
            connection.last_error = err.message
            db.commit()
            raise tiktok.TikTokError(RECONNECT, err.detail, err.code) from None
        raise
    _store(connection, tokens)
    db.commit()
    return tokens.access_token


def payload(connection: TikTokConnection | None) -> dict | None:
    """What the web shows of a connection: no token, nor any part of one."""
    if connection is None:
        return None
    return {
        "id": connection.id,
        "username": connection.username,
        "display_name": connection.display_name,
        "avatar_url": connection.avatar_url,
        "access_expires_at": connection.access_expires_at.isoformat(),
        "refresh_expires_at": connection.refresh_expires_at.isoformat(),
        "last_error": connection.last_error,
        "needs_reconnect": needs_reconnect(connection),
        "connected_at": connection.created_at.isoformat() if connection.created_at else None,
    }
