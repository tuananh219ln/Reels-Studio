"""What one job does. Runs inside the per-job child process started by the worker loop (worker.py)."""

import logging
import shutil
import tempfile
import time
import traceback
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from reels_render import RenderError, render_video
from reels_render.errors import FFmpegError
from reels_render.ffmpeg import audio_seconds, find_tools, probe
from reels_render.script import parse_script

from . import (
    affiliate_rounds,
    auto_photos,
    config,
    facebook,
    fanpages,
    hashtags,
    image_providers,
    image_style,
    knowledge,
    llm,
    plans,
    source_keys,
)
from .claude import (
    ClaudeError,
    GeneratedScript,
    build_clone_prompt,
    build_script_prompt,
    generate_script,
)
from .clips import ClipError, frame_at
from .facebook import FacebookError
from .frames import jpeg_bytes
from .imagegen import ImageGenError, generate_image
from .models import Job, KnowledgeTopic, Publication, Scene, Video
from .sessions import now
from .storage import DirectoryStorage
from .tts import TtsError, synthesize, voice_signature
from .uploads import MAX_IMAGE_BYTES, UploadRejected, image_extension
from .video_options import render_options, voice_id, voice_speed
from .videos import (
    LIVE_POST_STATUSES,
    OPEN_POST_STATUSES,
    active_job,
    auto_seconds,
    is_published,
    made_voice_seconds,
    new_key,
    pending_publication,
    refresh_thumbnail,
    render_signature,
    run_checks,
    scene_marks,
    split_scenes,
    spoken,
    text_position,
)

log = logging.getLogger(__name__)

TITLE_SECONDS = 3
# Auto-assign runs in the worker, not in a request, so each scene's search may take longer.


class JobFailure(Exception):
    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.message = message
        self.detail = detail


def work_dir(job_id: int) -> Path:
    """Fixed per job, so the worker loop can remove it even after killing the child."""
    return Path(tempfile.gettempdir()) / f"reels-job-{job_id}"


def run_job(
    job_id: int, factory: sessionmaker, storage: DirectoryStorage, call: Callable[[str, str], str] | None = None
) -> None:
    """`call` replaces the team's LLM (see llm.py) in unit tests that run a job in-process."""
    with factory() as db:
        job = db.get(Job, job_id)
        if job is None or job.status != "running":
            log.warning("Job %s is not running (%s), skipped", job_id, job.status if job else "deleted")
            return
        owner = f"video {job.video_id}" if job.video_id else f"topic group {job.knowledge_topic_id}"
        log.info("Job %s (%s) for %s started", job.id, job.kind, owner)
        try:
            if job.kind in ("script", "clone"):
                run_script_job(db, job, call)
            elif job.kind == "plan":
                run_plan_job(db, job, call)
            elif job.kind == "render":
                run_render_job(db, job, storage)
            elif job.kind == "image":
                run_image_job(db, job, storage)
            elif job.kind == "publish":
                run_publish_job(db, job, storage)
            elif job.kind == "unpublish":
                run_unpublish_job(db, job)
            elif job.kind == "check":
                run_check_job(db, job)
            elif job.kind == "voice":
                run_voice_job(db, job, storage)
            elif job.kind == "photos":
                auto_photos.run(db, job, storage)
            else:
                raise JobFailure(f"Loại job không hỗ trợ: {job.kind}")
        except auto_photos.AutoPhotosFailed as err:
            db.rollback()
            _finish(db, job_id, "failed", str(err))
            log.warning("Job %s failed: %s", job_id, err)
            return
        except JobFailure as err:
            db.rollback()
            _finish(db, job_id, "failed", err.message, err.detail)
            log.warning("Job %s failed: %s\n%s", job_id, err.message, err.detail)
            return
        except Exception:
            db.rollback()
            detail = traceback.format_exc()[-4000:]
            _finish(db, job_id, "failed", "Lỗi không mong đợi trong worker", detail)
            log.exception("Job %s crashed", job_id)
            return
        _finish(db, job_id, "done")
        log.info("Job %s done", job_id)
        if job.kind in ("script", "clone"):
            _queue_photos(db, job)


