"""Pre-render checks: blocking errors and yellow warnings, the same for Claude's script and a member's edits.

Text markup and box fit use reels_render's own code, so "passes here" means "renders there".
"""

import re
import unicodedata
from dataclasses import dataclass, field

from reels_render.markup import MarkupError, parse_scene_text
from reels_render.textbox import TextFitError, layout_sized
from reels_render.timeline import FPS, HALF_XFADE, fit_seconds

MIN_SECONDS = 1
MAX_SECONDS = 10
MAX_TOTAL_SECONDS = 90
SCENE_COUNT_RANGE = (5, 7)
# A narrated script at its 150-word limit runs about 52 seconds; a longer one has outgrown the format.
TOTAL_SECONDS_RANGE = (20, 55)
MAX_SCENE_WORDS = 10
MAX_TITLE_WORDS = 12

# A crossfade straddles each scene boundary, so a clip plays this much longer on every side with a neighbour.
CROSSFADE_SIDE_SECONDS = HALF_XFADE / FPS

DEFAULT_BANNED_WORDS = ["chữa khỏi", "thay thuốc", "diệt tế bào ung thư", "đặc trị", "khắc tinh"]


@dataclass(frozen=True)
class SceneInput:
    id: int
    is_title: bool
    text: str
    seconds: float
    has_image: bool  # a photo or a clip
    voice_text: str = ""  # the member's own voice text; empty when the video's narration is off
    voice_seconds: float | None = None  # length of the narration already made for the current voice text
    clip_seconds: float | None = None  # what is left of the scene's clip after its start time
    has_keywords: bool = True  # Vietnamese or English photo keywords, for "Tìm ảnh" and the picker
    clip_speed: float = 1.0  # a scene takes this many seconds of clip for each second it lasts
    text_size: str = "large"  # the size its text box is drawn at (reels_render.textbox.TEXT_SIZES)
    text_case: str = "upper"  # the letter case its text is drawn in (reels_render.markup.TEXT_CASES)
    photo_credit: dict | None = None  # the shown photo's licence asks for credit (videos.photo_credit)


@dataclass(frozen=True)
class Issue:
    message: str
    scene_id: int | None = None  # None: the whole video, or a post field named by `field`
    field: str = "text"


@dataclass
class Checks:
    blocking: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)


def count_words(text: str) -> int:
    return len(text.replace("*", "").replace("\n", " ").split())


def text_problem(text: str, is_title: bool, size: str = "large", case: str = "upper") -> str | None:
    """Why reels_render would refuse this text, drawn at `size` in `case` ("Dạng chữ"), or None. Also the reason
    shown instead of a preview."""
    if not text.strip():
        return None  # a scene without text simply has no box
    try:
        lines = parse_scene_text(text, case)
    except MarkupError as err:
        return f"Chữ sai cách đánh dấu: {err}"
    try:
        layout_sized(lines, size, is_title)
    except TextFitError as err:
        return f"Chữ tràn hộp: {err}"
    return None


def _comparable(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("*", "").casefold()
    return " ".join(text.split())


def banned_hits(text: str, banned_words: list[str]) -> list[str]:
    """Banned words found in the text, ignoring case, Unicode form (NFC vs NFD) and `*` markup."""
    haystack = _comparable(text)
    return [word for word in banned_words if _comparable(word) and _comparable(word) in haystack]


def credit_warning(credit: dict) -> str:
    """The warning of a photo whose licence asks for credit: the line to put in the post, and share-alike's extra."""
    text = f"Ảnh cần ghi nguồn khi đăng: “{credit.get('line') or credit.get('license')}”"
    if "SA" in str(credit.get("license") or "").upper().replace("-", " ").split():
        text += "; giấy phép CC BY-SA còn yêu cầu chia sẻ lại video theo cùng giấy phép"
    return text


def check_script(
    title: SceneInput | None,
    scenes: list[SceneInput],
    post_fields: dict[str, str],
    banned_words: list[str],
) -> Checks:
    checks = Checks()
    block, warn = checks.blocking.append, checks.warnings.append
    if not scenes:
        block(Issue("Chưa có cảnh nội dung nào", field="scenes"))

    every = ([title] if title else []) + scenes
    for index, scene in enumerate(every):
        problem = text_problem(scene.text, scene.is_title, scene.text_size, scene.text_case)
        if problem:
            block(Issue(problem, scene.id))
        if not scene.has_image:
            block(Issue("Cảnh chưa có ảnh", scene.id, "image"))
            if not scene.has_keywords:
                # A script may leave the keywords out; without them "Tìm ảnh" has nothing to search.
                warn(Issue("Cảnh chưa có từ khóa tìm ảnh: nhập từ khóa hoặc tải ảnh lên", scene.id, "keywords"))
        if scene.photo_credit:
            warn(Issue(credit_warning(scene.photo_credit), scene.id, "image"))
        if not MIN_SECONDS <= scene.seconds <= MAX_SECONDS:
            block(Issue(f"Số giây phải từ {MIN_SECONDS} đến {MAX_SECONDS}", scene.id, "seconds"))
        neighbours = (index > 0) + (index < len(every) - 1)
        played = fit_seconds(scene.seconds, scene.voice_seconds) + neighbours * CROSSFADE_SIDE_SECONDS
        if scene.clip_seconds is not None and played * scene.clip_speed > scene.clip_seconds + 0.01:
            speed = f"{scene.clip_speed:g}".replace(".", ",")
            at_speed = "Video" if scene.clip_speed == 1 else f"Ở tốc độ {speed}× video"
            warn(Issue(f"{at_speed} ngắn hơn cảnh, khung cuối sẽ đứng yên", scene.id, "video"))
        words, limit = count_words(scene.text), MAX_TITLE_WORDS if scene.is_title else MAX_SCENE_WORDS
        if words > limit:
            warn(Issue(f"Chữ có {words} từ, nên tối đa {limit} từ", scene.id))
        for word in banned_hits(scene.text, banned_words):
            warn(Issue(f"Có từ cấm: “{word}”", scene.id))
        for word in banned_hits(scene.voice_text, banned_words):
            warn(Issue(f"Lời đọc có từ cấm: “{word}”", scene.id, "voice"))

    # Scenes count as lengthened to fit narration made earlier; narration not made yet is measured by the render job.
    # Rounded so float sums such as 0.1 + 0.2 never push an exact 90 over the limit.
    total = round(
        sum(fit_seconds(scene.seconds, scene.voice_seconds) for scene in ([title] if title else []) + scenes), 3
    )
    if total > MAX_TOTAL_SECONDS:
        block(Issue(f"Tổng độ dài {total:g} giây, tối đa {MAX_TOTAL_SECONDS} giây", field="total"))
    elif not TOTAL_SECONDS_RANGE[0] <= total <= TOTAL_SECONDS_RANGE[1]:
        low, high = TOTAL_SECONDS_RANGE
        warn(Issue(f"Tổng độ dài {total:g} giây, nên trong khoảng {low}–{high} giây", field="total"))
    low, high = SCENE_COUNT_RANGE
    if scenes and not low <= len(scenes) <= high:
        warn(Issue(f"Có {len(scenes)} cảnh nội dung, công thức kênh là {low}–{high} cảnh", field="scenes"))

    for name, text in post_fields.items():
        for word in banned_hits(text, banned_words):
            warn(Issue(f"Có từ cấm: “{word}”", field=name))
    return checks


_SPACES = re.compile(r"\s+")


def plain_title(text: str) -> str:
    """A scene's on-screen text as one plain line, for lists, file names and narration."""
    return _SPACES.sub(" ", text.replace("*", "")).strip()
