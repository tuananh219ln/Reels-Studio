"""How a scene's photo fills the 1080x1920 frame ("Khung ảnh", owner's spec 2026-11-23).

A photo close to the frame's shape is cover-cropped, as every photo used to be. A wider one is no longer blown up
and cut at both sides: it is laid across the frame's full width over a blurred, darkened copy of itself, with a
soft shadow under it, and the scene's text goes on the blurred part above (or below) it instead of over the food.
Photos between 3:4 and about 4:3 are cut to a square first, so every such scene of a video puts its photo and its
text at the same place; wider ones keep their shape. A 9:16 photo that is itself an older blurred-padding frame
(a real picture in a middle band, blur above and below) has its band taken out first, so it is not padded twice.

Everything here is Pillow only, shared by the render (render.py) and the app's previews, so both show the same
frame. The render hands FFmpeg two layers (`layers`): the blurred copy with the shadow, as the scene's photo at
1080x1920 (its cover crop changes nothing), and the photo alone, laid in its box. The photo zooms inside its box and
the copy under it half as far (PHOTO_ZOOM_SHARE, BACKDROP_ZOOM_SHARE of the video's own zoom), so the box never moves
towards the text; the first frame is `compose`, which the previews draw.
"""

import math
import statistics
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps, ImageStat

from .textbox import FRAME_HEIGHT, FRAME_WIDTH, SAFE_ZONE

# What a scene asks for ("image_fit"): "auto" chooses by the photo's shape; the others force one way.
COVER, WHOLE, SQUARE = "cover", "whole", "square"
IMAGE_FITS = ("auto", COVER, WHOLE, SQUARE)
FRAME_RATIO = FRAME_WIDTH / FRAME_HEIGHT
# "auto": narrower than 3:4 fills the frame; up to about 4:3 is cut square; wider keeps its shape.
SQUARE_FROM = 0.745
SQUARE_UP_TO = 1.34
GAP = 40  # between the text box and the photo
# The spec's 1.06 for the photo and 1.03 for the copy under it, as shares of the default 1.12 zoom: applied to
# whatever zoom the video chose, with its own motion (zoom in or out, pan, handheld...).
PHOTO_ZOOM_SHARE = 0.5
BACKDROP_ZOOM_SHARE = 0.25
# The blurred copy under the photo: scaled past cover so its blurred edges never show, then darkened.
BACKDROP_ZOOM = 1.08
BACKDROP_SMALL = (270, 480)  # blurred at a quarter size: much faster, and the eye cannot tell at this strength
BACKDROP_BLUR = 11  # the spec's 45 px at full size
BACKDROP_BRIGHTNESS = 0.70
BACKDROP_SATURATION = 1.10
SHADOW_OFFSET = 14
SHADOW_BLUR = 24
SHADOW_OPACITY = 0.6
# A photo enlarged to the frame is sharpened a little (Lanczos then unsharp mask), as the spec's "Nâng HD" without AI.
UNSHARP = ImageFilter.UnsharpMask(radius=2, percent=120, threshold=2)
# Finding an older padded frame: rows measured at this width; padding is this much smoother than the real band.
PROBE_WIDTH = 540
PADDING_TOLERANCE = 0.03  # of the 9:16 ratio
SHARP_FACTOR = 3
MIN_SHARP = 3.0  # mean edge strength (0-255) a row needs, whatever the padding measures
BAND_SHARE = (0.30, 0.85)
MIN_PADDING_SHARE = 0.05  # each side's blurred rows, of the height
# "Ảnh mờ, nên thay ảnh khác": the variance of the Laplacian of the photo as shown (1080 px wide, sharpened when
# enlarged) under the spec's starting value, and also under BLURRY_RATIO times the photo's grey spread: a sharp photo
# with little texture (white tofu on a white board) has a low variance too, but not for its contrast. A photo almost
# one colour (spread under FLAT_SPREAD) has nothing to judge and never warns. To be tuned on the team's photos.
BLURRY_BELOW = 40.0
BLURRY_RATIO = 0.6
FLAT_SPREAD = 8.0
LAPLACIAN = ImageFilter.Kernel((3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0], scale=1, offset=128)


@dataclass(frozen=True)
class Framing:
    """Where things go on the frame. `kind` is what was done (COVER, WHOLE or SQUARE). `crop` is the part of the
    (unpadded) photo used, (left, top, right, bottom); `picture` where it lies on the frame (x, y, width, height),
    None for COVER. `text_centre` is where the text box goes when nobody placed it, None: the template's place."""

    kind: str
    crop: tuple[int, int, int, int]
    picture: tuple[int, int, int, int] | None
    text_centre: tuple[int, int] | None


def choose_kind(width: int, height: int, fit: str) -> str:
    """The way a photo of this size fills the frame for the scene's "image_fit"."""
    if fit != "auto":
        return fit
    ratio = width / height
    if ratio < SQUARE_FROM:
        return COVER
    return SQUARE if ratio <= SQUARE_UP_TO else WHOLE


