"""Video state shared by the api routes and the worker: locking, status, payloads, thumbnail."""

import hashlib
import json
import re
import secrets
import unicodedata
from datetime import date, datetime
from pathlib import Path

from PIL import Image, ImageOps
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from reels_render.blur import blur_image
from reels_render.layers import HALF, HALF_HEIGHT_DEFAULT, HALF_X, half_height, half_y, is_half
from reels_render.textbox import FRAME_HEIGHT, FRAME_WIDTH
from reels_render.timeline import VOICE_TAIL, fit_seconds

from . import (
    affiliate,
    analytics,
    brands,
    facebook,
    fanpages,
    hashtags,
    knowledge,
    llm,
    metrics,
    pinned,
    plans,
    post_comments,
)
from .clips import ClipError, frame_at
from .errors import ApiError
from .frames import thumbnail_bytes
from .models import (
    ACTIVE_JOB_STATUSES,
    Fanpage,
    Job,
    KnowledgeTopic,
    PageQueueItem,
    PostMetrics,
    Publication,
    Scene,
    SceneLayer,
    SceneSound,
    TopicPlanItem,
    User,
    Video,
    VideoAffiliateProduct,
    VideoNote,
    VideoReference,
)
from .script_rules import MAX_SECONDS as MAX_SCENE_SECONDS
from .script_rules import MIN_SECONDS as MIN_SCENE_SECONDS
from .script_rules import Checks, Issue, SceneInput, check_script, plain_title, text_problem
from .sessions import now
from .storage import DirectoryStorage
from .tts import voice_signature
from .video_options import (
    effective,
    look_signature,
    preview_look,
    render_options,
    text_case,
    text_size,
    voice_id,
    voice_pause,
    voice_speed,
)

STATUS_LABELS = {
    "draft": "Nháp",
    "queued": "Chờ",
    "writing": "Đang viết",
    "imaging": "Đang tạo ảnh",
    "editing": "Đang sửa ảnh",
    "finding": "Đang tìm ảnh",
    "voicing": "Đang tạo giọng",
    "rendering": "Đang render",
    "publishing": "Đang đăng",
    "unpublishing": "Đang gỡ bài",
    "checking": "Đang kiểm tra bài",
    "done": "Xong",
    "failed": "Lỗi",
}
POST_FIELDS = {"caption": "Caption", "pinned_comment": "Bình luận ghim"}
# How a video is built (Video.mode): each scene over its own photo or clip, or one backdrop ("Video xuyên suốt").
MODES = {"slides": "Slide ảnh", "single": "Video xuyên suốt"}
# A topic group's "Kiểu video" (KnowledgeTopic.video_mode): one of MODES, or by turns on the Vietnam calendar day.
ALTERNATE = "alternate"
GROUP_VIDEO_MODES = {**MODES, ALTERNATE: "Xen kẽ theo ngày (ngày lẻ: xuyên suốt, ngày chẵn: slide)"}
PHOTO_LAYER_MISSING = "Cảnh có ảnh món nhưng chưa có ảnh: chọn ảnh cho cảnh hoặc tắt ảnh món"
HALF_PHOTO_MISSING = "Cảnh có ảnh chèn nhưng chưa có ảnh: chọn ảnh cho cảnh hoặc xoá ảnh chèn"
# A new photo layer ("Ảnh món"): medium, for the whole scene (the render stops it at the scene's end), on the left or
# the right of the frame by turns from one photo to the next, a little above the middle, coming up from below.
PHOTO_LAYER_X = (367, 713)
PHOTO_LAYER_Y = 835
PHOTO_LAYER_SECONDS = 60


def half_layer() -> SceneLayer:
    """An inset photo ("Ảnh chèn") at its default size, flush with the bottom edge (2026-11-12), for the whole scene,
    showing its scene's photo until it has its own: what turning "Ảnh chèn" on gives a scene, and what a "Video xuyên
    suốt" script gives a scene that names a dish (owner's choice, 2026-11-09: such a video uses only inset photos)."""
    return SceneLayer(
        position=1,
        kind="photo",
        text="",
        sticker="",
        start=0,
        seconds=PHOTO_LAYER_SECONDS,
        x=HALF_X,
        y=half_y(FRAME_HEIGHT, HALF_HEIGHT_DEFAULT),
        height=HALF_HEIGHT_DEFAULT,
        size="medium",
        style=HALF,
        animation="none",
    )


def photo_layer(photos_before: int) -> SceneLayer:
    """A new photo layer for a scene that comes after `photos_before` scenes with one."""
    return SceneLayer(
        position=1,
        kind="photo",
        text="",
        sticker="",
        start=0,
        seconds=PHOTO_LAYER_SECONDS,
        x=PHOTO_LAYER_X[photos_before % 2],
        y=PHOTO_LAYER_Y,
        size="medium",
        style="rounded",
        animation="slide_up",
    )


JOB_KINDS = {
    "script": "Viết kịch bản",
    "clone": "Nhân bản",
    "render": "Render",
    "publish": "Đăng Facebook",
    "unpublish": "Gỡ bài Facebook",
    "check": "Kiểm tra bài Facebook",
    "image": "Tạo ảnh AI",
    "image_edit": "Sửa ảnh",
    "image_marks": "Tìm chữ/logo trên ảnh",
    "photos": "Tự tìm ảnh",
    "voice": "Tạo giọng thật",
    "plan": "Tạo kế hoạch 30 ngày",
    "text_look": "AI gợi ý kiểu chữ",
    "learn": "Học từ video mẫu",
    "revise": "AI sửa theo góp ý",
    "rework": "Nâng cấp kịch bản và tư liệu",
    "article_caption": "Viết bài viết",
    "motion": "Cảnh động",
    "tiktok_publish": "Đăng TikTok",
}
# What a post can still be cancelled or deleted from; `cancelled` and `deleted` are final.
LIVE_POST_STATUSES = ("scheduled", "published")
OPEN_POST_STATUSES = ("pending", *LIVE_POST_STATUSES)
# A line of on-screen text read aloud already pauses after one of these.
PAUSE_ENDS = (".", "!", "?", "…", ":", ",", ";")
# "2." or "2)" before a scene's text: read as "hai chấm". "2.5 lít" is a quantity, not a number in a list.
LIST_NUMBER = re.compile(r"^\s*\d+[.)](?!\d)\s*")


def new_key(video_id: int, name: str, extension: str) -> str:
    """Server-generated, unique per version, so browsers never show a cached old file."""
    return f"videos/{video_id}/{name}-{secrets.token_hex(6)}.{extension}"


def drop_original(scene: Scene) -> str | None:
    """The photo kept from before "Sửa ảnh" (image_edit.py), forgotten when the scene gets another photo or a clip or
    loses its photo: the caller deletes the returned file with the ones it replaces."""
    key, scene.image_original_key = scene.image_original_key, None
    return key


def blur_of(scene: Scene) -> list:
    """The boxes "Làm mờ vùng" blurs on the scene's clip, while the scene still shows the clip they were drawn on."""
    blur = scene.video_blur or {}
    return (blur.get("boxes") or []) if scene.video_key and blur.get("key") == scene.video_key else []


def marks_of(scene: Scene) -> list | None:
    """The boxes "Tìm chữ/logo tự động" found, while the scene still shows the photo they were found on."""
    marks = scene.image_marks or {}
    return marks.get("boxes") if scene.image_key and marks.get("key") == scene.image_key else None


def video_not_found() -> ApiError:
    return ApiError(404, "video_not_found", "Không tìm thấy video (có thể đã bị xóa)")


def scene_deleted() -> ApiError:
    return ApiError(404, "scene_deleted", "Cảnh này đã bị xóa")


