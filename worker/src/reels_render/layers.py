"""Text, sticker and photo layers laid over a scene for their own seconds: each a named preset, drawn once as a picture.

A photo layer ("Ảnh món") shows its scene's own photo framed over a video with one backdrop ("Video xuyên suốt");
the render lays it on only in that mode. A photo layer of style "half" ("Ảnh chèn") shows a photo of its own over
the backdrop: a square with rounded corners, `height` percent of the frame on each side (so always narrower than the
frame), cut to fill it, centred across, and moved only up and down; the render lays it under the scene's text box and
the other layers.

The api draws the same picture for the studio's preview (GET /api/layers/{id}/image.png), so the phone shows exactly
what the render overlays; only the entrance is played by CSS there. Keep the labels in step with
web/src/components/video/preview/layers.ts.
"""

import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps, UnidentifiedImageError

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

# "Ảnh chèn": a photo layer's style apart from PHOTO_SHAPES, since its photo is its own and its shape fixed.
HALF = "half"
HALF_LABEL = "Ảnh chèn"
HALF_X = FRAME_WIDTH // 2  # its centre across, always
# Its size ("Cỡ ảnh"): each side in percent of the frame's height; 45% is 864 px, so it never reaches the side edges.
HALF_HEIGHT_DEFAULT, HALF_HEIGHT_MIN, HALF_HEIGHT_MAX = 32, 30, 45
HALF_RADIUS = 36  # its rounded corners, in frame pixels; no border (owner's choice, 2026-11-12)


# "Thẻ" (2026-11-15, the comment-reading pages): a screenshot card of its own (a Threads post) kept whole, never cut
# or stretched, centred across and hung from its top edge (`y` is that edge, not a centre), under the scene's text
# like an inset photo, on a slide video as on a backdrop. Its size is its width in percent of the frame's width (kept
# in the layer's `height` field); a card too tall for CARD_MAX_HEIGHT is scaled down to it, narrower. Transparent
# rows stay transparent, so a card drawn with its lower part cleared shows only its upper part at the same scale.
CARD = "card"
CARD_LABEL = "Thẻ"
CARD_WIDTH_DEFAULT, CARD_WIDTH_MIN, CARD_WIDTH_MAX = 90, 50, 100
CARD_TOP_DEFAULT = 220  # below the platform's top bar
CARD_MAX_HEIGHT = 1500  # clear of the platform's caption and buttons at the bottom


def half_height(percent: float = HALF_HEIGHT_DEFAULT) -> int:
    """An inset photo's side in frame pixels from its percent of the frame's height (32% is 614 px, 38% is 730)."""
    return round(FRAME_HEIGHT * min(max(percent, HALF_HEIGHT_MIN), HALF_HEIGHT_MAX) / 100)


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
    # The kitchen set (owner, 2026-11-15): also what covers a blurred patch the scene's text leaves showing.
    "leaf": Named("Lá xanh"),
    "bowl": Named("Bát canh"),
    "chopsticks": Named("Đôi đũa"),
    "tea": Named("Chén trà"),
    "apple": Named("Quả táo"),
    "flower": Named("Bông hoa"),
}
KITCHEN_STICKERS = ("leaf", "bowl", "chopsticks", "tea", "apple", "flower")

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
    height: int = HALF_HEIGHT_DEFAULT  # an inset photo's size: its side, in percent of the frame's height

    @property
    def half(self) -> bool:
        return is_half(self.kind, self.style)

    @property
    def card(self) -> bool:
        return is_card(self.kind, self.style)

    @property
    def inset(self) -> bool:
        """Laid under the scene's text, in the seconds of its own picture: an inset photo or a card."""
        return self.half or self.card


def is_half(kind: str, style: str) -> bool:
    """A photo layer "Ảnh chèn nửa khung"."""
    return kind == "photo" and style == HALF


def is_card(kind: str, style: str) -> bool:
    """A photo layer "Thẻ"."""
    return kind == "photo" and style == CARD


def card_width(percent: float = CARD_WIDTH_DEFAULT) -> int:
    """A card's width in frame pixels from its percent of the frame's width."""
    return round(FRAME_WIDTH * min(max(percent, CARD_WIDTH_MIN), CARD_WIDTH_MAX) / 100)


