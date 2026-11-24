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
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import yt_dlp

from .clips import MAX_CLIP_BYTES, looks_like_clip
from .uploads import MAX_IMAGE_BYTES, MAX_MUSIC_BYTES, UploadRejected, check_mp3, image_extension

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


# Why a link failed, as a short code the assistant can branch on (add_links reports it next to the message).
NOT_PUBLIC = "not_public"  # the host wants a sign-in or refuses us: share the file publicly, or use another link
UNREACHABLE = "expired_or_unreachable"  # gone, expired or not answering: ask for a fresh link
TOO_LARGE = "too_large"  # over the photo or clip limit
NOT_A_FILE = "not_media"  # an address that is not a photo or clip: another link, not the same one again
BLOCKED_HOST = "blocked_host"  # points inside our network
INVALID_LINK = "invalid_link"  # not even an http(s) address


class RemoteMediaError(Exception):
    """The message is shown to members; `reason` is one of the codes above."""

    def __init__(self, message: str, reason: str = UNREACHABLE) -> None:
        super().__init__(message)
        self.reason = reason


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
        raise RemoteMediaError("Hãy dán link ảnh hoặc video", INVALID_LINK)
    if len(url) > MAX_URL_LENGTH:
        raise RemoteMediaError("Link quá dài", INVALID_LINK)
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise RemoteMediaError("Link phải bắt đầu bằng http:// hoặc https://", INVALID_LINK)
    if parts.username or parts.password:
        raise RemoteMediaError("Link không được chứa tên đăng nhập hay mật khẩu", INVALID_LINK)
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
        raise RemoteMediaError("Link trỏ vào địa chỉ nội bộ, không tải được", BLOCKED_HOST)