def _queue_photos(db: DbSession, job: Job) -> None:
    """ "Tự tìm ảnh" after a script: its own job, so a search problem never fails the script. A job a member queued
    for the video in the meantime (one active job per video) wins, and the search is simply not queued."""
    try:
        auto_photos.queue_after_script(db, job)
        db.commit()
    except IntegrityError:
        db.rollback()
        log.info("Job %s: another job is queued for video %s, no photo search", job.id, job.video_id)


def _finish(db: DbSession, job_id: int, status: str, error: str | None = None, detail: str | None = None) -> None:
    db.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(status=status, finished_at=now(), error=error, error_detail=detail or None)
    )
    db.commit()


# --- Script ---


def run_script_job(db: DbSession, job: Job, call: Callable[[str, str], str] | None) -> None:
    video = db.get(Video, job.video_id)
    # A retried job whose script was already saved has nothing to do: no new Claude call,
    # and nothing the members edited meanwhile is overwritten.
    if not video.has_script:
        topic = knowledge.topic_of(db, video)
        if topic is None:
            raise JobFailure("Video chưa thuộc nhóm chủ đề nào trong Kho kiến thức")
        if job.kind == "clone":
            # The snapshot from the moment "Nhân bản" was pressed: later edits of the source do not count.
            prompt = build_clone_prompt(topic.clone_prompt, video.clone_source, topic.banned_words)
        else:
            # A video made from a 30-day plan idea writes to that idea's pain and hook.
            idea = plans.idea_of_video(db, video.id)
            prompt = build_script_prompt(
                topic.script_prompt,
                video.topic,
                topic.banned_words,
                (idea.pain_group, idea.pain, idea.hook) if idea else None,
            )

        call, count_call = _llm(db, job, call)
        try:
            script = generate_script(prompt, f"job {job.id}", count_call, call)
        except ClaudeError as err:
            raise JobFailure(err.message, err.detail) from None
        save_script(db, video, script)
        affiliate_rounds.ask_after_script(db, video, job.created_by_id)
        db.commit()


def _llm(
    db: DbSession, job: Job, call: Callable[[str, str], str] | None
) -> tuple[Callable[[str, str], str], Callable[[], None]]:
    """The LLM call of a script, clone or plan job, and what counts each call on the job."""
    if call is None:
        # The provider chosen on /settings/ai when the job starts; the job remembers which one wrote.
        target = llm.active_target(db)
        db.execute(update(Job).where(Job.id == job.id).values(llm_provider=target.provider, llm_model=target.model))
        db.commit()

        def call(prompt: str, label: str) -> str:
            return llm.complete(target, prompt, label)

    def count_call() -> None:
        db.execute(update(Job).where(Job.id == job.id).values(claude_calls=Job.claude_calls + 1))
        db.commit()

    return call, count_call


# --- Plan ---


def run_plan_job(db: DbSession, job: Job, call: Callable[[str, str], str] | None) -> None:
    """ "Tạo bằng AI" on /knowledge: the whole 30-day plan, kept as a draft for a member to look at; the saved plan
    is replaced only when a member saves the draft."""
    topic = db.get(KnowledgeTopic, job.knowledge_topic_id)
    if topic is None:
        raise JobFailure("Nhóm chủ đề đã bị xoá")
    call, count_call = _llm(db, job, call)
    try:
        ideas = plans.generate(topic, f"job {job.id}", count_call, call)
    except ClaudeError as err:
        raise JobFailure(err.message, err.detail) from None
    topic = db.get(KnowledgeTopic, job.knowledge_topic_id, with_for_update=True, populate_existing=True)
    topic.plan_draft = plans.draft_payload(job.id, ideas)
    db.commit()


