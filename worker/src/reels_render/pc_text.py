"""The looks of PC Shopee's drawn text (docs/decisions/2026-11-27-pc-text-styles.md): "Neon game" and "Thương hiệu"
(and the title presets). Each draws one line of capitals as a picture: fill, outline(s), shadow and glow, all by role (a marked
word or a plain one), so the captions, the scenes' text and the title look alike. No box behind any of them.
"""

import math
import random
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

BUNGEE_PATH = Path(__file__).parent / "fonts" / "Bungee-Regular.ttf"
FONTS = Path(__file__).parent / "fonts"
PRESETS = ("neon_tech_teal", "neon_outline_price", "gold_metal", "grunge_rainbow", "esports_blue")
# Whole-frame effects of a title preset (the spec's frameEffects), as one FFmpeg chain on the title scene: Mẫu 4's
# glitch (red and blue shifted apart) and vignette. The member can switch them off (option `title_effects`).
SPARKLE_STYLES = ("gold_metal",)  # presets with the optional sparkles, drawn into the title's picture
FRAME_EFFECTS = {"grunge_rainbow": "format=gbrp,rgbashift=rh=-6:bh=6,vignette=angle=PI/5"}
PC_STYLES = (
    "neon_game",
    "brand_navy",
    # The five title presets (docs/decisions/2026-11-27-title-presets.md)
    "neon_tech_teal",
    "neon_outline_price",
    "gold_metal",
    "grunge_rainbow",
    "esports_blue",
)
PAD = 40  # room for the glow and the shadow around a line

RGB = tuple[int, int, int]


def hex_rgb(code: str) -> RGB:
    return int(code[1:3], 16), int(code[3:5], 16), int(code[5:7], 16)


@dataclass(frozen=True)
class LineStyle:
    font: Path
    fill: RGB | None  # None: only the outline is drawn, the letters stay hollow
    outline: tuple[int, RGB | tuple[RGB, RGB]]  # width, a colour or a (top, bottom) gradient
    outer: tuple[int, RGB] | None = None  # a second, outside outline: width, colour
    shadow: tuple[int, int, RGB] | None = None  # dx, dy, colour: a hard offset shadow, no blur
    glow: tuple[RGB, float, int] | None = None  # colour, opacity, blur
    gradient: tuple[RGB, RGB] | None = None  # the fill from the top colour to the bottom one
    spacing: float = 0.0  # extra space between letters, of the size
    variation: tuple[int, int | None] | None = None  # a variable font's weight and (if it has the axis) width
    across: tuple[RGB, ...] | None = None  # the fill as stops from the left edge to the right one
    echo: tuple[float, float, int] | None = None  # a faint copy above the line: offset (of the size), opacity, blur
    speckle: tuple[RGB, int, int] | None = None  # specks over the letters, the texture's stand-in: colour, count, seed
    tilt: float = 0.0  # degrees, anticlockwise
    vi: "LineStyle | None" = None  # the look used when the line has a Vietnamese mark and the font has none


def line_style(style: str, key: bool, index: int = 0) -> LineStyle:
    """The look of one line. `index` is its place in the lines stacked."""
    if style in PRESETS:
        return _preset(style, key, index)
    if style == "brand_navy":
        navy = hex_rgb("#10195E")
        return LineStyle(
            BUNGEE_PATH,
            hex_rgb("#FFC816") if key else hex_rgb("#FEFFFA"),
            (6, navy),
            shadow=(0, 6, navy),
            gradient=(hex_rgb("#FFD84A"), hex_rgb("#FFB113")) if key else None,
        )
    return LineStyle(
        BUNGEE_PATH,
        hex_rgb("#5EF2D0") if key else (255, 255, 255),
        (6, hex_rgb("#0B1E2B")),
        glow=(hex_rgb("#3FE0FF"), 0.55, 14),
    )


