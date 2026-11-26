"""The review gate's web routes: "Duyệt", "Bỏ" and "Khôi phục" on a video, and the count behind the menu's badge.
They call `review`, the same service Muse (MCP) and "Tự duyệt" use (docs/decisions/2026-11-26-review-gate.md)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession

from . import review
from .db import get_db
from .models import Session
from .sessions import current_member
from .videos import ensure_unlocked, lock_video, video_payload

router = APIRouter(prefix="/api/review")


class ApproveBody(BaseModel):
    # "Vẫn duyệt": the member saw the warnings listed in the video's `review.qc` and approves anyway.
    acknowledge_qc: bool = False


class RejectBody(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


@router.get("/pending-count")
def pending_count(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    return {"count": review.pending_count(db)}


@router.post("/{video_id}/approve")
def approve(
    video_id: int, body: ApproveBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    video = lock_video(db, video_id)
    review.approve(db, video, me.user_id, "web", body.acknowledge_qc)
    db.commit()
    return video_payload(db, video)


@router.post("/{video_id}/reject")
def reject(
    video_id: int, body: RejectBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    video = lock_video(db, video_id)
    ensure_unlocked(db, video)
    review.reject(db, video, me.user_id, "web", body.reason)
    db.commit()
    return video_payload(db, video)


@router.post("/{video_id}/restore")
def restore(video_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    video = lock_video(db, video_id)
    review.restore(db, video, me.user_id, "web")
    db.commit()
    return video_payload(db, video)
