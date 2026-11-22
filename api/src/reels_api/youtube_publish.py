"""The `youtube_publish` job: one YouTube upload (a Publication, platform youtube) sent private through YouTube's
resumable upload with the member's own connection. Runs only in the worker.

The post then waits as `private`: its member makes it public, or schedules it, in YouTube Studio, at the time they
planned (`scheduled_at`, a reminder only). The worker's YouTube readings (metrics.measure_youtube) see it once it is
public and mark it published.

Never uploaded twice: the session's URL is saved (and committed) before the file is sent, so "Thử lại" first asks
YouTube about that very upload and only starts over when YouTube no longer holds the session.
"""

import logging

from sqlalchemy.orm import Session as DbSession

from . import hashtags, youtube_connections, youtube_upload
from .models import Job, Publication, Video
from .storage import DirectoryStorage

log = logging.getLogger(__name__)


class PublishFailed(Exception):
    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.message = message
        self.detail = detail


def run(db: DbSession, job: Job, storage: DirectoryStorage) -> None:
    post = db.get(Publication, job.publication_id) if job.publication_id else None
    if post is None or post.platform != "youtube" or post.video_id is None:
        raise PublishFailed("Không tìm thấy bài YouTube của job này")
    if post.status in ("private", "published"):
        return
    if post.status != "pending":
        raise PublishFailed("Bài YouTube này đã hủy, hãy bấm Tải lên YouTube lại")
    video = db.get(Video, post.video_id)
    connection = youtube_connections.of_channel(db, post.channel_id)
    if connection is None or connection.owner_id != post.created_by_id:
        raise PublishFailed("Kênh YouTube chưa kết nối, hãy bấm Kết nối YouTube ở Quản lý kênh")
    key = post.remote_mp4_key or video.mp4_key
    if not key or not storage.exists(key):
        raise PublishFailed("Không thấy file MP4 trong storage, hãy render lại rồi tải lên")
    path = storage.path(key)
    size = path.stat().st_size
    try:
        token = youtube_connections.access_token(db, connection)
        uploaded = None
        if post.upload_url:
            held = youtube_upload.received(token, post.upload_url, size)
            if isinstance(held, dict):
                uploaded = held
            elif isinstance(held, int):
                uploaded = youtube_upload.send_file(token, post.upload_url, path, held)
            else:
                log.info("YouTube upload session of publication %s is gone: starting over", post.id)
        if uploaded is None:
            tags = hashtags.youtube_tags(video.hashtags or [])
            body = youtube_upload.metadata(post.caption or video.topic, post.post_text or "", tags)
            # Saved before the file is sent, so a retry asks YouTube about this very upload.
            post.upload_url, post.remote_mp4_key = youtube_upload.start_upload(token, body, size), key
            db.commit()
            uploaded = youtube_upload.send_file(token, post.upload_url, path)
    except youtube_upload.YouTubeUploadError as err:
        raise PublishFailed(err.message, err.detail) from None
    video_id = str(uploaded["id"])
    post.external_id, post.post_url = video_id, youtube_upload.shorts_url(video_id)
    post.status, post.upload_url = "private", None
    db.commit()
    log.info("Job %s uploaded video %s to YouTube as %s (private)", job.id, video.id, video_id)
