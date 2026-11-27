import hashlib
import io
import logging
import math
import re
import tempfile
import time
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from reels_render.blur import parse_blur
from reels_render.effects import COLOR_PRESETS, SCENE_TRANSITIONS
from reels_render.errors import InputError
from reels_render.layers import card_corner, render_card
from reels_render.markup import MarkupError, parse_scene_text
from reels_render.script import MAX_VIDEO_SPEED, MIN_VIDEO_SPEED
from reels_render.sounds import MUSIC_LEVELS
from reels_render.textbox import FRAME_HEIGHT, FRAME_WIDTH

from . import (
    affiliate_rounds,
    article_posts,
    articles,
    auto_photos,
    autoedit,
    brands,
    clips,
    edit_log,
    facebook,
    frames,
    image_edit,
    image_providers,
    knowledge,
    llm,
    media_cleanup,
    music_claims,
    music_topics,
    outro,
    page_queue,
    pinned,
    plans,
    post_comments,
    qc_config,
    remote_media,
    review,
    slot_comments,
    source_keys,
    stock_clips,
    text_looks,
    tts,
    video_options,
    voice_format,
    youtube_meta,
)
from .analytics import VIETNAM
from .claude import GeneratedScript
from .db import get_db
from .duplicate import MAX_NAME_LENGTH, duplicate_video, variant_drafts
from .errors import ApiError
from .models import (
    AffiliateProduct,
    AppSetting,
    Article,
    ArticlePlanSlot,
    EditTemplate,
    Fanpage,
    Job,
    KnowledgeTopic,
    MusicTrack,
    PageQueueItem,
    Publication,
    Scene,
    Session,
    TopicDoc,
    TopicPlanItem,
    User,
    Video,
    VideoNote,
)
from .openverse import Openverse, OpenverseError
from .ownership import ensure_can_take_down, ensure_group_editor, ensure_none_of_others, ensure_owner, ensure_page_owner
from .pexels import Pexels, PexelsError
from .pixabay import ORIENTATIONS, Pixabay, PixabayError
from .script_rules import CROSSFADE_SIDE_SECONDS, MAX_SECONDS, MIN_SECONDS, plain_title, text_problem
from .sessions import current_member, now
from .stock_sites import stock_site
from .storage import DirectoryStorage, get_storage
from .unsplash import Unsplash, UnsplashError
from .uploads import (
    MAX_IMAGE_BYTES,
    MAX_MUSIC_BYTES,
    UploadRejected,
    check_mp3,
    file_label,
    image_extension,
    read_limited,
)
from .videos import (
    JOB_KINDS,
    LIVE_POST_STATUSES,
    MAX_VOICE_BYTES,
    MODES,
    OPEN_POST_STATUSES,
    active_job,
    auto_seconds,
    drop_original,
    ensure_unlocked,
    follow_narration,
    framable,
    group_video_mode,
    is_card_layer,
    list_extras,
    list_payload,
    lock_scene,
    lock_video,
    made_from,
    made_voice_seconds,
    new_key,
    pending_publication,
    photo_fit,
    posted_fanpage_ids,
    publications_of,
    refresh_thumbnail,
    remove_custom_voice,
    render_signature,
    resolve_video_mode,
    run_checks,
    scene_still,
    set_custom_voice,
    split_scenes,
    spoken,
    text_floor,
    text_position,
    text_reserve,
    thumbnail_url,
    video_name,
    video_not_found,
    video_payload,
)
from .videos import (
    content_types as videos_content_types,
)
from .wikimedia import Wikimedia, WikimediaError

router = APIRouter(prefix="/api")

MAX_TOPIC_LENGTH = 300
MAX_CONTENT_TYPE_LENGTH = 40  # videos.content_type
MAX_TEXT_LENGTH = 500
MAX_VOICE_LENGTH = 1000
MAX_LONG_TEXT_LENGTH = 5000
MAX_KEYWORDS = 10
MAX_KEYWORD_LENGTH = 100
MAX_LIST_ITEMS = 20
MAX_EXTRA_COMMENTS = 12
NEW_SCENE_SECONDS = 4
MAX_MUSIC_START = 600  # seconds into a song; past its end the song loops from its start
TITLE_SECONDS = 3  # as the script job gives the title scene
# "Tự viết": a pasted script's limits, well past what a 150-second video can hold.
MAX_SCRIPT_LENGTH = 5000
MAX_HAND_SCENES = 20
VOICE_LINE = re.compile(r"^đọc\s*:\s*(.*)$", re.IGNORECASE)
# "Tìm lại ảnh" runs inside the request, so Pixabay gets about 10 seconds in total.
FIND_IMAGE_SECONDS = 10
IMAGE_TYPES = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
CLIP_TYPES = {"mp4": "video/mp4", "webm": "video/webm"}
# Scene length a new clip sets, so the whole clip plays without being longer than a scene may be.
MAX_CLIP_SCENE_SECONDS = 10
MAX_TOPIC_NAME_LENGTH = 100
# The upload takes a few minutes, and Facebook wants the time at least 10 minutes after it and within 29 days.
MIN_SCHEDULE_DELAY = timedelta(minutes=15)
MAX_SCHEDULE_DELAY = timedelta(days=29)


class NewVideoBody(BaseModel):
    topic: str
    knowledge_topic_id: int | None = None
    plan_item_id: int | None = None  # the 30-day plan idea the video is made from
    # "ai": the script job writes it; "manual" ("Tự viết"): no AI, the scenes come from `script`, or one empty scene.
    mode: Literal["ai", "manual"] = "ai"
    script: str = ""
    ai_effects: bool = False  # "AI gợi ý hiệu ứng": the script call also picks each scene's effects (AI scripts only)
    # How the video is built (videos.MODES): "slides", or "single" ("Video xuyên suốt", one backdrop). None: its
    # group's "Kiểu video" (videos.resolve_video_mode).
    video_mode: Literal["slides", "single"] | None = None


class VideoPatchBody(BaseModel):
    name: str | None = None  # "Tên video" in the lists; "" or null: back to the title's text. Metadata only.
    caption: str | None = None
    hashtags: list[str] | None = None
    affiliates: list[str] | None = None
    pinned_survey: str | None = None  # "Dòng khảo sát", the pinned comment's last line (pinned.py); "" for none
    extra_comments: list[str] | None = None  # "Bình luận thêm", at most MAX_EXTRA_COMMENTS
    music_suggestions: list[str] | None = None
    music_volume: int | None = None
    music_start: object = None  # seconds into the song where the video's music starts
    voice_enabled: bool | None = None
    options: dict | None = None  # some of video_options.DEFAULTS
    mode: str | None = None  # videos.MODES; switching keeps every photo, clip and layer
    content_type: str | None = None  # "Loại nội dung"; "" for none
    # "Không dùng tiêu đề": true empties the title scene's text (kept in `kept_title`) and lets the video be approved
    # without one; false gives the kept text back.
    no_title: bool | None = None
    keep_media: bool | None = None  # "Giữ media": the worker never deletes this video's media files (media_cleanup.py)


class ScenePatchBody(BaseModel):
    text: str | None = None
    seconds: float | None = None  # typing the seconds turns "Tự khớp lời đọc" off
    seconds_auto: bool | None = None  # true: the seconds follow the narration (at once when it is already made)
    keywords: list[str] | None = None
    keywords_en: list[str] | None = None
    image_prompt: str | None = None
    voice_text: str | None = None
    voice_id: object = None  # the scene's own voice; "" or null: the video's (video_options.scene_voice)
    video_start: float | None = None
    video_speed: float | None = None
    video_sound: bool | None = None  # "Tiếng gốc": the clip's own sound is heard in the render
    video_loop: bool | None = None  # "Lặp clip": a short clip starts again instead of holding its last frame
    text_position: object = None  # the text box centre [x, y]; null: back to the video's (or template's)
    image_checked: bool | None = None  # true: a member looked at the app's pick and keeps it ("Giữ ảnh này")
    transition: object = None  # the transition into this scene (reels_render.effects); null: the video's
    color: object = None  # its colour preset; null: as shot
    text_zone: object = None  # "top" or null (the lower zone): where PC Shopee's tiers and captions sit in the scene
    text_hold_sec: object = None  # "Ẩn chữ sau X giây" of the scene, 1–6 in 0.5 steps; null: the video's
    music_level: object = None  # the music's level during the scene (reels_render.sounds); null: the video's
    # "Khung ảnh" (reels_render.framing): "cover", "whole", "square"; null: "Tự động", by the photo's shape.
    image_fit: object = None
    image_crop_offset: object = None  # where the square is cut along the photo's longer side, 0–1; null: the middle


# What "Khung ảnh" may be set to; null is "Tự động".
IMAGE_FIT_CHOICES = ("cover", "whole", "square")


class PublishBody(BaseModel):
    fanpage_id: int
    scheduled_at: datetime | None = None
    # "Tự bình luận": the worker writes the affiliate comment under the reel once it is live (post_comments.py).
    auto_comment: bool = True
    # "Vẫn hẹn": the Page already has a post at that time and the member said two at once is meant.
    allow_overlap: bool = False


class ReelLinkBody(BaseModel):
    url: str


class SceneOrderBody(BaseModel):
    ids: list[int]


class SplitBody(BaseModel):
    at: float  # seconds into the scene where the second part begins


def invalid(message: str) -> ApiError:
    return ApiError(422, "invalid_value", message)


def _clean_text(value: str, limit: int, label: str) -> str:
    value = unicodedata.normalize("NFC", value.replace("\r\n", "\n"))
    if len(value) > limit:
        raise invalid(f"{label} dài quá {limit} ký tự")
    return value


def _clean_list(values: list[str], limit: int, label: str, max_items: int = MAX_LIST_ITEMS) -> list[str]:
    items = [unicodedata.normalize("NFC", value).strip() for value in values]
    items = [item for item in items if item]
    if len(items) > max_items or any(len(item) > limit for item in items):
        raise invalid(f"{label}: tối đa {max_items} mục, mỗi mục tối đa {limit} ký tự")
    return items


def _saved(db: DbSession, video: Video) -> dict:
    db.commit()
    return video_payload(db, video)


def _enqueue(
    db: DbSession,
    video: Video,
    kind: str,
    me: Session,
    retry_of: Job | None = None,
    scene_id: int | None = None,
    image_provider: str | None = None,
    publication_id: int | None = None,
    edit_boxes: list | None = None,
    edit_prompt: str | None = None,
) -> None:
    """Callers hold the video lock; the partial unique index is the last guard against a second job."""
    ensure_unlocked(db, video)
    db.add(
        Job(
            video_id=video.id,
            kind=kind,
            status="queued",
            created_by_id=me.user_id,
            retry_of_id=retry_of.id if retry_of else None,
            scene_id=scene_id,
            image_provider=image_provider,
            publication_id=publication_id,
            edit_boxes=edit_boxes,
            edit_prompt=edit_prompt,
        )
    )
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "video_locked", "Video đang có job chờ hoặc đang chạy") from None


def _ensure_renderable(db: DbSession, video: Video) -> None:
    if video.mode == "upload":
        raise ApiError(409, "upload_video", "Video “MP4 tải lên” đã có MP4 hoàn chỉnh, không render lại")
    if not video.has_script:
        raise ApiError(409, "no_script", "Video chưa có kịch bản")
    media_cleanup.ensure_media(video, "render")
    title, scenes = split_scenes(db, video)
    checks = run_checks(db, video, title, scenes)
    if checks.blocking:
        raise ApiError(409, "render_blocked", f"Chưa render được: {checks.blocking[0].message}")


# --- Videos ---


@router.get("/videos")
def list_videos(
    q: str = "",
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    knowledge_topic_id: int | None = None,
    fanpage_id: int | None = None,
) -> list[dict]:
    """Every video, newest first; `q` searches the name, the topic and the title, `knowledge_topic_id` keeps one topic group's
    (its "Video" tab in Kho kiến thức) and `fanpage_id` the ones posted on, or waiting in the queue of, one Page."""
    query = select(Video).order_by(Video.created_at.desc(), Video.id.desc())
    if knowledge_topic_id is not None:
        query = query.where(Video.knowledge_topic_id == knowledge_topic_id)
    if fanpage_id is not None:
        query = query.where(
            or_(
                Video.id.in_(select(Publication.video_id).where(Publication.fanpage_id == fanpage_id)),
                Video.id.in_(select(PageQueueItem.video_id).where(PageQueueItem.fanpage_id == fanpage_id)),
            )
        )
    if q.strip():
        literal = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{unicodedata.normalize('NFC', literal)}%"
        plain = func.replace(func.replace(Scene.text, "*", ""), "\n", " ")
        title_match = select(Scene.video_id).where(Scene.is_title, plain.ilike(pattern, escape="\\"))
        query = query.where(
            or_(
                Video.topic.ilike(pattern, escape="\\"),
                Video.name.ilike(pattern, escape="\\"),
                Video.id.in_(title_match),
            )
        )
    family = made_from(db)
    videos = db.scalars(query).all()
    extras = list_extras(db, videos)
    return [list_payload(db, video, family, extras[video.id]) for video in videos]


