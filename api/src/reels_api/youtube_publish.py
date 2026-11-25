"""The `youtube_publish` job: one YouTube upload (a Publication, platform youtube) sent private through YouTube's
resumable upload with the member's own connection. Runs only in the worker.

The post then waits as `private`: its member makes it public, or schedules it, in YouTube Studio, at the time they
planned (`scheduled_at`, a reminder only). The worker's YouTube readings (metrics.measure_youtube) see it once it is
public and mark it published.

Never uploaded twice: the session's URL is saved (and committed) before the file is sent, so "Thử lại" first asks
YouTube about that very upload and only starts over when YouTube no longer holds the session.

The description and tags are built when a session is opened, from the video's caption as it is then and its group's
"Mô tả YouTube" (youtube_meta.py), and the description sent is kept as the post's `post_text`. A resumed session keeps
the body it was opened with.
"""

import logging

from sqlalchemy.orm import Session as DbSession

from . import youtube_connections, youtube_meta, youtube_upload
from .clips import ClipError, frame_at
from .frames import jpeg_bytes
from .models import Channel, Job, KnowledgeTopic, Publication, Video
from .storage import DirectoryStorage
from .videos import motion_cover_second

log = logging.getLogger(__name__)


class PublishFailed(Exception):
    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.message = message
        self.detail = detail


def _set_thumbnail(db: DbSession, token: str, video: Video, video_id: str, path) -> None:
    """A motion title's thumbnail is its settled frame (videos.title_poster_second), not YouTube's pick. A thumbnail
    that cannot be set (an unverified channel, a lost answer) leaves YouTube's own: the upload stands."""
    second = motion_cover_second(db, video)
    if second is None:
        return
    try:
        youtube_upload.set_thumbnail(token, video_id, jpeg_bytes(frame_at(path, second)))
    except (ClipError, youtube_upload.YouTubeUploadError) as err:
        log.warning("YouTube video %s keeps the thumbnail YouTube picked: %s", video_id, err)


def _description_and_tags(db: DbSession, video: Video, post: Publication) -> tuple[str, list[str]]:
    """The description and tags of a new upload: the caption as it is now and the group's "Mô tả YouTube"."""
    group = db.get(KnowledgeTopic, video.knowledge_topic_id) if video.knowledge_topic_id else None
    channel = db.get(Channel, post.channel_id) if post.channel_id else None
    stored = group.youtube_meta if group else None
    description = youtube_meta.description(video.caption or "", video.hashtags or [], stored, channel and channel.name)
    return description, youtube_meta.tags(video.hashtags or [], stored)


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
            description, tags = _description_and_tags(db, video, post)
            body = youtube_upload.metadata(post.caption or video.topic, description, tags)
            # Saved before the file is sent, so a retry asks YouTube about this very upload; the description too, so
            # the post shows what YouTube got.
            post.upload_url, post.remote_mp4_key = youtube_upload.start_upload(token, body, size), key
            post.post_text = description
            db.commit()
            uploaded = youtube_upload.send_file(token, post.upload_url, path)
    except youtube_upload.YouTubeUploadError as err:
        raise PublishFailed(err.message, err.detail) from None
    video_id = str(uploaded["id"])
    post.external_id, post.post_url = video_id, youtube_upload.shorts_url(video_id)
    post.status, post.upload_url = "private", None
    db.commit()
    _set_thumbnail(db, token, video, video_id, path)
    log.info("Job %s uploaded video %s to YouTube as %s (private)", job.id, video.id, video_id)
