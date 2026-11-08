import io
import math
import re
import tempfile
import time
import unicodedata
from datetime import datetime, timedelta
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
from reels_render.script import MAX_VIDEO_SPEED, MIN_VIDEO_SPEED
from reels_render.sounds import MUSIC_LEVELS
from reels_render.textbox import FRAME_WIDTH

from . import (
    affiliate_rounds,
    article_posts,
    articles,
    auto_photos,
    autoedit,
    clips,
    frames,
    image_edit,
    image_providers,
    knowledge,
    llm,
    music_topics,
    plans,
    remote_media,
    source_keys,
    stock_clips,
    tts,
    video_options,
)
from .claude import GeneratedScript
from .db import get_db
from .errors import ApiError
from .models import (
    AffiliateProduct,
    AppSetting,
    Article,
    Fanpage,
    Job,
    KnowledgeTopic,
    MusicTrack,
    Publication,
    Scene,
    Session,
    TopicPlanItem,
    Video,
)
from .openverse import Openverse, OpenverseError
from .pexels import Pexels, PexelsError
from .pixabay import ORIENTATIONS, Pixabay, PixabayError
from .script_rules import CROSSFADE_SIDE_SECONDS, MAX_SECONDS, MIN_SECONDS, plain_title, text_problem
from .sessions import current_member, now
from .stock_sites import stock_site
from .storage import DirectoryStorage, get_storage
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
    MODES,
    OPEN_POST_STATUSES,
    active_job,
    auto_seconds,
    drop_original,
    ensure_unlocked,
    follow_narration,
    list_extras,
    list_payload,
    lock_scene,
    lock_video,
    made_from,
    made_voice_seconds,
    new_key,
    pending_publication,
    posted_fanpage_ids,
    publications_of,
    refresh_thumbnail,
    render_signature,
    run_checks,
    scene_still,
    split_scenes,
    spoken,
    text_position,
    title_of,
    video_not_found,
    video_payload,
)

router = APIRouter(prefix="/api")

MAX_TOPIC_LENGTH = 300
MAX_CONTENT_TYPE_LENGTH = 40  # videos.content_type
MAX_TEXT_LENGTH = 500
MAX_VOICE_LENGTH = 1000
MAX_LONG_TEXT_LENGTH = 5000
MAX_KEYWORDS = 10
MAX_KEYWORD_LENGTH = 100
MAX_LIST_ITEMS = 20
NEW_SCENE_SECONDS = 4
MAX_MUSIC_START = 600  # seconds into a song; past its end the song loops from its start
TITLE_SECONDS = 3  # as the script job gives the title scene
# "Tự viết": a pasted script's limits, well past what a 90-second video can hold.
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
    # How the video is built (videos.MODES): "slides", or "single" ("Video xuyên suốt", one backdrop).
    video_mode: Literal["slides", "single"] = "slides"


class VideoPatchBody(BaseModel):
    caption: str | None = None
    hashtags: list[str] | None = None
    affiliates: list[str] | None = None
    pinned_comment: str | None = None
    music_suggestions: list[str] | None = None
    music_volume: int | None = None
    music_start: object = None  # seconds into the song where the video's music starts
    voice_enabled: bool | None = None
    options: dict | None = None  # some of video_options.DEFAULTS
    mode: str | None = None  # videos.MODES; switching keeps every photo, clip and layer
    content_type: str | None = None  # "Loại nội dung"; "" for none


class ScenePatchBody(BaseModel):
    text: str | None = None
    seconds: float | None = None  # typing the seconds turns "Tự khớp lời đọc" off
    seconds_auto: bool | None = None  # true: the seconds follow the narration (at once when it is already made)
    keywords: list[str] | None = None
    keywords_en: list[str] | None = None
    image_prompt: str | None = None
    voice_text: str | None = None
    video_start: float | None = None
    video_speed: float | None = None
    video_sound: bool | None = None  # "Tiếng gốc": the clip's own sound is heard in the render
    text_position: object = None  # the text box centre [x, y]; null: back to the video's (or template's)
    image_checked: bool | None = None  # true: a member looked at the app's pick and keeps it ("Giữ ảnh này")
    transition: object = None  # the transition into this scene (reels_render.effects); null: the video's
    color: object = None  # its colour preset; null: as shot
    music_level: object = None  # the music's level during the scene (reels_render.sounds); null: the video's


