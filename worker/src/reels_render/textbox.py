import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .markup import Run

FONT_PATH = Path(__file__).parent / "fonts" / "BeVietnamPro-Black.ttf"

FRAME_WIDTH = 1080
FRAME_HEIGHT = 1920
MAX_BOX_WIDTH = 960
PAD_X = 44
PAD_Y = 30
RADIUS = 22
LEADING = 0.06  # of font size, keeps descenders off the stacked marks of the next line
SCENE_BOX_BOTTOM = 1440

BOX_COLOR = "#FFD60A"
TEXT_COLOR = "#111111"
RED_COLOR = "#E10600"


@dataclass(frozen=True)
class Palette:
    box: str | tuple[int, int, int, int]
    text: str
    accent: str  # the *marked* words


# The text box styles members choose from (options.TEXT_STYLES). "yellow" is the original template.
PALETTES = {
    "yellow": Palette(BOX_COLOR, TEXT_COLOR, RED_COLOR),
    "white": Palette("#FFFFFF", TEXT_COLOR, RED_COLOR),
    "dark": Palette((17, 17, 17, 224), "#FFFFFF", "#FFD60A"),
    "red": Palette("#E10600", "#FFFFFF", "#FFD60A"),
}

# Narration captions: white on a dark, see-through box, the spoken word in yellow.
CAPTION_SIZE = 58
CAPTION_MAX_LINES = 2
CAPTION_PAD_X = 28
CAPTION_PAD_Y = 16
CAPTION_GAP = 28  # between the captions and the text box under them
CAPTION_BOX = (0, 0, 0, 170)
CAPTION_TEXT = "#FFFFFF"
CAPTION_LIT = "#FFD60A"

# Stacked Vietnamese capitals rise above the font ascender; measured once per size.
_TALL_PROBE = "ỔẪẶỖỠỄỂẤẨ"


@dataclass(frozen=True)
class BoxStyle:
    max_size: int
    min_size: int
    max_lines: int


TITLE_STYLE = BoxStyle(max_size=96, min_size=64, max_lines=5)
SCENE_STYLE = BoxStyle(max_size=84, min_size=60, max_lines=3)


class TextFitError(ValueError):
    pass


@dataclass(frozen=True)
class TextLayout:
    font_size: int
    lines: list[list[Run]]
    line_widths: list[float]
    overshoot: int
    line_height: int
    width: int
    height: int


@lru_cache(maxsize=64)
def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_PATH), size)


def _overshoot(font: ImageFont.FreeTypeFont) -> int:
    top = font.getbbox(_TALL_PROBE, anchor="ls")[1]
    return max(0, -top - font.getmetrics()[0])


def _sizes(style: BoxStyle) -> list[int]:
    return [*range(style.max_size, style.min_size, -2), style.min_size]


def _split_words(line: list[Run]) -> list[list[Run]]:
    """Words keep their colour runs, so `*CANXI*,` stays one word with a red and a black part."""
    words: list[list[Run]] = [[]]
    for run in line:
        pieces = run.text.split(" ")
        for index, piece in enumerate(pieces):
            if index:
                words.append([])
            if piece:
                words[-1].append(Run(piece, run.red))
    return [word for word in words if word]


def _wrap(line: list[Run], font: ImageFont.FreeTypeFont, max_width: float) -> list[tuple[list[Run], float]] | None:
    space = font.getlength(" ")
    wrapped: list[tuple[list[Run], float]] = []
    current: list[Run] = []
    current_width = 0.0
    for word in _split_words(line):
        word_width = sum(font.getlength(run.text) for run in word)
        if word_width > max_width:
            return None
        if current and current_width + space + word_width <= max_width:
            current += [Run(" ", False), *word]
            current_width += space + word_width
        else:
            if current:
                wrapped.append((current, current_width))
            current, current_width = list(word), word_width
    wrapped.append((current, current_width))
    return wrapped


