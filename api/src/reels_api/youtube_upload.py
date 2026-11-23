"""Google's OAuth and YouTube's resumable upload, called with a member's own YouTube connection: the connection is made
from the request that comes back from Google, uploading only from the worker.

Every upload is private. A project Google has not audited cannot post publicly through the API, so the member makes
the Short public (or schedules it) in YouTube Studio themselves; the app only keeps the time they planned
(docs/decisions/2026-11-17-youtube-private-upload.md).

The client id and secret are the team's and come from .env; the tokens are each member's own and stay encrypted in the
database (youtube_connections). Tested only against the fake service (api/scripts/fake_services.py), reached through
GOOGLE_OAUTH_URL, YOUTUBE_API_URL and YOUTUBE_UPLOAD_URL; Google's consent page is only ever built as a link.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

import httpx

from . import config

TIMEOUT = 30.0
UPLOAD_TIMEOUT = 600.0
AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
# Must match an Authorized redirect URI of the Google Cloud OAuth client exactly.
REDIRECT_URI = "https://reels.quangdang.xyz/api/youtube/oauth/callback"
# Uploading, and reading which channel was connected (channels.list mine=true).
SCOPES = ("https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly")
MAX_TITLE = 100
MAX_DESCRIPTION = 5000

EXPIRED = "Kết nối YouTube đã hết hạn, hãy kết nối lại"
NOT_CONFIGURED = "Chưa cấu hình GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET trong .env"
QUOTA = "YouTube hết quota tải lên hôm nay, hãy thử lại vào ngày mai"
MESSAGES = {
    "quotaExceeded": QUOTA,
    "dailyLimitExceeded": QUOTA,
    "uploadLimitExceeded": "Kênh YouTube đã tải lên đủ số video cho phép hôm nay, hãy thử lại vào ngày mai",
    "rateLimitExceeded": "YouTube đang giới hạn tốc độ, thử lại sau",
    "youtubeSignupRequired": "Tài khoản Google này chưa có kênh YouTube",
    "invalidTitle": "YouTube không nhận tiêu đề này",
    "invalidDescription": "YouTube không nhận mô tả này",
    "forbidden": "YouTube không cho kênh này tải video lên",
}


class YouTubeUploadError(Exception):
    """`message` is shown to members, `detail` keeps Google's own answer for debugging; `expired` marks a connection
    that has to be made again."""

    def __init__(self, message: str, detail: str = "", status: int = 0):
        super().__init__(message)
        self.message = message
        self.detail = detail
        self.status = status

    @property
    def expired(self) -> bool:
        return self.message == EXPIRED


@dataclass(frozen=True)
class Tokens:
    scope: str
    access_token: str = field(repr=False)
    # Google sends a refresh token only with the first grant (prompt=consent asks for it every time); a refresh keeps
    # the old one, so None here means "unchanged".
    refresh_token: str | None = field(repr=False)
    access_expires_at: datetime


@dataclass(frozen=True)
class ChannelInfo:
    channel_id: str
    title: str
    # "@handle" when the channel has one, else "".
    handle: str


def _credentials() -> tuple[str, str]:
    client_id, secret = config.google_client_id(), config.google_client_secret()
    if not client_id or not secret:
        raise YouTubeUploadError(NOT_CONFIGURED)
    return client_id, secret


def authorize_url(state: str) -> str:
    client_id, _ = _credentials()
    query = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        # Always the consent screen, so Google sends a refresh token even to a member connecting again.
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(query)}"


def _reason(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    if not isinstance(body, dict):
        return ""
    error = body.get("error")
    if isinstance(error, str):
        return error  # the OAuth answer: {"error": "invalid_grant", ...}
    try:
        return str(error["errors"][0]["reason"])
    except (KeyError, IndexError, TypeError):
        return ""


def _error(response: httpx.Response) -> YouTubeUploadError:
    reason = _reason(response)
    detail = f"HTTP {response.status_code}: {response.text[:3000]}"
    if response.status_code == 401 or reason in ("invalid_grant", "authError", "unauthorized_client"):
        if reason == "youtubeSignupRequired":
            return YouTubeUploadError(MESSAGES[reason], detail, response.status_code)
        return YouTubeUploadError(EXPIRED, detail, response.status_code)
    if reason in MESSAGES:
        return YouTubeUploadError(MESSAGES[reason], detail, response.status_code)
    if response.status_code >= 500:
        return YouTubeUploadError(
            f"YouTube đang lỗi (HTTP {response.status_code}), thử lại sau", detail, response.status_code
        )
    return YouTubeUploadError(f"YouTube báo lỗi: {reason or response.status_code}", detail, response.status_code)


def _call(method: str, url: str, timeout: float = TIMEOUT, **kwargs) -> httpx.Response:
    try:
        return httpx.request(method, url, timeout=timeout, **kwargs)
    except httpx.HTTPError as err:
        raise YouTubeUploadError(
            "Không kết nối được YouTube, kiểm tra mạng rồi thử lại", err.__class__.__name__
        ) from None


def _tokens(form: dict) -> Tokens:
    client_id, secret = _credentials()
    response = _call(
        "POST", f"{config.google_oauth_url()}/token", data={"client_id": client_id, "client_secret": secret, **form}
    )
    if response.status_code != 200:
        # Nothing of the answer but its error goes in the detail: it never holds a token then, but stay safe.
        reason = _reason(response)
        if reason == "invalid_grant":
            raise YouTubeUploadError(EXPIRED, f"HTTP {response.status_code}: {reason}", response.status_code)
        raise YouTubeUploadError(
            f"Google từ chối kết nối ({reason or response.status_code})", f"HTTP {response.status_code}: {reason}"
        )
    try:
        answer = response.json()
        return Tokens(
            scope=str(answer.get("scope") or ""),
            access_token=str(answer["access_token"]),
            refresh_token=str(answer["refresh_token"]) if answer.get("refresh_token") else None,
            access_expires_at=datetime.now(UTC) + timedelta(seconds=int(answer["expires_in"])),
        )
    except (KeyError, TypeError, ValueError):
        raise YouTubeUploadError(
            "Google trả dữ liệu không đọc được, thử lại sau", "token answer without its fields"
        ) from None


def exchange_code(code: str) -> Tokens:
    try:
        return _tokens({"code": code, "grant_type": "authorization_code", "redirect_uri": REDIRECT_URI})
    except YouTubeUploadError as err:
        if err.expired:
            raise YouTubeUploadError(
                "Mã ủy quyền Google không hợp lệ hoặc đã hết hạn, hãy kết nối lại", err.detail
            ) from None
        raise


def refresh(refresh_token: str) -> Tokens:
    return _tokens({"grant_type": "refresh_token", "refresh_token": refresh_token})


def revoke(token: str) -> None:
    _call("POST", f"{config.google_oauth_url()}/revoke", data={"token": token})


def my_channel(access_token: str) -> ChannelInfo:
    """The channel the member picked on Google's consent page."""
    response = _call(
        "GET",
        f"{config.youtube_api_url()}/channels",
        params={"part": "snippet", "mine": "true"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if response.status_code != 200:
        raise _error(response)
    items = (response.json() or {}).get("items") or []
    if not items or not isinstance(items[0], dict) or not items[0].get("id"):
        raise YouTubeUploadError(MESSAGES["youtubeSignupRequired"], response.text[:3000])
    snippet = items[0].get("snippet") or {}
    handle = str(snippet.get("customUrl") or "")
    if handle and not handle.startswith("@"):
        handle = f"@{handle}"
    return ChannelInfo(
        channel_id=str(items[0]["id"]), title=str(snippet.get("title") or "YouTube")[:200], handle=handle
    )


def clean_title(title: str) -> str:
    """YouTube refuses `<` and `>` in a title, and more than 100 characters."""
    return " ".join(title.replace("<", "").replace(">", "").split())[:MAX_TITLE]


def metadata(title: str, description: str, tags: list[str] | None = None) -> dict:
    """The upload's body. `tags` are already cleaned (`hashtags.youtube_tags`); none means no `tags` field."""
    return {
        "snippet": {
            "title": clean_title(title),
            "description": description.replace("<", "").replace(">", "")[:MAX_DESCRIPTION],
            **({"tags": tags} if tags else {}),
        },
        "status": {
            "privacyStatus": "private",
            "selfDeclaredMadeForKids": False,
            # Every video of the app is made with AI: YouTube asks for the label, as TikTok does.
            "containsSyntheticMedia": True,
        },
    }


def start_upload(access_token: str, body: dict, size: int) -> str:
    """A resumable upload session for a `size`-byte MP4: its URL, which the file is then sent to."""
    response = _call(
        "POST",
        f"{config.youtube_upload_url()}/videos",
        params={"uploadType": "resumable", "part": "snippet,status"},
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Upload-Content-Length": str(size),
            "X-Upload-Content-Type": "video/mp4",
        },
        json=body,
    )
    location = response.headers.get("Location")
    if response.status_code != 200 or not location:
        raise _error(response)
    return location


def _done(response: httpx.Response) -> dict:
    try:
        video = response.json()
    except ValueError:
        video = None
    if not isinstance(video, dict) or not video.get("id"):
        raise YouTubeUploadError("YouTube trả dữ liệu không đọc được, thử lại sau", response.text[:3000])
    return video


def received(access_token: str, session_url: str, size: int) -> dict | int | None:
    """What YouTube holds of an upload session: the video (dict) when the upload is complete, how many bytes it has
    (int) when it is not, None when the session is gone and a new upload has to start."""
    response = _call(
        "PUT",
        session_url,
        headers={"Authorization": f"Bearer {access_token}", "Content-Range": f"bytes */{size}", "Content-Length": "0"},
    )
    if response.status_code in (200, 201):
        return _done(response)
    if response.status_code == 308:
        # "Range: bytes=0-999" says the first 1000 bytes arrived; no Range header, none did.
        last = (response.headers.get("Range") or "").rpartition("-")[2]
        return int(last) + 1 if last.isdigit() else 0
    if response.status_code in (404, 410):
        return None
    raise _error(response)


def send_file(access_token: str, session_url: str, path: Path, start: int = 0) -> dict:
    """Send the MP4 from byte `start` to the session; the uploaded video as YouTube returns it."""
    size = path.stat().st_size
    with path.open("rb") as file:
        file.seek(start)
        data = file.read()
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "video/mp4"}
    if start:
        headers["Content-Range"] = f"bytes {start}-{size - 1}/{size}"
    response = _call("PUT", session_url, timeout=UPLOAD_TIMEOUT, headers=headers, content=data)
    if response.status_code in (200, 201):
        return _done(response)
    raise _error(response)


def set_thumbnail(access_token: str, video_id: str, jpeg: bytes) -> None:
    """The video's custom thumbnail (thumbnails.set, a JPEG under 2 MB); YouTube allows it only on a verified channel."""
    response = _call(
        "POST",
        "https://www.googleapis.com/upload/youtube/v3/thumbnails/set",
        params={"videoId": video_id, "uploadType": "media"},
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "image/jpeg"},
        content=jpeg,
    )
    if response.status_code != 200:
        raise _error(response)


def studio_url(video_id: str) -> str:
    return f"https://studio.youtube.com/video/{video_id}/edit"


def shorts_url(video_id: str) -> str:
    return f"https://www.youtube.com/shorts/{video_id}"