def save_script(db: DbSession, video: Video, script: GeneratedScript) -> None:
    video.has_script = True
    video.title_options = script.titles
    video.caption = script.caption
    video.hashtags = script.hashtags
    video.affiliates = script.affiliates
    video.pinned_comment = script.pinned_comment
    video.self_review = script.self_review
    video.music_suggestions = script.music_suggestions
    db.add(
        Scene(
            video_id=video.id,
            is_title=True,
            position=0,
            text=script.titles[0],
            seconds=TITLE_SECONDS,
            seconds_auto=True,
            keywords=script.title_keywords,
            keywords_en=script.title_keywords_en,
            image_prompt=script.title_image_prompt,
            voice_text=script.title_voice,
        )
    )
    for position, scene in enumerate(script.scenes, start=1):
        db.add(
            Scene(
                video_id=video.id,
                is_title=False,
                position=position,
                text=scene.text,
                seconds=scene.seconds,
                seconds_auto=True,
                keywords=scene.keywords,
                keywords_en=scene.keywords_en,
                image_prompt=scene.image_prompt,
                voice_text=scene.voice,
            )
        )


# --- Render ---

MUSIC_UNREADABLE = "File nhạc không đọc được"


def _checked_music(video: Video, storage: DirectoryStorage, folder: Path) -> Path | None:
    """The MP3 for this render, or None for a silent video; a file FFmpeg cannot read fails the job here,
    with a clear reason, instead of as an FFmpeg error in the middle of the render."""
    if not video.music_key:
        return None
    if not storage.exists(video.music_key):
        raise JobFailure(MUSIC_UNREADABLE, "Không thấy file nhạc trong storage, hãy tải nhạc lên lại")
    music = storage.copy_to(video.music_key, folder / "music.mp3")
    try:
        streams = probe(find_tools().ffprobe, music).get("streams", [])
    except FFmpegError as err:
        raise JobFailure(MUSIC_UNREADABLE, err.stderr_tail) from None
    if not any(stream.get("codec_type") == "audio" for stream in streams):
        raise JobFailure(MUSIC_UNREADABLE, "File không có luồng âm thanh")
    return music


def _image_model(provider: str) -> str:
    return config.image_gen_cf_model() if provider == "cloudflare" else config.image_gen_model()


def _scene_label(scene: Scene, index: int) -> str:
    return "Cảnh tiêu đề" if scene.is_title else f"Cảnh {index}"


def make_voices(db: DbSession, video: Video, scenes: list[Scene], storage: DirectoryStorage) -> None:
    """Narration for every scene that has something to read but no MP3 made from it yet. Each MP3 is committed at once,
    so a retry after a failure pays ElevenLabs only for the scenes still missing."""
    for index, scene in enumerate(scenes):
        text = spoken(video, scene)
        if not text or (made_voice_seconds(video, scene) is not None and storage.exists(scene.voice_key)):
            continue
        label = _scene_label(scene, index)
        try:
            data = synthesize(text, source_keys.get(db, "elevenlabs"), voice_id(video), voice_speed(video))
        except TtsError as err:
            raise JobFailure(f"{label}: {err.message}", err.detail) from None
        key = new_key(video.id, f"voice-{scene.id}", "mp3")
        storage.save_bytes(key, data)
        try:
            seconds = audio_seconds(find_tools().ffprobe, storage.path(key))
        except FFmpegError:
            seconds = None
        if seconds is None:
            storage.delete(key)
            raise JobFailure(f"{label}: ElevenLabs trả file lời đọc không đọc được, thử lại sau")
        old = scene.voice_key
        scene.voice_key, scene.voice_signature, scene.voice_seconds = (
            key,
            voice_signature(text, voice_id(video), voice_speed(video)),
            seconds,
        )
        # "Tự khớp lời đọc": the scene now lasts as long as its narration, shorter or longer than before.
        if scene.seconds_auto:
            scene.seconds = auto_seconds(seconds)
        db.commit()
        if old and old != key:
            storage.delete(old)
        log.info("Narration for video %s %s: %.1fs", video.id, label, seconds)


