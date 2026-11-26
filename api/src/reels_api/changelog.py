""" "Có gì mới" for the assistants (docs/decisions/2026-11-26-whats-new.md): the changes the web shows, read from the
`changelog.json` the deploy wrote next to the web app. The api keeps no copy: the file is the only list."""

from datetime import datetime
from urllib.parse import urlsplit

import httpx

from . import config
from .errors import ApiError

KIND_LABEL = {"feature": "Tính năng mới", "fix": "Sửa lỗi", "improvement": "Cải thiện"}


def url() -> str:
    """CHANGELOG_URL, else the web's own `/changelog.json` (the origin of MCP_PUBLIC_URL); empty when neither is set."""
    explicit = config.read_env("CHANGELOG_URL")
    if explicit:
        return explicit
    public = urlsplit(config.read_env("MCP_PUBLIC_URL"))
    return f"{public.scheme}://{public.netloc}/changelog.json" if public.scheme and public.netloc else ""


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def read(since: datetime | None = None, limit: int = 20) -> dict:
    """The newest changes (merged after `since` when given), each with its kind in words and the in-app links."""
    where = url()
    if not where:
        raise ApiError(404, "changelog_unavailable", "Chưa có danh sách “Có gì mới” (app chưa được cập nhật lần nào)")
    try:
        response = httpx.get(where, params={"t": int(datetime.now().timestamp())}, timeout=10)
    except httpx.HTTPError:
        raise ApiError(502, "changelog_unreachable", "Không đọc được danh sách “Có gì mới”, thử lại sau") from None
    if response.status_code == 404:
        raise ApiError(404, "changelog_unavailable", "Chưa có danh sách “Có gì mới” (app chưa được cập nhật lần nào)")
    if response.status_code != 200:
        raise ApiError(502, "changelog_unreachable", "Không đọc được danh sách “Có gì mới”, thử lại sau")
    entries = response.json().get("entries") or []
    if since is not None:
        cutoff = since if since.tzinfo else since.astimezone()
        entries = [entry for entry in entries if _time(entry["merged_at"]) > cutoff]
    return {
        "changes": [
            {
                "title": entry["title"],
                "summary": entry.get("summary", ""),
                "kind": KIND_LABEL.get(entry.get("kind"), entry.get("kind")),
                "merged_at": entry["merged_at"],
                "deployed_at": entry.get("deployed_at"),
                "by": entry.get("author") or None,
                "screens": entry.get("pages", []),
                "guides": entry.get("guides", []),
            }
            for entry in entries[: max(1, min(limit, 60))]
        ]
    }
