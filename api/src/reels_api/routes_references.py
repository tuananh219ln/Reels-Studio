"""'Từ video mẫu': making a video from a sample video, and the samples learned so far (reference.py does the work).

The request only checks and stores what it was given and queues a learn job: downloading a link, the stills, the
words and every LLM call run in the worker.
"""

import tempfile
import unicodedata
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from . import reference, remote_media, video_options
from .db import get_db
from .errors import ApiError
from .models import ACTIVE_JOB_STATUSES, Job, KnowledgeTopic, Session, Video, VideoReference
from .ownership import ensure_owner
from .routes_videos import MAX_TOPIC_LENGTH, _enqueue, _inline, _saved, apply_default_music, invalid
from .sessions import current_member
from .storage import DirectoryStorage, get_storage
from .videos import REFERENCE_MODE_LABELS, reference_frames, split_scenes, title_of

router = APIRouter(prefix="/api/references")

MAX_NAME_LENGTH = 300
MAX_ANALYSIS_LENGTH = reference.MAX_ANALYSIS_LENGTH


def _not_found() -> ApiError:
    return ApiError(404, "reference_not_found", "Không tìm thấy video mẫu (có thể đã bị xoá)")


def _spool(upload: UploadFile, target: Path) -> None:
    with open(target, "wb") as file:
        copied = 0
        while chunk := upload.file.read(1024 * 1024):
            copied += len(chunk)
            if copied > remote_media.MAX_SAMPLE_BYTES:
                raise ApiError(413, "file_too_large", remote_media.SAMPLE_TOO_BIG)
            file.write(chunk)


def _summary(db: DbSession, sample: VideoReference) -> dict:
    used = db.scalar(select(func.count()).select_from(Video).where(Video.reference_id == sample.id))
    first = reference_frames(sample)[:1]
    return {
        "id": sample.id,
        "source_name": sample.source_name,
        "source_url": sample.source_url,
        "seconds": sample.seconds,
        "analyzed": bool(sample.analysis.strip()),
        "analysis": sample.analysis,
        "cover_url": first[0]["url"] if first else None,
        "video_count": used,
        "created_by": sample.created_by.name,
        "created_by_id": sample.created_by_id,
        "created_at": sample.created_at.isoformat(),
    }


