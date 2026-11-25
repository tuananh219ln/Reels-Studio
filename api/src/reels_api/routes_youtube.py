"""YouTube through its API, private only (docs/decisions/2026-11-17-youtube-private-upload.md): a member connects their
own YouTube channel (Google's OAuth, youtube_connections.py) on "Quản lý kênh", then "Tải lên YouTube" on a video sends
its MP4 there as a private video. The member makes it public, or schedules it, in YouTube Studio at the time they
planned; the app keeps that time as a reminder and sees the Short once it is public."""

import html
import logging
from datetime import datetime, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from . import crypto, hashtags, youtube_connections, youtube_upload
from .db import get_db
from .errors import ApiError
from .models import Channel, Job, Publication, Session, YouTubeConnection
from .routes_videos import invalid
from .sessions import current_member, current_session, now
from .videos import ensure_unlocked, lock_video, split_scenes, title_of, video_payload

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/youtube")

CHANNELS_PAGE = "/settings/affiliate-accounts"
# A planned time this far back is taken as a mistake: the reminder would be overdue already.
PLANNED_SLACK = timedelta(minutes=5)


def _back(outcome: str, message: str = "") -> HTMLResponse:
    """Back to "Quản lý kênh", which shows how the connection went. A page that sends the browser on by itself, never
    a 3xx: the web's /api proxy in production follows a redirect itself (see routes_tiktok._back)."""
    query = {"youtube": outcome, **({"message": message} if message else {})}
    target = html.escape(f"{CHANNELS_PAGE}?{urlencode(query)}")
    page = (
        '<!doctype html><html lang="vi"><head><meta charset="utf-8">'
        f'<meta http-equiv="refresh" content="0;url={target}"><title>Reels Studio</title></head>'
        f'<body><a href="{target}">Quay lại Quản lý kênh</a></body></html>'
    )
    # The address still holds Google's code: no cache, and no referrer for the next page.
    return HTMLResponse(page, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@router.get("/oauth/start")
def oauth_start(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Kết nối YouTube": Google's consent page with a one-use state bound to this member. The web sends the browser
    there itself."""
    try:
        state = youtube_connections.new_state(db, me.user_id)
        url = youtube_upload.authorize_url(state)
    except youtube_upload.YouTubeUploadError as err:
        db.rollback()
        raise ApiError(409, "youtube_not_configured", err.message) from None
    db.commit()
    return {"url": url}


@router.get("/oauth/callback")
def oauth_callback(
    request: Request,
    response: Response,
    code: str = "",
    state: str = "",
    error: str = "",
    db: DbSession = Depends(get_db),
) -> HTMLResponse:
    """Google sends the member back here. The session cookie comes along (same site); without it nothing is saved."""
    try:
        me = current_member(current_session(request, response, db))
    except ApiError:
        return _back("error", "Phiên đăng nhập đã hết, hãy đăng nhập lại rồi bấm Kết nối YouTube")
    if not youtube_connections.take_state(db, state, me.user_id):
        db.commit()
        return _back("error", "Lần kết nối YouTube này đã hết hạn hoặc không hợp lệ, hãy bấm Kết nối YouTube lại")
    db.commit()
    if error:
        log.info("YouTube authorization refused for user %s: %s", me.user_id, error)
        return _back("error", "Bạn chưa cho phép Reels Studio dùng kênh YouTube, hãy thử lại")
    try:
        tokens = youtube_upload.exchange_code(code)
        info = youtube_upload.my_channel(tokens.access_token)
        youtube_connections.connect(db, me.user_id, tokens, info)
        db.commit()
    except youtube_upload.YouTubeUploadError as err:
        db.rollback()
        log.warning("YouTube connection of user %s failed: %s %s", me.user_id, err.message, err.detail)
        return _back("error", err.message)
    except youtube_connections.ConnectError as err:
        db.rollback()
        return _back("error", err.message)
    except IntegrityError:
        db.rollback()
        return _back("error", "Kênh YouTube này vừa được kết nối ở nơi khác, hãy tải lại trang")
    return _back("connected")


@router.get("/connections")
def my_connections(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> list[dict]:
    """The member's own connected channels: the ones "Tải lên YouTube" and a Page's YouTube select offer."""
    return [youtube_connections.payload(connection) for connection in youtube_connections.mine(db, me.user_id)]


@router.delete("/connections/{connection_id}")
def disconnect(connection_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Ngắt kết nối": the app forgets the tokens. The channel and its posts stay."""
    connection = db.get(YouTubeConnection, connection_id)
    if connection is None or connection.owner_id != me.user_id:
        raise ApiError(404, "connection_not_found", "Không tìm thấy kết nối YouTube")
    try:
        youtube_upload.revoke(crypto.decrypt(connection.refresh_token_encrypted))
    except (youtube_upload.YouTubeUploadError, crypto.CannotDecrypt) as err:
        # Revoking on Google's side is a courtesy: the app forgets the tokens whatever Google answers.
        log.info("YouTube connection %s not revoked on Google: %s", connection.id, err)
    db.delete(connection)
    db.commit()
    return {"ok": True}


class UploadBody(BaseModel):
    channel_id: int
    title: str
    # When the member means to make it public in YouTube Studio: a reminder only, never sent to YouTube.
    planned_at: datetime | None = None


@router.post("/videos/{video_id}/upload", status_code=201)
def upload(
    video_id: int, body: UploadBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Tải lên YouTube": the worker sends the MP4 now, private, to one of the member's own connected channels."""
    video = lock_video(db, video_id)
    if not video.mp4_key:
        raise invalid("Video chưa render MP4 để đăng")
    channel = db.get(Channel, body.channel_id)
    connection = youtube_connections.of_channel(db, body.channel_id)
    if channel is None or connection is None or connection.owner_id != me.user_id:
        raise invalid("Hãy chọn một kênh YouTube bạn đã kết nối")
    if youtube_connections.needs_reconnect(connection):
        raise invalid(f"Kết nối YouTube của “{channel.name}” đã hết hạn, hãy kết nối lại ở Quản lý kênh")
    title = youtube_upload.clean_title(body.title)
    if not title:
        raise invalid("Hãy nhập tiêu đề video YouTube")
    planned = body.planned_at
    if planned is not None and planned.tzinfo is None:
        raise invalid("Giờ công khai phải có múi giờ")
    if planned is not None and planned < now() - PLANNED_SLACK:
        raise invalid("Giờ dự định công khai đã qua, hãy chọn giờ khác")
    ensure_unlocked(db, video)
    same = db.scalar(
        select(Publication.id).where(
            Publication.video_id == video.id,
            Publication.platform == "youtube",
            Publication.channel_id == channel.id,
            Publication.remote_mp4_key == video.mp4_key,
            Publication.status.in_(("private", "scheduled", "published")),
        )
    )
    if same is not None:
        raise ApiError(409, "youtube_already_uploaded", f"MP4 này đã tải lên kênh {channel.name}")
    waiting = db.scalar(
        select(Publication).where(
            Publication.video_id == video.id, Publication.platform == "youtube", Publication.status == "pending"
        )
    )
    if waiting is not None:
        if waiting.upload_url is not None:
            raise ApiError(
                409,
                "youtube_post_pending",
                "Lần tải lên YouTube trước chưa xong, hãy bấm Thử lại ở job lỗi thay vì tải lần nữa",
            )
        # Never reached YouTube (its job failed before the upload started): replaced by this one.
        waiting.status, waiting.closed_at, waiting.closed_by_id = "cancelled", now(), me.user_id
        db.flush()
    title_scene, _ = split_scenes(db, video)
    post = Publication(
        video_id=video.id,
        platform="youtube",
        status="pending",
        created_by_id=me.user_id,
        channel_id=channel.id,
        scheduled_at=planned,
        remote_mp4_key=video.mp4_key,
        # The title and description as sent, so "Thử lại" sends the same.
        caption=title or title_of(video, title_scene),
        post_text=hashtags.post_text(video.caption, video.hashtags),
    )
    db.add(post)
    try:
        db.flush()
        db.add(
            Job(
                video_id=video.id,
                kind="youtube_publish",
                status="queued",
                created_by_id=me.user_id,
                publication_id=post.id,
            )
        )
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "youtube_post_pending", "Video đang có việc chạy, hãy đợi xong") from None
    db.commit()
    return video_payload(db, video)
