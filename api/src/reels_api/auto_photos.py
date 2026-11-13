""" "Tự tìm ảnh": after a script is written, fill scenes without media from the free stock libraries by default.

With the opt-in auto_footage switch, first search for clips and select a segment using the active vision model;
only scenes without a suitable clip continue to the photo search below.

A job of its own (kind "photos"), queued when a script or clone job finishes, so a search problem never fails the
script. It uses the picker's rules: tall photos big enough for the frame, never one another scene shows, sources in
the video's topic group's order ("Thứ tự nguồn ảnh"; else the app's: Pexels, Unsplash, Pixabay, Wikimedia, Openverse)
minus those turned off or without a key; a source that fails (Unsplash out of calls, say) is not asked again in the
same job. A photo whose licence asks for credit keeps it on the scene, which then warns. It never generates AI photos. Each photo is stored with `image_auto`, shown
as "Tự chọn, kiểm tra lại" until a member changes it: stock libraries often show the wrong dish for Vietnamese food.
The team can turn it off on Cài đặt › Nguồn tư liệu.
"""

import logging
import time

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import auto_footage
from .models import AppSetting, Job, Scene, Video
from .storage import DirectoryStorage
from .videos import new_key, refresh_thumbnail, split_scenes

log = logging.getLogger(__name__)

SETTING_KEY = "auto_photos"
SECONDS_PER_SCENE = 20


class AutoPhotosFailed(Exception):
    """Every usable source failed; the message is shown to members."""


def enabled(db: DbSession) -> bool:
    setting = db.get(AppSetting, SETTING_KEY)
    return setting.value is not False if setting else True


def save(db: DbSession, on: bool, user_id: int) -> None:
    setting = db.get(AppSetting, SETTING_KEY)
    if setting is None:
        db.add(AppSetting(key=SETTING_KEY, value=on, updated_by_id=user_id))
    else:
        setting.value, setting.updated_by_id = on, user_id


def queue_after_script(db: DbSession, job: Job) -> None:
    """Called once a script or clone job is done; the caller commits. Off on the settings page: nothing."""
    if enabled(db):
        db.add(Job(video_id=job.video_id, kind="photos", status="queued", created_by_id=job.created_by_id))


def run(db: DbSession, job: Job, storage: DirectoryStorage) -> None:
    # The picker's clients and rules live with its routes; imported here to keep jobs free of the web layer at load.
    from . import routes_videos

    video = db.get(Video, job.video_id)
    title, scenes = split_scenes(db, video)
    if title is None:
        return
    off = routes_videos.stock_turned_off(db)
    order = routes_videos.stock_order(db, video)
    alive = [source for source in order if source not in off and routes_videos.stock_configured(source, db)]
    used = set(
        db.scalars(select(Scene.image_source).where(Scene.video_id == video.id, Scene.image_source.is_not(None)))
    )
    last_error = ""
    missing = 0
    footage = auto_footage.Finder(db, job, storage, video, order, off, used) if auto_footage.enabled(db) else None
    for scene in [title, *scenes]:
        if scene.image_key or scene.video_key:
            continue
        if footage and footage.fill(scene):
            continue
        photo = None
        for source in list(alive):
            client, error_type = routes_videos._stock_client(source, db)
            # Wikimedia and Openverse index Vietnamese titles, the others English; each list backs the other up.
            keywords = routes_videos.stock_keywords(source, list(scene.keywords), list(scene.keywords_en))
            if not keywords:
                break
            try:
                photo = client.find_photo(
                    keywords, time.monotonic() + SECONDS_PER_SCENE, avoid=used, orientation="vertical"
                )
            except error_type as err:
                log.warning("Photos job %s: %s failed: %s", job.id, source, err.message)
                alive.remove(source)
                last_error = err.message
                continue
            if photo is not None:
                break
        if photo is None:
            missing += 1
            continue
        key = new_key(video.id, f"scene-{scene.id}", photo.extension)
        storage.save_bytes(key, photo.data)
        scene.image_key, scene.image_source, scene.image_error, scene.image_auto = key, photo.url, None, True
        scene.image_credit = {"url": photo.url, **photo.credit} if photo.credit else None
        used.add(photo.url)
        if scene.is_title:
            refresh_thumbnail(db, storage, video, scene)
        db.commit()
    if missing and not alive and last_error:
        raise AutoPhotosFailed(f"Không tự tìm được ảnh: {last_error}")
