"""The article's "Ảnh ghép chữ + ảnh": one 4:5 photo with a band of text (the hook) over the dish photo, in place of
two photos that Facebook lays side by side (decisions 2026-11-25, "article composite").

Pillow port of the spec's canvas reference (`docs/decisions/2026-11-25-article-composite.md`): the same sizes, the same
auto-fit of the text, the same choice between `cover` and `blur`. The render is deterministic: the same source and
options give the same bytes. The Page's logo is not drawn here; it is laid on a copy when the article is posted
(photo_logo.py), over the photo area.
"""

import io
import itertools
import re
from dataclasses import dataclass, field
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from reels_render.textbox import FONT_PATH

WIDTH, HEIGHT = 1080, 1350
TOP = HEIGHT // 3  # 450: the band of text; the photo area is 1080 x 900 below it
JPEG_QUALITY = 90

PRESETS = {
    "cam": ("Cam", ("#FFC857", "#FF6B3D", "#E8432E")),
    "xanh_la": ("Xanh lá", ("#C8F169", "#4CB944", "#1F8A4C")),
}
DEFAULT_PRESET = "cam"
MODES = ("auto", "cover", "blur")

FILL, MAX_W, LH, TAGR, PILL_H, GAP = 0.74, 0.86, 1.2, 0.5, 1.9, 0.5
MAX_LINES = 3
MAX_LINE_CHARS = 60  # a line longer than this cannot fit the width at a readable size
MAX_TAG_CHARS = 60
SPLIT_SHORT, SPLIT_LONG = 22, 24
MIN_FONT_WARNING = 48
LOW_RES_WIDTH = 800
UPSCALE_WARNING = 1.5
MAX_MAIN_SCALE = 2.0
BLUR_RADIUS, BLUR_DIM, BLUR_BLEED = 28, 0.75, 40
SHADOW_ALPHA, SHADOW_BLUR = 0.4, 24

# The photo's own size is a limit of the render, like the rest of the app's photo tools.
MAX_SOURCE_PIXELS = 60_000_000

_EMOJI = re.compile("[\U0001f000-\U0001faff☀-➿⌀-⏿⬀-⯿️‍⃣\U000e0020-\U000e007f]+")
_DAY_PREFIX = re.compile(r"^\s*Ng[àa]y\s*\d+\s*[|:\-–—]\s*", re.IGNORECASE)
_PREFERRED_BREAK = "?!,–"


