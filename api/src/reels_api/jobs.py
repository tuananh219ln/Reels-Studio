"""What one job does. Runs inside the per-job child process started by the worker loop (worker.py)."""

import logging
import shutil
import tempfile
import time
import traceback
from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from PIL import Image, ImageOps
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from reels_render import RenderError, render_video
from reels_render.errors import FFmpegError
from reels_render.ffmpeg import audio_seconds, find_tools, probe
from reels_render.script import parse_script

from . import (
    affiliate_rounds,
    article_images,
    article_posts,
    articles,
    auto_approve,
    auto_photos,
    autoedit,
    brands,
    config,
    facebook,
    fanpages,
    footage,
    google_tts_quota,
    hashtags,
    ig_publish,
    image_edit,
    image_providers,
    image_style,
    instagram,
    knowledge,
    llm,
    metrics,
    motion,
    outro,
    pinned,
    plans,
    qc,
    reference,
    render_nodes,
    review,
    revise,
    rework,
    service_usage,
    slot_comments,
    source_keys,
    text_looks,
    tiktok_publish,
    youtube_connections,
    youtube_publish,
)
from .claude import (
    BACKDROP_FORMAT,
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
from .models import (
    AffiliateAccount,
    Article,
    Fanpage,
    Job,
    KnowledgeTopic,
    Publication,
    Scene,
    TopicPlanItem,
    Video,
    VideoNote,
    VideoReference,
)
from .sessions import now
from .storage import DirectoryStorage
from .tts import TtsError, all_keys_failed, is_google, service_name, synthesize, voice_signature
from .tts import key_name as tts_key_name
from .uploads import MAX_IMAGE_BYTES, UploadRejected, image_extension
from .video_options import effective, render_options, scene_voice, text_hold, voice_pause, voice_speed
from .videos import (
    LIVE_POST_STATUSES,
    OPEN_POST_STATUSES,
    active_job,
    auto_seconds,
    blur_of,
    drawn_layers,
    drop_original,
    half_layer,
    is_backdrop,
    is_card_layer,
    is_half_layer,
    is_published,
    layer_fields,
    layer_photo_key,
    made_voice_seconds,
    new_key,
    pending_publication,
    photo_fit,
    refresh_thumbnail,
    render_signature,
    reveal_steps,
    run_checks,
    scene_marks,
    sound_fields,
    split_scenes,
    spoken,
    text_position,
    title_of,
    title_poster_second,
)
from .videos import content_types as team_content_types

log = logging.getLogger(__name__)

TITLE_SECONDS = 3
# Auto-assign runs in the worker, not in a request, so each scene's search may take longer.


class JobFailure(Exception):
    """`retryable`: the reason may pass (the network, Facebook's own error), so an article's post is tried again by
    itself (article_posts.plan_retry); every other failure waits for a member's "Thử lại"."""

    def __init__(self, message: str, detail: str = "", retryable: bool = False):
        super().__init__(message)
        self.message = message
        self.detail = detail
        self.retryable = retryable


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
        owner = (
            f"video {job.video_id}"
            if job.video_id
            else f"article {job.article_id}"
            if job.article_id
            else f"topic group {job.knowledge_topic_id}"
        )
        log.info("Job %s (%s) for %s started", job.id, job.kind, owner)
        try:
            if job.kind in review.POSTING_JOBS and job.video_id is not None and (reason := review.skip_reason(db, job)):
                raise JobFailure(reason)
            if job.kind in ("script", "clone"):
                run_script_job(db, job, call, storage)
            elif job.kind == "learn":
                run_learn_job(db, job, storage, call)
            elif job.kind == "plan":
                run_plan_job(db, job, call)
            elif job.kind == text_looks.JOB_KIND:
                run_text_look_job(db, job, call)
            elif job.kind == "article_caption":
                run_article_caption_job(db, job, call)
            elif job.kind == slot_comments.JOB_KIND:
                llm_call, count_call = _llm(db, job, call)
                slot_comments.run_job(db, job, llm_call, count_call)
            elif job.kind == "render":
                run_render_job(db, job, storage)
            elif job.kind == "image":
                run_image_job(db, job, storage)
            elif job.kind == "article_image":
                run_article_image_job(db, job, storage)
            elif job.kind == "image_edit":
                run_image_edit_job(db, job, storage)
            elif job.kind == "image_marks":
                run_image_marks_job(db, job, storage)
            elif job.kind == "publish":
                run_publish_job(db, job, storage)
            elif job.kind == "unpublish":
                run_unpublish_job(db, job)
            elif job.kind == "tiktok_publish":
                try:
                    tiktok_publish.run(db, job, storage)
                except tiktok_publish.PublishFailed as err:
                    raise JobFailure(err.message, err.detail) from None
            elif job.kind == "ig_publish":
                try:
                    ig_publish.run(db, job, storage)
                except ig_publish.PublishFailed as err:
                    raise JobFailure(err.message, err.detail) from None
            elif job.kind == "youtube_publish":
                try:
                    youtube_publish.run(db, job, storage)
                except youtube_publish.PublishFailed as err:
                    raise JobFailure(err.message, err.detail) from None
            elif job.kind == "check":
                run_check_job(db, job)
            elif job.kind == "voice":
                run_voice_job(db, job, storage)
            elif job.kind == "photos":
                auto_photos.run(db, job, storage)
            elif job.kind == "revise":
                run_revise_job(db, job, call)
            elif job.kind == rework.KIND:
                try:
                    rework.run(db, job, storage, call)
                    rework.finish(db, job)
                except (rework.ReworkError, ClaudeError) as err:
                    raise JobFailure(str(err)) from None
                return
            elif job.kind == "motion":
                try:
                    motion.run(db, job, storage)
                except motion.MotionError as err:
                    raise JobFailure(err.message, err.detail) from None
            else:
                raise JobFailure(f"Loại job không hỗ trợ: {job.kind}")
        except render_nodes.HandedOff:
            # Packed for a render machine: the job stays running until a machine finishes it (routes_render_nodes).
            log.info("Job %s handed to a render machine", job_id)
            return
        except auto_photos.AutoPhotosFailed as err:
            db.rollback()
            _finish(db, job_id, "failed", str(err))
            log.warning("Job %s failed: %s", job_id, err)
            return
        except JobFailure as err:
            db.rollback()
            _finish(db, job_id, "failed", err.message, err.detail)
            if job.kind == "publish" and job.article_id is not None:
                article_posts.plan_retry(db, job.article_id, err.retryable)
            _reopen_notes(db, job)
            log.warning("Job %s failed: %s\n%s", job_id, err.message, err.detail)
            return
        except Exception:
            db.rollback()
            detail = traceback.format_exc()[-4000:]
            _finish(db, job_id, "failed", "Lỗi không mong đợi trong worker", detail)
            _reopen_notes(db, job)
            log.exception("Job %s crashed", job_id)
            return
        _finish(db, job_id, "done")
        log.info("Job %s done", job_id)
        if job.kind == "render":
            review.after_render(db, job.video_id)
            auto_approve.settle(db, job.video_id)
        if job.kind in ("script", "clone") or (job.kind == "learn" and _has_script(db, job)):
            _queue_photos(db, job)


def _has_script(db: DbSession, job: Job) -> bool:
    video = db.get(Video, job.video_id, populate_existing=True)
    return bool(video and video.has_script)


def _reopen_notes(db: DbSession, job: Job) -> None:
    """A failed "Nhờ AI sửa" gives its notes back, to change or send again; a failed "Cảnh động" stops showing as
    being made, and its scene keeps the picture it had."""
    if job.kind == "motion":
        motion.fail_pending(db, job)
    if job.kind == "revise":
        db.execute(
            update(VideoNote)
            .where(VideoNote.video_id == job.video_id, VideoNote.status == "sent")
            .values(status="open")
        )
        db.commit()


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


def run_script_job(
    db: DbSession, job: Job, call: Callable[[str, str], str] | None, storage: DirectoryStorage | None = None
) -> None:
    video = db.get(Video, job.video_id)
    # A retried job whose script was already saved has nothing to do: no new Claude call,
    # and nothing the members edited meanwhile is overwritten.
    if not video.has_script:
        topic = knowledge.topic_of(db, video)
        if topic is None:
            raise JobFailure("Video chưa thuộc nhóm chủ đề nào trong Kho kiến thức")
        if job.kind == "clone":
            # The snapshot from the moment "Nhân bản" was pressed: later edits of the source do not count.
            prompt = build_clone_prompt(
                topic.clone_prompt,
                video.clone_source,
                topic.banned_words,
                topic.photo_hint,
                content_types=team_content_types(db),
            )
            if topic.outro_cta:
                prompt = f"{prompt}\n\n{outro.SCRIPT_FORMAT}"
        else:
            idea = plans.idea_of_video(db, video.id)
            prompt = script_prompt(topic, video.topic, idea, video.ai_effects, False, team_content_types(db))
        if is_backdrop(video):
            prompt = f"{prompt}\n\n{BACKDROP_FORMAT}"

        call, count_call = _llm(db, job, call)
        try:
            script = generate_script(prompt, f"job {job.id}", count_call, call)
        except ClaudeError as err:
            raise JobFailure(err.message, err.detail) from None
        save_script(db, video, script)
        if storage is None:
            from .storage import get_storage

            storage = get_storage()
        outro.add(db, storage, video)
        affiliate_rounds.ask_after_script(db, video, job.created_by_id)
        db.commit()


def script_prompt(
    group: KnowledgeTopic,
    topic: str,
    idea: TopicPlanItem | None,
    ai_effects: bool,
    backdrop: bool,
    content_types: list[str] | None = None,
) -> str:
    """The whole prompt that writes a video's script: the script job sends it, and the MCP server hands the same one
    to a member's own Claude. A video made from a 30-day plan idea writes to that idea's pain and hook."""
    prompt = build_script_prompt(
        group.script_prompt,
        topic,
        group.banned_words,
        (idea.pain_group, idea.pain, idea.hook) if idea else None,
        photo_hint=group.photo_hint,
        content_types=content_types,
    )
    if ai_effects:
        prompt = f"{prompt}\n\n{autoedit.EFFECTS_FORMAT}"
    if group.text_ai:
        prompt = f"{prompt}\n\n{text_looks.SCRIPT_FORMAT}"
    if group.outro_cta:
        prompt = f"{prompt}\n\n{outro.SCRIPT_FORMAT}"
    if backdrop:
        prompt = f"{prompt}\n\n{BACKDROP_FORMAT}"
    return prompt


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


# --- Learn ("Từ video mẫu") ---


def run_learn_job(db: DbSession, job: Job, storage: DirectoryStorage, call: Callable | None) -> None:
    """A script learned from a sample video, in the way the video was made with (reference.py). The way "review"
    stops after the analysis; the job queued by "Viết kịch bản" then writes from the analysis as edited."""
    video = db.get(Video, job.video_id)
    if video.has_script:
        return
    topic = knowledge.topic_of(db, video)
    if topic is None:
        raise JobFailure("Video chưa thuộc nhóm chủ đề nào trong Kho kiến thức")
    sample = db.get(VideoReference, video.reference_id) if video.reference_id else None
    if sample is None:
        raise JobFailure("Video mẫu của video này đã bị xoá, hãy tạo video mới từ video mẫu")
    mode = video.reference_mode if video.reference_mode in reference.MODES else "quick"
    folder = work_dir(job.id)
    folder.mkdir(parents=True, exist_ok=True)
    label = f"job {job.id}"
    if mode == "footage":
        _make_from_footage(db, job, video, sample, storage, folder)
        return
    try:
        reference.prepare(db, sample, storage, folder)
        see, count_call = _seeing_llm(db, job, call)
        analyzed_before = reference.is_analyzed(sample)
        if mode != "quick" and not analyzed_before:
            reference.analyze(sample, topic, storage, see, count_call, label)
            db.commit()
            if mode == "review":
                # The member reads and edits the analysis, then "Viết kịch bản" queues the writing.
                return
        learned = reference.write(
            video.topic,
            sample,
            topic,
            storage,
            see,
            count_call,
            label,
            with_images=mode != "twostep",
            with_analysis=mode == "quick" and not analyzed_before,
            content_types=team_content_types(db),
        )
    except reference.ReferenceError as err:
        db.rollback()
        raise JobFailure(err.message, err.detail) from None
    except ClaudeError as err:
        db.rollback()
        raise JobFailure(err.message, err.detail) from None
    if learned.analysis and not reference.is_analyzed(sample):
        sample.analysis, sample.analyzed_at = learned.analysis, now()
    save_script(db, video, learned.script)
    db.flush()
    title, scenes = split_scenes(db, video)
    reference.attach_clips(storage, sample, title, scenes, learned, folder, lambda name: new_key(video.id, name, "mp4"))
    if title is not None and title.video_key:
        refresh_thumbnail(db, storage, video, title)
    # After the sample's clips are matched to the scenes, so none of them lands on the outro.
    outro.add(db, storage, video)
    affiliate_rounds.ask_after_script(db, video, job.created_by_id)
    db.commit()
    shutil.rmtree(folder, ignore_errors=True)


def _make_from_footage(
    db: DbSession, job: Job, video: Video, sample: VideoReference, storage: DirectoryStorage, folder: Path
) -> None:
    """ "Edit từ footage" (footage.py): the footage cut into scenes by what is said, with no LLM call."""
    try:
        reference.prepare(db, sample, storage, folder)
        footage.make(db, video, sample, storage, folder, lambda name: new_key(video.id, name, "mp4"))
    except reference.ReferenceError as err:
        db.rollback()
        raise JobFailure(err.message, err.detail) from None
    db.flush()
    title, _ = split_scenes(db, video)
    if title is not None:
        refresh_thumbnail(db, storage, video, title)
    # After the sample's clips are matched to the scenes, so none of them lands on the outro.
    outro.add(db, storage, video)
    affiliate_rounds.ask_after_script(db, video, job.created_by_id)
    db.commit()
    shutil.rmtree(folder, ignore_errors=True)


def expects_sound(video: Video, scenes: list[Scene]) -> bool:
    """Whether QC fails a silent MP4: it has narration, music or a clip's own sound to be heard."""
    return video.voice_enabled or bool(video.music_key) or any(scene.video_sound for scene in scenes)


def _seeing_llm(db: DbSession, job: Job, call: Callable | None) -> tuple[reference.SeeingCall, Callable[[], None]]:
    """Like _llm, for calls that may send a sample's stills as images."""
    if call is None:
        target = llm.active_target(db)
        db.execute(update(Job).where(Job.id == job.id).values(llm_provider=target.provider, llm_model=target.model))
        db.commit()

        def call(prompt: str, label: str, images=()) -> str:
            return llm.complete(target, prompt, label, images)

    def count_call() -> None:
        db.execute(update(Job).where(Job.id == job.id).values(claude_calls=Job.claude_calls + 1))
        db.commit()

    return call, count_call


# --- Revise ---


def run_revise_job(db: DbSession, job: Job, call: Callable[[str, str], str] | None) -> None:
    """ "Nhờ AI sửa": the notes sent with it change the scenes they point at, then each is answered."""
    video = db.get(Video, job.video_id)
    topic = knowledge.topic_of(db, video)
    template = (topic.revise_prompt if topic else "") or knowledge.default_revise_prompt()
    call, count_call = _llm(db, job, call)
    try:
        revise.run(db, video, template, topic.banned_words if topic else [], f"job {job.id}", count_call, call)
    except ClaudeError as err:
        raise JobFailure(err.message, err.detail) from None
    db.commit()


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


def run_text_look_job(db: DbSession, job: Job, call: Callable[[str, str], str] | None) -> None:
    """ "AI gợi ý" on a group's "Chữ & phụ đề": a few looks for it, kept for a member to pick one; the group's own
    look changes only when a member saves one."""
    topic = db.get(KnowledgeTopic, job.knowledge_topic_id)
    if topic is None:
        raise JobFailure("Nhóm chủ đề đã bị xoá")
    call, count_call = _llm(db, job, call)
    try:
        options = text_looks.generate(topic, f"job {job.id}", count_call, call)
    except ClaudeError as err:
        raise JobFailure(err.message, err.detail) from None
    topic = db.get(KnowledgeTopic, job.knowledge_topic_id, with_for_update=True, populate_existing=True)
    topic.text_suggestions = text_looks.suggestions_payload(job.id, options)
    db.commit()


def run_article_caption_job(db: DbSession, job: Job, call: Callable[[str, str], str] | None) -> None:
    """ "AI viết" on an article: its caption and hashtags, replacing what was there (the member asked for it, and the
    article cannot be edited while the job is queued or running)."""
    article = db.get(Article, job.article_id)
    if article is None:
        raise JobFailure("Bài viết đã bị xoá")
    if not article.topic.strip():
        raise JobFailure("Bài viết chưa có chủ đề")
    prompt = articles.build_prompt(
        articles.group_of(db, article), article, articles.comment_text(article.source_comment)
    )
    call, count_call = _llm(db, job, call)
    try:
        written = articles.generate(prompt, article.kind, f"job {job.id}", count_call, call)
    except ClaudeError as err:
        raise JobFailure(err.message, err.detail) from None
    article = db.get(Article, job.article_id, with_for_update=True, populate_existing=True)
    if article is None:
        raise JobFailure("Bài viết đã bị xoá")
    article.caption, article.hashtags = written.caption, written.hashtags
    article.pinned_comment, article.affiliates = written.pinned_comment, written.affiliates
    # As after a video's script: its product ideas are searched on Shopee when its writer has an account to do so.
    affiliate_rounds.ask_after_script(db, article, job.created_by_id)
    db.commit()


def save_script(db: DbSession, video: Video, script: GeneratedScript) -> None:
    video.has_script = True
    video.title_options = script.titles
    video.caption = script.caption
    video.hashtags = script.hashtags
    video.affiliates = script.affiliates
    # The AI writes only the survey line; the title and the scenes come from the video itself (pinned.py).
    video.pinned_survey = pinned.survey_of_script(script.pinned_comment)
    video.self_review = script.self_review
    video.music_suggestions = script.music_suggestions
    # The AI's "Loại nội dung", unless a member already gave the video one.
    if script.content_type and not video.content_type:
        video.content_type = script.content_type
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
        photo = is_backdrop(video) and bool(scene.keywords or scene.keywords_en)
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
                # "Video xuyên suốt": a scene the AI named a dish for (it wrote that dish's photo keywords) shows it
                # as a half-frame photo of the scene's photo, found by "Tự tìm ảnh" or chosen on its card.
                layers=[half_layer()] if photo else [],
            )
        )
    # The team's "Mẫu dựng" for new videos, if one is chosen, then the AI's own picks when it was asked for them.
    autoedit.apply_default(db, video)
    autoedit.apply_ai_effects(db, video, [scene.effects for scene in script.scenes])
    # "AI chọn kiểu chữ cho từng video": the AI's look for this video, over its group's and its maker's.
    group = knowledge.topic_of(db, video)
    if group is not None and group.text_ai:
        look = text_looks.loose_look(script.text_look)
        if look:
            video.options = {**(video.options or {}), **look}


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


def reveal_layers(fields: dict, steps: list[dict], folder: Path, stem: str) -> list[dict]:
    """A card shown part by part ("Hiện dần") as one card layer per part, each the whole card with the rows below its
    part cleared, so every one is laid at the same size and place and the card grows down as each comes in over the
    one before. Each lasts from its part's start to the card's own end."""
    with Image.open(folder / fields["image"]) as source:
        card = ImageOps.exif_transpose(source).convert("RGBA")
    end = fields["start"] + fields["seconds"]
    layers = []
    for number, step in enumerate(steps):
        start = max(fields["start"], step["start"])
        if start >= end:
            break
        shown = card.copy()
        cut = round(card.height * step["until"])
        if cut < card.height:
            shown.paste((0, 0, 0, 0), (0, cut, card.width, card.height))
        name = f"{stem}-part{number:02d}.png"
        shown.save(folder / name)
        layers.append(fields | {"image": name, "start": round(start, 2), "seconds": round(end - start, 2)})
    return layers


def make_voices(db: DbSession, video: Video, scenes: list[Scene], storage: DirectoryStorage) -> None:
    """Narration for every scene that has something to read but no MP3 made from it yet. Each MP3 is committed at once,
    so a retry after a failure pays the voice's service only for the scenes still missing."""
    failed: set[str] = set()  # keys found wrong or spent in this job: the scenes after skip them
    for index, scene in enumerate(scenes):
        voice = scene_voice(video, scene)
        text = spoken(video, scene)
        if not text or (made_voice_seconds(video, scene) is not None and storage.exists(scene.voice_key)):
            continue
        label = _scene_label(scene, index)
        try:
            if is_google(voice):
                # Google bills past its free tier with no way to stop there, so the app stops first.
                google_tts_quota.check(db, voice, text)
            words: list[dict] | None = [] if effective(video)["captions"] == "cumulative" else None
            data = narrate(db, video, text, voice, failed, words)
        except TtsError as err:
            raise JobFailure(f"{label}: {err.message}", err.detail) from None
        if is_google(voice):
            # Committed at once, which also frees the counter's row lock: what Google read is counted even if a
            # later step fails.
            google_tts_quota.record(db, voice, text)
            db.commit()
        key = new_key(video.id, f"voice-{scene.id}", "mp3")
        storage.save_bytes(key, data)
        try:
            seconds = audio_seconds(find_tools().ffprobe, storage.path(key))
        except FFmpegError:
            seconds = None
        if seconds is None:
            storage.delete(key)
            raise JobFailure(f"{label}: {service_name(voice)} trả file lời đọc không đọc được, thử lại sau")
        old = scene.voice_key
        scene.voice_key, scene.voice_signature, scene.voice_seconds, scene.voice_name = (
            key,
            voice_signature(text, voice, voice_speed(video)),
            seconds,
            None,
        )
        scene.voice_words = words or None
        # "Tự khớp lời đọc": the scene now lasts as long as its narration, shorter or longer than before.
        if scene.seconds_auto:
            scene.seconds = auto_seconds(seconds, voice_pause(video))
        db.commit()
        if old and old != key:
            storage.delete(old)
        log.info("Narration for video %s %s: %.1fs", video.id, label, seconds)