def _fetch(
    url: str, target: Path, max_bytes: int = MAX_CLIP_BYTES, too_big: str = TOO_BIG, seconds: float = DEADLINE_SECONDS
) -> None:
    """The link's body into `target`, at most `max_bytes` (a clip's size by default) within `seconds`."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/*,video/*,*/*;q=0.5"})
    deadline = time.monotonic() + seconds
    try:
        with _opener().open(request, timeout=TIMEOUT_SECONDS) as response, open(target, "wb") as file:
            length = response.headers.get("Content-Length", "")
            if length.isdigit() and int(length) > max_bytes:
                raise RemoteMediaError(too_big, TOO_LARGE)
            copied = 0
            while chunk := response.read(256 * 1024):
                copied += len(chunk)
                if copied > max_bytes:
                    raise RemoteMediaError(too_big, TOO_LARGE)
                file.write(chunk)
                if time.monotonic() > deadline:
                    raise RemoteMediaError("Trang này phản hồi quá chậm, hãy thử lại hoặc tải về rồi tải lên")
    except RemoteMediaError:
        raise
    except urllib.error.HTTPError as err:
        raise RemoteMediaError(
            f"Trang này từ chối tải (HTTP {err.code}): hãy sao chép ảnh rồi dán, hoặc tải về rồi tải lên",
            NOT_PUBLIC if err.code in (401, 403) else UNREACHABLE,
        ) from None
    except (OSError, http.client.HTTPException) as err:
        if isinstance(getattr(err, "reason", None), _BlockedAddress) or isinstance(err, _BlockedAddress):
            raise RemoteMediaError("Link trỏ vào địa chỉ nội bộ, không tải được", BLOCKED_HOST) from None
        raise RemoteMediaError("Không tải được từ link này, hãy kiểm tra link rồi thử lại") from None


def download_tiktok(url: str, folder: Path) -> Path:
    """A public TikTok video as a file in `folder`, the largest one TikTok offers, H.264 before HEVC at a size."""
    if "/photo/" in urllib.parse.urlsplit(url).path:
        raise RemoteMediaError("Đây là bài ảnh TikTok: hãy mở ảnh, sao chép ảnh rồi dán vào cảnh", NOT_A_FILE)
    return _download_with_ytdlp(
        url,
        folder,
        MAX_CLIP_BYTES,
        TOO_BIG,
        "Hãy dán link của một video TikTok (có /video/ trong link)",
        "Không tải được video TikTok này: hãy kiểm tra video còn công khai và link đúng rồi thử lại",
    )


def _download_with_ytdlp(url: str, folder: Path, max_bytes: int, too_big: str, not_one: str, failed: str) -> Path:
    """One public video of a page yt-dlp knows, as a file in `folder`: the largest one offered, H.264 before HEVC at a
    size. A page listing many videos (a profile, a search, a playlist) is refused with `not_one`."""
    options = {
        "outtmpl": str(folder / "linked.%(ext)s"),
        "format": "b",
        "format_sort": ["res", "vcodec:h264"],
        "max_filesize": max_bytes,
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
                raise RemoteMediaError(not_one, NOT_A_FILE)
            tool.process_ie_result(info, download=True)
    except yt_dlp.utils.DownloadError:
        raise RemoteMediaError(failed) from None
    files = [path for path in folder.glob("linked.*") if path.suffix not in (".part", ".ytdl")]
    if not files:
        # yt-dlp skips a file over max_filesize without an error.
        raise RemoteMediaError(too_big, TOO_LARGE)
    return files[0]


def is_youtube(host: str) -> bool:
    host = host.lower().rstrip(".")
    return host in ("youtu.be", "youtube.com") or host.endswith(".youtube.com")


# A sample video ("Từ video mẫu", reference.py) may be longer and larger than a scene clip.
MAX_SAMPLE_BYTES = 100 * 1024 * 1024
SAMPLE_TOO_BIG = "Video mẫu quá 100 MB, hãy chọn video ngắn hơn"
SAMPLE_DEADLINE_SECONDS = 180


def download_sample(url: str, folder: Path) -> Path:
    """A sample video from a pasted link: TikTok and YouTube pages through yt-dlp, any other link must be the video
    file itself (MP4, MOV, WebM), fetched like a scene's link."""
    url = check_url(url)
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname or ""
    if is_tiktok(host) or is_youtube(host):
        if "/photo/" in parts.path:
            raise RemoteMediaError("Đây là bài ảnh TikTok, không phải video", NOT_A_FILE)
        return _download_with_ytdlp(
            url,
            folder,
            MAX_SAMPLE_BYTES,
            SAMPLE_TOO_BIG,
            "Hãy dán link của một video, không phải trang cá nhân, danh sách hay kết quả tìm kiếm",
            "Không tải được video này: hãy kiểm tra video còn công khai và link đúng, hoặc tải video về rồi tải lên",
        )
    _check_host(parts)
    target = folder / "linked"
    _fetch(url, target, MAX_SAMPLE_BYTES, SAMPLE_TOO_BIG, SAMPLE_DEADLINE_SECONDS)
    with open(target, "rb") as file:
        head = file.read(16)
    if not looks_like_clip(head):
        raise RemoteMediaError(
            "Link này không phải video: hãy dán link TikTok, YouTube hoặc link file MP4, hoặc tải video về rồi tải lên"
        )
    return target


DRIVE_HOST = "drive.google.com"
DRIVE_DOWNLOAD_HOST = "drive.usercontent.google.com"
DRIVE_ID = re.compile(r"[A-Za-z0-9_-]{10,}")
DRIVE_FILE_PATH = re.compile(r"/file/(?:u/\d+/)?d/([^/]+)")
DRIVE_FOLDER_PATH = re.compile(r"/(?:drive/(?:u/\d+/)?)?folders/")
GOOGLE_DOC_PATHS = ("/document/", "/spreadsheets/", "/presentation/", "/forms/")
ONE_FILE_ONLY = "Hãy chia sẻ riêng từng file ảnh hoặc video (không dùng link thư mục hay tài liệu Google)"
DRIVE_NOT_PUBLIC = (
    "Link Google Drive này chưa chia sẻ công khai hoặc file quá lớn để tải thẳng: hãy đặt chia sẻ "
    "“Bất kỳ ai có đường liên kết” rồi thử lại, hoặc tải file lên bằng trình duyệt"
)


