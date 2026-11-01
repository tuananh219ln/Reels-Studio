"""Scene previews and the video thumbnail, drawn with reels_render's own text box code.

The renderer's first frame of a scene is the photo cover-cropped to 1080×1920 at zoom 1.00 (or the clip's
frame at its start time) with the text box on top, so this is exactly that frame for the title scene (which
has no fade-in).
"""

import io
from pathlib import Path

from PIL import Image, ImageOps

from reels_render.markup import parse_scene_text
from reels_render.textbox import (
    FRAME_HEIGHT,
    FRAME_WIDTH,
    SCENE_STYLE,
    TITLE_STYLE,
    layout_text,
    palette_for,
    render_box,
    scene_box_position,
    title_box_position,
    title_palette,
)

from .script_rules import text_problem

THUMBNAIL_SIZE = (540, 960)
DEFAULT_LOOK = ("yellow", "auto", "same")


def text_box(
    text: str, is_title: bool, look: tuple[str, str, str] = DEFAULT_LOOK
) -> tuple[Image.Image, tuple[int, int]]:
    """The exact RGBA box image render_video overlays for this scene, and where it goes."""
    layout = layout_text(parse_scene_text(text), TITLE_STYLE if is_title else SCENE_STYLE)
    place = title_box_position if is_title else scene_box_position
    palette = title_palette(*look) if is_title else palette_for(*look[:2])
    return render_box(layout, palette), place(layout.width, layout.height)


def compose_frame(
    image: Path | Image.Image, text: str, is_title: bool, look: tuple[str, str, str] = DEFAULT_LOOK
) -> Image.Image:
    """Cover-cropped photo (or clip frame) plus the text box; no box without text or while the text cannot render."""
    if isinstance(image, Image.Image):
        upright = image.convert("RGB")
    else:
        with Image.open(image) as source:
            source.load()
            upright = ImageOps.exif_transpose(source).convert("RGB")
    frame = ImageOps.fit(upright, (FRAME_WIDTH, FRAME_HEIGHT), Image.Resampling.BICUBIC, centering=(0.5, 0.5))
    if text.strip() and text_problem(text, is_title) is None:
        box, position = text_box(text, is_title, look)
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


def thumbnail_bytes(image: Path | Image.Image, title_text: str, look: tuple[str, str, str] = DEFAULT_LOOK) -> bytes:
    """`look` is the text box style, text colour and title style (video_options.text_look)."""
    frame = compose_frame(image, title_text, is_title=True, look=look)
    return jpeg_bytes(frame.resize(THUMBNAIL_SIZE, Image.Resampling.LANCZOS), quality=85)