class PublishBody(BaseModel):
    fanpage_id: int
    scheduled_at: datetime | None = None
    # "Tự bình luận": the worker writes the affiliate comment under the reel once it is live (post_comments.py).
    auto_comment: bool = True


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
    if not video.has_script:
        raise ApiError(409, "no_script", "Video chưa có kịch bản")
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
) -> list[dict]:
    """Every video, newest first; `q` searches the topic and the title, `knowledge_topic_id` keeps one topic group's
    (its "Video" tab in Kho kiến thức)."""
    query = select(Video).order_by(Video.created_at.desc(), Video.id.desc())
    if knowledge_topic_id is not None:
        query = query.where(Video.knowledge_topic_id == knowledge_topic_id)
    if q.strip():
        literal = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{unicodedata.normalize('NFC', literal)}%"
        plain = func.replace(func.replace(Scene.text, "*", ""), "\n", " ")
        title_match = select(Scene.video_id).where(Scene.is_title, plain.ilike(pattern, escape="\\"))
        query = query.where(or_(Video.topic.ilike(pattern, escape="\\"), Video.id.in_(title_match)))
    family = made_from(db)
    videos = db.scalars(query).all()
    extras = list_extras(db, videos)
    return [list_payload(db, video, family, extras[video.id]) for video in videos]


