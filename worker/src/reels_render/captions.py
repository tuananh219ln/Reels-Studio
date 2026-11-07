"""Captions: the spoken text split into short phrases, timed across what is said.

A narration's timing is an estimate: each word gets a share of the narration's length by its letters, plus a
pause after punctuation. Vietnamese words are single syllables of similar length, so the estimate stays close to
the voice; ElevenLabs' character timestamps could replace it later without changing anything else. A clip's own
sound ("Edit từ footage") comes with each word's real seconds from Speech-to-Text, and those are used as they are.
"""

from dataclasses import dataclass

from .textbox import caption_lines

MAX_PHRASE_WORDS = 4
PAUSE_WEIGHT = 3  # extra letters' worth of time after , . ! ? : ;
PAUSE_MARKS = ",.!?:;…"


@dataclass(frozen=True)
class Word:
    """One spoken word and its seconds: in the clip's own time in a script, in the video's time once placed."""

    text: str
    start: float
    end: float


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    lines: list[list[str]]
    lit: int | None  # the word being spoken, counted across `lines`; None in phrase mode


def _phrases(words: list[str]) -> list[list[str]]:
    phrases: list[list[str]] = [[]]
    for word in words:
        if len(phrases[-1]) == MAX_PHRASE_WORDS or (phrases[-1] and phrases[-1][-1][-1] in PAUSE_MARKS):
            phrases.append([])
        phrases[-1].append(word)
    # A phrase that still needs more than two caption lines (very long words) is split in half until it fits.
    fitted: list[list[str]] = []
    pending = [phrase for phrase in phrases if phrase]
    while pending:
        phrase = pending.pop(0)
        if len(phrase) > 1 and caption_lines(phrase) is None:
            half = len(phrase) // 2
            pending[:0] = [phrase[:half], phrase[half:]]
        else:
            fitted.append(phrase)
    return fitted


def plan_captions(text: str, start: float, seconds: float, mode: str) -> list[Cue]:
    """Cues for one scene's narration, which starts at `start` and lasts `seconds`; none for mode "off"."""
    words = [word for word in text.replace("*", "").split() if word]
    if mode == "off" or not words or seconds <= 0:
        return []
    weights = [len(word) + 1 + (PAUSE_WEIGHT if word[-1] in PAUSE_MARKS else 0) for word in words]
    scale = seconds / sum(weights)
    times, elapsed = [], start
    for weight in weights:
        times.append(elapsed)
        elapsed += weight * scale
    times.append(start + seconds)

    cues: list[Cue] = []
    first = 0
    for phrase in _phrases(words):
        lines = caption_lines(phrase) or [phrase]
        last = first + len(phrase)
        if mode == "phrase":
            cues.append(Cue(times[first], times[last], lines, None))
        else:
            cues += [Cue(times[first + n], times[first + n + 1], lines, n) for n in range(len(phrase))]
        first = last
    return cues


def plan_word_captions(words: list[Word], mode: str) -> list[Cue]:
    """Cues for words whose seconds are known (in the video's time), grouped into phrases as the estimate is. A word
    is lit until the next one starts, so the caption does not blink in the short gaps between words; a phrase stays
    until its last word ends."""
    words = [word for word in words if word.text.replace("*", "").strip() and word.end > word.start]
    if mode == "off" or not words:
        return []
    texts = [word.text.replace("*", "").strip() for word in words]
    cues: list[Cue] = []
    first = 0
    for phrase in _phrases(texts):
        lines = caption_lines(phrase) or [phrase]
        last = first + len(phrase)
        timed = words[first:last]
        if mode == "phrase":
            cues.append(Cue(timed[0].start, timed[-1].end, lines, None))
        else:
            for n, word in enumerate(timed):
                end = timed[n + 1].start if n + 1 < len(timed) else word.end
                cues.append(Cue(word.start, max(end, word.start + 0.05), lines, n))
        first = last
    return cues
