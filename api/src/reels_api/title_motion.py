"""The "Tiêu đề động" of a title scene (the owner's spec, phase 1, the "Sức khỏe" groups): a 3-second
"Cảnh động" (motion.py) that shows the listed dishes' photos popping in one by one over the blurred first photo, the
last one hidden behind a "?".

The members write nothing: the layout comes from the number of listed scenes and the video's "Loại nội dung"
(`choose_layout`), each slot shows the photo (or the clip's frame) of its own scene, and the markup is built here
(`build_html`). The slot photos are packed into one JPEG atlas that the markup shows as assets/photo.jpg, so the
render core, the HyperFrames job and the render machines need nothing new. The hook text stays the title scene's own
text box (drawn from second 0, at `HOOK_CENTRE`), and the title scene's sounds are replaced by `sounds()`.

The photo or clip the title scene showed is kept (`motion["classic"]`), so `set_mode` switches Cổ điển / Động without
a new render.
"""

import html as H
import io
import math
import re

from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import brands, clips, motion, outro
from .errors import ApiError
from .models import Scene, SceneSound, TopicPlanItem, Video
from .storage import DirectoryStorage
from .videos import ensure_unlocked, lock_scene, new_key, refresh_thumbnail, split_scenes

LAYOUTS = ("grid", "ring", "strip", "warn")
TITLE_SECONDS = 3.0
HOOK_CENTRE = (540, 400)
SAFE_BOTTOM = 1680  # the lowest pixel the slots may reach (the Reels caption zone starts below it)
SIDE_MARGIN = 60
GAP = 30  # between two slots, across and down
TITLE_GAP = 40  # between the hook box and the first row
SPRITE_SCALE = 2  # the atlas is cut at twice the slots' size so the photos stay sharp
AREA = (SIDE_MARGIN, 640, 1080 - SIDE_MARGIN, SAFE_BOTTOM)  # x0, y0, x1, y1: under the hook box, above the caption zone
MAX_LABEL = 22
COMBINED = re.compile(r"\+\s*\d+|kết hợp với\s*\d+", re.IGNORECASE)
# Words a health hook must not use (spec section 3): found ones are reported, never silently removed.
BANNED_HOOK = re.compile(
    r"chữa|khỏi bệnh|hơn (cả )?thuốc|thần dược|giải độc cực mạnh|kéo dài tuổi thọ|100\s*%", re.IGNORECASE
)
NOT_TITLE = "Chỉ cảnh tiêu đề mới có tiêu đề động"


def invalid(message: str) -> ApiError:
    return ApiError(422, "invalid_title_motion", message)


# --- Which layout ---


def choose_layout(content_type: str, title: str, n: int, requested: str = "auto") -> str:
    """The layout for `n` listed scenes (spec section 2); 422 when no layout holds that many."""
    if requested != "auto":
        layout = requested
    elif "tránh" in content_type.lower() and 2 <= n <= 6:
        layout = "warn"
    elif COMBINED.search(title) and 5 <= n <= 9:
        layout = "ring"
    elif 2 <= n <= 6:
        layout = "grid"
    elif 7 <= n <= 10:
        layout = "strip"
    else:
        raise invalid(f"Tiêu đề động làm được 2–10 món, video có {n} cảnh liệt kê")
    limits = {"grid": (2, 6), "warn": (2, 6), "ring": (5, 9), "strip": (7, 10)}
    if layout not in limits:
        raise invalid("Kiểu bố cục không có")
    low, high = limits[layout]
    if not low <= n <= high:
        raise invalid(f"Bố cục này dành cho {low}–{high} món, video có {n} cảnh liệt kê")
    return layout


# --- Geometry ---


def hook_bottom(video: Video, scene: Scene) -> int:
    """Where the title's text box ends in the render: a hook of four lines reaches well below two lines'."""
    from .frames import text_box
    from .videos import render_options

    try:
        image, (_, y) = text_box(scene.text or "", True, render_options(video), HOOK_CENTRE)
    except Exception:  # noqa: BLE001  (a text the box cannot lay out: the build goes on with the usual place)
        return AREA[1] - TITLE_GAP
    return y + image.height


def top_for(bottom: int) -> int:
    """The first row of the slots: the usual 640, or lower when the hook is taller (never below 1000, so they stay
    big enough to read)."""
    return max(AREA[1], min(1000, bottom + TITLE_GAP))