def _preset(style: str, key: bool, index: int) -> LineStyle:
    """One line of a title preset. A line the caller marks as the main one (`key`) takes the preset's emphasis line, the
    first of the others its upper line and any later one its lower line (the spec's lead / main / sub)."""
    slot = 1 if key else 0 if index == 0 else 2
    white, navy = (255, 255, 255), hex_rgb("#0B1E2B")
    saira_wide = LineStyle(FONTS / "Saira-VF.ttf", white, (4, navy), variation=(900, 125), spacing=0.02)
    if style == "neon_tech_teal":
        teal = hex_rgb("#3DF5D6")
        look = LineStyle(
            FONTS / "Audiowide-Regular.ttf",
            teal if key else white,
            (5, hex_rgb("#06242A")),
            glow=(teal, 0.6, 16),
            spacing=0.02,
        )
        return replace(look, vi=replace(saira_wide, fill=look.fill, outline=look.outline, glow=look.glow))
    if style == "neon_outline_price":
        blue = hex_rgb("#4DA6FF")
        if slot == 0:
            return LineStyle(
                FONTS / "Oswald-VF.ttf", white, (5, hex_rgb("#0A1A4A")), variation=(700, None), spacing=0.02
            )
        look = LineStyle(
            FONTS / ("Anton-Regular.ttf" if slot == 1 else "Audiowide-Regular.ttf"),
            None,
            (4, blue),
            glow=(blue, 0.7, 14),
            spacing=0.03,
        )
        return replace(
            look, vi=replace(saira_wide, fill=None, outline=look.outline, glow=look.glow, variation=(800, 125))
        )
    if style == "gold_metal":
        brown = hex_rgb("#3B2410")
        return LineStyle(
            FONTS / "Montserrat-VF.ttf",
            hex_rgb("#E8B923"),
            (6, brown),
            shadow=(0, 7, hex_rgb("#1A0F05")),
            gradient=(hex_rgb("#FFEFA0"), hex_rgb("#B7791F")),
            speckle=(hex_rgb("#FFF6C8"), 700, 7),
            variation=(900, None),
            spacing=0.02,
        )
    if style == "grunge_rainbow":
        dark = hex_rgb("#101014")
        if slot == 1:
            return LineStyle(
                FONTS / "Montserrat-VF.ttf",
                white,
                (5, dark),
                across=tuple(hex_rgb(c) for c in ("#FF4D4D", "#FFB020", "#FFF04D", "#4DE08A", "#4DA3FF", "#B06BFF")),
                variation=(900, None),
                spacing=0.02,
            )
        if slot == 2:
            marker = LineStyle(FONTS / "PermanentMarker-Regular.ttf", dark, (5, white), tilt=4.0)
            return replace(marker, vi=LineStyle(FONTS / "Mali-Bold.ttf", dark, (5, white), tilt=4.0))
        return LineStyle(
            FONTS / "Montserrat-VF.ttf",
            hex_rgb("#F2F2F2"),
            (4, dark),
            echo=(0.35, 0.35, 6),
            speckle=(hex_rgb("#7A7A7A"), 600, 3),
            variation=(900, None),
            spacing=0.02,
        )
    # esports_blue: charcoal lines with a white halo around a white line with a double blue outline
    if slot == 1:
        return LineStyle(
            FONTS / "SairaCondensed-Black.ttf",
            white,
            (6, hex_rgb("#1E6BFF")),
            outer=(4, hex_rgb("#0A2A66")),
            glow=(hex_rgb("#1E6BFF"), 0.5, 10),
            spacing=0.02,
        )
    return LineStyle(
        FONTS / "Montserrat-VF.ttf",
        hex_rgb("#3A3F47"),
        (5, white),
        glow=(white, 0.55, 12),
        variation=(900, None),
        spacing=0.02,
    )


@lru_cache(maxsize=64)
def _font(path: Path, size: int, variation: tuple[int, int | None] | None = None) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(str(path), size)
    if variation is not None:
        weight, width = variation
        values = []
        for axis in font.get_variation_axes():
            name = axis["name"].decode() if isinstance(axis["name"], bytes) else str(axis["name"])
            wanted = width if "width" in name.lower() else weight
            values.append(min(max(wanted if wanted is not None else axis["default"], axis["minimum"]), axis["maximum"]))
        font.set_variation_by_axes(values)
    return font


def _for_text(text: str, style: LineStyle) -> LineStyle:
    """The style, or its Vietnamese fallback when the line has a mark outside ASCII and the font has none (Audiowide)."""
    if style.vi is not None and not text.isascii():
        return style.vi
    return style


def _width(text: str, font: ImageFont.FreeTypeFont, spacing: float, size: int) -> float:
    return font.getlength(text) + spacing * size * max(0, len(text) - 1)


def fitted_size(text: str, size: int, style: LineStyle, max_width: int) -> int:
    """`size`, or smaller when the line (with its outline) would be wider than `max_width`."""
    style = _for_text(text, style)
    wide = _width(text, _font(style.font, size, style.variation), style.spacing, size) + 2 * style.outline[0]
    return size if wide <= max_width else max(24, math.floor(size * max_width / wide))


def _mask(text: str, size: int, style: LineStyle, grow: int, canvas: tuple[int, int]) -> Image.Image:
    """The line's letters as a mask on `canvas`, grown by `grow` px all round, centred across and starting PAD down."""
    mask = Image.new("L", canvas, 0)
    draw = ImageDraw.Draw(mask)
    font = _font(style.font, size, style.variation)
    total = _width(text, font, style.spacing, size)
    x = (canvas[0] - total) / 2
    for char in text:
        draw.text((x, PAD), char, font=font, fill=255, stroke_width=grow, stroke_fill=255)
        x += font.getlength(char) + style.spacing * size
    return mask


def _gradient(top: RGB, bottom: RGB, size: tuple[int, int]) -> Image.Image:
    column = Image.new("RGB", (1, size[1]))
    for y in range(size[1]):
        share = y / max(1, size[1] - 1)
        column.putpixel((0, y), tuple(round(a + (b - a) * share) for a, b in zip(top, bottom)))
    return column.resize(size)


