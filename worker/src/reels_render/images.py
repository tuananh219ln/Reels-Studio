from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from .errors import InputError

_READ_ERRORS = (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError)


def normalize_image(source: Path, target: Path, label: str) -> None:
    """Bake EXIF orientation into the pixels, because FFmpeg ignores the EXIF tag."""
    try:
        with Image.open(source) as image:
            image.load()
            upright = ImageOps.exif_transpose(image).convert("RGB")
    except _READ_ERRORS as err:
        raise InputError(f"{label}: ảnh hỏng hoặc không đọc được {source} ({err})") from None
    upright.save(target, "JPEG", quality=95)


def is_image(source: Path) -> bool:
    try:
        with Image.open(source) as image:
            image.load()
    except _READ_ERRORS:
        return False
    return True
