"""Posting Reels to the Instagram account linked to a Facebook Page (Instagram Content Publishing API, through Facebook
Login), with the Page's own token the app already keeps. Called only from the worker (ig_publish.py, the Page check).

A Reel goes in three calls: a container (`POST /{ig-user-id}/media`, `upload_type=resumable`), the file sent to
`rupload.facebook.com` by container id, then `POST /{ig-user-id}/media_publish` once Instagram has processed it.
Instagram has no draft and no scheduled time through the API: what is published is public at once.
"""

import json
import logging
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from . import config, crypto
from .facebook import (
    PERMISSION_ERRORS,
    RATE_LIMIT_ERRORS,
    REFUSED,
    REQUEST_TIMEOUT,
    UPLOAD_REFUSED,
    UPLOAD_TIMEOUT,
    FacebookError,
    Page,
    _send,
)

log = logging.getLogger("reels_api.instagram")

MAX_CAPTION = 2200
MAX_HASHTAGS = 30
# What Instagram's `status_code` of a container says.
FINISHED = "FINISHED"
IN_PROGRESS = "IN_PROGRESS"
PUBLISHED = "PUBLISHED"
FAILED = {"ERROR", "EXPIRED"}
NO_PERMISSION = "Token Page chưa có quyền đăng Instagram, hãy dán lại token có instagram_content_publish"
NOT_LINKED = "Page này chưa liên kết tài khoản Instagram Business"


@dataclass(frozen=True)
class Account:
    id: str
    username: str


def _error(err: FacebookError) -> FacebookError:
    """Facebook's messages speak of the Page: say it of Instagram where it differs."""
    if err.code in PERMISSION_ERRORS:
        return FacebookError(NO_PERMISSION, err.detail, err.status, err.code, err.subcode)
    if err.code in RATE_LIMIT_ERRORS or err.status == 429:
        message = "Instagram đang giới hạn số bài đăng, thử lại sau"
        return FacebookError(message, err.detail, err.status, err.code, err.subcode)
    if err.message == REFUSED:
        return FacebookError("Instagram từ chối đăng video này", err.detail, err.status, err.code, err.subcode)
    if err.message.startswith(UPLOAD_REFUSED):
        message = err.message.replace("Facebook", "Instagram", 1)
        return FacebookError(message, err.detail, err.status, err.code, err.subcode)
    return err


def _get(page: Page, path: str, **fields: str) -> dict:
    query = urllib.parse.urlencode({**fields, "access_token": page.token})
    url = f"{config.facebook_api_url()}/{path}?{query}"
    try:
        return _send(urllib.request.Request(url), REQUEST_TIMEOUT)
    except FacebookError as err:
        raise _error(err) from None


def _post(page: Page, path: str, **fields: str) -> dict:
    body = urllib.parse.urlencode({**fields, "access_token": page.token}).encode()
    url = f"{config.facebook_api_url()}/{path}"
    try:
        return _send(urllib.request.Request(url, data=body, method="POST"), REQUEST_TIMEOUT)
    except FacebookError as err:
        raise _error(err) from None


def _id(reply: dict) -> str:
    value = reply.get("id") if isinstance(reply, dict) else None
    if not value:
        raise FacebookError("Instagram trả dữ liệu không đọc được, thử lại sau", str(reply))
    return str(value)