@router.get("/video-content-types")
def content_types(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> list[str]:
    """The "Loại nội dung" the team's videos use, to pick from (videos.content_types)."""
    return videos_content_types(db)


@router.post("/videos", status_code=201)
def create_video(body: NewVideoBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    return _saved(db, start_video(body, me, db))


def start_video(
    body: NewVideoBody,
    me: Session,
    db: DbSession,
    written: GeneratedScript | None = None,
    via: str = "",
    app: str = "",
    on: date | None = None,
) -> Video:
    """A new video, its script queued, typed ("Tự viết") or, as `written`, already written from the group's prompt by
    a member's own Claude through MCP (`via` "assistant"): saved as the script job saves an answer, with no LLM call.
    Every way of making a video comes here, so its mode is decided here: the one asked, else its group's "Kiểu video"
    on `on` (the day it is made for; today in Vietnam by default). The caller commits."""
    topic = " ".join(unicodedata.normalize("NFC", body.topic).split())
    if not topic:
        raise invalid("Hãy nhập chủ đề")
    if len(topic) > MAX_TOPIC_LENGTH:
        raise invalid(f"Chủ đề dài quá {MAX_TOPIC_LENGTH} ký tự")
    group = db.get(KnowledgeTopic, body.knowledge_topic_id) if body.knowledge_topic_id else None
    if group is None:
        raise invalid("Hãy chọn nhóm chủ đề")
    manual = body.mode == "manual"
    if not manual and not group.script_prompt:
        raise invalid(f"Nhóm chủ đề “{group.name}” chưa có prompt viết kịch bản")
    scenes = hand_written_scenes(body.script) if manual else []
    idea = _free_idea(db, body.plan_item_id, group) if body.plan_item_id is not None else None
    video = Video(
        topic=topic,
        knowledge_topic_id=group.id,
        has_script=manual,
        created_by_id=me.user_id,
        ai_effects=body.ai_effects and not manual,
        mode=resolve_video_mode(body.video_mode, group, on),
        written_via=via,
        assistant_app=app,
    )
    video_options.apply_defaults(db, video, me.user_id)
    db.add(video)
    db.flush()
    apply_default_music(db, video, get_storage(), me.user_id)
    if idea is not None:
        idea.video_id = video.id
    if manual:
        _write_by_hand(db, video, topic, scenes)
        autoedit.apply_default(db, video)
        outro.add(db, get_storage(), video)
    elif written is not None:
        # Imported here: the job module loads the render core, which the routes otherwise do not need at import.
        from . import jobs

        jobs.save_script(db, video, written)
        outro.add(db, get_storage(), video)
        affiliate_rounds.ask_after_script(db, video, me.user_id)
        # As after a script job: "Tự tìm ảnh" looks for the scenes' photos, unless it is turned off.
        if auto_photos.enabled(db):
            _enqueue(db, video, "photos", me)
    else:
        _enqueue(db, video, "script", me)
    return video


def apply_default_music(db: DbSession, video: Video, storage: DirectoryStorage, user_id: int) -> None:
    """A new video starts with its maker's default music (Cài đặt › Thiết lập mặc định, theirs or the team's),
    copied like "Chọn từ thư viện" does, so editing or deleting the track later never changes the video. Nothing when
    no default is set, the track is gone or it was claimed on YouTube since (music_claims.py). Only new videos: the
    music a video already has is never replaced."""
    track_id = video_options.member_defaults(db, user_id).get("music_track_id")
    track = db.get(MusicTrack, track_id) if track_id else None
    if track is None or track.claimed_on_youtube or not storage.exists(track.storage_key):
        return
    video.music_key, video.music_name = new_key(video.id, "music", "mp3"), track.name
    storage.save_file(video.music_key, storage.path(track.storage_key))


def hand_written_scenes(script: str) -> list[tuple[str, str]]:
    """A pasted script as (on-screen text, voice text) per scene: one scene per paragraph (blank lines between), its
    lines starting with "Đọc:" its voice text, the rest its text with the line breaks kept. No paragraph: one empty
    scene, to fill in on the video page."""
    text = unicodedata.normalize("NFC", script).replace("\r\n", "\n")
    if len(text) > MAX_SCRIPT_LENGTH:
        raise invalid(f"Kịch bản dài quá {MAX_SCRIPT_LENGTH} ký tự")
    scenes = []
    for paragraph in re.split(r"\n\s*\n", text):
        shown, spoken = [], []
        for line in paragraph.split("\n"):
            line = " ".join(line.split())
            voice = VOICE_LINE.match(line)
            if voice:
                spoken.append(voice.group(1).strip())
            elif line:
                shown.append(line)
        if shown or spoken:
            scenes.append(("\n".join(shown), " ".join(part for part in spoken if part)))
    if len(scenes) > MAX_HAND_SCENES:
        raise invalid(f"Kịch bản có quá {MAX_HAND_SCENES} cảnh")
    return scenes or [("", "")]


def _write_by_hand(db: DbSession, video: Video, topic: str, scenes: list[tuple[str, str]]) -> None:
    video.hand_written = True
    video.title_options = [topic]
    db.add(
        Scene(
            video_id=video.id,
            is_title=True,
            position=0,
            text=topic,
            seconds=TITLE_SECONDS,
            seconds_auto=True,
            keywords=[],
        )
    )
    for position, (text, voice) in enumerate(scenes, start=1):
        db.add(
            Scene(
                video_id=video.id,
                is_title=False,
                position=position,
                text=text,
                voice_text=voice,
                seconds=NEW_SCENE_SECONDS,
                seconds_auto=True,
                keywords=[],
                keywords_en=[],
                image_prompt="",
            )
        )


def _free_idea(db: DbSession, item_id: int, group: KnowledgeTopic) -> TopicPlanItem:
    """The plan idea a new video is made from, locked so two members cannot both make it."""
    idea = db.scalar(select(TopicPlanItem).where(TopicPlanItem.id == item_id).with_for_update())
    if idea is None:
        raise ApiError(404, "plan_item_not_found", "Không tìm thấy ý tưởng trong kế hoạch (có thể đã bị xoá)")
    if idea.knowledge_topic_id != group.id:
        raise invalid("Ý tưởng này thuộc nhóm chủ đề khác")
    if idea.video_id is not None:
        raise ApiError(409, "plan_item_used", "Ý tưởng này đã có video")
    return idea


@router.get("/videos/{video_id}")
def get_video(video_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    video = db.get(Video, video_id)
    if video is None:
        raise video_not_found()
    return video_payload(db, video)


@router.patch("/videos/{video_id}")
def patch_video(
    video_id: int,
    body: VideoPatchBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    video = lock_video(db, video_id)
    ensure_unlocked(db, video)
    fields = body.model_fields_set
    title_before, _ = split_scenes(db, video)
    before = edit_log.video_snapshot(video, title_before)
    comments = video.pinned_survey, list(video.extra_comments)
    if "name" in fields:
        name = " ".join(unicodedata.normalize("NFC", body.name or "").split())
        if len(name) > MAX_NAME_LENGTH:
            raise invalid(f"Tên video tối đa {MAX_NAME_LENGTH} ký tự")
        video.name = name or None
    if "caption" in fields and body.caption is not None:
        video.caption = _clean_text(body.caption, MAX_LONG_TEXT_LENGTH, "Caption").strip()
    if "pinned_survey" in fields and body.pinned_survey is not None:
        video.pinned_survey = pinned.normalize(_clean_text(body.pinned_survey, MAX_TEXT_LENGTH, "Dòng khảo sát"))
    if "extra_comments" in fields and body.extra_comments is not None:
        video.extra_comments = _clean_list(
            body.extra_comments, MAX_LONG_TEXT_LENGTH, "Bình luận thêm", max_items=MAX_EXTRA_COMMENTS
        )
    if (video.pinned_survey, list(video.extra_comments)) != comments:
        post_comments.ask_after_edit(db, video)
    if "hashtags" in fields and body.hashtags is not None:
        video.hashtags = _clean_list(body.hashtags, MAX_KEYWORD_LENGTH, "Hashtag")
    if "affiliates" in fields and body.affiliates is not None:
        video.affiliates = _clean_list(body.affiliates, MAX_TEXT_LENGTH, "Affiliate")
    if "music_suggestions" in fields and body.music_suggestions is not None:
        video.music_suggestions = _clean_list(body.music_suggestions, MAX_TEXT_LENGTH, "Gợi ý nhạc")
    if "music_volume" in fields and body.music_volume is not None:
        if not 0 <= body.music_volume <= 100:
            raise invalid("Âm lượng phải từ 0 đến 100%")
        video.music_volume = body.music_volume
    if "music_start" in fields:
        start = body.music_start
        if isinstance(start, bool) or not isinstance(start, (int, float)) or not math.isfinite(start):
            raise invalid("Giây bắt đầu của bài nhạc phải là số")
        if not 0 <= start <= MAX_MUSIC_START:
            raise invalid(f"Giây bắt đầu của bài nhạc phải từ 0 đến {MAX_MUSIC_START}")
        video.music_start = round(start, 1)
    if "voice_enabled" in fields and body.voice_enabled is not None:
        video.voice_enabled = body.voice_enabled
    if "mode" in fields and body.mode is not None:
        if video.mode == "upload":
            raise ApiError(409, "upload_video", "Video “MP4 tải lên” không đổi sang kiểu video khác được")
        if body.mode not in MODES:
            raise invalid("Kiểu video không có trong danh sách")
        video.mode = body.mode
    if "content_type" in fields and body.content_type is not None:
        kind = " ".join(unicodedata.normalize("NFC", body.content_type).split())
        if len(kind) > MAX_CONTENT_TYPE_LENGTH:
            raise invalid(f"Loại nội dung tối đa {MAX_CONTENT_TYPE_LENGTH} ký tự")
        video.content_type = kind
    if "keep_media" in fields and body.keep_media is not None:
        video.keep_media = body.keep_media
    if "no_title" in fields and body.no_title is not None and body.no_title != video.no_title:
        _set_no_title(db, storage, video, body.no_title)
    look = video_options.text_look(video), video_options.effective(video)["title_text_position"]
    pause = video_options.voice_pause(video)
    if body.options:
        # The channel and its logo switch live in the options but are checked apart (brands.py).
        rest = brands.apply_video_options(db, video, me.user_id, body.options)
        try:
            changes = video_options.clean(rest)
        except video_options.OptionError as err:
            raise invalid(str(err)) from None
        sfx = video_options.effective(video)["title_sfx"]
        video.options = video_options.effective(video) | changes
        if video_options.effective(video)["title_sfx"] != sfx:
            from . import motion as motion_module
            from . import title_motion

            title, _ = split_scenes(db, video)
            if title is not None and motion_module.shows_motion(title):  # a classic title has no tings
                title_motion.sync_title_sfx(video, title)
    if video_options.voice_pause(video) != pause:
        title, scenes = split_scenes(db, video)
        follow_narration(video, [scene for scene in (title, *scenes) if scene is not None])
    if (video_options.text_look(video), video_options.effective(video)["title_text_position"]) != look:
        # The thumbnail is the title scene's first frame, drawn in the text box style at the title's place.
        title, _ = split_scenes(db, video)
        refresh_thumbnail(db, storage, video, title)
    _log_video_edit(db, video, me, before, title_before)
    return _saved(db, video)


def _log_video_edit(db: DbSession, video: Video, me: Session, before: dict, *scenes: Scene | None) -> None:
    """One "Lịch sử sửa" entry for what this edit changed in the video and `scenes` (edit_log.VIDEO)."""
    changes = edit_log.diff(before, edit_log.video_snapshot(video, *scenes))
    title, _ = split_scenes(db, video)
    label = video_name(video, title)
    edit_log.record(db, edit_log.VIDEO, video.id, "update", me.user_id, label=label, changes=changes)


def _set_no_title(db: DbSession, storage: DirectoryStorage, video: Video, no_title: bool) -> None:
    """ "Không dùng tiêu đề": ticked, the title scene's text is kept aside and emptied; unticked, it comes back (unless
    a member has typed a new one since). The MP4 is then outdated, as with any edit of the title."""
    title, _ = split_scenes(db, video)
    if title is None:
        raise invalid("Video này không có cảnh tiêu đề")
    if no_title:
        video.kept_title = title.text if title.text.strip() else None
        title.text = ""
    else:
        if not title.text.strip() and video.kept_title:
            title.text = video.kept_title
        video.kept_title = None
    video.no_title = no_title
    refresh_thumbnail(db, storage, video, title)


class GroupBody(BaseModel):
    knowledge_topic_id: int


@router.put("/videos/{video_id}/group")
def move_video(
    video_id: int, body: GroupBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Chuyển sang nhóm khác": the video, by its maker, to another topic group. Its look, mode and MP4 stay as they
    are (a group's settings are taken when a video is made); the old group's plan idea made from it is freed, so that
    plan shows the idea as still to make."""
    video = lock_video(db, video_id)
    ensure_unlocked(db, video)
    group = topic_group(db, body.knowledge_topic_id)
    if video.created_by_id != me.user_id:
        # The maker of the group a teammate's video sits in may send it back to a group of the video's maker, so
        # that their own group can be emptied and deleted without anyone deleting the teammate's work.
        current = db.get(KnowledgeTopic, video.knowledge_topic_id) if video.knowledge_topic_id else None
        if current is None or current.created_by_id != me.user_id or group.created_by_id != video.created_by_id:
            ensure_owner(video.created_by_id, me.user_id, "video này", "chuyển nhóm được")
    if group.id == video.knowledge_topic_id:
        raise invalid(f"Video đã ở nhóm “{group.name}”")
    place_in_group(db, video, group)
    return _saved(db, video)


def topic_group(db: DbSession, knowledge_topic_id: int) -> KnowledgeTopic:
    group = db.get(KnowledgeTopic, knowledge_topic_id)
    if group is None:
        raise ApiError(404, "topic_not_found", "Không tìm thấy nhóm chủ đề")
    return group


def place_in_group(db: DbSession, video: Video, group: KnowledgeTopic) -> None:
    """The video into another topic group; the old group's plan idea made from it is freed."""
    for idea in db.scalars(select(TopicPlanItem).where(TopicPlanItem.video_id == video.id)):
        idea.video_id = None
    video.knowledge_topic_id = group.id


@router.delete("/videos/{video_id}")
def delete_video(
    video_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    video = lock_video(db, video_id)
    ensure_owner(video.created_by_id, me.user_id, "video này")
    ensure_none_of_others(_others_work_in_video(db, video, me.user_id), "Video")
    ensure_unlocked(db, video)
    db.execute(delete(Video).where(Video.id == video_id))
    db.commit()
    # Files only go after the rows: a failed commit must not leave a video whose photos are gone.
    storage.delete_prefix(f"videos/{video_id}")
    return {"ok": True}


def _others_work_in_video(db: DbSession, video: Video, user_id: int) -> dict[str, int]:
    """What teammates made in the video that deleting it would take with it: posts, notes, queue places."""

    def count(model, owner) -> int:
        return db.scalar(select(func.count()).select_from(model).where(model.video_id == video.id, owner != user_id))

    return {
        "bài đăng": count(Publication, Publication.created_by_id),
        "góp ý": count(VideoNote, VideoNote.created_by_id),
        "lượt trong hàng chờ": count(PageQueueItem, PageQueueItem.added_by_id),
    }


@router.post("/videos/{video_id}/script")
def write_script(video_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    video = lock_video(db, video_id)
    if video.has_script:
        raise ApiError(409, "script_exists", "Video đã có kịch bản")
    # A cancelled clone draft reruns the clone with the snapshot and change request it was made with; a video made
    # from a sample video writes from it again, and in the way "review" this is how the edited analysis is written.
    kind = "learn" if video.reference_mode else ("clone" if video.clone_source else "script")
    _enqueue(db, video, kind, me)
    return _saved(db, video)


@router.post("/videos/{video_id}/render")
def render(video_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    video = lock_video(db, video_id)
    ensure_unlocked(db, video)
    _ensure_renderable(db, video)
    _enqueue(db, video, "render", me)
    return _saved(db, video)


@router.post("/videos/{video_id}/voices")
def make_narration(video_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Tạo giọng thật" in the preview: the video's voice (ElevenLabs, VieNeu, Gemini or Google) reads the scenes whose narration is
    missing or out of date.
    It costs credit once per text; the render reuses those MP3s, so a render after it pays nothing more."""
    video = lock_video(db, video_id)
    ensure_unlocked(db, video)
    if not video.has_script:
        raise ApiError(409, "no_script", "Video chưa có kịch bản")
    if not video.voice_enabled:
        raise ApiError(409, "voice_off", "Video đang tắt giọng đọc")
    title, scenes = split_scenes(db, video)
    missing = [
        scene
        for scene in (title, *scenes)
        if scene is not None and spoken(video, scene) and made_voice_seconds(video, scene) is None
    ]
    if not missing:
        voice = video_options.voice_id(video)
        raise ApiError(409, "voices_ready", f"Mọi cảnh đã có giọng {tts.service_name(voice)}")
    _enqueue(db, video, "voice", me)
    return _saved(db, video)


def _image_provider(db: DbSession, requested: str | None) -> str:
    try:
        return image_providers.choose(db, requested)
    except ValueError:
        raise invalid("Nguồn ảnh AI không hợp lệ") from None


@router.post("/videos/{video_id}/image")
def generate_images(
    video_id: int, provider: str | None = None, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """`provider`: the one picked from the button's arrow for this press; the team's default otherwise."""
    video = lock_video(db, video_id)
    if not video.has_script:
        raise ApiError(409, "no_script", "Video chưa có kịch bản")
    # Scenes that already have a photo or a clip are skipped by the job, so pressing this
    # again after a partial run only pays for the scenes still missing a photo.
    _enqueue(db, video, "image", me, image_provider=_image_provider(db, provider))
    return _saved(db, video)


@router.post("/scenes/{scene_id}/image-ai")
def generate_scene_image(
    scene_id: int, provider: str | None = None, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Tạo ảnh AI" / "Tạo lại ảnh AI" on one scene's card: a job that makes that scene's photo, replacing its photo
    or clip. The card asks first when the scene already has one."""
    video, scene = lock_scene(db, scene_id)
    if not video.has_script:
        raise ApiError(409, "no_script", "Video chưa có kịch bản")
    _enqueue(db, video, "image", me, scene_id=scene.id, image_provider=_image_provider(db, provider))
    return _saved(db, video)


class ImageEditBody(BaseModel):
    engine: str
    # [x, y, width, height] fractions of the photo as shown; "Xóa vùng" only.
    boxes: list = []
    prompt: str = ""


@router.post("/scenes/{scene_id}/image-edit")
def edit_scene_image(
    scene_id: int, body: ImageEditBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Sửa ảnh" on one scene's card (image_edit.py): an image_edit job that erases the boxes drawn over the photo
    (`lama` on the worker, free, or `cloudflare`) or changes it as asked in words (`gemini`, paid)."""
    if body.engine not in image_edit.ENGINES:
        raise invalid("Cách sửa ảnh không hợp lệ")
    try:
        boxes = image_edit.clean_boxes(body.boxes) if body.engine in image_edit.ERASERS else None
        prompt = image_edit.clean_prompt(body.prompt, required=body.engine == "gemini")
    except ValueError as err:
        raise invalid(str(err)) from None
    if body.engine != "lama" and not image_providers.configured(db, body.engine):
        name = image_edit.LABELS[body.engine]
        raise invalid(f"Chưa cài đặt {name}: nhập key ở Cài đặt › AI và nguồn tư liệu")
    video, scene = lock_scene(db, scene_id)
    if not scene.image_key or scene.video_key:
        raise ApiError(409, "no_image", "Cảnh này chưa có ảnh để sửa")
    _enqueue(
        db,
        video,
        "image_edit",
        me,
        scene_id=scene.id,
        image_provider=body.engine,
        edit_boxes=boxes,
        edit_prompt=prompt or None,
    )
    return _saved(db, video)


@router.post("/scenes/{scene_id}/image-marks")
def find_scene_image_marks(
    scene_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Tìm chữ/logo tự động" in "Sửa ảnh": a free job that finds the writing on the scene's photo; the boxes come
    back on the scene (`image_marks`) for the dialog to offer."""
    video, scene = lock_scene(db, scene_id)
    if not scene.image_key or scene.video_key:
        raise ApiError(409, "no_image", "Cảnh này chưa có ảnh để tìm chữ")
    _enqueue(db, video, "image_marks", me, scene_id=scene.id)
    return _saved(db, video)


class VideoBlurBody(BaseModel):
    # [x, y, width, height] fractions of the 1080x1920 frame; empty takes the blur away.
    boxes: list = []


@router.post("/scenes/{scene_id}/video-blur")
def set_scene_video_blur(
    scene_id: int,
    body: VideoBlurBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """ "Làm mờ vùng" on a clip scene: boxes blurred for the whole scene (a logo or a channel name burned into the
    clip), kept with the clip they were drawn on. Nothing is rendered now; the next render blurs them."""
    try:
        boxes = parse_blur(body.boxes, "Vùng làm mờ")
    except InputError as err:
        raise invalid(str(err)) from None
    video, scene = lock_scene(db, scene_id)
    ensure_unlocked(db, video)
    if not scene.video_key:
        raise ApiError(409, "no_clip", "Cảnh này không có video để làm mờ")
    scene.video_blur = {"key": scene.video_key, "boxes": [list(box) for box in boxes]} if boxes else None
    if scene.is_title:
        title, _ = split_scenes(db, video)
        refresh_thumbnail(db, storage, video, title)
    return _saved(db, video)


@router.post("/scenes/{scene_id}/image-original")
def restore_scene_image(
    scene_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """ "Khôi phục ảnh gốc": the photo the scene had before "Sửa ảnh", in place of the edited one."""
    video, scene = lock_scene(db, scene_id)
    ensure_unlocked(db, video)
    if not scene.image_key or not scene.image_original_key:
        raise ApiError(409, "no_original", "Ảnh của cảnh này chưa được sửa")
    edited = scene.image_key
    scene.image_key, scene.image_original_key, scene.image_error = scene.image_original_key, None, None
    if scene.is_title:
        title, _ = split_scenes(db, video)
        refresh_thumbnail(db, storage, video, title)
    payload = _saved(db, video)
    storage.delete(edited)
    return payload


@router.post("/videos/{video_id}/publish")
def publish(
    video_id: int, body: PublishBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    video = lock_video(db, video_id)
    ensure_unlocked(db, video)
    if not video.mp4_key:
        raise ApiError(409, "no_mp4", "Video chưa có MP4, hãy render trước")
    title, scenes = split_scenes(db, video)
    if video.rendered_signature != render_signature(video, title, scenes):
        raise ApiError(409, "mp4_outdated", "MP4 chưa cập nhật theo bản sửa, hãy render lại rồi đăng")
    review.ensure_approved(video)
    when = body.scheduled_at
    if when is not None:
        if when.tzinfo is None:
            raise invalid("Giờ đăng phải kèm múi giờ")
        if not now() + MIN_SCHEDULE_DELAY <= when <= now() + MAX_SCHEDULE_DELAY:
            raise invalid("Giờ hẹn phải sau ít nhất 15 phút và trong vòng 29 ngày tới")
    fanpage = db.get(Fanpage, body.fanpage_id)
    if fanpage is None or not fanpage.active:
        raise invalid("Hãy chọn một Fanpage đang dùng")
    ensure_page_owner(fanpage, me.user_id)
    if wrong := brands.mismatch(db, video, fanpage):
        raise ApiError(409, "brand_mismatch", wrong)
    if fanpage.id in posted_fanpage_ids(video, publications_of(db, video.id)):
        raise ApiError(
            409, "already_published", "Bản MP4 này đang có trên Fanpage đó, hãy render bản mới hoặc xóa bài cũ"
        )
    if when is not None and not body.allow_overlap and (clash := page_queue.post_near(db, fanpage, when, video.id)):
        raise ApiError(
            409,
            "slot_taken",
            f"Page “{fanpage.name}” đã có bài lúc {clash.astimezone(VIETNAM):%H:%M %d/%m} "
            "(gần giờ hẹn dưới 30 phút). Chọn giờ khác hoặc bấm Vẫn hẹn.",
        )
    post = pending_publication(db, video.id)
    if post is None:
        post = Publication(video_id=video.id, platform="facebook", created_by_id=me.user_id)
        db.add(post)
    # A reel belongs to its Page: moving the post would leave the first reel to go live by itself.
    elif post.remote_id and post.fanpage_id != fanpage.id:
        raise ApiError(409, "other_fanpage", "Video đã tải lên Fanpage khác, hãy đăng lại trên Fanpage đó")
    post.fanpage_id, post.scheduled_at, post.created_by_id = fanpage.id, when, me.user_id
    post.auto_comment = body.auto_comment
    _enqueue(db, video, "publish", me)
    return _saved(db, video)


@router.post("/posts/{post_id}/take-down")
def take_down(post_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Hủy đăng" and "Xóa". A post Facebook never received ends here; any other goes through the worker, which alone
    calls Facebook. Which of the two it ends as is decided there, by whether the reel really went live."""
    video_id = db.scalar(select(Publication.video_id).where(Publication.id == post_id))
    if video_id is None:
        raise ApiError(404, "post_not_found", "Không tìm thấy bài đăng")
    video = lock_video(db, video_id)
    post = db.scalar(select(Publication).where(Publication.id == post_id).execution_options(populate_existing=True))
    if post.platform != "facebook":
        # Instagram's own "Hủy hẹn" is routes_instagram.cancel; nothing here may ask Facebook about another platform.
        raise ApiError(404, "post_not_found", "Không tìm thấy bài đăng")
    ensure_can_take_down(db, post, me.user_id)
    if post.status not in OPEN_POST_STATUSES:
        raise ApiError(409, "post_closed", "Bài này đã hủy hoặc đã xóa")
    job = active_job(db, video.id)
    if job is not None and job.kind == "publish" and job.status == "queued":
        job.status, job.finished_at = "cancelled", now()
        db.flush()  # before the insert below: one active job per video
    elif job is not None:
        raise ApiError(409, "video_locked", "Video đang có job chạy, hãy đợi xong rồi hủy hoặc xóa bài")
    if post.remote_id is None:
        post.status, post.closed_at, post.closed_by_id = "cancelled", now(), me.user_id
    else:
        _enqueue(db, video, "unpublish", me, publication_id=post.id)
    return _saved(db, video)


@router.post("/posts/{post_id}/check")
def check_post(post_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Kiểm tra": read the reel on Facebook and record what it says, after a change made in Meta Business Suite."""
    video_id = db.scalar(select(Publication.video_id).where(Publication.id == post_id))
    if video_id is None:
        raise ApiError(404, "post_not_found", "Không tìm thấy bài đăng")
    video = lock_video(db, video_id)
    post = db.scalar(select(Publication).where(Publication.id == post_id).execution_options(populate_existing=True))
    if post.platform != "facebook" or post.status not in (*LIVE_POST_STATUSES, "deleted") or post.remote_id is None:
        raise ApiError(409, "post_not_checkable", "Chỉ kiểm tra được bài đã lên Facebook, đã hẹn giờ hoặc đã xóa")
    if active_job(db, video.id) is not None:
        raise ApiError(409, "video_locked", "Video đang có job chạy, hãy đợi xong rồi kiểm tra bài")
    _enqueue(db, video, "check", me, publication_id=post.id)
    return _saved(db, video)


@router.post("/posts/{post_id}/reel-link")
def set_reel_link(
    post_id: int, body: ReelLinkBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Sửa link reel": the reel the app saved for a post is not the one on Facebook (a post marked deleted while the
    reel is live). Saves the id in the link and queues a check, which reads that reel and sets the post right."""
    video_id = db.scalar(select(Publication.video_id).where(Publication.id == post_id))
    if video_id is None:
        raise ApiError(404, "post_not_found", "Không tìm thấy bài đăng")
    video = lock_video(db, video_id)
    post = db.scalar(select(Publication).where(Publication.id == post_id).execution_options(populate_existing=True))
    ensure_can_take_down(db, post, me.user_id)
    if post.platform != "facebook" or post.status not in (*LIVE_POST_STATUSES, "deleted") or post.remote_id is None:
        raise ApiError(409, "post_not_checkable", "Chỉ sửa link được bài đã lên Facebook, đã hẹn giờ hoặc đã xóa")
    reel_id = facebook.reel_id_from_link(body.url)
    if reel_id is None:
        raise ApiError(
            422, "invalid_reel_link", "Link không đúng dạng, hãy dán link reel như facebook.com/reel/123456789"
        )
    if active_job(db, video.id) is not None:
        raise ApiError(409, "video_locked", "Video đang có job chạy, hãy đợi xong rồi sửa link")
    taken = db.scalar(select(Publication.id).where(Publication.remote_id == reel_id, Publication.id != post.id))
    if taken is not None:
        raise ApiError(409, "reel_in_use", "Reel này đã gắn với một bài đăng khác")
    logging.getLogger(__name__).info(
        "Member %s changed the reel of post %s from %s to %s", me.user_id, post.id, post.remote_id, reel_id
    )
    post.remote_id = reel_id
    _enqueue(db, video, "check", me, publication_id=post.id)
    return _saved(db, video)


@router.post("/videos/{video_id}/music")
def upload_music(
    video_id: int,
    file: UploadFile = File(...),
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    data = read_limited(file, MAX_MUSIC_BYTES, "File nhạc quá 20 MB, hãy chọn file nhỏ hơn")
    try:
        check_mp3(data)
    except UploadRejected as err:
        raise ApiError(415, "invalid_music", str(err)) from None
    video = lock_video(db, video_id)
    ensure_unlocked(db, video)
    old = video.music_key
    video.music_key, video.music_name = new_key(video.id, "music", "mp3"), file_label(file.filename, "nhac.mp3")
    storage.save_bytes(video.music_key, data)
    payload = _saved(db, video)
    storage.delete(old)
    return payload


class LibraryMusicBody(BaseModel):
    track_id: int


@router.post("/videos/{video_id}/music/from-library")
def music_from_library(
    video_id: int,
    body: LibraryMusicBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    video = lock_video(db, video_id)
    ensure_unlocked(db, video)
    track = db.get(MusicTrack, body.track_id)
    if track is None or not storage.exists(track.storage_key):
        raise ApiError(404, "track_not_found", "Không tìm thấy bài nhạc (có thể đã bị xóa)")
    music_claims.ensure_usable(track)
    old = video.music_key
    # A copy of its own, like a clone's music: editing or deleting the track never changes this video.
    video.music_key, video.music_name = new_key(video.id, "music", "mp3"), track.name
    storage.save_file(video.music_key, storage.path(track.storage_key))
    payload = _saved(db, video)
    storage.delete(old)
    return payload


@router.delete("/videos/{video_id}/music")
def remove_music(
    video_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    video = lock_video(db, video_id)
    ensure_unlocked(db, video)
    old, video.music_key, video.music_name = video.music_key, None, None
    payload = _saved(db, video)
    storage.delete(old)
    return payload


class CloneBody(BaseModel):
    request: str
    # "tiktok": the TikTok version of a Facebook video ("Tạo bản TikTok"), linked to it; empty: the same platform.
    platform: str | None = None


def _one_line(text: str) -> str:
    return " / ".join(line.strip() for line in text.split("\n") if line.strip())


def clone_snapshot(db: DbSession, video: Video, request: str) -> dict:
    """What the clone prompt sees: the source exactly as edited at the moment "Nhân bản" was pressed."""
    title, scenes = split_scenes(db, video)
    lines = []

    def voice(scene: Scene) -> str:
        return f" — lời đọc: {_one_line(scene.voice_text)}" if scene.voice_text.strip() else ""

    if title is not None:
        lines.append(f"Cảnh tiêu đề ({title.seconds:g} giây): {_one_line(title.text)}{voice(title)}")
    for number, scene in enumerate(scenes, start=1):
        keywords = f" — từ khóa ảnh: {', '.join(scene.keywords)}" if scene.keywords else ""
        lines.append(f"Cảnh {number} ({scene.seconds:g} giây): {_one_line(scene.text)}{voice(scene)}{keywords}")
    if video.caption:
        lines.append(f"Caption: {video.caption}")
    if video.hashtags:
        lines.append(f"Hashtag: {' '.join(video.hashtags)}")
    if video.affiliates:
        lines.append(f"Affiliate: {'; '.join(video.affiliates)}")
    comment = pinned.text_of(db, video)
    if comment:
        lines.append(f"Bình luận ghim: {comment}")
    return {
        "video_id": video.id,
        "title": video_name(video, title),
        "topic": video.topic,
        "script": "\n".join(lines),
        "request": request,
    }


@router.post("/videos/{video_id}/clone", status_code=201)
def clone_video(
    video_id: int,
    body: CloneBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    request = " ".join(unicodedata.normalize("NFC", body.request).split())
    if not request:
        raise invalid("Hãy nhập yêu cầu đổi, ví dụ: đổi sang mốc 45 tuổi, tim mạch")
    if len(request) > MAX_TOPIC_LENGTH:
        raise invalid(f"Yêu cầu đổi dài quá {MAX_TOPIC_LENGTH} ký tự")
    # The source is only read, never locked for editing: a teammate may keep working on it.
    source = db.get(Video, video_id)
    if source is None:
        raise video_not_found()
    if not source.has_script:
        raise ApiError(409, "no_script", "Video gốc chưa có kịch bản để nhân bản")
    platform = body.platform or source.platform
    if platform not in ("facebook", "tiktok"):
        raise invalid("Nền tảng không có trong danh sách")
    group = knowledge.topic_of(db, source)
    if group is None or not group.clone_prompt:
        raise invalid(f"Nhóm chủ đề “{group.name if group else ''}” chưa có prompt nhân bản")
    draft = Video(
        topic=request,
        knowledge_topic_id=group.id,
        has_script=False,
        created_by_id=me.user_id,
        music_volume=source.music_volume,
        voice_enabled=source.voice_enabled,
        options=video_options.effective(source),
        mode=source.mode,
        clone_source=clone_snapshot(db, source, request),
        platform=platform,
        # A version for another platform keeps a link to the video it was made from.
        variant_of_id=source.id if platform != source.platform else None,
    )
    db.add(draft)
    db.flush()
    if source.music_key and storage.exists(source.music_key):
        # A copy of its own, so deleting or changing the source never takes the draft's music away.
        draft.music_key, draft.music_name = new_key(draft.id, "music", "mp3"), source.music_name
        storage.save_file(draft.music_key, storage.path(source.music_key))
    _enqueue(db, draft, "clone", me)
    return _saved(db, draft)


@router.post("/videos/{video_id}/duplicate", status_code=201)
def duplicate(
    video_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """ "Nhân bản y hệt": an exact copy of a video, named "… (copy)", with no LLM call; it is rendered before posting.
    The source is only read, never locked: a teammate may keep working on it."""
    draft = duplicate_video(db, storage, duplicable(db, video_id), me.user_id)
    return _saved(db, draft)


@router.post("/videos/{video_id}/variants", status_code=201)
def variants(
    video_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """ "Tạo 3 biến thể" of a winner: three draft copies named for what to change (hook, 1-2 dishes, format), with no
    LLM call; the member (or an assistant) edits each, then renders it. Only a video that went live and is a winner at
    48 hours is offered it, but the source is only read."""
    source = duplicable(db, video_id)
    drafts = variant_drafts(db, storage, source, me.user_id)
    db.commit()
    return {"videos": [video_payload(db, draft) for draft in drafts]}


def duplicable(db: DbSession, video_id: int) -> Video:
    """The source of "Nhân bản y hệt": any member's video with a script."""
    source = db.get(Video, video_id)
    if source is None:
        raise video_not_found()
    if source.mode == "upload":
        raise ApiError(409, "upload_video", "Video “MP4 tải lên” không nhân bản được, hãy tải MP4 lên lại")
    if not source.has_script:
        raise ApiError(409, "no_script", "Video gốc chưa có kịch bản để nhân bản")
    media_cleanup.ensure_media(source, "nhân bản")
    return source


# --- Scenes ---


@router.post("/videos/{video_id}/scenes", status_code=201)
def add_scene(video_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    video = lock_video(db, video_id)
    ensure_unlocked(db, video)
    if not video.has_script:
        raise ApiError(409, "no_script", "Video chưa có kịch bản")
    last = db.scalar(select(func.max(Scene.position)).where(Scene.video_id == video.id, Scene.is_title.is_(False)))
    db.add(
        Scene(
            video_id=video.id,
            is_title=False,
            position=(last or 0) + 1,
            text="",
            seconds=NEW_SCENE_SECONDS,
            seconds_auto=True,
            keywords=[],
            keywords_en=[],
            image_prompt="",
        )
    )
    return _saved(db, video)


@router.put("/videos/{video_id}/scene-order")
def reorder_scenes(
    video_id: int, body: SceneOrderBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    video = lock_video(db, video_id)
    ensure_unlocked(db, video)
    _, scenes = split_scenes(db, video)
    by_id = {scene.id: scene for scene in scenes}
    # The last order saved wins; scenes a teammate added meanwhile keep their place at the end.
    ordered = [by_id[scene_id] for scene_id in dict.fromkeys(body.ids) if scene_id in by_id]
    ordered += [scene for scene in scenes if scene not in ordered]
    for position, scene in enumerate(ordered, start=1):
        scene.position = position
    return _saved(db, video)


@router.post("/scenes/{scene_id}/split")
def split_scene(
    scene_id: int,
    body: SplitBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """ "Tách cảnh" in the studio: the scene ends at `at` and a new scene right after it shows the rest of the same
    photo or clip, as its own file, silent and without text. The first part keeps the text and the narration."""
    video, scene = lock_scene(db, scene_id)
    ensure_unlocked(db, video)
    if scene.is_title:
        raise ApiError(409, "title_scene", "Không tách được cảnh tiêu đề")
    latest = round(scene.seconds - MIN_SECONDS, 2)
    if not math.isfinite(body.at) or not MIN_SECONDS <= body.at <= latest:
        raise invalid(f"Chỉ tách được từ giây {MIN_SECONDS:g} đến {max(latest, MIN_SECONDS):g} của cảnh")
    at = round(body.at, 2)
    later = db.scalars(
        select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False), Scene.position > scene.position)
    ).all()
    for other in later:
        other.position += 1
    rest = Scene(
        video_id=video.id,
        is_title=False,
        position=scene.position + 1,
        text="",
        seconds=round(scene.seconds - at, 2),
        seconds_auto=False,
        keywords=list(scene.keywords),
        keywords_en=list(scene.keywords_en),
        image_prompt=scene.image_prompt,
        image_source=scene.image_source,
        image_credit=scene.image_credit,
        # The same picture goes on, so it cuts in rather than showing a transition into itself.
        transition="cut",
        color=scene.color,
        music_level=scene.music_level,
        text_hold_sec=scene.text_hold_sec,
        text_zone=scene.text_zone,
        voice_id=scene.voice_id,
    )
    db.add(rest)
    db.flush()
    if scene.video_key:
        rest.video_key = new_key(video.id, f"clip-{rest.id}", Path(scene.video_key).suffix.lstrip("."))
        storage.save_file(rest.video_key, storage.path(scene.video_key))
        rest.video_seconds, rest.video_speed = scene.video_seconds, scene.video_speed
        rest.video_loop = scene.video_loop
        rest.video_start = round(scene.video_start + at * scene.video_speed, 2)
        # The same file, so its sound and its words (in the clip's own seconds) stay in step from the new start.
        rest.video_sound, rest.words = scene.video_sound, scene.words
    elif scene.image_key:
        rest.image_key = new_key(video.id, f"scene-{rest.id}", Path(scene.image_key).suffix.lstrip("."))
        storage.save_file(rest.image_key, storage.path(scene.image_key))
    # Layers that start after the cut go with the rest, still at the same moment of the video.
    for item in [*scene.layers, *scene.sounds]:
        if item.start >= at:
            item.scene_id, item.start = rest.id, round(item.start - at, 2)
    scene.seconds, scene.seconds_auto = at, False
    return _saved(db, video)


@router.patch("/scenes/{scene_id}")
def patch_scene(
    scene_id: int,
    body: ScenePatchBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    video, scene = lock_scene(db, scene_id)
    ensure_unlocked(db, video)
    fields = body.model_fields_set
    before = edit_log.video_snapshot(video, scene)
    text_changed = False
    if "text" in fields and body.text is not None:
        text = _clean_text(body.text, MAX_TEXT_LENGTH, "Chữ")
        text_changed = text != scene.text
        scene.text = text
    if "seconds" in fields and body.seconds is not None:
        if not math.isfinite(body.seconds) or not 0 <= body.seconds <= 100 * MAX_SECONDS:
            raise invalid("Số giây không hợp lệ")
        scene.seconds = round(body.seconds, 2)
        scene.seconds_auto = False
        if scene.is_title:
            from . import motion as motion_module
            from . import title_motion

            if motion_module.shows_motion(scene):
                title_motion.sync_title_sfx(video, scene)  # a ting past the new end goes
    if body.seconds_auto is not None:
        scene.seconds_auto = body.seconds_auto
    if "keywords" in fields and body.keywords is not None:
        keywords = _clean_list(body.keywords, MAX_KEYWORD_LENGTH, "Từ khóa")
        if len(keywords) > MAX_KEYWORDS:
            raise invalid(f"Tối đa {MAX_KEYWORDS} từ khóa")
        scene.keywords = keywords
    if "keywords_en" in fields and body.keywords_en is not None:
        keywords_en = _clean_list(body.keywords_en, MAX_KEYWORD_LENGTH, "Từ khóa tiếng Anh")
        if len(keywords_en) > MAX_KEYWORDS:
            raise invalid(f"Tối đa {MAX_KEYWORDS} từ khóa")
        scene.keywords_en = keywords_en
    if body.image_checked:
        scene.image_auto = False
    if "image_prompt" in fields and body.image_prompt is not None:
        scene.image_prompt = _clean_text(body.image_prompt, MAX_LONG_TEXT_LENGTH, "Prompt ảnh").strip()
    if "voice_text" in fields and body.voice_text is not None:
        scene.voice_text = _clean_text(body.voice_text, MAX_VOICE_LENGTH, "Lời đọc").strip()
    if "voice_id" in fields:
        try:
            voice = video_options.clean_voice_id(body.voice_id or "")
        except video_options.OptionError as err:
            raise invalid(str(err)) from None
        # Only this scene's narration is made again, on the next voice job or render; the others keep theirs.
        scene.voice_id = voice or None
    start_changed = False
    if "video_start" in fields and body.video_start is not None:
        if not scene.video_key:
            raise invalid("Cảnh này chưa có video")
        # At least the shortest scene's worth of clip is left after the start.
        latest = max(0.0, (scene.video_seconds or 0) - MIN_SECONDS)
        if not math.isfinite(body.video_start) or not 0 <= body.video_start <= latest:
            raise invalid(f"Giây bắt đầu phải từ 0 đến {latest:g}")
        start = round(body.video_start, 2)
        start_changed = start != scene.video_start
        scene.video_start = start
    if "video_speed" in fields and body.video_speed is not None:
        if not scene.video_key:
            raise invalid("Cảnh này chưa có video")
        if not math.isfinite(body.video_speed) or not MIN_VIDEO_SPEED <= body.video_speed <= MAX_VIDEO_SPEED:
            raise invalid("Tốc độ clip phải từ 0,5 đến 2")
        scene.video_speed = round(body.video_speed, 2)
    if "video_sound" in fields and body.video_sound is not None:
        if not scene.video_key:
            raise invalid("Cảnh này chưa có video")
        if body.video_sound and not scene.video_sound and not clips.has_sound(storage.path(scene.video_key)):
            raise invalid("Video của cảnh này không có tiếng")
        if body.video_sound and scene.video_loop:
            raise invalid("Tắt “Lặp clip” trước khi giữ tiếng gốc của video")
        scene.video_sound = body.video_sound
    if "video_loop" in fields and body.video_loop is not None:
        if not scene.video_key:
            raise invalid("Cảnh này chưa có video")
        # A looped clip's own words would no longer line up with its captions.
        if body.video_loop and scene.video_sound:
            raise invalid("Tắt tiếng gốc của video trước khi lặp clip")
        scene.video_loop = body.video_loop
    if "image_fit" in fields:
        if body.image_fit is not None and body.image_fit not in IMAGE_FIT_CHOICES:
            raise invalid(f"Khung ảnh không hợp lệ: {body.image_fit!r}")
        if body.image_fit is not None and not framable(video, scene):
            raise invalid("Chỉ ảnh của cảnh nội dung trong video từng cảnh mới chọn được khung ảnh")
        scene.image_fit = body.image_fit
    if "image_crop_offset" in fields:
        offset = body.image_crop_offset
        if offset is not None:
            if isinstance(offset, bool) or not isinstance(offset, (int, float)) or not 0 <= offset <= 1:
                raise invalid("Vị trí khung vuông phải từ 0 đến 1")
            if not framable(video, scene):
                raise invalid("Chỉ ảnh của cảnh nội dung trong video từng cảnh mới chọn được khung ảnh")
            offset = round(float(offset), 3)
        scene.image_crop_offset = offset
    moved = False
    if "text_position" in fields:
        try:
            position = video_options.clean_position(body.text_position)
        except video_options.OptionError as err:
            raise invalid(str(err)) from None
        # The title moves only up and down (place_box): its x is kept at the centre.
        if position and scene.is_title:
            position[0] = FRAME_WIDTH // 2
        new_x, new_y = position if position else (None, None)
        moved = (new_x, new_y) != (scene.text_x, scene.text_y)
        scene.text_x, scene.text_y = new_x, new_y
    for field, presets, name in (("transition", SCENE_TRANSITIONS, "Chuyển cảnh"), ("color", COLOR_PRESETS, "Màu")):
        if field not in fields:
            continue
        value = getattr(body, field)
        if value is not None and scene.is_title:
            raise invalid(f"Cảnh tiêu đề không có {name.lower()} riêng")
        if value is not None and (not isinstance(value, str) or value not in presets):
            raise invalid(f"{name} không hợp lệ: {value!r}")
        setattr(scene, field, value)
    if "text_zone" in fields:
        if body.text_zone is not None and body.text_zone != "top":
            raise invalid("Vị trí chữ chỉ có “top” (Trên) hoặc để trống (Dưới)")
        scene.text_zone = body.text_zone
    if "text_hold_sec" in fields:
        if body.text_hold_sec is not None and scene.is_title:
            raise invalid("Cảnh tiêu đề luôn giữ chữ suốt cảnh")
        try:
            scene.text_hold_sec = video_options.clean_text_hold(body.text_hold_sec)
        except video_options.OptionError as err:
            raise invalid(str(err)) from None
    if "music_level" in fields:
        level = body.music_level
        if level is not None and (not isinstance(level, str) or level not in MUSIC_LEVELS):
            raise invalid(f"Mức nhạc không hợp lệ: {level!r}")
        scene.music_level = level
    if scene.is_title and text_changed and scene.text.strip() and video.no_title:
        # Typing a title is choosing one: "Không dùng tiêu đề" goes off by itself.
        video.no_title, video.kept_title = False, None
    _follow_voice(video, scene)
    if scene.is_title and (text_changed or start_changed or moved):
        title, _ = split_scenes(db, video)
        refresh_thumbnail(db, storage, video, title)
    _log_video_edit(db, video, me, before, scene)
    return _saved(db, video)


def _follow_voice(video: Video, scene: Scene) -> None:
    """A scene on "Tự khớp lời đọc" whose narration is already made takes its length now; otherwise the voice job
    sets it when it makes the narration."""
    made = made_voice_seconds(video, scene)
    if scene.seconds_auto and made is not None:
        scene.seconds = auto_seconds(made, video_options.voice_pause(video))


@router.delete("/scenes/{scene_id}")
def delete_scene(
    scene_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    video, scene = lock_scene(db, scene_id)
    # A scene goes with its video's maker's rights (the web and MCP alike).
    ensure_owner(video.created_by_id, me.user_id, "video này")
    ensure_unlocked(db, video)
    if scene.is_title:
        raise ApiError(409, "title_scene", "Không xóa được cảnh tiêu đề")
    files = [scene.image_key, scene.voice_key, scene.video_key, scene.image_original_key]
    # Half-frame photos keep a copy of their own, which goes with the scene.
    files += [layer.image_key for layer in scene.layers]
    db.delete(scene)
    payload = _saved(db, video)
    for key in files:
        storage.delete(key)
    return payload


def _store_photo(
    db: DbSession,
    storage: DirectoryStorage,
    scene_id: int,
    data: bytes,
    extension: str,
    source: str | None,
    auto: bool = False,
    credit: dict | None = None,
) -> dict:
    """Store a photo in place of the scene's photo or clip; `source` None keeps the photo's source (a crop of it), and
    its credit. `credit`: what a new photo's licence asks to be credited (Photo.credit)."""
    video, scene = lock_scene(db, scene_id)
    ensure_unlocked(db, video)
    old = [scene.image_key, scene.video_key]
    if source is None:
        if not scene.image_key:
            raise ApiError(409, "no_image", "Cảnh này chưa có ảnh để chỉnh khung")
        source = scene.image_source
    else:
        # A crop is still the edited photo, so "Khôi phục ảnh gốc" stays; another photo forgets the original.
        old.append(drop_original(scene))
        scene.image_credit = {"url": source, **credit} if credit else None
    key = new_key(video.id, f"scene-{scene.id}", extension)
    storage.save_bytes(key, data)
    scene.image_key, scene.image_source, scene.image_error = key, source, None
    # A member chose, uploaded or cropped this photo: it is no longer the app's unchecked pick. A photo the extension
    # picked from Google is one, until a member looks at it.
    scene.image_auto = auto
    # A photo replaces the scene's clip: a scene shows one or the other.
    scene.video_key, scene.video_seconds, scene.video_start, scene.video_speed = None, None, 0, 1
    scene.video_loop = False
    # A new or removed clip has no sound of its own heard, nor words ("Edit từ footage").
    scene.video_sound, scene.words = False, None
    if scene.is_title:
        title, _ = split_scenes(db, video)
        refresh_thumbnail(db, storage, video, title)
    payload = _saved(db, video)
    for key in old:
        storage.delete(key)
    return payload


@router.post("/scenes/{scene_id}/image")
def upload_scene_image(
    scene_id: int,
    file: UploadFile = File(...),
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    data = read_limited(file, MAX_IMAGE_BYTES, "Ảnh quá 15 MB, hãy chọn ảnh nhỏ hơn")
    try:
        extension = image_extension(data)
    except UploadRejected as err:
        raise ApiError(415, "invalid_image", str(err)) from None
    return _store_photo(db, storage, scene_id, data, extension, "upload")


class MediaLinkBody(BaseModel):
    url: str
    # "Lấy ảnh Google cho cảnh thiếu ảnh" (the team's Chrome extension): the app's own pick, not the member's. A
    # stock photo site is refused so the page tries the next result, and the photo is marked "Tự chọn, kiểm tra lại".
    auto: bool = False


class ReuseBody(BaseModel):
    scene_id: int


MAX_GROUP_MEDIA = 60


def _folded(text: str) -> str:
    """Lower case without accents, so "cai be" finds "Cải bẹ"."""
    plain = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(char for char in plain if not unicodedata.combining(char)).lower()


def _words(texts: list[str]) -> set[str]:
    # \w+ drops the *stars* around highlighted words and other punctuation.
    return {word for text in texts for word in re.findall(r"\w+", _folded(text)) if len(word) > 1}


@router.get("/scenes/{scene_id}/group-media")
def group_media(
    scene_id: int, q: str = "", me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Đã dùng trong nhóm": the photos and clips of the other videos in this scene's topic group, best match first:
    by the words typed, else by the words this scene's keywords share with theirs. Read only; "Dùng" copies one."""
    scene = db.get(Scene, scene_id)
    if scene is None:
        raise ApiError(404, "scene_not_found", "Không tìm thấy cảnh")
    video = db.get(Video, scene.video_id)
    rows = db.execute(
        select(Scene, Video)
        .join(Video, Scene.video_id == Video.id)
        .where(
            Video.knowledge_topic_id == video.knowledge_topic_id,
            Video.id != video.id,
            Video.media_cleaned_at.is_(None),
            or_(Scene.image_key.is_not(None), Scene.video_key.is_not(None)),
        )
        .order_by(Scene.id.desc())
    ).all()
    titles = dict(
        db.execute(
            select(Scene.video_id, Scene.text).where(
                Scene.is_title, Scene.video_id.in_({other.id for _, other in rows})
            )
        ).all()
    )
    typed = _words([q])
    wanted = typed or _words([*scene.keywords, *scene.keywords_en])
    found = []
    for other_scene, other in rows:
        words = _words([*other_scene.keywords, *other_scene.keywords_en, other_scene.text])
        score = len(wanted & words)
        if typed and score < len(typed):
            continue  # every typed word must be there
        found.append((score, other_scene, other))
    found.sort(key=lambda row: -row[0])  # stable: the newest first among equals
    items = []
    for _, other_scene, other in found[:MAX_GROUP_MEDIA]:
        base = f"/api/scenes/{other_scene.id}"
        items.append(
            {
                "scene_id": other_scene.id,
                "video_id": other.id,
                "video_title": plain_title(titles.get(other.id, "")) or other.topic,
                "text": other_scene.text,
                "keywords": other_scene.keywords,
                "kind": "clip" if other_scene.video_key else "photo",
                "url": f"{base}/video" if other_scene.video_key else f"{base}/image",
            }
        )
    return {"items": items, "total": len(rows)}


@router.post("/scenes/{scene_id}/reuse")
def reuse_media(
    scene_id: int,
    body: ReuseBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """ "Dùng" on "Đã dùng trong nhóm": a copy of another video's photo or clip in this group, stored as this scene's
    own file (deleting either video leaves the other's intact). A photo keeps its source, for a copyright claim."""
    scene = db.get(Scene, scene_id)
    source = db.get(Scene, body.scene_id)
    if scene is None or source is None:
        raise ApiError(404, "scene_not_found", "Không tìm thấy cảnh")
    video, other = db.get(Video, scene.video_id), db.get(Video, source.video_id)
    if other.knowledge_topic_id != video.knowledge_topic_id:
        raise invalid("Chỉ dùng lại được ảnh/video của video cùng nhóm chủ đề")
    image_key, image_source, clip_key = source.image_key, source.image_source, source.video_key
    db.rollback()
    if clip_key:
        with tempfile.TemporaryDirectory(prefix="reels_reuse_") as folder:
            copy = storage.copy_to(clip_key, Path(folder) / f"clip{Path(clip_key).suffix}")
            return _attach_clip(db, storage, scene_id, copy)
    if not image_key:
        raise invalid("Cảnh đó không còn ảnh hay video để dùng lại")
    data = storage.path(image_key).read_bytes()
    return _store_photo(db, storage, scene_id, data, Path(image_key).suffix.lstrip("."), image_source or "upload")


@router.post("/scenes/{scene_id}/media-from-url")
def media_from_url(
    scene_id: int,
    body: MediaLinkBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """A photo or clip pasted as a link or dragged from another tab (Google Ảnh, a shop, a video file, a TikTok
    video): downloaded here and stored like an upload. A photo keeps its link as the source so a copyright claim can
    be traced back; a clip longer than a minute keeps its first minute. With `auto` (a pick of the Chrome extension
    from Google Ảnh) a stock photo site is refused with `stock_photo`, so the page tries the next result."""
    if body.auto and (site := stock_site(body.url)):
        raise ApiError(422, "stock_photo", f"Ảnh của {site} có watermark và cần bản quyền, không tự chọn")
    video, _ = lock_scene(db, scene_id)
    ensure_unlocked(db, video)
    # No row lock may be held while the other site answers; the saves lock and re-check everything.
    db.rollback()
    with tempfile.TemporaryDirectory(prefix="reels_link_") as folder:
        try:
            media = remote_media.download(body.url, Path(folder))
        except remote_media.RemoteMediaError as err:
            raise invalid(str(err)) from None
        if media.photo is not None:
            data, extension = media.photo
            payload = _store_photo(db, storage, scene_id, data, extension, body.url.strip(), auto=body.auto)
            if site := stock_site(body.url):
                payload["notice"] = (
                    f"Ảnh này lấy từ {site}: ảnh xem trước thường có watermark và cần mua bản quyền. "
                    "Nếu nhóm chưa mua, hãy đổi ảnh khác (Tìm ảnh, Tạo ảnh AI)."
                )
            return payload
        assert media.clip is not None
        if body.auto:
            raise ApiError(422, "not_a_photo", "Link này là video, không phải ảnh")
        try:
            clip = clips.first_part(media.clip, Path(folder))
        except UploadRejected as err:
            raise ApiError(415, "invalid_video", str(err)) from None
        return _attach_clip(db, storage, scene_id, clip)


@router.post("/scenes/{scene_id}/image/crop")
def crop_scene_image(
    scene_id: int,
    file: UploadFile = File(...),
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """The scene's photo as cropped, turned or flipped in the browser. It keeps the photo's source, so an AI photo
    stays labelled as AI and a stock photo keeps its credit."""
    data = read_limited(file, MAX_IMAGE_BYTES, "Ảnh quá 15 MB, hãy chọn ảnh nhỏ hơn")
    try:
        extension = image_extension(data)
    except UploadRejected as err:
        raise ApiError(415, "invalid_image", str(err)) from None
    return _store_photo(db, storage, scene_id, data, extension, None)


def _spool_clip(upload: UploadFile, target: Path) -> None:
    """Copy the upload to a file of its own, refusing it once it passes the limit: clips are too big for memory."""
    with open(target, "wb") as file:
        copied = 0
        while chunk := upload.file.read(1024 * 1024):
            copied += len(chunk)
            if copied > clips.MAX_CLIP_BYTES:
                raise ApiError(413, "file_too_large", "Video quá 50 MB, hãy chọn video ngắn hơn hoặc nén nhỏ lại")
            file.write(chunk)


@router.post("/scenes/{scene_id}/video")
def upload_scene_video(
    scene_id: int,
    file: UploadFile = File(...),
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    with tempfile.TemporaryDirectory(prefix="reels_clip_") as folder:
        upload = Path(folder) / "clip"
        _spool_clip(file, upload)
        return _attach_clip(db, storage, scene_id, upload)


def _attach_clip(db: DbSession, storage: DirectoryStorage, scene_id: int, upload: Path) -> dict:
    """A clip file in place of the scene's photo or clip, whether uploaded or downloaded from a stock source."""
    # ffprobe runs before any row is locked; the save below locks and re-checks everything.
    try:
        clip = clips.check_clip(upload)
    except UploadRejected as err:
        raise ApiError(415, "invalid_video", str(err)) from None
    video, scene = lock_scene(db, scene_id)
    ensure_unlocked(db, video)
    old = [scene.image_key, scene.video_key, drop_original(scene)]
    key = new_key(video.id, f"clip-{scene.id}", clip.extension)
    storage.save_file(key, upload)
    scene.video_key, scene.video_seconds, scene.video_start, scene.video_speed = key, round(clip.seconds, 3), 0, 1
    scene.video_loop = False
    # A new or removed clip has no sound of its own heard, nor words ("Edit từ footage").
    scene.video_sound, scene.words = False, None
    # A clip replaces the scene's photo, and the scene lasts as long as the clip minus the crossfades around it
    # (one for the title, at most two for a content scene), in tenths, so the clip never ends on a held frame.
    scene.image_key, scene.image_source, scene.image_error = None, None, None
    scene.image_auto = False
    playable = clip.seconds - (1 if scene.is_title else 2) * CROSSFADE_SIDE_SECONDS
    scene.seconds = max(MIN_SECONDS, min(MAX_CLIP_SCENE_SECONDS, math.floor(round(playable * 10, 6)) / 10))
    _follow_voice(video, scene)
    if scene.is_title:
        title, _ = split_scenes(db, video)
        refresh_thumbnail(db, storage, video, title)
    payload = _saved(db, video)
    for old_key in old:
        storage.delete(old_key)
    return payload


@router.delete("/scenes/{scene_id}/video")
def remove_scene_video(
    scene_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    video, scene = lock_scene(db, scene_id)
    ensure_unlocked(db, video)
    old, scene.video_key, scene.video_seconds, scene.video_start = scene.video_key, None, None, 0
    scene.video_speed = 1
    scene.video_loop = False
    scene.video_sound, scene.words = False, None
    if scene.is_title:
        title, _ = split_scenes(db, video)
        refresh_thumbnail(db, storage, video, title)
    payload = _saved(db, video)
    storage.delete(old)
    return payload


def stock_orientation(value: str) -> str:
    if value not in ORIENTATIONS:
        raise invalid("Hướng ảnh không hợp lệ")
    return value


def _used_photos(db: DbSession, video_id: int, except_scene: int | None = None) -> set[str]:
    """The source addresses of the photos the video's scenes already use (all of them, or all but one scene's)."""
    query = select(Scene.image_source).where(Scene.video_id == video_id, Scene.image_source.is_not(None))
    if except_scene is not None:
        query = query.where(Scene.id != except_scene)
    return set(db.scalars(query))


@router.post("/scenes/{scene_id}/find-image")
def find_other_image(
    scene_id: int,
    source: str | None = None,
    orientation: str = "vertical",
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    orientation = stock_orientation(orientation)
    video, scene = lock_scene(db, scene_id)
    ensure_unlocked(db, video)
    # No source named: the first usable one of the video's topic group's order.
    source = source or first_stock_source(db, video)
    client, error_type = stock_client(source, db)
    if source in stock_turned_off(db):
        raise invalid("Nguồn này đang tắt trong Cài đặt › AI và nguồn tư liệu")
    # Each source is searched in the language it indexes: Wikimedia and Openverse in Vietnamese, the others in
    # English; the other list is the fallback (scenes scripted before English keywords existed).
    keywords = stock_keywords(source, list(scene.keywords), list(scene.keywords_en))
    current = scene.image_source
    # A photo another scene of this video shows is never picked again.
    used = _used_photos(db, video.id, except_scene=scene.id)
    if not keywords:
        raise invalid("Hãy nhập từ khóa tìm ảnh trước")
    # No row lock may be held while the source answers; the save below locks and re-checks everything.
    db.rollback()
    try:
        photo = client.find_photo(
            keywords, time.monotonic() + FIND_IMAGE_SECONDS, avoid=used, after=current, orientation=orientation
        )
    except error_type as err:
        code = "pixabay_error" if source == "pixabay" else "stock_error"
        raise ApiError(502, code, f"Không tìm được ảnh: {err.message}") from None
    if photo is None:
        raise ApiError(404, "no_other_image", "Không tìm thấy ảnh khác, hãy đổi từ khóa")
    return _store_photo(db, storage, scene_id, photo.data, photo.extension, photo.url, credit=photo.credit)


def _pixabay_failed(err: PixabayError) -> ApiError:
    return ApiError(502, "pixabay_error", f"Không tìm được ảnh: {err.message}")


@router.get("/scenes/{scene_id}/pixabay")
def search_pixabay(
    scene_id: int, q: str = "", me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """Results for the "Chọn từ Pixabay" grid; thumbnails are shown from Pixabay and never stored."""
    if db.get(Scene, scene_id) is None:
        raise ApiError(404, "scene_deleted", "Cảnh này đã bị xóa")
    keyword = " ".join(q.split())
    if not keyword:
        raise invalid("Hãy nhập từ khóa tìm ảnh")
    if len(keyword) > MAX_KEYWORD_LENGTH:
        raise invalid(f"Từ khóa dài quá {MAX_KEYWORD_LENGTH} ký tự")
    db.rollback()
    try:
        hits = Pixabay(source_keys.get(db, "pixabay")).search_hits(keyword, time.monotonic() + FIND_IMAGE_SECONDS)
    except PixabayError as err:
        raise _pixabay_failed(err) from None
    return {"keyword": keyword, "hits": [{"url": hit.url, "preview": hit.preview} for hit in hits]}


class PixabayChoiceBody(BaseModel):
    keyword: str
    url: str


@router.post("/scenes/{scene_id}/pixabay")
def choose_pixabay(
    scene_id: int,
    body: PixabayChoiceBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """Download the chosen photo into storage; it must be one of Pixabay's results for that keyword."""
    video, _ = lock_scene(db, scene_id)
    ensure_unlocked(db, video)
    db.rollback()
    client = Pixabay(source_keys.get(db, "pixabay"))
    deadline = time.monotonic() + FIND_IMAGE_SECONDS
    try:
        # The address comes from the browser: only a result Pixabay itself returned may be fetched.
        if body.url not in client.search(" ".join(body.keyword.split()), deadline):
            raise invalid("Ảnh này không có trong kết quả Pixabay, hãy tìm lại")
        photo = client.download(body.url, deadline)
    except PixabayError as err:
        raise _pixabay_failed(err) from None
    if photo is None:
        raise ApiError(422, "unusable_image", "Ảnh này không tải được, hãy chọn ảnh khác")
    return _store_photo(db, storage, scene_id, photo.data, photo.extension, photo.url)


# --- Stock sources for the picker ---

# The app's order, Pexels first: the picker opens on the first source offered, "Tìm ảnh" asks it and "Tự tìm ảnh"
# goes down the list. A topic group may set its own ("Thứ tự nguồn ảnh", KnowledgeTopic.stock_order).
STOCK_SOURCES = ("pexels", "unsplash", "pixabay", "wikimedia", "openverse")
STOCK_LABELS = {
    "pixabay": "Pixabay",
    "pexels": "Pexels",
    "unsplash": "Unsplash",
    "wikimedia": "Wikimedia Commons",
    "openverse": "Openverse",
}
# Sources that index Vietnamese titles: searched with the scene's Vietnamese keywords first, English as the fallback.
VIETNAMESE_FIRST = {"openverse", "wikimedia"}
# Sources that need a key (source_keys); the others answer anonymous calls.
KEYED_SOURCES = {"pixabay", "pexels", "unsplash"}
STOCK_OFF_KEY = "stock_sources_off"
CLIP_DOWNLOAD_SECONDS = 60


def stock_client(source: str, db: DbSession):
    """The picker client for a source and its error type; an unknown source is a bad request."""
    if source == "pixabay":
        return Pixabay(source_keys.get(db, "pixabay")), PixabayError
    if source == "pexels":
        return Pexels(source_keys.get(db, "pexels")), PexelsError
    if source == "unsplash":
        return Unsplash(source_keys.get(db, "unsplash")), UnsplashError
    if source == "wikimedia":
        return Wikimedia(), WikimediaError
    if source == "openverse":
        return Openverse(), OpenverseError
    raise invalid("Nguồn ảnh không hợp lệ")


def stock_keywords(source: str, vietnamese: list[str], english: list[str]) -> list[str]:
    """The keywords a source is searched with: the language it indexes, the other list as the fallback."""
    return (vietnamese or english) if source in VIETNAMESE_FIRST else (english or vietnamese)


def stock_configured(source: str, db: DbSession) -> bool:
    if source in KEYED_SOURCES:
        return bool(source_keys.get(db, source))
    return True  # Wikimedia and Openverse answer anonymous calls.


def clean_stock_order(order: list[str] | None) -> list[str]:
    """A group's order made whole: its known sources first, the others after them in the app's order."""
    first = [source for source in dict.fromkeys(order or []) if source in STOCK_SOURCES]
    return first + [source for source in STOCK_SOURCES if source not in first]


def stock_order(db: DbSession, video: Video | None) -> list[str]:
    """The order a video's photos are looked for in: its topic group's, else the app's."""
    topic = db.get(KnowledgeTopic, video.knowledge_topic_id) if video and video.knowledge_topic_id else None
    return clean_stock_order(topic.stock_order if topic else None)


def first_stock_source(db: DbSession, video: Video | None) -> str:
    """Where "Tìm ảnh" and the assistant's search go when no source is named: the first one usable, in order."""
    order = stock_order(db, video)
    return next((source for source in order if stock_available(source, db)), order[0])


def stock_turned_off(db: DbSession) -> set[str]:
    """The sources the team turned off on Cài đặt › AI và nguồn tư liệu."""
    setting = db.get(AppSetting, STOCK_OFF_KEY)
    return (
        {item for item in setting.value if item in STOCK_SOURCES}
        if setting and isinstance(setting.value, list)
        else set()
    )


def stock_available(source: str, db: DbSession) -> bool:
    return stock_configured(source, db) and source not in stock_turned_off(db)


@router.get("/stock/sources")
def stock_sources(
    video_id: int | None = None, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> list[dict]:
    """The picker's sources, in the video's topic group's order (the app's without a video); `clips` says which also
    offer video clips, `missing_key` which cannot be used until a key is pasted on Cài đặt › AI và nguồn tư liệu."""
    video = db.get(Video, video_id) if video_id is not None else None
    return [
        {
            "id": source,
            "label": STOCK_LABELS[source],
            "available": stock_available(source, db),
            "missing_key": not stock_configured(source, db),
            "clips": source in stock_clips.SOURCES and stock_available(source, db),
        }
        for source in stock_order(db, video)
    ]


@router.get("/scenes/{scene_id}/stock-clips")
def search_stock_clips(
    scene_id: int,
    q: str = "",
    source: str = "pexels",
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
) -> dict:
    """Video clips for the picker's "Video" mode: a still and the length of each, shown straight from the source."""
    if db.get(Scene, scene_id) is None:
        raise ApiError(404, "scene_deleted", "Cảnh này đã bị xóa")
    keyword = " ".join(q.split())
    if not keyword:
        raise invalid("Hãy nhập từ khóa tìm video")
    if len(keyword) > MAX_KEYWORD_LENGTH:
        raise invalid(f"Từ khóa dài quá {MAX_KEYWORD_LENGTH} ký tự")
    if source in stock_turned_off(db):
        raise invalid("Nguồn này đang tắt trong Cài đặt › AI và nguồn tư liệu")
    db.rollback()
    try:
        hits = stock_clips.search(source, keyword, FIND_IMAGE_SECONDS, source_keys.get(db, source))
    except stock_clips.ClipSearchError as err:
        raise ApiError(502, "stock_error", f"Không tìm được video: {err.message}") from None
    return {
        "keyword": keyword,
        "source": source,
        "hits": [{"id": hit.id, "preview": hit.preview, "url": hit.url, "seconds": hit.seconds} for hit in hits],
    }


class StockClipBody(BaseModel):
    source: str
    keyword: str
    id: str


@router.post("/scenes/{scene_id}/stock-clips")
def choose_stock_clip(
    scene_id: int,
    body: StockClipBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """Download the chosen clip and store it with the scene like an upload; it must be in the source's results."""
    video, _ = lock_scene(db, scene_id)
    ensure_unlocked(db, video)
    if body.source in stock_turned_off(db):
        raise invalid("Nguồn này đang tắt trong Cài đặt › AI và nguồn tư liệu")
    db.rollback()
    try:
        hit = next(
            (
                hit
                for hit in stock_clips.search(
                    body.source,
                    " ".join(body.keyword.split()),
                    FIND_IMAGE_SECONDS,
                    source_keys.get(db, body.source),
                )
                if hit.id == body.id
            ),
            None,
        )
        if hit is None:
            raise invalid("Video này không có trong kết quả tìm, hãy tìm lại")
        data = stock_clips.download(hit, CLIP_DOWNLOAD_SECONDS)
    except stock_clips.ClipSearchError as err:
        raise ApiError(502, "stock_error", err.message) from None
    with tempfile.TemporaryDirectory(prefix="reels_clip_") as folder:
        path = Path(folder) / "clip"
        path.write_bytes(data)
        return _attach_clip(db, storage, scene_id, path)


@router.get("/scenes/{scene_id}/stock")
def search_stock(
    scene_id: int,
    q: str = "",
    source: str | None = None,
    orientation: str = "vertical",
    hide_used: bool = True,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
) -> dict:
    """Results for the picker's source switch; the same contract as the Pixabay-only search. The picker's filters:
    `orientation` (vertical, square, all) and `hide_used` (leave out photos the video's scenes already show);
    photos too small for the frame are always left out."""
    scene = db.get(Scene, scene_id)
    if scene is None:
        raise ApiError(404, "scene_deleted", "Cảnh này đã bị xóa")
    orientation = stock_orientation(orientation)
    # No source named: the first usable one of the video's topic group's order.
    source = source or first_stock_source(db, db.get(Video, scene.video_id))
    used = _used_photos(db, scene.video_id) if hide_used else set()
    keyword = " ".join(q.split())
    if not keyword:
        raise invalid("Hãy nhập từ khóa tìm ảnh")
    if len(keyword) > MAX_KEYWORD_LENGTH:
        raise invalid(f"Từ khóa dài quá {MAX_KEYWORD_LENGTH} ký tự")
    if source in stock_turned_off(db):
        raise invalid("Nguồn này đang tắt trong Cài đặt › AI và nguồn tư liệu")
    client, error_type = stock_client(source, db)
    db.rollback()
    try:
        hits = client.search_hits(keyword, time.monotonic() + FIND_IMAGE_SECONDS, orientation)
    except error_type as err:
        raise ApiError(502, "stock_error", f"Không tìm được ảnh: {err.message}") from None
    return {
        "keyword": keyword,
        "source": source,
        # `credit`: the line a photo whose licence asks for credit must carry once posted (Wikimedia CC BY...).
        "hits": [
            {"url": hit.url, "preview": hit.preview, "credit": hit.credit["line"] if hit.credit else None}
            for hit in hits
            if hit.url not in used
        ],
    }


class StockChoiceBody(BaseModel):
    source: str
    keyword: str
    url: str
    # The orientation the grid was searched with, so the photo is looked for among the same results.
    orientation: str = "vertical"


@router.post("/scenes/{scene_id}/stock")
def choose_stock(
    scene_id: int,
    body: StockChoiceBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """Download the chosen photo from its source; it must be one of that source's results for the keyword."""
    video, _ = lock_scene(db, scene_id)
    ensure_unlocked(db, video)
    if body.source in stock_turned_off(db):
        raise invalid("Nguồn này đang tắt trong Cài đặt › AI và nguồn tư liệu")
    client, error_type = stock_client(body.source, db)
    db.rollback()
    deadline = time.monotonic() + FIND_IMAGE_SECONDS
    try:
        # The address comes from the browser: only a result the source itself returned may be fetched.
        if body.url not in client.search(" ".join(body.keyword.split()), deadline, stock_orientation(body.orientation)):
            raise invalid("Ảnh này không có trong kết quả tìm, hãy tìm lại")
        photo = client.download(body.url, deadline)
    except error_type as err:
        raise ApiError(502, "stock_error", f"Không tìm được ảnh: {err.message}") from None
    if photo is None:
        raise ApiError(422, "unusable_image", "Ảnh này không tải được, hãy chọn ảnh khác")
    return _store_photo(db, storage, scene_id, photo.data, photo.extension, photo.url, credit=photo.credit)


# --- Jobs ---

JOB_LIST_LIMIT = 300


@router.get("/jobs")
def list_jobs(
    before: int | None = None,
    whose: Literal["all", "mine"] = "all",
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
) -> list[dict]:
    """The job log: newest first, including cancelled jobs and every retry. One page per call; `before`
    (the oldest job id shown) gives the next, older page. `whose=mine` keeps the jobs the member started."""
    query = select(Job).order_by(Job.id.desc()).limit(JOB_LIST_LIMIT)
    if before is not None:
        query = query.where(Job.id < before)
    if whose == "mine":
        query = query.where(Job.created_by_id == me.user_id)
    jobs = db.scalars(query).all()
    titles = {}
    thumbnails: dict[int | None, str | None] = {}
    rows = []
    for job in jobs:
        # A plan job has no video: it is named after its topic group; an article's job after the article.
        owner = job.video_id or (
            f"article-{job.article_id}"
            if job.article_id
            else f"slot-{job.plan_slot_id}"
            if job.plan_slot_id
            else f"topic-{job.knowledge_topic_id}-{job.kind}"
        )
        if owner not in titles:
            if job.plan_slot_id is not None:
                slot = db.get(ArticlePlanSlot, job.plan_slot_id)
                titles[owner] = f"Bình luận ghim · {slot.hook}" if slot else "Bình luận ghim"
            elif job.article_id is not None:
                article = db.get(Article, job.article_id)
                titles[owner] = f"Bài viết · {article.topic or articles.KIND_LABELS[article.kind]}"
            elif job.video_id is None:
                group = db.get(KnowledgeTopic, job.knowledge_topic_id)
                what = "Chữ & phụ đề" if job.kind == text_looks.JOB_KIND else "Kế hoạch 30 ngày"
                titles[owner] = f"{what} · {group.name}"
            else:
                video = db.get(Video, job.video_id)
                title, _ = split_scenes(db, video)
                titles[owner] = video_name(video, title)
                thumbnails[job.video_id] = thumbnail_url(video)
        ended = job.finished_at
        rows.append(
            {
                "id": job.id,
                "video_id": job.video_id,
                "knowledge_topic_id": job.knowledge_topic_id,
                "article_id": job.article_id,
                "video_title": titles[owner],
                "kind": job.kind,
                "kind_label": JOB_KINDS.get(job.kind, job.kind) + (" (1 cảnh)" if job.scene_id is not None else ""),
                "can_cancel": job.status == "queued" or (job.status == "running" and job.node_stage == "ready"),
                "status": job.status,
                "created_by": job.created_by.name,
                "created_by_id": job.created_by_id,
                "created_at": job.created_at.isoformat(),
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "duration_seconds": round((ended - job.started_at).total_seconds(), 1)
                if job.started_at and ended
                else None,
                "claude_calls": job.claude_calls,
                "image_calls": job.image_calls,
                "llm": llm.label(job.llm_provider, job.llm_model)
                or (image_edit.LABELS if job.kind == "image_edit" else image_providers.LABELS).get(
                    job.image_provider or "", job.image_provider
                ),
                "error": job.error,
                "error_detail": job.error_detail,
                "retry_of_id": job.retry_of_id,
                "waited_seconds": round((job.started_at - job.created_at).total_seconds(), 1)
                if job.started_at
                else None,
                "thumbnail_url": thumbnails.get(job.video_id),
            }
        )
    return rows


def _lock_job(db: DbSession, job_id: int) -> Job:
    job = db.scalar(select(Job).where(Job.id == job_id).with_for_update().execution_options(populate_existing=True))
    if job is None:
        raise ApiError(404, "job_not_found", "Không tìm thấy job")
    return job


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    # Waits for the worker while it is claiming this very job (its row lock), then sees the real status.
    job = _lock_job(db, job_id)
    # A job waiting for a render machine (render_nodes.py) has done only its light steps: it may be cancelled too.
    waiting = job.status == "running" and job.node_stage == "ready"
    if job.status != "queued" and not waiting:
        raise ApiError(409, "job_not_queued", "Job đã bắt đầu chạy hoặc đã xong, không hủy được")
    job.status, job.finished_at, job.node_stage = "cancelled", now(), None
    db.commit()
    if waiting:
        from . import motion, render_nodes

        if job.kind == "motion":
            motion.fail_pending(db, job)
        render_nodes.clean(get_storage(), job.id)
    if job.plan_slot_id is not None:
        return {"id": job.id, "status": job.status}
    if job.article_id is not None:
        return article_posts.payload(db, db.get(Article, job.article_id))
    if job.video_id is None and job.kind == text_looks.JOB_KIND:
        return _knowledge_payload(db, me.user_id)
    if job.video_id is None:
        return plans.plan_payload(db, db.get(KnowledgeTopic, job.knowledge_topic_id))
    return video_payload(db, db.get(Video, job.video_id))


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    owner = db.execute(
        select(Job.video_id, Job.knowledge_topic_id, Job.article_id, Job.plan_slot_id).where(Job.id == job_id)
    ).first()
    if owner is None:
        raise ApiError(404, "job_not_found", "Không tìm thấy job")
    video_id, topic_id, article_id, slot_id = owner
    if slot_id is not None:
        return _retry_slot_comments(db, job_id, slot_id, me)
    if article_id is not None:
        return _retry_article(db, job_id, article_id, me)
    if video_id is None:
        return _retry_plan(db, job_id, topic_id, me)
    video = lock_video(db, video_id)
    job = db.get(Job, job_id)
    if job.status != "failed":
        raise ApiError(409, "job_not_failed", "Chỉ thử lại được job bị lỗi")
    ensure_unlocked(db, video)
    if job.kind == "render":
        _ensure_renderable(db, video)
    _enqueue(
        db,
        video,
        job.kind,
        me,
        retry_of=job,
        scene_id=job.scene_id,
        image_provider=job.image_provider,
        publication_id=job.publication_id,
        edit_boxes=job.edit_boxes,
        edit_prompt=job.edit_prompt,
    )
    return _saved(db, video)


def _retry_slot_comments(db: DbSession, job_id: int, slot_id: int, me: Session) -> dict:
    job = db.get(Job, job_id)
    if job.status != "failed":
        raise ApiError(409, "job_not_failed", "Chỉ thử lại được job bị lỗi")
    slot = db.get(ArticlePlanSlot, slot_id)
    params = job.params or {}
    if not slot_comments.queue(
        db, [slot], me.user_id, overwrite=bool(params.get("overwrite")), index=params.get("index")
    ):
        raise ApiError(409, "slot_comments_busy", "Kịch bản đang có bình luận chờ hoặc đang tạo")
    db.commit()
    return {"id": job.id, "status": job.status}


def _retry_plan(db: DbSession, job_id: int, topic_id: int, me: Session) -> dict:
    job = db.get(Job, job_id)
    if job.status != "failed":
        raise ApiError(409, "job_not_failed", "Chỉ thử lại được job bị lỗi")
    if job.kind == text_looks.JOB_KIND:
        if not text_looks.enqueue(db, topic_id, me.user_id, retry_of_id=job_id):
            raise ApiError(409, "text_look_busy", "Nhóm đang có gợi ý kiểu chữ chờ hoặc đang tạo")
        db.commit()
        return _knowledge_payload(db, me.user_id)
    if not plans.enqueue(db, topic_id, me.user_id, retry_of_id=job_id):
        raise ApiError(409, "plan_busy", "Nhóm chủ đề đang có kế hoạch chờ hoặc đang tạo")
    db.commit()
    return plans.plan_payload(db, db.get(KnowledgeTopic, topic_id))


def _retry_article(db: DbSession, job_id: int, article_id: int, me: Session) -> dict:
    article = db.get(Article, article_id, with_for_update=True)
    job = db.get(Job, job_id)
    if job.status != "failed":
        raise ApiError(409, "job_not_failed", "Chỉ thử lại được job bị lỗi")
    if job.kind == "article_caption":
        queued = articles.enqueue_caption(db, article, me.user_id, retry_of_id=job_id)
    elif job.kind == "article_image":
        provider = job.image_provider or image_providers.default(db)
        queued = articles.enqueue_image(db, article, me.user_id, provider, retry_of_id=job_id)
    else:
        queued = article_posts.enqueue(
            db, article, job.kind, me.user_id, publication_id=job.publication_id, retry_of_id=job_id
        )
        if queued and job.kind == "publish" and (post := article_posts.pending_post(db, article_id)) is not None:
            article_posts.reset_retries(post)
    if not queued:
        raise ApiError(409, "article_busy", "Bài viết đang có việc chờ hoặc đang chạy")
    db.commit()
    return article_posts.payload(db, db.get(Article, article_id))


# --- Files (all behind login) ---


def _file(storage: DirectoryStorage, key: str | None, media_type: str, filename: str | None = None) -> FileResponse:
    if not key or not storage.exists(key):
        raise ApiError(404, "file_not_found", "Không tìm thấy file")
    return FileResponse(
        storage.path(key),
        media_type=media_type,
        filename=filename,
        content_disposition_type="attachment",
        headers={"Cache-Control": "private, max-age=3600"},
    )


def _inline(storage: DirectoryStorage, key: str | None, media_type: str) -> FileResponse:
    if not key or not storage.exists(key):
        raise ApiError(404, "file_not_found", "Không tìm thấy file")
    return FileResponse(storage.path(key), media_type=media_type, headers={"Cache-Control": "private, max-age=3600"})


def _scene(db: DbSession, scene_id: int) -> Scene:
    scene = db.get(Scene, scene_id)
    if scene is None:
        raise ApiError(404, "scene_deleted", "Cảnh này đã bị xóa")
    return scene


@router.get("/scenes/{scene_id}/image")
def scene_image(
    scene_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> FileResponse:
    scene = _scene(db, scene_id)
    extension = (scene.image_key or "").rsplit(".", 1)[-1]
    return _inline(storage, scene.image_key, IMAGE_TYPES.get(extension, "application/octet-stream"))


@router.get("/scenes/{scene_id}/preview.jpg")
def scene_preview(
    scene_id: int,
    live: bool = False,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> Response:
    scene = _scene(db, scene_id)
    still = scene_still(storage, scene)
    if still is None:
        raise ApiError(404, "file_not_found", "Cảnh chưa có ảnh hoặc không lấy được khung hình từ video")
    video = db.get(Video, scene.video_id)
    frame = frames.compose_frame(
        still,
        scene.text,
        scene.is_title,
        video_options.render_options(video),
        text_position(video, scene),
        under=_card_under(storage, scene),
        **_framed(db, storage, video, scene),
        **_pc_text(db, video, scene),
        live=live,
    )
    return Response(
        frames.jpeg_bytes(frame), media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"}
    )


def _card_under(storage: DirectoryStorage, scene: Scene) -> list:
    """The scene's card ("Thẻ") whole, where the render lays it under the text; nothing without one."""
    card = next((layer for layer in scene.layers if is_card_layer(layer) and layer.image_key), None)
    if card is None or not storage.exists(card.image_key):
        return []
    try:
        picture = render_card(storage.path(card.image_key), card.height)
    except ValueError:
        return []
    return [(picture, card_corner(picture.width, picture.height, card.y))]


def _is_last(db: DbSession, video: Video, scene: Scene) -> bool:
    """The scene is the video's last content scene (the call to action, which keeps its text box)."""
    scenes = split_scenes(db, video)[1]
    return bool(scenes) and scenes[-1].id == scene.id


def _pc_text(db: DbSession, video: Video, scene: Scene) -> dict:
    """What PC Shopee's tiers and "Cộng dồn" captions need to draw a scene's preview: whether it is the last scene, its
    zone and its narration."""
    return {"last": _is_last(db, video, scene), "zone": scene.text_zone, "narration": spoken(video, scene)}


def _framed(db: DbSession, storage: DirectoryStorage, video: Video, scene: Scene) -> dict:
    """How the preview frames the scene's photo, as the render does ("Khung ảnh"): with the video's tallest framed
    text box, so every scene's photo starts on the same line."""
    if not framable(video, scene):
        return {}
    return {
        "fit": photo_fit(video, scene),
        "min_top": text_floor(video, scene),
        "crop_offset": scene.image_crop_offset,
        "reserve": text_reserve(storage, video, split_scenes(db, video)[1]),
    }


def _cumulative(db: DbSession, scene: Scene) -> tuple:
    """The pictures "Cộng dồn" lays over the scene (frames.cumulative_pictures); () when the scene shows none."""
    video = db.get(Video, scene.video_id)
    options = video_options.render_options(video)
    narration = spoken(video, scene)
    if not frames.captioned(options, scene.is_title, _is_last(db, video, scene), narration):
        return ()
    try:
        marked = frozenset(
            word.strip(",.!?:;…").casefold()
            for line in parse_scene_text(scene.text)
            for run in line
            if run.red
            for word in run.text.split()
        )
    except MarkupError:
        marked = frozenset()
    words = tuple((word["text"], float(word["start"]), float(word["end"])) for word in scene.voice_words or [])
    seconds = scene.voice_seconds or max(2.0, 0.35 * len(narration.split()))
    return frames.cumulative_pictures(
        narration, words, seconds, scene.seconds, marked, options.pc_style, scene.text_zone
    )


@router.get("/scenes/{scene_id}/cumulative")
def scene_cumulative(scene_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """The steps of the scene's "Cộng dồn" captions for the studio's player: their seconds into the scene and where
    each picture goes; the pictures are `cumulative/<n>.png`."""
    scene = _scene(db, scene_id)
    return {
        "steps": [
            {
                "start": start,
                "end": end,
                "url": f"/api/scenes/{scene_id}/cumulative/{number}.png?v={hashlib.md5(png).hexdigest()[:10]}",
                "left": left,
                "top": top,
                "width": width,
                "height": height,
            }
            for number, (start, end, png, left, top, width, height) in enumerate(_cumulative(db, scene))
        ]
    }


@router.get("/scenes/{scene_id}/cumulative/{number}.png")
def scene_cumulative_picture(
    scene_id: int, number: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> Response:
    pictures = _cumulative(db, _scene(db, scene_id))
    if not 0 <= number < len(pictures):
        raise ApiError(404, "no_caption_step", "Cảnh này không có phụ đề cộng dồn ở bước này")
    return Response(pictures[number][2], media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/scenes/{scene_id}/frame.jpg")
def scene_frame(
    scene_id: int,
    anchor: str = "top",
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> Response:
    """The scene's first frame without its text box, which the text box is dragged over. A framed photo
    ("Khung ảnh") moves with the box: `anchor` "bottom" lays it out for a box in the lower half, else the upper."""
    scene = _scene(db, scene_id)
    still = scene_still(storage, scene)
    if still is None:
        raise ApiError(404, "file_not_found", "Cảnh chưa có ảnh hoặc không lấy được khung hình từ video")
    video = db.get(Video, scene.video_id)
    if framable(video, scene):
        centre = [FRAME_WIDTH // 2, FRAME_HEIGHT - 1] if anchor == "bottom" else None
        frame = frames.compose_frame(
            still,
            scene.text,
            scene.is_title,
            video_options.render_options(video),
            centre,
            show_text=False,
            **_framed(db, storage, video, scene),
            last=_is_last(db, video, scene),
        )
    else:
        frame = frames.compose_frame(still, "", is_title=False)
    return Response(
        frames.jpeg_bytes(frame), media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"}
    )


@router.get("/scenes/{scene_id}/textbox.png")
def scene_textbox(scene_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> Response:
    """The exact box image the renderer overlays on this scene (transparent around it)."""
    scene = _scene(db, scene_id)
    video = db.get(Video, scene.video_id)
    size = video_options.text_size(video, scene.is_title)
    case = video_options.text_case(video, scene.is_title)
    options = video_options.render_options(video)
    last = _is_last(db, video, scene)
    drawn = frames.tiered(options, scene.is_title, last)
    if (
        not scene.text.strip()
        or frames.captioned(options, scene.is_title, last, spoken(video, scene))
        or (not drawn and text_problem(scene.text, scene.is_title, size, case) is not None)
    ):
        raise ApiError(404, "no_text_box", "Cảnh này không có chữ để đặt vị trí")
    box, _ = frames.text_box(scene.text, scene.is_title, options, last=last, zone=scene.text_zone)
    buffer = io.BytesIO()
    box.save(buffer, "PNG")
    return Response(buffer.getvalue(), media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/scenes/{scene_id}/video")
def scene_video(
    scene_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> FileResponse:
    scene = _scene(db, scene_id)
    extension = (scene.video_key or "").rsplit(".", 1)[-1]
    return _inline(storage, scene.video_key, CLIP_TYPES.get(extension, "application/octet-stream"))


@router.get("/scenes/{scene_id}/voice.mp3")
def scene_voice(
    scene_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> FileResponse:
    return _inline(storage, _scene(db, scene_id).voice_key, "audio/mpeg")


def custom_voice(db: DbSession, storage: DirectoryStorage, me: Session, scene_id: int, data: bytes, name: str) -> dict:
    """An MP3 made outside the app (another voice, a recorded one) as the scene's narration, from an upload or a link
    (MCP "Tải giọng đọc cho cảnh"): only the video's maker sets it, never while a job holds the video."""
    try:
        check_mp3(data)
    except UploadRejected:
        raise ApiError(
            415, "invalid_voice", "File giọng đọc phải là MP3 thật (đổi đuôi file khác thành .mp3 không dùng được)"
        ) from None
    video, scene = lock_scene(db, scene_id)
    ensure_owner(video.created_by_id, me.user_id, "video này", "đổi được giọng đọc")
    ensure_unlocked(db, video)
    old = set_custom_voice(db, storage, video, scene, data, name)
    payload = _saved(db, video)
    storage.delete(old)
    return payload


@router.post("/scenes/{scene_id}/voice")
def upload_scene_voice(
    scene_id: int,
    file: UploadFile = File(...),
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    data = read_limited(file, MAX_VOICE_BYTES, "File giọng đọc quá 20 MB, hãy chọn file nhỏ hơn")
    return custom_voice(db, storage, me, scene_id, data, file_label(file.filename, "giong-doc.mp3"))


@router.delete("/scenes/{scene_id}/voice")
def delete_scene_voice(
    scene_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """ "Bỏ giọng tải lên": the scene goes back to its voice; the next voice job or render reads it again."""
    video, scene = lock_scene(db, scene_id)
    ensure_owner(video.created_by_id, me.user_id, "video này", "đổi được giọng đọc")
    ensure_unlocked(db, video)
    old = remove_custom_voice(scene)
    payload = _saved(db, video)
    storage.delete(old)
    return payload


@router.get("/videos/{video_id}/thumbnail.jpg")
def thumbnail(
    video_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> FileResponse:
    video = db.get(Video, video_id)
    if video is None:
        raise video_not_found()
    return _inline(storage, video.thumbnail_key, "image/jpeg")


@router.get("/videos/{video_id}/music.mp3")
def music_file(
    video_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> FileResponse:
    video = db.get(Video, video_id)
    if video is None:
        raise video_not_found()
    return _inline(storage, video.music_key, "audio/mpeg")


@router.get("/videos/{video_id}/video.mp4")
def video_file(
    video_id: int,
    download: bool = False,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> FileResponse:
    video = db.get(Video, video_id)
    if video is None:
        raise video_not_found()
    if download:
        return _file(storage, video.mp4_key, "video/mp4", f"reels-video-{video.id}.mp4")
    return _inline(storage, video.mp4_key, "video/mp4")


# --- Knowledge ---


class NewTopicBody(BaseModel):
    name: str


class TopicPatchBody(BaseModel):
    name: str | None = None
    script_prompt: str | None = None
    clone_prompt: str | None = None
    revise_prompt: str | None = None  # "" goes back to the default
    banned_words: list[str] | None = None
    photo_hint: str | None = None
    # "Từ video mẫu": empty brings back the default prompt.
    learn_prompt: str | None = None
    analyze_prompt: str | None = None
    article_prompt: str | None = None  # "Bài viết": empty brings back the default prompt.
    voice_id: str | None = None  # the group's own voice; "" leaves it to each maker's defaults
    voice_backup_id: str | None = None  # the voice read instead when the voice above cannot; "" for none
    voice_format: dict | None = None  # "Giọng đọc theo vai" (voice_format.py); {} for none
    templates: list[int] | None = None  # the group's own "Mẫu dựng" (saved ones' ids)
    stock_order: list[str] | None = None  # "Thứ tự nguồn ảnh"; [] goes back to the app's order
    edit_template_default: object = None  # "app", one of `templates`, or null: what its new videos take (if sent)
    team_edit: bool | None = None  # "Cho cả đội sửa": only the group's maker turns it off or on
    video_mode: Literal["slides", "single", "alternate"] | None = None  # "Kiểu video" (videos.GROUP_VIDEO_MODES)
    text_look: dict | None = None  # "Chữ & phụ đề" (text_looks.FIELDS); null or {} (when sent): the maker's
    text_ai: bool | None = None  # "AI chọn kiểu chữ cho từng video"
    no_people: bool | None = None  # "Không dùng cảnh có người"
    outro_cta: bool | None = None  # "Cảnh kết Theo dõi & Chia sẻ" (outro.py)
    youtube_meta: dict | None = None  # "Mô tả YouTube" (youtube_meta.py); null or {} (when sent): none
    qc_config: dict | None = None  # "QC & duyệt" (qc_config.py); null or {} (when sent): the app's defaults
    media_folder: str | None = None  # "Tư liệu": its folder in the "Kho tư liệu"; null or "" (when sent) unlinks


MAX_PHOTO_HINT_LENGTH = 1000


def my_topic_ids(db: DbSession, user_id: int) -> set[int]:
    """ "My" topic groups: those of the Pages the member owns and uses (brief part B2)."""
    return set(
        db.scalars(
            select(Fanpage.knowledge_topic_id).where(
                Fanpage.owner_id == user_id, Fanpage.active.is_(True), Fanpage.knowledge_topic_id.is_not(None)
            )
        )
    )


def _knowledge_payload(db: DbSession, user_id: int) -> dict:
    counts = dict(db.execute(select(Video.knowledge_topic_id, func.count()).group_by(Video.knowledge_topic_id)).all())
    mine = my_topic_ids(db, user_id)
    last = edit_log.last_edits(db, edit_log.TOPIC)
    makers = dict(db.execute(select(User.id, User.name)).all())
    # What each group has towards "Sẵn sàng tạo video": active Pages that post it, documents, approved products.
    pages = dict(
        db.execute(
            select(Fanpage.knowledge_topic_id, func.count())
            .where(Fanpage.active.is_(True), Fanpage.knowledge_topic_id.is_not(None))
            .group_by(Fanpage.knowledge_topic_id)
        ).all()
    )
    page_rows: dict[int, list[dict]] = {}
    for row in db.scalars(
        select(Fanpage)
        .where(Fanpage.active.is_(True), Fanpage.knowledge_topic_id.is_not(None))
        .order_by(Fanpage.name, Fanpage.id)
    ):
        page_rows.setdefault(row.knowledge_topic_id, []).append({"id": row.id, "name": row.name})
    docs = dict(
        db.execute(select(TopicDoc.knowledge_topic_id, func.count()).group_by(TopicDoc.knowledge_topic_id)).all()
    )
    products = dict(
        db.execute(
            select(AffiliateProduct.knowledge_topic_id, func.count())
            .where(AffiliateProduct.status == "approved")
            .group_by(AffiliateProduct.knowledge_topic_id)
        ).all()
    )
    return {
        "topics": [
            {
                "id": topic.id,
                "name": topic.name,
                "script_prompt": topic.script_prompt,
                "clone_prompt": topic.clone_prompt,
                "revise_prompt": topic.revise_prompt,
                "banned_words": topic.banned_words,
                "photo_hint": topic.photo_hint,
                "learn_prompt": topic.learn_prompt,
                "analyze_prompt": topic.analyze_prompt,
                "article_prompt": topic.article_prompt,
                "voice_id": topic.voice_id,
                "voice_backup_id": topic.voice_backup_id,
                "voice_format": topic.voice_format or {},
                # "Kiểu video" and the mode a video made now takes by it ("Xen kẽ theo ngày" resolved for today).
                "video_mode": topic.video_mode,
                "video_mode_today": group_video_mode(topic),
                # "Chữ & phụ đề": the group's own look (None: each maker's), the AI's pick per video, the AI's last
                # suggested looks and its job (queued, running, or failed) while there is one to show.
                "text_look": text_looks.group_look(topic) or None,
                "text_ai": topic.text_ai,
                "no_people": topic.no_people,
                "outro_cta": topic.outro_cta,
                # "Mô tả YouTube": every field present; `youtube_meta_set` false while the group uploads the caption.
                "youtube_meta": youtube_meta.of(topic.youtube_meta),
                "youtube_meta_set": youtube_meta.is_set(topic.youtube_meta),
                # "QC & duyệt": every field present (the app's defaults where nothing is set).
                "qc_config": qc_config.of(topic.qc_config),
                "qc_config_set": qc_config.is_set(topic.qc_config),
                "text_suggestions": topic.text_suggestions,
                "text_job": text_looks.job_payload(text_looks.job_of(db, topic.id)),
                "created_by_id": topic.created_by_id,
                # The group's maker, who alone may turn "Cho cả đội sửa" off; None: "Nhận nhóm" is offered.
                "owner": makers.get(topic.created_by_id),
                "team_edit": topic.team_edit,
                "templates": [template.id for template in topic.edit_templates],
                "edit_template_default": topic.edit_template_default,
                # "Thứ tự nguồn ảnh": always whole; `stock_order_custom` false while the group takes the app's order.
                "stock_order": clean_stock_order(topic.stock_order),
                "stock_order_custom": bool(topic.stock_order),
                # "Tư liệu": the folder of the team's library the group's view shows; None: none linked yet.
                "media_folder": topic.media_folder,
                "video_count": counts.get(topic.id, 0),
                # The active Pages that post the group, to read its videos and revenue for one of them.
                "page_list": page_rows.get(topic.id, []),
                "readiness": {
                    "pages": pages.get(topic.id, 0),
                    "docs": docs.get(topic.id, 0),
                    "products": products.get(topic.id, 0),
                    "plan_started": topic.plan_start_date is not None,
                },
                # A group of a Page the member owns: listed first where a group is picked.
                "mine": topic.id in mine,
                # "Sửa lần cuối" under the group's name; None until its first logged change.
                "last_edit": edit_log.payload(last[topic.id]) if topic.id in last else None,
            }
            for topic in knowledge.all_topics(db)
        ],
        "default_script_prompt": knowledge.default_script_prompt(),
        "default_clone_prompt": knowledge.default_clone_prompt(),
        "default_learn_prompt": knowledge.default_learn_prompt(),
        "default_analyze_prompt": knowledge.default_analyze_prompt(),
        "default_revise_prompt": knowledge.default_revise_prompt(),
        "default_article_prompt": knowledge.default_article_prompt(),
        # Where a group's own "Chữ & phụ đề" starts from: the member's own defaults.
        "default_text_look": {
            name: value
            for name, value in video_options.member_defaults(db, user_id).items()
            if name in text_looks.FIELDS
        },
    }


def _topic_name(db: DbSession, raw: str, own_id: int | None = None) -> str:
    name = " ".join(unicodedata.normalize("NFC", raw).split())
    if not name:
        raise invalid("Hãy nhập tên nhóm chủ đề")
    if len(name) > MAX_TOPIC_NAME_LENGTH:
        raise invalid(f"Tên nhóm chủ đề dài quá {MAX_TOPIC_NAME_LENGTH} ký tự")
    if any(topic.id != own_id and topic.name.casefold() == name.casefold() for topic in knowledge.all_topics(db)):
        raise invalid(f"Đã có nhóm chủ đề “{name}”")
    return name


def _prompt(raw: str) -> str:
    value = unicodedata.normalize("NFC", raw.replace("\r\n", "\n")).strip()
    if not value:
        raise invalid("Prompt không được để trống")
    if len(value) > 20000:
        raise invalid("Prompt dài quá 20000 ký tự")
    return value


def _optional_prompt(raw: str) -> str:
    """A prompt that may be left empty, for its default to be used."""
    value = unicodedata.normalize("NFC", raw.replace("\r\n", "\n")).strip()
    if len(value) > 20000:
        raise invalid("Prompt dài quá 20000 ký tự")
    return value


def _topic(db: DbSession, topic_id: int) -> KnowledgeTopic:
    topic = db.get(KnowledgeTopic, topic_id)
    if topic is None:
        raise ApiError(404, "topic_not_found", "Không tìm thấy nhóm chủ đề")
    return topic


@router.get("/knowledge")
def get_knowledge(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    return _knowledge_payload(db, me.user_id)


@router.post("/knowledge/topics", status_code=201)
def create_topic(body: NewTopicBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    topic = KnowledgeTopic(name=_topic_name(db, body.name), created_by_id=me.user_id, updated_by_id=me.user_id)
    db.add(topic)
    db.flush()
    edit_log.record(
        db,
        edit_log.TOPIC,
        topic.id,
        "create",
        me.user_id,
        label=topic.name,
        changes={"name": {"old": None, "new": topic.name}},
    )
    db.commit()
    return _knowledge_payload(db, me.user_id)


# What "Nhân bản nhóm" copies: the prompts and the settings a group's new videos start from. Not its videos, plan,
# documents, text suggestions or linked folder (a folder belongs to one group).
COPIED_TOPIC_FIELDS = (
    "script_prompt",
    "clone_prompt",
    "revise_prompt",
    "learn_prompt",
    "analyze_prompt",
    "article_prompt",
    "plan_prompt",
    "photo_hint",
    "voice_id",
    "voice_backup_id",
    "voice_format",
    "video_mode",
    "text_ai",
    "no_people",
    "outro_cta",
    "qc_config",
    "edit_template_default",
)


def _copy_name(db: DbSession, name: str) -> str:
    """ "<name> (bản sao)", then "(bản sao 2)" and so on, cut to fit the name's length."""
    taken = {topic.name.casefold() for topic in knowledge.all_topics(db)}
    for number in range(1, 1000):
        suffix = " (bản sao)" if number == 1 else f" (bản sao {number})"
        candidate = name[: MAX_TOPIC_NAME_LENGTH - len(suffix)].rstrip() + suffix
        if candidate.casefold() not in taken:
            return candidate
    raise invalid("Có quá nhiều bản sao của nhóm này")


@router.post("/knowledge/topics/{topic_id}/duplicate", status_code=201)
def duplicate_topic(topic_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Nhân bản nhóm": a new group of the member's with the prompts and settings of this one. Using a group is open to
    everyone, so any member may copy any group; the copy is theirs, and open to the team."""
    source = _topic(db, topic_id)
    topic = KnowledgeTopic(
        name=_copy_name(db, source.name),
        created_by_id=me.user_id,
        updated_by_id=me.user_id,
        banned_words=list(source.banned_words),
        plan_post_times=list(source.plan_post_times),
        stock_order=list(source.stock_order) if source.stock_order else None,
        text_look=dict(source.text_look) if source.text_look else None,
        youtube_meta=youtube_meta.clean(source.youtube_meta),
        **{field: getattr(source, field) for field in COPIED_TOPIC_FIELDS},
    )
    topic.edit_templates = list(source.edit_templates)
    db.add(topic)
    db.flush()
    edit_log.record(
        db,
        edit_log.TOPIC,
        topic.id,
        "create",
        me.user_id,
        label=topic.name,
        changes={"name": {"old": None, "new": topic.name}},
    )
    db.commit()
    return _knowledge_payload(db, me.user_id)


@router.patch("/knowledge/topics/{topic_id}")
def patch_topic(
    topic_id: int, body: TopicPatchBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    topic = _topic(db, topic_id)
    if body.team_edit is not None:
        ensure_owner(topic.created_by_id, me.user_id, "nhóm chủ đề này", "đổi được “Cho cả đội sửa”")
        topic.team_edit = body.team_edit
    if body.model_fields_set - {"team_edit"}:
        ensure_group_editor(db, topic, me.user_id)
    before = edit_log.topic_snapshot(topic)
    if body.name is not None:
        old_name, topic.name = topic.name, _topic_name(db, body.name, topic.id)
        # The music library is tagged with the groups' names.
        music_topics.rename_topic(db, old_name, topic.name)
    if body.script_prompt is not None:
        topic.script_prompt = _prompt(body.script_prompt)
    if body.clone_prompt is not None:
        topic.clone_prompt = _prompt(body.clone_prompt)
    if body.revise_prompt is not None:
        topic.revise_prompt = _prompt(body.revise_prompt) if body.revise_prompt.strip() else ""
    if body.banned_words is not None:
        topic.banned_words = list(
            dict.fromkeys(_clean_list(body.banned_words, MAX_KEYWORD_LENGTH, "Từ cấm", max_items=500))
        )
    if body.photo_hint is not None:
        hint = unicodedata.normalize("NFC", body.photo_hint.replace("\r\n", "\n")).strip()
        if len(hint) > MAX_PHOTO_HINT_LENGTH:
            raise invalid(f"Gợi ý tìm ảnh dài quá {MAX_PHOTO_HINT_LENGTH} ký tự")
        topic.photo_hint = hint
    if body.learn_prompt is not None:
        topic.learn_prompt = _optional_prompt(body.learn_prompt)
    if body.analyze_prompt is not None:
        topic.analyze_prompt = _optional_prompt(body.analyze_prompt)
    if body.article_prompt is not None:
        article_prompt = _optional_prompt(body.article_prompt)
        topic.article_prompt = "" if article_prompt == knowledge.default_article_prompt() else article_prompt
    if body.voice_id is not None:
        try:
            topic.voice_id = video_options.clean({"voice_id": body.voice_id})["voice_id"]
        except video_options.OptionError as err:
            raise invalid(str(err)) from None
    if body.voice_backup_id is not None:
        try:
            topic.voice_backup_id = video_options.clean({"voice_id": body.voice_backup_id})["voice_id"]
        except video_options.OptionError as err:
            raise invalid(str(err)) from None
    if body.voice_format is not None:
        try:
            topic.voice_format = voice_format.clean(body.voice_format)
        except video_options.OptionError as err:
            raise invalid(str(err)) from None
    if body.video_mode is not None:
        topic.video_mode = body.video_mode
    if "text_look" in body.model_fields_set:
        try:
            topic.text_look = text_looks.clean_look(body.text_look, topic) if body.text_look else None
        except video_options.OptionError as err:
            raise invalid(str(err)) from None
    if body.text_ai is not None:
        topic.text_ai = body.text_ai
    if body.no_people is not None:
        topic.no_people = body.no_people
    if body.outro_cta is not None:
        topic.outro_cta = body.outro_cta
    if "youtube_meta" in body.model_fields_set:
        try:
            topic.youtube_meta = youtube_meta.clean(body.youtube_meta)
        except youtube_meta.MetaError as err:
            raise invalid(str(err)) from None
    if "qc_config" in body.model_fields_set:
        try:
            topic.qc_config = qc_config.clean(body.qc_config)
        except qc_config.ConfigError as err:
            raise invalid(str(err)) from None
    if "media_folder" in body.model_fields_set:
        from .routes_media import link_folder

        topic.media_folder = link_folder(db, topic, body.media_folder)
    if body.stock_order is not None:
        unknown = [source for source in body.stock_order if source not in STOCK_SOURCES]
        if unknown:
            raise invalid(f"Nguồn ảnh không hợp lệ: {', '.join(unknown[:3])}")
        order = clean_stock_order(body.stock_order) if body.stock_order else None
        # The app's own order saved as is stays "the app's", so later changes to it still reach the group.
        topic.stock_order = None if order == list(STOCK_SOURCES) else order
    _set_group_templates(db, topic, body)
    topic.updated_by_id = me.user_id
    changes = edit_log.diff(before, edit_log.topic_snapshot(topic))
    edit_log.record(db, edit_log.TOPIC, topic.id, "update", me.user_id, label=topic.name, changes=changes)
    db.commit()
    return _knowledge_payload(db, me.user_id)


def _set_group_templates(db: DbSession, topic: KnowledgeTopic, body: TopicPatchBody) -> None:
    """The group's own templates and the one its new videos take ("app" or one of its own; null for none)."""
    if body.templates is not None:
        ids = list(dict.fromkeys(body.templates))
        rows = db.scalars(select(EditTemplate).where(EditTemplate.id.in_(ids))).all() if ids else []
        if len(rows) != len(ids):
            raise invalid("Có mẫu dựng không còn trong thư viện")
        topic.edit_templates = sorted(rows, key=lambda row: row.name)
    held = {template.id for template in topic.edit_templates}
    if "edit_template_default" in body.model_fields_set:
        chosen = body.edit_template_default
        if (
            chosen is not None
            and chosen != autoedit.APP
            and not (isinstance(chosen, int) and not isinstance(chosen, bool) and chosen in held)
        ):
            raise invalid("Mẫu cho video mới của nhóm phải là một mẫu của nhóm")
        topic.edit_template_default = chosen
    elif isinstance(topic.edit_template_default, int) and topic.edit_template_default not in held:
        # A template taken off the group no longer dresses its new videos.
        topic.edit_template_default = None


@router.post("/knowledge/topics/{topic_id}/text-suggestions")
def suggest_text_looks(topic_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "AI gợi ý" on the group's "Chữ & phụ đề": a job (the team's LLM, one call); its looks wait on the group for a
    member to pick one and save it."""
    topic = _topic(db, topic_id)
    ensure_group_editor(db, topic, me.user_id)
    if not text_looks.enqueue(db, topic.id, me.user_id):
        raise ApiError(409, "text_look_busy", "Nhóm đang có gợi ý kiểu chữ chờ hoặc đang tạo")
    db.commit()
    return _knowledge_payload(db, me.user_id)


@router.post("/knowledge/topics/{topic_id}/owner")
def claim_topic(topic_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Nhận nhóm": a group nobody is known to have made becomes the member's, as "Nhận Page" does for a Page."""
    topic = db.scalar(select(KnowledgeTopic).where(KnowledgeTopic.id == topic_id).with_for_update())
    if topic is None:
        raise ApiError(404, "topic_not_found", "Không tìm thấy nhóm chủ đề")
    if topic.created_by_id is not None and topic.created_by_id != me.user_id:
        raise ApiError(409, "topic_has_owner", f"Nhóm “{topic.name}” đã có người tạo")
    topic.created_by_id = me.user_id
    db.commit()
    return _knowledge_payload(db, me.user_id)


@router.delete("/knowledge/topics/{topic_id}")
def delete_topic(topic_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    topic = _topic(db, topic_id)
    ensure_owner(topic.created_by_id, me.user_id, "nhóm chủ đề này")
    ensure_none_of_others(
        {
            "video": db.scalar(
                select(func.count())
                .select_from(Video)
                .where(Video.knowledge_topic_id == topic.id, Video.created_by_id != me.user_id)
            ),
            "ý tưởng kế hoạch": db.scalar(
                select(func.count())
                .select_from(TopicPlanItem)
                .where(
                    TopicPlanItem.knowledge_topic_id == topic.id,
                    TopicPlanItem.created_by_id.is_distinct_from(me.user_id),
                )
            ),
            "sản phẩm affiliate": db.scalar(
                select(func.count())
                .select_from(AffiliateProduct)
                .where(AffiliateProduct.knowledge_topic_id == topic.id, AffiliateProduct.created_by_id != me.user_id)
            ),
        },
        f"Nhóm chủ đề “{topic.name}”",
    )
    videos = db.scalar(select(func.count()).select_from(Video).where(Video.knowledge_topic_id == topic.id))
    if videos:
        raise ApiError(409, "topic_in_use", f"Nhóm chủ đề còn {videos} video nên chưa xoá được")
    products = db.scalar(
        select(func.count()).select_from(AffiliateProduct).where(AffiliateProduct.knowledge_topic_id == topic.id)
    )
    if products:
        raise ApiError(409, "topic_in_use", f"Nhóm chủ đề còn {products} sản phẩm affiliate nên chưa xoá được")
    job = plans.plan_job(db, topic.id)
    if job is not None and job.status != "failed":
        raise ApiError(409, "topic_in_use", "Nhóm chủ đề đang tạo kế hoạch bằng AI nên chưa xoá được")
    music_topics.drop_topic(db, topic.name)
    # What the group held, readable in the list's history after it is gone.
    held = {field: value for field, value in edit_log.topic_snapshot(topic).items() if value not in ("", [], None)}
    edit_log.record(
        db,
        edit_log.TOPIC,
        topic.id,
        "delete",
        me.user_id,
        label=topic.name,
        changes={field: {"old": value, "new": None} for field, value in held.items()},
    )
    db.delete(topic)
    db.commit()
    return _knowledge_payload(db, me.user_id)