def run_voice_job(db: DbSession, job: Job, storage: DirectoryStorage) -> None:
    """ "Tạo giọng thật" in the preview: only the narration a render would make, kept for that render to reuse."""
    video = db.get(Video, job.video_id)
    title, scenes = split_scenes(db, video)
    make_voices(db, video, [scene for scene in (title, *scenes) if scene is not None], storage)


def run_render_job(db: DbSession, job: Job, storage: DirectoryStorage) -> None:
    video = db.get(Video, job.video_id)
    title, scenes = split_scenes(db, video)
    if title is None or not scenes:
        raise JobFailure("Video chưa có kịch bản đủ để render")
    folder = work_dir(job.id)
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    try:
        make_voices(db, video, [title, *scenes], storage)
        # Narration lengthens its scene, so the total is only known now.
        blocking = run_checks(db, video, title, scenes).blocking
        if blocking:
            raise JobFailure(
                f"Chưa render được: {blocking[0].message}",
                "Lời đọc làm cảnh dài thêm: hãy rút gọn lời đọc hoặc bớt cảnh",
            )

        def entry(scene: Scene, index: int) -> dict:
            label = _scene_label(scene, index)
            # No "keywords": every photo or clip is already chosen, the renderer must never search stock itself.
            if scene.video_key:
                if not storage.exists(scene.video_key):
                    raise JobFailure(f"{label} chưa có video trong storage, hãy tải video lên lại rồi render")
                extension = scene.video_key.rsplit(".", 1)[-1]
                clip = storage.copy_to(scene.video_key, folder / f"clip-{index:02d}.{extension}")
                data = {
                    "text": scene.text,
                    "seconds": scene.seconds,
                    "video": clip.name,
                    "video_start": scene.video_start,
                    "video_speed": scene.video_speed,
                }
            else:
                if not scene.image_key or not storage.exists(scene.image_key):
                    raise JobFailure(f"{label} chưa có ảnh trong storage, hãy gán lại ảnh rồi render")
                image = storage.copy_to(
                    scene.image_key, folder / f"image-{index:02d}.{scene.image_key.rsplit('.', 1)[-1]}"
                )
                data = {"text": scene.text, "seconds": scene.seconds, "image": image.name}
            if position := text_position(video, scene):
                data["text_position"] = position
            if spoken(video, scene):
                data["voice"] = storage.copy_to(scene.voice_key, folder / f"voice-{index:02d}.mp3").name
                data["voice_text"] = spoken(video, scene)
            return data

        data = {"title": entry(title, 0), "scenes": [entry(scene, index) for index, scene in enumerate(scenes, 1)]}
        signature = render_signature(video, title, scenes)
        music = _checked_music(video, storage, folder)
        output = folder / "video.mp4"
        started = time.monotonic()
        try:
            render_video(
                parse_script(data, base_dir=folder),
                output,
                music=music,
                music_volume=video.music_volume / 100,
                options=render_options(video),
            )
            seconds = float(probe(find_tools().ffprobe, output)["format"]["duration"])
        except FFmpegError as err:
            raise JobFailure("FFmpeg lỗi khi render video", err.stderr_tail) from None
        except RenderError as err:
            raise JobFailure(str(err)) from None
        elapsed = time.monotonic() - started

        key = new_key(video.id, "video", "mp4")
        storage.save_file(key, output)
        old = video.mp4_key
        video.mp4_key, video.mp4_seconds, video.render_seconds = key, seconds, round(elapsed, 1)
        video.rendered_signature, video.rendered_at = signature, now()
        db.commit()
        # The old MP4 stays playable until the new one is committed.
        if old and old != key:
            storage.delete(old)
        log.info("Job %s rendered %.1fs of video in %.1fs", job.id, seconds, elapsed)
    finally:
        shutil.rmtree(folder, ignore_errors=True)


