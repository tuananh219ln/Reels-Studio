"""Phụ đề "Cộng dồn" (docs/decisions/2026-11-27-cumulative-captions.md): the narration's words appear one by one and stay
until the phrase is over, then the screen is cleared for the next phrase. Marked words (`*like this*`) are one line of
their own, large and coloured. Drawn as pictures (one per step), like the other captions, in the "Neon game" look.

Each word's seconds are an estimate across the narration's length unless real ones are known (a clip's own sound).
"""

from dataclasses import dataclass

from PIL import Image

from .captions import Word
from .markup import normalize_text
from .pc_text import PAD, line_style, render_line, stack
from .textbox import FRAME_HEIGHT, FRAME_WIDTH

MAX_LINES = 3
MAX_WORDS = 9
LINE_CHARS = 16  # a plain line
PAUSE_MARKS = ",.!?:;…"
BREAK_PAUSE = 0.3  # a pause in the voice this long ends the phrase
BLANK_PAUSE = 0.6  # a pause this long leaves the screen empty
PAUSE_WEIGHT = 1.5  # extra words' worth of time after , . ! ? : ;

LEAD_SIZE, KEY_SIZE, TAIL_SIZE, PLAIN_SIZE = 58, 100, 72, 72
LINE_GAP = 0.1  # of the font size
ZONE_TOP_UPPER = 0.14  # "Trên": the phrase starts 14% down (14–30%)
ZONE_TOP = 0.62  # the phrase starts 62% down the frame (62–78%: clear of the platforms' caption bars)
MAX_LINE_WIDTH = round(FRAME_WIDTH * 0.92)


@dataclass(frozen=True)
class TimedWord:
    text: str
    start: float
    end: float
    key: bool = False


@dataclass(frozen=True)
class Line:
    text: str
    size: int
    key: bool


@dataclass(frozen=True)
class Step:
    """The phrase as it stands from `start` to `end`: the words said so far."""

    start: float
    end: float
    lines: tuple[Line, ...]


def estimate_words(text: str, start: float, seconds: float, keywords: frozenset[str] = frozenset()) -> list[TimedWord]:
    """The narration's words with their seconds estimated: each word one syllable (Vietnamese), plus a pause after
    punctuation. `keywords` (lower-cased words of the scene's marked text) mark words when the narration has no `*`."""
    words: list[tuple[str, bool]] = []
    for index, part in enumerate(text.split("*")):
        words += [(word, index % 2 == 1) for word in part.split()]
    if not words or seconds <= 0:
        return []
    if not any(key for _, key in words) and keywords:
        words = [(word, word.strip(PAUSE_MARKS).casefold() in keywords) for word, _ in words]
    weights = [1 + (PAUSE_WEIGHT if word[-1] in PAUSE_MARKS else 0) for word, _ in words]
    scale = seconds / sum(weights)
    timed, at = [], start
    for (word, key), weight in zip(words, weights):
        timed.append(TimedWord(normalize_text(word), at, at + weight * scale, key))
        at += weight * scale
    return timed


def voiced_words(
    text: str, voice_words: list[Word], start: float, keywords: frozenset[str] = frozenset()
) -> list[TimedWord]:
    """The narration's words at their real seconds (`voice_words`, from the narration's start; `start` is where it
    starts in the video), with the marks of `text`. [] when the two do not have the same words (the text changed since
    the narration was made, or the voice read it differently): the caller then estimates."""
    marked = estimate_words(text, 0, 1, keywords)
    if not marked or len(marked) != len(voice_words):
        return []
    return [
        TimedWord(word.text, start + spoken.start, start + spoken.end, word.key)
        for word, spoken in zip(marked, voice_words)
    ]


def narration_steps(
    text: str,
    voice_words: list[Word],
    begin: float,
    seconds: float,
    scene_end: float,
    keywords: frozenset[str] = frozenset(),
) -> list[Step]:
    """The "Cộng dồn" steps of one narration that starts `begin` seconds in and lasts `seconds`: at the real seconds of
    each word when `voice_words` has them (and they match `text`), else estimated across the narration."""
    words = voiced_words(text, voice_words, begin, keywords) or estimate_words(text, begin, seconds, keywords)
    return plan_cumulative(words, scene_end)


def known_words(words: list[Word]) -> list[TimedWord]:
    """Words whose real seconds are known (a clip's own sound), in the video's time."""
    return [
        TimedWord(normalize_text(word.text.replace("*", "").strip()), word.start, word.end)
        for word in words
        if word.text.replace("*", "").strip() and word.end > word.start
    ]


