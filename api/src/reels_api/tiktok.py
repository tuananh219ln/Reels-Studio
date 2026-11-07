"""TikTok's Login Kit (OAuth 2.0) and Content Posting API, called with a member's own TikTok connection: the
connection is made from the request that comes back from TikTok, posting only from the worker.

The app's identity (client key and secret) is the team's and comes from .env; the tokens are each member's own and
stay encrypted in the database (tiktok_connections). Tested only against the fake service (api/scripts/fake_services.py),
reached through TIKTOK_API_URL; the authorize page on www.tiktok.com is only ever built as a link, never called.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import config

REQUEST_TIMEOUT = 30
UPLOAD_TIMEOUT = 300
AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
# Must match the Redirect URI registered on the developer app exactly: https, no query string.
REDIRECT_URI = "https://reels.quangdang.xyz/api/tiktok/oauth/callback"
# Exactly the three scopes the developer app was approved for; no reading of videos or numbers.
SCOPES = ("user.info.basic", "video.upload", "video.publish")
# Only what user.info.basic reads: asking for one more field (username needs user.info.profile) fails the whole call
# with scope_not_authorized. The username comes from creator_info, which video.publish reads.
USER_FIELDS = "open_id,union_id,avatar_url,display_name"
MAX_TITLE = 2200
# FILE_UPLOAD: a file up to 64 MB goes in one chunk; a bigger one in 10 MB chunks, the last one taking the rest.
SINGLE_CHUNK_LIMIT = 64 * 1024 * 1024
CHUNK_SIZE = 10 * 1024 * 1024
# What TikTok reports while it still works on a post, and when it is done: a draft has reached the member's inbox, a
# direct post is published.
BUSY_STATUSES = {"PROCESSING_UPLOAD", "PROCESSING_DOWNLOAD"}
DONE_STATUSES = {"draft": {"SEND_TO_USER_INBOX", "PUBLISH_COMPLETE"}, "direct": {"PUBLISH_COMPLETE"}}

EXPIRED = "Kết nối TikTok đã hết hạn, hãy kết nối lại"
RATE_LIMITED = "TikTok đang giới hạn tốc độ, thử lại sau"
NOT_CONFIGURED = "Chưa cấu hình TIKTOK_CLIENT_KEY/TIKTOK_CLIENT_SECRET trong .env"
AUTH_CODES = {"access_token_invalid", "invalid_token", "token_expired", "scope_not_authorized", "invalid_grant"}
RATE_LIMIT_CODES = {"rate_limit_exceeded"}
MESSAGES = {
    "spam_risk_too_many_posts": "Tài khoản TikTok đã đăng đủ số bài cho phép trong ngày, hãy đăng lại vào ngày mai",
    "spam_risk_user_banned_from_posting": "TikTok đang chặn tài khoản này đăng bài",
    "unaudited_client_can_only_post_to_private_accounts": (
        "App chưa qua duyệt TikTok: đăng thẳng chỉ được lên tài khoản đang để riêng tư (private), ở mức Chỉ mình tôi."
        " Hãy chuyển tài khoản sang private hoặc dùng chế độ Nháp"
    ),
    "privacy_level_option_mismatch": "Mức riêng tư đã chọn không nằm trong các mức TikTok cho phép tài khoản này",
    "url_ownership_unverified": "TikTok chưa xác minh tên miền của video",
    "reached_active_user_cap": "App chưa qua duyệt TikTok đã đủ số người đăng trong 24 giờ, hãy thử lại sau",
    "invalid_publish_id": "TikTok không còn giữ bài đăng này",
}


class TikTokError(Exception):
    """`message` is shown to members, `detail` keeps TikTok's own answer for debugging. `code` is TikTok's error code
    when its answer had one; `expired` marks a connection that has to be made again."""

    def __init__(self, message: str, detail: str = "", code: str = "", status: int = 0):
        super().__init__(message)
        self.message = message
        self.detail = detail
        self.code = code
        self.status = status

    @property
    def expired(self) -> bool:
        return self.message == EXPIRED


@dataclass(frozen=True)
class Credentials:
    client_key: str
    client_secret: str = field(repr=False)


@dataclass(frozen=True)
class Tokens:
    open_id: str
    scope: str
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    access_expires_at: datetime
    refresh_expires_at: datetime


@dataclass(frozen=True)
class User:
    open_id: str
    username: str
    display_name: str
    avatar_url: str | None


@dataclass(frozen=True)
class CreatorInfo:
    username: str
    privacy_level_options: list[str]
    comment_disabled: bool
    duet_disabled: bool
    stitch_disabled: bool


@dataclass(frozen=True)
class Upload:
    publish_id: str
    upload_url: str


def credentials() -> Credentials:
    key, secret = config.tiktok_client_key(), config.tiktok_client_secret()
    if not key or not secret:
        raise TikTokError(NOT_CONFIGURED)
    return Credentials(key, secret)


def authorize_url(state: str) -> str:
    query = {
        "client_key": credentials().client_key,
        "scope": ",".join(SCOPES),
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(query)}"


def _error(status: int, body: str, code: str = "", message: str = "") -> TikTokError:
    detail = f"HTTP {status}: {body}"[:4000] if status else body[:4000]
    if code in AUTH_CODES or status == 401:
        return TikTokError(EXPIRED, detail, code, status)
    if code in RATE_LIMIT_CODES or status == 429:
        return TikTokError(RATE_LIMITED, detail, code, status)
    if code in MESSAGES:
        return TikTokError(MESSAGES[code], detail, code, status)
    if status >= 500:
        return TikTokError(f"TikTok đang lỗi (HTTP {status}), thử lại sau", detail, code, status)
    return TikTokError(f"TikTok báo lỗi: {message or code or 'không rõ'}", detail, code, status)


def _send(request: urllib.request.Request, timeout: float = REQUEST_TIMEOUT) -> dict:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as err:
        body = err.read(4000).decode("utf-8", "replace")
        code, message = _code_of(body)
        raise _error(err.code, body, code, message) from None
    # URLError, timeouts, connection resets and SSL errors are all OSError subclasses.
    except OSError as err:
        raise TikTokError("Không kết nối được TikTok, kiểm tra mạng rồi thử lại", str(err)) from None
    except ValueError as err:
        raise TikTokError("TikTok trả dữ liệu không đọc được, thử lại sau", str(err)) from None


def _code_of(body: str) -> tuple[str, str]:
    """TikTok's error code and message, from either answer shape: the OAuth one ({"error": "invalid_grant",
    "error_description"}) or the API one ({"error": {"code", "message"}})."""
    try:
        parsed = json.loads(body)
    except ValueError:
        return "", ""
    if not isinstance(parsed, dict):
        return "", ""
    error = parsed.get("error")
    if isinstance(error, dict):
        code = str(error.get("code") or "")
        return ("" if code == "ok" else code), str(error.get("message") or "")
    if isinstance(error, str) and error:
        return error, str(parsed.get("error_description") or "")
    return "", ""


def _api(path: str, access_token: str, body: dict | None = None, query: str = "") -> dict:
    """A Content Posting or user call; its `data`, or TikTokError when the answer carries an error."""
    url = f"{config.tiktok_api_url()}{path}{'?' + query if query else ''}"
    headers = {"Authorization": f"Bearer {access_token}"}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode()
        headers["Content-Type"] = "application/json; charset=UTF-8"
    answer = _send(
        urllib.request.Request(url, data=data, method="POST" if body is not None else "GET", headers=headers)
    )
    code, message = _code_of(json.dumps(answer))
    if code:
        raise _error(0, json.dumps(answer, ensure_ascii=False), code, message)
    result = answer.get("data")
    if not isinstance(result, dict):
        raise TikTokError("TikTok trả dữ liệu không đọc được, thử lại sau", json.dumps(answer, ensure_ascii=False))
    return result


def _token_call(form: dict) -> Tokens:
    creds = credentials()
    payload = urllib.parse.urlencode({"client_key": creds.client_key, "client_secret": creds.client_secret, **form})
    request = urllib.request.Request(
        f"{config.tiktok_api_url()}/v2/oauth/token/",
        data=payload.encode(),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", "Cache-Control": "no-cache"},
    )
    answer = _send(request)
    code, message = _code_of(json.dumps(answer))
    if code:
        # Nothing of the answer goes in the detail but the error: it never holds a token then, but stay safe.
        raise _error(0, json.dumps({"error": code, "error_description": message}, ensure_ascii=False), code, message)
    try:
        moment = datetime.now(UTC)
        return Tokens(
            open_id=str(answer["open_id"]),
            scope=str(answer.get("scope") or ""),
            access_token=str(answer["access_token"]),
            refresh_token=str(answer["refresh_token"]),
            access_expires_at=moment + timedelta(seconds=int(answer["expires_in"])),
            refresh_expires_at=moment + timedelta(seconds=int(answer["refresh_expires_in"])),
        )
    except (KeyError, TypeError, ValueError):
        raise TikTokError("TikTok trả dữ liệu không đọc được, thử lại sau", "token answer without its fields") from None


def exchange_code(code: str) -> Tokens:
    try:
        return _token_call({"code": code, "grant_type": "authorization_code", "redirect_uri": REDIRECT_URI})
    except TikTokError as err:
        if err.code == "invalid_grant":
            raise TikTokError("Mã ủy quyền TikTok không hợp lệ hoặc đã hết hạn, hãy kết nối lại", err.detail) from None
        raise


def refresh(refresh_token: str) -> Tokens:
    """TikTok answers with a NEW refresh token every time: both tokens must be saved over the old ones."""
    return _token_call({"grant_type": "refresh_token", "refresh_token": refresh_token})


def revoke(access_token: str) -> None:
    creds = credentials()
    payload = urllib.parse.urlencode(
        {"client_key": creds.client_key, "client_secret": creds.client_secret, "token": access_token}
    )
    request = urllib.request.Request(
        f"{config.tiktok_api_url()}/v2/oauth/revoke/",
        data=payload.encode(),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    _send(request)


def user_info(access_token: str) -> User:
    """The member's TikTok account: open_id, name and avatar from user info, the username from creator_info."""
    data = _api("/v2/user/info/", access_token, query=urllib.parse.urlencode({"fields": USER_FIELDS}))
    user = data.get("user") if isinstance(data.get("user"), dict) else {}
    open_id = str(user.get("open_id") or "")
    if not open_id:
        raise TikTokError("TikTok không trả thông tin tài khoản, thử lại sau", json.dumps(data, ensure_ascii=False))
    username = creator_info(access_token).username
    return User(
        open_id=open_id,
        username=username,
        display_name=str(user.get("display_name") or username or "TikTok")[:200],
        avatar_url=user.get("avatar_url") or None,
    )


