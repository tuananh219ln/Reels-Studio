"""A video's own settings from its "Thiết lập" tab, and the team's defaults from Cài đặt › Mặc định video.

Each video keeps its own copy, taken from the team's defaults when it is created (a clone takes its source's),
so changing a default never makes an existing video render differently. Every choice is a named preset; the
code defaults below render exactly the original template.
"""

from sqlalchemy.orm import Session as DbSession

from reels_render.markup import TEXT_CASES
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
from reels_render.pc_text import PC_STYLES
from reels_render.textbox import FRAME_HEIGHT, FRAME_WIDTH, is_hex
from reels_render.timeline import VOICE_TAIL

from . import config
from .models import KnowledgeTopic, Scene, UserVideoDefaults, Video
from .tts import MAX_SPEED, MAX_VOICE_ID_LENGTH, MIN_SPEED, SPEED_STEP, is_vieneu

TITLE_SFX = ("reveal_ting", "manual", "off")

DEFAULTS_KEY = "video_defaults"  # the team's defaults before 2026-11-09 (migration 0067): kept, never read

DEFAULTS: dict = {
    # empty: the server's ELEVENLABS_VOICE_ID ("Adam" by default); "vieneu:<id>": a VieNeu voice, "gemini:<name>" a
    # Gemini one, "google:<name>" a Google Cloud one (tts.py)
    "voice_id": "",
    "voice_speed": 1.0,  # tempo factor, MIN_SPEED to MAX_SPEED
    "voice_volume": 100,  # percent
    "ducking": False,
    # "Nền tối mờ sau chữ": a black band (45% at its darkest) behind the content scenes' text (reels_render.textbox).
    "text_shade": False,
    "transition": "fade",
    "motion": "zoom_in",
    "zoom": "medium",
    "text_style": "yellow",
    "text_color": "auto",  # the text box style's own colour
    "title_style": "same",  # the title scene is drawn like the other scenes
    "box_color": "auto",  # the style's own box (or outline, without a box); or "#RRGGBB"
    "accent_color": "auto",  # marked words keep a colour apart from the text; or "#RRGGBB"
    "box_opacity": "auto",  # the style's own; or solid, soft (88%), clear (70%), faint (45%), none (outlined)
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
    # "Dạng chữ", the content scenes' (and their text layers') and the title's: "upper" (the original template) or
    # "keep", drawn as typed.
    "text_case": "upper",
    "title_text_case": "upper",
    # The content scenes' text box centre in the frame, [x, y]; None: the template's place. A scene's own wins.
    "text_position": None,
    # The title scene's text box centre, [x, y]; None: the template's place (the middle of the frame). The title stays
    # centred across, so only y counts; a place dragged on the title itself wins.
    "title_text_position": None,
    # "Nghỉ sau lời đọc": the pause after each scene's narration when its seconds follow it ("Tự khớp lời đọc").
    "voice_pause": VOICE_TAIL,
    # The title motion's sounds: "reveal_ting" a soft ding as each slot pops in (title_motion.sync_title_sfx), "manual"
    # the member's own sounds are left alone, "off" the title scene has none.
    "title_sfx": "reveal_ting",
    # "Thời gian hiện chữ" (PC Shopee only, see is_pc_shopee): the content scenes' text fades out after this many
    # seconds; None: it stays the whole scene, as it always did. A scene's own `text_hold_sec` wins.
    "text_hold_sec": None,
    # The look of PC Shopee's drawn text, a key of reels_render.pc_text.PC_STYLES ("Cộng dồn" captions for now).
    "pc_style": "neon_game",
    # PC Shopee's compact text (reels_render.tiers): "three_tier" draws the title as a small line, a main line, a sub line
    # and an optional label, "two_tier" a content scene's text as a numbered main line and a sub line; "box" is the text
    # box every other group has. `pc_title_style` is the title's look (a key of PC_STYLES).
    "title_layout": "box",
    "scene_text_layout": "box",
    "pc_title_style": "brand_navy",
}
# The topic group the "Ẩn chữ sau X giây" setting is for. Its new videos start with PC_SHOPEE_TEXT_HOLD; every other
# group keeps None, so nothing changes for them (docs/decisions/2026-11-27-text-hold.md).
PC_SHOPEE_GROUP = "PC Shopee"
PC_SHOPEE_TEXT_HOLD = 2.5
TEXT_HOLD_MIN, TEXT_HOLD_MAX, TEXT_HOLD_STEP = 1.0, 6.0, 0.5
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
    "text_case",
    "title_text_case",
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
    "text_case": TEXT_CASES,
    "title_text_case": TEXT_CASES,
    "title_sfx": TITLE_SFX,
    "pc_style": PC_STYLES,
    "title_layout": ("box", "three_tier"),
    "scene_text_layout": ("box", "two_tier"),
    "pc_title_style": PC_STYLES,
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
    "text_case": "Dạng chữ",
    "title_text_case": "Dạng chữ tiêu đề",
    "text_hold_sec": "Thời gian hiện chữ",
    "pc_style": "Kiểu chữ PC Shopee",
    "title_layout": "Bố cục tiêu đề",
    "scene_text_layout": "Bố cục chữ cảnh",
    "pc_title_style": "Kiểu chữ tiêu đề PC Shopee",
    "ducking": "Nhỏ nhạc khi có giọng",
    "text_shade": "Nền tối mờ sau chữ",
    "voice_pause": "Nghỉ sau lời đọc",
    "title_sfx": "Âm thanh tiêu đề động",
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