def narrate(
    db: DbSession, video: Video, text: str, voice: str | None, failed: set[str], words: list[dict] | None = None
) -> bytes:
    """One scene's narration in its voice; when every key of that voice's service is wrong or spent, in the video's
    group's backup voice (`voice_backup_id`) if it has one, which may be of another service."""
    try:
        return _narrate_with_keys(db, video, text, voice, failed, words)
    except TtsError as err:
        group = db.get(KnowledgeTopic, video.knowledge_topic_id) if video.knowledge_topic_id else None
        backup = group.voice_backup_id if group is not None else ""
        if not err.key_fault or not backup or backup == (voice or config.voice_id()):
            raise
        log.warning("Narration for video %s: %s cannot read (%s), using the backup voice", video.id, voice, err.message)
        try:
            return _narrate_with_keys(db, video, text, backup, failed, words)
        except TtsError as backup_err:
            raise TtsError(
                f"{err.message}. Giọng phụ của nhóm cũng không đọc được: {backup_err.message}",
                f"{err.detail} | backup: {backup_err.detail}",
            ) from None


def _narrate_with_keys(
    db: DbSession, video: Video, text: str, voice: str | None, failed: set[str], words: list[dict] | None = None
) -> bytes:
    """One scene's narration, trying the service's keys in order (source_keys.chain: the team's main key, then its
    backups): a key that is wrong, not allowed or out of quota passes the scene to the next, and its row on Cài đặt
    says why at once (source_keys.mark); a busy or broken service fails at once, as with one key. A key that failed
    earlier in the job (`failed`) is not asked again; one that reads again loses its old error."""
    service = tts_key_name(voice)
    keys = source_keys.chain(db, service)
    if not keys:
        return synthesize(text, "", voice, voice_speed(video), words)  # fails with "Chưa có key …"
    last: TtsError | None = None
    for ref in keys:
        if ref.key in failed:
            continue
        if service == "gemini":
            # Counted before each request, a backup key's too (Cài đặt › AI và nguồn tư liệu shows Gemini's today).
            service_usage.record(db, "gemini", "voice")
            db.commit()
        try:
            data = synthesize(text, ref.key, voice, voice_speed(video), words)
        except TtsError as err:
            if not err.key_fault:
                raise
            failed.add(ref.key)
            source_keys.mark(db, service, ref, err.message)
            db.commit()
            if len(keys) == 1:
                raise
            last = err
            log.warning(
                "Narration for video %s: %s key %s failed (%s), trying the next",
                video.id,
                service,
                ref.shown,
                err.message,
            )
            continue
        source_keys.mark(db, service, ref, None)
        return data
    raise TtsError(all_keys_failed(service, len(keys)), last.detail if last else "", True)


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
            if is_backdrop(video) and not scene.is_title:
                # "Video xuyên suốt": the renderer lays the title scene's photo or clip under this scene.
                data = {"text": scene.text, "seconds": scene.seconds}
            elif scene.video_key:
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
                if scene.video_loop:
                    data["video_loop"] = True
                if scene.video_sound:
                    data["video_sound"] = True
                    if scene.words:
                        data["words"] = scene.words
                if blurred := blur_of(scene):
                    data["video_blur"] = blurred
            else:
                if not scene.image_key or not storage.exists(scene.image_key):
                    raise JobFailure(f"{label} chưa có ảnh trong storage, hãy gán lại ảnh rồi render")
                image = storage.copy_to(
                    scene.image_key, folder / f"image-{index:02d}.{scene.image_key.rsplit('.', 1)[-1]}"
                )
                data = {"text": scene.text, "seconds": scene.seconds, "image": image.name}
                # "Khung ảnh" (reels_render.framing): a content scene's photo on a slide video; "cover" is the default.
                if (fit := photo_fit(video, scene)) != "cover":
                    data["image_fit"] = fit
                    if scene.image_crop_offset is not None:
                        data["image_crop_offset"] = scene.image_crop_offset
            if position := text_position(video, scene):
                data["text_position"] = position
            if scene.transition and not scene.is_title:
                data["transition"] = scene.transition
            if scene.color and not scene.is_title:
                data["color"] = scene.color
            if (layers := drawn_layers(video, scene)) and not scene.is_title:
                data["layers"] = [fields for layer in layers for fields in layer_data(layer, scene, index)]
            if scene.sounds:
                data["sounds"] = [sound_fields(sound) for sound in scene.sounds]
            if scene.music_level:
                data["music_level"] = scene.music_level
            if scene.text_zone:
                data["text_zone"] = scene.text_zone
            if (hold := text_hold(video, scene)) is not None:
                data["text_hold_sec"] = hold
            if spoken(video, scene):
                data["voice"] = storage.copy_to(scene.voice_key, folder / f"voice-{index:02d}.mp3").name
                data["voice_text"] = spoken(video, scene)
                if scene.voice_words and effective(video)["captions"] == "cumulative":
                    data["voice_words"] = scene.voice_words
            return data

        def layer_data(layer, scene: Scene, index: int) -> list[dict]:
            """The layer as the render script reads it; a card shown part by part is laid once per part."""
            fields = layer_fields(layer)
            if layer.kind == "photo":
                # A photo layer ("Ảnh món") shows its scene's own photo, which the checks make sure there is; a
                # half-frame photo ("Ảnh chèn nửa khung") or a card ("Thẻ") its own.
                key = layer_photo_key(layer)
                if not key or not storage.exists(key):
                    what = "thẻ" if is_card_layer(layer) else "ảnh chèn" if is_half_layer(layer) else "ảnh món"
                    raise JobFailure(f"{_scene_label(scene, index)} có {what} nhưng chưa có ảnh trong storage")
                extension = key.rsplit(".", 1)[-1]
                name = "card" if is_card_layer(layer) else "inset" if is_half_layer(layer) else "photo"
                fields["image"] = storage.copy_to(key, folder / f"{name}-{index:02d}.{extension}").name
                if is_card_layer(layer) and (steps := reveal_steps(video, scene)):
                    return reveal_layers(fields, steps, folder, f"{name}-{index:02d}")
            return [fields]

        data = {"title": entry(title, 0), "scenes": [entry(scene, index) for index, scene in enumerate(scenes, 1)]}
        signature = render_signature(video, title, scenes)
        options = render_options(video)
        if brands.badge_path(db, storage, video) is not None:
            data["logo"] = storage.copy_to(brands.brand_of(db, video).logo_badge_path, folder / "logo.png").name
            options = replace(options, logo=True)
        if any("video_blur" in item for item in [data["title"], *data["scenes"]]):
            options = replace(options, clip_blur=True)
        if any(item.get("video_loop") for item in [data["title"], *data["scenes"]]):
            options = replace(options, clip_loop=True)
        if any("text_hold_sec" in item for item in [data["title"], *data["scenes"]]):
            options = replace(options, text_hold=True)
        music = _checked_music(video, storage, folder)
        if render_nodes.enabled(db):
            # The heavy part runs on a member's render machine; the api finishes the job with save_render.
            manifest = {
                "kind": "render",
                "data": data,
                "music": music.name if music else None,
                "music_volume": video.music_volume / 100,
                "music_start": video.music_start,
                "options": render_nodes.options_dict(options),
                "expect_sound": expects_sound(video, [title, *scenes]),
                "signature": signature,
            }
            render_nodes.pack(db, storage, job, manifest, folder)
            raise render_nodes.HandedOff
        output = folder / "video.mp4"
        started = time.monotonic()
        try:
            render_video(
                parse_script(data, base_dir=folder),
                output,
                music=music,
                music_volume=video.music_volume / 100,
                music_start=video.music_start,
                options=options,
            )
            seconds = float(probe(find_tools().ffprobe, output)["format"]["duration"])
        except FFmpegError as err:
            raise JobFailure("FFmpeg lỗi khi render video", err.stderr_tail) from None
        except RenderError as err:
            raise JobFailure(str(err)) from None
        elapsed = time.monotonic() - started
        # Measured on the file before it is saved, so the MP4 and its QC always go together.
        measured = qc.measure(output, expect_sound=expects_sound(video, [title, *scenes]))
        save_render(db, storage, video, output, seconds, elapsed, measured, signature)
        log.info("Job %s rendered %.1fs of video in %.1fs", job.id, seconds, elapsed)
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def save_render(
    db: DbSession,
    storage: DirectoryStorage,
    video: Video,
    output: Path,
    seconds: float,
    elapsed: float,
    measured: dict | None,
    signature: str,
) -> None:
    """The MP4 becomes the video's, with its QC and the fingerprint of what it shows; the worker's own render and a
    render machine's both end here."""
    video.qc = measured
    key = new_key(video.id, "video", "mp4")
    storage.save_file(key, output)
    old = video.mp4_key
    video.mp4_key, video.mp4_seconds, video.render_seconds = key, seconds, round(elapsed, 1)
    video.rendered_signature, video.rendered_at = signature, now()
    if effective(video)["title_layout"] == "three_tier":
        # PC Shopee's compact title: the thumbnail is drawn again with each render, so a video whose title layout was
        # chosen before the thumbnail followed it is brought up to date.
        refresh_thumbnail(db, storage, video, split_scenes(db, video)[0])
    db.commit()
    # The old MP4 stays playable until the new one is committed.
    if old and old != key:
        storage.delete(old)


