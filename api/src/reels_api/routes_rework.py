"""Owner-scoped batch upgrades of unpublished videos. Long work only runs in the worker."""

import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, PositiveInt
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session as DbSession

from . import rework
from .db import get_db
from .errors import ApiError
from .models import Job, PageQueueItem, Session, Video
from .sessions import current_member
from .videos import thumbnail_url

router = APIRouter(prefix="/api/rework")


class ReworkBody(BaseModel):
    ids: list[PositiveInt] = Field(min_length=1, max_length=50)
    replace_manual: bool = False
    render_after: bool = True


@router.get("/videos")
def candidates(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    videos = db.scalars(
        select(Video).where(Video.created_by_id == me.user_id).order_by(Video.id.desc()).limit(500)
    ).all()
    reasons = rework.problems(db, videos, me.user_id)
    latest_ids = (
        select(func.max(Job.id))
        .where(Job.video_id.in_([video.id for video in videos]), Job.kind == rework.KIND)
        .group_by(Job.video_id)
    )
    latest_jobs = {job.video_id: job for job in db.scalars(select(Job).where(Job.id.in_(latest_ids)))}
    rows = []
    for video in videos:
        reason = reasons[video.id]
        latest = latest_jobs.get(video.id)
        rows.append(
            {
                "id": video.id,
                "topic": video.topic,
                "thumbnail_url": thumbnail_url(video),
                "created_at": video.created_at.isoformat(),
                "eligible": reason is None,
                "reason": reason,
                "job": {
                    "id": latest.id,
                    "status": latest.status,
                    "error": latest.error,
                    "progress": rework.state(latest),
                }
                if latest
                else None,
            }
        )
    return {"videos": rows, "limit": 500, "batch_limit": 50}


@router.post("/videos", status_code=202)
def enqueue(body: ReworkBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    ids = sorted(set(body.ids))
    videos = db.scalars(select(Video).where(Video.id.in_(ids)).order_by(Video.id).with_for_update()).all()
    if len(videos) != len(ids):
        raise ApiError(404, "video_not_found", "Có video không còn tồn tại, hãy tải lại danh sách")
    reasons = rework.problems(db, videos, me.user_id)
    for video in videos:
        if video.created_by_id != me.user_id:
            raise ApiError(403, "not_owner", "Chỉ người tạo được nâng cấp video")
        if reason := reasons[video.id]:
            raise ApiError(409, "rework_blocked", f"Video #{video.id}: {reason}")
    # Approval belonged to the previous render. Never let a reworked MP4 inherit permission to auto-publish.
    withdrawn = db.execute(delete(PageQueueItem).where(PageQueueItem.video_id.in_(ids))).rowcount
    for video in videos:
        db.add(
            Job(
                video_id=video.id,
                kind=rework.KIND,
                status="queued",
                created_by_id=me.user_id,
                edit_prompt=json.dumps({"replace_manual": body.replace_manual, "render_after": body.render_after}),
            )
        )
    db.commit()
    return {"queued": len(videos), "withdrawn": withdrawn, "ids": ids}
