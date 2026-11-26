"""A video's strategy and beats on the video page (strategy.py, docs/decisions/2026-11-26-strategy-beats.md)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from . import review, strategy
from .db import get_db
from .models import Session
from .sessions import current_member
from .storage import DirectoryStorage, get_storage
from .videos import ensure_unlocked, lock_video, video_payload

router = APIRouter(prefix="/api/strategy")


class StrategyBody(BaseModel):
    # Each part is replaced only when sent.
    strategy: dict | None = None
    beats: list | None = None


@router.get("/catalog")
def catalog(me: Session = Depends(current_member)) -> dict:
    return strategy.catalog()


@router.put("/{video_id}")
def save(
    video_id: int,
    body: StrategyBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """Saves the strategy and/or the beats. A changed beat text is written to the scene the beat names, so the MP4 is
    outdated until it is rendered again (and approving is refused until then)."""
    video = lock_video(db, video_id)
    ensure_unlocked(db, video)
    apply(db, video, body.strategy, body.beats, me, "web", storage)
    db.commit()
    return video_payload(db, video)


def apply(db, video, new_strategy, new_beats, me, channel: str, storage, sync_scenes: bool = True) -> None:
    """Shared with MCP. `sync_scenes`: copy a changed beat text to its scene (the web); Muse edits the scenes itself."""
    from .routes_videos import ScenePatchBody, patch_scene

    if new_strategy is not None:
        video.strategy = strategy.clean_strategy(new_strategy)
    if new_beats is not None:
        cleaned = strategy.clean_beats(db, video, new_beats)
        if sync_scenes:
            for scene_id, text in strategy.changed_texts(video.beats, cleaned):
                patch_scene(scene_id, ScenePatchBody(text=text), me, db, storage)
        video.beats = cleaned
    review.record(db, video, "strategy_saved", actor_id=me.user_id, channel=channel)
