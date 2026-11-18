"""'Clone' a competitor's video (docs/decisions/2026-11-18-competitor-clone-video.md): the "Tự viết" script of a new
video, built in code from the caption the scan read, never by an AI call. The title is the caption's first sentence,
the hook says it, each idea that follows is a scene, and a closing call to follow or save is a scene of its own.

Pure functions, no I/O: routes_competitors makes the video with them.
"""

import re
import unicodedata
from dataclasses import dataclass

from .errors import ApiError

MAX_TOPIC_LENGTH = 300  # routes_videos.MAX_TOPIC_LENGTH
MAX_SCRIPT_LENGTH = 5000  # routes_videos.MAX_SCRIPT_LENGTH
MAX_SCENES = 20  # routes_videos.MAX_HAND_SCENES, the title scene not counted
MAX_VOICE_LENGTH = 1000  # routes_videos.MAX_VOICE_LENGTH: what a scene's narration may hold
SCREEN_LENGTH = 60  # the on-screen text: the first words of what the scene says
SHORT_SENTENCE = 40  # a sentence shorter than this joins the scene before it
SCENE_WORDS = (15, 35)  # about 6 to 12 seconds of narration a scene
LONG_UNIT_WORDS = 60  # a run-on line longer than this is split into scenes of about SCENE_WORDS[1] words
THIN_CAPTION = 80  # a caption shorter than this, without its hashtags, is only a title
CALLS_TO_ACTION = ("theo dõi", "lưu lại", "chia sẻ", "nhớ", "follow", "share")
CLOSING = "Lưu lại và theo dõi để xem thêm nhé"

HASHTAG = re.compile(r"#\S+")
SEE_MORE = re.compile(r"(?:…|\.\.\.)?\s*\b(?:xem thêm|see more)\s*$", re.IGNORECASE)
NUMBERED = re.compile(r"^\d{1,2}\s*[.)/:]\s+")
# A full stop, or an emoji between words (BREAK, an invisible separator put in its place): captions often end a
# phrase with one instead of a stop.
BREAK = "\u2063"
SENTENCE_END = re.compile(r"(?<=[.!?…])\s+|\s*\u2063[\s\u2063]*")
CLAUSE_END = re.compile(r"[,;:–—](?:\s|$)|[.!?…](?:\s|$)")
# Emoji and other pictographs: the render's fonts have none, so they never reach the scenes.
INVISIBLE = {"\ufe0f", "\ufe0e", "\u200d", "\u20e3"}
NO_TEXT = "Caption không có chữ để clone (chỉ có hashtag hoặc biểu tượng)"


@dataclass
class ClonedScript:
    topic: str
    script: str  # the "Tự viết" format: a paragraph per scene, its "Đọc:" line the narration
    scenes: int
    thin: bool  # the caption was only a title: the script is a hook and a closing scene, to fill in by hand


@dataclass
class _Unit:
    text: str
    bullet: bool = False


def _is_picture(char: str) -> bool:
    return char in INVISIBLE or unicodedata.category(char) in ("So", "Sk", "Cs", "Co")


def _starts_with_marker(line: str) -> bool:
    """A list item: "1.", "2)", or a line opening with a dash, a bullet or an emoji such as 🔹 or 👉."""
    if NUMBERED.match(line):
        return True
    first = line[:1]
    return bool(first) and (first in "-–—•*+▪►▸→" or _is_picture(first))


def _clean(line: str) -> str:
    line = HASHTAG.sub(" ", line)
    line = SEE_MORE.sub("", line)
    line = "".join(BREAK if _is_picture(char) else char for char in line)
    line = re.sub(r"\s*\u2063[\s\u2063]*", BREAK, line).strip(BREAK + " ")
    return " ".join(line.split())


def _strip_marker(line: str) -> str:
    """The item without its dash or bullet; a number stays ("1. Ăn sáng"), it is part of what is said."""
    return line.lstrip("-–—•*+▪►▸→ ").strip()


def cut_words(text: str, limit: int) -> str:
    """`text` at most `limit` characters, cut between words, never inside one; a dangling comma or colon goes."""
    if len(text) <= limit:
        return text
    head = text[: limit + 1]
    space = head.rfind(" ")
    head = head[:space] if space > 0 else text[:limit]
    return head.rstrip(" ,;:–—-")


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in SENTENCE_END.split(text) if part.strip()]


def _words(text: str) -> int:
    return len(text.split())


def _split_long(text: str) -> list[str]:
    """A run-on line with no full stop, in pieces of about SCENE_WORDS[1] words."""
    words = text.split()
    if len(words) <= LONG_UNIT_WORDS:
        return [text]
    size = SCENE_WORDS[1]
    return [" ".join(words[start : start + size]) for start in range(0, len(words), size)]


