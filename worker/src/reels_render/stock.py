"""Pixabay photo search for scenes that have no usable image of their own."""

import hashlib
import http.client
import json
import os
import random
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from .env import read_env
from .errors import StockSearchError
from .images import is_image
from .script import Scene, Script

API_URL = "https://pixabay.com/api/"
USER_AGENT = "reels-render/0.1 (Reels Studio stock image search)"
CANDIDATES = 10
PICK_FROM = 3
REQUEST_TIMEOUT = 15
RETRY_DELAY = 5
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_DOWNLOAD_FAILURES = 2
# Pixabay's API terms require search results to be cached for 24 hours.
CACHE_TTL = 24 * 60 * 60

Warn = Callable[[str], None]


class HttpStatusError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}")
        self.status = status
        self.body = body


class NetworkError(Exception):
    """Connection failure, timeout, or a failed image download."""


class TooLargeError(Exception):
    pass


_clock = time.monotonic


def fetch(url: str, timeout: float, max_bytes: int) -> bytes:
    """GET with a total deadline that also covers a body trickling in slowly."""
    deadline = _clock() + timeout
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            length = response.headers.get("Content-Length", "")
            if length.isdigit() and int(length) > max_bytes:
                raise TooLargeError
            # urllib's timeout applies to each socket operation; shrinking it to the time left keeps
            # one stalled read from running past the total deadline.
            sock = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
            body = bytearray()
            while True:
                remaining = deadline - _clock()
                if remaining <= 0:
                    raise NetworkError("hết thời gian chờ")
                if sock is not None and not response.isclosed():
                    sock.settimeout(remaining)
                chunk = response.read1(64 * 1024)
                if not chunk:
                    # A connection dropped mid-body ends early without an error from urllib.
                    if length.isdigit() and len(body) < int(length):
                        raise NetworkError("mất kết nối khi đang nhận dữ liệu")
                    return bytes(body)
                body += chunk
                if len(body) > max_bytes:
                    raise TooLargeError
    except urllib.error.HTTPError as err:
        raise HttpStatusError(err.code, _error_body(err)) from None
    # URLError, timeouts, connection resets and SSL errors are all OSError subclasses.
    except (OSError, http.client.HTTPException) as err:
        reason = err.reason if isinstance(err, urllib.error.URLError) else err
        raise NetworkError(str(reason) or type(err).__name__) from None


def _error_body(err: urllib.error.HTTPError) -> str:
    try:
        return err.read(2000).decode("utf-8", "replace")
    except (OSError, http.client.HTTPException):
        return ""


def default_cache_dir() -> Path:
    return Path(tempfile.gettempdir()) / "reels_render_cache"


class SearchCache:
    """Search results per keyword on disk; any cache problem is treated as a miss, never an error."""

    def __init__(self, folder: Path, now: Callable[[], float] = time.time):
        self.folder = folder
        self._now = now

    def _path(self, keyword: str) -> Path:
        digest = hashlib.sha256(f"pixabay|vi|{keyword}".encode()).hexdigest()
        return self.folder / f"{digest}.json"

    def get(self, keyword: str) -> list[str] | None:
        try:
            data = json.loads(self._path(keyword).read_text(encoding="utf-8"))
            urls = data["urls"]
            fresh = 0 <= self._now() - data["saved_at"] < CACHE_TTL
        except (OSError, ValueError, KeyError, TypeError):
            return None
        if not fresh or not isinstance(urls, list) or not all(isinstance(url, str) for url in urls):
            return None
        return urls

    def put(self, keyword: str, urls: list[str]) -> None:
        temp = None
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            handle, temp = tempfile.mkstemp(suffix=".tmp", dir=self.folder)
            with os.fdopen(handle, "w", encoding="utf-8") as file:
                json.dump({"keyword": keyword, "saved_at": self._now(), "urls": urls}, file, ensure_ascii=False)
            os.replace(temp, self._path(keyword))
        except OSError:
            if temp is not None:
                Path(temp).unlink(missing_ok=True)


