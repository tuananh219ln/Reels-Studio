from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from .errors import InputError
from .framing import COVER, choose_kind, layers, plan_frame, unpadded
from .layout import DEFAULT_PROFILE, PROFILES, Profile

_READ_ERRORS = (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError)
JPEG_QUALITY = 95


def _upright(source: Path, label: str) -> Image.Image:
    """The photo as RGB with its EXIF orientation baked into the pixels, because FFmpeg ignores the EXIF tag."""
    try:
        with Image.open(source) as image:
            image.load()
            return ImageOps.exif_transpose(image).convert("RGB")
    except _READ_ERRORS as err:
        raise InputError(f"{label}: ảnh hỏng hoặc không đọc được {source} ({err})") from None


@dataclass(frozen=True)
class Fitted:
    """What fit_image made. `text_centre`: where the text box goes when nobody placed it (None: the template's place).
    A framed photo also has `picture`, the photo alone, to lay at `box` (x, y, width, height) over the target, which
    is then its blurred copy."""

    text_centre: tuple[int, int] | None = None
    picture: Path | None = None
    box: tuple[int, int, int, int] | None = None


def normalize_image(source: Path, target: Path, label: str) -> None:
    """Bake EXIF orientation into the pixels, because FFmpeg ignores the EXIF tag."""
    _upright(source, label).save(target, "JPEG", quality=JPEG_QUALITY)


def photo_is_framed(source: Path, label: str, fit: str) -> bool:
    """The photo will be laid over its blurred copy (not cover-cropped) for `fit`, as fit_image will do it."""
    if fit == COVER:
        return False
    picture = unpadded(_upright(source, label), fit)
    return choose_kind(picture.width, picture.height, fit) != COVER


def fit_image(
    source: Path,
    target: Path,
    label: str,
    fit: str,
    text_height: int,
    centre: tuple[int, int] | None,
    crop_offset: float | None = None,
    reserve: int | None = None,
    profile: Profile = PROFILES[DEFAULT_PROFILE],
) -> Fitted:
    """The scene's photo made ready for FFmpeg as its "image_fit" asks (framing.py): a photo to cover-crop as before,
    or its blurred copy at 1080x1920 in `target` and the photo alone beside it (`<target>-photo.jpg`). `centre` is a
    member's or the video's place for the text, which only says above or below the photo."""
    upright = _upright(source, label)
    if fit == COVER:
        upright.save(target, "JPEG", quality=JPEG_QUALITY)
        return Fitted()
    picture = unpadded(upright, fit)
    framing = plan_frame(picture.width, picture.height, fit, text_height, centre, crop_offset, reserve, profile)
    if framing.kind == COVER:
        picture.save(target, "JPEG", quality=JPEG_QUALITY)
        return Fitted(framing.text_centre)
    copy, photo = layers(picture, framing)
    copy.save(target, "JPEG", quality=JPEG_QUALITY)
    photo_path = target.with_name(f"{target.stem}-photo.jpg")
    photo.save(photo_path, "JPEG", quality=JPEG_QUALITY)
    return Fitted(framing.text_centre, picture=photo_path, box=framing.picture)


def is_image(source: Path) -> bool:
    try:
        with Image.open(source) as image:
            image.load()
    except _READ_ERRORS:
        return False
    return True
