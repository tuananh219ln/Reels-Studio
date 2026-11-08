"""Text, sticker and photo layers laid over a scene for their own seconds: each a named preset, drawn once as a picture.

A photo layer ("Ảnh món") shows its scene's own photo framed over a video with one backdrop ("Video xuyên suốt");
the render lays it on only in that mode.

The api draws the same picture for the studio's preview (GET /api/layers/{id}/image.png), so the phone shows exactly
what the render overlays; only the entrance is played by CSS there. Keep the labels in step with
web/src/components/video/preview/layers.ts.
"""

import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps, UnidentifiedImageError

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
    photo: int  # a photo's width, in frame pixels (35%, 48% and 65% of the frame)


TEXT_STYLES: dict[str, TextStyle] = {
    "outline": TextStyle("Chữ viền", Palette(None, "#FFFFFF", YELLOW, outline="#000000")),
    "yellow": TextStyle("Hộp vàng", Palette(YELLOW, DARK, RED_COLOR)),
    "dark": TextStyle("Hộp đen", Palette((17, 17, 17, 224), "#FFFFFF", YELLOW)),
    "white": TextStyle("Hộp trắng", Palette("#FFFFFF", DARK, RED_COLOR)),
    "red": TextStyle("Hộp đỏ", Palette(RED_COLOR, "#FFFFFF", YELLOW)),
}

SIZES: dict[str, Size] = {
    "small": Size("Nhỏ", BoxStyle(max_size=48, min_size=36, max_lines=4), 160, 380),
    "medium": Size("Vừa", BoxStyle(max_size=64, min_size=44, max_lines=4), 240, 520),
    "large": Size("Lớn", BoxStyle(max_size=84, min_size=56, max_lines=3), 340, 700),
}

# How a photo layer is framed. Every frame but "plain" gets a white edge and a soft shadow; "plain" keeps the photo
# as it is, for a product photo whose background is already transparent.
PHOTO_SHAPES: dict[str, Named] = {
    "rounded": Named("Bo góc"),
    "circle": Named("Tròn"),
    "square": Named("Vuông"),
    "plain": Named("Giữ nguyên"),
}
PHOTO_EDGE = 6  # the white edge, in frame pixels
PHOTO_SHADOW_PAD = 36  # room around the photo for its shadow
PHOTO_SHADOW_DROP = 10
PHOTO_SHADOW_BLUR = 14
PHOTO_SHADOW_ALPHA = 0.45
PHOTO_MAX_HEIGHT = 1100  # a tall photo is cut to this, so it never fills the frame from top to bottom

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
    kind: str  # "text", "sticker" or "photo"
    text: str = ""
    sticker: str = ""
    start: float = 0.0  # seconds into its scene
    seconds: float = 2.0
    x: int = FRAME_WIDTH // 2  # its centre in the frame
    y: int = FRAME_HEIGHT // 2
    size: str = "medium"
    style: str = "outline"  # a text layer's TEXT_STYLES, a photo layer's PHOTO_SHAPES
    animation: str = "fade"
    image: Path | None = None  # a photo layer's photo


def render_layer(layer: Layer, case: str = "upper") -> Image.Image:
    """The layer as a transparent picture, as large as what it shows, a text layer's letters in `case`
    (markup.TEXT_CASES, the video's scenes' "Dạng chữ"). Raises ValueError for text that will not fit."""
    if layer.kind == "text":
        try:
            lines = parse_scene_text(layer.text, case)
            layout = layout_text(lines, SIZES[layer.size].text)
        except (MarkupError, TextFitError) as err:
            raise ValueError(str(err)) from None
        return render_box(layout, TEXT_STYLES[layer.style].palette)
    if layer.kind == "photo":
        if layer.image is None:
            raise ValueError("lớp ảnh chưa có ảnh")
        return render_photo(layer.image, SIZES[layer.size].photo, layer.style)
    return _sticker(layer.sticker, SIZES[layer.size].sticker)


def render_photo(path: Path, width: int, shape: str) -> Image.Image:
    """The photo `width` pixels wide in its frame: cut square for "circle" and "square", with a white edge and a
    soft shadow below, transparent around it. Raises ValueError for a file that is not a photo."""
    try:
        with Image.open(path) as source:
            source.load()
            picture = ImageOps.exif_transpose(source).convert("RGBA")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as err:
        raise ValueError(f"ảnh hỏng hoặc không đọc được ({err})") from None
    if shape in ("circle", "square"):
        side = min(picture.size)
        left, top = (picture.width - side) // 2, (picture.height - side) // 2
        picture = picture.crop((left, top, left + side, top + side))
    height = max(1, round(width * picture.height / picture.width))
    if height > PHOTO_MAX_HEIGHT:
        keep = round(picture.width * PHOTO_MAX_HEIGHT / width)
        top = (picture.height - keep) // 2
        picture, height = picture.crop((0, top, picture.width, top + keep)), PHOTO_MAX_HEIGHT
    picture = picture.resize((width, height), Image.Resampling.LANCZOS)
    if shape == "plain":
        return picture
    radius = {"circle": min(width, height) // 2, "square": 0}.get(shape, round(min(width, height) * 0.08))
    outer = _shape_mask((width, height), radius, shape == "circle")
    inner_size = (width - 2 * PHOTO_EDGE, height - 2 * PHOTO_EDGE)
    inner = _shape_mask(inner_size, max(0, radius - PHOTO_EDGE), shape == "circle")
    card = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    card.putalpha(outer)
    photo = picture.convert("RGB").crop((PHOTO_EDGE, PHOTO_EDGE, width - PHOTO_EDGE, height - PHOTO_EDGE))
    card.paste(photo, (PHOTO_EDGE, PHOTO_EDGE), inner)
    pad = PHOTO_SHADOW_PAD
    canvas = Image.new("RGBA", (width + 2 * pad, height + 2 * pad), (0, 0, 0, 0))
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow.paste(
        Image.new("RGBA", (width, height), (0, 0, 0, round(255 * PHOTO_SHADOW_ALPHA))),
        (pad, pad + PHOTO_SHADOW_DROP),
        outer,
    )
    canvas = Image.alpha_composite(canvas, shadow.filter(ImageFilter.GaussianBlur(PHOTO_SHADOW_BLUR)))
    canvas.alpha_composite(card, (pad, pad))
    return canvas


def _shape_mask(size: tuple[int, int], radius: int, circle: bool) -> Image.Image:
    """A smooth-edged mask of the shape: drawn SUPERSAMPLE times larger, then scaled down."""
    big = (size[0] * SUPERSAMPLE, size[1] * SUPERSAMPLE)
    mask = Image.new("L", big, 0)
    draw = ImageDraw.Draw(mask)
    if circle:
        draw.ellipse((0, 0, big[0] - 1, big[1] - 1), fill=255)
    else:
        draw.rounded_rectangle((0, 0, big[0] - 1, big[1] - 1), radius=radius * SUPERSAMPLE, fill=255)
    return mask.resize(size, Image.Resampling.LANCZOS)


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
