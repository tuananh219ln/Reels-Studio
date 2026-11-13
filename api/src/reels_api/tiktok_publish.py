"""The `tiktok_publish` job: one TikTok post (a Publication, platform tiktok) sent through TikTok's Content Posting API
with the member's own connection, as a draft to their TikTok inbox or posted directly. Runs only in the worker.

Never posted twice: TikTok's publish_id is saved (and committed) before the upload, so "Thử lại" first asks TikTok
about that very post and only starts over when TikTok holds no finished upload of it. A rate limit fails the job; it is
never retried in a loop.
"""

import json
import logging
import time

from sqlalchemy.orm import Session as DbSession

from . import tiktok, tiktok_connections
from .models import Job, KnowledgeTopic, Publication, Video
from .sessions import now
from .storage import DirectoryStorage

log = logging.getLogger(__name__)

POLL_SECONDS = 10
WAIT_SECONDS = 300


class PublishFailed(Exception):
    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.message = message
        self.detail = detail


def run(db: DbSession, job: Job, storage: DirectoryStorage) -> None:
    post = db.get(Publication, job.publication_id) if job.publication_id else None
    if post is None or post.platform != "tiktok" or post.video_id is None:
        raise PublishFailed("Không tìm thấy bài TikTok của job này")
    if post.status == "published":
        return
    if post.status != "pending":
        raise PublishFailed("Bài TikTok này đã hủy, hãy bấm Đăng lên TikTok lại")
    video = db.get(Video, post.video_id)
    connection = tiktok_connections.of_account(db, post.affiliate_account_id) if post.affiliate_account_id else None
    if connection is None or connection.owner_id != post.created_by_id:
        raise PublishFailed("Tài khoản TikTok chưa kết nối, hãy bấm Kết nối TikTok trong Cài đặt › Tài khoản affiliate")
    try:
        token = tiktok_connections.access_token(db, connection)
        if post.remote_id and _carry_on(db, token, post, storage):
            _wait(db, token, post)
            return
        upload, path, chunk, chunks = _start(db, token, video, post, storage)
        tiktok.upload_chunks(upload.upload_url, path, chunk, chunks)
        _wait(db, token, post)
    except tiktok.TikTokError as err:
        raise PublishFailed(err.message, err.detail) from None
    log.info("Job %s sent video %s to TikTok (%s) as %s", job.id, video.id, post.publish_mode, post.remote_id)


def _carry_on(db: DbSession, token: str, post: Publication, storage: DirectoryStorage) -> bool:
    """A retry of a post TikTok was already given: True when TikTok holds it (done or still processing it), so this
    job only waits for it; False when it is gone, failed, or its upload never finished, and a new one is started."""
    try:
        found = tiktok.publish_status(token, post.remote_id)
    except tiktok.TikTokError as err:
        if err.code != "invalid_publish_id":
            raise
        found = None
    status = found.get("status") if found else None
    uploaded = int(found.get("uploaded_bytes") or 0) if found else 0
    unfinished_upload = status == "PROCESSING_UPLOAD" and uploaded < _size_sent(post, storage)
    if status is not None and status != "FAILED" and not unfinished_upload:
        return True
    log.info("TikTok post %s of publication %s is %s: starting over", post.remote_id, post.id, status or "gone")
    post.remote_id = None
    db.commit()
    return False


def _size_sent(post: Publication, storage: DirectoryStorage) -> int:
    """The size of the MP4 sent as `remote_id`; 0 when it is no longer stored, which counts as an unfinished upload."""
    if not post.remote_mp4_key or not storage.exists(post.remote_mp4_key):
        return 0
    return storage.path(post.remote_mp4_key).stat().st_size


def _start(db: DbSession, token: str, video: Video, post: Publication, storage: DirectoryStorage):
    if not video.mp4_key or not storage.exists(video.mp4_key):
        raise PublishFailed("Không thấy file MP4 trong storage, hãy render lại rồi đăng")
    path = storage.path(video.mp4_key)
    size = path.stat().st_size
    chunk, chunks = tiktok.chunk_plan(size)
    if post.publish_mode == "direct":
        info = tiktok.creator_info(token)
        level = post.privacy_level or "SELF_ONLY"
        if level not in info.privacy_level_options:
            allowed = ", ".join(info.privacy_level_options) or "không có mức nào"
            raise PublishFailed(
                f"TikTok không cho tài khoản này đăng ở mức riêng tư {level}; các mức được phép: {allowed}",
                json.dumps({"privacy_level_options": info.privacy_level_options}),
            )
        topic = db.get(KnowledgeTopic, video.knowledge_topic_id)
        post_info = {
            "title": tiktok.post_title(video.caption, topic.name if topic else None),
            "privacy_level": level,
            "disable_comment": False,
            "disable_duet": False,
            "disable_stitch": False,
            # Every video of the app is made with AI: TikTok asks for the label, and labelled posts are not held back.
            "is_aigc": True,
        }
        upload = tiktok.init_direct(token, post_info, size, chunk, chunks)
    else:
        # A draft carries no caption: the member finishes it in TikTok's app (caption, cart, AI label).
        upload = tiktok.init_inbox(token, size, chunk, chunks)
    # Saved before the upload, so a retry asks TikTok about this very post instead of sending a second one.
    post.remote_id, post.remote_mp4_key = upload.publish_id, video.mp4_key
    db.commit()
    return upload, path, chunk, chunks


def _wait(db: DbSession, token: str, post: Publication) -> None:
    """Until TikTok says the draft reached the inbox, or the post is published; WAIT_SECONDS at most. A post still
    processing then stays pending with its publish_id, for "Thử lại" to go on with."""
    done = tiktok.DONE_STATUSES.get(post.publish_mode or "draft", tiktok.DONE_STATUSES["draft"])
    deadline = time.monotonic() + WAIT_SECONDS
    while True:
        found = tiktok.publish_status(token, post.remote_id)
        status = found.get("status")
        if status in done:
            post.status, post.published_at = "published", now()
            db.commit()
            return
        if status == "FAILED":
            raise PublishFailed(
                f"TikTok không đăng được video này ({found.get('fail_reason') or 'không rõ lý do'}), hãy bấm Thử lại",
                json.dumps(found, ensure_ascii=False),
            )
        if time.monotonic() >= deadline:
            raise PublishFailed(
                "TikTok xử lý video quá lâu, hãy mở TikTok kiểm tra rồi bấm Thử lại",
                json.dumps(found, ensure_ascii=False),
            )
        time.sleep(POLL_SECONDS)
