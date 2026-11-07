"""YouTube Shorts and Instagram Reels: the app has no connection to either, so a member posts the video's MP4 in the
platform's own app and records the post here with its link, as "Đã đăng tay" does for TikTok. Any video may be
posted there, whatever platform it was made for (docs/decisions.md, 2026-11-08). The numbers stay on the platform."""

import re
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from .db import get_db
from .errors import ApiError
from .models import Publication, Session, Video
from .routes_videos import invalid
from .sessions import current_member
from .videos import MANUAL_PLATFORMS, video_payload

router = APIRouter(prefix="/api/manual-posts")

MAX_URL_LENGTH = 500
YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{6,20}$")
INSTAGRAM_PATH = re.compile(r"^/(?:[A-Za-z0-9._]+/)?(?:reel|reels|p)/[A-Za-z0-9_-]+/?$")


class ManualPostBody(BaseModel):
    platform: str
    url: str


def _youtube(parts) -> bool:
    host = (parts.hostname or "").lower()
    if host == "youtu.be":
        return bool(YOUTUBE_ID.match(parts.path.strip("/")))
    if host not in ("youtube.com", "www.youtube.com", "m.youtube.com"):
        return False
    if parts.path.startswith("/shorts/"):
        return bool(YOUTUBE_ID.match(parts.path.removeprefix("/shorts/").strip("/")))
    if parts.path == "/watch":
        return bool(YOUTUBE_ID.match((parse_qs(parts.query).get("v") or [""])[0]))
    return False


def _instagram(parts) -> bool:
    host = (parts.hostname or "").lower()
    return host in ("instagram.com", "www.instagram.com") and bool(INSTAGRAM_PATH.match(parts.path))


CHECKS = {
    "youtube": (_youtube, "Link YouTube phải có dạng https://youtube.com/shorts/… hoặc https://youtu.be/…"),
    "instagram": (_instagram, "Link Instagram phải có dạng https://www.instagram.com/reel/…"),
}


def post_url(platform: str, value: str) -> str:
    value = value.strip()
    check, message = CHECKS[platform]
    try:
        parts = urlsplit(value)
    except ValueError:
        raise invalid(message) from None
    if parts.scheme != "https" or len(value) > MAX_URL_LENGTH or not check(parts):
        raise invalid(message)
    return value


@router.post("/videos/{video_id}", status_code=201)
def record_post(
    video_id: int, body: ManualPostBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Đã đăng tay" on YouTube Shorts or Instagram Reels: the post a member made there from this video's MP4."""
    video = db.get(Video, video_id)
    if video is None:
        raise ApiError(404, "video_not_found", "Không tìm thấy video")
    if body.platform not in MANUAL_PLATFORMS:
        raise invalid("Nền tảng không hợp lệ")
    if not video.mp4_key:
        raise invalid("Video chưa render MP4 để đăng")
    url = post_url(body.platform, body.url)
    # No remote_id: the readings of numbers and comments are Facebook's and leave these posts alone.
    db.add(
        Publication(
            video_id=video.id,
            platform=body.platform,
            status="published",
            published_at=datetime.now(UTC),
            remote_mp4_key=video.mp4_key,
            created_by_id=me.user_id,
            post_url=url,
        )
    )
    db.commit()
    return video_payload(db, video)


@router.delete("/{post_id}")
def remove_post(post_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """A post recorded by mistake, removed by the member who recorded it. The post on the platform is not touched."""
    post = db.get(Publication, post_id)
    if post is None or post.platform not in MANUAL_PLATFORMS or post.video_id is None:
        raise ApiError(404, "post_not_found", "Không tìm thấy bài đăng")
    if post.created_by_id != me.user_id:
        raise ApiError(403, "not_post_author", "Chỉ người ghi bài này mới xóa được")
    video = db.get(Video, post.video_id)
    db.delete(post)
    db.commit()
    return video_payload(db, video)
