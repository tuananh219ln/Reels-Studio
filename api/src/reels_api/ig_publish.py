"""The `ig_publish` job: one Instagram Reel (a Publication, platform instagram) posted to the Instagram account linked
to its Facebook Page, with the Page's own token (instagram.py). Runs only in the worker. A post set for later waits as
`scheduled` until `jobs.queue_instagram_posts` starts this job at its time: Instagram has no scheduled time of its own.

Never posted twice: `finish_sent_at` is saved (and committed) before Instagram is asked to publish. A retry of a post
that has it first asks Instagram about that container, and finds the Reel among the account's newest media when the
answer was lost. Before that point nothing is public, so a retry simply starts a new container (an unused one expires
on Instagram's side after a day).
"""

import logging
import time
from datetime import datetime, timedelta

from sqlalchemy.orm import Session as DbSession

from . import fanpages, instagram
from .facebook import FacebookError, Page
from .models import Fanpage, Job, Publication, Video
from .sessions import now
from .storage import DirectoryStorage

log = logging.getLogger(__name__)

POLL_SECONDS = 5
PROCESSING_SECONDS = 300
# How far before `finish_sent_at` a Reel found on the account may have been published (clocks differ a little).
CLOCK_SLACK = timedelta(minutes=2)


class PublishFailed(Exception):
    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.message = message
        self.detail = detail


def run(db: DbSession, job: Job, storage: DirectoryStorage) -> None:
    post = db.get(Publication, job.publication_id) if job.publication_id else None
    if post is None or post.platform != "instagram" or post.video_id is None:
        raise PublishFailed("Không tìm thấy bài Instagram của job này")
    if post.status == "published":
        return
    if post.status != "pending":
        raise PublishFailed("Bài Instagram này đã hủy, hãy đăng lại")
    video = db.get(Video, post.video_id)
    row = db.get(Fanpage, post.fanpage_id) if post.fanpage_id else None
    if row is None or not row.instagram_user_id:
        raise PublishFailed(instagram.NOT_LINKED)
    key = post.remote_mp4_key or video.mp4_key
    if not key or not storage.exists(key):
        raise PublishFailed("Không thấy file MP4 trong storage, hãy render lại rồi đăng")
    try:
        page = fanpages.load_page(db, row.id)
        media_id = _resume(page, row.instagram_user_id, post) if post.finish_sent_at else None
        if media_id is None:
            media_id = _post(db, page, row.instagram_user_id, post, storage, key)
    except FacebookError as err:
        raise PublishFailed(err.message, err.detail) from None
    post.external_id, post.status, post.published_at = media_id, "published", now()
    try:
        post.post_url = instagram.permalink(page, media_id)
    except FacebookError as err:
        log.warning("Instagram media %s: no permalink: %s %s", media_id, err.message, err.detail)
    db.commit()
    log.info("Job %s posted video %s to Instagram as %s", job.id, video.id, media_id)


def _post(db: DbSession, page: Page, ig_user_id: str, post: Publication, storage: DirectoryStorage, key: str) -> str:
    """A new container, its file, and the publish."""
    post.finish_sent_at = None
    post.remote_mp4_key = key
    db.commit()
    link = instagram.video_link(post.id)
    post.remote_id, upload_uri = instagram.create_container(page, ig_user_id, post.post_text or "", link)
    db.commit()
    if link:
        log.info("Instagram container %s of post %s fetches its MP4 from our link", post.remote_id, post.id)
    else:
        instagram.upload(page, post.remote_id, storage.path(key), upload_uri)
    _wait(page, post.remote_id)
    return _publish(db, page, ig_user_id, post)


def _resume(page: Page, ig_user_id: str, post: Publication) -> str | None:
    """A post whose publish was asked for before: its media id when Instagram published it, None to start over."""
    code, status = instagram.container_status(page, post.remote_id) if post.remote_id else ("", "")
    if code == instagram.PUBLISHED:
        found = _find(page, ig_user_id, post)
        if found is None:
            raise PublishFailed(
                "Instagram báo đã đăng nhưng chưa thấy bài trên tài khoản, hãy kiểm tra trên Instagram rồi thử lại",
                f"container {post.remote_id}",
            )
        return found
    log.info("Instagram container %s of post %s is %s (%s): posting again", post.remote_id, post.id, code, status)
    return None


def _find(page: Page, ig_user_id: str, post: Publication) -> str | None:
    since = post.finish_sent_at - CLOCK_SLACK
    want = (post.post_text or "").strip()
    for item in instagram.recent_media(page, ig_user_id):
        try:
            at = datetime.strptime(str(item.get("timestamp")), "%Y-%m-%dT%H:%M:%S%z")
        except ValueError:
            continue
        if at >= since and str(item.get("caption") or "").strip() == want and item.get("id"):
            return str(item["id"])
    return None


def _wait(page: Page, container_id: str) -> None:
    deadline = time.monotonic() + PROCESSING_SECONDS
    while True:
        code, status = instagram.container_status(page, container_id)
        if code == instagram.FINISHED:
            return
        if code in instagram.FAILED:
            raise PublishFailed(f"Instagram không xử lý được video ({code})", status)
        if time.monotonic() >= deadline:
            raise PublishFailed("Instagram xử lý video quá lâu, hãy bấm Thử lại sau ít phút", f"{code} {status}")
        time.sleep(POLL_SECONDS)


def _publish(db: DbSession, page: Page, ig_user_id: str, post: Publication) -> str:
    # Saved before asking: from here the Reel may go public even if the answer is lost.
    post.finish_sent_at = now()
    db.commit()
    return instagram.publish(page, ig_user_id, post.remote_id)