# --- Publish ---

# Facebook refuses a scheduled time less than 10 minutes away.
MIN_SCHEDULE_LEAD = timedelta(minutes=10)
# After this long, a reel Facebook was asked to publish and still has not is taken as dropped.
SETTLE_TIME = timedelta(minutes=30)


def run_publish_job(db: DbSession, job: Job, storage: DirectoryStorage) -> None:
    if job.article_id is not None:
        run_article_publish_job(db, job, storage)
        return
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
    if post.status == "published":
        # The publish job already confirmed this reel was live on Facebook.
        post.checked_at = post.published_at
    db.commit()
    title, _ = split_scenes(db, video)
    _set_cover(page, post, storage, (title_poster_second(title) if title is not None else None) or 0)
    log.info("Job %s posted video %s to Facebook as %s", job.id, video.id, post.remote_id)


def run_article_publish_job(db: DbSession, job: Job, storage: DirectoryStorage) -> None:
    """An article's photo or text post. Never posted twice, as a reel: what is sent is stamped before Facebook is
    asked; a retry reads the post it got back, or, when that answer was lost, looks for the same text on the Page."""
    article = db.get(Article, job.article_id)
    post = article_posts.pending_post(db, article.id)
    if post is None:
        return
    try:
        page = fanpages.load_page(db, post.fanpage_id)
        status = _settled_status(db, page, post) if post.remote_id else None
        if post.remote_id is None and post.finish_sent_at is not None:
            found = facebook.find_post(page, post.post_text or "")
            if found is not None:
                post.remote_id = found
                db.commit()
                status = facebook.post_status(page, found)
            elif now() - post.finish_sent_at < SETTLE_TIME:
                raise JobFailure(
                    "Facebook có thể vẫn đang đăng lần trước, hãy xem Page, đợi 30 phút rồi Thử lại", retryable=True
                )
        if status is None:
            _check_article_publishable(article, post)
            with tempfile.TemporaryDirectory(prefix="reels_article_post_") as folder:
                photos = _article_photos(db, article, post, storage, Path(folder))
                post.post_text, post.remote_id, post.finish_sent_at = article_posts.post_text(db, article), None, now()
                db.commit()
                try:
                    if not photos:
                        remote = facebook.publish_text(page, post.post_text, post.scheduled_at)
                    elif len(photos) == 1:
                        remote = facebook.publish_photo(page, post.post_text, photos[0], post.scheduled_at)
                    else:
                        remote = facebook.publish_photos(page, post.post_text, photos, post.scheduled_at)
                except FacebookError as err:
                    # Only a refusal proves Facebook did not post it; a lost or 5xx answer proves nothing.
                    if 400 <= err.status < 500:
                        post.finish_sent_at = None
                        db.commit()
                    raise
            post.remote_id = remote
            db.commit()
            status = _settled_status(db, page, post)
            if status is None:
                raise JobFailure("Facebook không còn giữ bài vừa đăng, hãy xem Page rồi Thử lại")
    except FacebookError as err:
        raise JobFailure(err.message, err.detail, retryable=facebook.is_passing(err)) from None
    post.status = "published" if status["published"] else "scheduled"
    post.retry_at = None
    post.scheduled_at = (status["scheduled_at"] or post.scheduled_at) if post.status == "scheduled" else None
    post.published_at = now()
    if post.status == "published":
        post.checked_at = post.published_at
    db.commit()
    log.info("Job %s posted article %s to Facebook as %s", job.id, article.id, post.remote_id)


