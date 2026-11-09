"""Wikimedia Commons photos for scenes: Vietnamese dishes photographed by Vietnamese users, searched in Vietnamese.

Brief docs/specs/them-nguon-anh-stock. No key: the MediaWiki API answers anonymous calls, asking only for a
User-Agent that names the app and a way to reach its owners. Unlike Openverse (public domain only), every free
licence is taken, by the owner's choice of 2026-11-09: a photo whose licence asks for credit (CC BY, CC BY-SA...)
carries it in `Photo.credit`, which the scene keeps and shows as a warning until another photo replaces it.
"""

import html
import json
import re
import time
import urllib.parse
from collections.abc import Iterable

from reels_render import stock

from . import config
from .pixabay import Hit, Photo, find_photo, fits
from .uploads import UploadRejected, image_extension

MAX_SEARCH_BYTES = 4 * 1024 * 1024
RESULTS = 20  # the picker grid shows them all
# A standard thumbnail step of Wikimedia's: wide enough for the 1080-wide frame, far lighter than most originals.
PHOTO_WIDTH = 1280
PREVIEW_WIDTH = 330
MIMES = {"image/jpeg", "image/png", "image/webp"}
# Wikimedia's User-Agent policy: the app's name and where to reach its owners.
USER_AGENT = "ReelsStudio/1.0 (https://github.com/tuananh219ln/Reels-Studio; stock photo search)"
SOURCE_NAME = "Wikimedia Commons"
_FREE = re.compile(r"^(public domain|pd\b|cc0|cc-zero|no restrictions)", re.IGNORECASE)


class WikimediaError(Exception):
    """Wikimedia could not be used at all; `kind` (rate_limit, server, network) mirrors PixabayError."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


def credit_of(info: dict) -> dict | None:
    """What the scene must credit for this photo, or None when its licence asks for nothing."""
    meta = info.get("extmetadata") if isinstance(info.get("extmetadata"), dict) else {}

    def value(name: str) -> str:
        entry = meta.get(name)
        raw = entry.get("value") if isinstance(entry, dict) else ""
        return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", str(raw or ""))).split())

    license_name = value("LicenseShortName")
    needs_credit = value("AttributionRequired").lower() == "true" or not _FREE.match(license_name)
    if not needs_credit:
        return None
    author = value("Artist")[:200] or "không rõ tác giả"
    license_name = license_name[:100] or "giấy phép trên trang ảnh"
    page = info.get("descriptionurl") if isinstance(info.get("descriptionurl"), str) else ""
    return {
        "license": license_name,
        "author": author,
        "page": page,
        "source": SOURCE_NAME,
        "line": f"Ảnh: {author}, {license_name} ({SOURCE_NAME})",
    }


class Wikimedia:
    def __init__(self, api_url: str | None = None):
        self.api_url = api_url or config.wikimedia_api_url()
        parts = urllib.parse.urlsplit(self.api_url)
        self._api_origin = f"{parts.scheme}://{parts.netloc}/"
        # Credits of the results last searched, so the photo downloaded from them carries its own.
        self._credits: dict[str, dict | None] = {}

    def search(self, keyword: str, deadline: float, orientation: str = "all") -> list[str]:
        """Photo URLs for the keyword in Wikimedia's order; [] when nothing matches."""
        return [hit.url for hit in self.search_hits(keyword, deadline, orientation)]

    def search_hits(self, keyword: str, deadline: float, orientation: str = "all") -> list[Hit]:
        query = urllib.parse.urlencode(
            {
                "action": "query",
                "format": "json",
                "formatversion": "2",
                "generator": "search",
                "gsrnamespace": "6",  # File:
                "gsrsearch": f"{keyword} filetype:bitmap",
                "gsrlimit": RESULTS,
                "prop": "imageinfo",
                "iiprop": "url|size|mime|extmetadata",
                "iiurlwidth": PHOTO_WIDTH,
                "iiextmetadatafilter": "LicenseShortName|Artist|AttributionRequired",
            }
        )
        try:
            body = stock.fetch(
                f"{self.api_url}?{query}",
                self._remaining(deadline),
                MAX_SEARCH_BYTES,
                headers={"User-Agent": USER_AGENT},
            )
        except stock.HttpStatusError as err:
            if err.status == 429:
                raise WikimediaError("rate_limit", "Wikimedia đang giới hạn lượt tìm, thử lại sau") from None
            if err.status >= 500:
                raise WikimediaError("server", f"Wikimedia đang lỗi (HTTP {err.status}), thử lại sau") from None
            return []
        except stock.TooLargeError:
            raise WikimediaError("server", "Wikimedia trả kết quả quá lớn, thử lại sau") from None
        except stock.NetworkError as err:
            raise self._network_error(err) from None
        try:
            payload = json.loads(body)
            pages = (payload.get("query") or {}).get("pages") or []
            hits = []
            for page in sorted((p for p in pages if isinstance(p, dict)), key=lambda p: p.get("index") or 0):
                infos = page.get("imageinfo")
                info = infos[0] if isinstance(infos, list) and infos and isinstance(infos[0], dict) else None
                if info is None or info.get("mime") not in MIMES:
                    continue
                url = info.get("thumburl") or info.get("url")
                if not isinstance(url, str) or not self._allowed(url):
                    continue
                width = info.get("thumbwidth") or info.get("width")
                height = info.get("thumbheight") or info.get("height")
                # Same file, smaller step: thumbnails are named by their width.
                preview = url.replace(f"/{PHOTO_WIDTH}px-", f"/{PREVIEW_WIDTH}px-")
                credit = credit_of(info)
                hit = Hit(
                    url,
                    preview,
                    width if isinstance(width, int) else None,
                    height if isinstance(height, int) else None,
                    credit,
                )
                hits.append(hit)
                self._credits[url] = credit
        except (ValueError, KeyError, TypeError, AttributeError):
            raise WikimediaError("server", "Wikimedia trả kết quả không đọc được, thử lại sau") from None
        return [hit for hit in hits if fits(hit, orientation)]

    def download(self, url: str, deadline: float) -> Photo | None:
        """The photo with its credit, or None when the file is too large or not a usable JPG/PNG/WebP."""
        try:
            data = stock.fetch(
                url, self._remaining(deadline), stock.MAX_IMAGE_BYTES, headers={"User-Agent": USER_AGENT}
            )
        except (stock.TooLargeError, stock.HttpStatusError):
            return None
        except stock.NetworkError as err:
            raise self._network_error(err) from None
        try:
            return Photo(url, data, image_extension(data), self._credits.get(url))
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

    def _network_error(self, err: Exception) -> WikimediaError:
        return WikimediaError("network", f"Wikimedia không phản hồi kịp hoặc mất kết nối ({err})")

    def _remaining(self, deadline: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise WikimediaError("network", "Wikimedia không phản hồi kịp, thử lại sau")
        return remaining
