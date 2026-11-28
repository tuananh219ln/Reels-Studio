"""A channel's logo laid on the finished video ("Logo theo kênh").

The badge (a round logo with a white ring and a soft shadow) is made once, when the logo is uploaded, by
`make_badge`. The render lays it over the joined scenes, so it stays still through transitions and zooms. Its place and
size are layout.py's, or the video's own; the title scene (the cover) has none.
"""

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from .layout import DEFAULT_PROFILE, PROFILES, Profile, logo_box

BADGE_SIZE = 512  # the logo's diameter inside the stored badge
RING = 0.05  # white ring, as a share of the diameter
PAD = 0.12  # room around the ring for the shadow
SHADOW_OFFSET = 0.025
SHADOW_BLUR = 0.04

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


def placement(
    profile: Profile = PROFILES[DEFAULT_PROFILE], position: tuple[int, int] | None = None, size: int | None = None
) -> Placement:
    """Where the stored badge goes so that its white ring is `size` across with its top-left corner at `position`
    (layout.logo_box): the badge also holds the room for its shadow round the ring."""
    left, top, size = logo_box(profile, position, size)
    scale = size / (BADGE_SIZE + 2 * round(BADGE_SIZE * RING))
    pad = round(BADGE_SIZE * PAD) * scale
    return Placement(round(badge_canvas() * scale), round(left - pad), round(top - pad))
