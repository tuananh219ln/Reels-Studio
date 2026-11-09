"""Unsplash photos for scenes: high-quality photos, Asian dishes and ingredients among them.

Brief docs/specs/them-nguon-anh-stock. The Access Key is pasted on Cài đặt › Nguồn tư liệu (source_keys) or set in
the server's .env, and sent in a header, never in an address, so no log keeps it. The free ("demo") plan allows 50
calls an hour for the whole team; Unsplash answers 403 "Rate Limit Exceeded" once they are used up, which must not
read as a bad key. Unsplash's API terms ask for its download endpoint to be called whenever a photo is used: done
once the chosen photo is downloaded, and a failure there never stops the photo.
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
PHOTO_WIDTH = 1080  # Unsplash's "regular" size: the frame's width
MISSING_KEY = "Chưa cấu hình key Unsplash (Cài đặt › Nguồn tư liệu) nên không tìm được ảnh Unsplash"


class UnsplashError(Exception):
    """Unsplash could not be used at all; `kind` (key, rate_limit, server, network) mirrors PixabayError."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


class Unsplash:
    def __init__(self, key: str | None = None, api_url: str | None = None):
        self.key = config.read_env("UNSPLASH_ACCESS_KEY") if key is None else key
        self.api_url = api_url or config.unsplash_api_url()
        parts = urllib.parse.urlsplit(self.api_url)
        self._api_origin = f"{parts.scheme}://{parts.netloc}/"
        # download_location of the results last searched, called once the photo is used.
        self._downloads: dict[str, str] = {}

    def search(self, keyword: str, deadline: float, orientation: str = "all") -> list[str]:
        """Photo URLs for the keyword in Unsplash's order; [] when it has nothing."""
        return [hit.url for hit in self.search_hits(keyword, deadline, orientation)]

    def search_hits(self, keyword: str, deadline: float, orientation: str = "all") -> list[Hit]:
        if not self.key:
            raise UnsplashError("key", MISSING_KEY)
        shape = {"vertical": "portrait", "square": "squarish"}.get(orientation)
        query = urllib.parse.urlencode(
            {"query": keyword, "per_page": RESULTS, "content_filter": "high"}
            | ({"orientation": shape} if shape else {})
        )
        try:
            body = stock.fetch(
                f"{self.api_url}/search/photos?{query}",
                self._remaining(deadline),
                MAX_SEARCH_BYTES,
                headers=self._headers(),
            )
        except stock.HttpStatusError as err:
            if err.status == 429 or (err.status == 403 and "rate limit" in err.body.lower()):
                raise UnsplashError(
                    "rate_limit",
                    "Hết lượt Unsplash trong giờ này (gói miễn phí 50 lượt/giờ cho cả nhóm): thử lại sau hoặc chọn "
                    "nguồn khác",
                ) from None
            if err.status in (401, 403):
                raise UnsplashError("key", "Key Unsplash không hợp lệ") from None
            if err.status >= 500:
                raise UnsplashError("server", f"Unsplash đang lỗi (HTTP {err.status}), thử lại sau") from None
            return []
        except stock.TooLargeError:
            raise UnsplashError("server", "Unsplash trả kết quả quá lớn, thử lại sau") from None
        except stock.NetworkError as err:
            raise self._network_error(err) from None
        try:
            hits = []
            for item in json.loads(body)["results"][:RESULTS]:
                if not isinstance(item, dict) or not isinstance(item.get("urls"), dict):
                    continue
                urls = item["urls"]
                url, preview = urls.get("regular"), urls.get("small") or urls.get("thumb")
                if isinstance(url, str) and isinstance(preview, str) and self._allowed(url) and self._allowed(preview):
                    hits.append(
                        Hit(url, preview, *delivered_size(item.get("width"), item.get("height"), PHOTO_WIDTH, 10**6))
                    )
                    links = item.get("links") if isinstance(item.get("links"), dict) else {}
                    location = links.get("download_location")
                    if isinstance(location, str) and self._allowed(location):
                        self._downloads[url] = location
        except (ValueError, KeyError, TypeError):
            raise UnsplashError("server", "Unsplash trả kết quả không đọc được, thử lại sau") from None
        return [hit for hit in hits if fits(hit, orientation)]

    def download(self, url: str, deadline: float) -> Photo | None:
        """The photo, or None when the file is too large or not a usable JPG/PNG/WebP."""
        try:
            data = stock.fetch(url, self._remaining(deadline), stock.MAX_IMAGE_BYTES)
        except (stock.TooLargeError, stock.HttpStatusError):
            return None
        except stock.NetworkError as err:
            raise self._network_error(err) from None
        try:
            photo = Photo(url, data, image_extension(data))
        except UploadRejected:
            return None
        self._track_download(url, deadline)
        return photo

    def _track_download(self, url: str, deadline: float) -> None:
        """Unsplash's terms: tell it a photo was used. Best effort: the photo is kept whatever it answers."""
        location = self._downloads.get(url)
        if not location:
            return
        try:
            stock.fetch(location, max(min(deadline - time.monotonic(), 5.0), 1.0), 64 * 1024, headers=self._headers())
        except (stock.HttpStatusError, stock.TooLargeError, stock.NetworkError):
            pass

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

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Client-ID {self.key}", "Accept-Version": "v1"}

    def _allowed(self, url: str) -> bool:
        # Addresses come from the network: only https, or the configured (test) server itself.
        return url.startswith("https://") or url.startswith(self._api_origin)

    def _network_error(self, err: Exception) -> UnsplashError:
        return UnsplashError("network", f"Unsplash không phản hồi kịp hoặc mất kết nối ({err})")

    def _remaining(self, deadline: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise UnsplashError("network", "Unsplash không phản hồi kịp, thử lại sau")
        return remaining