def active_job(db: DbSession, video_id: int) -> Job | None:
    return db.scalar(select(Job).where(Job.video_id == video_id, Job.status.in_(ACTIVE_JOB_STATUSES)))


def lock_video(db: DbSession, video_id: int) -> Video:
    """Row-lock the video: every change and every new job for one video happens one after another."""
    video = db.scalar(
        select(Video).where(Video.id == video_id).with_for_update().execution_options(populate_existing=True)
    )
    if video is None:
        raise video_not_found()
    return video


def ensure_unlocked(db: DbSession, video: Video) -> None:
    job = active_job(db, video.id)
    if job is None:
        return
    if job.kind == "render":
        raise ApiError(409, "video_locked", "Video đang render, chưa lưu")
    if job.kind == "publish":
        raise ApiError(409, "video_locked", "Video đang đăng lên Facebook, chưa lưu")
    if job.kind == "unpublish":
        raise ApiError(409, "video_locked", "Video đang gỡ bài trên Facebook, chưa lưu")
    if job.kind == "check":
        raise ApiError(409, "video_locked", "Video đang kiểm tra bài trên Facebook, chưa lưu")
    if job.kind == "tiktok_publish":
        raise ApiError(409, "video_locked", "Video đang đăng lên TikTok, chưa lưu")
    if job.kind == "voice":
        raise ApiError(409, "video_locked", "Video đang tạo giọng đọc, chưa lưu")
    if job.kind == "revise":
        raise ApiError(409, "video_locked", "AI đang sửa video theo góp ý, chưa lưu")
    raise ApiError(409, "video_locked", "Video đang viết kịch bản, chưa lưu")


def lock_scene(db: DbSession, scene_id: int) -> tuple[Video, Scene]:
    """Lock the scene's video, then re-read the scene: a teammate may have deleted it meanwhile."""
    video_id = db.scalar(select(Scene.video_id).where(Scene.id == scene_id))
    if video_id is None:
        raise scene_deleted()
    video = lock_video(db, video_id)
    scene = db.scalar(select(Scene).where(Scene.id == scene_id).execution_options(populate_existing=True))
    if scene is None:
        raise scene_deleted()
    return video, scene


def split_scenes(db: DbSession, video: Video) -> tuple[Scene | None, list[Scene]]:
    rows = db.scalars(
        select(Scene)
        .where(Scene.video_id == video.id)
        .order_by(Scene.position, Scene.id)
        .execution_options(populate_existing=True)
    ).all()
    title = next((scene for scene in rows if scene.is_title), None)
    return title, [scene for scene in rows if not scene.is_title]


def screen_speech(scene: Scene) -> str:
    """The on-screen text as it is read when a scene has no voice text: the title whole; a content scene without its
    list number, each line its own sentence, so the dish and its benefit do not run together."""
    if scene.is_title:
        return plain_title(scene.text)
    lines = [plain_title(line) for line in LIST_NUMBER.sub("", scene.text.replace("*", "")).splitlines()]
    return " ".join(line if line.endswith(PAUSE_ENDS) else f"{line}." for line in lines if line)


def scene_name(scene: Scene) -> str:
    """What a content scene is about: the first line of its on-screen text, without its list number or marks
    ("Rau muống" of "Rau muống / Khoảng 3 tuần cắt ngọn")."""
    if scene.is_title:
        return ""
    lines = LIST_NUMBER.sub("", scene.text.replace("*", "")).strip().splitlines()
    return plain_title(lines[0]).rstrip(".,:;!?…").strip() if lines else ""


def pause_after_name(voice: str, name: str) -> str:
    """A voice text that opens with the scene's name gets a comma after it when nothing marks the pause, so the
    narration says "Rau muống, ngâm hạt…" instead of running the name into the sentence."""
    if not name or not voice.casefold().startswith(name.casefold()):
        return voice
    rest = voice[len(name) :]
    if not rest or not rest[0].isspace() or rest.lstrip()[:1] in (*PAUSE_ENDS, "-", "–", "—"):
        return voice
    # The case is kept: the voice reads "Ngâm" and "ngâm" alike, and a name such as "Phú Quốc" must stay as written.
    return f"{voice[: len(name)]}, {rest.lstrip()}"


def spoken(video: Video, scene: Scene) -> str:
    """The narration this scene gets in the next render: its voice text (with a pause after the scene's name), else
    its on-screen text; empty when it has neither or the video's narration is off."""
    if not video.voice_enabled:
        return ""
    if scene.voice_text.strip():
        return pause_after_name(scene.voice_text, scene_name(scene))
    return screen_speech(scene)


def group_video_mode(group: KnowledgeTopic, on: date | None = None) -> str:
    """The mode the group's new videos take on `on` (today in Vietnam by default): its switch, or for "Xen kẽ theo
    ngày" a backdrop video ("single") on odd calendar days and slides on even ones. A group never set: slides."""
    mode = group.video_mode or "slides"
    if mode != ALTERNATE:
        return mode
    day = on or plans.today()
    return "single" if day.day % 2 else "slides"


def resolve_video_mode(chosen: str | None, group: KnowledgeTopic, on: date | None = None) -> str:
    """A new video's mode, decided in one place for every way a video is made (videos.start_video): the one asked for
    this video, else its group's switch."""
    return chosen or group_video_mode(group, on)


def is_backdrop(video: Video) -> bool:
    """ "Video xuyên suốt": the title scene's photo or clip runs under every scene."""
    return video.mode == "single"


def auto_seconds(voice_seconds: float, pause: float = VOICE_TAIL) -> float:
    """A scene's seconds when they follow its narration: the narration, the lead-in before it and the pause after
    it (the video's "Nghỉ sau lời đọc", voice_pause), in tenths, within the 1–10 seconds a scene may be set to. A
    longer narration still lengthens the scene at render (fit_seconds)."""
    return min(MAX_SCENE_SECONDS, max(MIN_SCENE_SECONDS, fit_seconds(0, voice_seconds, pause)))


def follow_narration(video: Video, scenes: list[Scene]) -> None:
    """Every scene whose seconds follow its narration ("Tự khớp lời đọc") takes the seconds of the narration it
    has, after the video's pause changed."""
    for scene in scenes:
        made = made_voice_seconds(video, scene)
        if scene.seconds_auto and made is not None:
            scene.seconds = auto_seconds(made, voice_pause(video))


def made_voice_seconds(video: Video, scene: Scene) -> float | None:
    """Length of the stored narration when it was made from the current voice text, voice and model."""
    text = spoken(video, scene)
    if not text or not scene.voice_key or scene.voice_signature != voice_signature(text, *_voice(video)):
        return None
    return scene.voice_seconds


def scene_marks(video: Video, title: Scene | None, scenes: list[Scene]) -> list[dict]:
    """Where each scene starts and ends in a render of the current scenes, in seconds: each lasts its fitted seconds,
    as in the render's timeline, whose crossfades straddle the boundaries without changing them."""
    marks, start = [], 0.0
    for index, scene in enumerate([title, *scenes] if title else scenes):
        end = start + fit_seconds(scene.seconds, made_voice_seconds(video, scene))
        label = "Tiêu đề" if scene.is_title else f"Cảnh {index if title else index + 1}"
        marks.append({"label": label, "start": round(start, 2), "end": round(end, 2)})
        start = end
    return marks


def _voice(video: Video) -> tuple[str, str]:
    return voice_id(video), voice_speed(video)