class CompositeError(ValueError):
    """`code` is one of the spec's error codes; the message is Vietnamese and shown to the member."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Options:
    lines: list[str]
    tag: str | None = None
    preset: str = DEFAULT_PRESET
    mode: str = "auto"
    focus_x: float = 0.5
    focus_y: float = 0.5

    def as_json(self) -> dict:
        return {
            "lines": self.lines,
            "tag": self.tag,
            "preset": self.preset,
            "mode": self.mode,
            "focus_x": self.focus_x,
            "focus_y": self.focus_y,
        }


@dataclass
class Result:
    data: bytes
    mode_used: str
    font_size: int
    warnings: list[dict] = field(default_factory=list)


def warning(code: str, message: str) -> dict:
    return {"code": code, "message": message}


def strip_emoji(text: str) -> str:
    """The font has no emoji (Be Vietnam Pro): they are dropped before measuring so the centring stays true."""
    return " ".join(_EMOJI.sub("", text).split())


# --- Splitting a title into lines (spec §7) ---


def split_title(caption_first_line: str, has_tag: bool) -> list[str]:
    text = " ".join(_DAY_PREFIX.sub("", caption_first_line, count=1).split()) if has_tag else caption_first_line
    text = " ".join(text.split())
    if not text:
        raise CompositeError("TITLE_EMPTY", "Chưa có tiêu đề: viết caption trước (dòng đầu là chữ trên ảnh ghép)")
    if len(text) <= SPLIT_SHORT:
        return [text]
    words = text.split(" ")
    for n in (2, 3):
        best: tuple[float, list[str]] | None = None
        for cuts in itertools.combinations(range(1, len(words)), n - 1):
            bounds = (0, *cuts, len(words))
            lines = [" ".join(words[a:b]) for a, b in itertools.pairwise(bounds)]
            lengths = [len(line) for line in lines]
            if max(lengths) > SPLIT_LONG:
                continue
            preferred = sum(1 for line in lines[:-1] if line[-1] in _PREFERRED_BREAK)
            score = (max(lengths) - min(lengths)) - 4 * preferred
            if best is None or score < best[0]:
                best = (score, lines)
        if best:
            return best[1]
    raise CompositeError(
        "TITLE_TOO_LONG", "Tiêu đề quá dài để xếp vừa 3 dòng: hãy rút gọn (mỗi dòng 15–22 ký tự), app không tự cắt chữ"
    )


# --- Drawing ---


@lru_cache(maxsize=64)
def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_PATH), size)


def choose_mode(width: int, height: int) -> str:
    """Spec §5.3: a tall photo, a small one (a cover would blow it up) and a very wide one (a cover cuts much of it)
    keep their whole picture on a blurred background."""
    box_w, box_h = WIDTH, HEIGHT - TOP
    ratio, box = width / height, box_w / box_h
    scale = max(box_w / width, box_h / height)
    lost = 1 - min(ratio / box, box / ratio)
    if ratio < 0.9 or scale > 1.6 or lost > 0.35:
        return "blur"
    return "cover"


def _open(data: bytes) -> Image.Image:
    try:
        with Image.open(io.BytesIO(data)) as raw:
            if raw.width * raw.height > MAX_SOURCE_PIXELS:
                raise CompositeError("SOURCE_TOO_BIG", "Ảnh gốc quá lớn, hãy chọn ảnh nhỏ hơn")
            picture = ImageOps.exif_transpose(raw)
            if picture.mode in ("RGBA", "LA", "P"):
                picture = picture.convert("RGBA")
                backdrop = Image.new("RGBA", picture.size, "white")
                picture = Image.alpha_composite(backdrop, picture)
            return picture.convert("RGB")
    except CompositeError:
        raise
    except Exception:
        raise CompositeError("SOURCE_UNREADABLE", "Không đọc được ảnh gốc") from None


def _cover(src: Image.Image, box_w: int, box_h: int, focus_x: float, focus_y: float) -> Image.Image:
    scale = max(box_w / src.width, box_h / src.height)
    crop_w, crop_h = box_w / scale, box_h / scale
    left, upper = (src.width - crop_w) * focus_x, (src.height - crop_h) * focus_y
    return src.resize((box_w, box_h), Image.Resampling.LANCZOS, box=(left, upper, left + crop_w, upper + crop_h))


def _photo_area(src: Image.Image, mode: str, opts: Options, warnings: list[dict]) -> Image.Image:
    box_w, box_h = WIDTH, HEIGHT - TOP
    if mode == "cover":
        scale = max(box_w / src.width, box_h / src.height)
        if scale > UPSCALE_WARNING:
            warnings.append(warning("UPSCALED", f"Ảnh bị phóng {scale:.1f} lần nên có thể mờ: chọn ảnh lớn hơn"))
        return _cover(src, box_w, box_h, opts.focus_x, opts.focus_y)
    # blur: the same picture, covered, enlarged by the bleed and blurred, then the whole picture over it
    bleed = BLUR_BLEED
    area = _cover(src, box_w + 2 * bleed, box_h + 2 * bleed, 0.5, 0.5)
    area = area.filter(ImageFilter.GaussianBlur(BLUR_RADIUS))
    area = Image.eval(area, lambda value: round(value * BLUR_DIM)).crop((bleed, bleed, bleed + box_w, bleed + box_h))
    scale = min(box_w / src.width, box_h / src.height, MAX_MAIN_SCALE)
    if scale > UPSCALE_WARNING:
        warnings.append(warning("UPSCALED", f"Ảnh bị phóng {scale:.1f} lần nên có thể mờ: chọn ảnh lớn hơn"))
    main = src.resize((round(src.width * scale), round(src.height * scale)), Image.Resampling.LANCZOS)
    x, y = (box_w - main.width) // 2, (box_h - main.height) // 2
    pad = SHADOW_BLUR * 3
    shadow = Image.new("L", (main.width + 2 * pad, main.height + 2 * pad), 0)
    shadow.paste(round(255 * SHADOW_ALPHA), (pad, pad, pad + main.width, pad + main.height))
    shadow = shadow.filter(ImageFilter.GaussianBlur(SHADOW_BLUR / 2))
    area.paste((0, 0, 0), (x - pad, y - pad), shadow)
    area.paste(main, (x, y))
    return area


def _gradient(colours: tuple[str, str, str]) -> Image.Image:
    stops = [tuple(int(colour[i : i + 2], 16) for i in (1, 3, 5)) for colour in colours]
    band = Image.new("RGB", (WIDTH, TOP))
    draw = ImageDraw.Draw(band)
    for y in range(TOP):
        t = y / (TOP - 1)
        low, high, local = (stops[0], stops[1], t * 2) if t <= 0.5 else (stops[1], stops[2], (t - 0.5) * 2)
        draw.line(((0, y), (WIDTH, y)), fill=tuple(round(a + (b - a) * local) for a, b in zip(low, high, strict=True)))
    return band


def fit_font(lines: list[str], has_tag: bool) -> int:
    """Spec §4.3: the text block fills 74% of the band, and the longest line stays within 86% of the width."""
    tag_k = TAGR * PILL_H + GAP if has_tag else 0
    size = int(TOP * FILL // (len(lines) * LH + tag_k))
    widest = max(_font(size).getlength(line) for line in lines)
    if widest > WIDTH * MAX_W:
        size = int(size * WIDTH * MAX_W // widest)
    return max(size, 8)


def block_layout(lines: list[str], tag: str | None, size: int) -> tuple[float, float, float]:
    """The text block's top, its height and the pill's height: the block is centred in the band."""
    pill_h = round(size * TAGR) * PILL_H if tag else 0
    block = pill_h + (size * GAP if tag else 0) + len(lines) * size * LH
    return (TOP - block) / 2, block, pill_h


def _draw_text(band: Image.Image, lines: list[str], tag: str | None, size: int) -> None:
    tag_size = round(size * TAGR)
    y, _, pill_h = block_layout(lines, tag, size)
    overlay = Image.new("RGBA", band.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    if tag:
        font = _font(tag_size)
        pill_w = font.getlength(tag) + tag_size * 1.6
        draw.rounded_rectangle(
            ((WIDTH - pill_w) / 2, y, (WIDTH + pill_w) / 2, y + pill_h), radius=pill_h / 2, fill=(255, 255, 255, 61)
        )
        draw.text((WIDTH / 2, y + pill_h / 2 + 1), tag, font=font, fill="white", anchor="mm")
        y += pill_h + size * GAP
    font = _font(size)
    shadow = Image.new("RGBA", band.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    for i, line in enumerate(lines):
        centre = y + size * LH * (i + 0.5)
        shadow_draw.text((WIDTH / 2, centre + 3), line, font=font, fill=(0, 0, 0, 56), anchor="mm")
        draw.text((WIDTH / 2, centre), line, font=font, fill="white", anchor="mm")
    shadow = shadow.filter(ImageFilter.GaussianBlur(4))
    band.paste(Image.alpha_composite(Image.alpha_composite(band.convert("RGBA"), shadow), overlay).convert("RGB"))


def clean(opts: Options) -> Options:
    """The options checked and tidied, or a CompositeError."""
    lines = [strip_emoji(line) for line in opts.lines]
    lines = [line for line in lines if line]
    if not lines:
        raise CompositeError("TITLE_EMPTY", "Chưa có tiêu đề cho ảnh ghép")
    if len(opts.lines) > MAX_LINES or len(lines) > MAX_LINES:
        raise CompositeError("TITLE_TOO_LONG", f"Tiêu đề tối đa {MAX_LINES} dòng: hãy rút gọn, app không tự cắt chữ")
    if any(len(line) > MAX_LINE_CHARS for line in lines):
        raise CompositeError("TITLE_TOO_LONG", f"Mỗi dòng tiêu đề tối đa {MAX_LINE_CHARS} ký tự: hãy rút gọn")
    tag = strip_emoji(opts.tag or "").upper() or None
    if tag and len(tag) > MAX_TAG_CHARS:
        raise CompositeError("TAG_TOO_LONG", f"Nhãn tối đa {MAX_TAG_CHARS} ký tự")
    if opts.preset not in PRESETS:
        raise CompositeError("INVALID_PRESET", "Màu dải chữ không hợp lệ")
    if opts.mode not in MODES:
        raise CompositeError("INVALID_MODE", "Kiểu ảnh không hợp lệ (Tự động, Cắt vừa hoặc Nền mờ)")
    if not (0 <= opts.focus_x <= 1 and 0 <= opts.focus_y <= 1):
        raise CompositeError("INVALID_FOCUS", "Điểm cắt phải nằm trong khoảng 0–1")
    return Options(lines, tag, opts.preset, opts.mode, opts.focus_x, opts.focus_y)


def render(source: bytes, opts: Options) -> Result:
    """The composite as a JPEG (1080 x 1350), the band of text 450 px high over the photo area."""
    opts = clean(opts)
    src = _open(source)
    warnings: list[dict] = []
    if src.width < LOW_RES_WIDTH:
        warnings.append(warning("LOW_RES_SOURCE", f"Ảnh gốc chỉ rộng {src.width} px nên có thể mờ: chọn ảnh lớn hơn"))
    mode = choose_mode(src.width, src.height) if opts.mode == "auto" else opts.mode
    canvas = Image.new("RGB", (WIDTH, HEIGHT))
    canvas.paste(_photo_area(src, mode, opts, warnings), (0, TOP))
    band = _gradient(PRESETS[opts.preset][1])
    size = fit_font(opts.lines, bool(opts.tag))
    if size < MIN_FONT_WARNING:
        warnings.append(warning("FONT_TOO_SMALL", f"Chữ chỉ cỡ {size} px nên khó đọc: hãy rút gọn tiêu đề"))
    _draw_text(band, opts.lines, opts.tag, size)
    canvas.paste(band, (0, 0))
    buffer = io.BytesIO()
    canvas.save(buffer, "JPEG", quality=JPEG_QUALITY, subsampling=0)  # 4:4:4, so the band keeps a sharp edge
    return Result(buffer.getvalue(), mode, size, warnings)
