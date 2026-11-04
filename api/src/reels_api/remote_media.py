"""A photo or clip a member pastes as a link (or drags from another tab): downloaded by the api and stored like an
upload.

The address comes from the browser, so the download may only reach the public internet: every connection, the
first one and each redirect's, is checked against the address it actually reached (which also defeats a name that
resolves to a public address first and a private one later). Only http and https are followed.

A TikTok video's page is not the video file, so a TikTok link is handed to yt-dlp, which reads the page and fetches
the video from TikTok's own servers; only tiktok.com links go that way.
"""

import http.client
import ipaddress
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import yt_dlp

from .clips import MAX_CLIP_BYTES, looks_like_clip
from .uploads import MAX_IMAGE_BYTES, UploadRejected, image_extension

TIMEOUT_SECONDS = 15
# A whole download, a 50 MB clip included; each read still gives up after TIMEOUT_SECONDS of silence.
DEADLINE_SECONDS = 60
MAX_URL_LENGTH = 2000
MAX_REDIRECTS = 5
# Many image hosts refuse requests that do not look like a browser's.
USER_AGENT = "Mozilla/5.0 (compatible; ReelsStudio/1.0; +link pasted by a team member)"
TOO_BIG = "Video quá 50 MB, hãy chọn video ngắn hơn"
NOT_MEDIA = (
    "Link này không phải ảnh (JPG, PNG, WebP) hay video (MP4, MOV, WebM): với ảnh, hãy chuột phải vào ảnh, "
    "chọn “Sao chép địa chỉ hình ảnh”; với TikTok, dán link của video"
)


class RemoteMediaError(Exception):
    """The message is shown to members."""


@dataclass(frozen=True)
class Media:
    """What a link held: a photo's bytes and extension, or a clip saved as a file."""

    photo: tuple[bytes, str] | None = None
    clip: Path | None = None


def is_public(address: str) -> bool:
    """Whether the address is on the public internet (not loopback, private, link-local, reserved...)."""
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


class _BlockedAddress(OSError):
    pass


def _check_peer(sock: socket.socket) -> None:
    if not is_public(sock.getpeername()[0]):
        sock.close()
        raise _BlockedAddress("địa chỉ nội bộ")


class _HTTPConnection(http.client.HTTPConnection):
    def connect(self) -> None:
        super().connect()
        _check_peer(self.sock)


class _HTTPSConnection(http.client.HTTPSConnection, _HTTPConnection):
    """HTTPSConnection.connect calls super().connect(), which this order makes _HTTPConnection's: the TCP connection
    is checked before the TLS handshake sends anything."""


class _HTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(_HTTPConnection, req)


class _HTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_HTTPSConnection, req, context=self._context)


class _RedirectHandler(urllib.request.HTTPRedirectHandler):
    # urllib itself refuses redirects to anything but http, https and ftp, and this opener has no ftp handler.
    max_redirections = MAX_REDIRECTS


def _opener() -> urllib.request.OpenerDirector:
    # Built by hand, not with build_opener: no file://, ftp:// or data: handlers, and no proxy from the environment.
    opener = urllib.request.OpenerDirector()
    for handler in (
        _HTTPHandler(),
        _HTTPSHandler(),
        _RedirectHandler(),
        urllib.request.HTTPDefaultErrorHandler(),
        urllib.request.HTTPErrorProcessor(),
    ):
        opener.add_handler(handler)
    return opener


def check_url(url: str) -> str:
    """The link, trimmed, when it is an http(s) address worth trying; otherwise a member-facing error."""
    url = url.strip()
    if not url:
        raise RemoteMediaError("Hãy dán link ảnh hoặc video")
    if len(url) > MAX_URL_LENGTH:
        raise RemoteMediaError("Link quá dài")
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise RemoteMediaError("Link phải bắt đầu bằng http:// hoặc https://")
    if parts.username or parts.password:
        raise RemoteMediaError("Link không được chứa tên đăng nhập hay mật khẩu")
    return url


def is_tiktok(host: str) -> bool:
    host = host.lower().rstrip(".")
    return host == "tiktok.com" or host.endswith(".tiktok.com")