def clean_voice_id(value: object) -> str:
    """A voice id as typed or picked: an ElevenLabs id, vieneu:<name>, gemini:<name> or google:<name>; "" for none."""
    if not isinstance(value, str) or len(value) > MAX_VOICE_ID_LENGTH:
        raise OptionError("Mã giọng đọc không hợp lệ")
    value = value.strip()
    # VieNeu names its voices ("vieneu:Ngọc Lan"), so only its ids may hold single spaces.
    spaced = " ".join(value.split()) == value if is_vieneu(value) else len(value.split()) <= 1
    if not spaced or any(not char.isprintable() for char in value):
        raise OptionError("Mã giọng đọc không hợp lệ")
    return value


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
        elif name in ("ducking", "voice_enabled", "text_shade"):
            if not isinstance(value, bool):
                raise OptionError(f"“{LABELS[name]}” chỉ nhận bật hoặc tắt")
        elif name in ("text_position", "title_text_position"):
            value = clean_position(value)
        elif name == "text_hold_sec":
            value = clean_text_hold(value)
        elif name == "voice_speed":
            value = clean_speed(value)
        elif name == "voice_pause":
            if isinstance(value, bool) or value not in VOICE_PAUSES:
                raise OptionError(
                    f"“{LABELS[name]}” phải là một trong {', '.join(f'{pause:g}' for pause in VOICE_PAUSES)} giây"
                )
            value = float(value)
        elif name == "voice_id":
            value = clean_voice_id(value)
        elif name == "music_track_id" and (
            value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 1)
        ):
            raise OptionError("Bài nhạc mặc định không hợp lệ")
        cleaned[name] = value
    return cleaned


def choices() -> dict:
    """What each setting accepts, from the same lists `clean` checks against (the assistant's connection reads it)."""
    return (
        {name: list(values) for name, values in CHOICES.items()}
        | {name: [*values, "#RRGGBB"] for name, values in COLORS.items()}
        | {
            "voice_id": "ElevenLabs voice id, vieneu:<id>, gemini:<name> or google:<name>; empty: the team's server voice",
            "voice_speed": {"min": MIN_SPEED, "max": MAX_SPEED, "step": SPEED_STEP},
            "voice_volume": {"min": 0, "max": 100},
            "voice_pause": list(VOICE_PAUSES),
            "ducking": [True, False],
            "text_shade": [True, False],
            "text_hold_sec": {
                "min": TEXT_HOLD_MIN,
                "max": TEXT_HOLD_MAX,
                "step": TEXT_HOLD_STEP,
                "null": "whole scene",
            },
            "text_position": {"width": FRAME_WIDTH, "height": FRAME_HEIGHT},
            "title_text_position": {"width": FRAME_WIDTH, "height": FRAME_HEIGHT},
        }
    )


