"""The reels on Facebook and those waiting for their time, for the "Bài đăng" list and the "Lịch đăng bài" calendar.
Read only: a video is reviewed and posted from its own page."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .db import get_db
from .models import Publication, Session, Video
from .sessions import current_member
from .videos import live_at, publication_payload, split_scenes, title_of

router = APIRouter(prefix="/api/posts")


def _payload(db: DbSession, video: Video, post: Publication) -> dict:
    title, _ = split_scenes(db, video)
    return {
        **publication_payload(post),
        "video_id": video.id,
        "title": title_of(video, title) or video.topic,
        "at": live_at(post).isoformat(),
        "created_by": post.created_by.name,
    }


@router.get("")
def list_posts(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(Video, Publication)
        .join(Publication)
        .where(Publication.platform == "facebook", Publication.status.in_(("scheduled", "published")))
    )
    return [_payload(db, video, post) for video, post in sorted(rows, key=lambda row: live_at(row[1]), reverse=True)]
