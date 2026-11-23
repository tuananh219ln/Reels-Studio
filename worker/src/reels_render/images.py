from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from .errors import InputError
from .framing import COVER, compose, plan_frame, unpadded

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


def normalize_image(source: Path, target: Path, label: str) -> None:
    """Bake EXIF orientation into the pixels, because FFmpeg ignores the EXIF tag."""
    _upright(source, label).save(target, "JPEG", quality=JPEG_QUALITY)


def fit_image(
    source: Path,
    target: Path,
    label: str,
    fit: str,
    text_height: int,
    centre: tuple[int, int] | None,
    min_top: int | None,
    crop_offset: float | None = None,
) -> tuple[int, int] | None:
    """The scene's photo made ready for FFmpeg as its "image_fit" asks (framing.py): a photo to cover-crop as before,
    or the whole 1080x1920 frame with the blurred copy under it. Returns where the text box goes when nobody placed
    it (`centre` is a member's or the video's place, which only says above or below the photo), None for the
    template's place."""
    upright = _upright(source, label)
    if fit == COVER:
        upright.save(target, "JPEG", quality=JPEG_QUALITY)
        return None
    picture = unpadded(upright, fit)
    framing = plan_frame(picture.width, picture.height, fit, text_height, centre, min_top, crop_offset)
    if framing.kind != COVER:
        picture = compose(picture, framing)
    picture.save(target, "JPEG", quality=JPEG_QUALITY)
    return framing.text_centre


def is_image(source: Path) -> bool:
    try:
        with Image.open(source) as image:
            image.load()
    except _READ_ERRORS:
        return False
    return True