def clean_text_hold(value: object) -> float | None:
    """Seconds the text stays (1 to 6 in steps of 0.5), or None for the whole scene; the message is shown to members."""
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not TEXT_HOLD_MIN <= value <= TEXT_HOLD_MAX
        or (value - TEXT_HOLD_MIN) % TEXT_HOLD_STEP
    ):
        raise OptionError(
            f"“Thời gian hiện chữ” phải từ {TEXT_HOLD_MIN:g} đến {TEXT_HOLD_MAX:g} giây, mỗi bước 0,5 giây"
        )
    return float(value)


def is_pc_shopee(group: KnowledgeTopic | None) -> bool:
    return group is not None and group.name.strip().casefold() == PC_SHOPEE_GROUP.casefold()


def text_hold(video: Video, scene: Scene) -> float | None:
    """Seconds a scene's text stays before it fades out: its own, else the video's, else (compact text with phrase or word
    captions) PC_SHOPEE_TEXT_HOLD; None for the whole scene and always for the title scene. (The renderer also keeps the last scene's text: reels_render.graph.hold_seconds.)"""
    if scene.is_title:
        return None
    values = effective(video)
    hold = scene.text_hold_sec if scene.text_hold_sec is not None else values["text_hold_sec"]
    if hold is None and values["scene_text_layout"] == "two_tier" and values["captions"] in ("phrase", "word"):
        # The compact text and the captions are never on screen together (the spec's one layer of text): with no hold
        # chosen, the text goes after PC_SHOPEE_TEXT_HOLD and the captions start then (reels_render.captions.after_hold).
        return PC_SHOPEE_TEXT_HOLD
    return hold


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


def scene_voice(video: Video, scene: Scene) -> str:
    """The voice a scene reads with: its own when it has one, else the video's. Every place that makes, signs or
    checks a scene's narration goes through here, or a scene with its own voice would look stale on every render
    and be paid for again."""
    return scene.voice_id or voice_id(video)


def voice_speed(video: Video) -> float:
    return effective(video)["voice_speed"]


def voice_pause(video: Video) -> float:
    return effective(video)["voice_pause"]


def text_look(video: Video) -> tuple[str, ...]:
    """The values the text boxes are drawn with (LOOK_FIELDS, and PC Shopee's title layout and look): previews and the
    thumbnail change with them."""
    values = effective(video)
    return tuple(values[name] for name in (*LOOK_FIELDS, "title_layout", "pc_title_style"))


# What a content scene's box is drawn with; the title's depends on every look field.
SCENE_LOOK_FIELDS = (
    "text_style",
    "text_color",
    "box_color",
    "accent_color",
    "box_opacity",
    "text_size",
    "text_case",
    "text_shade",
)
# The scenes' letter case is not the title's, which has its own.
TITLE_LOOK_FIELDS = tuple(name for name in LOOK_FIELDS if name != "text_case")


def text_size(video: Video | None, is_title: bool) -> str:
    """The size a scene's text box is drawn at (reels_render.textbox.TEXT_SIZES)."""
    if video is None:
        return DEFAULTS["text_size"]
    return effective(video)["title_text_size" if is_title else "text_size"]


def text_case(video: Video | None, is_title: bool) -> str:
    """The letter case a scene's text is drawn in (reels_render.markup.TEXT_CASES); its text layers take the scenes'."""
    if video is None:
        return DEFAULTS["text_case"]
    return effective(video)["title_text_case" if is_title else "text_case"]


def preview_look(video: Video, is_title: bool) -> list[str]:
    """The look values a scene preview's address carries: none while they are the defaults (so previews cached
    before stay valid), and only what that scene is drawn with, so a title-only change leaves the scenes' alone."""
    values = effective(video)
    names = TITLE_LOOK_FIELDS if is_title else SCENE_LOOK_FIELDS
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
        text_shade=values["text_shade"],
        pc_style=values["pc_style"],
        pc_title_style=values["pc_title_style"],
        title_layout=values["title_layout"],
        scene_text_layout=values["scene_text_layout"],
        backdrop=video.mode == "single",
        **{name: values[name] for name in LOOK_FIELDS},
    )


