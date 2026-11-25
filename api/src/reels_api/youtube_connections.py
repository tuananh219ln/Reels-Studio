"""A member's own YouTube connection (Google's OAuth), on the `channels` row of that channel: made from Google's answer
to "Kết nối YouTube", its access token kept fresh before each use, and what the web may see of it (never a token, nor
any part of one).

One YouTube channel belongs to one member: a member uploads only to the channels they connected themselves.
"""

import hashlib
import secrets
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session as DbSession

from . import crypto, youtube_upload
from .models import Channel, YouTubeConnection, YouTubeOAuthState
from .sessions import now

STATE_LIFETIME = timedelta(minutes=10)
# A token this close to its end is refreshed before it is used.
REFRESH_MARGIN = timedelta(minutes=5)
RECONNECT = "Kết nối YouTube đã hết hạn, hãy bấm Kết nối YouTube lại ở Quản lý kênh"


class ConnectError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _hash(state: str) -> str:
    return hashlib.sha256(state.encode()).hexdigest()


def new_state(db: DbSession, user_id: int) -> str:
    """A one-use state for Google's consent page; only its hash is kept."""
    db.execute(delete(YouTubeOAuthState).where(YouTubeOAuthState.expires_at <= now()))
    state = secrets.token_urlsafe(32)
    db.add(YouTubeOAuthState(state_hash=_hash(state), user_id=user_id, expires_at=now() + STATE_LIFETIME))
    return state


def take_state(db: DbSession, state: str, user_id: int) -> bool:
    """The state was made for this member and is still valid; it is used up either way."""
    if not state:
        return False
    row = db.get(YouTubeOAuthState, _hash(state), with_for_update=True)
    if row is None:
        return False
    db.delete(row)
    return row.user_id == user_id and row.expires_at > now()


def channel_url(info: youtube_upload.ChannelInfo) -> str:
    return (
        f"https://www.youtube.com/{info.handle}"
        if info.handle
        else f"https://www.youtube.com/channel/{info.channel_id}"
    )


def _channel(db: DbSession, user_id: int, info: youtube_upload.ChannelInfo) -> Channel:
    """The `channels` row of the connected channel: the one added from its link ("Thêm kênh") when there is one."""
    found = db.scalar(select(Channel).where(Channel.platform == "youtube", Channel.external_id == info.channel_id))
    if found is None:
        handles = [handle.lower() for handle in (info.handle, info.channel_id) if handle]
        found = db.scalar(select(Channel).where(Channel.platform == "youtube", func.lower(Channel.handle).in_(handles)))
    if found is None:
        found = Channel(
            platform="youtube",
            handle=info.handle or info.channel_id,
            external_id=info.channel_id,
            name=info.title,
            url=channel_url(info),
            created_by_id=user_id,
        )
        db.add(found)
        db.flush()
    found.external_id = found.external_id or info.channel_id
    return found


def connect(
    db: DbSession, user_id: int, tokens: youtube_upload.Tokens, info: youtube_upload.ChannelInfo
) -> YouTubeConnection:
    """Save the connection Google just granted, on its channel (added when missing). Raises ConnectError when the
    channel is another member's, or Google sent no refresh token for a new connection."""
    connection = db.scalar(select(YouTubeConnection).where(YouTubeConnection.google_channel_id == info.channel_id))
    if connection is not None and connection.owner_id != user_id:
        raise ConnectError(f"Kênh YouTube {info.title} đã được một thành viên khác kết nối")
    if connection is None:
        if tokens.refresh_token is None:
            raise ConnectError("Google không cấp quyền dùng lâu dài, hãy bấm Kết nối YouTube lại")
        channel = _channel(db, user_id, info)
        connection = YouTubeConnection(owner_id=user_id, channel_id=channel.id, google_channel_id=info.channel_id)
        db.add(connection)
    connection.title = info.title
    _store(connection, tokens)
    db.flush()
    return connection


def _store(connection: YouTubeConnection, tokens: youtube_upload.Tokens) -> None:
    connection.access_token_encrypted = crypto.encrypt(tokens.access_token)
    if tokens.refresh_token is not None:
        connection.refresh_token_encrypted = crypto.encrypt(tokens.refresh_token)
    connection.access_expires_at = tokens.access_expires_at
    connection.scopes = tokens.scope or connection.scopes or ""
    connection.last_error = None


def of_channel(db: DbSession, channel_id: int | None) -> YouTubeConnection | None:
    if channel_id is None:
        return None
    return db.scalar(select(YouTubeConnection).where(YouTubeConnection.channel_id == channel_id))


def mine(db: DbSession, user_id: int) -> list[YouTubeConnection]:
    return list(
        db.scalars(
            select(YouTubeConnection).where(YouTubeConnection.owner_id == user_id).order_by(YouTubeConnection.title)
        )
    )


def needs_reconnect(connection: YouTubeConnection) -> bool:
    return connection.last_error is not None


def access_token(db: DbSession, connection: YouTubeConnection) -> str:
    """A usable access token, refreshed first when it ends within REFRESH_MARGIN (and committed at once). Raises
    youtube_upload.YouTubeUploadError."""
    if connection.last_error is not None:
        raise youtube_upload.YouTubeUploadError(RECONNECT, connection.last_error)
    try:
        if connection.access_expires_at - now() > REFRESH_MARGIN:
            return crypto.decrypt(connection.access_token_encrypted)
        refresh_token = crypto.decrypt(connection.refresh_token_encrypted)
    except crypto.CannotDecrypt:
        connection.last_error = "Không đọc được token YouTube đã lưu"
        db.commit()
        raise youtube_upload.YouTubeUploadError(RECONNECT) from None
    try:
        tokens = youtube_upload.refresh(refresh_token)
    except youtube_upload.YouTubeUploadError as err:
        if err.expired:
            connection.last_error = err.message
            db.commit()
            raise youtube_upload.YouTubeUploadError(RECONNECT, err.detail, err.status) from None
        raise
    _store(connection, tokens)
    db.commit()
    return tokens.access_token


def payload(connection: YouTubeConnection | None) -> dict | None:
    """What the web shows of a connection: no token, nor any part of one."""
    if connection is None:
        return None
    return {
        "id": connection.id,
        "channel_id": connection.channel_id,
        "title": connection.title,
        "owner_id": connection.owner_id,
        "last_error": connection.last_error,
        "needs_reconnect": needs_reconnect(connection),
        "connected_at": connection.created_at.isoformat() if connection.created_at else None,
    }