def layout_text(lines: list[list[Run]], style: BoxStyle) -> TextLayout:
    max_text_width = MAX_BOX_WIDTH - 2 * PAD_X
    needed_lines = 0
    for size in _sizes(style):
        font = _font(size)
        wrapped: list[tuple[list[Run], float]] = []
        for line in lines:
            line_wrap = _wrap(line, font, max_text_width)
            if line_wrap is None:
                break
            wrapped += line_wrap
        else:
            needed_lines = len(wrapped)
            if needed_lines <= style.max_lines:
                ascent, descent = font.getmetrics()
                overshoot = _overshoot(font)
                line_height = overshoot + ascent + descent + round(LEADING * size)
                return TextLayout(
                    font_size=size,
                    lines=[runs for runs, _ in wrapped],
                    line_widths=[width for _, width in wrapped],
                    overshoot=overshoot,
                    line_height=line_height,
                    width=math.ceil(max(width for _, width in wrapped)) + 2 * PAD_X,
                    height=line_height * len(wrapped) - round(LEADING * size) + 2 * PAD_Y,
                )
    if needed_lines:
        raise TextFitError(
            f"chữ quá dài: ở cỡ tối thiểu {style.min_size}px vẫn cần {needed_lines} dòng, tối đa {style.max_lines} dòng"
        )
    raise TextFitError(f"có từ quá dài, không vừa hộp rộng {MAX_BOX_WIDTH}px ở cỡ tối thiểu {style.min_size}px")


def render_box(layout: TextLayout, palette: Palette = PALETTES["yellow"]) -> Image.Image:
    image = Image.new("RGBA", (layout.width, layout.height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, layout.width - 1, layout.height - 1), radius=RADIUS, fill=palette.box)
    font = _font(layout.font_size)
    ascent = font.getmetrics()[0]
    for index, (runs, line_width) in enumerate(zip(layout.lines, layout.line_widths)):
        x = (layout.width - line_width) / 2
        baseline = PAD_Y + layout.overshoot + ascent + index * layout.line_height
        for run in runs:
            fill = palette.accent if run.red else palette.text
            draw.text((x, baseline), run.text, font=font, fill=fill, anchor="ls")
            x += font.getlength(run.text)
    return image


def empty_box() -> Image.Image:
    """A transparent pixel for a scene without text, so the filter graph keeps one image and one box per scene."""
    return Image.new("RGBA", (1, 1), (0, 0, 0, 0))


def title_box_position(width: int, height: int) -> tuple[int, int]:
    return (FRAME_WIDTH - width) // 2, (FRAME_HEIGHT - height) // 2


def scene_box_position(width: int, height: int) -> tuple[int, int]:
    return (FRAME_WIDTH - width) // 2, SCENE_BOX_BOTTOM - height


def caption_lines(words: list[str]) -> list[list[str]] | None:
    """The words wrapped to the caption width at the caption size; None when they need more than two lines."""
    font = _font(CAPTION_SIZE)
    max_width = MAX_BOX_WIDTH - 2 * CAPTION_PAD_X
    lines: list[list[str]] = [[]]
    for word in words:
        trial = " ".join([*lines[-1], word])
        if lines[-1] and font.getlength(trial) > max_width:
            lines.append([word])
        else:
            lines[-1].append(word)
    return lines if len(lines) <= CAPTION_MAX_LINES else None


def render_caption(lines: list[list[str]], lit: int | None) -> Image.Image:
    """One caption phrase; `lit` counts words across the lines and marks the one being spoken (None: none)."""
    font = _font(CAPTION_SIZE)
    ascent, descent = font.getmetrics()
    overshoot = _overshoot(font)
    line_height = overshoot + ascent + descent
    widths = [font.getlength(" ".join(line)) for line in lines]
    width = math.ceil(max(widths)) + 2 * CAPTION_PAD_X
    height = line_height * len(lines) + 2 * CAPTION_PAD_Y
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=RADIUS, fill=CAPTION_BOX)
    space = font.getlength(" ")
    number = 0
    for index, (line, line_width) in enumerate(zip(lines, widths)):
        x = (width - line_width) / 2
        baseline = CAPTION_PAD_Y + overshoot + ascent + index * line_height
        for word in line:
            draw.text((x, baseline), word, font=font, fill=CAPTION_LIT if number == lit else CAPTION_TEXT, anchor="ls")
            x += font.getlength(word) + space
            number += 1
    return image
