"""A video made from a finished MP4 ("MP4 tải lên", mode "upload"): the file is the video's MP4 as it is, never
rendered. A member sends it on the web, Muse through MCP; both come here, so the checks, the plan link and the gate
are one (docs/decisions/2026-11-26-upload-mp4.md).

The video has no scenes. Its MP4 is `mp4_key`, so every posting route reads it like any other; its fingerprint
(`rendered_signature`) is the file's own hash, so the review gate holds for exactly this file.
"""

import hashlib
import json
import secrets
import subprocess
import tempfile
import unicodedata
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from reels_render.ffmpeg import find_tools

from . import knowledge, review
from .errors import ApiError
from .models import KnowledgeTopic, Publication, Session, TopicPlanItem, Video
from .script_rules import banned_hits
from .storage import DirectoryStorage
from .videos import active_job, lock_video, new_key, render_signature

UPLOAD = "upload"
MAX_BYTES = 200 * 1024 * 1024
MIN_SECONDS, MAX_SECONDS = 3, 90
GOOD_SECONDS = (15, 60)
MIN_SHORT_SIDE = 540
CODECS = {"h264", "hevc"}
IDEMPOTENCY_WINDOW = timedelta(hours=24)
MAX_TITLE = 200


def is_upload(video: Video) -> bool:
    return video.mode == UPLOAD


def invalid_media(reason: str) -> ApiError:
    return ApiError(400, "invalid_media", reason)


def _run(argv: list[str]) -> bytes:
    try:
        return subprocess.run(argv, check=True, capture_output=True, timeout=60).stdout
    except (subprocess.SubprocessError, OSError):
        raise invalid_media("Không đọc được file này, hãy kiểm tra đó là file MP4 không bị hỏng") from None


def inspect(path: Path) -> tuple[dict, list[dict]]:
    """What ffprobe reads from the file and the soft findings as QC checks (`{label, status: "warn", detail}`);
    a hard failure raises `invalid_media` with its reason."""
    size = path.stat().st_size
    if size > MAX_BYTES:
        raise ApiError(413, "file_too_large", f"File quá {MAX_BYTES // 1024 // 1024} MB, hãy nén nhỏ hơn")
    with open(path, "rb") as file:
        head = file.read(12)
    if head[4:8] != b"ftyp":
        raise invalid_media("Đây không phải file MP4 (hoặc MOV): hãy xuất video ra định dạng MP4")
    raw = _run([find_tools().ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)])
    try:
        data = json.loads(raw)
    except ValueError:
        raise invalid_media("Không đọc được file này, hãy kiểm tra đó là file MP4 không bị hỏng") from None
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None or not video.get("width") or not video.get("height"):
        raise invalid_media("File không có hình, hãy kiểm tra file MP4")
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    width, height = int(video["width"]), int(video["height"])
    # A phone's rotation tag swaps the shown sides.
    rotation = abs(int(float(video.get("tags", {}).get("rotate", 0) or 0)))
    for side in video.get("side_data_list", []) or []:
        rotation = abs(int(float(side.get("rotation", rotation) or 0)))
    if rotation in (90, 270):
        width, height = height, width
    try:
        duration = float(video.get("duration") or data["format"]["duration"])
    except (KeyError, TypeError, ValueError):
        raise invalid_media("Không đọc được thời lượng của file") from None
    codec = str(video.get("codec_name", ""))
    if codec not in CODECS:
        raise invalid_media(f"Video dùng codec {codec or 'không rõ'}: cần H.264 hoặc HEVC, hãy xuất lại file MP4")
    if min(width, height) < MIN_SHORT_SIDE:
        raise invalid_media(f"Video {width}×{height} quá nhỏ: cạnh ngắn cần từ {MIN_SHORT_SIDE} px")
    if duration < MIN_SECONDS or duration > MAX_SECONDS:
        raise invalid_media(f"Video dài {duration:.1f}s: cần từ {MIN_SECONDS} đến {MAX_SECONDS} giây")
    try:
        numerator, _, denominator = str(video.get("avg_frame_rate", "0/1")).partition("/")
        fps = round(float(numerator) / float(denominator or 1), 2) if float(denominator or 1) else 0.0
    except ValueError:
        fps = 0.0
    info = {
        "width": width,
        "height": height,
        "duration_s": round(duration, 2),
        "fps": fps,
        "video_codec": codec,
        "audio_codec": audio.get("codec_name") if audio else None,
        "has_audio": audio is not None,
    }
    warns: list[str] = []
    if codec == "hevc":
        warns.append("Video mã hoá HEVC: một số nền tảng không nhận, nên xuất H.264")
    if abs(width / height - 9 / 16) > 0.01:
        warns.append(f"Video {width}×{height} không phải khung 9:16")
    elif (width, height) != (1080, 1920):
        warns.append(f"Video {width}×{height}, nên là 1080×1920")
    if not GOOD_SECONDS[0] <= duration <= GOOD_SECONDS[1]:
        warns.append(f"Video dài {duration:.1f}s, nên từ {GOOD_SECONDS[0]} đến {GOOD_SECONDS[1]} giây")
    if audio is None:
        warns.append("Video không có âm thanh")
    return info, [{"label": "MP4 tải lên", "status": "warn", "detail": text} for text in warns]