def _units(words: list[TimedWord]) -> list[list[TimedWord]]:
    """Words in the groups that appear together: a run of marked words is one, so it is never cut in two."""
    units: list[list[TimedWord]] = []
    for word in words:
        if word.key and units and units[-1][0].key:
            units[-1].append(word)
        else:
            units.append([word])
    return units


def _wrap(words: list[str], limit: int) -> list[str]:
    lines: list[str] = []
    for word in words:
        if lines and len(lines[-1]) + 1 + len(word) <= limit:
            lines[-1] += f" {word}"
        else:
            lines.append(word)
    return lines


def layout(words: list[TimedWord], has_key: bool) -> tuple[Line, ...]:
    """The words as lines: the plain words before a marked run (small), the run (large, one line), the plain words
    after it (medium). A phrase with no marked word is medium throughout (`has_key` is of the whole phrase, so the
    sizes do not change while it fills up)."""
    lines: list[Line] = []
    seen_key = False
    for key, group in _runs(words):
        texts = [word.text for word in group]
        if key:
            lines.append(Line(" ".join(texts), KEY_SIZE, True))
            seen_key = True
        else:
            size = (TAIL_SIZE if seen_key else LEAD_SIZE) if has_key else PLAIN_SIZE
            lines += [Line(text, size, False) for text in _wrap(texts, LINE_CHARS)]
    return tuple(lines)


def _runs(words: list[TimedWord]) -> list[tuple[bool, list[TimedWord]]]:
    runs: list[tuple[bool, list[TimedWord]]] = []
    for word in words:
        if runs and runs[-1][0] == word.key:
            runs[-1][1].append(word)
        else:
            runs.append((word.key, [word]))
    return runs


def chunks(words: list[TimedWord]) -> list[list[TimedWord]]:
    """The words split into phrases of at most MAX_WORDS words and MAX_LINES lines, ended at punctuation, at a
    pause in the voice and when full; a marked run is never split."""
    phrases: list[list[TimedWord]] = [[]]
    for unit in _units(words):
        current = phrases[-1]
        if current:
            full = len(current) + len(unit) > MAX_WORDS
            ended = current[-1].text[-1] in PAUSE_MARKS or unit[0].start - current[-1].end > BREAK_PAUSE
            crowded = len(layout(current + unit, any(w.key for w in current + unit))) > MAX_LINES
            if full or ended or crowded:
                phrases.append([])
        phrases[-1] += unit
    return [phrase for phrase in phrases if phrase]


def plan_cumulative(words: list[TimedWord], scene_end: float) -> list[Step]:
    """One step each time words appear, from the moment they are said; a phrase stays to its next one's start, or is
    cleared at its last word when the voice then rests for BLANK_PAUSE. The last phrase of a scene stays to the scene's
    end, so none crosses into the next scene."""
    steps: list[Step] = []
    phrases = chunks([word for word in words if word.start < scene_end])
    for number, phrase in enumerate(phrases):
        has_key = any(word.key for word in phrase)
        units = _units(phrase)
        if number + 1 < len(phrases):
            following = phrases[number + 1][0].start
            end = following if following - phrase[-1].end <= BLANK_PAUSE else phrase[-1].end
        else:
            end = scene_end
        end = min(end, scene_end)
        for index, unit in enumerate(units):
            shown = [word for earlier in units[: index + 1] for word in earlier]
            until = units[index + 1][0].start if index + 1 < len(units) else end
            if until - unit[0].start > 0.02:
                steps.append(Step(unit[0].start, min(until, end), layout(shown, has_key)))
    return steps


def render_cumulative(
    lines: tuple[Line, ...], style: str = "neon_game", zone: str | None = None
) -> tuple[Image.Image, tuple[int, int]]:
    """The lines as one picture in the chosen look (pc_text.PC_STYLES), centred across, and where its corner goes in the
    frame (the first line starts ZONE_TOP down)."""
    pictures = [
        render_line(line.text, line.size, line_style(style, line.key, index), MAX_LINE_WIDTH)
        for index, line in enumerate(lines)
    ]
    picture = stack(pictures, [round(LINE_GAP * line.size) for line in lines[:-1]])
    return picture, (
        (FRAME_WIDTH - picture.width) // 2,
        round(FRAME_HEIGHT * (ZONE_TOP_UPPER if zone == "top" else ZONE_TOP)) - PAD,
    )
