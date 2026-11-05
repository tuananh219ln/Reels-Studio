"""Per-video render choices, each a named preset; the defaults render exactly the original template.

Members pick these on the video's "Thiết lập" tab (and the team's defaults on Cài đặt › Mặc định video).
Colours may also be any "#RRGGBB" (the page warns about faint ones); sizes stay presets.
"""

from dataclasses import dataclass

from .errors import InputError
from .textbox import Palette, is_hex, palette_for, title_palette

TRANSITIONS = ("fade", "cut", "slide")
MOTIONS = ("zoom_in", "zoom_out", "pan", "static")
ZOOMS = {"light": 1.06, "medium": 1.12, "strong": 1.18}
# "box": a team box style's copied colours; "none": no box, outlined letters; the rest predate team styles.
TEXT_STYLES = ("yellow", "white", "dark", "red", "box", "none")
BOX_OPACITIES = ("auto", "solid", "soft", "clear", "none")  # the style's own, 100%, 88%, 70%, no background
TEXT_COLORS = ("auto", "white", "black", "yellow", "red")  # "auto": the style's own text colour; or "#RRGGBB"
TITLE_STYLES = ("same", "yellow")  # "same": the title scene is drawn like the other scenes
TITLE_TEXT_STYLES = ("same", *TEXT_STYLES)  # "same": no look of its own (title_style decides)
CAPTIONS = ("off", "phrase", "word")
TEXT_SIZE_NAMES = ("large", "medium", "small")  # textbox.TEXT_SIZES


@dataclass(frozen=True)
class RenderOptions:
    transition: str = "fade"  # fade: 0.4 s crossfade; cut: hard cut; slide: the next scene slides in
    motion: str = "zoom_in"  # photos only: clips never get motion on top of their own
    zoom: str = "medium"  # how far zoom_in / zoom_out / pan travel
    text_style: str = "yellow"  # the text box palette (textbox.PALETTES)
    captions: str = "off"  # narration captions: off, phrase by phrase, or phrase with the spoken word lit
    voice_volume: float = 1.0  # narration level, 0–1
    ducking: bool = False  # lower the music while narration plays
    text_color: str = "auto"  # the plain words' colour (textbox.palette_for)
    title_style: str = "same"  # the title scene's own text box (textbox.title_palette)
    box_color: str = "auto"  # the box's colour, or the outline's without a box: "auto" or "#RRGGBB"
    accent_color: str = "auto"  # the *marked* words' colour: "auto" or "#RRGGBB"
    box_opacity: str = "auto"  # how much of the photo shows through the box (textbox.BOX_ALPHAS)
    # The title scene's own look, like the five above; "same" follows the scenes (or title_style "yellow").
    title_text_style: str = "same"
    title_text_color: str = "auto"
    title_box_color: str = "auto"
    title_accent_color: str = "auto"
    title_box_opacity: str = "auto"
    text_size: str = "large"  # the content scenes' text box (textbox.TEXT_SIZES); "large" is the original
    title_text_size: str = "large"  # the title scene's

    def __post_init__(self) -> None:
        for name, value, allowed in (
            ("transition", self.transition, TRANSITIONS),
            ("motion", self.motion, MOTIONS),
            ("zoom", self.zoom, tuple(ZOOMS)),
            ("text_style", self.text_style, TEXT_STYLES),
            ("title_style", self.title_style, TITLE_STYLES),
            ("box_opacity", self.box_opacity, BOX_OPACITIES),
            ("title_text_style", self.title_text_style, TITLE_TEXT_STYLES),
            ("title_box_opacity", self.title_box_opacity, BOX_OPACITIES),
            ("captions", self.captions, CAPTIONS),
            ("text_size", self.text_size, TEXT_SIZE_NAMES),
            ("title_text_size", self.title_text_size, TEXT_SIZE_NAMES),
        ):
            if value not in allowed:
                raise InputError(f"Tuỳ chọn {name} không hợp lệ: {value!r} (chọn một trong {', '.join(allowed)})")
        for name, value, named in (
            ("text_color", self.text_color, TEXT_COLORS),
            ("box_color", self.box_color, ("auto",)),
            ("accent_color", self.accent_color, ("auto",)),
            ("title_text_color", self.title_text_color, TEXT_COLORS),
            ("title_box_color", self.title_box_color, ("auto",)),
            ("title_accent_color", self.title_accent_color, ("auto",)),
        ):
            if not isinstance(value, str) or (value not in named and not is_hex(value)):
                raise InputError(f"Màu {name} không hợp lệ: {value!r} (chọn một trong {', '.join(named)} hoặc #RRGGBB)")
        volume = self.voice_volume
        if isinstance(volume, bool) or not isinstance(volume, (int, float)) or not 0 <= volume <= 1:
            raise InputError(f"Âm lượng giọng đọc phải là số từ 0 đến 1 (đang là {volume})")

    @property
    def zoom_end(self) -> float:
        return ZOOMS[self.zoom]

    def scene_palette(self) -> Palette:
        """The content scenes' text box."""
        return palette_for(self.text_style, self.text_color, self.box_color, self.accent_color, self.box_opacity)

    def title_palette(self) -> Palette:
        """The title scene's text box: its own look, else the original yellow box ("Hộp vàng"), else the scenes'."""
        if self.title_text_style != "same":
            return palette_for(
                self.title_text_style,
                self.title_text_color,
                self.title_box_color,
                self.title_accent_color,
                self.title_box_opacity,
            )
        return title_palette(
            self.text_style, self.text_color, self.title_style, self.box_color, self.accent_color, self.box_opacity
        )


DEFAULT_OPTIONS = RenderOptions()