@router.get("/video-content-types")
def content_types(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> list[str]:
    """The "Loại nội dung" the team's videos use, to pick from: one per type whatever its case, in Vietnamese order
    (the first spelling met wins)."""
    seen: dict[str, str] = {}
    for kind in db.scalars(select(Video.content_type).where(Video.content_type != "").order_by(Video.id)):
        seen.setdefault(kind.casefold(), kind)
    return sorted(seen.values(), key=lambda kind: unicodedata.normalize("NFD", kind).casefold())


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
) -> Video:
    """A new video, its script queued, typed ("Tự viết") or, as `written`, already written from the group's prompt by
    a member's own Claude through MCP (`via` "assistant"): saved as the script job saves an answer, with no LLM call.
    The caller commits."""
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
        mode=body.video_mode,
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
    elif written is not None:
        # Imported here: the job module loads the render core, which the routes otherwise do not need at import.
        from . import jobs

        jobs.save_script(db, video, written)
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
    no default is set or the track is gone. Only new videos: the music a video already has is never replaced."""
    track_id = video_options.member_defaults(db, user_id).get("music_track_id")
    track = db.get(MusicTrack, track_id) if track_id else None
    if track is None or not storage.exists(track.storage_key):
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
    if "caption" in fields and body.caption is not None:
        video.caption = _clean_text(body.caption, MAX_LONG_TEXT_LENGTH, "Caption").strip()
    if "pinned_comment" in fields and body.pinned_comment is not None:
        video.pinned_comment = _clean_text(body.pinned_comment, MAX_LONG_TEXT_LENGTH, "Bình luận ghim").strip()
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
        if body.mode not in MODES:
            raise invalid("Kiểu video không có trong danh sách")
        video.mode = body.mode
    if "content_type" in fields and body.content_type is not None:
        kind = " ".join(unicodedata.normalize("NFC", body.content_type).split())
        if len(kind) > MAX_CONTENT_TYPE_LENGTH:
            raise invalid(f"Loại nội dung tối đa {MAX_CONTENT_TYPE_LENGTH} ký tự")
        video.content_type = kind
    look = video_options.text_look(video)
    pause = video_options.voice_pause(video)
    if body.options:
        try:
            changes = video_options.clean(body.options)
        except video_options.OptionError as err:
            raise invalid(str(err)) from None
        video.options = video_options.effective(video) | changes
    if video_options.voice_pause(video) != pause:
        title, scenes = split_scenes(db, video)
        follow_narration(video, [scene for scene in (title, *scenes) if scene is not None])
    if video_options.text_look(video) != look:
        # The thumbnail is the title scene's first frame, drawn in the text box style.
        title, _ = split_scenes(db, video)
        refresh_thumbnail(db, storage, video, title)
    return _saved(db, video)


@router.delete("/videos/{video_id}")
def delete_video(
    video_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    video = lock_video(db, video_id)
    ensure_unlocked(db, video)
    db.execute(delete(Video).where(Video.id == video_id))
    db.commit()
    # Files only go after the rows: a failed commit must not leave a video whose photos are gone.
    storage.delete_prefix(f"videos/{video_id}")
    return {"ok": True}


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
    """ "Tạo giọng thật" in the preview: the video's voice (ElevenLabs or VieNeu) reads the scenes whose narration is
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
        raise invalid(f"Chưa cài đặt {name}: nhập key ở Cài đặt › Nguồn tư liệu")
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
    when = body.scheduled_at
    if when is not None:
        if when.tzinfo is None:
            raise invalid("Giờ đăng phải kèm múi giờ")
        if not now() + MIN_SCHEDULE_DELAY <= when <= now() + MAX_SCHEDULE_DELAY:
            raise invalid("Giờ hẹn phải sau ít nhất 15 phút và trong vòng 29 ngày tới")
    fanpage = db.get(Fanpage, body.fanpage_id)
    if fanpage is None or not fanpage.active:
        raise invalid("Hãy chọn một Fanpage đang dùng")
    if fanpage.id in posted_fanpage_ids(video, publications_of(db, video.id)):
        raise ApiError(
            409, "already_published", "Bản MP4 này đang có trên Fanpage đó, hãy render bản mới hoặc xóa bài cũ"
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
    if post.status not in LIVE_POST_STATUSES or post.remote_id is None:
        raise ApiError(409, "post_not_checkable", "Chỉ kiểm tra được bài đã lên Facebook hoặc đã hẹn giờ")
    if active_job(db, video.id) is not None:
        raise ApiError(409, "video_locked", "Video đang có job chạy, hãy đợi xong rồi kiểm tra bài")
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
    if video.pinned_comment:
        lines.append(f"Bình luận ghim: {video.pinned_comment}")
    return {
        "video_id": video.id,
        "title": title_of(video, title) or video.topic,
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
        # The same picture goes on, so it cuts in rather than showing a transition into itself.
        transition="cut",
        color=scene.color,
        music_level=scene.music_level,
    )
    db.add(rest)
    db.flush()
    if scene.video_key:
        rest.video_key = new_key(video.id, f"clip-{rest.id}", Path(scene.video_key).suffix.lstrip("."))
        storage.save_file(rest.video_key, storage.path(scene.video_key))
        rest.video_seconds, rest.video_speed = scene.video_seconds, scene.video_speed
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
        scene.video_sound = body.video_sound
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
    if "music_level" in fields:
        level = body.music_level
        if level is not None and (not isinstance(level, str) or level not in MUSIC_LEVELS):
            raise invalid(f"Mức nhạc không hợp lệ: {level!r}")
        scene.music_level = level
    _follow_voice(video, scene)
    if scene.is_title and (text_changed or start_changed or moved):
        title, _ = split_scenes(db, video)
        refresh_thumbnail(db, storage, video, title)
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
) -> dict:
    """Store a photo in place of the scene's photo or clip; `source` None keeps the photo's source (a crop of it)."""
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
    key = new_key(video.id, f"scene-{scene.id}", extension)
    storage.save_bytes(key, data)
    scene.image_key, scene.image_source, scene.image_error = key, source, None
    # A member chose, uploaded or cropped this photo: it is no longer the app's unchecked pick. A photo the extension
    # picked from Google is one, until a member looks at it.
    scene.image_auto = auto
    # A photo replaces the scene's clip: a scene shows one or the other.
    scene.video_key, scene.video_seconds, scene.video_start, scene.video_speed = None, None, 0, 1
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
    scene.video_sound, scene.words = False, None
    if scene.is_title:
        title, _ = split_scenes(db, video)
        refresh_thumbnail(db, storage, video, title)
    payload = _saved(db, video)
    storage.delete(old)
    return payload