def card_size(width: int, height: int, percent: float = CARD_WIDTH_DEFAULT) -> tuple[int, int]:
    """The card's size in the frame for a picture `width` × `height`: its width percent, or less when that makes it
    taller than CARD_MAX_HEIGHT; never stretched."""
    wide = card_width(percent)
    tall = max(1, round(wide * height / max(width, 1)))
    if tall > CARD_MAX_HEIGHT:
        wide, tall = max(1, round(wide * CARD_MAX_HEIGHT / tall)), CARD_MAX_HEIGHT
    return wide, tall


def card_corner(width: int, height: int, top: int) -> tuple[int, int]:
    """Where a card goes: centred across, its top edge at `top`, kept inside the frame."""
    return (FRAME_WIDTH - width) // 2, min(max(top, 0), max(FRAME_HEIGHT - height, 0))


def half_y(y: float, height: int = HALF_HEIGHT_DEFAULT) -> int:
    """The centre of a half-frame photo kept inside the frame: flush with the top edge to flush with the bottom."""
    tall = half_height(height)
    return round(min(max(y, tall // 2), FRAME_HEIGHT - tall // 2))


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
        if layer.half:
            return render_half(layer.image, layer.height)
        if layer.card:
            return render_card(layer.image, layer.height)
        return render_photo(layer.image, SIZES[layer.size].photo, layer.style)
    return _sticker(layer.sticker, SIZES[layer.size].sticker)


def _open_photo(path: Path) -> Image.Image:
    try:
        with Image.open(path) as source:
            source.load()
            return ImageOps.exif_transpose(source).convert("RGBA")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as err:
        raise ValueError(f"ảnh hỏng hoặc không đọc được ({err})") from None


def render_half(path: Path, height: int = HALF_HEIGHT_DEFAULT) -> Image.Image:
    """ "Ảnh chèn": the photo scaled to cover a square `height` percent of the frame's height on each side and cut in
    the middle, never stretched, with rounded corners and no border, transparent only outside those corners. Raises
    ValueError for a file that is not a photo."""
    side = half_height(height)
    picture = _open_photo(path).convert("RGB")
    card = ImageOps.fit(picture, (side, side), Image.Resampling.LANCZOS, centering=(0.5, 0.5)).convert("RGBA")
    card.putalpha(_shape_mask((side, side), HALF_RADIUS, False))
    return card


def render_card(path: Path, percent: float = CARD_WIDTH_DEFAULT) -> Image.Image:
    """ "Thẻ": the picture whole at its card size (card_size), with its own transparency. Raises ValueError for a file
    that is not a photo."""
    picture = _open_photo(path)
    return picture.resize(card_size(picture.width, picture.height, percent), Image.Resampling.LANCZOS)


def render_photo(path: Path, width: int, shape: str) -> Image.Image:
    """The photo `width` pixels wide in its frame: cut square for "circle" and "square", with a white edge and a
    soft shadow below, transparent around it. Raises ValueError for a file that is not a photo."""
    picture = _open_photo(path)
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
    elif name in KITCHEN_STICKERS:
        _kitchen(draw, name, big, edge)
    else:
        raise ValueError(f"không có sticker {name!r}")
    return image.resize((side, side), Image.Resampling.LANCZOS)


LEAF_GREEN = "#2E9E4F"
BOWL_ORANGE = "#E8833A"
WOOD = "#9C6233"
TEA_GREEN = "#8DB33A"
APPLE_RED = "#D62D2D"
PETAL_PINK = "#F06C9B"
STEAM = "#FFFFFF"


def _kitchen(draw: ImageDraw.ImageDraw, name: str, big: int, edge: int) -> None:
    """The kitchen stickers, flat shapes with a white edge like the others, on a `big` square."""
    white = "#FFFFFF"

    def steam(xs: list[float], top: float, bottom: float) -> None:
        width = round(big * 0.035)
        for x in xs:
            points = [(big * (x + 0.03 * math.sin(i)), big * (bottom - (bottom - top) * i / 6)) for i in range(7)]
            draw.line(points, fill=DARK, width=width + edge, joint="curve")
            draw.line(points, fill=STEAM, width=width, joint="curve")

    if name == "leaf":
        # A leaf leaning right: two arcs meeting at the tip, a vein down the middle.
        # Two overlapping circles: where both are is a leaf pointed at both ends.
        left, right = Image.new("L", (big, big), 0), Image.new("L", (big, big), 0)
        ImageDraw.Draw(left).ellipse((big * -0.08, big * 0.12, big * 0.72, big * 0.88), fill=255)
        ImageDraw.Draw(right).ellipse((big * 0.28, big * 0.12, big * 1.08, big * 0.88), fill=255)
        leaf = ImageChops.multiply(left, right).rotate(-35, resample=Image.Resampling.BICUBIC)
        outline = leaf.filter(ImageFilter.MaxFilter(edge * 2 + 1))
        draw.bitmap((0, 0), outline, fill=white)
        draw.bitmap((0, 0), leaf, fill=LEAF_GREEN)
        draw.line([(big * 0.34, big * 0.76), (big * 0.66, big * 0.24)], fill=white, width=round(big * 0.04))
    elif name == "bowl":
        steam([0.36, 0.5, 0.64], 0.06, 0.36)
        box = (big * 0.08, big * 0.18, big * 0.92, big * 0.9)
        draw.chord(box, 0, 180, fill=BOWL_ORANGE, outline=white, width=edge)
        draw.ellipse((big * 0.08, big * 0.48, big * 0.92, big * 0.62), fill="#F6C28B", outline=white, width=edge)
        draw.rounded_rectangle(
            (big * 0.36, big * 0.86, big * 0.64, big * 0.94),
            radius=big * 0.03,
            fill=BOWL_ORANGE,
            outline=white,
            width=edge,
        )
    elif name == "chopsticks":
        stick = round(big * 0.07)
        for start, end in (((0.22, 0.08), (0.62, 0.94)), ((0.4, 0.06), (0.78, 0.92))):
            points = [(big * start[0], big * start[1]), (big * end[0], big * end[1])]
            draw.line(points, fill=white, width=stick + 2 * edge)
            draw.line(points, fill=WOOD, width=stick)
    elif name == "tea":
        steam([0.4, 0.54], 0.06, 0.32)
        draw.ellipse((big * 0.66, big * 0.46, big * 0.92, big * 0.74), outline=white, width=round(big * 0.09))
        draw.ellipse((big * 0.66, big * 0.46, big * 0.92, big * 0.74), outline="#E9E3D5", width=round(big * 0.05))
        draw.rounded_rectangle(
            (big * 0.14, big * 0.38, big * 0.76, big * 0.9),
            radius=big * 0.12,
            fill="#E9E3D5",
            outline=white,
            width=edge,
        )
        draw.ellipse((big * 0.18, big * 0.38, big * 0.72, big * 0.5), fill=TEA_GREEN)
    elif name == "apple":
        draw.ellipse((big * 0.1, big * 0.26, big * 0.58, big * 0.92), fill=APPLE_RED, outline=white, width=edge)
        draw.ellipse((big * 0.42, big * 0.26, big * 0.9, big * 0.92), fill=APPLE_RED, outline=white, width=edge)
        draw.ellipse((big * 0.2, big * 0.32, big * 0.8, big * 0.88), fill=APPLE_RED)
        draw.line([(big * 0.5, big * 0.32), (big * 0.54, big * 0.1)], fill=WOOD, width=round(big * 0.05))
        draw.ellipse((big * 0.55, big * 0.08, big * 0.82, big * 0.24), fill=LEAF_GREEN, outline=white, width=edge)
    else:  # flower
        for index in range(5):
            angle = math.pi / 2 + index * 2 * math.pi / 5
            cx, cy = big * (0.5 + 0.24 * math.cos(angle)), big * (0.5 - 0.24 * math.sin(angle))
            r = big * 0.2
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=PETAL_PINK, outline=white, width=edge)
        draw.ellipse((big * 0.37, big * 0.37, big * 0.63, big * 0.63), fill=YELLOW, outline=white, width=edge)


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
