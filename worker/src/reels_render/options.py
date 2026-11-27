"""Per-video render choices, each a named preset; the defaults render exactly the original template.

Members pick these on the video's "Thiết lập" tab (and the team's defaults on Cài đặt › Mặc định video).
Colours may also be any "#RRGGBB" (the page warns about faint ones); sizes stay presets.
"""

from dataclasses import dataclass

from .errors import InputError
from .markup import TEXT_CASES
from .pc_text import PC_STYLES
from .textbox import Palette, is_hex, palette_for, title_palette

# The video's transition between scenes, each a key of effects.SCENE_TRANSITIONS (a scene's own one wins). The first
# three are the original ones; the rest were added on 2026-11-19 (docs/decisions/2026-11-19-more-image-effects.md).
TRANSITIONS = ("fade", "cut", "slide", "zoom", "flash", "black", "blur", "smooth_slide")
# The photos' motion: the first four move linearly as they always have; the four added on 2026-11-19 ease in and out.
MOTIONS = ("zoom_in", "zoom_out", "pan", "static", "kenburns_diagonal", "pan_vertical", "handheld", "punch_in")
# How far a motion zooms. "extreme" was added on 2026-11-19; the other three keep their values, so no video saved
# before renders differently.
ZOOMS = {"light": 1.06, "medium": 1.12, "strong": 1.18, "extreme": 1.6}
# "box": a team box style's copied colours; "none": no box, outlined letters; the rest predate team styles.
TEXT_STYLES = ("yellow", "white", "dark", "red", "box", "none")
# The style's own, 100%, 88%, 70%, 45%, no background.
BOX_OPACITIES = ("auto", "solid", "soft", "clear", "faint", "none")
TEXT_COLORS = ("auto", "white", "black", "yellow", "red")  # "auto": the style's own text colour; or "#RRGGBB"
TITLE_STYLES = ("same", "yellow")  # "same": the title scene is drawn like the other scenes
TEXT_FONTS = ("be_vietnam", "bungee")  # the text boxes' font (textbox.FONTS)
TITLE_TEXT_STYLES = ("same", *TEXT_STYLES)  # "same": no look of its own (title_style decides)
# "cumulative" ("Cộng dồn", PC Shopee): the words pile up and a phrase clears; the content scenes' own text is not drawn.
CAPTIONS = ("off", "phrase", "word", "cumulative")
TEXT_SIZE_NAMES = ("large", "medium", "small")  # textbox.TEXT_SIZES


@dataclass(frozen=True)
class RenderOptions:
    transition: str = "fade"  # 0.4 s, effects.SCENE_TRANSITIONS; cut: hard cut
    motion: str = "zoom_in"  # photos only: clips never get motion on top of their own
    zoom: str = "medium"  # how far the motion zooms, and so how far a pan or a shake can travel
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
    text_font: str = "be_vietnam"  # the text boxes' font (TEXT_FONTS); "be_vietnam" is the original
    # "Dạng chữ" (markup.TEXT_CASES): the content scenes' text and the text layers, and the title scene's.
    text_case: str = "upper"
    title_text_case: str = "upper"
    # "Nền tối mờ sau chữ": a black band, 45% at its darkest, behind the content scenes' text (textbox.with_shade).
    text_shade: bool = False
    # "Video xuyên suốt": the title scene's photo or clip runs under every scene, joined by hard cuts, and the text
    # boxes fade in and out instead; photo layers ("Ảnh món") are laid on only then.
    backdrop: bool = False
    # Some clip has blurred boxes ("video_blur"). The render reads the boxes from the scenes; this flag exists so a
    # render machine on older code, which would drop the boxes and show the logo, refuses the video (an option it
    # does not know) instead (api/src/reels_api/render_nodes.options_dict).
    clip_blur: bool = False
    # The script carries a channel logo (`Script.logo`). Same reason: a machine on older code would render the video
    # without it, so it refuses the option instead.
    logo: bool = False
    # Some scene loops its clip ("video_loop"). Same reason: a machine on older code would hold the clip's last
    # frame instead, so it refuses the option.
    clip_loop: bool = False
    # Some scene hides its text after a few seconds ("text_hold_sec"). Same reason: a machine on older code would keep
    # the text all scene, so it refuses the option.
    text_hold: bool = False
    # The look of PC Shopee's drawn text (pc_text.PC_STYLES): the "Cộng dồn" captions, and later the scenes' and the
    # title's text. "neon_game" is the first and the default.
    pc_style: str = "neon_game"
    # PC Shopee's compact text: the title in three tiers and a content scene's text in two (tiers.py), drawn in
    # `pc_title_style` and `pc_style`; "box": the text boxes every other group has.
    title_layout: str = "box"
    scene_text_layout: str = "box"
    pc_title_style: str = "brand_navy"
    # The title preset's whole-frame effects (pc_text.FRAME_EFFECTS) on the title scene; sent only when on and the
    # preset has some, so a machine on older code refuses the option instead of rendering without them.
    title_effects: bool = False

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
            ("pc_style", self.pc_style, PC_STYLES),
            ("pc_title_style", self.pc_title_style, PC_STYLES),
            ("title_layout", self.title_layout, ("box", "three_tier")),
            ("scene_text_layout", self.scene_text_layout, ("box", "two_tier")),
            ("text_size", self.text_size, TEXT_SIZE_NAMES),
            ("title_text_size", self.title_text_size, TEXT_SIZE_NAMES),
            ("text_font", self.text_font, TEXT_FONTS),
            ("text_case", self.text_case, TEXT_CASES),
            ("title_text_case", self.title_text_case, TEXT_CASES),
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
        for name, flag in (
            ("backdrop", self.backdrop),
            ("text_shade", self.text_shade),
            ("title_effects", self.title_effects),
        ):
            if not isinstance(flag, bool):
                raise InputError(f"Tuỳ chọn {name} phải là true hoặc false (đang là {flag!r})")
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
