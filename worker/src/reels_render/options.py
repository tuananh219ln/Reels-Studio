"""Per-video render choices, each a named preset; the defaults render exactly the original template.

Members pick these on the video's "Thiết lập" tab (and the team's defaults on Cài đặt › Mặc định video).
Colours may also be any "#RRGGBB" (the page warns about faint ones); sizes stay presets.
"""

from dataclasses import dataclass

from .errors import InputError
from .textbox import is_hex

TRANSITIONS = ("fade", "cut", "slide")
MOTIONS = ("zoom_in", "zoom_out", "pan", "static")
ZOOMS = {"light": 1.06, "medium": 1.12, "strong": 1.18}
TEXT_STYLES = ("yellow", "white", "dark", "red", "none")  # "none": no box, outlined letters
TEXT_COLORS = ("auto", "white", "black", "yellow", "red")  # "auto": the style's own text colour; or "#RRGGBB"
TITLE_STYLES = ("same", "yellow")  # "same": the title scene is drawn like the other scenes
CAPTIONS = ("off", "phrase", "word")


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

    def __post_init__(self) -> None:
        for name, value, allowed in (
            ("transition", self.transition, TRANSITIONS),
            ("motion", self.motion, MOTIONS),
            ("zoom", self.zoom, tuple(ZOOMS)),
            ("text_style", self.text_style, TEXT_STYLES),
            ("title_style", self.title_style, TITLE_STYLES),
            ("captions", self.captions, CAPTIONS),
        ):
            if value not in allowed:
                raise InputError(f"Tuỳ chọn {name} không hợp lệ: {value!r} (chọn một trong {', '.join(allowed)})")
        for name, value, named in (
            ("text_color", self.text_color, TEXT_COLORS),
            ("box_color", self.box_color, ("auto",)),
            ("accent_color", self.accent_color, ("auto",)),
        ):
            if not isinstance(value, str) or (value not in named and not is_hex(value)):
                raise InputError(f"Màu {name} không hợp lệ: {value!r} (chọn một trong {', '.join(named)} hoặc #RRGGBB)")
        volume = self.voice_volume
        if isinstance(volume, bool) or not isinstance(volume, (int, float)) or not 0 <= volume <= 1:
            raise InputError(f"Âm lượng giọng đọc phải là số từ 0 đến 1 (đang là {volume})")

    @property
    def zoom_end(self) -> float:
        return ZOOMS[self.zoom]


DEFAULT_OPTIONS = RenderOptions()