def grid_boxes(n: int, top: int = AREA[1]) -> list[tuple[int, int, int, int]]:
    """The slots fill the height from `top` to SAFE_BOTTOM and the width between the side margins: 2 dishes one over
    the other, 3 a wide one over two, 4–6 two columns (a last odd one in the middle), none taller than wide."""
    if not 2 <= n <= 6:
        raise invalid("Lưới dành cho 2–6 món")
    x0, _, x1, y1 = AREA
    width, avail = x1 - x0, y1 - top
    cols = 1 if n == 2 else 2
    rows = math.ceil(n / cols) if n != 3 else 2
    tile_w = (width - (cols - 1) * GAP) // cols
    tile_h = min((avail - (rows - 1) * GAP) // rows, tile_w)
    y0 = top
    if tile_h == tile_w:  # the tile hit its width, not the room: the grid sits in the middle of what is left
        y0 += (avail - (rows * tile_h + (rows - 1) * GAP)) // 2
    step = tile_h + GAP
    if n == 3:
        return [(x0, y0, width, tile_h)] + [(x0 + c * (tile_w + GAP), y0 + step, tile_w, tile_h) for c in range(2)]
    boxes = [(x0 + (i % cols) * (tile_w + GAP), y0 + (i // cols) * step, tile_w, tile_h) for i in range(n)]
    if n == 5:
        boxes[4] = ((1080 - tile_w) // 2, boxes[4][1], tile_w, tile_h)
    return boxes


def strip_height(n: int, top: int = AREA[1]) -> int:
    return (AREA[3] - top - 14 * (n - 1)) // n


def ring_boxes(n: int, top: int = AREA[1]) -> list[tuple[int, int, int, int]]:
    """The main dish in the middle and the others round it, as big as the room allows: the ring reaches the side
    margins (or the room's half height), the main dish is 70 % of that reach, and a bubble is the biggest that
    neither touches the main dish nor its neighbours."""
    height = AREA[3] - top
    cx, cy = 540, top + height // 2
    reach = min((AREA[2] - AREA[0]) / 2, height / 2) - 4
    leaves = n - 1
    hero = round(0.7 * reach)
    near = math.sin(math.pi / leaves)
    bubble = round(min(reach - hero / 2 - 14, (2 * near * reach - 12) / (1 + near), 300))
    radius = reach - bubble / 2
    boxes = [(cx - hero // 2, cy - hero // 2, hero, hero)]
    for k in range(leaves):
        angle = -math.pi / 2 + 2 * math.pi * k / leaves
        boxes.append(
            (
                round(cx + radius * math.cos(angle) - bubble / 2),
                round(cy + radius * math.sin(angle) - bubble / 2),
                bubble,
                bubble,
            )
        )
    return boxes


def slot_sizes(layout: str, n: int, top: int = AREA[1]) -> list[tuple[int, int]]:
    """The size of each slot's photo, as the markup shows it."""
    if layout in ("grid", "warn"):
        return [(w, h) for _, _, w, h in grid_boxes(n, top)]
    if layout == "ring":
        return [(w, h) for _, _, w, h in ring_boxes(n, top)]
    h = strip_height(n, top)
    return [(round(h * 1.6), h)] * n


def atlas_layout(sizes: list[tuple[int, int]]) -> tuple[int, int, list[tuple[int, int]]]:
    """Slots stacked one under another: the atlas's width and height, and where each slot starts."""
    offsets, top = [], 0
    for _, h in sizes:
        offsets.append((0, top))
        top += h
    return max(w for w, _ in sizes), top, offsets


# --- Timing and sounds ---


def timing(n: int) -> tuple[list[float], float]:
    step = min(0.35, 1.2 / max(n - 1, 1))
    starts = [round(0.1 + i * step, 2) for i in range(n)]
    return starts, round(starts[-1] + 0.55, 2)


def sounds(layout: str, n: int) -> list[tuple[str, float, str]]:
    """The title scene's sounds (spec section 6): (sound, second, volume)."""
    starts, _ = timing(n)
    out = [("whoosh", 0.0, "soft")]
    hide = layout != "warn"
    for i, t in enumerate(starts):
        if hide and i == n - 1:
            out.append(("rise", max(0.0, round(t - 0.25, 2)), "normal"))
        elif n >= 6 and i % 2 == 1:
            continue  # many dishes: a ding on every other one keeps the sound thin
        else:
            out.append(("wrong" if layout == "warn" else "ding", t, "soft"))
    return out


# --- Markup ---

CSS = """
#root{font-family:"Be Vietnam Pro",sans-serif;overflow:hidden;background:#1b120e}
.bg{position:absolute;left:-80px;top:-80px;width:1240px;height:2080px;background-color:#3a2a20;background-repeat:no-repeat;filter:blur(24px) saturate(1.2)}
.shade{position:absolute;left:0;top:0;width:1080px;height:1920px;background:linear-gradient(180deg,rgba(0,0,0,.55) 0%,rgba(0,0,0,.25) 45%,rgba(0,0,0,.6) 100%)}
.it{position:absolute;overflow:hidden;box-shadow:0 14px 0 rgba(0,0,0,.3)}
.it:after{content:"";position:absolute;left:0;top:0;right:0;bottom:0;border:6px solid #fff;border-radius:inherit}
.ph{position:absolute;left:0;top:0;right:0;bottom:0;background-color:#3f4a37;background-repeat:no-repeat}
.badge{position:absolute;left:18px;top:16px;width:72px;height:72px;border-radius:50%;background:#FF3B30;color:#fff;font-weight:900;font-size:44px;line-height:70px;text-align:center;box-shadow:0 4px 0 rgba(0,0,0,.3);z-index:2}
.name{position:absolute;left:0;bottom:0;width:100%;padding:40px 8px 20px;box-sizing:border-box;text-align:center;font-weight:900;font-size:46px;line-height:1.05;color:#fff;background:linear-gradient(180deg,rgba(0,0,0,0),rgba(0,0,0,.78));text-shadow:0 3px 0 rgba(0,0,0,.5)}
.hid .ph{filter:blur(8px) brightness(.5);transform:scale(1.12)}
.hid .badge{background:#FFD60A;color:#111}
.qm{position:absolute;left:0;width:100%;text-align:center;font-weight:900;line-height:1;color:#FFD60A;text-shadow:0 8px 0 rgba(0,0,0,.45);z-index:2}
.sub{position:absolute;left:0;bottom:18px;width:100%;text-align:center;font-weight:800;font-size:36px;color:#fff;text-shadow:0 3px 0 rgba(0,0,0,.5);z-index:2}
.x{position:absolute;left:0;top:0;right:0;bottom:0;z-index:2}
.x:before,.x:after{content:"";position:absolute;left:50%;top:44%;width:78%;height:26px;margin-left:-39%;background:#FF3B30;border-radius:13px;box-shadow:0 4px 0 rgba(0,0,0,.35)}
.x:before{transform:rotate(35deg)}.x:after{transform:rotate(-35deg)}
"""


def _photo(atlas: dict, i: int) -> str:
    """CSS showing slot i of the atlas, 1:1 inside a box of the slot's size."""
    ox, oy = atlas["offsets"][i]
    return (
        f"background-image:url(assets/{atlas['name']});background-size:{atlas['width']}px {atlas['height']}px;"
        f"background-position:-{ox}px -{oy}px"
    )


def _background(atlas: dict) -> str:
    """Slot 1 of the atlas, scaled to cover the blurred 1240×2080 background."""
    (w, h), (ox, oy) = atlas["sizes"][0], atlas["offsets"][0]
    scale = max(1240 / w, 2080 / h)
    left, top = ox * scale + (w * scale - 1240) / 2, oy * scale + (h * scale - 2080) / 2
    return (
        f"background-image:url(assets/{atlas['name']});background-size:{atlas['width'] * scale:.1f}px "
        f"{atlas['height'] * scale:.1f}px;background-position:-{left:.1f}px -{top:.1f}px"
    )


def scale_of(height: int) -> float:
    """How much a slot taller than the 189 px the details were drawn for scales them (1 to 1.3)."""
    return max(1.0, min(1.3, height / 189))


def fit_name(label: str, width: int, size: int) -> int:
    """The font size that keeps `label` on one line in a slot `width` wide (about 0.7 em a bold capital)."""
    return max(20, min(size, int((width - 28) / (0.7 * max(len(label), 1)))))


def fit_round_name(label: str, width: int, size: int) -> int:
    """The font size for a name of up to two lines inside a round slot (its bottom is narrow, so only 80 % of the
    width is used): the longest line is the longest word or half the name."""
    longest = max([len(word) for word in label.split()] + [math.ceil(len(label) / 2) if " " in label else len(label)])
    return max(18, min(size, int((width * 0.7 - 8) / (0.75 * max(longest, 1)))))


def _card(
    i, label, box, radius, hidden, atlas, hidden_label, *, name_size=46, badge=True, qsize=200, warn=False, fit=False,
    ring=False,
):  # fmt: skip
    x, y, w, h = box
    k = scale_of(h) if fit else 1.0
    inner = f'<div class="ph" style="{_photo(atlas, i)}"></div>'
    if badge:
        kb = min(k, 7 / 6)  # the approved sample's 84 px badge
        d = round(72 * kb)
        inner += (
            f'<div class="badge" style="width:{d}px;height:{d}px;font-size:{math.ceil(44 * kb)}px;line-height:{d - 2}px">'
            f"{i + 1}</div>"
        )
    if hidden:
        top = 18 if fit else max(10, (h - qsize) // 2 - 20)
        inner += f'<div class="qm" style="top:{top}px;font-size:{qsize}px">?</div>'
        if hidden_label and h >= (360 if fit else 260) and (fit or w != h):
            inner += f'<div class="sub">{H.escape(hidden_label)}</div>'
    else:
        if warn:
            inner += '<div class="x"></div>'
        if ring:
            size = fit_round_name(label, w, round(w * 0.15))
            style = f"font-size:{size}px;padding:{size}px {round(w * 0.15)}px {round(w * 0.17)}px"
        elif fit:
            style = f"font-size:{fit_name(label, w, min(48, round(40 * k)))}px;white-space:nowrap"
        else:
            style = f"font-size:{name_size}px"
        inner += f'<div class="name" style="{style}">{H.escape(label)}</div>'
    return (
        f'<div class="it s{i}{" hid" if hidden else ""}" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px;'
        f'border-radius:{radius}px">{inner}</div>'
    )


def build_html(layout: str, labels: list[str], atlas: dict, hidden_label: str, top: int = AREA[1]) -> str:
    """The motion scene's markup. `atlas`: {"name", "width", "height", "sizes", "offsets"} of the packed photos."""
    n = len(labels)
    parts = [f"<style>{CSS}</style>", f'<div class="bg" style="{_background(atlas)}"></div><div class="shade"></div>']
    starts, shake = timing(n)
    anim = ['tl.fromTo(".bg",{scale:1.15},{scale:1,duration:3,ease:"none"},0);']
    if layout in ("grid", "warn"):
        for i, box in enumerate(grid_boxes(n, top)):
            hidden = layout == "grid" and i == n - 1
            parts.append(
                _card(
                    i, labels[i], box, round(36 * min(scale_of(box[3]), 1.05)), hidden, atlas, hidden_label,
                    qsize=round(box[3] * 0.87), warn=layout == "warn", fit=True,
                )
            )  # fmt: skip
    elif layout == "ring":
        for i, box in enumerate(ring_boxes(n, top)):
            parts.append(
                _card(
                    i, labels[i], box, box[2] // 2, i == n - 1, atlas, hidden_label,
                    badge=False, qsize=round(box[2] * 0.6), ring=True,
                )
            )  # fmt: skip
    else:
        x0, _, x1, _ = AREA
        y0 = top
        h = strip_height(n, top)
        for i, label in enumerate(labels):
            hidden = i >= n - 2
            y = y0 + i * (h + 14)
            photo_w = atlas["sizes"][i][0]
            parts.append(
                f'<div class="it s{i}{" hid" if hidden else ""}" style="left:{x0}px;top:{y}px;width:{x1 - x0}px;'
                f'height:{h}px;border-radius:{h // 2}px;background:rgba(255,248,236,.95)">'
                f'<div class="ph" style="right:auto;width:{photo_w}px;border-radius:{h // 2}px 0 0 {h // 2}px;'
                f'{_photo(atlas, i)}"></div>'
                f'<div style="position:absolute;left:{photo_w + 24}px;top:0;height:{h}px;line-height:{h}px;'
                f'font-weight:900;font-size:{min(56, int(h * 0.55))}px;color:#1F2937">'
                f'<span style="color:#FF3B30">{i + 1}.</span> {"?" if hidden else H.escape(label)}</div></div>'
            )
    for i, t in enumerate(starts):
        scale = "0.6" if i == 0 else "0"
        anim.append(
            f'tl.from(".s{i}",{{scale:{scale},opacity:0,duration:.33,ease:"back.out(1.8)",transformOrigin:"50% 50%"}},{t});'
        )
    if layout != "warn":
        anim.append(
            f'tl.to(".s{n - 1}",{{rotation:4,duration:.08,yoyo:true,repeat:7,ease:"sine.inOut",transformOrigin:"50% 50%"}},{shake});'
        )
    parts.append("<script>\n" + "\n".join(anim) + "\n</script>")
    return "\n".join(parts)


# --- The slots' photos ---


def label_of(scene: Scene, after_plus: bool = False) -> str:
    """A dish's name for its slot: the scene's first line without markup, cut at the first dash or colon. With
    `after_plus` ("TRỨNG + LÁ LỐT" round the main dish), only what follows the last "+"."""
    line = (scene.text or "").replace("*", "").strip().split("\n")[0]
    line = re.sub(r"^\s*(\d+\s*[.):\-–]\s*|[-–•]\s*)", "", line)
    line = re.split(r"\s[-–—]\s|\s*[:,;]\s", line)[0].strip().upper()
    if after_plus and line.rsplit("+", 1)[-1].strip():
        line = line.rsplit("+", 1)[-1].strip()
    return line if len(line) <= MAX_LABEL else line[: MAX_LABEL - 1].rstrip() + "…"


# What the dishes are, found in the video's topic, for "ĂN 4 TRÁI NÀY"; the first one found wins.
NOUNS = (
    ("trái cây", "TRÁI"),
    ("hoa quả", "TRÁI"),
    ("rau", "RAU"),
    ("canh", "CANH"),
    ("cháo", "CHÁO"),
    ("món sáng", "MÓN SÁNG"),
    ("loại hạt", "LOẠI HẠT"),
    ("hạt", "LOẠI HẠT"),
    ("củ", "CỦ"),
    ("cá", "CÁ"),
    ("trà", "LOẠI TRÀ"),
)


def noun_of(topic: str) -> str:
    """The word for the dishes in a hook ("" when the topic names none)."""
    words = f" {(topic or '').lower()} "
    return next((noun for key, noun in NOUNS if f" {key} " in words or f" {key}," in words), "")


def hook_lines(layout: str, n: int, pain: str, noun: str, main: str = "") -> str:
    """The hook of the spec's section 3, two lines: a worry and the number, or the main dish and the number."""
    pain = pain.strip().upper()
    dishes = noun or "MÓN"
    if layout == "ring":
        kind = f" {noun}" if noun else ""
        return f"{main} + {n - 1} LOẠI{kind}\nSỐ {n - 1} ÍT AI BIẾT"
    if layout == "warn":
        return f"{pain}\nTRÁNH {n} {dishes} NÀY" if pain else f"TRÁNH {n} {dishes} NÀY"
    return f"LO {pain}?\nĂN {n} {dishes} NÀY" if pain else f"ĂN {n} {dishes} NÀY"


NUMBER_WORDS = {1: "một", 2: "hai", 3: "ba", 4: "bốn", 5: "năm", 6: "sáu", 7: "bảy", 8: "tám", 9: "chín", 10: "mười"}
# The dishes' word on screen -> what is said ("ĂN 4 TRÁI NÀY" is read "Ăn bốn loại trái cây này").
SPOKEN_NOUNS = {
    "TRÁI": "loại trái cây",
    "RAU": "loại rau",
    "CANH": "món canh",
    "CHÁO": "món cháo",
    "MÓN SÁNG": "món sáng",
    "LOẠI HẠT": "loại hạt",
    "CỦ": "loại củ",
    "CÁ": "loại cá",
    "LOẠI TRÀ": "loại trà",
}


def hook_voice(layout: str, n: int, pain: str, noun: str, main: str = "") -> str:
    """The title's narration for the same hook, as it is said (numbers in words), short enough for about 2 seconds."""
    pain = pain.strip().lower()
    dishes = SPOKEN_NOUNS.get(noun, "món")
    if layout == "ring":
        count = NUMBER_WORDS[n - 1]
        kind = f" {SPOKEN_NOUNS[noun].split(' ', 1)[1]}" if noun in SPOKEN_NOUNS and " " in SPOKEN_NOUNS[noun] else ""
        return f"{main.capitalize()} kết hợp {count} loại{kind}, loại thứ {count} ít ai biết."
    count = NUMBER_WORDS[n]
    if layout == "warn":
        return f"{pain.capitalize()}? Tránh {count} {dishes} này." if pain else f"Tránh {count} {dishes} này."
    return f"Lo {pain}? Ăn {count} {dishes} này." if pain else f"Ăn {count} {dishes} này."


def listed_scenes(db: DbSession, video: Video) -> list[Scene]:
    """The scenes the title lists: the content scenes without the outro and a closing call to action."""
    _, scenes = split_scenes(db, video)
    scenes = [scene for scene in scenes if not outro.is_outro(scene)]
    if len(scenes) > 1 and outro.is_call_to_action(scenes[-1]):
        scenes = scenes[:-1]
    return scenes


def subject_centre(image: Image.Image) -> tuple[float, float]:
    """Where the dish most likely is, as fractions of the photo: the middle of what is sharp and colourful on a small
    copy (a plate on a plain table, a fruit among leaves), pulled halfway back to the middle so a wrong guess still
    crops sensibly. There is no object detector here, so this is a heuristic, not a recognition."""
    small = ImageOps.exif_transpose(image).convert("RGB").resize((48, 48), Image.Resampling.BILINEAR)
    edges = small.convert("L").filter(ImageFilter.FIND_EDGES).tobytes()
    colour = small.convert("HSV").getchannel("S").tobytes()
    total = sx = sy = 0.0
    for index in range(48 * 48):
        weight = edges[index] + colour[index] * 0.5
        total += weight
        sx += weight * (index % 48)
        sy += weight * (index // 48)
    if total <= 0:
        return 0.5, 0.5
    cx, cy = (sx / total + 0.5) / 48, (sy / total + 0.5) / 48
    return (cx + 0.5) / 2, (cy + 0.5) / 2


def slot_photo(
    storage: DirectoryStorage,
    scene: Scene,
    number: int,
    size: tuple[int, int],
    focus: tuple[float, float] | None = None,
    own: str | None = None,
) -> Image.Image:
    """The scene's photo, or its clip's frame at the start time, cut to `size` around the dish (`focus`, a
    member's pick, else `subject_centre`)."""
    try:
        if own and storage.exists(own):
            frame = Image.open(storage.path(own))
            frame.load()
        elif scene.video_key and storage.exists(scene.video_key):
            frame = clips.frame_at(storage.path(scene.video_key), scene.video_start or 0)
        elif scene.image_key and storage.exists(scene.image_key):
            frame = Image.open(storage.path(scene.image_key))
            frame.load()
        else:
            raise invalid(f"Cảnh liệt kê số {number} chưa có ảnh hoặc clip: hãy chọn ảnh cho cảnh rồi tạo lại tiêu đề")
    except (clips.ClipError, UnidentifiedImageError, OSError):
        raise invalid(f"Không đọc được ảnh hoặc clip của cảnh liệt kê số {number}") from None
    frame = ImageOps.exif_transpose(frame).convert("RGB")
    centre = focus or subject_centre(frame)
    return ImageOps.fit(frame, size, Image.Resampling.LANCZOS, centering=centre)


def pack(images: list[Image.Image], atlas: dict) -> bytes:
    sheet = Image.new("RGB", (atlas["width"] * SPRITE_SCALE, atlas["height"] * SPRITE_SCALE), (63, 74, 55))
    for image, (ox, oy) in zip(images, atlas["offsets"], strict=True):
        sheet.paste(image, (ox * SPRITE_SCALE, oy * SPRITE_SCALE))
    out = io.BytesIO()
    sheet.save(out, "JPEG", quality=90)
    return out.getvalue()


# --- Building and switching ---


def hook_warnings(scene: Scene) -> list[str]:
    found = BANNED_HOOK.findall(f"{scene.text or ''}\n{scene.voice_text or ''}")
    words = sorted({m.group(0).lower() for m in BANNED_HOOK.finditer(f"{scene.text or ''}\n{scene.voice_text or ''}")})
    del found
    return [f"Tiêu đề có từ nên tránh: “{word}”" for word in words]


def other_scene(db: DbSession, video: Video, scene_id: int) -> Scene:
    found = db.get(Scene, scene_id)
    if found is None or found.video_id != video.id or found.is_title:
        raise invalid("Ô này lấy ảnh từ một cảnh không còn trong video")
    return found


def clean_slots(
    db: DbSession, video: Video, slots: list[dict], n: int, previous: list[dict] | None = None
) -> list[dict]:
    """One entry per slot with only the keys a member set; entries past the dishes are dropped, missing ones empty.
    A slot's own photo (`image_key`) is never taken from the request: it stays as `previous` has it."""
    out = []
    for i in range(n):
        raw = slots[i] if i < len(slots) and isinstance(slots[i], dict) else {}
        slot = {}
        if i < len(previous or []) and (previous or [])[i].get("image_key"):
            slot["image_key"] = previous[i]["image_key"]
        if raw.get("from_scene"):
            slot["from_scene"] = other_scene(db, video, int(raw["from_scene"])).id
        if (raw.get("label") or "").strip():
            slot["label"] = raw["label"].strip().upper()[:MAX_LABEL]
        focus = raw.get("focus")
        if focus and len(focus) == 2 and all(isinstance(v, int | float) and 0 <= v <= 1 for v in focus):
            slot["focus"] = [float(focus[0]), float(focus[1])]
        out.append(slot)
    return out


def build(
    db: DbSession,
    storage: DirectoryStorage,
    scene_id: int,
    me,
    *,
    layout: str = "auto",
    labels: list[str] | None = None,
    hidden_label: str | None = None,
    count: int | None = None,
    write_hook: bool = False,
    slots: list[dict] | None = None,
) -> tuple[dict, list[str]]:
    """Makes the title scene's motion and queues its render; returns the video's payload and the hook's warnings.
    `labels` rename the slots (and set how many there are), `count` limits the listed scenes taken from the start,
    `slots` ("Ảnh các ô": [{"from_scene", "label", "focus": [x, y]}], each key optional, null for a slot as it is)
    replaces the earlier ones, which a rebuild keeps while none are given. `write_hook` writes the title's text from the layout and the plan idea's pain group (an empty title always gets it)."""
    video, scene = lock_scene(db, scene_id)
    ensure_unlocked(db, video)
    if not scene.is_title:
        raise invalid(NOT_TITLE)
    listed = listed_scenes(db, video)
    if labels:
        count = len(labels)
    if count is not None:
        listed = listed[:count]
    n = len(listed)
    earlier = ((scene.motion or {}).get("title") or {}).get("slots") or []
    slots = clean_slots(db, video, earlier if slots is None else slots, n, earlier)
    listed = [
        other_scene(db, video, slot["from_scene"]) if slot.get("from_scene") else s
        for s, slot in zip(listed, slots, strict=True)
    ]
    if labels and n != len(labels):
        raise invalid(f"Video chỉ có {n} cảnh liệt kê, không đủ cho {len(labels)} tên món")
    layout = choose_layout(video.content_type or "", scene.text or "", n, layout)
    given = [
        (slot.get("label") or (labels[i] if labels else "")).strip().upper()[:MAX_LABEL] for i, slot in enumerate(slots)
    ]
    names = [
        label or label_of(s, layout == "ring" and i > 0) for i, (label, s) in enumerate(zip(given, listed, strict=True))
    ]
    if not all(names):
        raise invalid("Có cảnh liệt kê chưa có chữ để làm tên món")
    scene.text_x, scene.text_y = HOOK_CENTRE
    if write_hook or not (scene.text or "").strip():
        pain = db.scalar(select(TopicPlanItem.pain_group).where(TopicPlanItem.video_id == video.id)) or ""
        noun = noun_of(video.topic)
        scene.text = hook_lines(layout, n, pain, noun, names[0])
        scene.voice_text = hook_voice(layout, n, pain, noun, names[0])
    top = top_for(hook_bottom(video, scene))  # a tall hook pushes the slots down
    sizes = slot_sizes(layout, n, top)
    width, height, offsets = atlas_layout(sizes)
    atlas = {"name": "photo.jpg", "width": width, "height": height, "sizes": sizes, "offsets": offsets}
    images = [
        slot_photo(
            storage,
            s,
            i + 1,
            (size[0] * SPRITE_SCALE, size[1] * SPRITE_SCALE),
            tuple(slots[i]["focus"]) if slots[i].get("focus") else None,
            slots[i].get("image_key"),
        )
        for i, (s, size) in enumerate(zip(listed, sizes, strict=True))
    ]
    number = n - 1 if layout == "ring" else n
    hidden = (hidden_label or f"SỐ {number} ÍT AI NGỜ").strip().upper()[:30]
    markup = build_html(layout, names, atlas, hidden, top)
    for old in list(scene.sounds):
        db.delete(old)
    db.flush()
    for sound, start, volume in sounds(layout, n):
        scene.sounds.append(SceneSound(sound=sound, start=start, volume=volume))
    info = {"layout": layout, "labels": names, "hidden_label": hidden, "count": n, "slots": slots, "top": top}
    # The Page's "Kiểu tiêu đề": a title built for the first time shows its classic photo or clip when the channel
    # says so (motion.attach); the member switches to "Động" on the video. A rebuild keeps what the member chose.
    brand = brands.brand_of(db, video)
    if brand is not None and brand.title_style == "classic" and not (scene.motion or {}).get("clip_key"):
        info["style"] = "classic"
    payload = motion.request(
        db, storage, scene_id, markup, TITLE_SECONDS, me, atlas=(pack(images, atlas), "jpg"), title=info
    )
    return payload, hook_warnings(scene)


def set_slot_photo(
    db: DbSession, storage: DirectoryStorage, scene_id: int, index: int, data: bytes, extension: str
) -> dict:
    """ "Ảnh các ô": a photo of the member's own for one slot (uploaded, from a link or from the library) takes the
    place of its scene's photo the next time the title is built. The caller checked `data` is an image."""
    from . import routes_videos

    video, scene = lock_scene(db, scene_id)
    ensure_unlocked(db, video)
    made = scene.motion or {}
    info = made.get("title")
    if not scene.is_title or not info:
        raise invalid("Cảnh tiêu đề chưa có tiêu đề động")
    if not 0 <= index < info["count"]:
        raise invalid("Tiêu đề không có ô này")
    slots = [dict(slot) for slot in info.get("slots") or []]
    slots += [{} for _ in range(info["count"] - len(slots))]
    old = slots[index].get("image_key")
    key = new_key(video.id, f"title-slot-{scene.id}-{index}", extension)
    storage.save_bytes(key, data)
    slots[index]["image_key"] = key
    scene.motion = {**made, "title": {**info, "slots": slots}}
    payload = routes_videos._saved(db, video)
    storage.delete(old)
    return payload


def remove_slot_photo(db: DbSession, storage: DirectoryStorage, scene_id: int, index: int) -> dict:
    """ "Xóa ảnh" of a slot: it follows its scene's photo again from the next build."""
    from . import routes_videos

    video, scene = lock_scene(db, scene_id)
    ensure_unlocked(db, video)
    made = scene.motion or {}
    info = made.get("title")
    if not scene.is_title or not info:
        raise invalid("Cảnh tiêu đề chưa có tiêu đề động")
    if not 0 <= index < info["count"]:
        raise invalid("Tiêu đề không có ô này")
    slots = [dict(slot) for slot in info.get("slots") or []]
    old = slots[index].pop("image_key", None) if index < len(slots) else None
    scene.motion = {**made, "title": {**info, "slots": slots}}
    payload = routes_videos._saved(db, video)
    storage.delete(old)
    return payload


def set_mode(db: DbSession, storage: DirectoryStorage, scene_id: int, mode: str) -> dict:
    """Cổ điển / Động: the title scene shows the photo or clip it had, or the motion clip already rendered. No job."""
    from . import routes_videos

    video, scene = lock_scene(db, scene_id)
    ensure_unlocked(db, video)
    made = scene.motion or {}
    if not scene.is_title or not made.get("title"):
        raise invalid("Cảnh tiêu đề chưa có tiêu đề động")
    if made.get("pending"):
        raise invalid("Tiêu đề động đang được dựng, chờ xong rồi đổi")
    if mode == "classic":
        classic = made.get("classic")
        if not motion.shows_motion(scene):
            return routes_videos._saved(db, video)
        if not classic:
            raise invalid("Cảnh này không có ảnh hoặc clip cũ để quay về")
        for name in motion.CLASSIC_FIELDS:
            setattr(scene, name, classic.get(name))
        scene.words = None
    else:
        key = made.get("clip_key")
        if not key or not storage.exists(key):
            raise invalid("Tiêu đề động chưa dựng xong, hãy bấm tạo tiêu đề động")
        if motion.shows_motion(scene):
            return routes_videos._saved(db, video)
        classic = motion.snapshot(scene)
        scene.motion = {**made, "classic": classic}
        scene.video_key, scene.video_seconds = key, made.get("clip_seconds")
        scene.video_start, scene.video_speed, scene.video_loop, scene.video_sound = 0, 1, False, False
        scene.words = None
        scene.image_key, scene.image_source, scene.image_auto = None, None, False
        scene.seconds, scene.seconds_auto = made["seconds"], False
    title, _ = split_scenes(db, video)
    refresh_thumbnail(db, storage, video, title)
    return routes_videos._saved(db, video)
