"""A channel's logo laid on the finished video ("Logo theo kênh").

The badge (a round logo with a white ring and a soft shadow) is made once, when the logo is uploaded, by
`make_badge`. The render lays it over the joined scenes, so it stays still through transitions and zooms. Positions
are measured on the 1080x1920 frame; `docs/ux-guidelines.md` has the safe zone they come from.
"""

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from .textbox import FRAME_WIDTH

BADGE_SIZE = 512  # the logo's diameter inside the stored badge
RING = 0.05  # white ring, as a share of the diameter
PAD = 0.12  # room around the ring for the shadow
SHADOW_OFFSET = 0.025
SHADOW_BLUR = 0.04

TITLE_DIAMETER = 170  # on the title scene
CORNER_DIAMETER = 120  # on the other scenes
CORNER_RIGHT = 60  # gap from the right edge to the ring's outer edge
CORNER_TOP = 200  # gap from the top edge to the ring's outer edge
TITLE_NO_BOX_TOP = 200  # title without a box: the ring's outer top edge
TITLE_NO_BOX_TEXT_TOP = 400  # ... and where its text may start
TITLE_BOX_MIN_TOP = 290  # title with a box: the box's top edge at least
TEXT_TOP_MIN = 370  # content scenes: where the text may start while the logo is on

MIN_SOURCE_SIDE = 256  # the shorter side of an uploaded logo
MAX_SOURCE_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class Placement:
    """A badge scaled to `width` pixels across, laid with its top-left corner at (x, y)."""

    width: int
    x: int
    y: int


def badge_canvas(size: int = BADGE_SIZE) -> int:
    return size + 2 * (round(size * RING) + round(size * PAD))


def make_badge(src_path: Path, out_path: Path, size: int = BADGE_SIZE) -> None:
    """A square RGBA PNG: the logo cut to a circle (cover, centred) with a white ring and a soft shadow."""
    ring = round(size * RING)
    pad = round(size * PAD)
    outer = size + 2 * ring
    canvas = outer + 2 * pad
    with Image.open(src_path) as source:
        logo = ImageOps.fit(source.convert("RGBA"), (size, size))
    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size * 4 - 1, size * 4 - 1], fill=255)
    logo.putalpha(mask.resize((size, size), Image.Resampling.LANCZOS))

    out = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    offset = round(size * SHADOW_OFFSET)
    ImageDraw.Draw(shadow).ellipse([pad, pad + offset, pad + outer, pad + outer + offset], fill=(0, 0, 0, 102))
    out = Image.alpha_composite(out, shadow.filter(ImageFilter.GaussianBlur(size * SHADOW_BLUR)))
    ImageDraw.Draw(out).ellipse([pad, pad, pad + outer - 1, pad + outer - 1], fill="white")
    out.alpha_composite(logo, (pad + ring, pad + ring))
    out.save(out_path)


def _scaled(diameter: int) -> tuple[int, float]:
    """The badge's width at a logo `diameter`, and the scale from the stored badge."""
    scale = diameter / BADGE_SIZE
    return round(badge_canvas() * scale), scale


def _pad(scale: float) -> float:
    return round(BADGE_SIZE * PAD) * scale


def title_placement(box_top: int | None) -> Placement:
    """The title scene's badge: centred across, its centre on the text box's top edge (`box_top`), or, with no box,
    its ring's top edge 200 px from the top."""
    width, scale = _scaled(TITLE_DIAMETER)
    x = (FRAME_WIDTH - width) // 2
    if box_top is None:
        return Placement(width, x, round(TITLE_NO_BOX_TOP - _pad(scale)))
    return Placement(width, x, round(box_top - width / 2))


def corner_placement() -> Placement:
    """The other scenes' badge: its ring 60 px from the right edge and 200 px from the top."""
    width, scale = _scaled(CORNER_DIAMETER)
    return Placement(width, round(FRAME_WIDTH - CORNER_RIGHT + _pad(scale) - width), round(CORNER_TOP - _pad(scale)))