# --- Publish ---

# Facebook refuses a scheduled time less than 10 minutes away.
MIN_SCHEDULE_LEAD = timedelta(minutes=10)
# After this long, a reel Facebook was asked to publish and still has not is taken as dropped.
SETTLE_TIME = timedelta(minutes=30)


def run_publish_job(db: DbSession, job: Job, storage: DirectoryStorage) -> None:
    video = db.get(Video, job.video_id)
    post = pending_publication(db, video.id)
    if post is None:
        return
    try:
        # An attempt before this one may have reached Facebook whatever it reported, so its reel decides first.
        page = fanpages.load_page(db, post.fanpage_id)
        status = facebook.reel_status(page, post.remote_id) if post.remote_id else None
        asked = status is not None and post.finish_sent_at is not None and not facebook.is_failed(status)
        if asked and facebook.is_busy(status):
            status = facebook.wait_until_live(page, post.remote_id)
        if status is None or not facebook.is_live(status):
            _check_publishable(db, video, post, storage)
            # A reel is finished again only if it holds this very MP4; a new render gets a reel of its own.
            if status is None or not facebook.is_uploaded(status) or post.remote_mp4_key != video.mp4_key:
                # Facebook may still publish a reel it was asked to, and a new one would then be a second post.
                if asked and now() - post.finish_sent_at < SETTLE_TIME:
                    raise JobFailure("Facebook có thể vẫn đang đăng bản trước, hãy xem Page, đợi 30 phút rồi Thử lại")
                post.remote_id, upload_url = facebook.start_upload(page)
                post.remote_mp4_key, post.finish_sent_at = video.mp4_key, None
                # _check_publishable made sure the MP4 is a render of the current scenes.
                post.scene_marks = scene_marks(video, *split_scenes(db, video))
                db.commit()
                facebook.upload(page, upload_url, storage.path(video.mp4_key))
            post.finish_sent_at = now()
            db.commit()
            _finish_reel(db, page, video, post)
            status = facebook.wait_until_live(page, post.remote_id)
    except FacebookError as err:
        raise JobFailure(err.message, err.detail) from None
    # What Facebook says counts: after a lost answer it can differ from what the member asked for last.
    post.status = "scheduled" if facebook.is_scheduled(status) else "published"
    post.scheduled_at = (facebook.scheduled_time(status) or post.scheduled_at) if post.status == "scheduled" else None
    post.published_at = now()
    db.commit()
    _set_cover(page, post, storage)
    log.info("Job %s posted video %s to Facebook as %s", job.id, video.id, post.remote_id)


def _set_cover(page: facebook.Page, post: Publication, storage: DirectoryStorage) -> None:
    """The reel's cover is the title scene: the first frame of the MP4 the reel holds, so it matches what was posted
    even when the title changed since. Set once the reel is live or scheduled, since Facebook may not take a cover
    for a reel it is still processing. A cover that cannot be set leaves Facebook's own pick: the post stands."""
    try:
        if not post.remote_mp4_key or not storage.exists(post.remote_mp4_key):
            raise ClipError("MP4 của bài đăng không còn trong storage")
        cover = jpeg_bytes(frame_at(storage.path(post.remote_mp4_key), 0))
        facebook.set_cover(page, post.remote_id, cover)
    except (ClipError, FacebookError) as err:
        log.warning("Reel %s keeps the cover Facebook picked: %s", post.remote_id, err)


def run_unpublish_job(db: DbSession, job: Job) -> None:
    """Facebook publishes a scheduled reel by itself, so stopping one means deleting it there. Facebook's own answer
    says whether the post was ever public: "Đã hủy" must not stand for a reel people saw."""
    post = db.get(Publication, job.publication_id)
    if post is None or post.status not in OPEN_POST_STATUSES:
        return
    went_live = is_published(post)
    try:
        page = fanpages.load_page(db, post.fanpage_id)
        status = facebook.reel_status(page, post.remote_id)
        if status is not None:
            went_live = went_live or (facebook.is_live(status) and not facebook.is_scheduled(status))
            facebook.delete_reel(page, post.remote_id)
    except FacebookError as err:
        raise JobFailure(err.message, err.detail) from None
    _close(post, went_live, job.created_by_id)
    db.commit()
    log.info("Job %s took reel %s off Facebook as %s", job.id, post.remote_id, post.status)


