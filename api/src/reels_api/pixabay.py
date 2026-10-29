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


class PixabayError(Exception):
    """Pixabay could not be used at all; `kind` (key, rate_limit, server, network) goes to the job detail."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


@dataclass(frozen=True)
class Photo:
    url: str
    data: bytes
    extension: str


@dataclass(frozen=True)
class Hit:
    url: str  # large image, downloaded only when chosen
    preview: str  # small thumbnail, shown in the picker straight from Pixabay and never stored


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
            return [Hit(item["url"], item["preview"]) for item in data["hits"]]
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

    def search(self, keyword: str, deadline: float) -> list[str]:
        """Large image URLs for the keyword in Pixabay's relevance order; [] when it has nothing."""
        return [hit.url for hit in self.search_hits(keyword, deadline)]

    def search_hits(self, keyword: str, deadline: float) -> list[Hit]:
        if not self.key:
            raise PixabayError("key", "Chưa cấu hình PIXABAY_API_KEY nên không tìm được ảnh Pixabay")
        cached = self.cache.get(keyword)
        if cached is not None:
            return [hit for hit in cached if self._allowed(hit.url) and self._allowed(hit.preview)]
        query = urllib.parse.urlencode({
            "key": self.key, "q": keyword, "lang": "vi", "image_type": "photo", "safesearch": "true",
            "per_page": RESULTS,
        })
        try:
            body = stock.fetch(f"{self.api_url}?{query}", self._remaining(deadline), MAX_SEARCH_BYTES)
        except stock.HttpStatusError as err:
            if err.status == 400 and "API key" in err.body:
                raise PixabayError("key", "Key Pixabay không hợp lệ") from None
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
            hits = [Hit(item["largeImageURL"], item.get("previewURL") or item.get("webformatURL") or "")
                    for item in items if isinstance(item, dict) and isinstance(item.get("largeImageURL"), str)]
        except (ValueError, KeyError, TypeError):
            raise PixabayError("server", "Pixabay trả kết quả không đọc được, thử lại sau") from None
        hits = [hit for hit in hits if isinstance(hit.preview, str) and self._allowed(hit.url)
                and self._allowed(hit.preview)]
        self.cache.put(keyword, hits)
        return hits

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

    def find_photo(self, keywords: Iterable[str], deadline: float, avoid: Iterable[str] = (),
                   after: str | None = None) -> Photo | None:
        """The first usable photo over the keywords, in order, skipping `avoid`.

        With `after` (the photo in use), results that come after it are tried first, so pressing
        "Tìm lại ảnh" again walks through the results instead of bouncing between two photos.
        """
        avoid = set(avoid) | ({after} if after else set())
        for keyword in keywords:
            urls = self.search(keyword, deadline)
            if after in urls:
                index = urls.index(after)
                urls = urls[index + 1:] + urls[:index]
            for url in urls:
                if url in avoid:
                    continue
                photo = self.download(url, deadline)
                if photo is not None:
                    return photo
                avoid.add(url)
        return None

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