def _across(stops: tuple[RGB, ...], size: tuple[int, int]) -> Image.Image:
    """The stops as one band from the left edge to the right one."""
    row = Image.new("RGB", (size[0], 1))
    for x in range(size[0]):
        place = x / max(1, size[0] - 1) * (len(stops) - 1)
        low = min(int(place), len(stops) - 2)
        share = place - low
        row.putpixel((x, 0), tuple(round(a + (b - a) * share) for a, b in zip(stops[low], stops[low + 1])))
    return row.resize(size)


def _speckle(size: tuple[int, int], colour: RGB, count: int, seed: int) -> Image.Image:
    """Random specks (a glitter or a grunge texture made in code, so no image is bundled), the same every time."""
    layer = Image.new("RGBA", size, (*colour, 0))
    draw = ImageDraw.Draw(layer)
    rng = random.Random(seed)
    for _ in range(count):
        x, y, r = rng.randrange(size[0]), rng.randrange(size[1]), rng.choice((1, 1, 2, 3))
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(*colour, rng.randrange(90, 230)))
    return layer


def sparkles(size: tuple[int, int], colour: RGB, count: int, seed: int) -> Image.Image:
    """Four-pointed stars scattered over a picture of `size`, the spec's optional `sparkles` frame effect."""
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    rng = random.Random(seed)
    for _ in range(count):
        x, y, r = rng.randrange(size[0]), rng.randrange(size[1]), rng.randrange(10, 26)
        pinch = r * 0.22
        draw.polygon(
            [
                (x, y - r),
                (x + pinch, y - pinch),
                (x + r, y),
                (x + pinch, y + pinch),
                (x, y + r),
                (x - pinch, y + pinch),
                (x - r, y),
                (x - pinch, y - pinch),
            ],
            fill=(*colour, 235),
        )
    return layer


def render_line(text: str, size: int, style: LineStyle, max_width: int = 990) -> Image.Image:
    """One line as an RGBA picture, text centred, with room all round for the glow and the shadow."""
    style = _for_text(text, style)
    size = fitted_size(text, size, style, max_width)
    font = _font(style.font, size, style.variation)
    ascent, descent = font.getmetrics()
    outer = style.outer[0] if style.outer else 0
    reach = style.outline[0] + outer
    width = math.ceil(_width(text, font, style.spacing, size)) + 2 * (PAD + reach)
    height = ascent + descent + 2 * PAD + 2 * reach
    canvas = (width, height)
    picture = Image.new("RGBA", canvas, (0, 0, 0, 0))

    def paint(mask: Image.Image, fill: Image.Image | RGB, opacity: float = 1.0) -> None:
        layer = fill if isinstance(fill, Image.Image) else Image.new("RGB", canvas, fill)
        layer = layer.convert("RGBA")
        layer.putalpha(mask.point(lambda value: round(value * opacity)))
        picture.alpha_composite(layer)

    shifted = lambda mask, dx, dy: ImageChops.offset(mask, dx, dy)  # noqa: E731  (a one-line helper)
    widest = _mask(text, size, style, reach, canvas)
    letters = _mask(text, size, style, 0, canvas)
    if style.echo is not None:
        offset, opacity, blur = style.echo
        faint = shifted(letters, 0, -round(offset * size)).filter(ImageFilter.GaussianBlur(blur))
        paint(faint, style.fill or style.outline[1], opacity)
    if style.glow is not None:
        colour, opacity, blur = style.glow
        grown = _mask(text, size, style, reach + 4, canvas)
        paint(grown.filter(ImageFilter.GaussianBlur(blur)), colour, opacity)
    if style.shadow is not None:
        dx, dy, colour = style.shadow
        paint(shifted(widest, dx, dy), colour)
    if style.outer is not None:
        paint(widest, style.outer[1])
    inner = _mask(text, size, style, style.outline[0], canvas)
    if style.fill is None:  # hollow letters: the outline is a ring, the middle stays clear
        inner = ImageChops.subtract(inner, letters)
    colour = style.outline[1]
    paint(inner, _gradient(*colour, canvas) if isinstance(colour[0], tuple) else colour)
    if style.fill is not None:
        if style.across:
            fill: Image.Image | RGB = _across(style.across, canvas)
        else:
            fill = _gradient(*style.gradient, canvas) if style.gradient else style.fill
        paint(letters, fill)
    if style.speckle is not None and style.fill is not None:
        specks = _speckle(canvas, *style.speckle)
        specks.putalpha(ImageChops.multiply(specks.getchannel("A"), letters))
        picture.alpha_composite(specks)
    if style.tilt:
        picture = picture.rotate(style.tilt, expand=True, resample=Image.Resampling.BICUBIC)
    return picture


def stack(pictures: list[Image.Image], gaps: list[int]) -> Image.Image:
    """The lines one under another, centred across. Their padding overlaps by the gap, so spacing is by the letters."""
    width = max(picture.width for picture in pictures)
    height = sum(picture.height for picture in pictures) + sum(gaps) - 2 * PAD * (len(pictures) - 1)
    result = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    y = 0
    for index, picture in enumerate(pictures):
        result.alpha_composite(picture, ((width - picture.width) // 2, y))
        y += picture.height - 2 * PAD + (gaps[index] if index < len(gaps) else 0)
    return result
