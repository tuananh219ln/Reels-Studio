"""Openverse photos for scenes: openly licensed images (Flickr, Wikimedia and more) in the picker.

Only CC0 and public-domain-marked works are used: the channel earns money and the app shows no
attribution anywhere, so anything carrying conditions stays out. The license filter runs in the
query and again here on every result, in case a source mislabels its own work.

No key is required. When OPENVERSE_CLIENT_ID and OPENVERSE_CLIENT_SECRET are configured, the
client exchanges them for an OAuth access token (cached in memory until it expires) for the
registered rate limits; if that exchange fails for any reason, the search quietly goes anonymous
instead of breaking.
"""

import json
import threading
import time
import urllib.parse
from collections.abc import Iterable

from reels_render import stock

from . import config
from .pixabay import Hit, Photo, find_photo
from .uploads import UploadRejected, image_extension

MAX_SEARCH_BYTES = 2 * 1024 * 1024
RESULTS = 20  # the picker grid shows them all; also the anonymous page-size cap
LICENSES = {"cc0", "pdm"}  # the only licenses the picker may use; see docs/decisions.md
TOKEN_EXPIRY_MARGIN = 60  # seconds shaved off a token's life so it is never used right at expiry

# Access tokens by credential pair, shared by every client in this process: a picker search
# builds a fresh client each time, so an instance cache would re-ask for a token on every search.
_tokens: dict[str, tuple[str, float]] = {}
_tokens_lock = threading.Lock()


class OpenverseError(Exception):
    """Openverse could not be used at all; `kind` (rate_limit, server, network) mirrors PixabayError."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


class Openverse:
    def __init__(self, api_url: str | None = None, client_id: str | None = None, client_secret: str | None = None):
        self.api_url = api_url or config.openverse_api_url()
        self.client_id = config.openverse_client_id() if client_id is None else client_id
        self.client_secret = config.openverse_client_secret() if client_secret is None else client_secret
        parts = urllib.parse.urlsplit(self.api_url)
        self._api_origin = f"{parts.scheme}://{parts.netloc}/"

    def search(self, keyword: str, deadline: float) -> list[str]:
        """Original image URLs for the keyword; [] when nothing public-domain matches."""
        return [hit.url for hit in self.search_hits(keyword, deadline)]

    def search_hits(self, keyword: str, deadline: float) -> list[Hit]:
        query = urllib.parse.urlencode(
            {
                "q": keyword,
                "license": ",".join(sorted(LICENSES)),
                "license_type": "commercial",
                "page_size": RESULTS,
            }
        )
        token = self._access_token(deadline)
        headers = {"Authorization": f"Bearer {token}"} if token else None
        try:
            body = stock.fetch(
                f"{self.api_url}/v1/images/?{query}", self._remaining(deadline), MAX_SEARCH_BYTES, headers=headers
            )
        except stock.HttpStatusError as err:
            if err.status == 429:
                raise OpenverseError("rate_limit", "Openverse đang giới hạn lượt tìm, thử lại sau") from None
            if err.status >= 500:
                raise OpenverseError("server", f"Openverse đang lỗi (HTTP {err.status}), thử lại sau") from None
            return []  # Openverse refuses some keywords: nothing found.
        except stock.TooLargeError:
            raise OpenverseError("server", "Openverse trả kết quả quá lớn, thử lại sau") from None
        except stock.NetworkError as err:
            raise self._network_error(err) from None
        try:
            hits = []
            for item in json.loads(body)["results"][:RESULTS]:
                if not isinstance(item, dict):
                    continue
                url, preview = item.get("url"), item.get("thumbnail")
                if (
                    str(item.get("license") or "").strip().lower() in LICENSES
                    and isinstance(url, str)
                    and isinstance(preview, str)
                    and self._allowed(url)
                    and self._allowed(preview)
                ):
                    hits.append(Hit(url, preview))
        except (ValueError, KeyError, TypeError):
            raise OpenverseError("server", "Openverse trả kết quả không đọc được, thử lại sau") from None
        return hits

    def _access_token(self, deadline: float) -> str | None:
        """A registered access token, or None to search anonymously.

        Anonymous is also the fallback for every failure here (wrong credentials, Openverse
        down): the picker must keep working, just at the anonymous rate limit.
        """
        if not (self.client_id and self.client_secret):
            return None
        cache_key = f"{self.api_url}\n{self.client_id}\n{self.client_secret}"
        with _tokens_lock:
            cached = _tokens.get(cache_key)
        if cached and cached[1] > time.monotonic():
            return cached[0]
        form = urllib.parse.urlencode(
            {"grant_type": "client_credentials", "client_id": self.client_id, "client_secret": self.client_secret}
        ).encode()
        try:
            body = stock.fetch(
                f"{self.api_url}/v1/auth_tokens/token/",
                self._remaining(deadline),
                MAX_SEARCH_BYTES,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data=form,
            )
            payload = json.loads(body)
            token = payload["access_token"]
            if not isinstance(token, str):
                return None
            expires_in = float(payload.get("expires_in") or 3600)
        except (stock.HttpStatusError, stock.TooLargeError, stock.NetworkError, ValueError, KeyError, TypeError):
            return None
        with _tokens_lock:
            _tokens[cache_key] = (token, time.monotonic() + max(expires_in - TOKEN_EXPIRY_MARGIN, 0))
        return token

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
        self, keywords: Iterable[str], deadline: float, avoid: Iterable[str] = (), after: str | None = None
    ) -> Photo | None:
        """For "Tìm ảnh khác": the next usable photo over the keywords, as Pixabay.find_photo."""
        return find_photo(self, keywords, deadline, avoid, after)

    def _allowed(self, url: str) -> bool:
        # Addresses come from the network: only https, or the configured (test) server itself.
        return url.startswith("https://") or url.startswith(self._api_origin)

    def _network_error(self, err: Exception) -> OpenverseError:
        return OpenverseError("network", f"Openverse không phản hồi kịp hoặc mất kết nối ({err})")

    def _remaining(self, deadline: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise OpenverseError("network", "Openverse không phản hồi kịp, thử lại sau")
        return remaining
