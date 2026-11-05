"""Sound effects on a scene ("Âm thanh" in the studio), each saved on its own like the scene fields. The sounds are
made by FFmpeg (reels_render.sounds), so the studio plays the same sound the render mixes in."""

import math
import tempfile
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from reels_render.errors import RenderError
from reels_render.sounds import SOUND_VOLUMES, SOUNDS, make_sound

from .db import get_db
from .errors import ApiError
from .models import SceneSound, Session
from .sessions import current_member
from .videos import ensure_unlocked, lock_scene, video_payload

router = APIRouter(prefix="/api/sounds")

MAX_START = 60


class SoundBody(BaseModel):
    sound: object = None
    start: object = None
    volume: object = None


class NewSoundBody(SoundBody):
    scene_id: int


def invalid(message: str) -> ApiError:
    return ApiError(422, "invalid_value", message)


def _apply(row: SceneSound, body: SoundBody) -> None:
    fields = body.model_fields_set
    if "sound" in fields:
        if not isinstance(body.sound, str) or body.sound not in SOUNDS:
            raise invalid(f"Âm thanh không hợp lệ: {body.sound!r}")
        row.sound = body.sound
    if "start" in fields:
        start = body.start
        if isinstance(start, bool) or not isinstance(start, (int, float)) or not math.isfinite(start):
            raise invalid("Giây bắt đầu phải là số")
        if not 0 <= start <= MAX_START:
            raise invalid(f"Giây bắt đầu phải từ 0 đến {MAX_START}")
        row.start = round(start, 2)
    if "volume" in fields:
        if not isinstance(body.volume, str) or body.volume not in SOUND_VOLUMES:
            raise invalid(f"Mức âm không hợp lệ: {body.volume!r}")
        row.volume = body.volume


def _sound(db: DbSession, sound_id: int):
    """The sound's scene and video locked, then the sound re-read: a teammate may have removed it meanwhile."""
    scene_id = db.scalar(select(SceneSound.scene_id).where(SceneSound.id == sound_id))
    if scene_id is None:
        raise ApiError(404, "sound_not_found", "Âm thanh này đã bị xoá")
    video, _ = lock_scene(db, scene_id)
    row = db.get(SceneSound, sound_id)
    if row is None:
        raise ApiError(404, "sound_not_found", "Âm thanh này đã bị xoá")
    return video, row


def _saved(db: DbSession, video) -> dict:
    db.commit()
    return video_payload(db, video)


@router.post("", status_code=201)
def add_sound(body: NewSoundBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """A sound effect on the scene, from `start` seconds into it (0 when not given), at "Vừa"."""
    video, scene = lock_scene(db, body.scene_id)
    ensure_unlocked(db, video)
    if "sound" not in body.model_fields_set:
        raise invalid("Âm thanh không hợp lệ: hãy chọn một âm")
    row = SceneSound(scene_id=scene.id, sound="", start=0, volume="normal")
    _apply(row, body)
    db.add(row)
    return _saved(db, video)


@router.patch("/{sound_id}")
def patch_sound(
    sound_id: int, body: SoundBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    video, row = _sound(db, sound_id)
    ensure_unlocked(db, video)
    _apply(row, body)
    return _saved(db, video)


@router.delete("/{sound_id}")
def delete_sound(sound_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    video, row = _sound(db, sound_id)
    ensure_unlocked(db, video)
    db.delete(row)
    return _saved(db, video)


@lru_cache(maxsize=len(SOUNDS))
def _library_mp3(name: str) -> bytes:
    with tempfile.TemporaryDirectory(prefix="reels_sound_") as folder:
        return make_sound(name, Path(folder) / f"{name}.mp3").read_bytes()


@router.get("/library/{name}.mp3")
def library_sound(name: str, me: Session = Depends(current_member)) -> Response:
    """The sound as the render makes it, to hear before adding it and to play in the preview."""
    if name not in SOUNDS:
        raise ApiError(404, "sound_not_found", "Không có âm thanh này")
    try:
        data = _library_mp3(name)
    except RenderError as err:
        raise ApiError(503, "sound_unavailable", f"Không tạo được âm thanh: {err}") from None
    return Response(data, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=86400"})