def creator_info(access_token: str) -> CreatorInfo:
    data = _api("/v2/post/publish/creator_info/query/", access_token, body={})
    options = data.get("privacy_level_options")
    return CreatorInfo(
        username=str(data.get("creator_username") or "")[:100],
        privacy_level_options=[str(option) for option in options] if isinstance(options, list) else [],
        comment_disabled=bool(data.get("comment_disabled")),
        duet_disabled=bool(data.get("duet_disabled")),
        stitch_disabled=bool(data.get("stitch_disabled")),
    )


def chunk_plan(size: int) -> tuple[int, int]:
    """(chunk_size, total_chunk_count) for a file of `size` bytes."""
    if size <= SINGLE_CHUNK_LIMIT:
        return size, 1
    return CHUNK_SIZE, size // CHUNK_SIZE


def _source(size: int, chunk_size: int, chunks: int) -> dict:
    return {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk_size, "total_chunk_count": chunks}


def _upload(data: dict) -> Upload:
    publish_id, upload_url = data.get("publish_id"), data.get("upload_url")
    if not publish_id or not upload_url:
        raise TikTokError("TikTok không trả chỗ tải video lên, thử lại sau", json.dumps(data, ensure_ascii=False))
    return Upload(str(publish_id), str(upload_url))


def init_inbox(access_token: str, size: int, chunk_size: int, chunks: int) -> Upload:
    """A draft: the video goes to the member's TikTok inbox, where they finish the post (caption, cart, AI label)."""
    body = {"source_info": _source(size, chunk_size, chunks)}
    return _upload(_api("/v2/post/publish/inbox/video/init/", access_token, body=body))


