"""Text and sticker layers laid over a scene for their own seconds: each a named preset, drawn once as a picture.

The api draws the same picture for the studio's preview (GET /api/layers/{id}/image.png), so the phone shows exactly
what the render overlays; only the entrance is played by CSS there. Keep the labels in step with
web/src/components/video/preview/layers.ts.
"""

import math
from dataclasses import dataclass

from PIL import Image, ImageDraw

from .markup import MarkupError, parse_scene_text
from .textbox import (
    FRAME_HEIGHT,
    FRAME_WIDTH,
    RED_COLOR,
    BoxStyle,
    Palette,
    TextFitError,
    _font,
    layout_text,
    render_box,
)

ANIMATION_SECONDS = 0.3
SLIDE_UP_PX = 120
SUPERSAMPLE = 4  # stickers are drawn this many times larger, then scaled down, for smooth edges
GREEN = "#16A34A"
YELLOW = "#FFD60A"
DARK = "#111111"


@dataclass(frozen=True)
class Named:
    label: str


@dataclass(frozen=True)
class TextStyle(Named):
    palette: Palette


@dataclass(frozen=True)
class Size(Named):
    text: BoxStyle
    sticker: int  # the sticker's longest side, in frame pixels


TEXT_STYLES: dict[str, TextStyle] = {
    "outline": TextStyle("Chữ viền", Palette(None, "#FFFFFF", YELLOW, outline="#000000")),
    "yellow": TextStyle("Hộp vàng", Palette(YELLOW, DARK, RED_COLOR)),
    "dark": TextStyle("Hộp đen", Palette((17, 17, 17, 224), "#FFFFFF", YELLOW)),
    "white": TextStyle("Hộp trắng", Palette("#FFFFFF", DARK, RED_COLOR)),
    "red": TextStyle("Hộp đỏ", Palette(RED_COLOR, "#FFFFFF", YELLOW)),
}

SIZES: dict[str, Size] = {
    "small": Size("Nhỏ", BoxStyle(max_size=48, min_size=36, max_lines=4), 160),
    "medium": Size("Vừa", BoxStyle(max_size=64, min_size=44, max_lines=4), 240),
    "large": Size("Lớn", BoxStyle(max_size=84, min_size=56, max_lines=3), 340),
}

STICKERS: dict[str, Named] = {
    "arrow_down": Named("Mũi tên xuống"),
    "arrow_right": Named("Mũi tên phải"),
    "ring": Named("Khoanh tròn"),
    "star": Named("Ngôi sao"),
    "heart": Named("Trái tim"),
    "check": Named("Dấu tích"),
    "cross": Named("Dấu X"),
    "new": Named("Nhãn MỚI"),
    "hot": Named("Nhãn HOT"),
    "sale": Named("Nhãn SALE"),
}

# How a layer comes in; every entrance but "none" also fades in over ANIMATION_SECONDS.
ANIMATIONS: dict[str, Named] = {
    "none": Named("Hiện ngay"),
    "fade": Named("Mờ dần"),
    "slide_up": Named("Trượt lên"),
    "slide_left": Named("Trượt từ trái"),
}


@dataclass(frozen=True)
class Layer:
    kind: str  # "text" or "sticker"
    text: str = ""
    sticker: str = ""
    start: float = 0.0  # seconds into its scene
    seconds: float = 2.0
    x: int = FRAME_WIDTH // 2  # its centre in the frame
    y: int = FRAME_HEIGHT // 2
    size: str = "medium"
    style: str = "outline"  # text only
    animation: str = "fade"


def render_layer(layer: Layer) -> Image.Image:
    """The layer as a transparent picture, as large as what it shows. Raises ValueError for text that will not fit."""
    if layer.kind == "text":
        try:
            lines = parse_scene_text(layer.text)
            layout = layout_text(lines, SIZES[layer.size].text)
        except (MarkupError, TextFitError) as err:
            raise ValueError(str(err)) from None
        return render_box(layout, TEXT_STYLES[layer.style].palette)
    return _sticker(layer.sticker, SIZES[layer.size].sticker)


