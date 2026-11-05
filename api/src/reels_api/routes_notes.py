"""The studio's notes ("Góp ý"): a member's comment at a second of the video, and "Nhờ AI sửa", which sends the open
notes to a revise job (jobs.run_revise_job). A note is only text until it is sent, so adding one never locks the
video; a sent note waits for the AI and is neither changed nor removed by hand."""

import math
import unicodedata

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import routes_videos
from .db import get_db
from .errors import ApiError
from .models import Session, Video, VideoNote
from .sessions import current_member
from .videos import (
    ensure_unlocked,
    fit_seconds,
    lock_video,
    made_voice_seconds,
    split_scenes,
    video_not_found,
    video_payload,
)

router = APIRouter(prefix="/api/notes")

MAX_NOTE_LENGTH = 500


class NoteBody(BaseModel):
    text: object = None


class NewNoteBody(NoteBody):
    video_id: int
    at: object = None


def invalid(message: str) -> ApiError:
    return ApiError(422, "invalid_value", message)


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise invalid("Góp ý phải là chữ")
    text = unicodedata.normalize("NFC", value.replace("\r\n", "\n")).strip()
    if not text:
        raise invalid("Góp ý đang trống")
    if len(text) > MAX_NOTE_LENGTH:
        raise invalid(f"Góp ý dài quá {MAX_NOTE_LENGTH} ký tự")
    return text


def _length(db: DbSession, video: Video) -> float:
    title, scenes = split_scenes(db, video)
    every = ([title] if title else []) + scenes
    return sum(fit_seconds(scene.seconds, made_voice_seconds(video, scene)) for scene in every)


def _note(db: DbSession, note_id: int) -> tuple[Video, VideoNote]:
    video_id = db.scalar(select(VideoNote.video_id).where(VideoNote.id == note_id))
    if video_id is None:
        raise ApiError(404, "note_not_found", "Góp ý này đã bị xoá")
    video = lock_video(db, video_id)
    note = db.get(VideoNote, note_id)
    if note is None:
        raise ApiError(404, "note_not_found", "Góp ý này đã bị xoá")
    if note.status == "sent":
        raise ApiError(409, "note_sent", "Góp ý đã gửi cho AI, chờ AI sửa xong")
    return video, note


def _saved(db: DbSession, video: Video) -> dict:
    db.commit()
    return video_payload(db, video)


@router.post("", status_code=201)
def add_note(body: NewNoteBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    video = lock_video(db, body.video_id)
    text = _text(body.text)
    at, length = body.at, _length(db, video)
    if isinstance(at, bool) or not isinstance(at, (int, float)) or not math.isfinite(at) or not 0 <= at <= length:
        raise invalid(f"Giây của góp ý phải từ 0 đến {length:g}")
    db.add(VideoNote(video_id=video.id, at=round(at, 1), text=text, status="open", reply="", created_by_id=me.user_id))
    return _saved(db, video)


@router.patch("/{note_id}")
def patch_note(note_id: int, body: NoteBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)):
    video, note = _note(db, note_id)
    if "text" in body.model_fields_set:
        note.text = _text(body.text)
        # Changed after an answer, it is a new request.
        note.status, note.reply = "open", ""
    return _saved(db, video)


@router.delete("/{note_id}")
def delete_note(note_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    video, note = _note(db, note_id)
    db.delete(note)
    return _saved(db, video)


@router.post("/send/{video_id}")
def send_notes(video_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Nhờ AI sửa": every open note goes to one revise job (one LLM call, which costs money)."""
    video = lock_video(db, video_id)
    if video is None:
        raise video_not_found()
    if not video.has_script:
        raise ApiError(409, "no_script", "Video chưa có kịch bản")
    ensure_unlocked(db, video)
    notes = db.scalars(select(VideoNote).where(VideoNote.video_id == video.id, VideoNote.status == "open")).all()
    if not notes:
        raise invalid("Video chưa có góp ý nào để gửi")
    routes_videos._enqueue(db, video, "revise", me)  # noqa: SLF001 (the one way a video's job is queued)
    for note in notes:
        note.status = "sent"
    return _saved(db, video)
