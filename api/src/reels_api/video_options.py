"""A video's own settings from its "Thiết lập" tab, and the team's defaults from Cài đặt › Mặc định video.

Each video keeps its own copy, taken from the team's defaults when it is created (a clone takes its source's),
so changing a default never makes an existing video render differently. Every choice is a named preset; the
code defaults below render exactly the original template.
"""

from sqlalchemy.orm import Session as DbSession

from reels_render.options import (
    BOX_OPACITIES,
    CAPTIONS,
    MOTIONS,
    TEXT_COLORS,
    TEXT_SIZE_NAMES,
    TEXT_STYLES,
    TITLE_STYLES,
    TITLE_TEXT_STYLES,
    TRANSITIONS,
    ZOOMS,
    RenderOptions,
)
from reels_render.textbox import FRAME_HEIGHT, FRAME_WIDTH, is_hex
from reels_render.timeline import VOICE_TAIL

from . import config
from .models import AppSetting, Video
from .tts import MAX_SPEED, MAX_VOICE_ID_LENGTH, MIN_SPEED, SPEED_STEP, is_vieneu

DEFAULTS_KEY = "video_defaults"

DEFAULTS: dict = {
    # empty: the server's ELEVENLABS_VOICE_ID ("Adam" by default); "vieneu:<id>": a VieNeu voice (tts.py)
    "voice_id": "",
    "voice_speed": 1.0,  # tempo factor, MIN_SPEED to MAX_SPEED
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
    "box_opacity": "auto",  # the style's own; or solid, soft (88%), clear (70%), none (outlined)
    # The title scene's own look, like the five above; "same" follows the scenes (or title_style "yellow").
    "title_text_style": "same",
    "title_text_color": "auto",
    "title_box_color": "auto",
    "title_accent_color": "auto",
    "title_box_opacity": "auto",
    "captions": "off",
    # The text box's size, the content scenes' and the title's ("large": the original template).
    "text_size": "large",
    "title_text_size": "large",
    # The content scenes' text box centre in the frame, [x, y]; None: the template's place. A scene's own wins.
    "text_position": None,
    # "Nghỉ sau lời đọc": the pause after each scene's narration when its seconds follow it ("Tự khớp lời đọc").
    "voice_pause": VOICE_TAIL,
}
# The pauses offered, in seconds; the shortest is the one every video had before the choice existed.
VOICE_PAUSES = (VOICE_TAIL, 0.7, 1.0)
# What the text boxes are drawn with (previews, thumbnail, MP4); text_look keeps this order.
LOOK_FIELDS = (
    "text_style",
    "text_color",
    "title_style",
    "box_color",
    "accent_color",
    "box_opacity",
    "title_text_style",
    "title_text_color",
    "title_box_color",
    "title_accent_color",
    "title_box_opacity",
    "text_size",
    "title_text_size",
)
# Left out of the MP4 fingerprint while unused, so videos rendered before each existed stay current.
LATER_LOOK_FIELDS = LOOK_FIELDS[2:]
# Kept as columns of their own before these settings existed; the team defaults hold them too. "music_track_id" is
# the library track a new video starts with (routes_videos.apply_default_music copies it), None for no music.
VIDEO_FIELDS = {"voice_enabled": True, "music_volume": 25, "music_track_id": None}
# Colours: a named one or any "#RRGGBB", stored in capitals.
COLORS = {
    "text_color": TEXT_COLORS,
    "box_color": ("auto",),
    "accent_color": ("auto",),
    "title_text_color": TEXT_COLORS,
    "title_box_color": ("auto",),
    "title_accent_color": ("auto",),
}
CHOICES = {
    "transition": TRANSITIONS,
    "motion": MOTIONS,
    "zoom": tuple(ZOOMS),
    "text_style": TEXT_STYLES,
    "title_style": TITLE_STYLES,
    "box_opacity": BOX_OPACITIES,
    "title_text_style": TITLE_TEXT_STYLES,
    "title_box_opacity": BOX_OPACITIES,
    "captions": CAPTIONS,
    "text_size": TEXT_SIZE_NAMES,
    "title_text_size": TEXT_SIZE_NAMES,
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
    "box_opacity": "Độ trong của hộp",
    "title_style": "Kiểu tiêu đề",
    "title_text_style": "Kiểu hộp chữ tiêu đề",
    "title_text_color": "Màu chữ tiêu đề",
    "title_box_color": "Màu nền hộp tiêu đề",
    "title_accent_color": "Màu chữ đánh dấu tiêu đề",
    "title_box_opacity": "Độ trong của hộp tiêu đề",
    "captions": "Phụ đề theo giọng",
    "text_size": "Cỡ chữ",
    "title_text_size": "Cỡ chữ tiêu đề",
    "ducking": "Nhỏ nhạc khi có giọng",
    "voice_pause": "Nghỉ sau lời đọc",
    "voice_enabled": "Giọng đọc",
}


class OptionError(ValueError):
    """The message is shown to members."""