def _thumbnail(path: Path, at: float, duration: float) -> bytes | None:
    at = min(max(at, 0), max(duration - 0.1, 0))
    try:
        return (
            _run(
                [
                    find_tools().ffmpeg,
                    "-v",
                    "error",
                    "-nostdin",
                    "-ss",
                    f"{at:.2f}",
                    "-i",
                    str(path),
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=540:-2",
                    "-f",
                    "image2pipe",
                    "-vcodec",
                    "mjpeg",
                    "-",
                ]
            )
            or None
        )
    except ApiError:
        return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def clean_text(value: str | None, limit: int) -> str:
    return unicodedata.normalize("NFC", (value or "").strip())[:limit]


def _store(
    db: DbSession,
    storage: DirectoryStorage,
    video: Video,
    path: Path,
    me: Session,
    note: str | None,
    thumbnail_at: float,
) -> list[str]:
    """Put the file on the video: its MP4, its facts and its thumbnail. Returns the keys the video had, for the
    caller to delete after the commit."""
    info, checks = inspect(path)
    sha = _sha256(path)
    old = [key for key in (video.mp4_key, video.thumbnail_key) if key]
    key = new_key(video.id, "upload", "mp4")
    storage.save_file(key, path)
    video.mp4_key, video.mp4_seconds = key, info["duration_s"]
    video.source_mp4 = {
        "storage_key": key,
        "url": f"/api/videos/{video.id}/video.mp4",
        "size_bytes": path.stat().st_size,
        "sha256": sha,
        "uploaded_at": datetime.now(UTC).isoformat(),
        "uploaded_by": me.user_id,
    }
    video.media_info = info
    video.qc = {"status": "warn" if checks else "pass", "checks": checks}
    video.rendered_signature = render_signature(video, None, [])  # the file's own hash
    video.rendered_at = datetime.now(UTC)
    video.render_seconds = None
    if note is not None:
        video.upload_note = clean_text(note, 1000) or None
    frame = _thumbnail(path, thumbnail_at, info["duration_s"])
    if frame is not None:
        video.thumbnail_key = new_key(video.id, "thumb", "jpg")
        storage.save_bytes(video.thumbnail_key, frame)
    else:
        video.thumbnail_key = None
    return old


def _idea(db: DbSession, item_id: int, group: KnowledgeTopic, replace_existing: bool) -> TopicPlanItem:
    idea = db.scalar(select(TopicPlanItem).where(TopicPlanItem.id == item_id).with_for_update())
    if idea is None:
        raise ApiError(404, "plan_item_not_found", "Không tìm thấy ý tưởng trong kế hoạch (có thể đã bị xoá)")
    if idea.knowledge_topic_id != group.id:
        raise ApiError(422, "invalid_value", "Ý tưởng này thuộc nhóm chủ đề khác")
    if idea.video_id is not None and not replace_existing:
        raise ApiError(409, "plan_item_taken", f"Ý tưởng này đã có video #{idea.video_id}")
    return idea


def existing(db: DbSession, key: str | None) -> Video | None:
    """The video an earlier send with the same key made in the last 24 hours."""
    if not key:
        return None
    return db.scalar(
        select(Video)
        .where(Video.upload_key == key, Video.created_at > datetime.now(UTC) - IDEMPOTENCY_WINDOW)
        .order_by(Video.id.desc())
        .limit(1)
    )


