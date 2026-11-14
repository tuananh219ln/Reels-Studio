"""The reels on their way to Facebook, those on it or waiting for their time, and those cancelled or deleted, for the
"Bài đăng" list and its calendar. A video is reviewed and posted from its own page; here a member can only ask for a
post's numbers to be read again."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import analytics, metrics
from .db import get_db
from .errors import ApiError
from .models import Job, Publication, Session, Video
from .sessions import current_member, now
from .videos import (
    active_job,
    is_published,
    live_at,
    publication_payload,
    split_scenes,
    thumbnail_url,
    video_name,
)

router = APIRouter(prefix="/api/posts")


def _attempt(db: DbSession, post: Publication) -> dict | None:
    """Where a post not on Facebook yet stands: its video's last publish job is still to run ("working"), or failed
    ("failed", with the job "Thử lại" sends again and its reason). None for a post past that."""
    if post.status != "pending":
        return None
    job = db.scalar(
        select(Job).where(Job.video_id == post.video_id, Job.kind == "publish").order_by(Job.id.desc()).limit(1)
    )
    if job is None or job.status != "failed":
        return {"state": "working", "job_id": None, "error": None}
    return {"state": "failed", "job_id": job.id, "error": job.error}


def _payload(db: DbSession, video: Video, post: Publication, by_page: dict) -> dict:
    title, _ = split_scenes(db, video)
    return {
        **publication_payload(post, by_page),
        # Whose it is: "Của tôi" keeps the posts a member made or that are on a Page they own.
        "created_by_id": post.created_by_id,
        "fanpage_owner_id": post.fanpage.owner_id if post.fanpage else None,
        "video_id": video.id,
        # The video's topic group, for "Lịch đăng" of Kho kiến thức.
        "knowledge_topic_id": video.knowledge_topic_id,
        "title": video_name(video, title),
        "thumbnail_url": thumbnail_url(video),
        "busy": active_job(db, video.id) is not None,
        "attempt": _attempt(db, post),
    }


@router.get("")
def list_posts(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> list[dict]:
    rows = db.execute(select(Video, Publication).join(Publication).where(Publication.platform == "facebook"))
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


@router.post("/refresh")
def refresh_topic(
    knowledge_topic_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Cập nhật view" of a topic group: the worker reads the numbers of its posts in its next round. The request never
    calls Facebook."""
    asked = metrics.ask_for_topic(db, knowledge_topic_id)
    db.commit()
    return {"asked": asked}


@router.post("/{post_id}/comment")
def request_comment(post_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Bình luận ngay" / "Cập nhật bình luận": the worker writes the affiliate comment, or edits the one it wrote, in
    its next round. The request itself never calls Facebook."""
    post = db.get(Publication, post_id, with_for_update=True)
    # An article's post is handled on its own page (/api/articles).
    if post is None or post.video_id is None:
        raise ApiError(404, "post_not_found", "Không tìm thấy bài đăng")
    if post.platform != "facebook" or post.remote_id is None or not is_published(post):
        raise ApiError(409, "post_not_live", "Chỉ bình luận được dưới bài đã lên Facebook")
    if db.get(Video, post.video_id).manual_comment:
        raise ApiError(
            409,
            "manual_comment",
            "Video đã đánh dấu dán link tay nên app không bình luận; bỏ đánh dấu ở Affiliate trước",
        )
    post.comment_requested_at = now()
    db.commit()
    return _payload(db, db.get(Video, post.video_id), post, analytics.medians(db))


@router.post("/{post_id}/metrics")
def refresh_metrics(post_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Cập nhật view": the worker reads the post's numbers in its next round, within seconds. The request
    itself never calls Facebook."""
    post = db.get(Publication, post_id, with_for_update=True)
    # An article's post is handled on its own page (/api/articles).
    if post is None or post.video_id is None:
        raise ApiError(404, "post_not_found", "Không tìm thấy bài đăng")
    if post.platform != "facebook" or post.remote_id is None or not is_published(post):
        raise ApiError(409, "post_not_measurable", "Chỉ cập nhật view được cho bài đã đăng lên Facebook")
    post.metrics_requested_at = now()
    db.commit()
    return _payload(db, db.get(Video, post.video_id), post, analytics.medians(db))


@router.get("/{post_id}")
def get_post(post_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """Read one managed reel with the same actions and metrics as the posts list."""
    post = db.get(Publication, post_id)
    if post is None or post.video_id is None or post.platform != "facebook":
        raise ApiError(404, "post_not_found", "Không tìm thấy bài đăng")
    return _payload(db, db.get(Video, post.video_id), post, analytics.medians(db))
