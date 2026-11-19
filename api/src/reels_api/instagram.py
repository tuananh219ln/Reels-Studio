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
from pathlib import Path

from . import config
from .facebook import (
    PERMISSION_ERRORS,
    RATE_LIMIT_ERRORS,
    REFUSED,
    REQUEST_TIMEOUT,
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


def create_container(page: Page, ig_user_id: str, text: str) -> str:
    """A Reel container waiting for its file; its id is what the file and the publish are sent to."""
    reply = _post(
        page,
        f"{urllib.parse.quote(ig_user_id, safe='')}/media",
        media_type="REELS",
        upload_type="resumable",
        caption=text,
        share_to_feed="true",
    )
    return _id(reply)


def upload(page: Page, container_id: str, path: Path) -> None:
    size = str(path.stat().st_size)
    with path.open("rb") as file:
        request = urllib.request.Request(
            f"{config.instagram_upload_url()}/{urllib.parse.quote(container_id, safe='')}",
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
