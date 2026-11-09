"""Pixabay photos for scenes, chosen while editing and stored, so the render uses the photo the member saw.

Built on reels_render's fetch (a total deadline per request). Search results are cached for 24 hours,
as Pixabay's API terms require.
"""

import hashlib
import json
import os
import re
import tempfile
import time
import urllib.parse
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from reels_render import stock

from . import config
from .uploads import UploadRejected, image_extension

MAX_SEARCH_BYTES = 2 * 1024 * 1024
RESULTS = 20  # the picker grid shows them all; automatic choices only ever use the first few


BLOCKED_MESSAGE = (
    "Pixabay đang chặn mạng của máy chủ (trang kiểm tra chống bot của Cloudflare): thử tắt VPN hoặc đổi mạng, "
    "hoặc chọn nguồn khác ở mũi tên cạnh nút tìm ảnh"
)


def _blocked_by_cloudflare(err: stock.HttpStatusError) -> bool:
    """Cloudflare's bot check answers with an HTML page; Pixabay's own errors (a real rate limit included) are text."""
    body = err.body.lstrip().lower()
    return err.status in (403, 429, 503) and (body.startswith("<!doctype html") or body.startswith("<html"))


class PixabayError(Exception):
    """Pixabay could not be used at all; `kind` (key, rate_limit, blocked, server, network) goes to the job detail."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


@dataclass(frozen=True)
class Photo:
    url: str
    data: bytes
    extension: str
    # What the scene must credit for this photo (wikimedia.credit_of); None: its licence asks for nothing.
    credit: dict | None = None


@dataclass(frozen=True)
class Hit:
    url: str  # large image, downloaded only when chosen
    preview: str  # small thumbnail, shown in the picker straight from Pixabay and never stored
    # Size of the file `url` serves, when the source says; None: unknown, so no filter leaves it out.
    width: int | None = None
    height: int | None = None
    # What using it would have to credit (wikimedia.credit_of); None: its licence asks for nothing.
    credit: dict | None = None


# The picker's "Hướng ảnh": tall photos by default, since the 9:16 frame crops least of them.
ORIENTATIONS = ("vertical", "square", "all")
# A photo whose short side is below this would be blown up blurry in the 1080-wide frame. Pixabay's and Pexels'
# large files of a tall photo are about 720 wide, so the bar sits under that.
MIN_SHORT_SIDE = 640


def fits(hit: Hit, orientation: str) -> bool:
    """Whether a result has the asked shape and is big enough; one of unknown size always fits."""
    if not hit.width or not hit.height:
        return True
    if min(hit.width, hit.height) < MIN_SHORT_SIDE:
        return False
    ratio = hit.height / hit.width
    if orientation == "vertical":
        return ratio >= 1.1
    if orientation == "square":
        return 0.8 <= ratio <= 1.25
    return True


def delivered_size(width: object, height: object, max_width: int, max_height: int) -> tuple[int | None, int | None]:
    """The size of a source's scaled-down file from the original's size, fitted inside max_width × max_height."""
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        return None, None
    scale = min(1.0, max_width / width, max_height / height)
    return round(width * scale), round(height * scale)


class HitCache:
    """Search results with their thumbnails, kept 24 hours as Pixabay's terms require; problems count as a miss."""

    def __init__(self, folder: Path, now=time.time):
        self.folder = folder
        self._now = now

    def _path(self, keyword: str) -> Path:
        return self.folder / f"{hashlib.sha256(f'pixabay-hits|vi|{keyword}'.encode()).hexdigest()}.json"

    def get(self, keyword: str) -> list[Hit] | None:
        try:
            data = json.loads(self._path(keyword).read_text(encoding="utf-8"))
            if not 0 <= self._now() - data["saved_at"] < stock.CACHE_TTL:
                return None
            return [Hit(item["url"], item["preview"], item.get("width"), item.get("height")) for item in data["hits"]]
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def put(self, keyword: str, hits: list[Hit]) -> None:
        temp = None
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            handle, temp = tempfile.mkstemp(suffix=".tmp", dir=self.folder)
            with os.fdopen(handle, "w", encoding="utf-8") as file:
                json.dump({"saved_at": self._now(), "hits": [hit.__dict__ for hit in hits]}, file, ensure_ascii=False)
            os.replace(temp, self._path(keyword))
        except OSError:
            if temp is not None:
                Path(temp).unlink(missing_ok=True)


