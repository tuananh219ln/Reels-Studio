"""Where text, captions and the channel logo go on the 1080×1920 frame (docs/decisions/2026-11-28-safe-layout.md).

The one place for these numbers: the render, the app's previews and QC read them here, and the web gets them from the
api. They are estimates read off real TikTok and Reels screens, not figures the platforms publish for ordinary posts,
so they may change when the apps do. Only places live here; sizes, fonts and styles are each video's own choice (and its
topic group's).
"""

from dataclasses import dataclass

FRAME_WIDTH = 1080
FRAME_HEIGHT = 1920
CAPTION_GAP = 28  # between the captions and a text box they would otherwise land on


@dataclass(frozen=True)
class Profile:
    label: str
    text_top_min: int  # the highest a text may start; also where it goes when nobody placed it
    text_left: int
    text_right: int
    subtitle_bottom: int  # the captions' bottom edge, and the lowest a text may end
    subtitle_margin_lr: int
    logo_x: int  # the badge's white ring, its top-left corner and its diameter
    logo_y: int
    logo_size: int

    @property
    def text_width(self) -> int:
        return self.text_right - self.text_left

    @property
    def subtitle_width(self) -> int:
        return FRAME_WIDTH - 2 * self.subtitle_margin_lr


PROFILES = {
    # Ordinary posts on TikTok and Facebook Reels: the captions sit low.
    "balanced": Profile("TikTok, Facebook Reels", 290, 65, 1015, 1530, 192, 895, 160, 120),
    # Also on YouTube Shorts, Instagram Reels or boosted as an ad: the tightest of their frames.
    "universal": Profile("Mọi nền tảng và quảng cáo", 290, 65, 888, 1248, 192, 768, 160, 120),
}
DEFAULT_PROFILE = "balanced"
LOGO_MIN_SIZE, LOGO_MAX_SIZE = 80, 240
LOGO_TOP_MIN = 120  # the logo may sit over the texts, up in the corner, just under the phone's status bar


def profile_of(name: str) -> Profile:
    return PROFILES[name]


def place_box(
    width: int,
    height: int,
    centre: tuple[int, int] | None,
    is_title: bool,
    profile: Profile = PROFILES[DEFAULT_PROFILE],
    inset: int = 0,
) -> tuple[int, int]:
    """Top-left corner of a text picture. Nobody placed it: centred across, its top at `text_top_min`. `centre` (a
    member dragged it) moves it there, kept between the profile's edges; the title moves only up and down, so the
    thumbnail stays centred. A box too tall for the room keeps its top; one too wide is centred between the sides.
    `inset` is the clear margin round what is drawn (the compact text's pictures), which may leave the edges."""
    middle = FRAME_WIDTH // 2 if is_title or centre is None else centre[0]
    x = middle - width // 2
    left, right = profile.text_left - inset, profile.text_right + inset
    x = left + (right - left - width) // 2 if width > right - left else max(left, min(x, right - width))
    top = profile.text_top_min - inset
    y = top if centre is None else centre[1] - height // 2
    return x, max(top, min(y, profile.subtitle_bottom + inset - height))


def caption_top(height: int, profile: Profile, text: tuple[int, int] | None = None, text_stays: bool = True) -> int:
    """Where a caption of `height` starts: its bottom on `subtitle_bottom`. When the scene's text (`text`: its top and
    bottom) is still on screen and the caption would land on it, the caption goes just over the text, if that stays
    below `text_top_min`."""
    floor = profile.subtitle_bottom - height
    if text is None or not text_stays:
        return floor
    top, bottom = text
    if top >= profile.subtitle_bottom or bottom + CAPTION_GAP <= floor:
        return floor
    above = top - CAPTION_GAP - height
    return above if above >= profile.text_top_min else floor


def logo_box(
    profile: Profile, position: tuple[int, int] | None = None, size: int | None = None
) -> tuple[int, int, int]:
    """The logo ring's top-left corner and diameter: the video's own, else the profile's, kept between the text's
    side edges and between LOGO_TOP_MIN and `subtitle_bottom`."""
    size = max(LOGO_MIN_SIZE, min(size or profile.logo_size, LOGO_MAX_SIZE))
    x, y = position or (profile.logo_x, profile.logo_y)
    x = max(profile.text_left, min(x, profile.text_right - size))
    y = max(LOGO_TOP_MIN, min(y, profile.subtitle_bottom - size))
    return x, y, size
