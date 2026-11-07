"""TikTok: the app makes the TikTok version of a video and its MP4, then a member either posts it in TikTok's app (where
the AI label and TikTok Shop's cart are set) and records the post here with its link, or sends it through TikTok's
Content Posting API with their own TikTok connection (issue #46): as a draft to their TikTok inbox, or posted directly.

The connection is the member's own (TikTok's Login Kit, tiktok_connections.py): each member connects and posts only
their own TikTok accounts. TikTok's API gives no link to the post, so a member adds it afterwards, as for one posted
by hand."""

import html
import logging
import re
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from . import crypto, tiktok, tiktok_connections
from .db import get_db
from .errors import ApiError
from .models import AffiliateAccount, Job, Publication, Session, TikTokConnection, Video
from .routes_videos import invalid
from .sessions import current_member, current_session, now
from .videos import ensure_unlocked, lock_video, video_payload

log = logging.getLogger(__name__)

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


# --- Connecting a member's TikTok account (Login Kit) ---

SETTINGS_PAGE = "/settings/affiliate-accounts"


def _back(outcome: str, message: str = "") -> HTMLResponse:
    """Back to "Tài khoản affiliate", which shows how the connection went. A page that sends the browser on by itself,
    never a 3xx: the web's /api proxy in production (Cloudflare Workers) follows a redirect itself, on the api's host,
    instead of handing it to the browser."""
    query = {"tiktok": outcome, **({"message": message} if message else {})}
    target = html.escape(f"{SETTINGS_PAGE}?{urlencode(query)}")
    page = (
        '<!doctype html><html lang="vi"><head><meta charset="utf-8">'
        f'<meta http-equiv="refresh" content="0;url={target}"><title>Reels Studio</title></head>'
        f'<body><a href="{target}">Quay lại Tài khoản affiliate</a></body></html>'
    )
    # The address still holds TikTok's code: no cache, and no referrer for the next page.
    return HTMLResponse(page, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@router.get("/oauth/start")
def oauth_start(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Kết nối TikTok": TikTok's authorize page with a one-use state bound to this member. The web sends the browser
    there itself (see _back for why this is not a redirect)."""
    try:
        state = tiktok_connections.new_state(db, me.user_id)
        url = tiktok.authorize_url(state)
    except tiktok.TikTokError as err:
        db.rollback()
        raise ApiError(409, "tiktok_not_configured", err.message) from None
    db.commit()
    return {"url": url}


@router.get("/oauth/callback")
def oauth_callback(
    request: Request,
    response: Response,
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = "",
    db: DbSession = Depends(get_db),
) -> HTMLResponse:
    """TikTok sends the member back here. The session cookie comes along (same site); without it nothing is saved."""
    try:
        me = current_member(current_session(request, response, db))
    except ApiError:
        return _back("error", "Phiên đăng nhập đã hết, hãy đăng nhập lại rồi bấm Kết nối TikTok")
    if not tiktok_connections.take_state(db, state, me.user_id):
        db.commit()
        return _back("error", "Lần kết nối TikTok này đã hết hạn hoặc không hợp lệ, hãy bấm Kết nối TikTok lại")
    db.commit()
    if error:
        log.info("TikTok authorization refused for user %s: %s %s", me.user_id, error, error_description)
        return _back("error", "Bạn chưa cho phép Reels Studio dùng tài khoản TikTok, hãy thử lại")
    try:
        tokens = tiktok.exchange_code(code)
        user = tiktok.user_info(tokens.access_token)
        tiktok_connections.connect(db, me.user_id, tokens, user)
        db.commit()
    except tiktok.TikTokError as err:
        db.rollback()
        log.warning("TikTok connection of user %s failed: %s %s", me.user_id, err.message, err.detail)
        return _back("error", err.message)
    except tiktok_connections.ConnectError as err:
        db.rollback()
        return _back("error", err.message)
    except IntegrityError:
        db.rollback()
        return _back("error", "Tài khoản TikTok này vừa được kết nối ở nơi khác, hãy tải lại trang")
    return _back("connected")


@router.delete("/connections/{connection_id}")
def disconnect(connection_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Ngắt kết nối": the app forgets the tokens. The TikTok account, as an affiliate account, and its posts stay."""
    connection = db.get(TikTokConnection, connection_id)
    if connection is None or connection.owner_id != me.user_id:
        raise ApiError(404, "connection_not_found", "Không tìm thấy kết nối TikTok")
    try:
        tiktok.revoke(crypto.decrypt(connection.access_token_encrypted))
    except (tiktok.TikTokError, crypto.CannotDecrypt) as err:
        # Revoking on TikTok's side is a courtesy: the app forgets the tokens whatever TikTok answers.
        log.info("TikTok connection %s not revoked on TikTok: %s", connection.id, err)
    db.delete(connection)
    db.commit()
    return {"ok": True}


# --- Posting through TikTok's Content Posting API ---

# The privacy levels TikTok may offer; which ones an account gets is TikTok's answer, read when the job posts.
PRIVACY_LEVELS = ("PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "SELF_ONLY")


class PublishBody(BaseModel):
    account_id: int
    mode: Literal["draft", "direct"] = "draft"
    privacy_level: str | None = None


class UrlBody(BaseModel):
    url: str


@router.post("/videos/{video_id}/publish", status_code=201)
def publish(
    video_id: int, body: PublishBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Đăng lên TikTok": the worker sends the MP4 now, with the member's own connection: a draft to their TikTok
    inbox (the default), or posted directly."""
    video = lock_video(db, video_id)
    if video.platform != "tiktok":
        raise invalid("Chỉ đăng lên TikTok bản TikTok của video")
    if not video.mp4_key:
        raise invalid("Video chưa render MP4 để đăng")
    account = db.get(AffiliateAccount, body.account_id)
    if account is None or account.owner_id != me.user_id or account.platform != "tiktok":
        raise invalid("Hãy chọn một tài khoản TikTok của bạn")
    if not account.active:
        raise invalid(f"Tài khoản “{account.name}” đang ngừng dùng")
    connection = tiktok_connections.of_account(db, account.id)
    if connection is None or connection.owner_id != me.user_id:
        raise invalid(
            f"Tài khoản “{account.name}” chưa kết nối TikTok, hãy bấm Kết nối TikTok trong Tài khoản affiliate"
        )
    if tiktok_connections.needs_reconnect(connection):
        raise invalid(f"Kết nối TikTok của “{account.name}” đã hết hạn, hãy kết nối lại trong Tài khoản affiliate")
    privacy = None
    if body.mode == "direct":
        privacy = body.privacy_level or "SELF_ONLY"
        if privacy not in PRIVACY_LEVELS:
            raise invalid("Mức riêng tư không hợp lệ")
    ensure_unlocked(db, video)
    waiting = db.scalar(
        select(Publication).where(
            Publication.video_id == video.id, Publication.platform == "tiktok", Publication.status == "pending"
        )
    )
    if waiting is not None:
        if waiting.remote_id is not None:
            raise ApiError(
                409,
                "tiktok_post_pending",
                "Bài TikTok trước đã gửi tới TikTok nhưng chưa xong, hãy bấm Thử lại ở job lỗi thay vì đăng lần nữa",
            )
        # Never reached TikTok (its job failed before the upload): replaced by this one.
        waiting.status, waiting.closed_at, waiting.closed_by_id = "cancelled", now(), me.user_id
        db.flush()
    post = Publication(
        video_id=video.id,
        platform="tiktok",
        status="pending",
        created_by_id=me.user_id,
        affiliate_account_id=account.id,
        publish_mode=body.mode,
        privacy_level=privacy,
    )
    db.add(post)
    try:
        db.flush()
        db.add(
            Job(
                video_id=video.id,
                kind="tiktok_publish",
                status="queued",
                created_by_id=me.user_id,
                publication_id=post.id,
            )
        )
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "tiktok_post_pending", "Video đang có một bài TikTok đang đăng, hãy đợi xong") from None
    db.commit()
    return video_payload(db, video)


@router.post("/posts/{post_id}/url")
def add_post_url(
    post_id: int, body: UrlBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """The link of a post sent through TikTok's API, which TikTok does not give back: added by the member who sent it,
    once it is on TikTok."""
    post = db.get(Publication, post_id, with_for_update=True)
    if post is None or post.platform != "tiktok" or post.video_id is None:
        raise ApiError(404, "post_not_found", "Không tìm thấy bài đăng")
    if post.created_by_id != me.user_id:
        raise ApiError(403, "not_post_author", "Chỉ người đăng bài này mới gắn được link")
    if post.post_url:
        raise ApiError(409, "post_has_url", "Bài này đã có link")
    if post.status != "published":
        raise ApiError(409, "post_not_live", "Bài chưa lên TikTok, hãy đợi đăng xong rồi gắn link")
    post.post_url = _post_url(body.url)
    db.commit()
    return video_payload(db, db.get(Video, post.video_id))
