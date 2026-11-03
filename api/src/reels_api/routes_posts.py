"""The reels on Facebook, those waiting for their time, and those cancelled or deleted, for the "Bài đăng" list and
the "Lịch đăng bài" calendar. A video is reviewed and posted from its own page; here a member can only ask for a
post's numbers to be read again."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import analytics, metrics
from .db import get_db
from .errors import ApiError
from .models import Publication, Session, Video
from .sessions import current_member, now
from .videos import active_job, is_published, live_at, publication_payload, split_scenes, thumbnail_url, title_of

router = APIRouter(prefix="/api/posts")


def _payload(db: DbSession, video: Video, post: Publication, by_page: dict) -> dict:
    title, _ = split_scenes(db, video)
    return {
        **publication_payload(post, by_page),
        "video_id": video.id,
        "title": title_of(video, title) or video.topic,
        "thumbnail_url": thumbnail_url(video),
        "busy": active_job(db, video.id) is not None,
    }


@router.get("")
def list_posts(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(Video, Publication)
        .join(Publication)
        .where(
            Publication.platform == "facebook",
            Publication.status.in_(("scheduled", "published", "cancelled", "deleted")),
        )
    )
    by_page = analytics.medians(db)
    return [
        _payload(db, video, post, by_page)
        for video, post in sorted(rows, key=lambda row: live_at(row[1]), reverse=True)
    ]


@router.get("/kpis")
def weekly_kpis(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """The KPI strip of "Bài đăng": this week and last, Monday to Sunday in Vietnam time, from the 48-hour numbers."""
    return analytics.kpis(db)


@router.post("/freshen")
def freshen(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """Opening "Bài đăng": the worker reads the followed posts not read lately. The request never calls Facebook."""
    asked = metrics.ask_if_stale(db)
    db.commit()
    return {"asked": asked}


@router.post("/{post_id}/comment")
def request_comment(post_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Bình luận ngay" / "Cập nhật bình luận": the worker writes the affiliate comment, or edits the one it wrote, in
    its next round. The request itself never calls Facebook."""
    post = db.get(Publication, post_id, with_for_update=True)
    if post is None:
        raise ApiError(404, "post_not_found", "Không tìm thấy bài đăng")
    if post.platform != "facebook" or post.remote_id is None or not is_published(post):
        raise ApiError(409, "post_not_live", "Chỉ bình luận được dưới bài đã lên Facebook")
    post.comment_requested_at = now()
    db.commit()
    return _payload(db, db.get(Video, post.video_id), post, analytics.medians(db))


@router.post("/{post_id}/metrics")
def refresh_metrics(post_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Cập nhật view": the worker reads the post's numbers in its next round, within seconds. The request
    itself never calls Facebook."""
    post = db.get(Publication, post_id, with_for_update=True)
    if post is None:
        raise ApiError(404, "post_not_found", "Không tìm thấy bài đăng")
    if post.platform != "facebook" or post.remote_id is None or not is_published(post):
        raise ApiError(409, "post_not_measurable", "Chỉ cập nhật view được cho bài đã đăng lên Facebook")
    post.metrics_requested_at = now()
    db.commit()
    return _payload(db, db.get(Video, post.video_id), post, analytics.medians(db))
