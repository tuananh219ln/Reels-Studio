"""PC Shopee's compact text (docs/decisions/2026-11-27-pc-text-tiers.md): the title in three tiers (a small line, the main
line, a sub line, and an optional orange label) and a content scene's text in two (a numbered circle and the main line, then
a sub line). No box behind either. Drawn in one of the pc_text looks, as a picture the render lays like any text box."""

import re
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from .layout import DEFAULT_PROFILE, FRAME_HEIGHT, FRAME_WIDTH, PROFILES
from .markup import Run, normalize_text
from .pc_text import PAD, PRESETS, SPARKLE_STYLES, fitted_size, hex_rgb, line_style, render_line, sparkles, stack
from .textbox import FONT_PATH

TITLE_SIZES = (52, 104, 64)  # small, main, sub
TITLE_GAP = 0.08  # of the size
# Each title preset's sizes (small, main, sub) and the gap between its lines, of the size; a negative gap overlaps the lines
# (docs/decisions/2026-11-27-title-presets.md). Estimates from the spec's table, to compare with the five reels.
PRESET_TITLE = {
    "neon_outline_price": ((56, 128, 56), -0.12),
    "gold_metal": ((56, 116, 68), 0.04),
    "grunge_rainbow": ((64, 104, 60), 0.04),
    "esports_blue": ((56, 112, 64), -0.08),
}
ACCENT_EXTRA = 0.12  # of the size: more room under a negative gap when the lower line carries Vietnamese marks
PREFIX_SCALE = 0.42  # "^PHP 14,999": the first word at this share of the size, raised
TITLE_MAX_WIDTH = round(FRAME_WIDTH * 0.88)
TITLE_MAX_CHARS = 14  # a longer line still renders, shrunk to TITLE_MAX_WIDTH; the page warns (api checks)

SCENE_SIZES = (80, 54)  # main, sub
SCENE_MAX_CHARS, SCENE_MAX_SUB_WORDS = 16, 4
SCENE_CENTRE_LOW = (FRAME_WIDTH // 2, round(FRAME_HEIGHT * 0.68))  # "Dưới": the lower zone; else at the top
SCENE_MAX_WIDTH = PROFILES[DEFAULT_PROFILE].text_width
NUMBER_DIAMETER, NUMBER_SIZE, NUMBER_GAP = 76, 52, 16
# The video's "Cỡ chữ" (options.text_size, title_text_size) as a share of the sizes above: "large" is how it always was.
TEXT_SCALE = {"large": 1.0, "medium": 0.8, "small": 0.65}

ORANGE = hex_rgb("#FB7A14")
LABEL_RADIUS, LABEL_SIZE, LABEL_TILT = 16, 48, 6
_LABEL = re.compile(r"^\s*\[\[(.+?)\]\]\s*$")
_NUMBER = re.compile(r"^\s*(\d{1,2})\s*[.)]\s*")


@dataclass(frozen=True)
class TitleTiers:
    small: str
    main: str
    sub: str
    label: str


@dataclass(frozen=True)
class SceneTiers:
    number: str
    main: str
    sub: str


def _plain(line: list[Run]) -> str:
    return normalize_text("".join(run.text for run in line).strip())


_SPLIT = re.compile(r"\s*[:|,;]\s*")


def _split_one_line(text: str) -> tuple[str, str, str]:
    """A title written on one line, cut at ":", "|", "," and ";" into small / main / sub ("BLACK FRIDAY: 5 MÓN PC ĐÁNG SĂN,
    XEM TRƯỚC KHI MUA"). Three parts or more: the first is small, the second main and the rest the sub; two parts: a short
    first part (up to TITLE_MAX_CHARS) before a longer one is small and main, else main and sub; one: all main."""
    parts = [part for part in _SPLIT.split(text) if part.strip()]
    if len(parts) >= 3:
        return parts[0], parts[1], ", ".join(parts[2:])
    if len(parts) == 2:
        first, second = parts
        if len(first) <= TITLE_MAX_CHARS and len(second) > len(first):
            return first, second, ""
        return "", first, second
    return "", parts[0] if parts else "", ""


def parse_title(lines: list[list[Run]]) -> TitleTiers:
    """The title's lines as tiers: one line is cut at its punctuation (_split_one_line); two lines are main and sub; three or
    more small, main and sub (the rest joins the sub). A line written `[[-50%]]` is the orange label."""
    texts = [_plain(line) for line in lines if _plain(line)]
    label = ""
    rest: list[str] = []
    for text in texts:
        found = _LABEL.match(text)
        if found and not label:
            label = found.group(1).strip()
        else:
            rest.append(text)
    if len(rest) >= 3:
        small, main, sub = rest[0], rest[1], " ".join(rest[2:])
    elif len(rest) == 2:
        small, main, sub = "", rest[0], rest[1]
    else:
        small, main, sub = _split_one_line(rest[0] if rest else "")
    return TitleTiers(small, main, sub, label)


def parse_scene(lines: list[list[Run]]) -> SceneTiers:
    """A scene's text as the main line and the sub line, with the number the first line may start with ("3."). With two
    lines or more the first is the main one (the product's name) and the rest the sub (what it does), however the words
    are marked: a scene's `*marked*` words highlight the benefit, not the name. A single line with marked words has them
    as the main line and the rest as the sub (`*LOGITECH G304* không dây`); without any, the line is the main one."""
    number = ""
    rows: list[list[Run]] = []
    for index, line in enumerate(lines):
        if index == 0 and line and (found := _NUMBER.match(line[0].text)):
            number = found.group(1)
            line = [Run(line[0].text[found.end() :], line[0].red), *line[1:]]
        if any(run.text.strip() for run in line):
            rows.append(line)
    if not rows:
        return SceneTiers(number, "", "")
    text = lambda runs: normalize_text(" ".join(run.text.strip() for run in runs if run.text.strip()))  # noqa: E731
    if len(rows) >= 2:
        return SceneTiers(number, text(rows[0]), " ".join(text(row) for row in rows[1:]))
    marked = [run for run in rows[0] if run.red]
    plain = [run for run in rows[0] if not run.red]
    if marked and any(run.text.strip() for run in plain):
        return SceneTiers(number, text(marked), text(plain))
    return SceneTiers(number, text(rows[0]), "")


def _label(text: str) -> Image.Image:
    """The orange label: a rounded box, white text, tilted a little."""
    font = ImageFont.truetype(str(FONT_PATH), LABEL_SIZE)
    width, height = round(font.getlength(text)) + 48, LABEL_SIZE + 32
    box = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(box)
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=LABEL_RADIUS, fill=ORANGE)
    draw.text((width / 2, height / 2), text, font=font, fill=(255, 255, 255), anchor="mm")
    return box.rotate(LABEL_TILT, expand=True, resample=Image.Resampling.BICUBIC)


