"""Per-video render choices, each a named preset; the defaults render exactly the original template.

Members pick these on the video's "Thiết lập" tab (and the team's defaults on Cài đặt › Mặc định video).
Free colour or size sliders are deliberately not offered: a few tested presets keep every video readable.
"""

from dataclasses import dataclass

from .errors import InputError

TRANSITIONS = ("fade", "cut", "slide")
MOTIONS = ("zoom_in", "zoom_out", "pan", "static")
ZOOMS = {"light": 1.06, "medium": 1.12, "strong": 1.18}
TEXT_STYLES = ("yellow", "white", "dark", "red")
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

    def __post_init__(self) -> None:
        for name, value, allowed in (
            ("transition", self.transition, TRANSITIONS),
            ("motion", self.motion, MOTIONS),
            ("zoom", self.zoom, tuple(ZOOMS)),
            ("text_style", self.text_style, TEXT_STYLES),
            ("captions", self.captions, CAPTIONS),
        ):
            if value not in allowed:
                raise InputError(f"Tuỳ chọn {name} không hợp lệ: {value!r} (chọn một trong {', '.join(allowed)})")
        volume = self.voice_volume
        if isinstance(volume, bool) or not isinstance(volume, (int, float)) or not 0 <= volume <= 1:
            raise InputError(f"Âm lượng giọng đọc phải là số từ 0 đến 1 (đang là {volume})")

    @property
    def zoom_end(self) -> float:
        return ZOOMS[self.zoom]


DEFAULT_OPTIONS = RenderOptions()
