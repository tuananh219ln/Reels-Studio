"""The Page's logo on an article's photos (decisions 2026-11-15, "article photos and logo").

A brand (brands.py) keeps, besides the round badge burned into its videos, how its logo sits on a photo: one of nine
places, a width and a distance from the edges in % of the photo's width, an opacity, and a white version used when
the photo under the logo is darker than a threshold. The logo is the uploaded picture itself (its transparency kept),
not the video's round badge.

The stored photo never changes: the logo is laid on a copy when the article is posted, for the Page it is posted to,
and on the editor's preview. So a changed logo or setting reaches every article still to be posted, and one photo's
switch or own position changes only that photo.
"""

import io
import re
from dataclasses import dataclass, replace
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageStat

from .models import PHOTO_LOGO_POSITIONS, PHOTO_LOGO_SHAPES, ArticleImage, Brand

DEFAULT_POSITION = "bottom_right"
MIN_SIZE, MAX_SIZE = 3.0, 40.0  # % of the photo's width
MAX_MARGIN = 20.0
# A round or rounded logo is a badge: a white ring (6% of its diameter, at least 4 px) round the logo, which is never
# drawn smaller than 120 px across nor closer than 16 px to the edge.
MIN_BADGE = 120
MIN_BADGE_MARGIN = 16
RING = 0.06
ROUNDED_RADIUS = 0.22  # of the badge's side
SHADOW_OPACITY, SHADOW_BLUR, SHADOW_OFFSET = 0.25, 0.02, 0.01  # of the badge's diameter
DEFAULT_BORDER_COLOR = "#FFFFFF"
MIN_OPACITY = 0.1
JPEG_QUALITY = 92
PREVIEW_WIDTH = 800
# Facebook keeps photos up to 2048 px on the long side: a bigger one is shrunk here, so the logo keeps its share.
MAX_POSTED_SIDE = 2048
# The three shapes a member previews the logo on, with a light, a soft and a dark sample photo.
SAMPLE_RATIOS = {"1:1": (1080, 1080), "4:5": (1080, 1350), "1.91:1": (1200, 628)}
SAMPLE_COLOURS = {
    "1:1": ((0xF6, 0xC1, 0x6B), (0xF0, 0x8A, 0x6C)),
    "4:5": ((0xF2, 0xB8, 0xE0), (0xA8, 0xC0, 0xF0)),
    "1.91:1": ((0x3A, 0x3A, 0x3A), (0x0E, 0x0E, 0x0E)),
}


_HEX = re.compile(r"#[0-9A-Fa-f]{6}")


class LogoSettingsError(ValueError):
    pass


@dataclass(frozen=True)
class Look:
    position: str = DEFAULT_POSITION
    size: float = 12.0
    margin: float = 3.0
    opacity: float = 1.0
    alt_threshold: float | None = None
    shape: str = "circle"  # one of PHOTO_LOGO_SHAPES: "none" lays the logo as uploaded, the others make a badge
    border: bool = True
    border_color: str = DEFAULT_BORDER_COLOR
    shadow: bool = True

    @property
    def badge(self) -> bool:
        return self.shape != "none"


def look_of(brand: Brand) -> Look:
    return Look(
        brand.photo_logo_position,
        brand.photo_logo_size,
        brand.photo_logo_margin,
        brand.photo_logo_opacity,
        brand.photo_logo_alt_threshold,
        brand.photo_logo_shape,
        brand.photo_logo_border,
        brand.photo_logo_border_color,
        brand.photo_logo_shadow,
    )


def checked(look: Look) -> Look:
    """The settings as saved, or LogoSettingsError with the reason a member reads."""
    if look.position not in PHOTO_LOGO_POSITIONS:
        raise LogoSettingsError("Vị trí logo không hợp lệ")
    if not MIN_SIZE <= look.size <= MAX_SIZE:
        raise LogoSettingsError(f"Kích thước logo phải từ {MIN_SIZE:g}% đến {MAX_SIZE:g}% cạnh ngắn của ảnh")
    if not 0 <= look.margin <= MAX_MARGIN:
        raise LogoSettingsError(f"Lề phải từ 0% đến {MAX_MARGIN:g}% cạnh ngắn của ảnh")
    if not MIN_OPACITY <= look.opacity <= 1:
        raise LogoSettingsError(f"Độ mờ phải từ {round(MIN_OPACITY * 100)}% đến 100%")
    if look.alt_threshold is not None and not 0 <= look.alt_threshold <= 1:
        raise LogoSettingsError("Ngưỡng độ sáng phải từ 0 đến 1")
    if look.shape not in PHOTO_LOGO_SHAPES:
        raise LogoSettingsError("Kiểu logo không hợp lệ")
    if not _HEX.fullmatch(look.border_color):
        raise LogoSettingsError("Màu viền phải có dạng #RRGGBB")
    return look


