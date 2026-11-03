"""Posting reels to the team's Facebook Pages (Reels Publishing API) and reading them back, called only from the worker
and from "Kết nối Fanpage"."""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import config

REQUEST_TIMEOUT = 60
UPLOAD_TIMEOUT = 300
# The worker reads numbers between jobs, so a slow Facebook must not hold the queue for long.
INSIGHTS_TIMEOUT = 10
POLL_SECONDS = 5
PROCESSING_SECONDS = 180
FAILED_STATUSES = {"error", "expired", "upload_failed"}
TOKEN_ERRORS = {102, 190}
PERMISSION_ERRORS = {10, 200}
RATE_LIMIT_ERRORS = {4, 17, 32, 613}
# _http_error's message for a refusal it cannot name; it speaks of posting, so a read replaces it.
REFUSED = "Facebook từ chối đăng video này"


class FacebookError(Exception):
    """`message` is shown to members, `detail` is diagnostic."""

    def __init__(self, message: str, detail: str = "", status: int = 0, code: int | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail
        self.status = status
        self.code = code  # Facebook's error code, when its answer had one


@dataclass(frozen=True)
class Page:
    id: str
    token: str = field(repr=False)


def reel_url(video_id: str) -> str:
    return f"https://www.facebook.com/reel/{video_id}"


def _send(request: urllib.request.Request, timeout: float) -> dict:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as err:
        raise _http_error(err.code, err.read(4000).decode("utf-8", "replace")) from None
    # URLError, timeouts, connection resets and SSL errors are all OSError subclasses.
    except OSError as err:
        raise FacebookError("Không kết nối được Facebook, kiểm tra mạng rồi thử lại", str(err)) from None
    except ValueError as err:
        raise FacebookError("Facebook trả dữ liệu không đọc được, thử lại sau", str(err)) from None


def _http_error(status: int, body: str) -> FacebookError:
    detail = f"HTTP {status}: {body}"
    try:
        error = json.loads(body)["error"]
        code, subcode = error["code"], error.get("error_subcode")
    except (ValueError, KeyError, TypeError, AttributeError):
        code, subcode = None, None
    if code == 100 and subcode == 33:
        message = "Facebook không cho token này truy cập Page, hãy dán token mới trong Kết nối Fanpage"
    elif code in TOKEN_ERRORS:
        message = "Token Facebook hết hạn hoặc không hợp lệ, hãy dán token mới trong Kết nối Fanpage"
    elif code in PERMISSION_ERRORS:
        message = "Token Facebook chưa có quyền đăng lên Page này"
    elif code in RATE_LIMIT_ERRORS or status == 429:
        message = "Facebook đang giới hạn lượt đăng, thử lại sau"
    elif status >= 500:
        message = f"Facebook đang lỗi (HTTP {status}), thử lại sau"
    else:
        message = REFUSED
    return FacebookError(message, detail, status, code)


def _publish_call(page: Page, fields: dict[str, str]) -> dict:
    body = urllib.parse.urlencode({**fields, "access_token": page.token}).encode()
    url = f"{config.facebook_api_url()}/{urllib.parse.quote(page.id, safe='')}/video_reels"
    return _send(urllib.request.Request(url, data=body, method="POST"), REQUEST_TIMEOUT)


def _read(page: Page, path: str, **fields: str) -> dict:
    query = urllib.parse.urlencode({**fields, "access_token": page.token})
    return _send(urllib.request.Request(f"{config.facebook_api_url()}/{path}?{query}"), REQUEST_TIMEOUT)


def managed_pages(token: str) -> list[dict]:
    """The Pages a pasted token reaches, each with the Page's own token, the only kind that can post. Facebook gives
    those to whoever manages a Page; a Page's token reaches only that Page."""
    page = Page("", token)
    me = _read(page, "me", fields="id,name")
    try:
        accounts = _read(page, "me/accounts", fields="id,name,access_token,tasks", limit="100").get("data", [])
    except FacebookError:
        return [{"id": str(me.get("id")), "name": str(me.get("name", "")), "token": token, "can_post": True}]
    return [
        {
            "id": str(account.get("id")),
            "name": str(account.get("name", "")),
            "token": account.get("access_token", ""),
            "can_post": "CREATE_CONTENT" in account.get("tasks", []) and bool(account.get("access_token")),
        }
        for account in accounts
    ]


def page_info(page: Page) -> dict:
    """The Page's `name` and `followers` (None when Facebook leaves it out), read with the Page's own token: the
    worker's check that the token still works (fanpages.check). Reading the Page needs `pages_read_engagement`."""
    query = urllib.parse.urlencode({"fields": "name,followers_count", "access_token": page.token})
    url = f"{config.facebook_api_url()}/{urllib.parse.quote(page.id, safe='')}?{query}"
    try:
        reply = _send(urllib.request.Request(url), INSIGHTS_TIMEOUT)
    except FacebookError as err:
        if err.code in PERMISSION_ERRORS:
            raise FacebookError(
                "Token Facebook chưa có quyền đọc Page (pages_read_engagement), hãy dán token mới trong Kết nối Fanpage",
                err.detail,
                err.status,
                err.code,
            ) from None
        if err.message == REFUSED:
            raise FacebookError("Facebook không cho đọc Page này", err.detail, err.status, err.code) from None
        raise
    return {"name": str(reply.get("name") or ""), "followers": _count(reply.get("followers_count"))}


# Page Insights metrics by the name the app keeps them under; daily values. Meta replaced `page_impressions` with
# `page_media_view` and `page_impressions_unique` with `page_total_media_view_unique` (Nov 2025). This is the one place
# that knows the names, so a change on Meta's side is fixed here alone.
PAGE_METRICS = {
    "views": "page_media_view",
    "reach": "page_total_media_view_unique",
    "engagements": "page_post_engagements",
}


def page_insights(page: Page, since: datetime, until: datetime) -> tuple[dict, list[str]]:
    """The Page's daily numbers between `since` and `until`, as {day: {"views", "reach", "engagements"}}, and what
    went wrong for the metrics Facebook refused. Each metric is asked alone, so one Meta drops does not lose the
    others. Facebook's day is the Page's own (Pacific time for most), given by the end of the day. Needs
    `read_insights`."""
    days: dict = {}
    problems: list[str] = []
    for key, metric in PAGE_METRICS.items():
        query = urllib.parse.urlencode(
            {
                "metric": metric,
                "period": "day",
                "since": str(int(since.timestamp())),
                "until": str(int(until.timestamp())),
                "access_token": page.token,
            }
        )
        url = f"{config.facebook_api_url()}/{urllib.parse.quote(page.id, safe='')}/insights?{query}"
        try:
            reply = _send(urllib.request.Request(url), INSIGHTS_TIMEOUT)
        except FacebookError as err:
            if err.code in PERMISSION_ERRORS:
                problems.append("Token chưa có quyền đọc số liệu Page (read_insights)")
            elif err.code in TOKEN_ERRORS or err.code in RATE_LIMIT_ERRORS:
                problems.append(err.message)
            else:
                problems.append(f"Facebook không trả số liệu {metric}")
            continue
        for item in reply.get("data") or []:
            for value in item.get("values") or [] if isinstance(item, dict) else []:
                end = _time(value.get("end_time"))
                day = (end - timedelta(days=1)).date()
                days.setdefault(day, {"views": None, "reach": None, "engagements": None})[key] = _count(
                    value.get("value")
                )
    return days, list(dict.fromkeys(problems))


def start_upload(page: Page) -> tuple[str, str]:
    """A new upload session: Facebook's id of the reel, and where its file goes."""
    reply = _publish_call(page, {"upload_phase": "start"})
    try:
        return str(reply["video_id"]), reply["upload_url"]
    except (KeyError, TypeError):
        raise FacebookError("Facebook trả dữ liệu không đọc được, thử lại sau", str(reply)) from None


def upload(page: Page, upload_url: str, path: Path) -> None:
    size = str(path.stat().st_size)
    with path.open("rb") as file:
        request = urllib.request.Request(
            upload_url,
            data=file,
            method="POST",
            headers={
                "Authorization": f"OAuth {page.token}",
                "offset": "0",
                "file_size": size,
                "Content-Length": size,
                "Content-Type": "application/octet-stream",
            },
        )
        _send(request, UPLOAD_TIMEOUT)


def finish(page: Page, video_id: str, description: str, scheduled_at: datetime | None) -> None:
    """Publish now, or let Facebook publish at `scheduled_at`."""
    fields = {"upload_phase": "finish", "video_id": video_id, "description": description, "video_state": "PUBLISHED"}
    if scheduled_at is not None:
        fields |= {"video_state": "SCHEDULED", "scheduled_publish_time": str(int(scheduled_at.timestamp()))}
    _publish_call(page, fields)


def set_cover(page: Page, video_id: str, image: bytes) -> None:
    """The reel's cover (Video Thumbnails, `is_preferred`), a JPEG of at most 10 MB. Without one Facebook picks a
    frame itself, often one from the middle of the video."""
    boundary = uuid.uuid4().hex
    fields = {"is_preferred": "true", "access_token": page.token}
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        for name, value in fields.items()
    ]
    parts += [
        f'--{boundary}\r\nContent-Disposition: form-data; name="source"; filename="cover.jpg"\r\n'
        "Content-Type: image/jpeg\r\n\r\n".encode(),
        image,
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    url = f"{config.facebook_api_url()}/{urllib.parse.quote(video_id, safe='')}/thumbnails"
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    _send(urllib.request.Request(url, data=b"".join(parts), method="POST", headers=headers), REQUEST_TIMEOUT)


# Video Insights metrics of a reel (lifetime). "Views" is every play, replays included, as Meta counts a reel's plays.
REEL_METRICS = ("fb_reels_total_plays", "post_video_social_actions", "post_video_likes_by_reaction_type")


def reel_insights(page: Page, video_id: str) -> dict[str, int | None]:
    """The reel's `views`, `shares`, `comments` and `reactions`, each None when Facebook leaves it out. This is the one
    place that knows Meta's metric names and shapes, so a change on their side is fixed here alone. Needs the
    `read_insights` permission on the Page's token."""
    query = urllib.parse.urlencode({"metric": ",".join(REEL_METRICS), "period": "lifetime", "access_token": page.token})
    url = f"{config.facebook_api_url()}/{urllib.parse.quote(video_id, safe='')}/video_insights?{query}"
    try:
        reply = _send(urllib.request.Request(url), INSIGHTS_TIMEOUT)
    except FacebookError as err:
        if err.code in PERMISSION_ERRORS:
            raise FacebookError(
                "Token Facebook chưa có quyền đọc chỉ số (read_insights), hãy dán token mới trong Kết nối Fanpage",
                err.detail,
                err.status,
                err.code,
            ) from None
        if err.status == 404 or err.code == 100:
            raise FacebookError(
                "Facebook không còn reel này hoặc chưa có chỉ số", err.detail, err.status, err.code
            ) from None
        raise
    values = {}
    for item in reply.get("data") or []:
        if isinstance(item, dict) and item.get("values"):
            values[item.get("name")] = item["values"][-1].get("value")
    social = values.get("post_video_social_actions")
    return {
        "views": _count(values.get("fb_reels_total_plays")),
        "shares": _part(social, "share"),
        "comments": _part(social, "comment"),
        "reactions": _count(values.get("post_video_likes_by_reaction_type")),
    }


def _count(value: object) -> int | None:
    """A number, or the sum of a breakdown such as reactions by type."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return int(value)
    if isinstance(value, dict):
        parts = [part for part in value.values() if isinstance(part, int | float) and not isinstance(part, bool)]
        return int(sum(parts)) if parts else None
    return None


def _part(value: object, key: str) -> int | None:
    """One entry of a breakdown such as {"SHARE": 3, "COMMENT": 5}; Meta's case is not documented."""
    if not isinstance(value, dict):
        return None
    for name, part in value.items():
        if str(name).lower() == key:
            return _count(part)
    return 0


def _comment_error(err: FacebookError) -> FacebookError:
    if err.code in PERMISSION_ERRORS:
        return FacebookError(
            "Token Facebook chưa có quyền bình luận (pages_manage_engagement), hãy dán token mới trong Kết nối Fanpage",
            err.detail,
            err.status,
            err.code,
        )
    if err.message == REFUSED:
        return FacebookError("Facebook từ chối bình luận này", err.detail, err.status, err.code)
    return err


def post_comment(page: Page, object_id: str, message: str) -> str:
    """Comment as the Page on a reel, or reply to a comment; returns the new comment's id. Needs
    `pages_manage_engagement`."""
    body = urllib.parse.urlencode({"message": message, "access_token": page.token}).encode()
    url = f"{config.facebook_api_url()}/{urllib.parse.quote(object_id, safe='')}/comments"
    try:
        reply = _send(urllib.request.Request(url, data=body, method="POST"), REQUEST_TIMEOUT)
    except FacebookError as err:
        raise _comment_error(err) from None
    return str(reply.get("id") or "")


def edit_comment(page: Page, comment_id: str, message: str) -> None:
    body = urllib.parse.urlencode({"message": message, "access_token": page.token}).encode()
    url = f"{config.facebook_api_url()}/{urllib.parse.quote(comment_id, safe='')}"
    try:
        _send(urllib.request.Request(url, data=body, method="POST"), REQUEST_TIMEOUT)
    except FacebookError as err:
        raise _comment_error(err) from None


def page_comment(page: Page, object_id: str, message: str) -> str | None:
    """The id of a comment the Page already wrote under the reel with this message, if any: an attempt whose answer was
    lost may still have reached Facebook. Reads the newest 100 comments; needs `pages_read_user_content`."""
    query = urllib.parse.urlencode(
        {"fields": "id,message,from", "order": "reverse_chronological", "limit": "100", "access_token": page.token}
    )
    url = f"{config.facebook_api_url()}/{urllib.parse.quote(object_id, safe='')}/comments?{query}"
    try:
        reply = _send(urllib.request.Request(url), REQUEST_TIMEOUT)
    except FacebookError as err:
        raise _comment_error(err) from None
    for comment in reply.get("data") or []:
        author = comment.get("from") or {}
        if str(author.get("id")) == page.id and (comment.get("message") or "").strip() == message.strip():
            return str(comment.get("id"))
    return None


def visitor_comments(page: Page, object_id: str) -> list[dict]:
    """The newest 100 top-level comments under the reel that are not the Page's own: each `id`, `message`, `author`,
    `created` (UTC), `hidden`, and `answered` when the Page replied under it. Needs `pages_read_user_content`."""
    query = urllib.parse.urlencode(
        {
            "fields": "id,message,from{id,name},created_time,is_hidden,comments.limit(25){from{id}}",
            "filter": "toplevel",
            "order": "reverse_chronological",
            "limit": "100",
            "access_token": page.token,
        }
    )
    url = f"{config.facebook_api_url()}/{urllib.parse.quote(object_id, safe='')}/comments?{query}"
    try:
        reply = _send(urllib.request.Request(url), INSIGHTS_TIMEOUT)
    except FacebookError as err:
        if err.code in PERMISSION_ERRORS:
            raise FacebookError(
                "Token Facebook chưa có quyền đọc bình luận (pages_read_user_content), hãy dán token mới trong Kết nối "
                "Fanpage",
                err.detail,
                err.status,
                err.code,
            ) from None
        if err.status == 404 or err.code == 100:
            raise FacebookError("Facebook không còn reel này", err.detail, err.status, err.code) from None
        raise
    found = []
    for item in reply.get("data") or []:
        author = item.get("from") or {}
        if not isinstance(item, dict) or not item.get("id") or str(author.get("id")) == page.id:
            continue
        replies = (item.get("comments") or {}).get("data") or []
        found.append(
            {
                "id": str(item["id"]),
                "message": str(item.get("message") or ""),
                "author": str(author.get("name") or ""),
                "created": _time(item.get("created_time")),
                "hidden": bool(item.get("is_hidden")),
                "answered": any(str((one.get("from") or {}).get("id")) == page.id for one in replies),
            }
        )
    return found


def _time(value: object) -> datetime:
    """Graph API's "2026-11-03T07:00:00+0000"; now when it is missing or unreadable."""
    try:
        return datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%S%z").astimezone(UTC)
    except ValueError:
        return datetime.now(UTC)


def hide_comment(page: Page, comment_id: str) -> None:
    body = urllib.parse.urlencode({"is_hidden": "true", "access_token": page.token}).encode()
    url = f"{config.facebook_api_url()}/{urllib.parse.quote(comment_id, safe='')}"
    try:
        _send(urllib.request.Request(url, data=body, method="POST"), REQUEST_TIMEOUT)
    except FacebookError as err:
        raise _comment_error(err) from None


def reel_status(page: Page, video_id: str) -> dict | None:
    """Facebook's status of the reel, or None when it no longer has the reel. Any other failure raises: a reel
    whose state is unknown may be live, so it must never be taken for a lost one and posted again."""
    query = urllib.parse.urlencode({"fields": "status", "access_token": page.token})
    url = f"{config.facebook_api_url()}/{urllib.parse.quote(video_id, safe='')}?{query}"
    try:
        reply = _send(urllib.request.Request(url), REQUEST_TIMEOUT)
    except FacebookError as err:
        if err.status == 404:
            return None
        raise FacebookError(
            f"Không đọc được trạng thái reel, hãy xem Page trước khi thử lại: {err.message}", err.detail
        ) from None
    if not reply.get("status"):
        raise FacebookError("Không đọc được trạng thái reel, hãy xem Page trước khi thử lại", str(reply))
    return reply["status"]


def delete_reel(page: Page, video_id: str) -> None:
    """Take a reel off the Page, live or waiting for its time. A reel Facebook no longer has is already gone."""
    query = urllib.parse.urlencode({"access_token": page.token})
    url = f"{config.facebook_api_url()}/{urllib.parse.quote(video_id, safe='')}?{query}"
    try:
        reply = _send(urllib.request.Request(url, method="DELETE"), REQUEST_TIMEOUT)
    except FacebookError as err:
        if err.status == 404:
            return
        if 400 <= err.status < 500 and err.status != 429:
            raise FacebookError(
                "Facebook từ chối xóa bài này, hãy kiểm tra token trong Kết nối Fanpage hoặc xóa trong Meta Business Suite",
                err.detail,
            ) from None
        raise
    if not reply.get("success"):
        raise FacebookError("Facebook chưa xóa bài này, hãy xem Page rồi thử lại", str(reply))


def is_live(status: dict) -> bool:
    """Published, or accepted for the scheduled time."""
    return status.get("publishing_phase", {}).get("publish_status") in ("published", "scheduled")


def is_scheduled(status: dict) -> bool:
    return status.get("publishing_phase", {}).get("publish_status") == "scheduled"


def scheduled_time(status: dict) -> datetime | None:
    moment = status.get("publishing_phase", {}).get("publish_time")
    return datetime.fromtimestamp(moment, UTC) if isinstance(moment, (int, float)) else None


def _phases(status: dict) -> list[dict]:
    return [status.get(phase, {}) for phase in ("processing_phase", "publishing_phase")]


def is_failed(status: dict) -> bool:
    # Meta's example of a refused reel has an `error` in a phase that is still "not_started".
    return status.get("video_status") in FAILED_STATUSES or any(
        phase.get("status") == "error" or phase.get("error") for phase in _phases(status)
    )


def is_busy(status: dict) -> bool:
    """Facebook is working on the reel, so it may still go live by itself."""
    return not is_failed(status) and any(phase.get("status") == "in_progress" for phase in _phases(status))


def is_uploaded(status: dict) -> bool:
    return not is_failed(status) and status.get("uploading_phase", {}).get("status") in ("complete", "completed")


def wait_until_live(page: Page, video_id: str) -> dict:
    deadline = time.monotonic() + PROCESSING_SECONDS
    while True:
        status = reel_status(page, video_id)
        if status is None:
            raise FacebookError("Facebook không còn giữ video này, hãy bấm Thử lại")
        if is_live(status):
            return status
        if is_failed(status):
            raise FacebookError("Facebook không xử lý được video này", json.dumps(status, ensure_ascii=False))
        if time.monotonic() >= deadline:
            raise FacebookError(
                "Facebook xử lý video quá lâu, hãy xem Page rồi bấm Thử lại", json.dumps(status, ensure_ascii=False)
            )
        time.sleep(POLL_SECONDS)