def init_direct(access_token: str, post_info: dict, size: int, chunk_size: int, chunks: int) -> Upload:
    body = {"post_info": post_info, "source_info": _source(size, chunk_size, chunks)}
    return _upload(_api("/v2/post/publish/video/init/", access_token, body=body))


def upload_chunks(upload_url: str, path: Path, chunk_size: int, chunks: int) -> None:
    """PUT the file to `upload_url`, chunk by chunk; the last chunk takes whatever is left."""
    size = path.stat().st_size
    with path.open("rb") as file:
        for index in range(chunks):
            start = index * chunk_size
            end = size - 1 if index == chunks - 1 else start + chunk_size - 1
            file.seek(start)
            data = file.read(end - start + 1)
            request = urllib.request.Request(
                upload_url,
                data=data,
                method="PUT",
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Length": str(len(data)),
                    "Content-Range": f"bytes {start}-{end}/{size}",
                },
            )
            _send(request, UPLOAD_TIMEOUT)


def publish_status(access_token: str, publish_id: str) -> dict:
    """{"status", "fail_reason", ...} as TikTok reports the post."""
    return _api("/v2/post/publish/status/fetch/", access_token, body={"publish_id": publish_id})


def post_title(caption: str, hashtags: list[str]) -> str:
    """A direct post's caption: the video's caption, then its hashtags, cut at TikTok's limit."""
    tags = " ".join(tag for tag in hashtags if tag)
    return " ".join(part for part in (caption.strip(), tags) if part)[:MAX_TITLE]
