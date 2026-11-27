""" "Video này được làm như thế nào" and "Lịch sử sửa" on the video page (docs/decisions/2026-11-26-per-group-qc.md).

`GET /api/video-story/{id}`: who made the video and how (its script's source, each scene's voice and where it comes
from, its music), how long it took, and one timeline of its jobs, its review steps (`video_events`) and its edits
(`edit_logs`, entity "video"), with a text to copy into a report or a chat.

`POST /api/video-story/{id}/undo/{log_id}` ("Hoàn tác"): puts back what an edit changed, through the same edit routes,
as a new "restore" entry; nothing in the history is removed. It refuses when the video has been edited at that place
since (a conflict, never an overwrite), or when the scene is gone.
"""

from collections import Counter
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import selectinload

from . import edit_log, video_options
from .db import get_db
from .errors import ApiError
from .models import EditLog, Job, KnowledgeTopic, Scene, Session, User, Video, VideoEvent
from .routes_videos import ScenePatchBody, VideoPatchBody, patch_scene, patch_video, video_not_found
from .sessions import current_member
from .storage import DirectoryStorage, get_storage
from .videos import script_writer, split_scenes, video_name

router = APIRouter(prefix="/api/video-story")

VIETNAM = ZoneInfo("Asia/Ho_Chi_Minh")
TIMELINE_LIMIT = 200

JOB_LABELS = {
    "script": "Viết kịch bản",
    "clone": "Viết kịch bản nhân bản",
    "revise": "Sửa kịch bản bằng AI",
    "check": "Rà soát an toàn",
    "voice": "Tạo giọng đọc",
    "photos": "Tìm ảnh",
    "photo": "Tạo ảnh",
    "image": "Tạo ảnh",
    "image_edit": "Sửa ảnh",
    "render": "Render",
    "publish": "Đăng Facebook",
    "ig_publish": "Đăng Instagram",
    "tiktok_publish": "Đăng TikTok",
    "youtube_publish": "Tải lên YouTube",
    "unpublish": "Rút bài đã hẹn",
}
JOB_STATUS = {"done": "xong", "failed": "lỗi", "cancelled": "đã hủy", "running": "đang chạy", "queued": "đang chờ"}
EVENT_LABELS = {
    "review_requested": "Chờ duyệt bản render mới",
    "approved": "Duyệt",
    "rejected": "Bỏ",
    "restored": "Khôi phục để duyệt lại",
    "publish_skipped": "Không đăng vì chưa duyệt",
    "uploaded": "Tải MP4 lên",
    "mp4_replaced": "Thay MP4",
}
CHANNEL_LABELS = {
    "web": "trên web",
    "muse_chat": "qua Muse",
    "mcp": "qua MCP",
    "auto": "tự động",
    "telegram": "qua Telegram",
}
FIELD_LABELS = {
    "name": "Tên video",
    "caption": "Caption",
    "hashtags": "Hashtag",
    "affiliates": "Affiliate",
    "pinned_survey": "Dòng khảo sát",
    "extra_comments": "Bình luận thêm",
    "music_suggestions": "Gợi ý nhạc",
    "music_volume": "Âm lượng nhạc",
    "music_start": "Giây bắt đầu nhạc",
    "voice_enabled": "Bật giọng đọc",
    "options": "Tùy chọn video",
    "mode": "Kiểu video",
    "content_type": "Loại nội dung",
    "no_title": "Không dùng tiêu đề",
    "text": "Chữ",
    "voice_text": "Lời đọc",
    "seconds": "Số giây",
    "seconds_auto": "Tự khớp lời đọc",
    "keywords": "Từ khóa",
    "keywords_en": "Từ khóa tiếng Anh",
    "image_prompt": "Prompt ảnh",
    "voice_id": "Giọng",
    "video_start": "Giây bắt đầu clip",
    "video_speed": "Tốc độ clip",
    "video_sound": "Tiếng gốc",
    "video_loop": "Lặp clip",
    "text_x": "Vị trí chữ",
    "text_y": "Vị trí chữ",
    "transition": "Chuyển cảnh",
    "color": "Màu",
    "music_level": "Mức nhạc",
    "image_fit": "Khung ảnh",
    "image_crop_offset": "Vị trí khung vuông",
}


