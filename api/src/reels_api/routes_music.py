"""The team music library: licensed tracks tagged by topic and mood, chosen for a video from its music card."""

import secrets
import unicodedata

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .db import get_db
from .errors import ApiError
from .models import MusicTrack, Session
from .routes_videos import MAX_TEXT_LENGTH, _inline, invalid
from .sessions import current_member
from .storage import DirectoryStorage, get_storage
from .uploads import MAX_MUSIC_BYTES, UploadRejected, check_mp3, file_label, read_limited

router = APIRouter(prefix="/api/music")

# Fixed lists: the topics follow the channel's topic matrix (issue #42), "chung" fits any topic.
TOPICS = ["tuổi thọ", "tim mạch", "máu não", "xương khớp", "gan", "da tóc", "giấc ngủ", "giảm cân", "chung"]
MOODS = ["nhẹ nhàng", "piano", "thư giãn", "truyền cảm hứng", "vui tươi", "trầm lắng"]
MAX_NAME_LENGTH = 200


class TrackPatchBody(BaseModel):
    name: str | None = None
    topics: list[str] | None = None
    mood: str | None = None
    license_note: str | None = None


def like_pattern(value: str) -> str:
    """The search text with LIKE wildcards made plain, for use with escape="\\\\"."""
    return unicodedata.normalize("NFC", value.strip()).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def track_not_found() -> ApiError:
    return ApiError(404, "track_not_found", "Không tìm thấy bài nhạc (có thể đã bị xóa)")


def get_track(db: DbSession, track_id: int) -> MusicTrack:
    track = db.get(MusicTrack, track_id)
    if track is None:
        raise track_not_found()
    return track


def _name(value: str) -> str:
    value = unicodedata.normalize("NFC", value).strip()
    if not value:
        raise invalid("Tên bài nhạc không được để trống")
    if len(value) > MAX_NAME_LENGTH:
        raise invalid(f"Tên bài nhạc dài quá {MAX_NAME_LENGTH} ký tự")
    return value


def _without_mp3(label: str) -> str:
    return label[:-4] if label.lower().endswith(".mp3") and len(label) > 4 else label


def _topics(values: list[str]) -> list[str]:
    chosen = set(unicodedata.normalize("NFC", value).strip() for value in values)
    if not chosen:
        raise invalid("Chọn ít nhất một chủ đề")
    if not chosen <= set(TOPICS):
        raise invalid("Chủ đề không có trong danh sách")
    return [topic for topic in TOPICS if topic in chosen]


def _mood(value: str) -> str:
    value = unicodedata.normalize("NFC", value).strip()
    if value not in MOODS:
        raise invalid("Mood không có trong danh sách")
    return value


def _license(value: str) -> str:
    value = unicodedata.normalize("NFC", value).strip()
    if len(value) > MAX_TEXT_LENGTH:
        raise invalid(f"Nguồn / giấy phép dài quá {MAX_TEXT_LENGTH} ký tự")
    return value


def track_payload(track: MusicTrack) -> dict:
    return {
        "id": track.id,
        "name": track.name,
        "topics": track.topics,
        "mood": track.mood,
        "license_note": track.license_note,
        "url": f"/api/music/{track.id}/audio.mp3",
        "created_by": track.created_by.name,
        "created_at": track.created_at.isoformat(),
    }


@router.get("")
def list_tracks(
    topic: str | None = None,
    mood: str | None = None,
    q: str | None = None,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
) -> list[dict]:
    query = select(MusicTrack).order_by(MusicTrack.id.desc())
    if topic:
        query = query.where(MusicTrack.topics.contains([topic]))
    if mood:
        query = query.where(MusicTrack.mood == mood)
    if q and q.strip():
        query = query.where(MusicTrack.name.ilike(f"%{like_pattern(q)}%", escape="\\"))
    return [track_payload(track) for track in db.scalars(query)]


@router.get("/options")
def options(me: Session = Depends(current_member)) -> dict:
    return {"topics": TOPICS, "moods": MOODS}


@router.post("")
def add_track(
    file: UploadFile = File(...),
    topics: list[str] = Form(default=[]),
    mood: str = Form(""),
    name: str = Form(""),
    license_note: str = Form(""),
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    # Fields first, so a wrong form is refused before the file is read.
    track = MusicTrack(
        name=_name(name or _without_mp3(file_label(file.filename, "nhac.mp3"))),
        topics=_topics(topics),
        mood=_mood(mood),
        license_note=_license(license_note),
        storage_key=f"music/track-{secrets.token_hex(6)}.mp3",
        created_by_id=me.user_id,
    )
    data = read_limited(file, MAX_MUSIC_BYTES, "File nhạc quá 20 MB, hãy chọn file nhỏ hơn")
    try:
        check_mp3(data)
    except UploadRejected as err:
        raise ApiError(415, "invalid_music", str(err)) from None
    storage.save_bytes(track.storage_key, data)
    db.add(track)
    db.commit()
    return track_payload(track)


@router.patch("/{track_id}")
def update_track(
    track_id: int, body: TrackPatchBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    track = get_track(db, track_id)
    if body.name is not None:
        track.name = _name(body.name)
    if body.topics is not None:
        track.topics = _topics(body.topics)
    if body.mood is not None:
        track.mood = _mood(body.mood)
    if body.license_note is not None:
        track.license_note = _license(body.license_note)
    db.commit()
    return track_payload(track)


@router.delete("/{track_id}")
def delete_track(
    track_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    # Videos that used the track keep their own copy of the file.
    track = get_track(db, track_id)
    key = track.storage_key
    db.delete(track)
    db.commit()
    storage.delete(key)
    return {"ok": True}


@router.get("/{track_id}/audio.mp3")
def track_audio(
    track_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> FileResponse:
    return _inline(storage, get_track(db, track_id).storage_key, "audio/mpeg")