def _orientation(value: str) -> str:
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
    source: str = "pexels",
    orientation: str = "vertical",
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    orientation = _orientation(orientation)
    client, error_type = _stock_client(source, db)
    video, scene = lock_scene(db, scene_id)
    ensure_unlocked(db, video)
    if source in stock_turned_off(db):
        raise invalid("Nguồn này đang tắt trong Cài đặt › Nguồn tư liệu")
    # Each source is searched in the language it indexes: Openverse in Vietnamese, Pixabay and Pexels
    # in English; the other list is the fallback (scenes scripted before English keywords existed).
    vietnamese, english = list(scene.keywords), list(scene.keywords_en)
    keywords = (vietnamese or english) if source == "openverse" else (english or vietnamese)
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
    return _store_photo(db, storage, scene_id, photo.data, photo.extension, photo.url)


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

# Pexels first: the default of the picker, "Tìm ảnh" and "Tự tìm ảnh".
STOCK_SOURCES = ("pexels", "pixabay", "openverse")
STOCK_LABELS = {"pixabay": "Pixabay", "pexels": "Pexels", "openverse": "Openverse"}
STOCK_OFF_KEY = "stock_sources_off"
CLIP_DOWNLOAD_SECONDS = 60


def _stock_client(source: str, db: DbSession):
    """The picker client for a source and its error type; an unknown source is a bad request."""
    if source == "pixabay":
        return Pixabay(source_keys.get(db, "pixabay")), PixabayError
    if source == "pexels":
        return Pexels(source_keys.get(db, "pexels")), PexelsError
    if source == "openverse":
        return Openverse(), OpenverseError
    raise invalid("Nguồn ảnh không hợp lệ")


def stock_configured(source: str, db: DbSession) -> bool:
    if source in ("pixabay", "pexels"):
        return bool(source_keys.get(db, source))
    return True  # Openverse answers anonymous calls.


def stock_turned_off(db: DbSession) -> set[str]:
    """The sources the team turned off on Cài đặt › Nguồn tư liệu."""
    setting = db.get(AppSetting, STOCK_OFF_KEY)
    return (
        {item for item in setting.value if item in STOCK_SOURCES}
        if setting and isinstance(setting.value, list)
        else set()
    )


def _stock_available(source: str, db: DbSession) -> bool:
    return stock_configured(source, db) and source not in stock_turned_off(db)