def voice_source(voice: str) -> str:
    """The service a voice id reads with (video_options.clean_voice_id's forms)."""
    if not voice:
        return "Không có giọng"
    for prefix, name in (("vieneu:", "VieNeu"), ("gemini:", "Gemini"), ("google:", "Google")):
        if voice.startswith(prefix):
            return name
    return "ElevenLabs"


def voice_name(voice: str) -> str:
    return voice.partition(":")[2] if ":" in voice else voice


def _when(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _local(value: datetime | None) -> str:
    return value.astimezone(VIETNAM).strftime("%H:%M %d/%m") if value else ""


def made_via(db: DbSession, video: Video) -> str:
    """How the video was made, in a member's words."""
    if video.mode == "upload":
        return "MP4 tải lên"
    if video.competitor_source_url:
        return "Clone từ video đối thủ"
    if video.reference_id:
        return "Học từ video mẫu"
    if video.shuffled_from_id:
        return "Nhân bản xáo cảnh"
    if video.variant_of_id:
        return "Biến thể của video khác"
    if video.written_via == "assistant":
        return f"{video.assistant_app or 'Trợ lý của thành viên'} qua MCP"
    if video.hand_written:
        return "Thành viên tự viết kịch bản"
    if video.has_script:
        writer = script_writer(db, video)
        return f"AI của nhóm ({writer})" if writer else "AI của nhóm"
    return "Chưa có kịch bản"


def scene_voices(video: Video, title: Scene | None, scenes: list[Scene]) -> list[dict]:
    rows = []
    for index, scene in enumerate([title, *scenes]):
        if scene is None:
            continue
        label = "Tiêu đề" if scene.is_title else f"Cảnh {index}"
        if not video.voice_enabled:
            source, voice = "Tắt giọng đọc", ""
        elif (scene.voice_signature or "").startswith("custom:"):
            source, voice = "MP3 tải lên", scene.voice_name or ""
        elif not scene.voice_text.strip():
            source, voice = "Không có lời đọc", ""
        else:
            voice_id = video_options.scene_voice(video, scene)
            source, voice = voice_source(voice_id), voice_name(voice_id)
        rows.append({"scene_id": scene.id, "label": label, "source": source, "voice": voice})
    return rows


SILENT = ("Tắt giọng đọc", "Không có lời đọc", "Không có giọng")


def _short(value: Any, limit: int = 80) -> str:
    if value is None or value == "" or value == []:
        return "(trống)"
    if isinstance(value, bool):
        return "bật" if value else "tắt"
    if isinstance(value, list):
        value = ", ".join(str(item) for item in value)
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def change_rows(changes: dict, places: dict[int, str]) -> list[dict]:
    """Each changed field of an entry, with where it is ("Cảnh 3", "Tiêu đề", "Cảnh đã xóa") and old → new."""
    rows = []
    for key, change in changes.items():
        parsed = edit_log.parse_scene_key(key)
        if parsed:
            scene_id, field = parsed
            place = places.get(scene_id, "Cảnh đã xóa")
        else:
            field, place = key, "Video"
        rows.append(
            {
                "key": key,
                "place": place,
                "field": FIELD_LABELS.get(field, field),
                "old": _short(change.get("old")),
                "new": _short(change.get("new")),
                "restorable": field in (edit_log.SCENE_RESTORABLE if parsed else edit_log.VIDEO_RESTORABLE),
            }
        )
    return rows


def _places(title: Scene | None, scenes: list[Scene]) -> dict[int, str]:
    places = {title.id: "Tiêu đề"} if title is not None else {}
    places |= {scene.id: f"Cảnh {index}" for index, scene in enumerate(scenes, 1)}
    return places


def history(db: DbSession, video: Video, places: dict[int, str]) -> list[dict]:
    entries = edit_log.entries(db, edit_log.VIDEO, video.id, limit=TIMELINE_LIMIT)
    undone = {entry.restored_from_id for entry in entries if entry.restored_from_id}
    return [
        {
            "id": entry.id,
            "action": entry.action,
            "at": entry.created_at.isoformat(),
            "by": entry.user.name if entry.user else None,
            "source": entry.source,
            "restored_from_id": entry.restored_from_id,
            "undone": entry.id in undone,
            "changes": change_rows(entry.changes, places),
        }
        for entry in entries
    ]


def story(db: DbSession, video: Video) -> dict:
    title, scenes = split_scenes(db, video)
    places = _places(title, scenes)
    maker = db.get(User, video.created_by_id)
    group = db.get(KnowledgeTopic, video.knowledge_topic_id) if video.knowledge_topic_id else None
    voices = scene_voices(video, title, scenes) if video.mode != "upload" else []
    sources = Counter(row["source"] for row in voices if row["source"] not in SILENT)
    jobs = list(db.scalars(select(Job).where(Job.video_id == video.id).order_by(Job.id)))
    events = list(db.scalars(select(VideoEvent).where(VideoEvent.video_id == video.id).order_by(VideoEvent.id)))
    users = {user.id: user.name for user in db.scalars(select(User))}
    edits = history(db, video, places)
    last_render = next((job for job in reversed(jobs) if job.kind == "render" and job.status == "done"), None)

    timeline: list[dict] = [
        {
            "at": video.created_at.isoformat(),
            "kind": "created",
            "text": f"Tạo video ({made_via(db, video)})",
            "by": maker.name if maker else None,
        }
    ]
    for job in jobs:
        label = JOB_LABELS.get(job.kind, job.kind)
        took = (
            f", {round((job.finished_at - job.started_at).total_seconds())} giây"
            if job.finished_at and job.started_at
            else ""
        )
        timeline.append(
            {
                "at": (job.finished_at or job.created_at).isoformat(),
                "kind": "job",
                "text": f"{label}: {JOB_STATUS.get(job.status, job.status)}{took}",
                "by": users.get(job.created_by_id),
            }
        )
    for event in events:
        channel = CHANNEL_LABELS.get(event.channel, "")
        timeline.append(
            {
                "at": event.created_at.isoformat(),
                "kind": "review",
                "text": " ".join(part for part in (EVENT_LABELS.get(event.type, event.type), channel) if part),
                "by": users.get(event.actor_user_id) if event.actor_user_id else None,
            }
        )
    for entry in edits:
        fields = list(dict.fromkeys(f"{row['place']}: {row['field']}" for row in entry["changes"]))
        verb = "Hoàn tác" if entry["action"] == "restore" else "Sửa"
        timeline.append(
            {
                "at": entry["at"],
                "kind": "edit",
                "text": f"{verb} {', '.join(fields[:4])}{'…' if len(fields) > 4 else ''} "
                f"{CHANNEL_LABELS.get(entry['source'], '')}".strip(),
                "by": entry["by"],
            }
        )
    timeline.sort(key=lambda row: row["at"])

    made = {
        "by": maker.name if maker else None,
        "at": video.created_at.isoformat(),
        "via": made_via(db, video),
        "free": video.written_via == "assistant",
        "group": group.name if group else None,
        "mode": video.mode,
        "platform": video.platform,
    }
    times = {
        "created_at": video.created_at.isoformat(),
        "rendered_at": _when(video.rendered_at),
        "minutes_to_render": round((video.rendered_at - video.created_at).total_seconds() / 60)
        if video.rendered_at
        else None,
        "render_seconds": video.render_seconds
        if video.render_seconds is not None
        else (
            round((last_render.finished_at - last_render.started_at).total_seconds())
            if last_render and last_render.finished_at and last_render.started_at
            else None
        ),
        "last_edit_at": edits[0]["at"] if edits else None,
        "last_edit_by": edits[0]["by"] if edits else None,
    }
    music = {"name": video.music_name, "volume": video.music_volume} if video.music_key else None
    payload = {
        "made": made,
        "voices": voices,
        "voice_sources": dict(sources),
        "mixed_voices": len(sources) > 1,
        "music": music,
        "times": times,
        "timeline": timeline[-TIMELINE_LIMIT:],
        "history": edits,
    }
    payload["text"] = story_text(video_name(video, title), video.id, payload)
    return payload


def story_text(name: str, video_id: int, data: dict) -> str:
    """ "Sao chép hồ sơ video": the card as plain text, times in Vietnam time."""
    made, times = data["made"], data["times"]
    lines = [
        f"Video #{video_id}: {name}",
        f"Tạo bởi: {made['by'] or '?'} lúc {_local(datetime.fromisoformat(made['at']))}, {made['via']}",
        f"Nhóm: {made['group'] or '(không nhóm)'}",
    ]
    if data["voice_sources"]:
        summary = ", ".join(f"{source} {count} cảnh" for source, count in data["voice_sources"].items())
        lines.append(f"Giọng: {summary}{' (trộn nhiều nguồn)' if data['mixed_voices'] else ''}")
        for row in data["voices"]:
            lines.append(f"  - {row['label']}: {row['source']}{' ' + row['voice'] if row['voice'] else ''}")
    if data["music"]:
        lines.append(f"Nhạc: {data['music']['name'] or 'có'} ({data['music']['volume']}%)")
    if times["rendered_at"]:
        lines.append(
            f"Render xong: {_local(datetime.fromisoformat(times['rendered_at']))} "
            f"({times['minutes_to_render']} phút từ lúc tạo"
            + (f", render {round(times['render_seconds'])} giây" if times["render_seconds"] is not None else "")
            + ")"
        )
    lines.append("Dòng thời gian:")
    for row in data["timeline"]:
        who = f" ({row['by']})" if row["by"] else ""
        lines.append(f"  {_local(datetime.fromisoformat(row['at']))} {row['text']}{who}")
    return "\n".join(lines)


@router.get("/{video_id}")
def get_story(video_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    video = db.get(Video, video_id)
    if video is None:
        raise video_not_found()
    return story(db, video)


def _current(video: Video, scenes_by_id: dict[int, Scene], key: str) -> Any:
    parsed = edit_log.parse_scene_key(key)
    if parsed is None:
        return getattr(video, key)
    scene = scenes_by_id.get(parsed[0])
    if scene is None:
        raise ApiError(409, "scene_gone", "Cảnh của lần sửa này đã bị xóa, không hoàn tác được")
    return getattr(scene, parsed[1])


@router.post("/{video_id}/undo/{log_id}")
def undo(
    video_id: int,
    log_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """ "Hoàn tác": every field the entry changed goes back to its old value, if none was edited again since."""
    video = db.get(Video, video_id)
    if video is None:
        raise video_not_found()
    entry = db.scalar(select(EditLog).where(EditLog.id == log_id).options(selectinload(EditLog.user)))
    if entry is None or entry.entity_type != edit_log.VIDEO or entry.entity_id != video.id:
        raise ApiError(404, "edit_log_not_found", "Không tìm thấy lần sửa này trong lịch sử")
    title, scenes = split_scenes(db, video)
    scenes_by_id = {scene.id: scene for scene in ([title] if title else []) + scenes}
    video_fields: dict[str, Any] = {}
    scene_fields: dict[int, dict[str, Any]] = {}
    for key, change in entry.changes.items():
        parsed = edit_log.parse_scene_key(key)
        field = parsed[1] if parsed else key
        if field not in (edit_log.SCENE_RESTORABLE if parsed else edit_log.VIDEO_RESTORABLE):
            continue
        if _current(video, scenes_by_id, key) != change.get("new"):
            place = "video" if parsed is None else "cảnh"
            raise ApiError(
                409,
                "edited_since",
                f"“{FIELD_LABELS.get(field, field)}” của {place} đã được sửa sau lần này, hoàn tác sẽ đè lên bản mới",
            )
        if parsed:
            scene_fields.setdefault(parsed[0], {})[field] = change.get("old")
        else:
            video_fields[field] = change.get("old")
    if not video_fields and not scene_fields:
        raise ApiError(409, "not_restorable", "Lần sửa này không hoàn tác được (chỉ đổi vị trí chữ hoặc tùy chọn)")
    token = edit_log.RESTORING.set(entry.id)
    try:
        payload = None
        if video_fields:
            payload = patch_video(video.id, VideoPatchBody(**video_fields), me, db, storage)
        for scene_id, fields in scene_fields.items():
            if "voice_id" in fields and fields["voice_id"] is None:
                fields["voice_id"] = ""
            # The title's text was already put back by "Không dùng tiêu đề" going off: nothing left to change.
            if all(getattr(scenes_by_id[scene_id], field) == value for field, value in fields.items()):
                continue
            payload = patch_scene(scene_id, ScenePatchBody(**fields), me, db, storage)
    finally:
        edit_log.RESTORING.reset(token)
    db.expire_all()
    return {"video": payload, "story": story(db, db.get(Video, video_id))}