def box(photo: tuple[int, int], logo: tuple[int, int], look: Look) -> tuple[int, int, int, int]:
    """Where the logo goes on a photo of size `photo`: (left, top, width, height), its width `look.size` % and its
    distance from the edges it sits by `look.margin` % of the photo's short side, so it looks the same on every
    shape of photo. A badge is square and never smaller than MIN_BADGE nor nearer an edge than MIN_BADGE_MARGIN."""
    width, height = photo
    base = min(width, height)
    if look.badge:
        logo_w = max(MIN_BADGE, round(base * look.size / 100))
        logo_h = logo_w
        margin = round(base * look.margin / 100)
        if look.margin > 0:
            margin = max(MIN_BADGE_MARGIN, margin)
    else:
        logo_w = max(1, round(base * look.size / 100))
        logo_h = max(1, round(logo_w * logo[1] / logo[0]))
        margin = round(base * look.margin / 100)
    row, _, column = look.position.partition("_")
    if look.position == "center":
        row, column = "middle", "center"
    left = {"left": margin, "center": (width - logo_w) // 2, "right": width - logo_w - margin}[column]
    top = {"top": margin, "middle": (height - logo_h) // 2, "bottom": height - logo_h - margin}[row]
    return left, top, logo_w, logo_h


def brightness(photo: Image.Image, area: tuple[int, int, int, int]) -> float:
    """The mean brightness (0 black – 1 white) of the photo under `area` (left, top, width, height)."""
    left, top, width, height = area
    region = photo.crop((left, top, left + width, top + height)).convert("L")
    return ImageStat.Stat(region).mean[0] / 255


def _logo_picture(path: Path) -> Image.Image:
    with Image.open(path) as source:
        return ImageOps.exif_transpose(source).convert("RGBA")


def _shape_mask(size: int, shape: str) -> Image.Image:
    """The badge's outline, drawn at 4x and shrunk so its edge is smooth."""
    big = size * 4
    mask = Image.new("L", (big, big), 0)
    draw = ImageDraw.Draw(mask)
    if shape == "circle":
        draw.ellipse((0, 0, big - 1, big - 1), fill=255)
    else:
        draw.rounded_rectangle((0, 0, big - 1, big - 1), radius=round(big * ROUNDED_RADIUS), fill=255)
    return mask.resize((size, size), Image.Resampling.LANCZOS)


def badge(logo: Path, diameter: int, look: Look) -> Image.Image:
    """The logo as a badge of `diameter` px (RGBA): the logo cut to the shape, cover-fitted and never stretched, with
    the ring round it. A transparent logo is laid on the ring's colour, so the badge is solid all through. The ring
    is `border_color` (white by default), 6% of the diameter and at least 4 px; with no border the logo fills it."""
    ring = max(4, round(diameter * RING)) if look.border else 0
    inner = diameter - 2 * ring
    colour = look.border_color if look.border else DEFAULT_BORDER_COLOR
    picture = ImageOps.fit(_logo_picture(logo), (inner, inner), Image.Resampling.LANCZOS)
    face = Image.new("RGBA", (inner, inner), colour)
    face.alpha_composite(picture)
    face.putalpha(_shape_mask(inner, look.shape))
    result = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
    solid = Image.new("RGBA", (diameter, diameter), colour)
    solid.putalpha(_shape_mask(diameter, look.shape))
    result.alpha_composite(solid)
    result.alpha_composite(face, (ring, ring))
    return result


def _shadow(shape: Image.Image, diameter: int) -> Image.Image:
    """A soft black shadow of a badge: 25% opaque, blurred by 2% of the diameter."""
    pad = round(diameter * SHADOW_BLUR * 3)
    alpha = Image.new("L", (diameter + 2 * pad,) * 2, 0)
    alpha.paste(shape.getchannel("A"), (pad, pad))
    alpha = alpha.filter(ImageFilter.GaussianBlur(diameter * SHADOW_BLUR)).point(lambda v: round(v * SHADOW_OPACITY))
    black = Image.new("RGBA", alpha.size, (0, 0, 0, 0))
    black.putalpha(alpha)
    return black


def lay(photo: Image.Image, logo: Path, alt: Path | None, look: Look) -> Image.Image:
    """The photo (RGB) with the logo on it. A badge shape lays the round or rounded badge; "none" lays the logo as
    uploaded, the white one when there is one and the photo under the logo is darker than the threshold."""
    picture = _logo_picture(logo)
    area = box(photo.size, picture.size, look)
    left, top, width, height = area
    result = photo.convert("RGB")
    if look.badge:
        picture = badge(logo, width, look)
        if look.opacity < 1:
            picture.putalpha(picture.getchannel("A").point(lambda value: round(value * look.opacity)))
        if look.shadow:
            shade = _shadow(picture, width)
            offset = round(width * SHADOW_OFFSET)
            pad = (shade.width - width) // 2
            if look.opacity < 1:
                shade.putalpha(shade.getchannel("A").point(lambda value: round(value * look.opacity)))
            result.paste(shade, (left - pad, top - pad + offset), shade)
        result.paste(picture, (left, top), picture)
        return result
    if alt is not None and look.alt_threshold is not None and brightness(photo, area) < look.alt_threshold:
        picture = _logo_picture(alt)
        area = box(photo.size, picture.size, look)
        left, top, width, height = area
    picture = picture.resize((width, height), Image.Resampling.LANCZOS)
    if look.opacity < 1:
        alpha = picture.getchannel("A").point(lambda value: round(value * look.opacity))
        picture.putalpha(alpha)
    result.paste(picture, (left, top), picture)
    return result


def _open(data: bytes) -> Image.Image:
    with Image.open(io.BytesIO(data)) as source:
        return ImageOps.exif_transpose(source).convert("RGB")


def _jpeg(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=JPEG_QUALITY)
    return buffer.getvalue()


@dataclass(frozen=True)
class BrandLogo:
    """A brand's logo files and settings, read once for every photo of an article."""

    logo: Path
    alt: Path | None
    look: Look


def logo_for_photo(brand_logo: BrandLogo | None, image: ArticleImage) -> BrandLogo | None:
    """The logo this photo gets: None when the Page has no logo or the photo's switch is off; its own position
    over the brand's."""
    if brand_logo is None or not image.logo_enabled:
        return None
    if image.logo_position:
        return replace(brand_logo, look=replace(brand_logo.look, position=image.logo_position))
    return brand_logo


def render(data: bytes, logo: BrandLogo | None, max_side: int = MAX_POSTED_SIDE) -> bytes:
    """The photo as posted: at most `max_side` on its long side, with the logo when there is one, as JPEG."""
    photo = _open(data)
    if max(photo.size) > max_side:
        photo.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    if logo is not None:
        photo = lay(photo, logo.logo, logo.alt, logo.look)
    return _jpeg(photo)


def sample(ratio: str, logo: BrandLogo | None) -> bytes:
    """One of the three sample photos (a light 1:1, a soft 4:5, a dark 1.91:1) with the logo, at most
    PREVIEW_WIDTH on its long side."""
    width, height = SAMPLE_RATIOS[ratio]
    start, end = SAMPLE_COLOURS[ratio]
    gradient = Image.linear_gradient("L").resize((width, height)).rotate(-45, expand=False, fillcolor=128)
    photo = Image.composite(Image.new("RGB", (width, height), end), Image.new("RGB", (width, height), start), gradient)
    if logo is not None:
        photo = lay(photo, logo.logo, logo.alt, logo.look)
    photo.thumbnail((PREVIEW_WIDTH, PREVIEW_WIDTH), Image.Resampling.LANCZOS)
    return _jpeg(photo)
