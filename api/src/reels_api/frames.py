"""Scene previews and the video thumbnail, drawn with reels_render's own text box code.

The renderer's first frame of a scene is the photo fitted to 1080×1920 at zoom 1.00 (cover-cropped, or laid over its
blurred copy by "Khung ảnh": reels_render.framing) or the clip's frame at its start time, with the text box on top, so
this is exactly that frame for the title scene (which has no fade-in).
"""

import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from reels_render.framing import COVER, Framing, choose_kind, frame_photo, is_blurry, plan_frame, unpadded
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
    text: str,
    is_title: bool,
    options: RenderOptions = DEFAULT_OPTIONS,
    centre: Centre = None,
    min_top: int | None = None,
) -> tuple[Image.Image, tuple[int, int]]:
    """The exact RGBA box image render_video overlays for this scene, and where it goes."""
    case = options.title_text_case if is_title else options.text_case
    layout = layout_sized(
        parse_scene_text(text, case), options.title_text_size if is_title else options.text_size, is_title
    )
    palette = options.title_palette() if is_title else options.scene_palette()
    position = tuple(centre) if centre else None
    return render_box(layout, palette), place_box(layout.width, layout.height, position, is_title, min_top)


def text_height(text: str, is_title: bool, options: RenderOptions = DEFAULT_OPTIONS) -> int:
    """The height of the scene's text box as the render lays it; 0 without text or while it cannot render."""
    size = options.title_text_size if is_title else options.text_size
    case = options.title_text_case if is_title else options.text_case
    if not text.strip() or text_problem(text, is_title, size, case) is not None:
        return 0
    return layout_sized(parse_scene_text(text, case), size, is_title).height


@lru_cache(maxsize=1024)
def _photo_facts(path: str) -> tuple[tuple[int, int], tuple[int, int], bool] | None:
    """The upright photo's size, its size with its padding taken off, and whether it looks blurry once framed; a
    stored photo never changes under its key, so it is measured once per process. None for a file that cannot be
    read."""
    try:
        with Image.open(path) as source:
            source.load()
            upright = ImageOps.exif_transpose(source).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None
    picture = unpadded(upright, "auto")
    return upright.size, picture.size, is_blurry(picture)


def _photo_size(path: str, stripped: bool) -> tuple[int, int] | None:
    """The upright photo's size, after its padding is taken off when `stripped`; None for a file that cannot be read."""
    facts = _photo_facts(path)
    return None if facts is None else facts[1 if stripped else 0]


def photo_blurry(path: Path) -> bool:
    """ "Ảnh mờ, nên thay ảnh khác": the photo still looks soft at the frame's width (reels_render.framing.is_blurry);
    False for a file that cannot be read (that has its own reason)."""
    facts = _photo_facts(str(path))
    return facts is not None and facts[2]


def plan_photo(
    path: Path,
    fit: str,
    text: str,
    is_title: bool,
    options: RenderOptions = DEFAULT_OPTIONS,
    centre: Centre = None,
    min_top: int | None = None,
    crop_offset: float | None = None,
    reserve: int | None = None,
) -> tuple[Framing, tuple[int, int]] | None:
    """How the render frames the photo at `path` (reels_render.framing), and the photo's (unpadded) size; None for a
    file that cannot be read."""
    size = _photo_size(str(path), fit != COVER)
    if size is None:
        return None
    height = text_height(text, is_title, options)
    return plan_frame(*size, fit, height, tuple(centre) if centre else None, min_top, crop_offset, reserve), size


def is_framed(path: Path, fit: str) -> bool:
    """The render lays the photo at `path` over its blurred copy for `fit`, not filling the frame; False for a file
    that cannot be read."""
    size = _photo_size(str(path), fit != COVER)
    return size is not None and fit != COVER and choose_kind(*size, fit) != COVER


def compose_frame(
    image: Path | Image.Image,
    text: str,
    is_title: bool,
    options: RenderOptions = DEFAULT_OPTIONS,
    centre: Centre = None,
    under: list[tuple[Image.Image, tuple[int, int]]] | None = None,
    fit: str = COVER,
    min_top: int | None = None,
    crop_offset: float | None = None,
    show_text: bool = True,
    reserve: int | None = None,
) -> Image.Image:
    """The fitted photo (or clip frame) plus the text box; no box without text or while the text cannot render.
    `under`: pictures laid on the frame under the text box, at their corners (a card, as the render lays it). `fit`,
    `min_top`, `crop_offset` and `reserve` (the video's tallest framed text box) frame a photo as the render does (reels_render.framing); `show_text` False leaves the
    box out but still frames the photo around it, for dragging the box."""
    if isinstance(image, Image.Image):
        upright = image.convert("RGB")
    else:
        with Image.open(image) as source:
            source.load()
            upright = ImageOps.exif_transpose(source).convert("RGB")
    if fit == COVER:
        frame = ImageOps.fit(upright, (FRAME_WIDTH, FRAME_HEIGHT), Image.Resampling.BICUBIC, centering=(0.5, 0.5))
    else:
        position = tuple(centre) if centre else None
        frame, framing = frame_photo(
            upright, fit, text_height(text, is_title, options), position, min_top, crop_offset, reserve
        )
        centre = centre or framing.text_centre
    for picture, corner in under or []:
        frame.paste(picture, corner, picture if picture.mode == "RGBA" else None)
    size = options.title_text_size if is_title else options.text_size
    case = options.title_text_case if is_title else options.text_case
    if show_text and text.strip() and text_problem(text, is_title, size, case) is None:
        box, position = text_box(text, is_title, options, centre, min_top)
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
