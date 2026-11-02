"""A photo a member pastes as a link (or drags from another tab): downloaded by the api and stored like an upload.

The address comes from the browser, so the download may only reach the public internet: every connection, the
first one and each redirect's, is checked against the address it actually reached (which also defeats a name that
resolves to a public address first and a private one later). Only http and https are followed.
"""

import http.client
import ipaddress
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

from .uploads import MAX_IMAGE_BYTES, UploadRejected, image_extension

TIMEOUT_SECONDS = 15
MAX_URL_LENGTH = 2000
MAX_REDIRECTS = 5
# Many image hosts refuse requests that do not look like a browser's.
USER_AGENT = "Mozilla/5.0 (compatible; ReelsStudio/1.0; +image link pasted by a team member)"


class RemoteImageError(Exception):
    """The message is shown to members."""


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
        raise RemoteImageError("Hãy dán link ảnh")
    if len(url) > MAX_URL_LENGTH:
        raise RemoteImageError("Link ảnh quá dài")
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise RemoteImageError("Link ảnh phải bắt đầu bằng http:// hoặc https://")
    if parts.username or parts.password:
        raise RemoteImageError("Link ảnh không được chứa tên đăng nhập hay mật khẩu")
    return url


def _check_host(parts: urllib.parse.SplitResult) -> None:
    """Refuse a host that resolves to a non-public address before connecting, so the member hears why; the check on
    each connection (_check_peer) still guards against a name that resolves differently by then."""
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
    except (OSError, UnicodeError):
        raise RemoteImageError("Không tìm thấy trang chứa ảnh, hãy kiểm tra link rồi thử lại") from None
    if not all(is_public(info[4][0]) for info in infos):
        raise RemoteImageError("Link ảnh trỏ vào địa chỉ nội bộ, không tải được")


def download(url: str) -> tuple[bytes, str]:
    """The photo's bytes and extension (jpg, png, webp), within the upload limits."""
    url = check_url(url)
    _check_host(urllib.parse.urlsplit(url))
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/*,*/*;q=0.5"})
    deadline = time.monotonic() + TIMEOUT_SECONDS
    try:
        with _opener().open(request, timeout=TIMEOUT_SECONDS) as response:
            length = response.headers.get("Content-Length", "")
            if length.isdigit() and int(length) > MAX_IMAGE_BYTES:
                raise RemoteImageError("Ảnh quá 15 MB, hãy chọn ảnh nhỏ hơn")
            body = bytearray()
            while chunk := response.read(64 * 1024):
                body += chunk
                if len(body) > MAX_IMAGE_BYTES:
                    raise RemoteImageError("Ảnh quá 15 MB, hãy chọn ảnh nhỏ hơn")
                if time.monotonic() > deadline:
                    raise RemoteImageError("Trang chứa ảnh phản hồi quá chậm, hãy thử lại hoặc tải ảnh về rồi tải lên")
    except RemoteImageError:
        raise
    except urllib.error.HTTPError as err:
        raise RemoteImageError(
            f"Trang chứa ảnh từ chối tải (HTTP {err.code}): hãy sao chép ảnh rồi dán, hoặc tải ảnh về rồi tải lên"
        ) from None
    except (OSError, http.client.HTTPException) as err:
        if isinstance(getattr(err, "reason", None), _BlockedAddress) or isinstance(err, _BlockedAddress):
            raise RemoteImageError("Link ảnh trỏ vào địa chỉ nội bộ, không tải được") from None
        raise RemoteImageError("Không tải được ảnh từ link này, hãy kiểm tra link rồi thử lại") from None
    try:
        return bytes(body), image_extension(bytes(body))
    except UploadRejected:
        raise RemoteImageError(
            "Link này không phải ảnh JPG, PNG hay WebP: hãy chuột phải vào ảnh, chọn “Sao chép địa chỉ hình ảnh”"
        ) from None
