"""The three looks of PC Shopee's drawn text (docs/decisions/2026-11-27-pc-text-styles.md): "Neon game", "Halftone tím"
and "Thương hiệu". Each draws one line of capitals as a picture: fill, outline(s), shadow and glow, all by role (a marked
word or a plain one), so the captions, the scenes' text and the title look alike. No box behind any of them.
"""

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from .textbox import FONT_PATH as BE_VIETNAM_PATH

BUNGEE_PATH = Path(__file__).parent / "fonts" / "Bungee-Regular.ttf"
PC_STYLES = ("neon_game", "halftone_purple", "brand_navy")
PAD = 40  # room for the glow and the shadow around a line

RGB = tuple[int, int, int]


def hex_rgb(code: str) -> RGB:
    return int(code[1:3], 16), int(code[3:5], 16), int(code[5:7], 16)


@dataclass(frozen=True)
class LineStyle:
    font: Path
    fill: RGB
    outline: tuple[int, RGB | tuple[RGB, RGB]]  # width, a colour or a (top, bottom) gradient
    outer: tuple[int, RGB] | None = None  # a second, outside outline: width, colour
    shadow: tuple[int, int, RGB] | None = None  # dx, dy, colour: a hard offset shadow, no blur
    glow: tuple[RGB, float, int] | None = None  # colour, opacity, blur
    dots: tuple[RGB, float] | None = None  # halftone dots over the fill: colour, coverage
    gradient: tuple[RGB, RGB] | None = None  # the fill from the top colour to the bottom one
    spacing: float = 0.0  # extra space between letters, of the size


def line_style(style: str, key: bool, index: int = 0) -> LineStyle:
    """The look of one line. `index` is its place in the lines stacked (Halftone alternates black and white)."""
    if style == "halftone_purple":
        if key or index % 2 == 0:
            return LineStyle(
                BE_VIETNAM_PATH,
                hex_rgb("#111114"),
                (6, (hex_rgb("#C8B6FF"), hex_rgb("#A8F0E0")) if key else hex_rgb("#C8B6FF")),
                outer=(3, hex_rgb("#1A1530")),
                dots=((255, 255, 255), 0.25),
                spacing=0.02,
            )
        return LineStyle(
            BE_VIETNAM_PATH,
            hex_rgb("#EDEDF2"),
            (5, hex_rgb("#111114")),
            glow=((255, 255, 255), 0.4, 8),
            dots=(hex_rgb("#3A3A44"), 0.30),
            spacing=0.02,
        )
    if style == "brand_navy":
        navy = hex_rgb("#10195E")
        return LineStyle(
            BE_VIETNAM_PATH,
            hex_rgb("#FFC816") if key else hex_rgb("#FEFFFA"),
            (6, navy),
            shadow=(0, 6, navy),
            gradient=(hex_rgb("#FFD84A"), hex_rgb("#FFB113")) if key else None,
            spacing=0.02,
        )
    return LineStyle(
        BUNGEE_PATH,
        hex_rgb("#5EF2D0") if key else (255, 255, 255),
        (6, hex_rgb("#0B1E2B")),
        glow=(hex_rgb("#3FE0FF"), 0.55, 14),
    )


@lru_cache(maxsize=32)
def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def _width(text: str, font: ImageFont.FreeTypeFont, spacing: float, size: int) -> float:
    return font.getlength(text) + spacing * size * max(0, len(text) - 1)


def fitted_size(text: str, size: int, style: LineStyle, max_width: int) -> int:
    """`size`, or smaller when the line (with its outline) would be wider than `max_width`."""
    wide = _width(text, _font(style.font, size), style.spacing, size) + 2 * style.outline[0]
    return size if wide <= max_width else max(24, math.floor(size * max_width / wide))


def _mask(text: str, size: int, style: LineStyle, grow: int, canvas: tuple[int, int]) -> Image.Image:
    """The line's letters as a mask on `canvas`, grown by `grow` px all round, centred across and starting PAD down."""
    mask = Image.new("L", canvas, 0)
    draw = ImageDraw.Draw(mask)
    font = _font(style.font, size)
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


def _dots(size: tuple[int, int], colour: RGB, coverage: float) -> Image.Image:
    """A halftone: dots on a grid of 128 px cells' worth of pattern, covering `coverage` of the area."""
    cell = 14
    radius = cell * math.sqrt(coverage / math.pi)
    tile = Image.new("L", (cell * 8, cell * 8), 0)
    draw = ImageDraw.Draw(tile)
    for row in range(8):
        for column in range(8):
            cx, cy = (column + 0.5 + (0.5 if row % 2 else 0)) * cell, (row + 0.5) * cell
            draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=255)
    pattern = Image.new("L", size, 0)
    for left in range(0, size[0], tile.width):
        for top in range(0, size[1], tile.height):
            pattern.paste(tile, (left, top))
    layer = Image.new("RGBA", size, (*colour, 0))
    layer.putalpha(pattern)
    return layer


def render_line(text: str, size: int, style: LineStyle, max_width: int = 990) -> Image.Image:
    """One line as an RGBA picture, text centred, with room all round for the glow and the shadow."""
    size = fitted_size(text, size, style, max_width)
    font = _font(style.font, size)
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
    colour = style.outline[1]
    paint(inner, _gradient(*colour, canvas) if isinstance(colour[0], tuple) else colour)
    letters = _mask(text, size, style, 0, canvas)
    paint(letters, _gradient(*style.gradient, canvas) if style.gradient else style.fill)
    if style.dots is not None:
        dots = _dots(canvas, *style.dots)
        clipped = ImageChops.multiply(dots.getchannel("A"), letters)
        dots.putalpha(clipped)
        picture.alpha_composite(dots)
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