def _check_host(parts: urllib.parse.SplitResult) -> None:
    """Refuse a host that resolves to a non-public address before connecting, so the member hears why; the check on
    each connection (_check_peer) still guards against a name that resolves differently by then."""
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
    except (OSError, UnicodeError):
        raise RemoteMediaError("Không tìm thấy trang này, hãy kiểm tra link rồi thử lại") from None
    if not all(is_public(info[4][0]) for info in infos):
        raise RemoteMediaError("Link trỏ vào địa chỉ nội bộ, không tải được")


def _fetch(url: str, target: Path) -> None:
    """The link's body into `target`, at most a clip's size."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/*,video/*,*/*;q=0.5"})
    deadline = time.monotonic() + DEADLINE_SECONDS
    try:
        with _opener().open(request, timeout=TIMEOUT_SECONDS) as response, open(target, "wb") as file:
            length = response.headers.get("Content-Length", "")
            if length.isdigit() and int(length) > MAX_CLIP_BYTES:
                raise RemoteMediaError(TOO_BIG)
            copied = 0
            while chunk := response.read(256 * 1024):
                copied += len(chunk)
                if copied > MAX_CLIP_BYTES:
                    raise RemoteMediaError(TOO_BIG)
                file.write(chunk)
                if time.monotonic() > deadline:
                    raise RemoteMediaError("Trang này phản hồi quá chậm, hãy thử lại hoặc tải về rồi tải lên")
    except RemoteMediaError:
        raise
    except urllib.error.HTTPError as err:
        raise RemoteMediaError(
            f"Trang này từ chối tải (HTTP {err.code}): hãy sao chép ảnh rồi dán, hoặc tải về rồi tải lên"
        ) from None
    except (OSError, http.client.HTTPException) as err:
        if isinstance(getattr(err, "reason", None), _BlockedAddress) or isinstance(err, _BlockedAddress):
            raise RemoteMediaError("Link trỏ vào địa chỉ nội bộ, không tải được") from None
        raise RemoteMediaError("Không tải được từ link này, hãy kiểm tra link rồi thử lại") from None


def download_tiktok(url: str, folder: Path) -> Path:
    """A public TikTok video as a file in `folder`, the largest one TikTok offers, H.264 before HEVC at a size."""
    if "/photo/" in urllib.parse.urlsplit(url).path:
        raise RemoteMediaError("Đây là bài ảnh TikTok: hãy mở ảnh, sao chép ảnh rồi dán vào cảnh")
    options = {
        "outtmpl": str(folder / "tiktok.%(ext)s"),
        "format": "b",
        "format_sort": ["res", "vcodec:h264"],
        "max_filesize": MAX_CLIP_BYTES,
        "noplaylist": True,
        "socket_timeout": TIMEOUT_SECONDS,
        "retries": 1,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    try:
        with yt_dlp.YoutubeDL(options) as tool:
            # Read without downloading first: a profile or a search page lists many videos and is refused.
            info = tool.extract_info(url, download=False, process=False)
            if info is None or info.get("_type") in ("playlist", "multi_video") or "entries" in info:
                raise RemoteMediaError("Hãy dán link của một video TikTok (có /video/ trong link)")
            tool.process_ie_result(info, download=True)
    except yt_dlp.utils.DownloadError:
        raise RemoteMediaError(
            "Không tải được video TikTok này: hãy kiểm tra video còn công khai và link đúng rồi thử lại"
        ) from None
    files = [path for path in folder.glob("tiktok.*") if path.suffix not in (".part", ".ytdl")]
    if not files:
        # yt-dlp skips a file over max_filesize without an error.
        raise RemoteMediaError(TOO_BIG)
    return files[0]


def download(url: str, folder: Path) -> Media:
    """What the link holds, within the upload limits: a photo (jpg, png, webp) or a clip saved in `folder`."""
    url = check_url(url)
    parts = urllib.parse.urlsplit(url)
    if is_tiktok(parts.hostname or ""):
        return Media(clip=download_tiktok(url, folder))
    _check_host(parts)
    target = folder / "link"
    _fetch(url, target)
    with open(target, "rb") as file:
        head = file.read(16)
    if looks_like_clip(head):
        return Media(clip=target)
    if target.stat().st_size > MAX_IMAGE_BYTES:
        raise RemoteMediaError("Ảnh quá 15 MB, hãy chọn ảnh nhỏ hơn")
    data = target.read_bytes()
    try:
        return Media(photo=(data, image_extension(data)))
    except UploadRejected:
        raise RemoteMediaError(NOT_MEDIA) from None
