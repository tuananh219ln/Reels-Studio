"""Footage tools for an always-on assistant (the MCP): list scenes that lack media, find clip candidates, attach one.

The assistant looks at the frames itself, so this path makes no LLM call of the team's. Candidates are downloaded into
a short-lived cache of the api host; attaching re-uses the same cut as the automatic job (`auto_footage.attach`).
"""

import json
import math
import re
import secrets
import shutil
import tempfile
import time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import auto_footage, clips, source_keys, stock_clips, youtube_footage
from .errors import ApiError
from .models import Scene, Session, Video
from .storage import DirectoryStorage
from .uploads import UploadRejected
from .videos import ensure_unlocked, lock_scene, split_scenes

SOURCES = ("youtube", *stock_clips.SOURCES)
CACHE = Path(tempfile.gettempdir()) / "reels_footage_candidates"
TTL_SECONDS = 3600
MAX_CACHED = 30
CANDIDATES_PER_CALL = 2
BUDGET_SECONDS = 100
CANDIDATE_ID = re.compile(r"[0-9a-f]{16}")


def missing(db: DbSession, me: Session, video_id: int | None = None, upgrade_photos: bool = False) -> dict:
    """Scenes of the member's videos with no photo or clip (and, on request, scenes holding only an automatic photo)."""
    query = select(Video).where(Video.created_by_id == me.user_id).order_by(Video.id.desc()).limit(200)
    if video_id is not None:
        query = select(Video).where(Video.id == video_id)
    rows = []
    for video in db.scalars(query):
        title, content = split_scenes(db, video)
        for scene in [title, *content] if title else content:
            if video.mode == "single" and not scene.is_title:
                continue
            if scene.video_key or not (scene.keywords or scene.keywords_en):
                continue
            if scene.image_key and not (upgrade_photos and scene.image_auto):
                continue
            rows.append(
                {
                    "video_id": video.id,
                    "topic": video.topic,
                    "scene_id": scene.id,
                    "title": scene.is_title,
                    "text": scene.text,
                    "voice": scene.voice_text,
                    "keywords": scene.keywords,
                    "keywords_en": scene.keywords_en,
                    "has_photo": bool(scene.image_key),
                }
            )
    return {"scenes": rows[:100], "total": len(rows)}


def _purge() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    folders = sorted(CACHE.iterdir(), key=lambda path: path.stat().st_mtime)
    now = time.time()
    for path in folders[: max(0, len(folders) - MAX_CACHED + CANDIDATES_PER_CALL)] + [
        path for path in folders if now - path.stat().st_mtime > TTL_SECONDS
    ]:
        shutil.rmtree(path, ignore_errors=True)


def _scene_for(db: DbSession, scene_id: int) -> tuple[Video, Scene]:
    scene = db.get(Scene, scene_id)
    if scene is None:
        raise ApiError(404, "scene_deleted", "Cảnh này đã bị xóa")
    video = db.get(Video, scene.video_id)
    if video.mode == "single" and not scene.is_title:
        raise ApiError(
            409,
            "single_backdrop",
            "Video xuyên suốt chỉ dùng clip cho cảnh tiêu đề (nền chung); cảnh này dùng ảnh chèn, hãy tìm ảnh kho",
        )
    return video, scene


def find(db: DbSession, scene_id: int, keyword: str, source: str) -> tuple[list[dict], list[tuple[str, bytes]]]:
    """Download up to two unused candidates for the keyword and return them with one frame per possible window."""
    if source not in SOURCES:
        raise ApiError(422, "invalid_source", "Nguồn clip phải là youtube, pexels hoặc pixabay")
    video, scene = _scene_for(db, scene_id)
    key = "" if source == "youtube" else source_keys.get(db, source)
    if source != "youtube" and not key:
        raise ApiError(409, "missing_key", f"Chưa cấu hình key {source}; thử nguồn khác")
    used = set(db.scalars(select(Scene.image_source).where(Scene.video_id == video.id, Scene.id != scene.id)))
    length = auto_footage.scene_length(video, scene)
    _purge()
    try:
        hits = youtube_footage.search(keyword) if source == "youtube" else stock_clips.search(source, keyword, 20, key)
    except (youtube_footage.FootageError, stock_clips.ClipSearchError) as err:
        raise ApiError(502, "footage_search_failed", str(err)) from None
    found: list[dict] = []
    images: list[tuple[str, bytes]] = []
    started = time.monotonic()
    for hit in hits:
        url = hit if isinstance(hit, str) else hit.url
        if url in used or len(found) >= CANDIDATES_PER_CALL or time.monotonic() - started > BUDGET_SECONDS:
            continue
        identifier = secrets.token_hex(8)
        folder = CACHE / identifier
        folder.mkdir(parents=True)
        try:
            if source == "youtube":
                path = youtube_footage.download(url, folder)
            else:
                path = folder / "source.mp4"
                path.write_bytes(stock_clips.download(hit, 30))
            sample = clips.probe_sample(path)
            starts = auto_footage.windows(sample, length)
            if starts is None:
                raise clips.ClipError("Clip quá ngắn hoặc quá dài cho cảnh này")
            frames = [auto_footage._vertical_frame(path, sample, start + 0.5 * length) for start in starts]
        except (
            youtube_footage.FootageError,
            stock_clips.ClipSearchError,
            clips.ClipError,
            UploadRejected,
            OSError,
        ):
            shutil.rmtree(folder, ignore_errors=True)
            continue
        (folder / "meta.json").write_text(
            json.dumps({"scene_id": scene.id, "url": url, "length": length, "starts": starts, "path": path.name})
        )
        found.append(
            {
                "candidate": identifier,
                "source": source,
                "url": url,
                "seconds": round(sample.seconds, 1),
                "clip_seconds": length,
                "windows": [{"window": index, "start": start} for index, start in enumerate(starts)],
            }
        )
        images += [(f"Ứng viên {identifier[:4]} · đoạn {index}", frame) for index, frame in enumerate(frames)]
    return found, images


def use(db: DbSession, storage: DirectoryStorage, scene_id: int, candidate: str, window: int) -> None:
    """Cut the chosen window of a cached candidate into the scene (replacing its photo or clip)."""
    if not CANDIDATE_ID.fullmatch(candidate):
        raise ApiError(422, "invalid_candidate", "Mã ứng viên không hợp lệ")
    folder = CACHE / candidate
    try:
        meta = json.loads((folder / "meta.json").read_text())
        path = folder / meta["path"]
        assert path.is_file() and meta["scene_id"] == scene_id
    except (OSError, ValueError, KeyError, AssertionError):
        raise ApiError(404, "candidate_expired", "Ứng viên đã hết hạn hoặc thuộc cảnh khác, hãy tìm lại") from None
    starts = meta["starts"]
    if type(window) is not int or not 0 <= window < len(starts):
        raise ApiError(422, "invalid_window", f"Đoạn phải từ 0 đến {len(starts) - 1}")
    video, scene = lock_scene(db, scene_id)
    ensure_unlocked(db, video)
    if not math.isfinite(meta["length"]):
        raise ApiError(422, "invalid_candidate", "Mã ứng viên không hợp lệ")
    try:
        sample = clips.probe_sample(path)
        old = auto_footage.attach(db, storage, video, scene, path, sample, starts[window], meta["length"], meta["url"])
    except (clips.ClipError, UploadRejected, OSError) as err:
        raise ApiError(422, "invalid_video", f"Không cắt được đoạn này: {err}") from None
    db.commit()
    for key in old:
        storage.delete(key)
    shutil.rmtree(folder, ignore_errors=True)