def _settled_status(db: DbSession, page: facebook.Page, post: Publication) -> dict | None:
    """The status of the article's post, keeping the id of the post itself when Facebook first gave another."""
    settled = facebook.settle_post(page, post.remote_id, post.post_text or "")
    if settled is None:
        return None
    if settled[0] != post.remote_id:
        post.remote_id = settled[0]
        db.commit()
    return settled[1]


def _check_article_publishable(article: Article, post: Publication) -> None:
    """Also covers "Thử lại", which does not pass through the publish endpoint."""
    blocking = articles.checks(article, [])["blocking"]
    if blocking:
        raise JobFailure(blocking[0]["message"])
    if post.scheduled_at is not None and post.scheduled_at < now() + MIN_SCHEDULE_LEAD:
        raise JobFailure("Giờ hẹn đã qua hoặc còn dưới 10 phút, hãy chọn giờ khác rồi bấm đăng lại")


def _article_photos(
    db: DbSession, article: Article, post: Publication, storage: DirectoryStorage, folder: Path
) -> list[Path]:
    """The article's photos as posted to the post's Page: with that Page's logo, unless a photo's switch is off."""
    try:
        return article_images.posted_files(db, storage, article, post.fanpage_id, folder)
    except FileNotFoundError as err:
        raise JobFailure(f"Không thấy {str(err).lower()} của bài trong storage, hãy chọn lại ảnh rồi đăng") from None