def normalize_link(url: str) -> str:
    """The address to download: a Google Drive file's link (a "view" page, `open?id=`, `uc?id=`) becomes its
    direct-download address, since the page itself is HTML. Any other link comes back unchanged; a Drive folder or a
    Google document is refused, as one link is one file."""
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower()
    if host == "docs.google.com" and parts.path.startswith(GOOGLE_DOC_PATHS):
        raise RemoteMediaError(ONE_FILE_ONLY, NOT_A_FILE)
    if host != DRIVE_HOST:
        return url
    if DRIVE_FOLDER_PATH.match(parts.path):
        raise RemoteMediaError(ONE_FILE_ONLY, NOT_A_FILE)
    query = urllib.parse.parse_qs(parts.query)
    found = DRIVE_FILE_PATH.match(parts.path)
    file_id = found.group(1) if found else (query.get("id") or [""])[0] if parts.path in ("/open", "/uc") else ""
    if not DRIVE_ID.fullmatch(file_id):
        return url
    direct = {"id": file_id, "export": "download"}
    if key := (query.get("resourcekey") or [""])[0]:
        direct["resourcekey"] = key
    return f"https://{DRIVE_DOWNLOAD_HOST}/download?" + urllib.parse.urlencode(direct)


def download(url: str, folder: Path) -> Media:
    """What the link holds, within the upload limits: a photo (jpg, png, webp) or a clip saved in `folder`. A Google
    Drive file's link is fetched through its direct-download address (`normalize_link`)."""
    url = check_url(url)
    url = normalize_link(url)
    parts = urllib.parse.urlsplit(url)
    if is_tiktok(parts.hostname or ""):
        return Media(clip=download_tiktok(url, folder))
    via_drive = parts.hostname == DRIVE_DOWNLOAD_HOST
    _check_host(parts)
    target = folder / "link"
    _fetch(url, target)
    with open(target, "rb") as file:
        head = file.read(16)
    if looks_like_clip(head):
        return Media(clip=target)
    if target.stat().st_size > MAX_IMAGE_BYTES:
        raise RemoteMediaError("Ảnh quá 15 MB, hãy chọn ảnh nhỏ hơn", TOO_LARGE)
    data = target.read_bytes()
    try:
        return Media(photo=(data, image_extension(data)))
    except UploadRejected:
        if via_drive:
            raise RemoteMediaError(DRIVE_NOT_PUBLIC, NOT_PUBLIC) from None
        raise RemoteMediaError(NOT_MEDIA, NOT_A_FILE) from None


MUSIC_TOO_BIG = "File nhạc quá 20 MB, hãy chọn file nhỏ hơn"


def download_music(url: str, folder: Path) -> bytes:
    """An MP3 file's bytes from a direct link (a free music site's download), within the upload's 20 MB. A TikTok or
    YouTube link is refused: their sound is someone's work that Facebook mutes or blocks (owner, 2026-11-15)."""
    url = check_url(url)
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname or ""
    if is_tiktok(host) or is_youtube(host):
        raise RemoteMediaError(
            "Không lấy nhạc từ TikTok hay YouTube: hãy dùng link file MP3 của nguồn nhạc có giấy phép"
        )
    _check_host(parts)
    target = folder / "music"
    _fetch(url, target, MAX_MUSIC_BYTES, MUSIC_TOO_BIG)
    data = target.read_bytes()
    try:
        check_mp3(data)
    except UploadRejected:
        raise RemoteMediaError("Link không phải file MP3: hãy dùng link tải thẳng file .mp3") from None
    return data
