""" "Nhân bản xáo cảnh" (shuffle.py): the dialog's preview, making the copies, "Xáo lại cảnh" on a copy and "Bỏ qua"
on its banner. No LLM call and no job, as "Nhân bản y hệt"; a renumbered voice text is read again at the next render.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession

from . import shuffle
from .db import get_db
from .errors import ApiError
from .models import Session
from .routes_videos import duplicable
from .sessions import current_member
from .storage import DirectoryStorage, get_storage
from .videos import ensure_unlocked, lock_video, video_payload

router = APIRouter(prefix="/api/shuffle")


class PreviewBody(BaseModel):
    count: int = Field(1, ge=1, le=shuffle.MAX_COPIES)
    lock_last: bool = False
    # "Ghim cảnh": content scenes (by id) that keep their place in every copy.
    pinned_scene_ids: list[int] = Field(default_factory=list, max_length=60)


class CopiesBody(BaseModel):
    orders: list[list[int]] = Field(min_length=1, max_length=shuffle.MAX_COPIES)
    lock_last: bool = False
    pinned_scene_ids: list[int] = Field(default_factory=list, max_length=60)
    renumber: bool = True


class ReshuffleBody(BaseModel):
    lock_last: bool = False
    pinned_scene_ids: list[int] = Field(default_factory=list, max_length=60)
    renumber: bool = True
    # "Hoàn tác": the order the copy had before, as its scene ids; None draws a new one.
    order: list[int] | None = None


@router.post("/videos/{video_id}/preview")
def preview(
    video_id: int, body: PreviewBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    return shuffle.preview(db, duplicable(db, video_id), body.count, body.lock_last, body.pinned_scene_ids)


@router.post("/videos/{video_id}/copies", status_code=201)
def make_copies(
    video_id: int,
    body: CopiesBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """The copies in the orders the dialog showed, all in one transaction. The source is only read, never locked."""
    copies, renumbered, warnings = shuffle.make_copies(
        db,
        storage,
        duplicable(db, video_id),
        body.orders,
        body.lock_last,
        body.renumber,
        me.user_id,
        body.pinned_scene_ids,
    )
    db.commit()
    return {
        "videos": [{"id": copy.id, "name": copy.name} for copy in copies],
        "renumbered": renumbered,
        "warnings": warnings,
    }


@router.post("/videos/{video_id}/reshuffle")
def reshuffle(
    video_id: int, body: ReshuffleBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Xáo lại cảnh" on a copy; `previous_order` lets the toast's "Hoàn tác" put it back."""
    video = lock_video(db, video_id)
    ensure_unlocked(db, video)
    if video.scene_order is None:
        raise ApiError(409, "not_a_shuffle", "Chỉ xáo lại được bản nhân bản xáo cảnh")
    previous = shuffle.reshuffle(db, video, body.lock_last, body.renumber, body.order, body.pinned_scene_ids)
    db.commit()
    return {**video_payload(db, video), "previous_order": previous}


@router.delete("/videos/{video_id}/title-review")
def skip_title_review(video_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Bỏ qua" on the banner: the copy keeps its title and no longer asks for a new one."""
    video = lock_video(db, video_id)
    video.review_title = None
    db.commit()
    return video_payload(db, video)