# The reading speed was three presets before the slider; what was saved then reads as the wider levels.
OLD_SPEEDS = {"slow": 0.8, "normal": 1.0, "fast": 1.2}
SPEED_ERROR = f"Tốc độ đọc phải từ {MIN_SPEED} đến {MAX_SPEED}"


def effective(video: Video) -> dict:
    values = DEFAULTS | (video.options or {})
    return values | {"voice_speed": OLD_SPEEDS.get(values["voice_speed"], values["voice_speed"])}


def clean_speed(value: object) -> float:
    """A reading speed from the slider, kept to its step; an old preset name still means its level."""
    if isinstance(value, str) and value in OLD_SPEEDS:
        return OLD_SPEEDS[value]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise OptionError(SPEED_ERROR)
    speed = round(round(value / SPEED_STEP) * SPEED_STEP, 2)
    if not MIN_SPEED <= speed <= MAX_SPEED:
        raise OptionError(SPEED_ERROR)
    return speed


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
        elif name == "text_position":
            value = clean_position(value)
        elif name == "voice_speed":
            value = clean_speed(value)
        elif name == "voice_pause":
            if isinstance(value, bool) or value not in VOICE_PAUSES:
                raise OptionError(
                    f"“{LABELS[name]}” phải là một trong {', '.join(f'{pause:g}' for pause in VOICE_PAUSES)} giây"
                )
            value = float(value)
        elif name == "voice_id":
            if not isinstance(value, str) or len(value) > MAX_VOICE_ID_LENGTH:
                raise OptionError("Mã giọng đọc không hợp lệ")
            value = value.strip()
            # VieNeu names its voices ("vieneu:Ngọc Lan"), so only its ids may hold single spaces.
            spaced = " ".join(value.split()) == value if is_vieneu(value) else len(value.split()) <= 1
            if not spaced or any(not char.isprintable() for char in value):
                raise OptionError("Mã giọng đọc không hợp lệ")
        elif name == "music_track_id" and (
            value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 1)
        ):
            raise OptionError("Bài nhạc mặc định không hợp lệ")
        cleaned[name] = value
    return cleaned


def clean_position(value: object) -> list[int] | None:
    """A text box centre [x, y] inside the frame, or None; the message is shown to members."""
    if value is None:
        return None
    if (
        not isinstance(value, list)
        or len(value) != 2
        or not all(isinstance(number, int) and not isinstance(number, bool) for number in value)
        or not (0 <= value[0] <= FRAME_WIDTH and 0 <= value[1] <= FRAME_HEIGHT)
    ):
        raise OptionError(f"Vị trí chữ phải là [x, y] trong khung {FRAME_WIDTH}×{FRAME_HEIGHT}")
    return [value[0], value[1]]


def voice_id(video: Video) -> str:
    return effective(video)["voice_id"] or config.voice_id()


def voice_speed(video: Video) -> float:
    return effective(video)["voice_speed"]


def voice_pause(video: Video) -> float:
    return effective(video)["voice_pause"]


def text_look(video: Video) -> tuple[str, ...]:
    """The values the text boxes are drawn with (LOOK_FIELDS): previews and the thumbnail change with them."""
    values = effective(video)
    return tuple(values[name] for name in LOOK_FIELDS)


# What a content scene's box is drawn with; the title's depends on every look field.
SCENE_LOOK_FIELDS = ("text_style", "text_color", "box_color", "accent_color", "box_opacity", "text_size")


def text_size(video: Video | None, is_title: bool) -> str:
    """The size a scene's text box is drawn at (reels_render.textbox.TEXT_SIZES)."""
    if video is None:
        return DEFAULTS["text_size"]
    return effective(video)["title_text_size" if is_title else "text_size"]


def preview_look(video: Video, is_title: bool) -> list[str]:
    """The look values a scene preview's address carries: none while they are the defaults (so previews cached
    before stay valid), and only what that scene is drawn with, so a title-only change leaves the scenes' alone."""
    values = effective(video)
    names = LOOK_FIELDS if is_title else SCENE_LOOK_FIELDS
    look = [values[name] for name in names]
    return [] if look == [DEFAULTS[name] for name in names] else look


def render_options(video: Video) -> RenderOptions:
    values = effective(video)
    return RenderOptions(
        transition=values["transition"],
        motion=values["motion"],
        zoom=values["zoom"],
        captions=values["captions"],
        voice_volume=values["voice_volume"] / 100,
        ducking=values["ducking"],
        backdrop=video.mode == "single",
        **{name: values[name] for name in LOOK_FIELDS},
    )


def look_signature(video: Video) -> dict | None:
    """What of these settings changes the MP4 apart from the narration (whose voice and speed are in each scene's
    narration signature); None while all are the defaults, so MP4s rendered before they existed stay current."""
    values = effective(video)
    # The pause after narration changes the seconds, which the fingerprint holds already.
    changed = {name: values[name] for name in DEFAULTS if name not in ("voice_id", "voice_speed", "voice_pause")}
    if changed == {name: DEFAULTS[name] for name in changed}:
        return None
    for name in (*LATER_LOOK_FIELDS, "text_position"):
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