class Pixabay:
    def __init__(self, key: str, cache: SearchCache | None = None, sleep: Callable[[float], None] = time.sleep):
        self.key = key
        self.cache = cache if cache is not None else SearchCache(default_cache_dir())
        self.sleep = sleep
        self.api_calls = 0

    def search(self, keyword: str, label: str, warn: Warn) -> list[str]:
        """Return the largeImageURL of the first results, in Pixabay's relevance order."""
        cached = self.cache.get(keyword)
        if cached is not None:
            return cached
        query = urllib.parse.urlencode(
            {
                "key": self.key,
                "q": keyword,
                "lang": "vi",
                "image_type": "photo",
                "safesearch": "true",
                "per_page": CANDIDATES,
            }
        )
        try:
            body = self._get_with_retry(f"{API_URL}?{query}")
        except HttpStatusError as err:
            if err.status == 400 and "API key" in err.body:
                raise StockSearchError("Key Pixabay không hợp lệ, kiểm tra file .env") from None
            detail = self.redact(err.body.strip())[:200]
            warn(f"{label}: Pixabay từ chối từ khóa \"{keyword}\" (HTTP {err.status}: {detail}), bỏ qua")
            return []
        try:
            hits = json.loads(body)["hits"][:CANDIDATES]
        except (ValueError, KeyError, TypeError):
            raise StockSearchError("Pixabay trả kết quả không đọc được, thử lại sau") from None
        urls = [hit.get("largeImageURL") for hit in hits if isinstance(hit, dict)]
        # The address comes from the network; only https may be fetched, never file:// or similar.
        urls = [url for url in urls if isinstance(url, str) and url.startswith("https://")]
        self.cache.put(keyword, urls)
        return urls

    def _get_with_retry(self, url: str) -> bytes:
        for attempt in (1, 2):
            self.api_calls += 1
            try:
                return fetch(url, REQUEST_TIMEOUT, MAX_RESPONSE_BYTES)
            except HttpStatusError as err:
                if err.status != 429 and err.status < 500:
                    raise
                failure: Exception = err
            except (NetworkError, TooLargeError) as err:
                failure = err
            if attempt == 1:
                self.sleep(RETRY_DELAY)
        if isinstance(failure, HttpStatusError) and failure.status == 429:
            raise StockSearchError("Pixabay đang giới hạn lượt tìm, thử lại sau 1 phút")
        if isinstance(failure, HttpStatusError):
            raise StockSearchError(f"Pixabay đang lỗi (HTTP {failure.status}), thử lại sau")
        if isinstance(failure, TooLargeError):
            raise StockSearchError("Pixabay trả kết quả quá lớn, thử lại sau")
        raise StockSearchError(f"Không kết nối được Pixabay ({self.redact(str(failure))}). Kiểm tra mạng rồi thử lại")

    def download(self, url: str, target: Path) -> bool:
        """Save the image and say whether it is usable; a network failure raises NetworkError."""
        try:
            data = fetch(url, REQUEST_TIMEOUT, MAX_IMAGE_BYTES)
        except TooLargeError:
            return False
        except HttpStatusError as err:
            raise NetworkError(str(err)) from None
        target.write_bytes(data)
        return is_image(target)

    def redact(self, text: str) -> str:
        text = re.sub(r"key=[^&\s]*", "key=***", text)
        return text.replace(self.key, "***") if self.key else text


@dataclass(frozen=True)
class StockResult:
    script: Script
    missing: list[Scene]  # scenes still without an image because nothing usable was found
    api_calls: int


def find_stock_images(
    script: Script,
    work_dir: Path,
    on_warning: Warn | None = None,
    client: Pixabay | None = None,
    rng: random.Random | None = None,
) -> StockResult:
    """Fill every scene without a usable image from Pixabay, downloading into work_dir.

    Never asks anyone: scenes with nothing usable come back in `missing`. Key, network and
    rate-limit problems raise StockSearchError.
    """
    warn = on_warning or (lambda message: None)
    for scene in script.all_scenes:
        if scene.image is None and scene.missing_image is not None:
            hint = ", sẽ tìm ảnh thay thế" if scene.keywords else ""
            warn(f"{scene.label}: không thấy file {scene.missing_image}{hint}")

    to_search = [scene for scene in script.all_scenes if scene.image is None and scene.video is None and scene.keywords]
    if to_search and client is None:
        key = read_env("PIXABAY_API_KEY")
        if not key:
            raise StockSearchError(
                "Chưa có key Pixabay để tìm ảnh: thêm dòng PIXABAY_API_KEY=<key> vào file .env ở thư mục "
                "gốc repo (lấy key miễn phí tại https://pixabay.com/api/docs/)"
            )
        client = Pixabay(key)

    picker = _Picker(client, work_dir, rng or random.Random(), warn)
    found = {scene.number: picker.pick(scene) for scene in to_search}

    def resolve(scene: Scene) -> Scene:
        image = found.get(scene.number)
        return replace(scene, image=image) if image is not None else scene

    resolved = Script(title=resolve(script.title), scenes=[resolve(scene) for scene in script.scenes])
    missing = [scene for scene in resolved.all_scenes if scene.image is None and scene.video is None]
    return StockResult(resolved, missing, client.api_calls if client is not None else 0)


class _Picker:
    def __init__(self, client: Pixabay | None, work_dir: Path, rng: random.Random, warn: Warn):
        self.client = client
        self.work_dir = work_dir
        self.rng = rng
        self.warn = warn
        self.used: dict[str, Path] = {}  # downloaded URL -> file, shared by every scene of the video
        self.broken: set[str] = set()
        self.downloads = 0

    def pick(self, scene: Scene) -> Path | None:
        network_failures = 0
        duplicate = None
        for keyword in scene.keywords:
            urls = self.client.search(keyword, scene.label, self.warn)
            if duplicate is None:
                duplicate = next((self.used[url] for url in urls if url in self.used), None)
            fresh = [url for url in urls if url not in self.used and url not in self.broken]
            while fresh:
                url = self.rng.choice(fresh[:PICK_FROM])
                fresh.remove(url)
                self.downloads += 1
                target = self.work_dir / f"stock-{self.downloads:03d}.img"
                try:
                    usable = self.client.download(url, target)
                except NetworkError:
                    network_failures += 1
                    if network_failures >= MAX_DOWNLOAD_FAILURES:
                        raise StockSearchError("Mạng chậm hoặc bị chặn khi tải ảnh, thử lại sau") from None
                    continue
                if usable:
                    self.used[url] = target
                    return target
                self.broken.add(url)
                target.unlink(missing_ok=True)
        if duplicate is not None:
            return duplicate
        # A user image would be written into the JSON for good while Pixabay may still have photos,
        # so a network problem stops the render instead of asking.
        if network_failures:
            raise StockSearchError(f"Không tải được ảnh cho {scene.label} do lỗi mạng, thử lại sau")
        return None
