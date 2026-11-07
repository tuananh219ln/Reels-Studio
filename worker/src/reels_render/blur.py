"""A clip's blurred boxes ("Làm mờ vùng" on a clip scene): a logo or a channel name burned into the clip, made
unreadable for the whole scene. Each box is [x, y, width, height] as fractions of the rendered 1080x1920 frame, so a
member draws it over the frame exactly as the video will show it. The render blurs with FFmpeg's boxblur; the
previews in the app blur the same pixels with Pillow, so what is drawn is what is rendered."""

import math

from PIL import Image, ImageFilter

from .errors import InputError
from .textbox import FRAME_HEIGHT, FRAME_WIDTH

MAX_BLUR_BOXES = 10
# A box under this many pixels across is a slip of the mouse; FFmpeg's boxblur also needs some room.
MIN_BLUR_PIXELS = 8
Box = tuple[float, float, float, float]


def parse_blur(value: object, label: str) -> tuple[Box, ...]:
    """The scene's "video_blur" list, checked; empty when absent."""
    if value is None:
        return ()
    if not isinstance(value, list) or len(value) > MAX_BLUR_BOXES:
        raise InputError(f'{label}: "video_blur" phải là danh sách tối đa {MAX_BLUR_BOXES} vùng [x, y, rộng, cao]')
    boxes = []
    for item in value:
        if (
            not isinstance(item, list)
            or len(item) != 4
            or not all(
                isinstance(number, int | float) and not isinstance(number, bool) and math.isfinite(number)
                for number in item
            )
        ):
            raise InputError(f'{label}: mỗi vùng của "video_blur" là [x, y, rộng, cao] theo tỉ lệ 0–1 của khung')
        x, y, width, height = (float(number) for number in item)
        if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > 1.0001 or y + height > 1.0001:
            raise InputError(f'{label}: vùng {item} của "video_blur" nằm ngoài khung')
        boxes.append((x, y, width, height))
    return tuple(boxes)


def pixel_boxes(boxes: tuple[Box, ...]) -> list[tuple[int, int, int, int]]:
    """Each box in the frame's pixels, on even numbers (the video's colour planes are half size), at least
    MIN_BLUR_PIXELS across and inside the frame."""
    result = []
    for x, y, width, height in boxes:
        left = min(max(0, round(x * FRAME_WIDTH / 2) * 2), FRAME_WIDTH - MIN_BLUR_PIXELS)
        top = min(max(0, round(y * FRAME_HEIGHT / 2) * 2), FRAME_HEIGHT - MIN_BLUR_PIXELS)
        right = min(FRAME_WIDTH, max(left + MIN_BLUR_PIXELS, round((x + width) * FRAME_WIDTH / 2) * 2))
        bottom = min(FRAME_HEIGHT, max(top + MIN_BLUR_PIXELS, round((y + height) * FRAME_HEIGHT / 2) * 2))
        result.append((left, top, right - left, bottom - top))
    return result


def radius(width: int, height: int) -> int:
    """Strong enough that letters cannot be read, and within what boxblur allows for the half-size colour planes."""
    return max(1, min(width, height) // 6)


def ffmpeg_blur(source: str, target: str, boxes: tuple[Box, ...], prefix: str) -> str:
    """Filtergraph statements from the `source` pad (a 1080x1920 yuv420p stream) to the `target` pad with every box
    blurred: each box is cut out, blurred and laid back on the frame. `prefix` keeps the pads of one scene apart."""
    placed = pixel_boxes(boxes)
    if not placed:
        return f"[{source}]null[{target}]"
    copies = "".join(f"[{prefix}c{index}]" for index in range(len(placed)))
    statements = [f"[{source}]split={len(placed) + 1}[{prefix}m0]{copies}"]
    for index, (left, top, width, height) in enumerate(placed):
        strength = radius(width, height)
        statements.append(
            f"[{prefix}c{index}]crop={width}:{height}:{left}:{top},"
            f"boxblur=luma_radius={strength}:luma_power=2[{prefix}b{index}]"
        )
        out = target if index == len(placed) - 1 else f"{prefix}m{index + 1}"
        statements.append(f"[{prefix}m{index}][{prefix}b{index}]overlay={left}:{top}[{out}]")
    return ";".join(statements)


def blur_image(frame: Image.Image, boxes: tuple[Box, ...]) -> Image.Image:
    """The 1080x1920 frame with its boxes blurred like the render does it, for the app's previews."""
    if not boxes:
        return frame
    result = frame.copy()
    for left, top, width, height in pixel_boxes(boxes):
        region = result.crop((left, top, left + width, top + height))
        # Two box blurs come close to boxblur's luma_power=2.
        strength = radius(width, height)
        softened = region.filter(ImageFilter.BoxBlur(strength)).filter(ImageFilter.BoxBlur(strength))
        result.paste(softened, (left, top))
    return result