class Pixabay:
    def __init__(self, key: str | None = None, api_url: str | None = None, cache: HitCache | None = None):
        self.key = config.pixabay_key() if key is None else key
        self.api_url = api_url or config.pixabay_api_url()
        self.cache = cache or HitCache(stock.default_cache_dir() / "api-hits")
        parts = urllib.parse.urlsplit(self.api_url)
        self._api_origin = f"{parts.scheme}://{parts.netloc}/"

    def search(self, keyword: str, deadline: float, orientation: str = "all") -> list[str]:
        """Large image URLs for the keyword in Pixabay's relevance order; [] when it has nothing."""
        return [hit.url for hit in self.search_hits(keyword, deadline, orientation)]

    def search_hits(self, keyword: str, deadline: float, orientation: str = "all") -> list[Hit]:
        """Pixabay can be asked for tall photos only; square ones are picked out of all by their size."""
        if not self.key:
            raise PixabayError("key", "Chưa cấu hình PIXABAY_API_KEY nên không tìm được ảnh Pixabay")
        tall = orientation == "vertical"
        cache_key = f"{keyword}|vertical" if tall else keyword
        cached = self.cache.get(cache_key)
        if cached is not None:
            return [
                hit
                for hit in cached
                if self._allowed(hit.url) and self._allowed(hit.preview) and fits(hit, orientation)
            ]
        query = urllib.parse.urlencode(
            {
                "key": self.key,
                "q": keyword,
                "lang": "vi",
                "image_type": "photo",
                "safesearch": "true",
                "per_page": RESULTS,
            }
            | ({"orientation": "vertical"} if tall else {})
        )
        try:
            body = stock.fetch(f"{self.api_url}?{query}", self._remaining(deadline), MAX_SEARCH_BYTES)
        except stock.HttpStatusError as err:
            if err.status == 400 and "API key" in err.body:
                raise PixabayError("key", "Key Pixabay không hợp lệ") from None
            if _blocked_by_cloudflare(err):
                raise PixabayError("blocked", BLOCKED_MESSAGE) from None
            if err.status == 429:
                raise PixabayError("rate_limit", "Pixabay đang giới hạn lượt tìm, thử lại sau 1 phút") from None
            if err.status >= 500:
                raise PixabayError("server", f"Pixabay đang lỗi (HTTP {err.status}), thử lại sau") from None
            return []  # Pixabay refuses some keywords (too long, odd characters): nothing found.
        except stock.TooLargeError:
            raise PixabayError("server", "Pixabay trả kết quả quá lớn, thử lại sau") from None
        except stock.NetworkError as err:
            raise self._network_error(err) from None
        try:
            items = json.loads(body)["hits"][:RESULTS]
            hits = [
                # largeImageURL is scaled to at most 1280 px on its long side.
                Hit(
                    item["largeImageURL"],
                    item.get("previewURL") or item.get("webformatURL") or "",
                    *delivered_size(item.get("imageWidth"), item.get("imageHeight"), 1280, 1280),
                )
                for item in items
                if isinstance(item, dict) and isinstance(item.get("largeImageURL"), str)
            ]
        except (ValueError, KeyError, TypeError):
            raise PixabayError("server", "Pixabay trả kết quả không đọc được, thử lại sau") from None
        hits = [
            hit
            for hit in hits
            if isinstance(hit.preview, str) and self._allowed(hit.url) and self._allowed(hit.preview)
        ]
        self.cache.put(cache_key, hits)
        return [hit for hit in hits if fits(hit, orientation)]

    def download(self, url: str, deadline: float) -> Photo | None:
        """The photo, or None when the file is too large or not a usable JPG/PNG/WebP."""
        try:
            data = stock.fetch(url, self._remaining(deadline), stock.MAX_IMAGE_BYTES)
        except stock.TooLargeError:
            return None
        except stock.HttpStatusError:
            return None
        except stock.NetworkError as err:
            raise self._network_error(err) from None
        try:
            return Photo(url, data, image_extension(data))
        except UploadRejected:
            return None

    def find_photo(
        self,
        keywords: Iterable[str],
        deadline: float,
        avoid: Iterable[str] = (),
        after: str | None = None,
        orientation: str = "all",
    ) -> Photo | None:
        return find_photo(self, keywords, deadline, avoid, after, orientation)

    def redact(self, text: str) -> str:
        text = re.sub(r"key=[^&\s]*", "key=***", text)
        return text.replace(self.key, "***") if self.key else text

    def _allowed(self, url: str) -> bool:
        # Addresses come from the network: only https, or the configured (test) server itself.
        return url.startswith("https://") or url.startswith(self._api_origin)

    def _network_error(self, err: Exception) -> PixabayError:
        return PixabayError("network", f"Pixabay không phản hồi kịp hoặc mất kết nối ({self.redact(str(err))})")

    @staticmethod
    def _remaining(deadline: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise PixabayError("network", "Pixabay không phản hồi kịp, thử lại sau")
        return remaining


def find_photo(
    client,
    keywords: Iterable[str],
    deadline: float,
    avoid: Iterable[str] = (),
    after: str | None = None,
    orientation: str = "all",
) -> Photo | None:
    """The first usable photo from any stock client (search + download) over the keywords, in order, skipping `avoid`.

    With `after` (the photo in use), results that come after it are tried first, so pressing
    "Tìm ảnh khác" again walks through the results instead of bouncing between two photos.
    """
    avoid = set(avoid) | ({after} if after else set())
    for keyword in keywords:
        urls = client.search(keyword, deadline, orientation)
        if after in urls:
            index = urls.index(after)
            urls = urls[index + 1 :] + urls[:index]
        for url in urls:
            if url in avoid:
                continue
            photo = client.download(url, deadline)
            if photo is not None:
                return photo
            avoid.add(url)
    return None
