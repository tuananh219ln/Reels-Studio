"""PC Shopee's compact text (docs/decisions/2026-11-27-pc-text-tiers.md): the title in three tiers (a small line, the main
line, a sub line, and an optional orange label) and a content scene's text in two (a numbered circle and the main line, then
a sub line). No box behind either. Drawn in one of the pc_text looks, as a picture the render lays like any text box."""

import re
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from .markup import Run, normalize_text
from .pc_text import PAD, hex_rgb, line_style, render_line, stack
from .textbox import FONT_PATH, FRAME_HEIGHT, FRAME_WIDTH

TITLE_SIZES = (56, 110, 72)  # small, main, sub
TITLE_GAP = 0.08  # of the size
TITLE_MAX_WIDTH = round(FRAME_WIDTH * 0.88)
TITLE_CENTRE = (FRAME_WIDTH // 2, round(FRAME_HEIGHT * 0.22))
TITLE_MAX_CHARS = 14  # a longer line still renders, shrunk to TITLE_MAX_WIDTH; the page warns (api checks)

SCENE_SIZES = (88, 60)  # main, sub
SCENE_MAX_CHARS, SCENE_MAX_SUB_WORDS = 16, 4
SCENE_CENTRE = (
    FRAME_WIDTH // 2,
    1300,
)  # the block spans 62–78% of the frame and stays above the platforms' caption bars
SCENE_MAX_WIDTH = round(FRAME_WIDTH * 0.92)
SCENE_CENTRE_TOP = (FRAME_WIDTH // 2, round(FRAME_HEIGHT * 0.22))  # "Trên": the 14–30% zone
NUMBER_DIAMETER, NUMBER_SIZE, NUMBER_GAP = 76, 52, 16

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


def parse_title(lines: list[list[Run]]) -> TitleTiers:
    """The title's lines as tiers: one line is the main one; two, main and sub; three or more, small, main and sub (the
    rest joins the sub). A line written `[[-50%]]` is the orange label."""
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
        small, main, sub = "", rest[0] if rest else "", ""
    return TitleTiers(small, main, sub, label)


def parse_scene(lines: list[list[Run]]) -> SceneTiers:
    """A scene's text as the main line (the `*marked*` words; else the first line) and the sub line (the rest), with the
    number the first line may start with ("3.")."""
    number = ""
    marked: list[str] = []
    plain: list[str] = []
    for index, line in enumerate(lines):
        if index == 0 and line and (found := _NUMBER.match(line[0].text)):
            number = found.group(1)
            line = [Run(line[0].text[found.end() :], line[0].red), *line[1:]]
        for run in line:
            text = normalize_text(run.text.strip())
            if text:
                (marked if run.red else plain).append(text)
    if not marked and plain:
        marked, plain = [plain[0]], plain[1:]
    return SceneTiers(number, " ".join(marked), " ".join(plain))


def _label(text: str) -> Image.Image:
    """The orange label: a rounded box, white text, tilted a little."""
    font = ImageFont.truetype(str(FONT_PATH), LABEL_SIZE)
    width, height = round(font.getlength(text)) + 48, LABEL_SIZE + 32
    box = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(box)
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=LABEL_RADIUS, fill=ORANGE)
    draw.text((width / 2, height / 2), text, font=font, fill=(255, 255, 255), anchor="mm")
    return box.rotate(LABEL_TILT, expand=True, resample=Image.Resampling.BICUBIC)


def render_title(tiers: TitleTiers, style: str = "brand_navy") -> Image.Image:
    """The three tiers stacked and centred, the label at the block's top right. Each line shrinks to fit 88% of the width."""
    sizes = [size for size, text in zip(TITLE_SIZES, (tiers.small, tiers.main, tiers.sub)) if text]
    texts = [text for text in (tiers.small, tiers.main, tiers.sub) if text]
    pictures = [
        render_line(text, size, line_style(style, key=text == tiers.main, index=index), TITLE_MAX_WIDTH)
        for index, (text, size) in enumerate(zip(texts, sizes))
    ]
    block = stack(pictures, [round(TITLE_GAP * size) for size in sizes[:-1]])
    if tiers.label:
        label = _label(tiers.label)
        canvas = Image.new("RGBA", (max(block.width, label.width + 40), block.height + label.height // 2), (0, 0, 0, 0))
        canvas.alpha_composite(block, ((canvas.width - block.width) // 2, label.height // 2))
        canvas.alpha_composite(label, (canvas.width - label.width - 20, 0))
        return canvas
    return block


def _circle(number: str) -> Image.Image:
    circle = Image.new("RGBA", (NUMBER_DIAMETER, NUMBER_DIAMETER), (0, 0, 0, 0))
    draw = ImageDraw.Draw(circle)
    draw.ellipse((0, 0, NUMBER_DIAMETER - 1, NUMBER_DIAMETER - 1), fill=ORANGE)
    font = ImageFont.truetype(str(FONT_PATH), NUMBER_SIZE)
    draw.text((NUMBER_DIAMETER / 2, NUMBER_DIAMETER / 2), number, font=font, fill=(255, 255, 255), anchor="mm")
    return circle


def render_scene(tiers: SceneTiers, style: str = "neon_game") -> Image.Image:
    """The main line with the numbered circle at its left, and the sub line under, the whole block centred."""
    rows: list[Image.Image] = []
    if tiers.main:
        main = render_line(tiers.main, SCENE_SIZES[0], line_style(style, True, 0), SCENE_MAX_WIDTH - NUMBER_DIAMETER)
        if tiers.number:
            circle = _circle(tiers.number)
            left = circle.width + NUMBER_GAP - PAD  # the line's own padding overlaps the circle's side
            row = Image.new("RGBA", (left + main.width, max(main.height, circle.height)), (0, 0, 0, 0))
            row.alpha_composite(main, (left, (row.height - main.height) // 2))
            row.alpha_composite(circle, (0, (row.height - circle.height) // 2))  # on top of the line's glow
            main = row
        rows.append(main)
    if tiers.sub:
        rows.append(render_line(tiers.sub, SCENE_SIZES[1], line_style(style, False, 1), SCENE_MAX_WIDTH))
    if not rows:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    return stack(rows, [round(0.1 * SCENE_SIZES[0])] * (len(rows) - 1))


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