def _screen_text(voice: str) -> str:
    """What the scene shows: the first clause of what it says, at most SCREEN_LENGTH characters."""
    number = NUMBERED.match(voice)
    prefix = number.group(0) if number else ""
    rest = voice[len(prefix) :]
    found = CLAUSE_END.search(rest)
    first = rest[: found.start()] if found and found.start() > 0 else rest
    return cut_words(prefix + first.strip(), SCREEN_LENGTH).rstrip(".!?…") or cut_words(voice, SCREEN_LENGTH)


def _is_call_to_action(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in CALLS_TO_ACTION)


def _merge(units: list[_Unit]) -> list[str]:
    """Scenes of about SCENE_WORDS words: a short sentence, or one following a scene still short, joins the scene
    before it; a list item is always a scene of its own."""
    scenes: list[_Unit] = []
    for unit in units:
        last = scenes[-1] if scenes else None
        if (
            last is not None
            and not unit.bullet
            and not last.bullet
            and (len(unit.text) < SHORT_SENTENCE or _words(last.text) < SCENE_WORDS[0])
            and _words(last.text) + _words(unit.text) <= SCENE_WORDS[1]
        ):
            last.text = f"{last.text} {unit.text}"
        else:
            scenes.append(_Unit(unit.text, unit.bullet))
    return [scene.text for scene in scenes]


def _paragraph(voice: str, screen: str | None = None) -> str:
    return f"{screen if screen is not None else _screen_text(voice)}\nĐọc: {voice}"


def _render(topic: str, middle: list[str], closing: str | None) -> str:
    parts = [_paragraph(topic, topic)] + [_paragraph(voice) for voice in middle]
    if closing:
        parts.append(_paragraph(closing))
    return "\n\n".join(parts)


def _fit(topic: str, middle: list[str], closing: str | None) -> list[str]:
    """Within 20 scenes and 5000 characters: the two neighbouring middle scenes with the fewest words are joined
    first (no idea is cut short) while the joined narration stays a scene's; past that, middle scenes are dropped from
    the end, a whole scene at a time."""
    middle = list(middle)
    fixed = 1 + (1 if closing else 0)

    def too_big() -> bool:
        return fixed + len(middle) > MAX_SCENES or len(_render(topic, middle, closing)) > MAX_SCRIPT_LENGTH

    while too_big() and len(middle) > 1:
        pairs = [
            (_words(middle[index]) + _words(middle[index + 1]), index)
            for index in range(len(middle) - 1)
            if len(middle[index]) + len(middle[index + 1]) + 1 <= MAX_VOICE_LENGTH
        ]
        if not pairs:
            break
        _, index = min(pairs)
        middle[index : index + 2] = [f"{middle[index]} {middle[index + 1]}"]
    while too_big() and middle:
        middle.pop()
    return middle


def clone_script(caption: str | None) -> ClonedScript:
    """The script of a clone from a competitor's caption, built in code: hashtags, emoji and "Xem thêm" dropped, the
    first sentence the title and the hook, each following idea a scene (a list item always its own), a closing call
    to action its own scene. Raises 422 when the caption has no words at all."""
    text = unicodedata.normalize("NFC", caption or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for raw in text.split("\n"):
        stripped = raw.strip()
        bullet = _starts_with_marker(stripped)
        line = _clean(stripped)
        if not any(char.isalnum() for char in line):
            continue  # only emoji, hashtags or decoration
        lines.append(_Unit(_strip_marker(line) if bullet else line, bullet))
    if not lines:
        raise ApiError(422, "competitor_video_no_text", NO_TEXT)

    first = _sentences(lines[0].text)
    taken = 1
    while taken < len(first) and _words(" ".join(first[:taken])) < 3:  # "Wow 😍 món này…": not a title alone
        taken += 1
    topic = cut_words(" ".join(first[:taken]), MAX_TOPIC_LENGTH)
    units: list[_Unit] = [_Unit(sentence) for sentence in first[taken:]]
    for line in lines[1:]:
        if line.bullet:
            units.extend(_Unit(piece, True) for piece in _split_long(line.text))
        else:
            units.extend(_Unit(piece) for sentence in _sentences(line.text) for piece in _split_long(sentence))
    units = [_Unit(cut_words(unit.text, MAX_VOICE_LENGTH), unit.bullet) for unit in units]

    closing = None
    if units and _is_call_to_action(units[-1].text):
        closing = units.pop().text
    cleaned_length = len(" ".join(line.text for line in lines))
    thin = not units or cleaned_length < THIN_CAPTION
    if thin and not units and closing is None:
        closing = CLOSING
    middle = _fit(topic, _merge(units), closing)
    script = _render(topic, middle, closing)
    return ClonedScript(topic=topic, script=script, scenes=1 + len(middle) + (1 if closing else 0), thin=thin)
