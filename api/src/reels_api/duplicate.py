"""'Nhân bản y hệt': a copy of a video exactly as it is (script, scenes, layers, sounds, photos, clips, narration,
music, products), with no LLM call. Only its name in the app differs ("… (copy)"); its MP4 is not copied, so the
copy is rendered before it is posted (docs/decisions/2026-11-14-duplicate-video.md)."""

import copy
from pathlib import PurePosixPath

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .models import Scene, SceneLayer, SceneSound, Video, VideoAffiliateProduct
from .storage import DirectoryStorage
from .videos import new_key, split_scenes, video_name

COPY_SUFFIX = " (copy)"
MAX_NAME_LENGTH = 200

# What belongs to the source alone, or to its MP4: left to their defaults on the copy.
_VIDEO_SKIP = {
    "id",
    "created_at",
    "created_by_id",
    "name",
    "mp4_key",
    "mp4_seconds",
    "qc",
    "render_seconds",
    "rendered_signature",
    "rendered_at",
    "clone_source",
    "variant_of_id",
    "suggest_requested_at",
    "suggest_by_id",
    "suggested_at",
    "suggest_error",
}


def copy_name(source_name: str) -> str:
    return source_name[: MAX_NAME_LENGTH - len(COPY_SUFFIX)] + COPY_SUFFIX


class _Files:
    """Copies the source's files into the new video's folder, each once, so deleting either video leaves the other's
    intact. A file gone from storage is dropped rather than pointed at."""

    def __init__(self, storage: DirectoryStorage, video_id: int):
        self.storage, self.video_id, self.copied = storage, video_id, {}

    def __call__(self, key: str | None) -> str | None:
        if not key:
            return key
        if key not in self.copied:
            if not self.storage.exists(key):
                self.copied[key] = None
            else:
                path = PurePosixPath(key)
                target = new_key(self.video_id, path.stem.split("-")[0] or "file", path.suffix.lstrip(".") or "bin")
                self.storage.save_file(target, self.storage.path(key))
                self.copied[key] = target
        return self.copied[key]


def _columns(row, skip: set[str]) -> dict:
    return {
        column.key: copy.deepcopy(getattr(row, column.key))
        for column in row.__table__.columns
        if column.key not in skip
    }


def _with_files(values: dict, files: _Files) -> dict:
    for field, value in values.items():
        if field.endswith("_key") and isinstance(value, str):
            values[field] = files(value)
    return values


def duplicate_video(db: DbSession, storage: DirectoryStorage, source: Video, user_id: int) -> Video:
    title, _ = split_scenes(db, source)
    draft = Video(
        **_columns(source, _VIDEO_SKIP),
        name=copy_name(video_name(source, title)),
        created_by_id=user_id,
    )
    db.add(draft)
    db.flush()
    try:
        _copy_into(db, source, draft, _Files(storage, draft.id))
    except BaseException:
        # Files only stay with the rows: a copy that failed half-way leaves nothing behind.
        storage.delete_prefix(f"videos/{draft.id}")
        raise
    return draft


def _copy_into(db: DbSession, source: Video, draft: Video, files: _Files) -> None:
    for column in Video.__table__.columns:
        if column.key.endswith("_key"):
            setattr(draft, column.key, files(getattr(draft, column.key)))
    scenes = db.scalars(select(Scene).where(Scene.video_id == source.id).order_by(Scene.id)).all()
    for scene in scenes:
        values = _with_files(_columns(scene, {"id", "video_id"}), files)
        if isinstance(values.get("motion"), dict):
            values["motion"] = _with_files(values["motion"], files)
        new_scene = Scene(**values, video_id=draft.id)
        new_scene.layers = [
            SceneLayer(**_with_files(_columns(layer, {"id", "scene_id"}), files)) for layer in scene.layers
        ]
        new_scene.sounds = [SceneSound(**_columns(sound, {"id", "scene_id"})) for sound in scene.sounds]
        db.add(new_scene)
    for product_id in db.scalars(
        select(VideoAffiliateProduct.product_id).where(VideoAffiliateProduct.video_id == source.id)
    ):
        db.add(VideoAffiliateProduct(video_id=draft.id, product_id=product_id))
    db.flush()