@router.get("/stock/sources")
def stock_sources(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> list[dict]:
    """The picker's sources; `clips` says which also offer video clips."""
    return [
        {
            "id": source,
            "label": STOCK_LABELS[source],
            "available": _stock_available(source, db),
            "clips": source in stock_clips.SOURCES and _stock_available(source, db),
        }
        for source in STOCK_SOURCES
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
        raise invalid("Nguồn này đang tắt trong Cài đặt › Nguồn tư liệu")
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
        raise invalid("Nguồn này đang tắt trong Cài đặt › Nguồn tư liệu")
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
    source: str = "pexels",
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
    orientation = _orientation(orientation)
    used = _used_photos(db, scene.video_id) if hide_used else set()
    keyword = " ".join(q.split())
    if not keyword:
        raise invalid("Hãy nhập từ khóa tìm ảnh")
    if len(keyword) > MAX_KEYWORD_LENGTH:
        raise invalid(f"Từ khóa dài quá {MAX_KEYWORD_LENGTH} ký tự")
    if source in stock_turned_off(db):
        raise invalid("Nguồn này đang tắt trong Cài đặt › Nguồn tư liệu")
    client, error_type = _stock_client(source, db)
    db.rollback()
    try:
        hits = client.search_hits(keyword, time.monotonic() + FIND_IMAGE_SECONDS, orientation)
    except error_type as err:
        raise ApiError(502, "stock_error", f"Không tìm được ảnh: {err.message}") from None
    return {
        "keyword": keyword,
        "source": source,
        "hits": [{"url": hit.url, "preview": hit.preview} for hit in hits if hit.url not in used],
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
        raise invalid("Nguồn này đang tắt trong Cài đặt › Nguồn tư liệu")
    client, error_type = _stock_client(body.source, db)
    db.rollback()
    deadline = time.monotonic() + FIND_IMAGE_SECONDS
    try:
        # The address comes from the browser: only a result the source itself returned may be fetched.
        if body.url not in client.search(" ".join(body.keyword.split()), deadline, _orientation(body.orientation)):
            raise invalid("Ảnh này không có trong kết quả tìm, hãy tìm lại")
        photo = client.download(body.url, deadline)
    except error_type as err:
        raise ApiError(502, "stock_error", f"Không tìm được ảnh: {err.message}") from None
    if photo is None:
        raise ApiError(422, "unusable_image", "Ảnh này không tải được, hãy chọn ảnh khác")
    return _store_photo(db, storage, scene_id, photo.data, photo.extension, photo.url)


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
    rows = []
    for job in jobs:
        # A plan job has no video: it is named after its topic group; an article's job after the article.
        owner = job.video_id or (f"article-{job.article_id}" if job.article_id else f"topic-{job.knowledge_topic_id}")
        if owner not in titles:
            if job.article_id is not None:
                article = db.get(Article, job.article_id)
                titles[owner] = f"Bài viết · {article.topic or articles.KIND_LABELS[article.kind]}"
            elif job.video_id is None:
                group = db.get(KnowledgeTopic, job.knowledge_topic_id)
                titles[owner] = f"Kế hoạch 30 ngày · {group.name}"
            else:
                video = db.get(Video, job.video_id)
                title, _ = split_scenes(db, video)
                titles[owner] = title_of(video, title) or video.topic
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
    if job.article_id is not None:
        return article_posts.payload(db, db.get(Article, job.article_id))
    if job.video_id is None:
        return plans.plan_payload(db, db.get(KnowledgeTopic, job.knowledge_topic_id))
    return video_payload(db, db.get(Video, job.video_id))


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    owner = db.execute(select(Job.video_id, Job.knowledge_topic_id, Job.article_id).where(Job.id == job_id)).first()
    if owner is None:
        raise ApiError(404, "job_not_found", "Không tìm thấy job")
    video_id, topic_id, article_id = owner
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


def _retry_plan(db: DbSession, job_id: int, topic_id: int, me: Session) -> dict:
    if db.get(Job, job_id).status != "failed":
        raise ApiError(409, "job_not_failed", "Chỉ thử lại được job bị lỗi")
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
    else:
        queued = article_posts.enqueue(
            db, article, job.kind, me.user_id, publication_id=job.publication_id, retry_of_id=job_id
        )
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
        still, scene.text, scene.is_title, video_options.render_options(video), text_position(video, scene)
    )
    return Response(
        frames.jpeg_bytes(frame), media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"}
    )


@router.get("/scenes/{scene_id}/frame.jpg")
def scene_frame(
    scene_id: int,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> Response:
    """The scene's first frame without its text box, which the text box is dragged over."""
    still = scene_still(storage, _scene(db, scene_id))
    if still is None:
        raise ApiError(404, "file_not_found", "Cảnh chưa có ảnh hoặc không lấy được khung hình từ video")
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
    if not scene.text.strip() or text_problem(scene.text, scene.is_title, size, case) is not None:
        raise ApiError(404, "no_text_box", "Cảnh này không có chữ để đặt vị trí")
    box, _ = frames.text_box(scene.text, scene.is_title, video_options.render_options(video))
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
                "video_count": counts.get(topic.id, 0),
                # A group of a Page the member owns: listed first where a group is picked.
                "mine": topic.id in mine,
            }
            for topic in knowledge.all_topics(db)
        ],
        "default_script_prompt": knowledge.default_script_prompt(),
        "default_clone_prompt": knowledge.default_clone_prompt(),
        "default_learn_prompt": knowledge.default_learn_prompt(),
        "default_analyze_prompt": knowledge.default_analyze_prompt(),
        "default_revise_prompt": knowledge.default_revise_prompt(),
        "default_article_prompt": knowledge.default_article_prompt(),
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
    db.add(KnowledgeTopic(name=_topic_name(db, body.name), updated_by_id=me.user_id))
    db.commit()
    return _knowledge_payload(db, me.user_id)


@router.patch("/knowledge/topics/{topic_id}")
def patch_topic(
    topic_id: int, body: TopicPatchBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    topic = _topic(db, topic_id)
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
    topic.updated_by_id = me.user_id
    db.commit()
    return _knowledge_payload(db, me.user_id)


@router.delete("/knowledge/topics/{topic_id}")
def delete_topic(topic_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    topic = _topic(db, topic_id)
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
    db.delete(topic)
    db.commit()
    return _knowledge_payload(db, me.user_id)