def _close(post: Publication, went_live: bool, by: int | None) -> None:
    """ "Đã hủy" must not stand for a reel people may have seen."""
    post.status = "deleted" if went_live else "cancelled"
    post.closed_at, post.closed_by_id = now(), by


# Facebook publishes a scheduled reel by itself; the check after its time gives it this long.
CHECK_DELAY = timedelta(minutes=10)


def queue_post_checks(db: DbSession) -> None:
    """Queue one check of each scheduled reel whose time has passed, so a reel cancelled, moved or dropped on Facebook
    is not shown as posted. Once per scheduled time, failed or not: a member retries it or presses "Kiểm tra"."""
    due = db.scalars(
        select(Publication).where(
            Publication.status == "scheduled",
            Publication.remote_id.is_not(None),
            Publication.scheduled_at <= now() - CHECK_DELAY,
            or_(Publication.checked_at.is_(None), Publication.checked_at < Publication.scheduled_at),
        )
    ).all()
    for post in due:
        # One active job per video: the check waits for the next round.
        if active_job(db, post.video_id) is not None:
            continue
        try:
            with db.begin_nested():
                db.add(
                    Job(
                        video_id=post.video_id,
                        kind="check",
                        status="queued",
                        created_by_id=post.created_by_id,
                        publication_id=post.id,
                    )
                )
                post.checked_at = now()
        except IntegrityError:
            continue
        log.info("Queued a check of post %s on Facebook", post.id)


def run_check_job(db: DbSession, job: Job) -> None:
    """Read the reel on Facebook and record what Facebook says. A member may have cancelled, moved or deleted it in
    Meta Business Suite, or Facebook dropped it, and nothing else tells the app. Never changes anything on Facebook."""
    post = db.get(Publication, job.publication_id)
    if post is None or post.status not in LIVE_POST_STATUSES or post.remote_id is None:
        return
    try:
        page = fanpages.load_page(db, post.fanpage_id)
        status = facebook.reel_status(page, post.remote_id)
    except FacebookError as err:
        raise JobFailure(err.message, err.detail) from None
    post.checked_at = now()
    if status is not None and facebook.is_live(status):
        if facebook.is_scheduled(status):
            post.status = "scheduled"
            post.scheduled_at = facebook.scheduled_time(status) or post.scheduled_at
        else:
            post.status = "published"
    elif status is None or not facebook.is_busy(status):
        _close(post, is_published(post), None)
    db.commit()
    log.info("Job %s found reel %s %s on Facebook", job.id, post.remote_id, post.status)


def _finish_reel(db: DbSession, page: facebook.Page, video: Video, post: Publication) -> None:
    description = hashtags.post_text(video.caption, video.hashtags)
    try:
        facebook.finish(page, post.remote_id, description, post.scheduled_at)
    except FacebookError as err:
        # Only a refusal proves Facebook will not publish it; a lost or 5xx answer proves nothing.
        if 400 <= err.status < 500:
            post.finish_sent_at = None
            db.commit()
        raise


def _check_publishable(db: DbSession, video: Video, post: Publication, storage: DirectoryStorage) -> None:
    """Also covers "Thử lại", which does not pass through the publish endpoint."""
    title, scenes = split_scenes(db, video)
    if video.rendered_signature != render_signature(video, title, scenes):
        raise JobFailure("MP4 chưa cập nhật theo bản sửa, hãy render lại rồi đăng")
    if post.scheduled_at is not None and post.scheduled_at < now() + MIN_SCHEDULE_LEAD:
        raise JobFailure("Giờ hẹn đã qua hoặc còn dưới 10 phút, hãy chọn giờ khác rồi bấm đăng lại")
    if not video.mp4_key or not storage.exists(video.mp4_key):
        raise JobFailure("Không thấy file MP4 trong storage, hãy render lại rồi đăng")


