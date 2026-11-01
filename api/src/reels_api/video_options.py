"""A video's own settings from its "Thiết lập" tab, and the team's defaults from Cài đặt › Mặc định video.

Each video keeps its own copy, taken from the team's defaults when it is created (a clone takes its source's),
so changing a default never makes an existing video render differently. Every choice is a named preset; the
code defaults below render exactly the original template.
"""

from sqlalchemy.orm import Session as DbSession

from reels_render.options import (
    CAPTIONS,
    MOTIONS,
    TEXT_COLORS,
    TEXT_STYLES,
    TITLE_STYLES,
    TRANSITIONS,
    ZOOMS,
    RenderOptions,
)
from reels_render.textbox import is_hex

from . import config
from .models import AppSetting, Video
from .tts import SPEEDS

DEFAULTS_KEY = "video_defaults"
MAX_VOICE_ID_LENGTH = 64

DEFAULTS: dict = {
    "voice_id": "",  # empty: the server's ELEVENLABS_VOICE_ID ("Adam" by default)
    "voice_speed": "normal",
    "voice_volume": 100,  # percent
    "ducking": False,
    "transition": "fade",
    "motion": "zoom_in",
    "zoom": "medium",
    "text_style": "yellow",
    "text_color": "auto",  # the text box style's own colour
    "title_style": "same",  # the title scene is drawn like the other scenes
    "box_color": "auto",  # the style's own box (or outline, without a box); or "#RRGGBB"
    "accent_color": "auto",  # marked words keep a colour apart from the text; or "#RRGGBB"
    "captions": "off",
}
# Kept as columns of their own before these settings existed; the team defaults hold them too.
VIDEO_FIELDS = {"voice_enabled": True, "music_volume": 25}
# Colours: a named one or any "#RRGGBB", stored in capitals.
COLORS = {"text_color": TEXT_COLORS, "box_color": ("auto",), "accent_color": ("auto",)}
CHOICES = {
    "voice_speed": tuple(SPEEDS),
    "transition": TRANSITIONS,
    "motion": MOTIONS,
    "zoom": tuple(ZOOMS),
    "text_style": TEXT_STYLES,
    "title_style": TITLE_STYLES,
    "captions": CAPTIONS,
}


LABELS = {
    "voice_speed": "Tốc độ đọc",
    "transition": "Chuyển cảnh",
    "motion": "Chuyển động",
    "zoom": "Độ zoom",
    "text_style": "Kiểu hộp chữ",
    "text_color": "Màu chữ",
    "box_color": "Màu nền hộp",
    "accent_color": "Màu chữ đánh dấu",
    "title_style": "Kiểu tiêu đề",
    "captions": "Phụ đề theo giọng",
    "ducking": "Nhỏ nhạc khi có giọng",
    "voice_enabled": "Giọng đọc",
}


class OptionError(ValueError):
    """The message is shown to members."""


def effective(video: Video) -> dict:
    return DEFAULTS | (video.options or {})


def clean(values: dict, allow_video_fields: bool = False) -> dict:
    """Checked values for the fields given; unknown fields and values are refused."""
    known = set(DEFAULTS) | (set(VIDEO_FIELDS) if allow_video_fields else set())
    cleaned = {}
    for name, value in values.items():
        if name not in known:
            raise OptionError(f"Không có tuỳ chọn “{name}”")
        if name in COLORS:
            if not isinstance(value, str) or (value not in COLORS[name] and not is_hex(value)):
                raise OptionError(f"Giá trị không hợp lệ cho “{LABELS[name]}” (cần dạng #RRGGBB)")
            value = value.upper() if is_hex(value) else value
        elif name in CHOICES:
            if value not in CHOICES[name]:
                raise OptionError(f"Giá trị không hợp lệ cho “{LABELS[name]}”")
        elif name in ("voice_volume", "music_volume"):
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
                raise OptionError("Âm lượng phải từ 0 đến 100%")
        elif name in ("ducking", "voice_enabled"):
            if not isinstance(value, bool):
                raise OptionError(f"“{LABELS[name]}” chỉ nhận bật hoặc tắt")
        elif name == "voice_id":
            if not isinstance(value, str) or len(value) > MAX_VOICE_ID_LENGTH or len(value.split()) > 1:
                raise OptionError("Mã giọng đọc không hợp lệ")
            value = value.strip()
        cleaned[name] = value
    return cleaned


def voice_id(video: Video) -> str:
    return effective(video)["voice_id"] or config.voice_id()


def voice_speed(video: Video) -> str:
    return effective(video)["voice_speed"]


def text_look(video: Video) -> tuple[str, str, str, str, str]:
    """The text box style, text colour, title style, box colour and marked-word colour, which previews and the
    thumbnail are drawn with (frames.DEFAULT_LOOK)."""
    values = effective(video)
    return (
        values["text_style"],
        values["text_color"],
        values["title_style"],
        values["box_color"],
        values["accent_color"],
    )


def render_options(video: Video) -> RenderOptions:
    values = effective(video)
    return RenderOptions(
        transition=values["transition"],
        motion=values["motion"],
        zoom=values["zoom"],
        text_style=values["text_style"],
        text_color=values["text_color"],
        title_style=values["title_style"],
        box_color=values["box_color"],
        accent_color=values["accent_color"],
        captions=values["captions"],
        voice_volume=values["voice_volume"] / 100,
        ducking=values["ducking"],
    )


def look_signature(video: Video) -> dict | None:
    """What of these settings changes the MP4 apart from the narration (whose voice and speed are in each scene's
    narration signature); None while all are the defaults, so MP4s rendered before they existed stay current."""
    values = effective(video)
    changed = {name: values[name] for name in DEFAULTS if name not in ("voice_id", "voice_speed")}
    if changed == {name: DEFAULTS[name] for name in changed}:
        return None
    # Left out while unused, so videos with other presets, rendered before it existed, stay current.
    for name in ("title_style", "box_color", "accent_color"):
        if changed[name] == DEFAULTS[name]:
            del changed[name]
    return changed


def team_defaults(db: DbSession) -> dict:
    setting = db.get(AppSetting, DEFAULTS_KEY)
    stored = setting.value if setting and isinstance(setting.value, dict) else {}
    try:
        stored = clean(stored, allow_video_fields=True)
    except OptionError:
        stored = {}
    return VIDEO_FIELDS | DEFAULTS | stored


def save_team_defaults(db: DbSession, values: dict, user_id: int) -> dict:
    merged = team_defaults(db) | clean(values, allow_video_fields=True)
    setting = db.get(AppSetting, DEFAULTS_KEY)
    if setting is None:
        db.add(AppSetting(key=DEFAULTS_KEY, value=merged, updated_by_id=user_id))
    else:
        setting.value, setting.updated_by_id = merged, user_id
    return merged


def apply_team_defaults(db: DbSession, video: Video) -> None:
    defaults = team_defaults(db)
    video.voice_enabled, video.music_volume = defaults["voice_enabled"], defaults["music_volume"]
    video.options = {name: defaults[name] for name in DEFAULTS}
