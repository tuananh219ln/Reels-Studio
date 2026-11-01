"""Stock video clips for scenes, from Pexels Videos and Pixabay Videos, chosen in the picker's "Video" mode.

A chosen clip is downloaded by the api and stored with its scene exactly like an uploaded clip, so the render
only ever uses what the member saw. The browser names the clip by its id; the api searches again and fetches
only a file that search returned.
"""

import json
import urllib.parse
from dataclasses import dataclass

from reels_render import stock

from . import config
from .clips import MAX_CLIP_BYTES

MAX_SEARCH_BYTES = 4 * 1024 * 1024
RESULTS = 20
# The file closest to the frame's width is picked; bigger only costs download time.
TARGET_WIDTH = 1080
SOURCES = {"pixabay": "Pixabay", "pexels": "Pexels"}


class ClipSearchError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class ClipHit:
    id: str
    preview: str  # a still for the grid, shown straight from the source
    url: str  # the MP4 file the api downloads when it is chosen
    seconds: float
    width: int
    height: int


def _get(url: str, deadline_seconds: float, headers: dict | None = None) -> dict:
    try:
        body = stock.fetch(url, deadline_seconds, MAX_SEARCH_BYTES, headers=headers)
        data = json.loads(body)
    except stock.HttpStatusError as err:
        if err.status in (400, 401, 403):
            raise ClipSearchError("Key của nguồn video không hợp lệ") from None
        if err.status == 429:
            raise ClipSearchError("Nguồn video đang giới hạn lượt tìm, thử lại sau") from None
        raise ClipSearchError(f"Nguồn video đang lỗi (HTTP {err.status}), thử lại sau") from None
    except (stock.NetworkError, stock.TooLargeError, ValueError):
        raise ClipSearchError("Không kết nối được nguồn video, thử lại sau") from None
    if not isinstance(data, dict):
        raise ClipSearchError("Nguồn video trả kết quả không đọc được")
    return data


def _closest(files: list[tuple[str, int, int]]) -> tuple[str, int, int] | None:
    usable = [item for item in files if item[0] and item[1] > 0 and item[2] > 0]
    return min(usable, key=lambda item: abs(item[1] - TARGET_WIDTH), default=None)


def search(source: str, keyword: str, timeout: float, key: str) -> list[ClipHit]:
    """`key` is the source's API key (source_keys)."""
    if source not in SOURCES:
        raise ClipSearchError("Nguồn video không hợp lệ")
    if not key:
        raise ClipSearchError(f"Chưa cấu hình key {SOURCES[source]} nên không tìm được video")
    hits: list[ClipHit] = []
    if source == "pexels":
        query = urllib.parse.urlencode({"query": keyword, "orientation": "portrait", "per_page": RESULTS})
        data = _get(f"{config.pexels_api_url()}/videos/search?{query}", timeout, {"Authorization": key})
        for item in data.get("videos") or []:
            files = [
                (str(f.get("link") or ""), int(f.get("width") or 0), int(f.get("height") or 0))
                for f in item.get("video_files") or []
                if f.get("file_type") == "video/mp4"
            ]
            best = _closest(files)
            if best and item.get("id") is not None:
                hits.append(
                    ClipHit(
                        str(item["id"]),
                        str(item.get("image") or ""),
                        best[0],
                        float(item.get("duration") or 0),
                        best[1],
                        best[2],
                    )
                )
    else:
        query = urllib.parse.urlencode({"key": key, "q": keyword, "per_page": RESULTS, "safesearch": "true"})
        data = _get(f"{config.pixabay_api_url().rstrip('/')}/videos/?{query}", timeout)
        for item in data.get("hits") or []:
            sizes = item.get("videos") or {}
            files = [
                (str(size.get("url") or ""), int(size.get("width") or 0), int(size.get("height") or 0))
                for size in sizes.values()
                if isinstance(size, dict)
            ]
            best = _closest(files)
            still = next(
                (size.get("thumbnail") for size in sizes.values() if isinstance(size, dict) and size.get("thumbnail")),
                "",
            )
            if best and item.get("id") is not None:
                hits.append(
                    ClipHit(
                        str(item["id"]), str(still or ""), best[0], float(item.get("duration") or 0), best[1], best[2]
                    )
                )
    return hits


def download(hit: ClipHit, timeout: float) -> bytes:
    try:
        return stock.fetch(hit.url, timeout, MAX_CLIP_BYTES)
    except stock.TooLargeError:
        raise ClipSearchError("Video này quá 50 MB, hãy chọn video khác") from None
    except (stock.HttpStatusError, stock.NetworkError):
        raise ClipSearchError("Không tải được video này, hãy chọn video khác") from None