def _set_cover(page: facebook.Page, post: Publication, storage: DirectoryStorage, second: float = 0) -> None:
    """The reel's cover is the title scene: the first frame of the MP4 the reel holds (a motion title's settled frame,
    `second`), so it matches what was posted even when the title changed since. Set once the reel is live or scheduled, since Facebook may not take a cover
    for a reel it is still processing. A cover that cannot be set leaves Facebook's own pick: the post stands."""
    try:
        if not post.remote_mp4_key or not storage.exists(post.remote_mp4_key):
            raise ClipError("MP4 của bài đăng không còn trong storage")
        cover = jpeg_bytes(frame_at(storage.path(post.remote_mp4_key), second))
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
        if post.article_id is not None:
            status = facebook.post_status(page, post.remote_id)
            if status is not None:
                went_live = went_live or status["published"]
                facebook.delete_post(page, post.remote_id)
        else:
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


# A live post is also checked again now and then (metrics.recheck_due), a few per round: the first round after this
# shipped meets every post never checked, and each check is a job of its own.
RECHECK_PER_ROUND = 5


def queue_post_checks(db: DbSession) -> None:
    """Queue one check of each scheduled reel whose time has passed, so a reel cancelled, moved or dropped on Facebook
    is not shown as posted. Once per scheduled time, failed or not: a member retries it or presses "Kiểm tra". A live
    post is checked again by the schedule of metrics.recheck_due, so one deleted on Facebook afterwards is found."""
    at = now()
    due = db.scalars(
        select(Publication).where(
            Publication.platform == "facebook",
            Publication.status == "scheduled",
            Publication.remote_id.is_not(None),
            Publication.scheduled_at <= at - CHECK_DELAY,
            or_(Publication.checked_at.is_(None), Publication.checked_at < Publication.scheduled_at),
        )
    ).all()
    waiting = db.scalar(
        select(func.count()).select_from(Job).where(Job.kind == "check", Job.status.in_(("queued", "running")))
    )
    room = max(0, RECHECK_PER_ROUND - (waiting or 0))
    again = (
        db.scalars(
            select(Publication)
            .where(Publication.platform == "facebook", Publication.remote_id.is_not(None), metrics.recheck_due(at))
            .order_by(Publication.checked_at.asc().nulls_first(), Publication.id)
            .limit(room)
        ).all()
        if room
        else []
    )
    for post in [*due, *again]:
        # One active job per video or article: the check waits for the next round.
        busy = articles.active_job(db, post.article_id) if post.article_id else active_job(db, post.video_id)
        if busy is not None:
            continue
        try:
            with db.begin_nested():
                db.add(
                    Job(
                        video_id=post.video_id,
                        article_id=post.article_id,
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


TIKTOK_SWEEP_WINDOW = timedelta(hours=24)


def queue_tiktok_posts(db: DbSession) -> None:
    """Send each video whose Facebook post has reached its slot to TikTok: a draft into the Page owner's TikTok inbox,
    or a public post when the Page's mode is "direct". TikTok has no scheduled time, so this round, which runs about
    once a minute, is the clock. Only a reel that is scheduled or out counts (a pending one is not yet on Facebook, a
    cancelled one was stopped), once per video, and only through a TikTok account of the Page's owner."""
    due = db.scalars(
        select(Publication).where(
            Publication.video_id.is_not(None),
            Publication.platform == "facebook",
            Publication.status.in_(("scheduled", "published")),
            Publication.scheduled_at <= now(),
            # Only a slot of the last day: videos posted long ago (before this existed) are never sent in a flood.
            Publication.scheduled_at >= now() - TIKTOK_SWEEP_WINDOW,
        )
    ).all()
    for post in due:
        video = db.get(Video, post.video_id)
        page = db.get(Fanpage, post.fanpage_id) if post.fanpage_id else None
        if video is None or not video.mp4_key or page is None or page.owner_id is None or not page.tiktok_account_id:
            continue
        account = db.get(AffiliateAccount, page.tiktok_account_id)
        if account is None or not account.active or account.platform != "tiktok" or account.owner_id != page.owner_id:
            continue
        if active_job(db, video.id) is not None:
            continue  # the next round tries again
        already = db.scalar(
            select(Publication.id).where(
                Publication.video_id == video.id,
                Publication.platform == "tiktok",
                Publication.status.in_(("pending", "scheduled", "published")),
            )
        )
        if already is not None:
            continue
        mode = page.tiktok_auto_mode or "draft"
        try:
            with db.begin_nested():
                made = Publication(
                    video_id=video.id,
                    platform="tiktok",
                    status="pending",
                    created_by_id=page.owner_id,
                    affiliate_account_id=account.id,
                    publish_mode=mode,
                    privacy_level="PUBLIC_TO_EVERYONE" if mode == "direct" else None,
                )
                db.add(made)
                db.flush()
                db.add(
                    Job(
                        video_id=video.id,
                        kind="tiktok_publish",
                        status="queued",
                        created_by_id=page.owner_id,
                        publication_id=made.id,
                    )
                )
        except IntegrityError:
            continue
        log.info("Queued a TikTok %s post of video %s for Page %s", mode, video.id, page.name)


def queue_instagram_auto_posts(db: DbSession) -> None:
    """Post each video whose Facebook post has reached its slot to the Instagram account linked to its Page, when the
    Page's owner turned `instagram_auto` on. Like `queue_tiktok_posts`, this round (about once a minute) is the clock,
    so Instagram follows Facebook by about a minute. Only a scheduled slot of the last day counts: an "Đăng ngay" post
    has no slot. A video with any Instagram post but a cancelled one is left alone, a failed one too, so an error that
    repeats (a token without permission) is not retried every minute: its member presses "Thử lại"."""
    due = db.scalars(
        select(Publication).where(
            Publication.video_id.is_not(None),
            Publication.platform == "facebook",
            Publication.status.in_(("scheduled", "published")),
            Publication.scheduled_at <= now(),
            Publication.scheduled_at >= now() - TIKTOK_SWEEP_WINDOW,
        )
    ).all()
    for post in due:
        video = db.get(Video, post.video_id)
        page = db.get(Fanpage, post.fanpage_id) if post.fanpage_id else None
        if video is None or not video.mp4_key or page is None or page.owner_id is None:
            continue
        if not page.instagram_auto or not page.instagram_user_id:
            continue
        if active_job(db, video.id) is not None:
            continue  # the next round tries again
        already = db.scalar(
            select(Publication.id).where(
                Publication.video_id == video.id,
                Publication.platform == "instagram",
                Publication.status != "cancelled",
            )
        )
        if already is not None:
            continue
        try:
            with db.begin_nested():
                made = Publication(
                    video_id=video.id,
                    platform="instagram",
                    status="pending",
                    fanpage_id=page.id,
                    created_by_id=page.owner_id,
                    remote_mp4_key=video.mp4_key,
                    post_text=instagram.caption(hashtags.post_text(video.caption, video.hashtags)),
                )
                db.add(made)
                db.flush()
                db.add(
                    Job(
                        video_id=video.id,
                        kind="ig_publish",
                        status="queued",
                        created_by_id=page.owner_id,
                        publication_id=made.id,
                    )
                )
        except IntegrityError:
            continue
        log.info("Queued an Instagram post of video %s for Page %s", video.id, page.name)


def queue_youtube_auto_posts(db: DbSession) -> None:
    """Upload each video whose Facebook post has reached its slot, private, to the YouTube channel of its Page, when the
    Page's owner turned `youtube_auto` on: the same upload as the "Tải lên YouTube" card, started by this round (about
    once a minute) instead of a click. Like Instagram's round, only a scheduled slot of the last day counts, and a
    video with any YouTube post but a cancelled one on that channel is left alone, a failed one too, so an error that
    repeats is not retried every minute: its member presses "Thử lại". A channel whose connection ran out is skipped
    without a word here (its Page shows the warning); a slot missed that way is not made up after a day."""
    due = db.scalars(
        select(Publication).where(
            Publication.video_id.is_not(None),
            Publication.platform == "facebook",
            Publication.status.in_(("scheduled", "published")),
            Publication.scheduled_at <= now(),
            Publication.scheduled_at >= now() - TIKTOK_SWEEP_WINDOW,
        )
    ).all()
    for post in due:
        video = db.get(Video, post.video_id)
        page = db.get(Fanpage, post.fanpage_id) if post.fanpage_id else None
        if video is None or not video.mp4_key or page is None or page.owner_id is None:
            continue
        if not page.youtube_auto or page.youtube_channel_id is None:
            continue
        connection = youtube_connections.of_channel(db, page.youtube_channel_id)
        if (
            connection is None
            or connection.owner_id != page.owner_id
            or youtube_connections.needs_reconnect(connection)
        ):
            continue
        if active_job(db, video.id) is not None:
            continue  # the next round tries again
        already = db.scalar(
            select(Publication.id).where(
                Publication.video_id == video.id,
                Publication.platform == "youtube",
                Publication.channel_id == page.youtube_channel_id,
                Publication.status != "cancelled",
            )
        )
        if already is not None:
            continue
        title_scene, _ = split_scenes(db, video)
        try:
            with db.begin_nested():
                made = Publication(
                    video_id=video.id,
                    platform="youtube",
                    status="pending",
                    fanpage_id=page.id,
                    created_by_id=page.owner_id,
                    channel_id=page.youtube_channel_id,
                    remote_mp4_key=video.mp4_key,
                    caption=title_of(video, title_scene),
                    post_text=hashtags.post_text(video.caption, video.hashtags),
                )
                db.add(made)
                db.flush()
                db.add(
                    Job(
                        video_id=video.id,
                        kind="youtube_publish",
                        status="queued",
                        created_by_id=page.owner_id,
                        publication_id=made.id,
                    )
                )
        except IntegrityError:
            continue
        log.info("Queued a YouTube upload of video %s for Page %s", video.id, page.name)


# An Instagram post this late (the worker was down) is not posted any more: its member decides again.
INSTAGRAM_LATE_LIMIT = timedelta(hours=24)


def queue_instagram_posts(db: DbSession) -> None:
    """Start each Instagram post set for later whose time has come: Instagram has no scheduled time through its API, so
    this round, which runs about once a minute, is the clock. A post more than `INSTAGRAM_LATE_LIMIT` late is
    cancelled instead, with the reason on it, so a worker back after a long stop does not post old videos by itself."""
    due = db.scalars(
        select(Publication).where(
            Publication.platform == "instagram",
            Publication.status == "scheduled",
            Publication.video_id.is_not(None),
            Publication.scheduled_at <= now(),
        )
    ).all()
    for post in due:
        if post.scheduled_at < now() - INSTAGRAM_LATE_LIMIT:
            post.status, post.closed_at = "cancelled", now()
            log.warning("Instagram post %s missed its time by over a day: cancelled", post.id)
            db.add(
                Job(
                    video_id=post.video_id,
                    kind="ig_publish",
                    status="failed",
                    created_by_id=post.created_by_id,
                    publication_id=post.id,
                    error="Quá giờ hẹn hơn 24 giờ nên chưa đăng Instagram, hãy đăng lại nếu vẫn muốn",
                    finished_at=now(),
                )
            )
            continue
        if active_job(db, post.video_id) is not None:
            continue  # the next round tries again
        try:
            with db.begin_nested():
                post.status = "pending"
                db.add(
                    Job(
                        video_id=post.video_id,
                        kind="ig_publish",
                        status="queued",
                        created_by_id=post.created_by_id,
                        publication_id=post.id,
                    )
                )
        except IntegrityError:
            continue
        log.info("Queued the Instagram post %s of video %s at its time", post.id, post.video_id)


def run_check_job(db: DbSession, job: Job) -> None:
    """Read the reel on Facebook and record what Facebook says. A member may have cancelled, moved or deleted it in
    Meta Business Suite, or Facebook dropped it, and nothing else tells the app. Never changes anything on Facebook.
    A post marked deleted is read again too: one Facebook still has goes back to live. A read that does not settle it
    fails the job and leaves the post as it was; "could not read" is never "deleted"."""
    post = db.get(Publication, job.publication_id)
    if post is None or post.status not in (*LIVE_POST_STATUSES, "deleted") or post.remote_id is None:
        return
    was_deleted = post.status == "deleted"
    try:
        page = fanpages.load_page(db, post.fanpage_id)
        if post.article_id is not None:
            found = facebook.post_status(page, post.remote_id)
            # A feed post is live or waiting for its time; there is no processing phase to wait for.
            status = None if found is None else _as_reel_status(found)
        else:
            status = facebook.reel_status(page, post.remote_id)
    except FacebookError as err:
        log.warning(
            "Job %s could not read reel %s, the post stays %s: %s", job.id, post.remote_id, post.status, err.detail
        )
        raise JobFailure(err.message, err.detail) from None
    post.checked_at = now()
    if status is not None and facebook.is_live(status):
        if post.status == "deleted":
            # Facebook still has it: the app had it wrong.
            post.closed_at, post.closed_by_id = None, None
            post.published_at = post.published_at or now()
        if facebook.is_scheduled(status):
            post.status = "scheduled"
            post.scheduled_at = facebook.scheduled_time(status) or post.scheduled_at
        else:
            post.status = "published"
    elif post.status != "deleted" and (status is None or not facebook.is_busy(status)):
        _close(post, is_published(post), None)
    db.commit()
    if was_deleted and post.status == "deleted":
        # A deleted post that stays deleted says why, or the member sees a finished job and no change.
        if status is None:
            raise JobFailure(
                f"Facebook không trả reel {post.remote_id} (không còn, hoặc token của Page không đọc được nó), "
                "bài vẫn ghi là đã xóa",
                f"reel {post.remote_id}",
            )
        raise JobFailure(
            "Facebook có reel này nhưng chưa công khai hay hẹn giờ, bài vẫn ghi là đã xóa",
            f"{post.remote_id}: {status}",
        )
    log.info("Job %s found reel %s %s on Facebook", job.id, post.remote_id, post.status)


def _as_reel_status(found: dict) -> dict:
    """A feed post's status in the reel's shape, so the check reads both alike."""
    moment = found["scheduled_at"]
    phase = {"publish_status": "published" if found["published"] else "scheduled"}
    if moment is not None:
        phase["publish_time"] = moment.timestamp()
    return {"publishing_phase": phase}


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
    if (page := db.get(Fanpage, post.fanpage_id)) is not None and (wrong := brands.mismatch(db, video, page)):
        raise JobFailure(wrong)
    if post.scheduled_at is not None and post.scheduled_at < now() + MIN_SCHEDULE_LEAD:
        raise JobFailure("Giờ hẹn đã qua hoặc còn dưới 10 phút, hãy chọn giờ khác rồi bấm đăng lại")
    if not video.mp4_key or not storage.exists(video.mp4_key):
        raise JobFailure("Không thấy file MP4 trong storage, hãy render lại rồi đăng")


# --- Images ---


def run_article_image_job(db: DbSession, job: Job, storage: DirectoryStorage) -> None:
    """An article's "Tạo ảnh AI": one photo in the article's shape (1:1, 4:5 or 1.91:1) from its prompt, added last.
    Counted before the call, as a scene's; a refused prompt or a provider failure fails the job and adds nothing."""
    article = db.get(Article, job.article_id)
    prompt = articles.image_prompt_of(article)
    if not prompt:
        raise JobFailure("Bài chưa có prompt ảnh AI, từ khóa tìm ảnh hay chủ đề để tạo ảnh")
    if article_images.count(db, article.id) >= article_images.MAX_IMAGES:
        raise JobFailure(f"Bài đã đủ {article_images.MAX_IMAGES} ảnh, hãy bỏ bớt ảnh rồi tạo lại")
    provider = job.image_provider or image_providers.default(db)
    db.execute(update(Job).where(Job.id == job.id).values(image_calls=Job.image_calls + 1))
    service_usage.record(db, provider, "image")
    db.commit()
    try:
        data = generate_image(
            image_style.styled(prompt, image_style.get(db)),
            source_keys.get(db, provider),
            provider,
            article.image_aspect,
        )
        if len(data) > MAX_IMAGE_BYTES:
            raise ImageGenError(
                f"Ảnh {image_providers.LABELS.get(provider, provider)} trả về quá 15 MB, hãy bấm tạo lại"
            )
        try:
            extension = image_extension(data)
        except UploadRejected as err:
            raise ImageGenError(str(err)) from None
    except ImageGenError as err:
        raise JobFailure(err.message, err.detail) from None
    # Locked again: a member may have added photos while the provider worked.
    article = db.get(Article, job.article_id, with_for_update=True, populate_existing=True)
    if article_images.count(db, article.id) >= article_images.MAX_IMAGES:
        raise JobFailure(f"Bài đã đủ {article_images.MAX_IMAGES} ảnh, hãy bỏ bớt ảnh rồi tạo lại")
    article_images.add(db, storage, article, data, extension, "ai", f"ai:{_image_model(provider)}")
    db.commit()
    log.info("Job %s: AI photo added to article %s", job.id, article.id)


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
            service_usage.record(db, provider, "image")
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
        old = [scene.image_key, scene.video_key, drop_original(scene)]
        key = new_key(video.id, f"scene-{scene.id}", extension)
        storage.save_bytes(key, data)
        scene.image_key, scene.image_source, scene.image_error = key, f"ai:{_image_model(provider)}", None
        scene.image_auto = False
        # A photo replaces the scene's clip: a scene shows one or the other.
        scene.video_key, scene.video_seconds, scene.video_start, scene.video_speed = None, None, 0, 1
        scene.video_loop = False
        # A new or removed clip has no sound of its own heard, nor words ("Edit từ footage").
        scene.video_sound, scene.words = False, None
        if scene.is_title:
            refresh_thumbnail(db, storage, video, scene)
        db.commit()
        for stale in old:
            if stale and stale != key:
                storage.delete(stale)
        log.info("Image job %s: %s stored", job.id, label)


def run_image_edit_job(db: DbSession, job: Job, storage: DirectoryStorage) -> None:
    """ "Sửa ảnh" on one scene's card (image_edit.py): its photo with the drawn boxes erased (LaMa or Cloudflare) or
    changed as asked in words (Gemini). The photo from before the first edit is kept for "Khôi phục ảnh gốc"; a photo
    between two edits is deleted. Any failure fails the job, and the scene keeps its photo."""
    video = db.get(Video, job.video_id)
    scene = db.get(Scene, job.scene_id) if job.scene_id is not None else None
    if scene is None or scene.video_id != video.id:
        raise JobFailure("Cảnh cần sửa ảnh không còn trong video (đã bị xoá)")
    if not scene.image_key or scene.video_key or not storage.exists(scene.image_key):
        raise JobFailure("Cảnh này không còn ảnh để sửa")
    engine = job.image_provider or "lama"
    key = "" if engine == "lama" else source_keys.get(db, engine)
    if engine != "lama":
        # Counted before the call, like the image job: a killed job keeps the count.
        db.execute(update(Job).where(Job.id == job.id).values(image_calls=Job.image_calls + 1))
        service_usage.record(db, engine, "edit")
        db.commit()
    try:
        data = image_edit.edit(
            storage.path(scene.image_key).read_bytes(), engine, job.edit_boxes, job.edit_prompt or "", key
        )
        if len(data) > MAX_IMAGE_BYTES:
            raise ImageGenError("Ảnh sửa xong quá 15 MB, hãy thử lại")
        extension = image_extension(data)
    except ImageGenError as err:
        raise JobFailure(err.message, err.detail) from None
    except UploadRejected as err:
        raise JobFailure(str(err)) from None
    replaced = scene.image_key
    new = new_key(video.id, f"scene-{scene.id}", extension)
    storage.save_bytes(new, data)
    if scene.image_original_key is None:
        scene.image_original_key, replaced = scene.image_key, None
    # The source stays: an edited stock photo keeps its credit and an edited AI photo is still labelled as AI.
    scene.image_key, scene.image_error, scene.image_auto = new, None, False
    if scene.is_title:
        refresh_thumbnail(db, storage, video, scene)
    db.commit()
    storage.delete(replaced)
    log.info("Image edit job %s: scene %s edited with %s", job.id, scene.id, engine)


def run_image_marks_job(db: DbSession, job: Job, storage: DirectoryStorage) -> None:
    """ "Tìm chữ/logo tự động" in "Sửa ảnh" (image_edit.find_marks): the writing on the scene's photo, kept on the scene
    with the photo it was found on, for the dialog to offer as boxes. Free: a small model on the worker."""
    scene = db.get(Scene, job.scene_id) if job.scene_id is not None else None
    if scene is None or scene.video_id != job.video_id:
        raise JobFailure("Cảnh cần tìm chữ không còn trong video (đã bị xoá)")
    if not scene.image_key or scene.video_key or not storage.exists(scene.image_key):
        raise JobFailure("Cảnh này không còn ảnh để tìm chữ")
    try:
        boxes = image_edit.find_marks(storage.path(scene.image_key).read_bytes())
    except ImageGenError as err:
        raise JobFailure(err.message, err.detail) from None
    scene.image_marks = {"key": scene.image_key, "boxes": boxes}
    db.commit()
    log.info("Image marks job %s: %s box(es) on scene %s", job.id, len(boxes), scene.id)