def meta_reason(err: FacebookError) -> str:
    """Meta's own words in a refusal ("(#10) Requires instagram_basic"), cut short; "" when there are none."""
    _, _, body = err.detail.partition(": ")
    try:
        message = json.loads(body)["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return ""
    return str(message)[:200]


LINK_FIELDS = ("instagram_business_account", "connected_instagram_account")


def account_of(page: Page) -> Account | None:
    """The Instagram Business/Creator account linked to the Page, or None when there is none.

    Its id alone is read from the Page first, one field at a time (`instagram_business_account`, else
    `connected_instagram_account`, which Meta fills for some links): asking for the account's username in the same call
    fails the whole read when the token lacks `instagram_basic`, and the id is all posting needs. The username is then
    read on its own and left empty when refused."""
    path = urllib.parse.quote(page.id, safe="")
    account_id = None
    for field in LINK_FIELDS:
        try:
            linked = _get(page, path, fields=field).get(field)
        except FacebookError:
            if field == LINK_FIELDS[0]:
                raise
            break
        if isinstance(linked, dict) and linked.get("id"):
            account_id = str(linked["id"])
            break
    if account_id is None:
        return None
    try:
        username = str(_get(page, urllib.parse.quote(account_id, safe=""), fields="username").get("username") or "")
    except FacebookError as err:
        log.warning("Instagram account %s: username not read: %s %s", account_id, err.message, err.detail)
        username = ""
    return Account(account_id, username[:100])


def caption(text: str) -> str:
    """The caption as Instagram takes it: at most 30 hashtags (the later ones dropped) and 2,200 characters."""
    words, tags = [], 0
    for line in text.split("\n"):
        kept = []
        for word in line.split(" "):
            if word.startswith("#") and len(word) > 1:
                tags += 1
                if tags > MAX_HASHTAGS:
                    continue
            kept.append(word)
        words.append(" ".join(kept).rstrip())
    return "\n".join(words).strip()[:MAX_CAPTION]


LINK_SECONDS = 6 * 3600  # how long the link Instagram fetches the MP4 from stays valid


def video_link(post_id: int) -> str:
    """The public link Instagram fetches a post's MP4 from ("" when no public address is set): it carries its own
    permission, a sealed post id good for LINK_SECONDS, and serves that post's file only (routes_instagram)."""
    base = config.instagram_video_base_url()
    return f"{base}/api/instagram/media/{crypto.seal(str(post_id))}/video.mp4" if base else ""


def link_post_id(token: str) -> int | None:
    value = crypto.unseal(token, LINK_SECONDS)
    return int(value) if value is not None and value.isdigit() else None


def create_container(page: Page, ig_user_id: str, text: str, video_url: str = "") -> tuple[str, str]:
    """A Reel container: its id (what the publish is sent to) and the `uri` Meta gave to send the file to ("" when it
    gave none). With a `video_url` Instagram fetches the MP4 itself; without, it waits for the file by resumable
    upload."""
    how = {"video_url": video_url} if video_url else {"upload_type": "resumable"}
    reply = _post(
        page,
        f"{urllib.parse.quote(ig_user_id, safe='')}/media",
        media_type="REELS",
        **how,
        caption=text,
        share_to_feed="true",
    )
    uri = reply.get("uri") if isinstance(reply, dict) else None
    return _id(reply), uri if isinstance(uri, str) else ""


def upload_target(container_id: str, uri: str = "") -> str:
    """Where the file goes: the `uri` Meta returned with the container, when it is on the upload server's own host (the
    token goes with it, so no other host is trusted); else the address built from the container id."""
    base = config.instagram_upload_url()
    parsed = urllib.parse.urlparse(uri)
    if (
        uri
        and parsed.scheme == urllib.parse.urlparse(base).scheme
        and parsed.netloc == urllib.parse.urlparse(base).netloc
    ):
        return uri
    return f"{base}/{urllib.parse.quote(container_id, safe='')}"


def upload(page: Page, container_id: str, path: Path, uri: str = "") -> None:
    size = str(path.stat().st_size)
    target = upload_target(container_id, uri)
    log.info("Instagram upload: container %s, %s bytes, to %s", container_id, size, target)
    with path.open("rb") as file:
        request = urllib.request.Request(
            target,
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
        try:
            _send(request, UPLOAD_TIMEOUT)
        except FacebookError as err:
            log.error("Instagram upload of container %s failed: %s | %s", container_id, err.message, err.detail)
            raise _error(err) from None


def container_status(page: Page, container_id: str) -> tuple[str, str]:
    """Instagram's `status_code` of the container (FINISHED, IN_PROGRESS, PUBLISHED, ERROR, EXPIRED) and its `status`
    text, which says why on an error."""
    reply = _get(page, urllib.parse.quote(container_id, safe=""), fields="status_code,status")
    return str(reply.get("status_code") or ""), str(reply.get("status") or "")


def publish(page: Page, ig_user_id: str, container_id: str) -> str:
    """Publish the processed container; returns the media id."""
    return _id(_post(page, f"{urllib.parse.quote(ig_user_id, safe='')}/media_publish", creation_id=container_id))


def permalink(page: Page, media_id: str) -> str | None:
    reply = _get(page, urllib.parse.quote(media_id, safe=""), fields="permalink")
    link = reply.get("permalink")
    return link if isinstance(link, str) and link.startswith("https://") else None


def recent_media(page: Page, ig_user_id: str) -> list[dict]:
    """The account's newest media, {id, caption, permalink, timestamp}: where a Reel whose publish answer was lost is
    looked for."""
    reply = _get(
        page,
        f"{urllib.parse.quote(ig_user_id, safe='')}/media",
        fields="id,caption,permalink,timestamp",
        limit="25",
    )
    data = reply.get("data")
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


# --- The account's numbers (Instagram Insights; needs `instagram_manage_insights` on the Page's token) ---

NO_INSIGHTS_PERMISSION = "Token chưa có quyền đọc số liệu Instagram (instagram_manage_insights)"
# One number for a whole window, asked a day at a time: `views`, `reach` and `total_interactions` give the account's
# total over `since`..`until` (`metric_type=total_value`), so a day's number is the total of a one-day window.
DAY_METRICS = {"views": "views", "reach": "reach", "interactions": "total_interactions"}


def _count(value) -> int | None:
    return int(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _day_total(page: Page, ig_user_id: str, metric: str, start: datetime, end: datetime) -> int | None:
    """The account's `metric` over [start, end), or None when Instagram gives no number for it."""
    reply = _get(
        page,
        f"{urllib.parse.quote(ig_user_id, safe='')}/insights",
        metric=metric,
        metric_type="total_value",
        period="day",
        since=str(int(start.timestamp())),
        until=str(int(end.timestamp())),
    )
    for item in reply.get("data") or []:
        if isinstance(item, dict) and item.get("name") == metric:
            return _count((item.get("total_value") or {}).get("value"))
    return None


def account_insights(
    page: Page, ig_user_id: str, days: list[date], zone
) -> tuple[dict[date, dict], int | None, list[str]]:
    """The linked account's numbers for each of `days` (days in `zone`, Vietnam time): {day: {"views", "reach",
    "interactions", "follows"}}, its followers now, and what went wrong. A metric Instagram refuses is left None and
    named in the problems, so one the account lacks does not lose the others; a token without
    `instagram_manage_insights` stops at the first call. `follows` is `follower_count`, the new followers of each day.
    Instagram's data lags up to 48 hours: the last days are rewritten on each check."""
    numbers: dict[date, dict] = {
        day: {"views": None, "reach": None, "interactions": None, "follows": None} for day in days
    }
    problems: list[str] = []
    for key, metric in DAY_METRICS.items():
        for day in days:
            start = datetime(day.year, day.month, day.day, tzinfo=zone)
            try:
                numbers[day][key] = _day_total(page, ig_user_id, metric, start, start + timedelta(days=1))
            except FacebookError as err:
                if err.code in PERMISSION_ERRORS:
                    return numbers, None, [NO_INSIGHTS_PERMISSION]
                problems.append(
                    err.message if err.code in RATE_LIMIT_ERRORS else f"Instagram không trả số liệu {metric}"
                )
                break
    first = datetime(days[0].year, days[0].month, days[0].day, tzinfo=zone)
    last = datetime(days[-1].year, days[-1].month, days[-1].day, tzinfo=zone) + timedelta(days=1)
    try:
        reply = _get(
            page,
            f"{urllib.parse.quote(ig_user_id, safe='')}/insights",
            metric="follower_count",
            period="day",
            since=str(int(first.timestamp())),
            until=str(int(last.timestamp())),
        )
        for item in reply.get("data") or []:
            for value in (item.get("values") or []) if isinstance(item, dict) else []:
                ended = value.get("end_time")
                if not isinstance(ended, str):
                    continue
                day = (
                    (
                        datetime.fromisoformat(ended.replace("Z", "+00:00").replace("+0000", "+00:00"))
                        - timedelta(days=1)
                    )
                    .astimezone(zone)
                    .date()
                )
                if day in numbers:
                    numbers[day]["follows"] = _count(value.get("value"))
    except FacebookError as err:
        problems.append(err.message if err.code in RATE_LIMIT_ERRORS else "Instagram không trả số liệu follower_count")
    followers = None
    try:
        followers = _count(
            _get(page, urllib.parse.quote(ig_user_id, safe=""), fields="followers_count").get("followers_count")
        )
    except FacebookError as err:
        log.warning("Instagram account %s: followers not read: %s %s", ig_user_id, err.message, err.detail)
    return numbers, followers, list(dict.fromkeys(problems))


# A Reel's numbers (Media Insights): the app's own key -> Instagram's metric. `views` replaced `plays` and `impressions`
# in 2025; `saved` is saves; `ig_reels_avg_watch_time` is milliseconds. All go in one call.
MEDIA_METRICS = {
    "views": "views",
    "reach": "reach",
    "likes": "likes",
    "comments": "comments",
    "shares": "shares",
    "saves": "saved",
    "interactions": "total_interactions",
    "avg_watch_ms": "ig_reels_avg_watch_time",
}


def media_insights(page: Page, media_id: str) -> dict:
    """The Reel's numbers by the app's keys (MEDIA_METRICS), each None when Instagram leaves it out. This is the one
    place that knows Meta's names for them. Needs `instagram_manage_insights`. Meta fails the whole call with (#100) when
    it refuses one metric (a photo has no watch time), so after a (#100) each is asked alone and only the refused ones
    come back None; a Reel that every metric refuses is gone."""
    path = f"{urllib.parse.quote(media_id, safe='')}/insights"
    names = list(MEDIA_METRICS.values())
    try:
        data = _get(page, path, metric=",".join(names)).get("data") or []
    except FacebookError as err:
        if err.code != 100:
            raise _insights_error(err) from None
        data = []
        for name in names:
            try:
                data += _get(page, path, metric=name).get("data") or []
            except FacebookError as one:
                if one.code != 100:
                    raise _insights_error(one) from None
        if not data:
            raise _insights_error(err) from None
    found: dict = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        values = item.get("values")
        value = values[-1].get("value") if values else (item.get("total_value") or {}).get("value")
        found[item.get("name")] = value
    return {key: _count(found.get(name)) for key, name in MEDIA_METRICS.items()}


def _insights_error(err: FacebookError) -> FacebookError:
    if err.code in PERMISSION_ERRORS:
        return FacebookError(NO_INSIGHTS_PERMISSION, err.detail, err.status, err.code, err.subcode)
    return err


# The followers' audience: one call per breakdown. Instagram gives it only to an account with 100 or more followers.
AUDIENCE_BREAKDOWNS = ("gender", "age", "city")
NO_AUDIENCE = "Instagram chỉ cho xem đối tượng khi tài khoản có từ 100 người theo dõi"


def audience(page: Page, ig_user_id: str) -> tuple[dict, str | None]:
    """The followers' share (percent) by gender, age range and city: {"gender": {"F": 72.0}, "age": {"25-34": 45.0},
    "city": {"Ho Chi Minh City, Vietnam": 38.0}}, each breakdown missing when Instagram refused it, and what went wrong.
    Needs `instagram_manage_insights`."""
    found: dict = {}
    problem = None
    for breakdown in AUDIENCE_BREAKDOWNS:
        try:
            reply = _get(
                page,
                f"{urllib.parse.quote(ig_user_id, safe='')}/insights",
                metric="follower_demographics",
                period="lifetime",
                metric_type="total_value",
                breakdown=breakdown,
            )
        except FacebookError as err:
            if err.code in PERMISSION_ERRORS:
                return {}, NO_INSIGHTS_PERMISSION
            problem = err.message if err.code in RATE_LIMIT_ERRORS else NO_AUDIENCE
            continue
        results: list = []
        for item in reply.get("data") or []:
            for part in ((item.get("total_value") or {}).get("breakdowns") or []) if isinstance(item, dict) else []:
                results += part.get("results") or []
        counts = {}
        for row in results:
            keys, value = row.get("dimension_values") or [], _count(row.get("value"))
            if keys and value is not None:
                counts[str(keys[0])] = value
        total = sum(counts.values())
        if total > 0:
            shares = {key: round(value * 100 / total, 1) for key, value in counts.items()}
            found[breakdown] = dict(sorted(shares.items(), key=lambda item: item[1], reverse=True)[:10])
    if not found and problem is None:
        problem = NO_AUDIENCE
    return found, problem