def plan_frame(
    width: int,
    height: int,
    fit: str,
    text_height: int,
    centre: tuple[int, int] | None = None,
    min_top: int | None = None,
    crop_offset: float | None = None,
) -> Framing:
    """Where a photo of `width` x `height` goes. The text sits above the photo unless it was placed in the frame's
    lower half (`centre`, a member's or the video's place); `text_height` is its box's (0: no text, the photo is
    centred). `min_top` is where a content scene's text may start while the channel logo is on. `crop_offset` slides
    the square along the photo's longer side, 0 to 1 (None: the middle)."""
    kind = choose_kind(width, height, fit)
    if kind == COVER:
        return Framing(COVER, (0, 0, width, height), None, None)
    crop = (0, 0, width, height)
    if kind == SQUARE:
        side = min(width, height)
        slide = 0.5 if crop_offset is None else min(max(crop_offset, 0.0), 1.0)
        start = round((max(width, height) - side) * slide)
        crop = (start, 0, start + side, side) if width > height else (0, start, side, start + side)
    shown_w, shown_h = crop[2] - crop[0], crop[3] - crop[1]
    picture_w = min(FRAME_WIDTH, round(FRAME_HEIGHT * shown_w / shown_h))
    # Even sizes and places, so the photo lines up with the MP4's half-size colour planes when FFmpeg lays it.
    picture_w -= picture_w % 2
    picture_h = min(FRAME_HEIGHT, 2 * round(picture_w * shown_h / shown_w / 2))
    x = (FRAME_WIDTH - picture_w) // 4 * 2
    if text_height <= 0:
        return Framing(kind, crop, (x, (FRAME_HEIGHT - picture_h) // 4 * 2, picture_w, picture_h), None)
    y, text_top = _place(picture_h, text_height, centre is not None and centre[1] >= FRAME_HEIGHT // 2, min_top)
    y -= y % 2
    return Framing(kind, crop, (x, y, picture_w, picture_h), (FRAME_WIDTH // 2, text_top + text_height // 2))


def _place(picture_h: int, text_h: int, below: bool, min_top: int | None) -> tuple[int, int]:
    """The photo's top and the text box's top. Text and photo fit the safe zone together: centred there as one
    group. Otherwise the text keeps to the zone's edge and the photo comes right after it, up to the frame's edge,
    where it may run under the text when it is too tall."""
    top, bottom = max(SAFE_ZONE[1], min_top or 0), SAFE_ZONE[3]
    group = text_h + GAP + picture_h
    if group <= bottom - top:
        start = top + (bottom - top - group) // 2
        return (start, start + picture_h + GAP) if below else (start + text_h + GAP, start)
    if below:
        return max(0, bottom - text_h - GAP - picture_h), bottom - text_h
    return min(top + text_h + GAP, FRAME_HEIGHT - picture_h), top


def strip_padding(image: Image.Image) -> Image.Image:
    """The real picture of a 9:16 frame padded with its own blur above and below; any other photo unchanged."""
    band = padded_band(image)
    return image if band is None else image.crop((0, band[0], image.width, band[1]))


def padded_band(image: Image.Image) -> tuple[int, int] | None:
    """The rows (top, bottom) of the sharp band of a 9:16 frame that is blurred above and below it; None when the
    photo is not such a frame. Each row's sharpness is its mean edge strength; the padding is the top and bottom
    tenth, and the band runs from the first to the last row clearly sharper than it."""
    if abs(image.width / image.height - FRAME_RATIO) > FRAME_RATIO * PADDING_TOLERANCE:
        return None
    probe_h = round(image.height * PROBE_WIDTH / image.width)
    gray = image.convert("L").resize((PROBE_WIDTH, probe_h), Image.Resampling.BILINEAR)
    # FIND_EDGES copies the border pixels, so they are left out.
    edges = gray.filter(ImageFilter.FIND_EDGES).crop((1, 1, PROBE_WIDTH - 1, probe_h - 1))
    rows = list(edges.resize((1, edges.height), Image.Resampling.BOX).tobytes())
    count = len(rows)
    tenth = max(1, count // 10)
    threshold = max(SHARP_FACTOR * statistics.median(rows[:tenth] + rows[-tenth:]), MIN_SHARP)
    sharp = [index for index, value in enumerate(rows) if value > threshold]
    if not sharp:
        return None
    first, last = sharp[0], sharp[-1]
    share = (last - first + 1) / count
    margin = MIN_PADDING_SHARE * count
    if not BAND_SHARE[0] <= share <= BAND_SHARE[1] or first < margin or count - 1 - last < margin:
        return None
    scale = image.height / probe_h
    # +1 for the border row left out above; the band's bottom is the row after its last sharp one.
    return math.floor((first + 1) * scale), min(image.height, math.ceil((last + 2) * scale))


def sharpness(image: Image.Image) -> tuple[float, float] | None:
    """How sharp the photo looks once laid across the frame: the variance of the Laplacian of its grey at 1080 px
    wide, after the same Lanczos and unsharp mask the framing gives an enlarged photo, and the grey's spread. None for
    a photo almost one colour, which cannot be judged."""
    gray = image.convert("L")
    spread = ImageStat.Stat(gray).stddev[0]
    if spread < FLAT_SPREAD:
        return None
    shown = gray.resize(
        (FRAME_WIDTH, max(1, round(image.height * FRAME_WIDTH / image.width))), Image.Resampling.LANCZOS
    )
    if FRAME_WIDTH > image.width:
        shown = shown.filter(UNSHARP)
    return ImageStat.Stat(shown.filter(LAPLACIAN)).var[0], spread


def is_blurry(image: Image.Image) -> bool:
    """The photo looks soft even after sharpening: worth replacing."""
    measured = sharpness(image)
    if measured is None:
        return False
    variance, spread = measured
    return variance < BLURRY_BELOW and variance < BLURRY_RATIO * spread


def compose(image: Image.Image, framing: Framing) -> Image.Image:
    """The 1080x1920 frame for a WHOLE or SQUARE framing of `image`: its blurred copy, the shadow, the photo."""
    canvas, picture = layers(image, framing)
    canvas.paste(picture, framing.picture[:2])
    return canvas


def layers(image: Image.Image, framing: Framing) -> tuple[Image.Image, Image.Image]:
    """The two layers of a WHOLE or SQUARE framing: the 1080x1920 blurred copy with the photo's shadow on it, and the
    photo alone at its size in the frame (Lanczos, sharpened when enlarged), to lay at framing.picture."""
    canvas = backdrop(image)
    x, y, width, height = framing.picture
    shadow = Image.new("L", BACKDROP_SMALL, 0)
    quarter = BACKDROP_SMALL[0] / FRAME_WIDTH
    ImageDraw.Draw(shadow).rectangle(
        [
            x * quarter,
            (y + SHADOW_OFFSET) * quarter,
            (x + width) * quarter,
            (y + height + SHADOW_OFFSET) * quarter,
        ],
        fill=round(255 * SHADOW_OPACITY),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(SHADOW_BLUR * quarter))
    canvas.paste((0, 0, 0), (0, 0), shadow.resize(canvas.size, Image.Resampling.BICUBIC))
    picture = image.resize((width, height), Image.Resampling.LANCZOS, box=framing.crop)
    if width > framing.crop[2] - framing.crop[0]:
        picture = picture.filter(UNSHARP)
    return canvas, picture


def backdrop(image: Image.Image) -> Image.Image:
    """The whole photo (never the square cut of it) covering the frame a little past its edges, blurred, a bit more
    colourful and darkened, so the sharp photo and white or yellow text stand out on it."""
    scale = max(FRAME_WIDTH / image.width, FRAME_HEIGHT / image.height) * BACKDROP_ZOOM
    seen_w, seen_h = FRAME_WIDTH / scale, FRAME_HEIGHT / scale
    left, top = (image.width - seen_w) / 2, (image.height - seen_h) / 2
    small = image.resize(BACKDROP_SMALL, Image.Resampling.BILINEAR, box=(left, top, left + seen_w, top + seen_h))
    small = small.filter(ImageFilter.GaussianBlur(BACKDROP_BLUR))
    small = ImageEnhance.Color(small).enhance(BACKDROP_SATURATION)
    small = ImageEnhance.Brightness(small).enhance(BACKDROP_BRIGHTNESS)
    return small.resize((FRAME_WIDTH, FRAME_HEIGHT), Image.Resampling.BICUBIC)


def unpadded(image: Image.Image, fit: str) -> Image.Image:
    """The photo the framing works on: a forced cover keeps the photo exactly as it was rendered before."""
    return image if fit == COVER else strip_padding(image)


def frame_photo(
    image: Image.Image,
    fit: str,
    text_height: int,
    centre: tuple[int, int] | None = None,
    min_top: int | None = None,
    crop_offset: float | None = None,
) -> tuple[Image.Image, Framing]:
    """The upright RGB photo fitted to the 1080x1920 frame, and how. COVER is cropped from the centre like the
    render's FFmpeg chain does it (for previews; the render itself hands COVER photos to FFmpeg unchanged)."""
    source = unpadded(image, fit)
    framing = plan_frame(source.width, source.height, fit, text_height, centre, min_top, crop_offset)
    if framing.kind == COVER:
        return ImageOps.fit(source, (FRAME_WIDTH, FRAME_HEIGHT), Image.Resampling.BICUBIC), framing
    return compose(source, framing), framing
