"""Pexels photos for scenes: a second source in the picker, next to Pixabay.

Same shape as the Pixabay client (search hits for the grid, a download once one is chosen),
but Pexels takes its key in a header instead of the query string. No result cache: nothing
in Pexels' terms asks for one, and the picker searches are cheap.
"""

import json
import time
import urllib.parse
from collections.abc import Iterable

from reels_render import stock

from . import config
from .pixabay import Hit, Photo, delivered_size, find_photo, fits
from .uploads import UploadRejected, image_extension

MAX_SEARCH_BYTES = 2 * 1024 * 1024
RESULTS = 20  # the picker grid shows them all


class PexelsError(Exception):
    """Pexels could not be used at all; `kind` (key, rate_limit, server, network) mirrors PixabayError."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


class Pexels:
    def __init__(self, key: str | None = None, api_url: str | None = None):
        self.key = config.pexels_key() if key is None else key
        self.api_url = api_url or config.pexels_api_url()
        parts = urllib.parse.urlsplit(self.api_url)
        self._api_origin = f"{parts.scheme}://{parts.netloc}/"

    def search(self, keyword: str, deadline: float, orientation: str = "all") -> list[str]:
        """Large image URLs for the keyword in Pexels' order; [] when it has nothing."""
        return [hit.url for hit in self.search_hits(keyword, deadline, orientation)]

    def search_hits(self, keyword: str, deadline: float, orientation: str = "all") -> list[Hit]:
        if not self.key:
            raise PexelsError("key", "Chưa cấu hình PEXELS_API_KEY nên không tìm được ảnh Pexels")
        shape = {"vertical": "portrait", "square": "square"}.get(orientation)
        query = urllib.parse.urlencode(
            {"query": keyword, "locale": "vi-VN", "per_page": RESULTS} | ({"orientation": shape} if shape else {})
        )
        try:
            body = stock.fetch(
                f"{self.api_url}/v1/search?{query}",
                self._remaining(deadline),
                MAX_SEARCH_BYTES,
                headers={"Authorization": self.key},
            )
        except stock.HttpStatusError as err:
            if err.status in (401, 403):
                raise PexelsError("key", "Key Pexels không hợp lệ") from None
            if err.status == 429:
                raise PexelsError("rate_limit", "Pexels đang giới hạn lượt tìm, thử lại sau") from None
            if err.status >= 500:
                raise PexelsError("server", f"Pexels đang lỗi (HTTP {err.status}), thử lại sau") from None
            return []  # Pexels refuses some keywords: nothing found.
        except stock.TooLargeError:
            raise PexelsError("server", "Pexels trả kết quả quá lớn, thử lại sau") from None
        except stock.NetworkError as err:
            raise self._network_error(err) from None
        try:
            hits = []
            for item in json.loads(body)["photos"][:RESULTS]:
                if not isinstance(item, dict) or not isinstance(item.get("src"), dict):
                    continue
                src = item["src"]
                # large2x is big enough for a 1080-wide render and far lighter than the original.
                url = src.get("large2x") or src.get("original") or src.get("large")
                preview = src.get("small") or src.get("tiny") or src.get("medium")
                if isinstance(url, str) and isinstance(preview, str) and self._allowed(url) and self._allowed(preview):
                    # large2x fits inside 1880 × 1300.
                    size = delivered_size(item.get("width"), item.get("height"), 1880, 1300)
                    hits.append(Hit(url, preview, *size))
        except (ValueError, KeyError, TypeError):
            raise PexelsError("server", "Pexels trả kết quả không đọc được, thử lại sau") from None
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
        """For "Tìm ảnh khác": the next usable photo over the keywords, as Pixabay.find_photo."""
        return find_photo(self, keywords, deadline, avoid, after, orientation)

    def _allowed(self, url: str) -> bool:
        # Addresses come from the network: only https, or the configured (test) server itself.
        return url.startswith("https://") or url.startswith(self._api_origin)

    def _network_error(self, err: Exception) -> PexelsError:
        return PexelsError("network", f"Pexels không phản hồi kịp hoặc mất kết nối ({err})")

    def _remaining(self, deadline: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise PexelsError("network", "Pexels không phản hồi kịp, thử lại sau")
        return remaining