def look_signature(video: Video) -> dict | None:
    """What of these settings changes the MP4 apart from the narration (whose voice and speed are in each scene's
    narration signature); None while all are the defaults, so MP4s rendered before they existed stay current."""
    values = effective(video)
    # The pause after narration changes the seconds, which the fingerprint holds already.
    # The title's sounds are in the scenes' sounds, which the fingerprint holds already.
    # The text's hold joins each scene's part in videos.render_signature, where a scene's own value counts too.
    skipped = ("voice_id", "voice_speed", "voice_pause", "title_sfx", "text_hold_sec")
    changed = {name: values[name] for name in DEFAULTS if name not in skipped}
    if changed == {name: DEFAULTS[name] for name in changed}:
        return None
    for name in (
        *LATER_LOOK_FIELDS,
        "text_position",
        "title_text_position",
        "text_shade",
        "pc_style",
        "title_layout",
        "scene_text_layout",
        "pc_title_style",
    ):
        if changed[name] == DEFAULTS[name]:
            del changed[name]
    return changed


def built_in_defaults() -> dict:
    """What a member who never saved their own defaults starts new videos with: the app's own."""
    return VIDEO_FIELDS | DEFAULTS


def member_defaults(db: DbSession, user_id: int) -> dict:
    """What a member's new videos start with: their own defaults, or the app's built-in ones while they have none. A
    value their copy lacks (a setting added since they saved) or no longer accepts (a preset since removed, or a
    value written by newer code) is the built-in one; the rest of their copy still counts. There is no team level
    (part 3 of docs/specs/per-user-settings-ownership): the team's old row (DEFAULTS_KEY) is never read."""
    own = db.get(UserVideoDefaults, user_id)
    if own is None or not isinstance(own.value, dict):
        return built_in_defaults()
    stored: dict = {}
    for name, value in own.value.items():
        try:
            stored |= clean({name: value}, allow_video_fields=True)
        except OptionError:
            continue
    return built_in_defaults() | stored


def has_own_defaults(db: DbSession, user_id: int) -> bool:
    return db.get(UserVideoDefaults, user_id) is not None


def save_member_defaults(db: DbSession, user_id: int, values: dict) -> dict:
    """A member's own defaults, started from what they use now (the built-in ones the first time) with `values`
    changed."""
    merged = member_defaults(db, user_id) | clean(values, allow_video_fields=True)
    own = db.get(UserVideoDefaults, user_id)
    if own is None:
        db.add(UserVideoDefaults(user_id=user_id, value=merged))
    else:
        own.value = merged
    return merged


def forget_member_defaults(db: DbSession, user_id: int) -> None:
    """Back to the app's built-in defaults ("Về mặc định gốc")."""
    own = db.get(UserVideoDefaults, user_id)
    if own is not None:
        db.delete(own)


def apply_defaults(db: DbSession, video: Video, user_id: int) -> None:
    """A new video takes its maker's defaults (member_defaults), and the voice and "Chữ & phụ đề" of its topic group
    when the group has them: video's own › group's › maker's own › built-in. It also starts on the channel whose
    Page is in the video's topic group (`brands.default_for`), so the logo is on without picking it each time —
    and on no channel at all when the group has none of the maker's Pages. Set `video.knowledge_topic_id` first."""
    from . import brands  # imported here, like text_looks: kept out of this module's import-time graph
    from .text_looks import group_look  # imported here: text_looks reads this module

    defaults = member_defaults(db, user_id)
    video.voice_enabled, video.music_volume = defaults["voice_enabled"], defaults["music_volume"]
    video.options = {name: defaults[name] for name in DEFAULTS}
    group = db.get(KnowledgeTopic, video.knowledge_topic_id) if video.knowledge_topic_id else None
    if group is not None and group.voice_id:
        video.options["voice_id"] = group.voice_id
    if is_pc_shopee(group):
        # PC Shopee's own start (docs/decisions/2026-11-27-text-hold.md, 2026-11-27-cumulative-captions.md): "Cộng dồn"
        # captions in place of the scenes' text; the hold waits for when "Cộng dồn" is turned off.
        video.options["text_hold_sec"] = PC_SHOPEE_TEXT_HOLD
        video.options["captions"] = "cumulative"
        video.options["title_layout"], video.options["scene_text_layout"] = "three_tier", "two_tier"
    video.options.update(group_look(group))  # the group's own look wins over PC Shopee's starting values
    brand = brands.default_for(db, user_id, video.knowledge_topic_id)
    if brand is not None:
        video.options["brand_id"] = brand.id
