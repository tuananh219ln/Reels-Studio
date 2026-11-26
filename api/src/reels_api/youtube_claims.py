"""YouTube claims noted by hand (docs/decisions/2026-11-26-youtube-claimed-music.md). The app cannot read YouTube's
Content ID claims (the Data API has no such field, the Content ID API needs a CMS account), so a member who finds one in
YouTube Studio notes it on the video, and clears it once it is resolved. Both are `video_events` rows; the newest one
says whether the video's YouTube row shows "Bị chặn"."""

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .models import User, Video, VideoEvent

NOTED = "youtube_claim"
CLEARED = "youtube_claim_cleared"
MAX_NOTE_LENGTH = 1000


def history(db: DbSession, video_id: int) -> list[dict]:
    """The video's claim notes, newest first."""
    rows = db.execute(
        select(VideoEvent, User.name)
        .outerjoin(User, User.id == VideoEvent.actor_user_id)
        .where(VideoEvent.video_id == video_id, VideoEvent.type.in_((NOTED, CLEARED)))
        .order_by(VideoEvent.id.desc())
    ).all()
    return [
        {
            "id": event.id,
            "cleared": event.type == CLEARED,
            "note": (event.payload or {}).get("note", ""),
            "at": event.created_at.isoformat(),
            "by": name,
            "channel": event.channel,
        }
        for event, name in rows
    ]


def payload(db: DbSession, video_id: int) -> dict:
    """`active`: the claim the video's YouTube copy is held by now (None: none, or the last one was cleared)."""
    notes = history(db, video_id)
    return {"active": notes[0] if notes and not notes[0]["cleared"] else None, "history": notes}


def record(db: DbSession, video: Video, *, cleared: bool, note: str, user_id: int | None, channel: str) -> None:
    db.add(
        VideoEvent(
            video_id=video.id,
            type=CLEARED if cleared else NOTED,
            actor_user_id=user_id,
            channel=channel,
            payload={"note": note},
        )
    )
