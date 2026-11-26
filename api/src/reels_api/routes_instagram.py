"""Instagram Reels through the API, by way of the Facebook Page the account is linked to
(docs/specs/instagram-posting/brief.md): "Đăng bài" › Instagram posts the video's MP4 now, or at a set time like
Facebook. Only the Page's owner posts. The worker does the posting (ig_publish.py); a post set for later waits as
`scheduled` until the worker's round reaches its time (jobs.queue_instagram_posts)."""

from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from . import brands, hashtags, instagram, review
from .db import get_db
from .errors import ApiError
from .models import Fanpage, Job, Publication, Session
from .ownership import ensure_can_take_down, ensure_page_owner
from .routes_videos import MAX_SCHEDULE_DELAY, MIN_SCHEDULE_DELAY, invalid
from .sessions import current_member, now
from .storage import DirectoryStorage, get_storage
from .videos import active_job, ensure_unlocked, lock_video, render_signature, split_scenes, video_payload

router = APIRouter(prefix="/api/instagram")


class PublishBody(BaseModel):
    fanpage_id: int
    # None: now. Else the time it goes out, at least 15 minutes and at most 29 days ahead, as for Facebook.
    scheduled_at: datetime | None = None


@router.post("/videos/{video_id}/publish", status_code=201)
def publish(
    video_id: int, body: PublishBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    video = lock_video(db, video_id)
    ensure_unlocked(db, video)
    if not video.mp4_key:
        raise ApiError(409, "no_mp4", "Video chưa có MP4, hãy render trước")
    title, scenes = split_scenes(db, video)
    if video.rendered_signature != render_signature(video, title, scenes):
        raise ApiError(409, "mp4_outdated", "MP4 chưa cập nhật theo bản sửa, hãy render lại rồi đăng")
    review.ensure_approved(video)
    when = body.scheduled_at
    if when is not None:
        if when.tzinfo is None:
            raise invalid("Giờ đăng phải kèm múi giờ")
        if not now() + MIN_SCHEDULE_DELAY <= when <= now() + MAX_SCHEDULE_DELAY:
            raise invalid("Giờ hẹn phải sau ít nhất 15 phút và trong vòng 29 ngày tới")
    fanpage = db.get(Fanpage, body.fanpage_id)
    if fanpage is None or not fanpage.active:
        raise invalid("Hãy chọn một Fanpage đang dùng")
    ensure_page_owner(fanpage, me.user_id)
    if not fanpage.instagram_user_id:
        raise invalid(f"Page “{fanpage.name}” chưa liên kết tài khoản Instagram Business")
    if wrong := brands.mismatch(db, video, fanpage):
        raise ApiError(409, "brand_mismatch", wrong)
    same = db.scalar(
        select(Publication.id).where(
            Publication.video_id == video.id,
            Publication.platform == "instagram",
            Publication.fanpage_id == fanpage.id,
            Publication.remote_mp4_key == video.mp4_key,
            Publication.status.in_(("scheduled", "published")),
        )
    )
    if same is not None:
        raise ApiError(409, "instagram_already_posted", "Bản MP4 này đã đăng hoặc đã hẹn lên Instagram của Page đó")
    waiting = db.scalar(
        select(Publication).where(
            Publication.video_id == video.id, Publication.platform == "instagram", Publication.status == "pending"
        )
    )
    if waiting is not None:
        running = active_job(db, video.id)
        if running is not None and running.publication_id == waiting.id:
            raise ApiError(409, "instagram_post_pending", "Video đang được đăng lên Instagram, hãy đợi xong")
        if waiting.finish_sent_at is not None:
            raise ApiError(
                409,
                "instagram_post_pending",
                "Lần đăng Instagram trước chưa rõ kết quả, hãy bấm Thử lại ở job lỗi thay vì đăng lần nữa",
            )
        # Never made public (its job failed before asking Instagram to publish): replaced by this one.
        waiting.status, waiting.closed_at, waiting.closed_by_id = "cancelled", now(), me.user_id
        db.flush()
    post = Publication(
        video_id=video.id,
        platform="instagram",
        status="scheduled" if when is not None else "pending",
        scheduled_at=when,
        fanpage_id=fanpage.id,
        created_by_id=me.user_id,
        remote_mp4_key=video.mp4_key,
        # The caption as sent, so "Thử lại" sends the same and a lost answer is found by it.
        post_text=instagram.caption(hashtags.post_text(video.caption, video.hashtags)),
    )
    db.add(post)
    try:
        db.flush()
        if when is None:
            db.add(
                Job(
                    video_id=video.id,
                    kind="ig_publish",
                    status="queued",
                    created_by_id=me.user_id,
                    publication_id=post.id,
                )
            )
            db.flush()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "video_locked", "Video đang có việc chạy, hãy đợi xong rồi đăng Instagram") from None
    db.commit()
    return video_payload(db, video)


@router.post("/posts/{post_id}/cancel")
def cancel(post_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Hủy hẹn": an Instagram post set for later that has not started. Nothing was sent to Instagram yet."""
    video_id = db.scalar(select(Publication.video_id).where(Publication.id == post_id))
    if video_id is None:
        raise ApiError(404, "post_not_found", "Không tìm thấy bài đăng")
    video = lock_video(db, video_id)
    post = db.scalar(select(Publication).where(Publication.id == post_id).execution_options(populate_existing=True))
    if post.platform != "instagram":
        raise ApiError(404, "post_not_found", "Không tìm thấy bài đăng")
    ensure_can_take_down(db, post, me.user_id)
    if post.status != "scheduled":
        raise ApiError(409, "post_not_scheduled", "Chỉ hủy được bài Instagram đang hẹn giờ, chưa đăng")
    post.status, post.closed_at, post.closed_by_id = "cancelled", now(), me.user_id
    db.commit()
    return video_payload(db, video)


@router.get("/media/{token}/video.mp4")
def media_file(
    token: str, db: DbSession = Depends(get_db), storage: DirectoryStorage = Depends(get_storage)
) -> FileResponse:
    """The MP4 of a pending Instagram post, for Instagram's servers to fetch (`video_url`): no sign-in, the sealed token
    in the link is the permission, and it names one post and expires (instagram.LINK_SECONDS)."""
    post_id = instagram.link_post_id(token)
    post = db.get(Publication, post_id) if post_id is not None else None
    key = post.remote_mp4_key if post is not None and post.platform == "instagram" else None
    if post is None or post.status != "pending" or not key or not storage.exists(key):
        raise ApiError(404, "file_not_found", "Không tìm thấy file")
    return FileResponse(storage.path(key), media_type="video/mp4", headers={"Cache-Control": "private, no-store"})