@router.post("/videos", status_code=201)
def create_from_sample(
    topic: str = Form(...),
    knowledge_topic_id: int = Form(...),
    mode: str = Form("quick"),
    url: str = Form(""),
    reference_id: int | None = Form(None),
    file: UploadFile | None = File(None),
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """A new video learned from a sample: a pasted link, an uploaded file, or (way "reuse") a sample learned before."""
    topic = " ".join(unicodedata.normalize("NFC", topic).split())
    if not topic:
        raise invalid("Hãy nhập chủ đề hoặc yêu cầu cho video mới")
    if len(topic) > MAX_TOPIC_LENGTH:
        raise invalid(f"Chủ đề dài quá {MAX_TOPIC_LENGTH} ký tự")
    if mode not in reference.MODES:
        raise invalid("Cách làm không có trong danh sách")
    group = db.get(KnowledgeTopic, knowledge_topic_id)
    if group is None:
        raise invalid("Hãy chọn nhóm chủ đề")
    has_file = file is not None and bool(file.filename)
    if mode == "reuse":
        sample = db.get(VideoReference, reference_id) if reference_id else None
        if sample is None:
            raise invalid("Hãy chọn một video mẫu đã học")
        return _make_video(db, me, group, topic, mode, sample)
    if has_file == bool(url.strip()):
        raise invalid("Hãy dán link video mẫu hoặc tải video lên (chỉ một trong hai)")
    if has_file:
        with tempfile.TemporaryDirectory(prefix="reels_sample_") as folder:
            path = Path(folder) / "sample"
            _spool(file, path)
            try:
                sample_file = reference.check_sample(path)
            except reference.ReferenceError as err:
                raise ApiError(415, "invalid_video", err.message) from None
            name = (file.filename or "video")[:MAX_NAME_LENGTH]
            sample = VideoReference(source_name=name, created_by_id=me.user_id, seconds=round(sample_file.seconds, 3))
            db.add(sample)
            db.flush()
            sample.video_key = reference.source_key(sample.id, sample_file.extension)
            storage.save_file(sample.video_key, path)
    else:
        try:
            link = remote_media.check_url(url)
        except remote_media.RemoteMediaError as err:
            raise invalid(str(err)) from None
        sample = VideoReference(source_url=link, source_name=link[:MAX_NAME_LENGTH], created_by_id=me.user_id)
        db.add(sample)
        db.flush()
    return _make_video(db, me, group, topic, mode, sample)


def _make_video(
    db: DbSession, me: Session, group: KnowledgeTopic, topic: str, mode: str, sample: VideoReference
) -> dict:
    video = Video(
        topic=topic,
        knowledge_topic_id=group.id,
        has_script=False,
        created_by_id=me.user_id,
        reference_id=sample.id,
        reference_mode=mode,
    )
    video_options.apply_defaults(db, video, me.user_id)
    db.add(video)
    db.flush()
    apply_default_music(db, video, get_storage(), me.user_id)
    _enqueue(db, video, "learn", me)
    return _saved(db, video)


@router.get("")
def list_samples(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> list[dict]:
    """The samples learned so far, newest first, for "Dùng mẫu đã học"."""
    samples = db.scalars(select(VideoReference).order_by(VideoReference.created_at.desc(), VideoReference.id.desc()))
    return [_summary(db, sample) for sample in samples]


@router.get("/{reference_id}")
def get_sample(reference_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    sample = db.get(VideoReference, reference_id)
    if sample is None:
        raise _not_found()
    videos = db.scalars(select(Video).where(Video.reference_id == sample.id).order_by(Video.id)).all()
    return {
        **_summary(db, sample),
        "transcript": sample.transcript,
        "frames": reference_frames(sample),
        "videos": [
            {
                "id": video.id,
                "title": title_of(video, split_scenes(db, video)[0]) or video.topic,
                "mode": video.reference_mode,
            }
            for video in videos
        ],
        "modes": REFERENCE_MODE_LABELS,
    }


class AnalysisBody(BaseModel):
    analysis: str


@router.patch("/{reference_id}")
def edit_analysis(
    reference_id: int, body: AnalysisBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """A member's edit of the analysis (way "review", or before reusing a sample): later scripts write from it."""
    sample = db.get(VideoReference, reference_id, with_for_update=True)
    if sample is None:
        raise _not_found()
    analysis = unicodedata.normalize("NFC", body.analysis.replace("\r\n", "\n")).strip()
    if not analysis:
        raise invalid("Bản phân tích không được để trống")
    if len(analysis) > MAX_ANALYSIS_LENGTH:
        raise invalid(f"Bản phân tích dài quá {MAX_ANALYSIS_LENGTH} ký tự")
    if _busy(db, sample.id):
        raise ApiError(409, "reference_busy", "Video mẫu đang được dùng trong một job, hãy đợi job xong")
    sample.analysis = analysis
    db.commit()
    return _summary(db, sample)


def _busy(db: DbSession, reference_id: int) -> bool:
    return (
        db.scalar(
            select(Job.id)
            .join(Video, Video.id == Job.video_id)
            .where(Video.reference_id == reference_id, Job.status.in_(ACTIVE_JOB_STATUSES))
            .limit(1)
        )
        is not None
    )


@router.delete("/{reference_id}")
def delete_sample(
    reference_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """The sample and its files; the videos made from it keep their scripts and clips (their own copies)."""
    sample = db.get(VideoReference, reference_id, with_for_update=True)
    if sample is None:
        raise _not_found()
    ensure_owner(sample.created_by_id, me.user_id, "video mẫu này")
    if _busy(db, sample.id):
        raise ApiError(409, "reference_busy", "Video mẫu đang được dùng trong một job, hãy đợi job xong")
    db.delete(sample)
    db.commit()
    storage.delete_prefix(f"references/{reference_id}")
    return {"ok": True}


@router.get("/{reference_id}/frames/{number}.jpg")
def sample_frame(
    reference_id: int,
    number: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> FileResponse:
    sample = db.get(VideoReference, reference_id)
    if sample is None or not 1 <= number <= len(sample.frames):
        raise ApiError(404, "file_not_found", "Không tìm thấy file")
    return _inline(storage, sample.frames[number - 1]["key"], "image/jpeg")
