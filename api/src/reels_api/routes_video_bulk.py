"""Delete many videos at once ("Chọn nhiều video" on /videos, docs/decisions/2026-11-28-bulk-delete-videos.md).

The web sends the ids it shows (the list is filtered in the browser, so "all that match the filter" is its ids). Each
video follows the rule of deleting one (`DELETE /api/videos/{id}`): only its maker, never one a teammate has work in,
never while a job runs, and here also never one posted anywhere (kept for the view report). A video that may not go
is skipped with its reason; the rest are deleted, one transaction each, so one failure never undoes the others."""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, PositiveInt
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session as DbSession

from .db import get_db
from .models import ACTIVE_JOB_STATUSES, Job, Publication, Session, Video
from .routes_videos import _others_work_in_video
from .sessions import current_member
from .storage import DirectoryStorage, get_storage

router = APIRouter(prefix="/api/video-bulk")
log = logging.getLogger(__name__)

MAX_IDS = 500


class BulkIds(BaseModel):
    ids: list[PositiveInt] = Field(min_length=1, max_length=MAX_IDS)


def _count_posts(db: DbSession, video_id: int, status: str) -> int:
    return db.scalar(
        select(func.count())
        .select_from(Publication)
        .where(Publication.video_id == video_id, Publication.status == status)
    )


def blocker(db: DbSession, video: Video, user_id: int) -> str | None:
    """Why this video is not deleted: "forbidden" (not the member's own, or holding a teammate's post, note or queue
    place), "published" (out on a platform: kept for the view report) or "rendering" (a job holds it); else None."""
    if video.created_by_id != user_id or any(_others_work_in_video(db, video, user_id).values()):
        return "forbidden"
    if _count_posts(db, video.id, "published"):
        return "published"
    busy = db.scalar(
        select(func.count()).select_from(Job).where(Job.video_id == video.id, Job.status.in_(ACTIVE_JOB_STATUSES))
    )
    return "rendering" if busy else None


@router.post("/delete/preview")
def preview(body: BulkIds, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """What deleting these videos would do: how many go, how many of those have a scheduled post (it goes with the
    video) and how many are skipped, by reason."""
    counts = {"count": 0, "scheduled": 0, "published": 0, "rendering": 0, "forbidden": 0}
    for video in db.scalars(select(Video).where(Video.id.in_(set(body.ids)))):
        reason = blocker(db, video, me.user_id)
        if reason:
            counts[reason] += 1
            continue
        counts["count"] += 1
        counts["scheduled"] += bool(_count_posts(db, video.id, "scheduled"))
    return counts


@router.post("/delete")
def bulk_delete(
    body: BulkIds,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    deleted: list[int] = []
    skipped: list[dict] = []
    for video_id in dict.fromkeys(body.ids):
        # Locked and checked again here, not trusting the preview: a job or a post may have come since.
        video = db.scalar(
            select(Video).where(Video.id == video_id).with_for_update().execution_options(populate_existing=True)
        )
        if video is None:
            skipped.append({"id": video_id, "reason": "missing"})
            continue
        reason = blocker(db, video, me.user_id)
        if reason:
            db.rollback()
            skipped.append({"id": video_id, "reason": reason})
            continue
        try:
            db.execute(delete(Video).where(Video.id == video_id))
            db.commit()
        except Exception:
            db.rollback()
            log.exception("bulk delete: video %s not deleted", video_id)
            skipped.append({"id": video_id, "reason": "error"})
            continue
        # Files only go after the rows, as when deleting one.
        storage.delete_prefix(f"videos/{video_id}")
        deleted.append(video_id)
    log.info("bulk delete by user %s: deleted %s, skipped %s", me.user_id, deleted, skipped)
    return {"deleted": len(deleted), "deleted_ids": deleted, "skipped": skipped}
