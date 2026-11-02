"""Who else has a video open, and whether they are editing it.

An open video page reports itself every few seconds with a random id of its own ("tab"), so one member with two
tabs counts once, and closing one tab leaves the other. A page that stops reporting (closed without saying so, a
lost connection, a sleeping laptop) drops out after TIMEOUT. This is information only: nothing is locked.
"""

from datetime import timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as DbSession

from .db import get_db
from .models import Session, User, Video, VideoPresence
from .rules import avatar_initial
from .sessions import current_member, now
from .videos import video_not_found

router = APIRouter(prefix="/api/presence")

# The page reports every 10 s; three missed reports and it no longer counts.
TIMEOUT = timedelta(seconds=30)
TAB_PATTERN = r"^[A-Za-z0-9_-]{1,40}$"


class HereBody(BaseModel):
    tab: str = Field(pattern=TAB_PATTERN)
    editing: bool = False


class LeaveBody(BaseModel):
    tab: str = Field(pattern=TAB_PATTERN)


@router.post("/videos/{video_id}")
def here(video_id: int, body: HereBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """Marks this page as open on the video and answers with the other members who have it open."""
    if db.get(Video, video_id) is None:
        raise video_not_found()
    moment = now()
    db.execute(delete(VideoPresence).where(VideoPresence.seen_at < moment - TIMEOUT))
    row = {"video_id": video_id, "tab": body.tab, "user_id": me.user_id, "editing": body.editing, "seen_at": moment}
    db.execute(
        insert(VideoPresence)
        .values(row)
        .on_conflict_do_update(
            index_elements=["video_id", "tab"],
            set_={"editing": body.editing, "seen_at": moment},
            # A tab id is only ever refreshed by the member who made it.
            where=VideoPresence.user_id == me.user_id,
        )
    )
    db.commit()

    others: dict[int, dict] = {}
    rows = db.execute(
        select(User.id, User.name, VideoPresence.editing)
        .join(User, User.id == VideoPresence.user_id)
        .where(VideoPresence.video_id == video_id, VideoPresence.user_id != me.user_id)
    )
    for user_id, name, editing in rows:
        entry = others.setdefault(
            user_id, {"id": user_id, "name": name, "initial": avatar_initial(name), "editing": False}
        )
        entry["editing"] = entry["editing"] or editing
    # Whoever is editing first, then by name.
    return {"others": sorted(others.values(), key=lambda o: (not o["editing"], o["name"]))}


@router.post("/videos/{video_id}/leave")
def leave(
    video_id: int, body: LeaveBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """The page is closing: it stops counting now rather than after the time-out."""
    db.execute(
        delete(VideoPresence).where(
            VideoPresence.video_id == video_id, VideoPresence.tab == body.tab, VideoPresence.user_id == me.user_id
        )
    )
    db.commit()
    return {"ok": True}