def create(
    db: DbSession,
    storage: DirectoryStorage,
    me: Session,
    path: Path,
    *,
    topic_id: int,
    plan_item_id: int | None = None,
    title: str | None = None,
    caption: str = "",
    hashtags: list[str] | None = None,
    pinned_comment_text: str = "",
    title_options: list[str] | None = None,
    thumbnail_at_s: float = 1,
    upload_note: str | None = None,
    idempotency_key: str | None = None,
    replace_existing: bool = False,
    via: str = "",
    app: str = "",
) -> Video:
    """A new "MP4 tải lên" video, in the draft state with its MP4 already there, linked to a plan idea when given. The
    caller commits; a refused file leaves nothing behind."""
    group = db.get(KnowledgeTopic, topic_id)
    if group is None:
        raise ApiError(422, "invalid_value", "Hãy chọn nhóm chủ đề")
    idea = _idea(db, plan_item_id, group, replace_existing) if plan_item_id is not None else None
    name = clean_text(title, MAX_TITLE) or (idea.topic if idea else "") or Path(path.name).stem[:MAX_TITLE] or "MP4"
    video = Video(
        topic=name,
        name=name,
        knowledge_topic_id=group.id,
        mode=UPLOAD,
        has_script=False,
        created_by_id=me.user_id,
        caption=clean_text(caption, 5000),
        hashtags=[tag.strip() for tag in (hashtags or []) if tag.strip()][:30],
        pinned_survey=clean_text(pinned_comment_text, 2000),
        title_options=[clean_text(one, MAX_TITLE) for one in (title_options or []) if one.strip()][:10],
        written_via=via,
        assistant_app=app,
        upload_key=idempotency_key or None,
        upload_note=clean_text(upload_note, 1000) or None,
    )
    db.add(video)
    db.flush()
    try:
        _store(db, storage, video, path, me, None, thumbnail_at_s)
        if idea is not None:
            if idea.video_id is not None:
                _free_old(db, idea.video_id)
            idea.video_id = video.id
        review.record(db, video, "uploaded", actor_id=me.user_id, channel=via or "web")
        db.flush()
    except BaseException:
        db.rollback()
        storage.delete_prefix(f"videos/{video.id}")
        raise
    return video


def _free_old(db: DbSession, video_id: int) -> None:
    """`replace_existing`: the idea lets go of its old video; the old video stays, unlinked."""
    idea = db.scalar(select(TopicPlanItem).where(TopicPlanItem.video_id == video_id))
    if idea is not None:
        idea.video_id = None
        db.flush()


def replace(
    db: DbSession,
    storage: DirectoryStorage,
    me: Session,
    video_id: int,
    path: Path,
    note: str | None = None,
) -> Video:
    """A new MP4 for an upload video that is not posted yet. Caption, plan idea and the rest stay; the video goes back
    to review and what was planned for the old file is withdrawn, as after a render (the gate holds for one file)."""
    video = lock_video(db, video_id)
    if not is_upload(video):
        raise ApiError(409, "not_upload", "Chỉ thay được MP4 của video “MP4 tải lên”")
    if _posted(db, video):
        raise ApiError(409, "already_posted", "Video đã đăng, không thay MP4 được")
    if active_job(db, video.id) is not None:
        raise ApiError(409, "video_locked", "Video đang có việc chạy (đăng bài), hãy đợi xong")
    old = _store(db, storage, video, path, me, note, 1)
    review.record(db, video, "mp4_replaced", actor_id=me.user_id, channel="web")
    db.commit()
    for key in old:
        storage.delete(key)
    review.after_render(db, video.id)
    return video


def _posted(db: DbSession, video: Video) -> bool:
    return (
        db.scalar(
            select(Publication.id).where(Publication.video_id == video.id, Publication.status == "published").limit(1)
        )
        is not None
    )


def warnings(db: DbSession, video: Video) -> list[str]:
    """What the sender should know and nothing stops: the file's soft findings and banned words in what a post says."""
    found = [check["detail"] for check in (video.qc or {}).get("checks", []) if check.get("status") != "pass"]
    words = knowledge.banned_words(db, video)
    for field, text in (
        ("tiêu đề", video.name or ""),
        ("caption", video.caption),
        ("bình luận ghim", video.pinned_survey),
    ):
        found += [f"Có từ cấm trong {field}: “{word}”" for word in banned_hits(text, words)]
    return found


def save_temp(data: bytes) -> tuple[tempfile.TemporaryDirectory, Path]:
    folder = tempfile.TemporaryDirectory(prefix="reels_upload_")
    path = Path(folder.name) / f"file-{secrets.token_hex(4)}.mp4"
    path.write_bytes(data)
    return folder, path
