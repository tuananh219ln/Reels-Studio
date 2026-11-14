"""YouTube Data API v3, read with the team's key (`YOUTUBE_API_KEY`): a Short's views, likes, comments, time and length,
50 ids per call (one quota unit). An id missing from the answer is a video YouTube no longer shows (deleted or
private)."""

import re
from datetime import datetime

import httpx

from . import config

TIMEOUT = 10.0
BATCH = 50
_DURATION = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?$")


class YouTubeError(Exception):
    """A call that did not answer (network, 5xx, quota): never read as "removed"."""


def enabled() -> bool:
    return config.youtube_api_key() is not None


def videos(ids: list[str]) -> dict[str, dict]:
    """The items YouTube returns for `ids` (at most BATCH), by id."""
    if not ids:
        return {}
    try:
        response = httpx.get(
            f"{config.youtube_api_url()}/videos",
            params={
                "part": "snippet,statistics,contentDetails",
                "id": ",".join(ids[:BATCH]),
                "key": config.youtube_api_key(),
            },
            timeout=TIMEOUT,
        )
    except httpx.HTTPError as err:
        raise YouTubeError(f"Không gọi được YouTube: {err.__class__.__name__}") from None
    if response.status_code != 200:
        reason = ""
        try:
            reason = response.json()["error"]["errors"][0]["reason"]
        except (ValueError, KeyError, IndexError, TypeError):
            pass
        if reason in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"):
            raise YouTubeError("YouTube hết quota hôm nay, sẽ đọc lại sau")
        raise YouTubeError(f"YouTube trả lỗi {response.status_code} {reason}".strip())
    return {item["id"]: item for item in response.json().get("items", []) if isinstance(item, dict) and "id" in item}


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def numbers(item: dict) -> dict:
    stats = item.get("statistics") or {}
    return {
        "views": _int(stats.get("viewCount")),
        "likes": _int(stats.get("likeCount")),
        "comments": _int(stats.get("commentCount")),
        "shares": None,
    }


def published_at(item: dict) -> datetime | None:
    value = (item.get("snippet") or {}).get("publishedAt")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None
    except ValueError:
        return None


def duration_seconds(item: dict) -> float | None:
    match = _DURATION.match((item.get("contentDetails") or {}).get("duration") or "")
    if not match:
        return None
    days, hours, minutes, seconds = (float(part) if part else 0.0 for part in match.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds
