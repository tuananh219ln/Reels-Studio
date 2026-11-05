"""Scene previews and the video thumbnail, drawn with reels_render's own text box code.

The renderer's first frame of a scene is the photo cover-cropped to 1080×1920 at zoom 1.00 (or the clip's
frame at its start time) with the text box on top, so this is exactly that frame for the title scene (which
has no fade-in).
"""

import io
from pathlib import Path

from PIL import Image, ImageOps

from reels_render.markup import parse_scene_text
from reels_render.options import DEFAULT_OPTIONS, RenderOptions
from reels_render.textbox import (
    FRAME_HEIGHT,
    FRAME_WIDTH,
    layout_sized,
    place_box,
    render_box,
)

from .script_rules import text_problem

THUMBNAIL_SIZE = (540, 960)


Centre = list[int] | tuple[int, int] | None


def text_box(
    text: str, is_title: bool, options: RenderOptions = DEFAULT_OPTIONS, centre: Centre = None
) -> tuple[Image.Image, tuple[int, int]]:
    """The exact RGBA box image render_video overlays for this scene, and where it goes."""
    layout = layout_sized(parse_scene_text(text), options.title_text_size if is_title else options.text_size, is_title)
    palette = options.title_palette() if is_title else options.scene_palette()
    position = tuple(centre) if centre else None
    return render_box(layout, palette), place_box(layout.width, layout.height, position, is_title)


def compose_frame(
    image: Path | Image.Image,
    text: str,
    is_title: bool,
    options: RenderOptions = DEFAULT_OPTIONS,
    centre: Centre = None,
) -> Image.Image:
    """Cover-cropped photo (or clip frame) plus the text box; no box without text or while the text cannot render."""
    if isinstance(image, Image.Image):
        upright = image.convert("RGB")
    else:
        with Image.open(image) as source:
            source.load()
            upright = ImageOps.exif_transpose(source).convert("RGB")
    frame = ImageOps.fit(upright, (FRAME_WIDTH, FRAME_HEIGHT), Image.Resampling.BICUBIC, centering=(0.5, 0.5))
    size = options.title_text_size if is_title else options.text_size
    if text.strip() and text_problem(text, is_title, size) is None:
        box, position = text_box(text, is_title, options, centre)
        frame.paste(box, position, box)
    return _yuv420(frame)


def _yuv420(frame: Image.Image) -> Image.Image:
    """Halve the colour resolution like the MP4's yuv420p does; the red/yellow text edges otherwise differ."""
    luma, *chroma = frame.convert("YCbCr").split()
    half = (frame.width // 2, frame.height // 2)
    chroma = [
        plane.resize(half, Image.Resampling.BOX).resize(frame.size, Image.Resampling.BILINEAR) for plane in chroma
    ]
    return Image.merge("YCbCr", (luma, *chroma)).convert("RGB")


def jpeg_bytes(image: Image.Image, quality: int = 90) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=quality)
    return buffer.getvalue()


def thumbnail_bytes(
    image: Path | Image.Image, title_text: str, options: RenderOptions = DEFAULT_OPTIONS, centre: Centre = None
) -> bytes:
    """Drawn with the video's text box choices (video_options.render_options) and the title's place."""
    frame = compose_frame(image, title_text, is_title=True, options=options, centre=centre)
    return jpeg_bytes(frame.resize(THUMBNAIL_SIZE, Image.Resampling.LANCZOS), quality=85)
