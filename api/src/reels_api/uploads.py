"""Checks for files members upload: the type is read from the bytes, never from the name."""

import io

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from .errors import ApiError

MAX_IMAGE_BYTES = 15 * 1024 * 1024
IMAGE_FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
MAX_IMAGE_PIXELS = Image.MAX_IMAGE_PIXELS  # about 89 megapixels, far above any phone photo under 15 MB
_READ_ERRORS = (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError)


class UploadRejected(ValueError):
    pass


def image_extension(data: bytes) -> str:
    """The file extension for a JPG/PNG/WebP photo that Pillow can fully decode."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            kind = image.format
            # A small file can decode to gigabytes (a "decompression bomb"); Pillow only warns below
            # twice its limit, so the size from the header is checked before decoding anything.
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise UploadRejected(f"Ảnh quá lớn: tối đa {MAX_IMAGE_PIXELS // 1_000_000} megapixel")
            image.load()
    except UploadRejected:
        raise
    except _READ_ERRORS:
        raise UploadRejected("Ảnh phải là JPG, PNG hoặc WebP và không bị hỏng") from None
    if kind not in IMAGE_FORMATS:
        raise UploadRejected("Ảnh phải là JPG, PNG hoặc WebP và không bị hỏng")
    return IMAGE_FORMATS[kind]


def read_limited(upload: UploadFile, max_bytes: int, too_large: str) -> bytes:
    # Starlette has already spooled the part to disk; reading one byte past the limit is enough to refuse it.
    data = upload.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ApiError(413, "file_too_large", too_large)
    return data