def _line(text: str, size: int, style: str, key: bool, index: int, max_width: int) -> Image.Image:
    """One title line. A line written `^PHP 14,999` draws its first word small and raised (the spec's superscript prefix)."""
    look = line_style(style, key, index)
    if not (style in PRESETS and text.startswith("^") and " " in text):
        return render_line(text.lstrip("^"), size, look, max_width)
    prefix, rest = text[1:].split(" ", 1)
    small_size = round(size * PREFIX_SCALE)
    small = render_line(prefix, small_size, look, max_width // 3)
    big = render_line(rest, size, look, max_width - small.width + 2 * PAD)
    overlap = 2 * PAD - 12  # the pictures' own padding overlaps, so the letters sit a normal space apart
    row = Image.new("RGBA", (small.width + big.width - overlap, big.height), (0, 0, 0, 0))
    row.alpha_composite(big, (small.width - overlap, 0))
    row.alpha_composite(small, (0, PAD // 4))  # top-aligned: the baseline shift of a superscript
    return row


MIN_FIT = 0.7  # a preset's line may shrink to this share of its size; a longer one is wrapped (the spec's rule 3)
SPARKLE_COUNT, SPARKLE_COLOUR = 14, "#FFF3B0"


def _wrapped(text: str) -> list[str]:
    """The text cut in two at the space nearest its middle (itself when it has no space)."""
    spaces = [at for at, char in enumerate(text) if char == " "]
    if not spaces:
        return [text]
    cut = min(spaces, key=lambda at: abs(at - len(text) / 2))
    return [text[:cut], text[cut + 1 :]]


def render_title(
    tiers: TitleTiers,
    style: str = "brand_navy",
    effects: bool = True,
    scale: float = 1.0,
    max_width: int = TITLE_MAX_WIDTH,
) -> Image.Image:
    """The three tiers stacked and centred, the label at the block's top right. Each line shrinks to fit `max_width`;
    in a title preset a line that would shrink under 70% is wrapped in two, and the whole block shrinks by one factor
    instead, so the lines keep their sizes' proportions. `effects` draws the preset's sparkles, where it has them; `scale`
    is the video's text size (TEXT_SCALE)."""
    base, gap = PRESET_TITLE.get(style, (TITLE_SIZES, TITLE_GAP))
    base = tuple(round(size * scale) for size in base)
    # (text, size, is the main line, the place for the look): a wrapped line's halves share the last two
    items = [
        (text, size, text == tiers.main, index)
        for index, (text, size) in enumerate((t, z) for z, t in zip(base, (tiers.small, tiers.main, tiers.sub)) if t)
    ]
    if style in PRESETS:
        wrapped = []
        for text, size, key, index in items:
            look = line_style(style, key, index)
            if fitted_size(text.lstrip("^"), size, look, max_width) < size * MIN_FIT and " " in text:
                wrapped += [(half, size, key, index) for half in _wrapped(text)]
            else:
                wrapped.append((text, size, key, index))
        items = wrapped
        factor = min(
            fitted_size(text.lstrip("^"), size, line_style(style, key, index), max_width) / size
            for text, size, key, index in items
        )
        items = [(text, max(24, round(size * factor)), key, index) for text, size, key, index in items]
    pictures = [_line(text, size, style, key, index, max_width) for text, size, key, index in items]
    gaps = [
        round((gap + (ACCENT_EXTRA if gap < 0 and not items[at + 1][0].isascii() else 0)) * items[at][1])
        for at in range(len(items) - 1)
    ]
    block = stack(pictures, gaps)
    if effects and style in SPARKLE_STYLES:
        stars = sparkles(block.size, hex_rgb(SPARKLE_COLOUR), SPARKLE_COUNT, 11)  # inside the picture's own padding
        stars.alpha_composite(block)  # the letters over the stars
        block = stars
    if tiers.label:
        label = _label(tiers.label)
        # The label keeps the block's clear margin (PAD) round it, so it stays inside the text's edges too.
        size = (max(block.width, label.width + 2 * PAD), block.height + label.height // 2 + PAD)
        canvas = Image.new("RGBA", size, (0, 0, 0, 0))
        canvas.alpha_composite(block, ((canvas.width - block.width) // 2, label.height // 2 + PAD))
        canvas.alpha_composite(label, (canvas.width - label.width - PAD, PAD))
        return canvas
    return block


def _circle(number: str, scale: float = 1.0) -> Image.Image:
    diameter = round(NUMBER_DIAMETER * scale)
    circle = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
    draw = ImageDraw.Draw(circle)
    draw.ellipse((0, 0, diameter - 1, diameter - 1), fill=ORANGE)
    font = ImageFont.truetype(str(FONT_PATH), round(NUMBER_SIZE * scale))
    draw.text((diameter / 2, diameter / 2), number, font=font, fill=(255, 255, 255), anchor="mm")
    return circle


def render_scene(
    tiers: SceneTiers, style: str = "neon_game", scale: float = 1.0, max_width: int = SCENE_MAX_WIDTH
) -> Image.Image:
    """The main line with the numbered circle at its left, and the sub line under, the whole block centred. `scale` is the
    video's text size (TEXT_SCALE); `max_width` the room between the text's side edges."""
    rows: list[Image.Image] = []
    sizes = [round(size * scale) for size in SCENE_SIZES]
    if tiers.main:
        beside = round((NUMBER_DIAMETER + NUMBER_GAP) * scale) if tiers.number else 0
        main = render_line(tiers.main, sizes[0], line_style(style, True, 0), max_width - beside)
        if tiers.number:
            circle = _circle(tiers.number, scale)
            # The circle keeps the same clear margin (PAD) at its left; the line's own overlaps the circle's side.
            left = circle.width + round(NUMBER_GAP * scale)
            row = Image.new("RGBA", (left + main.width, max(main.height, circle.height)), (0, 0, 0, 0))
            row.alpha_composite(main, (left, (row.height - main.height) // 2))
            row.alpha_composite(circle, (PAD, (row.height - circle.height) // 2))  # on top of the line's glow
            main = row
        rows.append(main)
    if tiers.sub:
        rows.append(render_line(tiers.sub, sizes[1], line_style(style, False, 1), max_width))
    if not rows:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    return stack(rows, [round(0.1 * sizes[0])] * (len(rows) - 1))


def title_problems(tiers: TitleTiers) -> list[str]:
    """Lines longer than TITLE_MAX_CHARS: they are shrunk to fit, so the page only warns."""
    return [text for text in (tiers.small, tiers.main, tiers.sub) if len(text) > TITLE_MAX_CHARS]


def scene_problems(tiers: SceneTiers) -> list[str]:
    problems = []
    if len(tiers.main) > SCENE_MAX_CHARS:
        problems.append(tiers.main)
    if len(tiers.sub.split()) > SCENE_MAX_SUB_WORDS:
        problems.append(tiers.sub)
    return problems