def text_position(video: Video, scene: Scene) -> list[int] | None:
    """Where the scene's text box goes (its centre): its own place, else the video's place for its kind (the title's
    `title_text_position`, the content scenes' `text_position`), else None (where the template puts it). The title's
    video-wide place keeps it centred across, as a place dragged on it does."""
    if scene.text_x is not None and scene.text_y is not None:
        return [scene.text_x, scene.text_y]
    if scene.is_title:
        position = effective(video)["title_text_position"]
        return [FRAME_WIDTH // 2, position[1]] if position else None
    return effective(video)["text_position"] or opposite_the_inset(video, scene)


def opposite_the_inset(video: Video, scene: Scene) -> list[int] | None:
    """Where a content scene's text goes when nobody placed it (its own, the video's) and the scene has an inset photo:
    the side facing away from it, so it does not sit on the photo. An inset flush with the top edge leaves the text at
    the template's place (the bottom); one in the middle or at the bottom sends it to the top. Never moved once a
    member chose a place: moving the inset does not touch a place that is set."""
    inset = next((layer for layer in scene.layers if is_half_layer(layer)), None)
    if inset is None or not is_backdrop(video):
        return None
    if inset.y - half_height(inset.height) // 2 <= 0:
        return None
    return [FRAME_WIDTH // 2, 0]


LAYER_FIELDS = ("kind", "text", "sticker", "start", "seconds", "x", "y", "size", "style", "animation", "height")


def layer_fields(layer: SceneLayer) -> dict:
    """A layer as the render script and the studio read it (reels_render.layers.Layer); a photo layer's photo (its
    scene's own, or a half-frame photo's own) is added by the render job."""
    return {field: getattr(layer, field) for field in LAYER_FIELDS}


def is_half_layer(layer: SceneLayer) -> bool:
    """ "Ảnh chèn nửa khung" (reels_render.layers.HALF): a photo of its own across half the frame."""
    return is_half(layer.kind, layer.style)


def layer_photo_key(layer: SceneLayer) -> str | None:
    """The photo a photo layer shows: a half-frame photo's own, else its scene's (as "Ảnh món" always does): the one a
    "Video xuyên suốt" script gives a scene that names a dish has none of its own until a member picks one."""
    if layer.kind != "photo":
        return None
    return (layer.image_key if is_half_layer(layer) else None) or layer.scene.image_key


def _own_photo(layer: SceneLayer) -> dict:
    return {"image_key": layer.image_key} if layer.image_key else {}


def drawn_layers(video: Video, scene: Scene) -> list[SceneLayer]:
    """The layers the render lays over the scene: photo layers ("Ảnh món") only over a backdrop; on a slide video
    they are kept for switching back, and not drawn; so are half-frame photos (2026-11-09: only over a backdrop)."""
    return [layer for layer in scene.layers if layer.kind != "photo" or is_backdrop(video)]


def layer_payload(layer: SceneLayer, case: str = "upper") -> dict:
    # Its picture changes only with what is drawn, not with where or when it shows; a photo layer's with its photo, a
    # text layer's with the letter case it is drawn in (the scenes' "Dạng chữ"; capitals keep the earlier addresses).
    photo = layer_photo_key(layer)
    kept = [case] if layer.kind == "text" and case != "upper" else []
    if is_half_layer(layer):
        # An inset photo's size changes its picture; its place does not.
        kept += [str(layer.height)]
    look = _version(layer.kind, layer.text, layer.sticker, layer.size, layer.style, *([photo] if photo else []), *kept)
    # A half-frame photo says whether its photo is its own or its scene's, so the card shows where to choose it.
    own = {"own_image": bool(layer.image_key)} if is_half_layer(layer) else {}
    return {"id": layer.id, **layer_fields(layer), **own, "image_url": f"/api/layers/{layer.id}/image.png?v={look}"}


def sound_fields(sound: SceneSound) -> dict:
    """A sound effect as the render script reads it (reels_render.sounds.SceneSound)."""
    return {"sound": sound.sound, "start": sound.start, "volume": sound.volume}


def sound_payload(sound: SceneSound) -> dict:
    return {"id": sound.id, **sound_fields(sound), "url": f"/api/sounds/library/{sound.sound}.mp3"}


def render_signature(video: Video, title: Scene | None, scenes: list[Scene]) -> str:
    """Fingerprint of what changes the MP4 (text, seconds, photo, order, music, volume, narration); captions and
    keywords are left out."""
    every = ([title] if title else []) + scenes
    # A clip joins its scene's part only when there is one, so MP4s rendered before clips existed stay current.
    # So does a clip speed other than 1×, and a moved text box, so a box in the template's place keeps the fingerprint from before.
    parts = [
        [
            scene.text,
            scene.seconds,
            scene.image_key,
            *([scene.video_key, scene.video_start] if scene.video_key else []),
            *([["video_speed", scene.video_speed]] if scene.video_speed not in (None, 1) else []),
            *([["video_loop", True]] if scene.video_key and scene.video_loop else []),
            # The clip's own sound and its words join only when heard, so MP4s rendered before them stay current.
            *([["video_sound", scene.words or []]] if scene.video_key and scene.video_sound else []),
            *([["text_position", *position]] if (position := text_position(video, scene)) else []),
            # The studio's effects join only when set, so MP4s rendered before they existed stay current.
            *([["transition", scene.transition]] if scene.transition else []),
            *([["color", scene.color]] if scene.color else []),
            *(
                # A half-frame photo's own photo joins too; other layers have none, so their fingerprint stays.
                [["layers", [layer_fields(layer) | _own_photo(layer) for layer in layers]]]
                if (layers := drawn_layers(video, scene))
                else []
            ),
            *([["sounds", [sound_fields(sound) for sound in scene.sounds]]] if scene.sounds else []),
            *([["music_level", scene.music_level]] if scene.music_level else []),
            # Blurred boxes on the clip join only when there are some, so earlier MP4s stay current.
            *([["video_blur", blurred]] if (blurred := blur_of(scene)) else []),
        ]
        for scene in every
    ]
    # Without music or narration the fingerprint keeps the format MP4s rendered before those existed were
    # stored with, so they are not flagged as outdated.
    # The song's start joins only when moved, so MP4s rendered before it existed stay current.
    music = [video.music_key, video.music_volume, *([["music_start", video.music_start]] if video.music_start else [])]
    data = [parts, music] if video.music_key else parts
    # Joins only for a backdrop video, so slide videos rendered before modes existed stay current.
    if is_backdrop(video):
        data = [data, ["mode", video.mode]]
    voices = [
        voice_signature(spoken(video, scene), *_voice(video)) if spoken(video, scene) else None for scene in every
    ]
    if any(voices):
        data = [data, voices]
    look = look_signature(video)
    if look is not None:
        data = [data, look]
    # The channel logo joins only while it is laid on, so MP4s rendered before logos existed stay current.
    if (logo := brands.logo_signature(video)) is not None:
        data = [data, logo]
    return hashlib.sha256(json.dumps(data, ensure_ascii=False).encode()).hexdigest()


def scene_still(storage: DirectoryStorage, scene: Scene) -> Path | Image.Image | None:
    """What the scene's first frame is drawn from: the clip's frame at its start time, or the photo."""
    if scene.video_key:
        if not storage.exists(scene.video_key):
            return None
        try:
            frame = frame_at(storage.path(scene.video_key), scene.video_start)
        except ClipError:
            return None
        if blurred := blur_of(scene):
            # Framed like the render, then blurred where the render blurs, so every preview shows the boxes.
            fitted = ImageOps.fit(frame.convert("RGB"), (FRAME_WIDTH, FRAME_HEIGHT), Image.Resampling.BICUBIC)
            return blur_image(fitted, tuple(tuple(box) for box in blurred))
        return frame
    if scene.image_key and storage.exists(scene.image_key):
        return storage.path(scene.image_key)
    return None


def refresh_thumbnail(db: DbSession, storage: DirectoryStorage, video: Video, title: Scene | None) -> None:
    """The thumbnail is the title scene's preview; it follows every change of that photo, clip or text."""
    old = video.thumbnail_key
    still = scene_still(storage, title) if title is not None else None
    if still is None:
        video.thumbnail_key = None
    else:
        key = new_key(video.id, "thumb", "jpg")
        storage.save_bytes(key, thumbnail_bytes(still, title.text, render_options(video), text_position(video, title)))
        video.thumbnail_key = key
    if old and old != video.thumbnail_key:
        storage.delete(old)


def scene_inputs(video: Video, title: Scene | None, scenes: list[Scene]) -> tuple[SceneInput | None, list[SceneInput]]:
    backdrop = is_backdrop(video)

    def to_input(scene: Scene) -> SceneInput:
        clip_seconds = scene.video_seconds - scene.video_start if scene.video_key and scene.video_seconds else None
        # Over a backdrop a content scene needs no picture of its own, and the backdrop clip loops, never ends.
        own_picture = backdrop and not scene.is_title
        return SceneInput(
            scene.id,
            scene.is_title,
            scene.text,
            scene.seconds,
            own_picture or bool(scene.image_key or scene.video_key),
            scene.voice_text if spoken(video, scene) else "",
            made_voice_seconds(video, scene),
            None if backdrop else clip_seconds,
            own_picture or bool(scene.keywords or scene.keywords_en),
            scene.video_speed,
            text_size(video, scene.is_title),
            text_case(video, scene.is_title),
            photo_credit(scene),
            bool(scene.video_key and scene.video_loop),
        )

    return (to_input(title) if title else None), [to_input(scene) for scene in scenes]


def run_checks(db: DbSession, video: Video, title: Scene | None, scenes: list[Scene]) -> Checks:
    title_input, scene_input = scene_inputs(video, title, scenes)
    posts = {name: getattr(video, name) for name in POST_FIELDS}
    # The pinned comment is checked as it reads now, its variables filled from these scenes (pinned.py).
    source = pinned.scenes_source(title, scenes, pinned.product_names(db, video.id), video.topic)
    posts["pinned_comment"] = pinned.render(video.pinned_comment, source)
    checks = check_script(title_input, scene_input, posts, knowledge.banned_words(db, video))
    checks.warnings.extend(pinned.validate(video.pinned_comment, source, video.extra_comments))
    for scene in scenes:
        # A photo layer without a photo of its own shows its scene's: a clip, or no picture, leaves it nothing.
        drawn = drawn_layers(video, scene)
        if any(layer.kind == "photo" and not layer_photo_key(layer) for layer in drawn):
            missing = HALF_PHOTO_MISSING if any(is_half_layer(layer) for layer in drawn) else PHOTO_LAYER_MISSING
            checks.blocking.append(Issue(missing, scene.id, "image"))
    return checks


def _last_failed(db: DbSession, video_id: int) -> Job | None:
    """The latest finished job when it failed; cancelled jobs leave the video as it was before them."""
    job = db.scalar(
        select(Job).where(Job.video_id == video_id, Job.status.in_(("done", "failed"))).order_by(Job.id.desc()).limit(1)
    )
    return job if job is not None and job.status == "failed" else None


def queue_position(db: DbSession, job: Job) -> int:
    return db.scalar(select(func.count()).select_from(Job).where(Job.status == "queued", Job.id <= job.id))


# A video with its MP4 and no job, by where its posts stand: "Xong" said nothing about posting (2026-11-12).
POST_STAGE_LABELS = {"ready": "Chờ đăng", "scheduled": "Đã lên lịch", "posted": "Đã đăng"}


def post_stage(extras: dict) -> str:
    """Out anywhere (`posted_on`), else a Facebook post set for later, else waiting to be posted."""
    if extras.get("posted_on"):
        return "posted"
    post = extras.get("post")
    return "scheduled" if post and post.get("state") == "scheduled" else "ready"


def _with_post_stage(status: dict, extras: dict) -> dict:
    """The status of a "done" video named by its posting, with `post_stage` (None while not done)."""
    if status["status"] != "done":
        return {**status, "post_stage": None}
    stage = post_stage(extras)
    return {**status, "status_label": POST_STAGE_LABELS[stage], "post_stage": stage}


def _status(db: DbSession, video: Video, job: Job | None, failed: Job | None) -> dict:
    if job is not None and job.status == "queued":
        code, label = "queued", f"Chờ thứ {queue_position(db, job)}"
    elif job is not None:
        code = {
            "render": "rendering",
            "publish": "publishing",
            "tiktok_publish": "publishing",
            "unpublish": "unpublishing",
            "check": "checking",
            "image": "imaging",
            "image_edit": "editing",
            "image_marks": "editing",
            "photos": "finding",
            "voice": "voicing",
        }.get(job.kind, "writing")
        label = STATUS_LABELS[code]
    elif video.mp4_key:
        code, label = "done", STATUS_LABELS["done"]
    elif failed is not None:
        code, label = "failed", STATUS_LABELS["failed"]
    else:
        code, label = "draft", STATUS_LABELS["draft"]
    return {"status": code, "status_label": label}


def _job_payload(job: Job | None) -> dict | None:
    if job is None:
        return None
    return {
        "id": job.id,
        "kind": job.kind,
        # The one scene an image job makes a photo for; None for every other job.
        "scene_id": job.scene_id,
        "image_provider": job.image_provider,
        "status": job.status,
        # A render or motion job waiting for a render machine ("ready") or being rendered on one ("taken").
        "node_stage": job.node_stage,
        "error": job.error,
        "error_detail": job.error_detail,
        "created_by": job.created_by.name if job.created_by else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


def publications_of(db: DbSession, video_id: int) -> list[Publication]:
    """Every post of the video, newest first, cancelled and deleted ones included."""
    return list(
        db.scalars(
            select(Publication)
            .where(Publication.video_id == video_id, Publication.platform == "facebook")
            .order_by(Publication.id.desc())
        )
    )


def publication_of(db: DbSession, video_id: int) -> Publication | None:
    """The newest post still on its way or on the platform."""
    return next((post for post in publications_of(db, video_id) if post.status in OPEN_POST_STATUSES), None)


def pending_publication(db: DbSession, video_id: int) -> Publication | None:
    """The post the publish job works on; at most one, by the partial unique index."""
    return next((post for post in publications_of(db, video_id) if post.status == "pending"), None)


def tiktok_posts_of(db: DbSession, video_id: int) -> list[Publication]:
    """The video's TikTok posts, made by hand in TikTok's app or sent through TikTok's API, newest first."""
    return list(
        db.scalars(
            select(Publication)
            .where(Publication.video_id == video_id, Publication.platform == "tiktok")
            .order_by(Publication.id.desc())
        )
    )


# Platforms a video is posted to only by hand, its post recorded with its link (routes_manual_posts.py).
MANUAL_PLATFORMS = {"youtube": "YouTube Shorts", "instagram": "Instagram Reels"}


# Every platform a video's MP4 may be posted to, in the order the app lists them.
POST_PLATFORMS = ("facebook", "tiktok", "youtube", "instagram")


def manual_posts_of(db: DbSession, video_id: int) -> list[Publication]:
    """The video's posts on YouTube Shorts and Instagram Reels, recorded by hand, newest first."""
    return list(
        db.scalars(
            select(Publication)
            .where(Publication.video_id == video_id, Publication.platform.in_(MANUAL_PLATFORMS))
            .order_by(Publication.id.desc())
        )
    )


def manual_post_payload(post: Publication) -> dict:
    return {
        "id": post.id,
        "platform": post.platform,
        "platform_label": MANUAL_PLATFORMS[post.platform],
        "url": post.post_url,
        "at": live_at(post).isoformat(),
        "created_by": post.created_by.name,
        "created_by_id": post.created_by_id,
    }


def tiktok_post_payload(post: Publication) -> dict:
    return {
        "id": post.id,
        "url": post.post_url,
        "account": post.affiliate_account.name if post.affiliate_account else None,
        "at": live_at(post).isoformat(),
        "created_by": post.created_by.name,
        "created_by_id": post.created_by_id,
        # pending | published | cancelled; one recorded by hand is published.
        "status": post.status,
        # "draft" | "direct" for a post sent through TikTok's API, None for one posted by hand.
        "mode": post.publish_mode,
        "privacy_level": post.privacy_level,
    }


def _video_link(db: DbSession, video: Video | None) -> dict | None:
    if video is None:
        return None
    title, _ = split_scenes(db, video)
    return {"id": video.id, "title": video_name(video, title), "platform": video.platform}


def published_publication(db: DbSession, video_id: int) -> Publication | None:
    return next((post for post in publications_of(db, video_id) if is_published(post)), None)


def is_published(post: Publication) -> bool:
    # Facebook publishes a scheduled reel by itself, so nothing here changes when the time comes.
    return post.status == "published" or (
        post.status == "scheduled" and post.scheduled_at is not None and post.scheduled_at <= now()
    )


def live_at(post: Publication) -> datetime:
    # The publish job stamps published_at when the upload ends, which for a scheduled reel is before it goes live.
    # A post cancelled before its upload has neither.
    return post.scheduled_at or post.published_at or post.created_at


REFERENCE_MODE_LABELS = {
    "quick": "Nhanh",
    "twostep": "Hai bước tự động",
    "review": "Duyệt phân tích trước",
    "reuse": "Dùng mẫu đã học",
    "footage": "Edit từ footage",
}


def reference_frames(sample: VideoReference) -> list[dict]:
    return [
        {"second": frame["second"], "note": frame.get("note", ""), "url": f"/api/references/{sample.id}/frames/{n}.jpg"}
        for n, frame in enumerate(sample.frames, start=1)
    ]


def reference_payload(db: DbSession, video: Video) -> dict | None:
    """The sample video a video is learned from ("Từ video mẫu"), for its card on the video page."""
    if not video.reference_mode:
        return None
    sample = db.get(VideoReference, video.reference_id) if video.reference_id else None
    analyzed = bool(sample and sample.analysis.strip())
    return {
        "id": sample.id if sample else None,
        "created_by_id": sample.created_by_id if sample else None,  # only they delete it
        "mode": video.reference_mode,
        "mode_label": REFERENCE_MODE_LABELS.get(video.reference_mode, video.reference_mode),
        "source_name": sample.source_name if sample else None,
        "source_url": sample.source_url if sample else None,
        "seconds": sample.seconds if sample else None,
        "transcript": sample.transcript if sample else "",
        "analysis": sample.analysis if sample else "",
        "frames": reference_frames(sample) if sample else [],
        # The way "review": the analysis is written and waits for a member before the script.
        "awaiting_review": video.reference_mode == "review" and analyzed and not video.has_script,
    }


def thumbnail_url(video: Video) -> str | None:
    """The title-scene frame of the last render, versioned so a new render is not served from the cache."""
    return f"/api/videos/{video.id}/thumbnail.jpg?v={_version(video.thumbnail_key)}" if video.thumbnail_key else None


def publication_payload(post: Publication | None, by_page: dict[int | None, analytics.Median]) -> dict | None:
    """`by_page`: analytics.medians, read once per request."""
    if post is None:
        return None
    published = is_published(post)
    return {
        "id": post.id,
        "status": "published" if published else post.status,
        "fanpage": post.fanpage.name if post.fanpage else None,
        "scheduled_at": post.scheduled_at.isoformat() if post.scheduled_at else None,
        "at": live_at(post).isoformat(),
        "url": facebook.reel_url(post.remote_id) if published and post.remote_id else None,
        "created_by": post.created_by.name,
        "created_by_id": post.created_by_id,
        "fanpage_owner_id": post.fanpage.owner_id if post.fanpage else None,
        "closed_at": post.closed_at.isoformat() if post.closed_at else None,
        "closed_by": post.closed_by.name if post.closed_by else None,
        "metrics": metrics.payload(post, by_page),
        "comment": post_comments.payload(post),
    }


def posted_fanpage_ids(video: Video, posts: list[Publication]) -> list[int]:
    """The Pages that hold the current MP4, so the same file is not posted to them again."""
    return [
        post.fanpage_id
        for post in posts
        if post.status in LIVE_POST_STATUSES and post.remote_mp4_key == video.mp4_key and post.fanpage_id is not None
    ]


def _version(*parts: object) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()[:12]


def motion_payload(scene: Scene) -> dict | None:
    """A scene's motion while its clip is the one the motion made, or while that clip is being made; else None
    (another photo or clip took its place, or its job failed)."""
    motion = scene.motion
    if not motion or not (motion.get("pending") or (motion.get("clip_key") and motion["clip_key"] == scene.video_key)):
        return None
    return {"html": motion["html"], "seconds": motion["seconds"], "pending": bool(motion.get("pending"))}


def photo_credit(scene: Scene) -> dict | None:
    """The credit the scene's shown photo asks for, without its url; None for no photo, a clip, or a photo that needs
    none. Kept only while the photo it was noted for is still the scene's (any other photo ends it)."""
    credit = scene.image_credit
    if not (scene.image_key and not scene.video_key and isinstance(credit, dict)):
        return None
    if credit.get("url") != scene.image_source:
        return None
    return {name: value for name, value in credit.items() if name != "url"}


def scene_payload(video: Video, scene: Scene, checks: Checks) -> dict:
    image = f"/api/scenes/{scene.id}"
    size, case = text_size(video, scene.is_title), text_case(video, scene.is_title)
    voice_seconds = made_voice_seconds(video, scene)
    style = preview_look(video, scene.is_title)
    position = text_position(video, scene)
    if position:
        style = [*style, "text_position", *position]
    still = scene.video_key or scene.image_key
    return {
        "id": scene.id,
        "video_id": scene.video_id,
        "is_title": scene.is_title,
        "text": scene.text,
        "seconds": scene.seconds,
        "seconds_auto": scene.seconds_auto,
        "keywords": scene.keywords,
        "keywords_en": scene.keywords_en,
        "image_prompt": scene.image_prompt,
        "voice_text": scene.voice_text,
        "spoken_text": spoken(video, scene),
        # Known once a render has made the narration for the current text; None until then.
        "voice_seconds": voice_seconds,
        "voice_url": f"{image}/voice.mp3?v={_version(scene.voice_key)}" if voice_seconds is not None else None,
        "fitted_seconds": fit_seconds(scene.seconds, voice_seconds),
        "has_image": bool(scene.image_key),
        # An AI photo: the card offers "Tạo lại ảnh AI" instead of "Tạo ảnh AI".
        "image_ai": bool(scene.image_key) and (scene.image_source or "").startswith("ai:"),
        # Changed by "Sửa ảnh" since the photo came in: the card offers "Khôi phục ảnh gốc".
        "image_edited": bool(scene.image_key and scene.image_original_key),
        # "Tìm chữ/logo tự động": the boxes found on the photo now shown ([] when none); None until looked for.
        "image_marks": marks_of(scene),
        # Picked by "Tự tìm ảnh" and not yet changed by a member: the card says "Tự chọn, kiểm tra lại".
        "image_auto": bool(scene.image_key) and scene.image_auto,
        # A stock photo whose licence asks for credit (Wikimedia CC BY...): the line to put in the post; None if not.
        "image_credit": photo_credit(scene),
        "image_error": scene.image_error,
        "image_url": f"{image}/image?v={_version(scene.image_key)}" if scene.image_key else None,
        "video": {
            "url": f"{image}/video?v={_version(scene.video_key)}",
            # "Làm mờ vùng": boxes blurred for the whole scene, fractions of the 1080x1920 frame.
            "blur": blur_of(scene),
            "seconds": scene.video_seconds,
            "start": scene.video_start,
            "speed": scene.video_speed,
            "loop": scene.video_loop,
            # "Tiếng gốc": the clip's own sound is heard in the render; `words` say whether captions follow it.
            "sound": scene.video_sound,
            "words": len(scene.words or []),
        }
        if scene.video_key
        else None,
        "preview_url": (
            f"{image}/preview.jpg?v={_version(scene.video_key, scene.video_start, blur_of(scene), scene.text, *style)}"
            if scene.video_key
            else f"{image}/preview.jpg?v={_version(scene.image_key, scene.text, *style)}"
            if scene.image_key
            else None
        ),
        # Where a member dragged this scene's box; None: the video's place (content scenes) or the template's.
        "text_position": [scene.text_x, scene.text_y] if scene.text_x is not None else None,
        "placed_at": position,  # where it goes after all: its own place, the video's, or None (the template's)
        # The drag is drawn from the frame without text and the exact box image the renderer overlays.
        "frame_url": f"{image}/frame.jpg?v={_version(still, scene.video_start, blur_of(scene))}" if still else None,
        "textbox_url": (
            f"{image}/textbox.png?v={_version(scene.text, *preview_look(video, scene.is_title))}"
            if scene.text.strip() and text_problem(scene.text, scene.is_title, size, case) is None
            else None
        ),
        "text_problem": text_problem(scene.text, scene.is_title, size, case),
        "transition": scene.transition,
        "color": scene.color,
        "layers": [layer_payload(layer, text_case(video, False)) for layer in scene.layers],
        "sounds": [sound_payload(sound) for sound in scene.sounds],
        "music_level": scene.music_level,
        # A "Cảnh động" (motion.py): its markup and seconds while the scene shows its clip or it is being made.
        "motion": motion_payload(scene),
        "blocking": [issue.message for issue in checks.blocking if issue.scene_id == scene.id],
        "warnings": [issue.message for issue in checks.warnings if issue.scene_id == scene.id],
        # The same, each with the field it is about, so the page can offer the fix beside it ("Lặp clip").
        "issues": [
            {"message": issue.message, "field": issue.field, "level": level}
            for level, found in (("blocking", checks.blocking), ("warning", checks.warnings))
            for issue in found
            if issue.scene_id == scene.id
        ],
    }


def _labels(video: Video, title: Scene | None, scenes: list[Scene], job: Job | None, failed: Job | None) -> dict:
    return {
        "mp4_outdated": bool(video.mp4_key) and video.rendered_signature != render_signature(video, title, scenes),
        # A failed re-render keeps the old MP4 and the "Xong" status, with this extra label.
        "rerender_failed": job is None and bool(video.mp4_key) and failed is not None and failed.kind == "render",
    }


def assistant_writer(app: str) -> str:
    """Who wrote a script through MCP, named by the assistant (ChatGPT, Claude, Muse...) when it is known."""
    return f"{app or 'Trợ lý AI'} của thành viên qua kết nối MCP (gói đăng ký, không tốn phí AI của nhóm)"


def made_via(video: Video) -> str:
    """How the video's script came: "assistant" (a member's own Claude through MCP), "sample" ("Từ video mẫu"),
    "clone" ("Nhân bản", a TikTok version included), "manual" ("Tự viết") or "ai" (the team's AI service)."""
    if video.written_via == "assistant":
        return "assistant"
    if video.reference_id is not None or video.reference_mode:
        return "sample"
    if video.clone_source:
        return "clone"
    if video.hand_written:
        return "manual"
    return "ai"


def content_types(db: DbSession) -> list[str]:
    """The "Loại nội dung" the team's videos use: one per type whatever its case (the first spelling met wins), in
    Vietnamese order. Members pick from them, and the AI that writes a script is told them."""
    seen: dict[str, str] = {}
    for kind in db.scalars(select(Video.content_type).where(Video.content_type != "").order_by(Video.id)):
        seen.setdefault(kind.casefold(), kind)
    return sorted(seen.values(), key=lambda kind: unicodedata.normalize("NFD", kind).casefold())


def _script_job(db: DbSession, video: Video) -> Job | None:
    """The last finished job that wrote the video's script; None for one written by hand or by an assistant."""
    return db.scalar(
        select(Job)
        .where(Job.video_id == video.id, Job.kind.in_(("script", "clone", "learn")), Job.status == "done")
        .order_by(Job.id.desc())
        .limit(1)
    )


def script_writer(db: DbSession, video: Video) -> str | None:
    """Who wrote the video's script, so reviewers know what they read: a member's own Claude through MCP, or the
    provider and model of the job that wrote it."""
    if video.written_via == "assistant":
        return assistant_writer(video.assistant_app)
    job = _script_job(db, video)
    return llm.label(job.llm_provider, job.llm_model) if job else None


def script_at(db: DbSession, video: Video) -> str | None:
    """When the script was written, for the progress line: its last job's end, or the video's making when no job
    wrote it (by hand, or sent by an assistant over MCP)."""
    if not video.has_script:
        return None
    job = _script_job(db, video) if video.written_via != "assistant" else None
    return (job.finished_at if job and job.finished_at else video.created_at).isoformat()


def title_of(video: Video, title: Scene | None) -> str:
    return plain_title(title.text) if title is not None and title.text.strip() else ""


def video_name(video: Video, title: Scene | None) -> str:
    """How lists name a video: its own name ("… (copy)"), else its title scene's text, else its topic."""
    return video.name or title_of(video, title) or video.topic


def notes_payload(db: DbSession, video: Video, title: Scene | None, scenes: list[Scene]) -> list[dict]:
    """The studio's notes in the order of the video, each with the scene playing at its second now."""
    every = ([title] if title else []) + scenes
    ends, end = [], 0.0
    for scene in every:
        end += fit_seconds(scene.seconds, made_voice_seconds(video, scene))
        ends.append(end)
    rows = db.execute(
        select(VideoNote, User.name)
        .join(User, User.id == VideoNote.created_by_id)
        .where(VideoNote.video_id == video.id)
        .order_by(VideoNote.at, VideoNote.id)
    ).all()
    payload = []
    for note, author in rows:
        index = next((number for number, value in enumerate(ends) if note.at < value), len(every) - 1)
        payload.append(
            {
                "id": note.id,
                "at": note.at,
                "scene_id": every[index].id if every else None,
                "text": note.text,
                "status": note.status,
                "reply": note.reply,
                "created_by": author,
                "created_by_id": note.created_by_id,  # only they delete it
                "created_at": note.created_at.isoformat(),
            }
        )
    return payload


def video_payload(db: DbSession, video: Video) -> dict:
    title, scenes = split_scenes(db, video)
    job = active_job(db, video.id)
    failed = _last_failed(db, video.id)
    checks = run_checks(db, video, title, scenes) if video.has_script else Checks()
    topic = knowledge.topic_of(db, video)
    posts = publications_of(db, video.id)
    # One small query, and only for a video that has posts: this payload answers every save and poll of the editor.
    by_page = analytics.medians(db) if posts else {}
    extras = list_extras(db, [video])[video.id]
    pinned_source = pinned.scenes_source(title, scenes, pinned.product_names(db, video.id), video.topic)
    payload = {
        "id": video.id,
        "topic": video.topic,
        "title": title_of(video, title),
        "name": video.name,
        "has_script": video.has_script,
        "hand_written": video.hand_written,
        "title_options": video.title_options,
        "caption": video.caption,
        "hashtags": video.hashtags,
        # What a post sends: the caption, then the hashtags it does not already hold.
        "post_text": hashtags.post_text(video.caption, video.hashtags),
        # The caption for TikTok: the caption text without its Facebook hashtags, then the group's TikTok set.
        "tiktok_caption": hashtags.tiktok_caption(video.caption, topic.name if topic else None),
        "affiliates": video.affiliates,
        "platform": video.platform,
        "variant_of": _video_link(db, db.get(Video, video.variant_of_id)) if video.variant_of_id else None,
        "variants": [
            _video_link(db, variant)
            for variant in db.scalars(select(Video).where(Video.variant_of_id == video.id).order_by(Video.id))
        ],
        "tiktok_posts": [tiktok_post_payload(post) for post in tiktok_posts_of(db, video.id)],
        # YouTube Shorts and Instagram Reels, posted by hand from the same MP4.
        "manual_posts": [manual_post_payload(post) for post in manual_posts_of(db, video.id)],
        "suggest": {
            "state": "pending" if video.suggest_requested_at else ("failed" if video.suggest_error else "idle"),
            "error": video.suggest_error,
            "at": video.suggested_at.isoformat() if video.suggested_at else None,
        },
        # The products whose links go in the comment under the video's reels (post_comments.py).
        "affiliate_product_ids": [product.id for product in affiliate.products_of(db, video.id)],
        # The template a member edits, and what it reads as now: "Copy ghim" and the Page's comment use the latter.
        "pinned_comment": video.pinned_comment,
        "pinned_comment_text": pinned.render(video.pinned_comment, pinned_source),
        # The attached products' names, for `{products}` in the web's live preview (web/src/lib/pinned.ts).
        "pinned_products": pinned_source.product_names,
        "extra_comments": video.extra_comments,
        "self_review": video.self_review,
        "music_suggestions": video.music_suggestions,
        "created_by": video.created_by.name,
        # Only its maker deletes it, or its scenes (ownership.py).
        "created_by_id": video.created_by_id,
        "created_at": video.created_at.isoformat(),
        **_with_post_stage(_status(db, video, job, failed), extras),
        **_labels(video, title, scenes, job, failed),
        "locked": job is not None,
        "queue": extras.get("queue"),
        "suggested_post_at": extras.get("suggested_post_at"),
        "active_job": _job_payload(job),
        "failed_job": _job_payload(failed) if job is None else None,
        "mp4": {
            "url": f"/api/videos/{video.id}/video.mp4?v={_version(video.mp4_key)}",
            "download_url": f"/api/videos/{video.id}/video.mp4?download=1&v={_version(video.mp4_key)}",
            "seconds": video.mp4_seconds,
            "render_seconds": video.render_seconds,
            "rendered_at": video.rendered_at.isoformat() if video.rendered_at else None,
            # Automatic QC of this MP4 (qc.py); None for an MP4 rendered before QC existed.
            "qc": video.qc,
        }
        if video.mp4_key
        else None,
        "thumbnail_url": thumbnail_url(video),
        **brands.payload_of(db, video),
        "music": {
            "url": f"/api/videos/{video.id}/music.mp3?v={_version(video.music_key)}",
            "name": video.music_name,
        }
        if video.music_key
        else None,
        "music_volume": video.music_volume,
        "music_start": video.music_start,
        "ai_effects": video.ai_effects,
        # The "Mẫu dựng" it wears ({id, name, source: video|group|member}), None for none.
        "edit_template": (
            {name: video.edit_template.get(name) for name in ("id", "name", "source")}
            if isinstance(video.edit_template, dict)
            else None
        ),
        "notes": notes_payload(db, video, title, scenes),
        "voice_enabled": video.voice_enabled,
        "mode": video.mode,
        "made_via": made_via(video),
        "assistant_app": video.assistant_app,
        "content_type": video.content_type,
        "options": effective(video),
        "publication": publication_payload(publication_of(db, video.id), by_page),
        "publications": [publication_payload(post, by_page) for post in posts],
        "posted_fanpage_ids": posted_fanpage_ids(video, posts),
        # Where it is out, as on the list: the page's row of platform icons.
        "posted_on": extras["posted_on"],
        "posted_links": extras["posted_links"],
        "fanpages": [
            {
                "id": page.id,
                "name": page.name,
                "owner": page.owner.name if page.owner else None,
                # Whose it is: the page lists the viewer's own Pages first (brief part B2).
                "owner_id": page.owner_id,
                # The group it posts: the publish dialog starts on the viewer's own Page of the video's group (B3).
                "knowledge_topic_id": page.knowledge_topic_id,
                # The TikTok account picked for the Page on /fanpages: its videos' Đăng TikTok card opens with it.
                "tiktok_account_id": page.tiktok_account_id,
                "error": page.check_error,
            }
            for page in fanpages.in_use(db)
        ],
        "knowledge_topic": topic.name if topic else None,
        "knowledge_topic_id": video.knowledge_topic_id,
        # Who made the group: its maker may send a teammate's video back to a group of the video's maker.
        "knowledge_topic_owner_id": topic.created_by_id if topic else None,
        "plan_idea": _plan_idea(db, video),
        "script_by": script_writer(db, video) if video.has_script else None,
        # When the script was written, for the progress line under the title.
        "script_at": script_at(db, video),
        "clone_of": {
            "title": video.clone_source["title"],
            "request": video.clone_source["request"],
        }
        if video.clone_source
        else None,
        "reference": reference_payload(db, video),
        "title_scene": scene_payload(video, title, checks) if title else None,
        "scenes": [scene_payload(video, scene, checks) for scene in scenes],
        "video_blocking": [issue.message for issue in checks.blocking if issue.scene_id is None],
        "video_warnings": [
            {"field": issue.field, "message": issue.message} for issue in checks.warnings if issue.scene_id is None
        ],
        "can_render": video.has_script and not checks.blocking and job is None,
    }
    return payload


def _plan_idea(db: DbSession, video: Video) -> dict | None:
    """The 30-day plan idea the video was made from, to compare against while editing, and when the plan means the
    video to go out ("Đăng" starts with that time)."""
    idea = db.scalar(select(TopicPlanItem).where(TopicPlanItem.video_id == video.id))
    if idea is None:
        return None
    post_at = plans.suggested_post_at(db.get(KnowledgeTopic, idea.knowledge_topic_id), idea)
    return {
        "id": idea.id,
        "knowledge_topic_id": idea.knowledge_topic_id,
        "day": idea.day,
        "topic": idea.topic,
        "pain_group": idea.pain_group,
        "pain": idea.pain,
        "hook": idea.hook,
        "suggested_post_at": post_at.isoformat() if post_at else None,
    }


def made_from(db: DbSession) -> tuple[set[int], set[int]]:
    """The videos that have a TikTok version, and those a Facebook clone was made from ("Nhân bản", a version for
    another Page), for the list's suggestions on "Bài đăng"; read once per list."""
    tiktok = set(db.scalars(select(Video.variant_of_id).where(Video.variant_of_id.is_not(None))))
    sources = db.scalars(
        select(Video.clone_source["video_id"].as_integer()).where(
            Video.clone_source.is_not(None), Video.platform == "facebook"
        )
    )
    return tiktok, {source for source in sources if source is not None}


def list_extras(db: DbSession, videos: list[Video]) -> dict[int, dict]:
    """What a video's card on /videos shows besides itself, by video id: its topic group, its 30-day plan day, and
    its Facebook posts: whether one is out or set for later, its views and how its best post did at 48 hours.
    Everything is read in a few queries for the whole list, and the Page medians once."""
    ids = [video.id for video in videos]
    if not ids:
        return {}
    queued = {
        item.video_id: {"id": item.id, "fanpage": page, "error": item.error}
        for item, page in db.execute(
            select(PageQueueItem, Fanpage.name).join(Fanpage).where(PageQueueItem.video_id.in_(ids))
        )
    }
    topics = {topic.id: topic for topic in db.scalars(select(KnowledgeTopic))}
    groups = {topic.id: topic.name for topic in topics.values()}
    ideas = list(db.scalars(select(TopicPlanItem).where(TopicPlanItem.video_id.in_(ids))))
    days = {idea.video_id: idea.day for idea in ideas}
    suggested = {}
    for idea in ideas:
        topic = topics.get(idea.knowledge_topic_id)
        at = plans.suggested_post_at(topic, idea) if topic else None
        suggested[idea.video_id] = at.isoformat() if at else None
    posts = db.execute(
        select(Publication, Fanpage.name)
        .outerjoin(Fanpage, Fanpage.id == Publication.fanpage_id)
        .where(
            Publication.video_id.in_(ids),
            Publication.platform == "facebook",
            Publication.status.in_(LIVE_POST_STATUSES),
        )
    ).all()
    readings: dict[tuple[int, str], PostMetrics] = {}
    if posts:
        for row in db.scalars(select(PostMetrics).where(PostMetrics.publication_id.in_([p.id for p, _ in posts]))):
            readings[(row.publication_id, row.window)] = row
    by_page = analytics.medians(db) if posts else {}
    on_tiktok = set(
        db.scalars(select(Publication.video_id).where(Publication.video_id.in_(ids), Publication.platform == "tiktok"))
    )
    products = dict(
        db.execute(
            select(VideoAffiliateProduct.video_id, func.count())
            .where(VideoAffiliateProduct.video_id.in_(ids))
            .group_by(VideoAffiliateProduct.video_id)
        ).all()
    )
    # Where each video is out: Facebook from its live posts, the others from any post recorded or sent there.
    elsewhere: dict[int, set[str]] = {}
    # The link of each platform's newest post, for the icon to open it.
    links: dict[int, dict[str, str]] = {}
    for video_id, platform, url in db.execute(
        select(Publication.video_id, Publication.platform, Publication.post_url)
        .where(
            Publication.video_id.in_(ids),
            Publication.platform != "facebook",
            Publication.status.in_(LIVE_POST_STATUSES),
        )
        .order_by(Publication.id)
    ):
        elsewhere.setdefault(video_id, set()).add(platform)
        if url:
            links.setdefault(video_id, {})[platform] = url
    by_video: dict[int, list[tuple[Publication, str]]] = {}
    for post, page in posts:
        by_video.setdefault(post.video_id, []).append((post, page or ""))
    extras = {}
    for video in videos:
        live = [(post, page) for post, page in by_video.get(video.id, []) if is_published(post)]
        later = sorted(
            ((post, page) for post, page in by_video.get(video.id, []) if not is_published(post)),
            key=lambda item: item[0].scheduled_at or item[0].created_at,
        )
        extras[video.id] = {
            "knowledge_topic": groups.get(video.knowledge_topic_id),
            "plan_day": days.get(video.id),
            "suggested_post_at": suggested.get(video.id),
            "queue": queued.get(video.id),
            "post": _post_summary(live, later, readings, by_page),
            # A TikTok post of this video (its TikTok version's or its own MP4's): the card says "Đã đăng" for it.
            "tiktok_posted": video.id in on_tiktok,
            # The products attached to it (their links go in the pinned comment): the list marks a product video.
            "product_count": products.get(video.id, 0),
            # Every platform the video is out on, in a fixed order, for the card's "Đã đăng" line.
            "posted_on": [
                platform
                for platform in POST_PLATFORMS
                if (platform == "facebook" and live) or platform in elsewhere.get(video.id, set())
            ],
            "posted_links": _posted_links(live, links.get(video.id, {})),
        }
    return extras


def _posted_links(live: list[tuple[Publication, str]], others: dict[str, str]) -> dict[str, str]:
    """Where to open each platform's post: the newest live Facebook reel, and the recorded link of the others."""
    links = dict(others)
    reels = [post for post, _ in live if post.remote_id]
    if reels:
        newest = max(reels, key=lambda post: post.published_at or post.created_at)
        links["facebook"] = facebook.reel_url(newest.remote_id)
    return {platform: links[platform] for platform in POST_PLATFORMS if platform in links}


def _post_summary(
    live: list[tuple[Publication, str]],
    later: list[tuple[Publication, str]],
    readings: dict[tuple[int, str], PostMetrics],
    by_page: dict,
) -> dict | None:
    """The card's post line. Views are each live post's `latest` reading added up; the 48-hour line is of the post
    with the most views, and only its `48h` reading, so posts are compared at the same age."""
    if not live and not later:
        return None
    if not live:
        post, page = later[0]
        return {
            "state": "scheduled",
            "fanpage": page,
            "fanpages": sorted({name for _, name in later if name}),
            "pages": len(later),
            "at": live_at(post).isoformat(),
            "views": None,
            "views_48h": None,
            "shares": None,
            "share_rate": None,
            "share_met": None,
            "times_median": None,
        }

    def latest_views(item: tuple[Publication, str]) -> int:
        row = readings.get((item[0].id, "latest"))
        return row.views if row is not None and row.views is not None else -1

    counted = [latest_views(item) for item in live if latest_views(item) >= 0]
    post, page = max(live, key=latest_views)
    mark = readings.get((post.id, "48h"))
    views_48h, shares_48h = (mark.views, mark.shares) if mark is not None else (None, None)
    analysis = analytics.of_post(post, views_48h, shares_48h, by_page)
    return {
        "state": "posted",
        "fanpage": page,
        # Every Page it is out on or set for, for the list's Fanpage filter.
        "fanpages": sorted({name for _, name in [*live, *later] if name}),
        "pages": len(live),
        "at": live_at(post).isoformat(),
        "views": sum(counted) if counted else None,
        "views_48h": views_48h,
        "shares": shares_48h,
        "share_rate": analysis["share_rate"],
        "share_met": analysis["share_rate"] >= analytics.SHARE_GOAL if analysis["share_rate"] is not None else None,
        "times_median": analysis["times_median"],
    }


def list_payload(
    db: DbSession, video: Video, family: tuple[set[int], set[int]] = (set(), set()), extras: dict | None = None
) -> dict:
    """`family`: made_from, and `extras`: this video's list_extras, both read once per list."""
    extras = extras or {
        "knowledge_topic": None,
        "plan_day": None,
        "suggested_post_at": None,
        "queue": None,
        "post": None,
        "tiktok_posted": False,
        "posted_on": [],
        "posted_links": {},
        "product_count": 0,
    }
    title, scenes = split_scenes(db, video)
    job = active_job(db, video.id)
    failed = _last_failed(db, video.id)
    return {
        "id": video.id,
        "topic": video.topic,
        "title": title_of(video, title),
        "name": video.name,
        "platform": video.platform,
        # The video a TikTok version was made from: the list shows the version on its source's card.
        "variant_of_id": video.variant_of_id,
        "has_tiktok_version": video.id in family[0],
        "cloned": video.id in family[1],
        "created_by": video.created_by.name,
        # Whose it is: the list starts on the viewer's own ("Của tôi").
        "created_by_id": video.created_by_id,
        "created_at": video.created_at.isoformat(),
        # Its kind on the list: how the script came, how it is built, its products and its "Loại nội dung".
        "made_via": made_via(video),
        "assistant_app": video.assistant_app,
        "mode": video.mode,
        "content_type": video.content_type,
        **_labels(video, title, scenes, job, failed),
        "thumbnail_url": thumbnail_url(video),
        **extras,
        **_with_post_stage(_status(db, video, job, failed), extras),
    }