def layer_corner(width: int, height: int, centre: tuple[int, int]) -> tuple[int, int]:
    """Where a layer's picture goes so it is centred on `centre` yet never leaves the frame."""
    left = min(max(centre[0] - width // 2, 0), max(FRAME_WIDTH - width, 0))
    top = min(max(centre[1] - height // 2, 0), max(FRAME_HEIGHT - height, 0))
    return left, top


def _sticker(name: str, side: int) -> Image.Image:
    big = side * SUPERSAMPLE
    if name in ("new", "hot", "sale"):
        return _badge(name, side)
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    edge = round(big * 0.04)
    if name in ("arrow_down", "arrow_right"):
        shaft, head = 0.32, 0.9
        points = [
            (big * (0.5 - shaft / 2), big * 0.05),
            (big * (0.5 + shaft / 2), big * 0.05),
            (big * (0.5 + shaft / 2), big * 0.5),
            (big * (0.5 + head / 2), big * 0.5),
            (big * 0.5, big * 0.95),
            (big * (0.5 - head / 2), big * 0.5),
            (big * (0.5 - shaft / 2), big * 0.5),
        ]
        draw.polygon(points, fill=RED_COLOR, outline="#FFFFFF", width=edge)
        if name == "arrow_right":
            image = image.rotate(90, resample=Image.Resampling.BICUBIC)
    elif name == "ring":
        width = round(big * 0.08)
        draw.ellipse((width, width, big - width, big - width), outline=RED_COLOR, width=width)
    elif name == "star":
        draw.polygon(_star_points(big), fill=YELLOW, outline=DARK, width=edge)
    elif name == "heart":
        r = big * 0.26
        draw.ellipse((big * 0.5 - 2 * r, big * 0.12, big * 0.5, big * 0.12 + 2 * r), fill=RED_COLOR)
        draw.ellipse((big * 0.5, big * 0.12, big * 0.5 + 2 * r, big * 0.12 + 2 * r), fill=RED_COLOR)
        draw.polygon([(big * 0.04, big * 0.42), (big * 0.96, big * 0.42), (big * 0.5, big * 0.92)], fill=RED_COLOR)
    elif name in ("check", "cross"):
        draw.ellipse((edge, edge, big - edge, big - edge), fill=GREEN if name == "check" else RED_COLOR)
        stroke = round(big * 0.1)
        if name == "check":
            draw.line([(big * 0.28, big * 0.52), (big * 0.44, big * 0.68), (big * 0.74, big * 0.36)], "#FFFFFF", stroke)
        else:
            draw.line([(big * 0.32, big * 0.32), (big * 0.68, big * 0.68)], "#FFFFFF", stroke)
            draw.line([(big * 0.68, big * 0.32), (big * 0.32, big * 0.68)], "#FFFFFF", stroke)
    else:
        raise ValueError(f"không có sticker {name!r}")
    return image.resize((side, side), Image.Resampling.LANCZOS)


def _star_points(big: int) -> list[tuple[float, float]]:
    points = []
    for index in range(10):
        radius = big * (0.47 if index % 2 == 0 else 0.2)
        angle = math.pi / 2 + index * math.pi / 5
        points.append((big / 2 + radius * math.cos(angle), big * 0.52 - radius * math.sin(angle)))
    return points


def _badge(name: str, side: int) -> Image.Image:
    """A word on a rounded label, as wide as `side`."""
    word, fill, ink = {
        "new": ("MỚI", GREEN, "#FFFFFF"),
        "hot": ("HOT", RED_COLOR, "#FFFFFF"),
        "sale": ("SALE", YELLOW, DARK),
    }[name]
    height = round(side * 0.46)
    font = _font(round(height * 0.62))
    image = Image.new("RGBA", (side, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, side - 1, height - 1), radius=height // 3, fill=fill)
    draw.text((side / 2, height / 2), word, font=font, fill=ink, anchor="mm")
    return image
