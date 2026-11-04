"""TikTok, posted by hand: the app makes the TikTok version of a video and its MP4, a member posts it in TikTok's app
(where the AI label and TikTok Shop's cart are set) and records the post here with its link. Nothing calls TikTok:
posting through TikTok's API waits for issue #46."""

import re
from datetime import UTC, datetime
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from .db import get_db
from .errors import ApiError
from .models import AffiliateAccount, Publication, Session, Video
from .routes_videos import invalid
from .sessions import current_member
from .videos import video_payload

router = APIRouter(prefix="/api/tiktok")

MAX_URL_LENGTH = 500
VIDEO_PATH = re.compile(r"^/@[^/]+/video/\d+/?$")


class PostBody(BaseModel):
    account_id: int
    url: str


def _post_url(value: str) -> str:
    value = value.strip()
    try:
        parts = urlsplit(value)
    except ValueError:
        parts = None
    host = (parts.hostname or "") if parts else ""
    full = host in ("tiktok.com", "www.tiktok.com", "m.tiktok.com") and VIDEO_PATH.match(parts.path)
    short = host in ("vt.tiktok.com", "vm.tiktok.com") and len(parts.path.strip("/")) > 0
    if not parts or parts.scheme != "https" or not (full or short) or len(value) > MAX_URL_LENGTH:
        raise invalid(
            "Link bài TikTok phải có dạng https://www.tiktok.com/@ten-kenh/video/123… hoặc https://vt.tiktok.com/…"
        )
    return value


@router.post("/videos/{video_id}/posts", status_code=201)
def record_post(
    video_id: int, body: PostBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Đã đăng tay": the post a member made in TikTok's app, on one of their own TikTok accounts."""
    video = db.get(Video, video_id)
    if video is None:
        raise ApiError(404, "video_not_found", "Không tìm thấy video")
    if video.platform != "tiktok":
        raise invalid("Chỉ ghi bài TikTok cho bản TikTok của video")
    if not video.mp4_key:
        raise invalid("Video chưa render MP4 để đăng")
    account = db.get(AffiliateAccount, body.account_id)
    if account is None or account.owner_id != me.user_id or account.platform != "tiktok":
        raise invalid("Hãy chọn một tài khoản TikTok của bạn")
    if not account.active:
        raise invalid(f"Tài khoản “{account.name}” đang ngừng dùng")
    url = _post_url(body.url)
    # No remote_id: the reads of numbers and comments are Facebook's, and leave a TikTok post alone.
    db.add(
        Publication(
            video_id=video.id,
            platform="tiktok",
            status="published",
            published_at=datetime.now(UTC),
            remote_mp4_key=video.mp4_key,
            created_by_id=me.user_id,
            affiliate_account_id=account.id,
            post_url=url,
        )
    )
    db.commit()
    return video_payload(db, video)


@router.delete("/posts/{post_id}")
def remove_post(post_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """A TikTok post recorded by mistake, removed by the member who recorded it. The post on TikTok is not touched."""
    post = db.get(Publication, post_id)
    if post is None or post.platform != "tiktok":
        raise ApiError(404, "post_not_found", "Không tìm thấy bài đăng")
    if post.created_by_id != me.user_id:
        raise ApiError(403, "not_post_author", "Chỉ người ghi bài này mới xóa được")
    video = db.get(Video, post.video_id)
    db.delete(post)
    db.commit()
    return video_payload(db, video)
