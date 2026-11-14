"""'Quản lý kênh': the channels posts are recorded on, by platform. Facebook Pages are managed as before
(routes_fanpages.py); a TikTok channel is a TikTok account (`affiliate_accounts`, its owner the member who added it,
connected through TikTok's API from Cài đặt); a YouTube channel is a `channels` row. Both are added from their link
(docs/decisions/2026-11-14-posts-board.md)."""

import re
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from . import post_links, tiktok_connections
from .db import get_db
from .errors import ApiError
from .models import AffiliateAccount, Channel, Fanpage, Publication, Session, User
from .routes_videos import invalid
from .sessions import current_member

router = APIRouter(prefix="/api/channels")

YOUTUBE_PATH = re.compile(r"^/(?:(@[A-Za-z0-9._-]{3,30})|channel/(UC[A-Za-z0-9_-]{22}))/?")
TIKTOK_PATH = re.compile(r"^/@([A-Za-z0-9._]{2,24})/?$")
CHANNEL_LINK_HINT = "Link kênh phải có dạng https://www.tiktok.com/@ten-kenh hoặc https://www.youtube.com/@ten-kenh"


class ChannelBody(BaseModel):
    url: str


def parse_channel(raw: str) -> tuple[str, str, str | None, str]:
    """(platform, handle, YouTube channel id, link written one way) of a channel's link."""
    value = raw.strip()
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    try:
        parts = urlsplit(value)
    except ValueError:
        raise invalid(CHANNEL_LINK_HINT) from None
    host = (parts.hostname or "").lower()
    if host in post_links.TIKTOK_HOSTS and (match := TIKTOK_PATH.match(parts.path)):
        handle = match.group(1).lower()
        return "tiktok", handle, None, f"https://www.tiktok.com/@{handle}"
    if host in post_links.YOUTUBE_HOSTS and (match := YOUTUBE_PATH.match(parts.path)):
        handle, channel_id = match.groups()
        if handle:
            return "youtube", handle.lower(), None, f"https://www.youtube.com/{handle}"
        return "youtube", channel_id, channel_id, f"https://www.youtube.com/channel/{channel_id}"
    raise invalid(CHANNEL_LINK_HINT)


def _counts(db: DbSession, column) -> dict[int, int]:
    return dict(
        db.execute(
            select(column, func.count())
            .where(column.is_not(None), Publication.status != "pending_link")
            .group_by(column)
        ).all()
    )


@router.get("")
def list_channels(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """Every channel of the team by platform, for "Quản lý kênh" and the board's channel filter."""
    names = dict(db.execute(select(User.id, User.name)).all())
    tiktok_posts = _counts(db, Publication.affiliate_account_id)
    youtube_posts = _counts(db, Publication.channel_id)
    return {
        "facebook": [
            {"id": page.id, "name": page.name, "owner_id": page.owner_id}
            for page in db.scalars(select(Fanpage).where(Fanpage.active.is_(True)).order_by(Fanpage.name))
        ],
        "tiktok": [
            {
                "id": account.id,
                "name": account.name,
                "handle": handle,
                "url": account.profile_url,
                "owner_id": account.owner_id,
                "owner": names.get(account.owner_id),
                # Connected through TikTok's API ("Kết nối TikTok" in Cài đặt); the views come with part 4.
                "connected": tiktok_connections.of_account(db, account.id) is not None,
                "post_count": tiktok_posts.get(account.id, 0),
            }
            for account, handle in post_links.tiktok_accounts(db)
        ],
        "youtube": [
            {
                "id": channel.id,
                "name": channel.name,
                "handle": channel.handle,
                "url": channel.url,
                "created_by_id": channel.created_by_id,
                "created_by": channel.created_by.name,
                "post_count": youtube_posts.get(channel.id, 0),
            }
            for channel in db.scalars(select(Channel).where(Channel.platform == "youtube").order_by(Channel.name))
        ],
    }


@router.post("", status_code=201)
def add_channel(body: ChannelBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Thêm kênh" from its link: a TikTok channel becomes the member's own TikTok account, a YouTube one a channel."""
    platform, handle, channel_id, url = parse_channel(body.url)
    if platform == "tiktok":
        if any(known == handle for _, known in post_links.tiktok_accounts(db)):
            raise ApiError(409, "channel_exists", f"Kênh TikTok @{handle} đã có")
        account = AffiliateAccount(platform="tiktok", owner_id=me.user_id, name=f"@{handle}", profile_url=url)
        db.add(account)
        db.commit()
        return {"platform": "tiktok", "id": account.id, "name": account.name}
    channel = Channel(
        platform="youtube",
        handle=handle,
        external_id=channel_id,
        name=handle,
        url=url,
        created_by_id=me.user_id,
    )
    db.add(channel)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "channel_exists", f"Kênh YouTube {handle} đã có") from None
    return {"platform": "youtube", "id": channel.id, "name": channel.name}


@router.delete("/youtube/{channel_id}")
def remove_youtube(channel_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """A YouTube channel added by mistake, removed by whoever added it; its posts stay, without a channel. A TikTok
    account is removed where accounts are managed (Cài đặt)."""
    channel = db.get(Channel, channel_id)
    if channel is None:
        raise ApiError(404, "channel_not_found", "Không tìm thấy kênh")
    if channel.created_by_id != me.user_id:
        raise ApiError(403, "not_channel_author", "Chỉ người thêm kênh này mới xóa được")
    db.delete(channel)
    db.commit()
    return {"ok": True}
