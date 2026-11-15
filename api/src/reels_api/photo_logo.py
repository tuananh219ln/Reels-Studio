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
from dataclasses import dataclass, replace
from pathlib import Path

from PIL import Image, ImageOps, ImageStat

from .models import PHOTO_LOGO_POSITIONS, ArticleImage, Brand

DEFAULT_POSITION = "bottom_right"
MIN_SIZE, MAX_SIZE = 3.0, 40.0  # % of the photo's width
MAX_MARGIN = 20.0
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


class LogoSettingsError(ValueError):
    pass


@dataclass(frozen=True)
class Look:
    position: str = DEFAULT_POSITION
    size: float = 12.0
    margin: float = 3.0
    opacity: float = 1.0
    alt_threshold: float | None = None


def look_of(brand: Brand) -> Look:
    return Look(
        brand.photo_logo_position,
        brand.photo_logo_size,
        brand.photo_logo_margin,
        brand.photo_logo_opacity,
        brand.photo_logo_alt_threshold,
    )


def checked(look: Look) -> Look:
    """The settings as saved, or LogoSettingsError with the reason a member reads."""
    if look.position not in PHOTO_LOGO_POSITIONS:
        raise LogoSettingsError("Vị trí logo không hợp lệ")
    if not MIN_SIZE <= look.size <= MAX_SIZE:
        raise LogoSettingsError(f"Kích thước logo phải từ {MIN_SIZE:g}% đến {MAX_SIZE:g}% chiều rộng ảnh")
    if not 0 <= look.margin <= MAX_MARGIN:
        raise LogoSettingsError(f"Lề phải từ 0% đến {MAX_MARGIN:g}% chiều rộng ảnh")
    if not MIN_OPACITY <= look.opacity <= 1:
        raise LogoSettingsError(f"Độ mờ phải từ {round(MIN_OPACITY * 100)}% đến 100%")
    if look.alt_threshold is not None and not 0 <= look.alt_threshold <= 1:
        raise LogoSettingsError("Ngưỡng độ sáng phải từ 0 đến 1")
    return look


def box(photo: tuple[int, int], logo: tuple[int, int], look: Look) -> tuple[int, int, int, int]:
    """Where the logo goes on a photo of size `photo`: (left, top, width, height), its width `look.size` % of the
    photo's and `look.margin` % of the photo's width from the edges it sits by."""
    width, height = photo
    logo_w = max(1, round(width * look.size / 100))
    logo_h = max(1, round(logo_w * logo[1] / logo[0]))
    margin = round(width * look.margin / 100)
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


def lay(photo: Image.Image, logo: Path, alt: Path | None, look: Look) -> Image.Image:
    """The photo (RGB) with the logo on it; the white logo when there is one and the photo under the logo is darker
    than the threshold."""
    picture = _logo_picture(logo)
    area = box(photo.size, picture.size, look)
    if alt is not None and look.alt_threshold is not None and brightness(photo, area) < look.alt_threshold:
        picture = _logo_picture(alt)
        area = box(photo.size, picture.size, look)
    left, top, width, height = area
    picture = picture.resize((width, height), Image.Resampling.LANCZOS)
    if look.opacity < 1:
        alpha = picture.getchannel("A").point(lambda value: round(value * look.opacity))
        picture.putalpha(alpha)
    result = photo.convert("RGB")
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
    """One of the three sample photos (a light 1:1, a soft 4:5, a dark 1.91:1) with the logo, PREVIEW_WIDTH wide."""
    width, height = SAMPLE_RATIOS[ratio]
    start, end = SAMPLE_COLOURS[ratio]
    gradient = Image.linear_gradient("L").resize((width, height)).rotate(-45, expand=False, fillcolor=128)
    photo = Image.composite(Image.new("RGB", (width, height), end), Image.new("RGB", (width, height), start), gradient)
    if logo is not None:
        photo = lay(photo, logo.logo, logo.alt, logo.look)
    photo.thumbnail((PREVIEW_WIDTH, PREVIEW_WIDTH), Image.Resampling.LANCZOS)
    return _jpeg(photo)