# --- Images ---


def run_image_job(db: DbSession, job: Job, storage: DirectoryStorage) -> None:
    """AI photos for the scenes that have neither a photo nor a clip yet, or for the job's one scene.

    Every finished scene is committed at once, so a cancelled job (or a dead worker) keeps
    the photos already paid for, and pressing the button again only pays for the scenes
    still missing one. A prompt the provider refuses fails only its scene: the reason stays on
    the scene's `image_error`, where members see it. Only a provider-wide failure (no key,
    quota) fails the job, after the scenes already done.

    A job for one scene ("Tạo ảnh AI" / "Tạo lại ảnh AI" on its card) makes that scene's photo
    whatever it has, replacing its photo or clip; any failure fails the job, and the scene keeps
    what it had.
    """
    video = db.get(Video, job.video_id)
    title, scenes = split_scenes(db, video)
    if title is None:
        raise JobFailure("Video chưa có kịch bản đủ để tạo ảnh")
    ordered = [title, *scenes]
    if job.scene_id is not None:
        targets = [(index, scene) for index, scene in enumerate(ordered) if scene.id == job.scene_id]
        if not targets:
            raise JobFailure("Cảnh cần tạo ảnh không còn trong video (đã bị xoá)")
    else:
        targets = [(index, scene) for index, scene in enumerate(ordered) if not (scene.image_key or scene.video_key)]
    provider = job.image_provider or image_providers.default(db)
    style = image_style.get(db)
    for index, scene in targets:
        label = _scene_label(scene, index)
        prompt = scene.image_prompt.strip() or (scene.text.strip().splitlines() or [""])[0].strip()
        try:
            if not prompt:
                raise ImageGenError("Cảnh chưa có prompt ảnh, cũng chưa có chữ để tạo ảnh")
            # Counted before the call, like the script job counts Claude: a killed job keeps the count.
            db.execute(update(Job).where(Job.id == job.id).values(image_calls=Job.image_calls + 1))
            db.commit()
            data = generate_image(image_style.styled(prompt, style), source_keys.get(db, provider), provider)
            if len(data) > MAX_IMAGE_BYTES:
                raise ImageGenError(
                    f"Ảnh {image_providers.LABELS.get(provider, provider)} trả về quá 15 MB, hãy bấm tạo lại"
                )
            try:
                extension = image_extension(data)
            except UploadRejected as err:
                raise ImageGenError(str(err)) from None
        except ImageGenError as err:
            if err.fatal:
                raise JobFailure(err.message, err.detail) from None
            if job.scene_id is not None:
                # The scene keeps its photo or clip; a scene without one shows why.
                if not (scene.image_key or scene.video_key):
                    scene.image_error = err.message
                    db.commit()
                raise JobFailure(f"{label}: {err.message}", err.detail) from None
            scene.image_error = err.message
            db.commit()
            log.warning("Image job %s: %s failed: %s", job.id, label, err.message)
            continue
        old = [scene.image_key, scene.video_key]
        key = new_key(video.id, f"scene-{scene.id}", extension)
        storage.save_bytes(key, data)
        scene.image_key, scene.image_source, scene.image_error = key, f"ai:{_image_model(provider)}", None
        scene.image_auto = False
        # A photo replaces the scene's clip: a scene shows one or the other.
        scene.video_key, scene.video_seconds, scene.video_start, scene.video_speed = None, None, 0, 1
        if scene.is_title:
            refresh_thumbnail(db, storage, video, scene)
        db.commit()
        for stale in old:
            if stale and stale != key:
                storage.delete(stale)
        log.info("Image job %s: %s stored", job.id, label)
