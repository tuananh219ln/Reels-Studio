"""'Edit từ footage': a member's own footage of someone talking, cut into scenes by what is said.

The learn job prepares the footage like a sample video (reference.py: stored file, stills, words from ElevenLabs
Speech-to-Text with each word's seconds). Here, with no LLM: the words are split into stretches of speech at every
pause and every filler ("ờ", "à", "ừm"…), and a stretch longer than a scene may be is split at a sentence end or its
longest gap; a short one stays a scene of its own, a jump cut. Each stretch becomes a scene whose clip is cut from the footage
with its own sound ("Tiếng gốc") and the words it says, so the captions follow the real speech. The title scene is
the first stretch with the video's topic as its text. The video is set up for speech: no narration, hard cuts,
word-by-word captions and the music ducking under the voice.
"""

import logging
import math
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session as DbSession

from . import clips
from .models import Scene, Video, VideoReference
from .reference import ReferenceError, check_sample, spoken_words
from .script_rules import MAX_SECONDS, MAX_TITLE_WORDS, MAX_TOTAL_SECONDS, MIN_SECONDS, text_problem
from .storage import DirectoryStorage
from .uploads import UploadRejected

log = logging.getLogger(__name__)

# What is dropped between stretches: hesitation sounds, compared without case, accents' composition or punctuation.
FILLERS = frozenset(
    {"ờ", "ơ", "à", "ừ", "ừm", "ưm", "ờm", "ờ ờ", "hừm", "hmm", "ừa", "uh", "um", "uhm", "ah", "er", "erm", "eh"}
)
# A silence between two words at least this long is cut out ("Mặc định" of AIEV's auto-cut: 0.45 s).
PAUSE_SECONDS = 0.45
# Kept around each stretch so the first sound and the last word's tail are not clipped.
PAD_BEFORE = 0.12
PAD_AFTER = 0.25
SENTENCE_ENDS = (".", "!", "?", "…")
# Extra clip after the scene's end, so a scene lengthened a little in the studio does not end on a held frame.
CLIP_SPARE_SECONDS = 0.5


@dataclass(frozen=True)
class Segment:
    """A stretch of the footage to keep, in the footage's seconds, and the words said in it."""

    start: float
    end: float
    words: tuple[dict, ...]

    @property
    def seconds(self) -> float:
        return self.end - self.start

    @property
    def text(self) -> str:
        return " ".join(word["text"] for word in self.words)


def _bare(text: str) -> str:
    text = unicodedata.normalize("NFC", text).casefold()
    return " ".join("".join(ch for ch in text if ch.isalnum() or ch.isspace()).split())


def is_filler(text: str) -> bool:
    return _bare(text) in FILLERS


def _runs(words: list[dict]) -> list[list[dict]]:
    """Stretches of speech, split at every filler and every pause of PAUSE_SECONDS or more."""
    runs: list[list[dict]] = []
    current: list[dict] = []
    for word in words:
        if is_filler(word["text"]):
            if current:
                runs.append(current)
            current = []
            continue
        if current and word["start"] - current[-1]["end"] >= PAUSE_SECONDS:
            runs.append(current)
            current = []
        current.append(word)
    if current:
        runs.append(current)
    return runs


def _span(run: list[dict]) -> float:
    return run[-1]["end"] - run[0]["start"] + PAD_BEFORE + PAD_AFTER


def _split_long(run: list[dict]) -> list[list[dict]]:
    """A stretch longer than a scene may be, split until each part fits: after the sentence end nearest its middle,
    else at its longest gap between words, else in the middle."""
    if _span(run) <= MAX_SECONDS or len(run) < 2:
        return [run]
    middle = (run[0]["start"] + run[-1]["end"]) / 2
    cuts = range(1, len(run))
    sentence = [n for n in cuts if run[n - 1]["text"].endswith(SENTENCE_ENDS)]
    if sentence:
        at = min(sentence, key=lambda n: abs(run[n]["start"] - middle))
    else:
        gaps = {n: run[n]["start"] - run[n - 1]["end"] for n in cuts}
        widest = max(gaps.values())
        at = (
            min((n for n in cuts if gaps[n] == widest), key=lambda n: abs(run[n]["start"] - middle))
            if widest > 0.05
            else min(cuts, key=lambda n: abs(run[n]["start"] - middle))
        )
    return _split_long(run[:at]) + _split_long(run[at:])


def plan(words: list[dict], footage_seconds: float) -> list[Segment]:
    """The stretches to keep, in order, at most MAX_TOTAL_SECONDS together (the rest is left out). Each is padded
    around its words, never past the footage or into its neighbour's words. A short one stays a scene of its own (a
    jump cut, never joined to a neighbour, which would bring the pause or the filler back): one under MIN_SECONDS
    takes a little of the silence after it, then before it, and joins the previous scene only when it cannot."""
    runs: list[list[dict]] = []
    for run in _runs(words):
        runs += _split_long(run)
    # Where each word sits among all of them, fillers included, so the padding never reaches into a dropped filler.
    order = {id(word): position for position, word in enumerate(words)}
    segments: list[Segment] = []
    for run in runs:
        first, last = order[id(run[0])], order[id(run[-1])]
        previous_end = max(segments[-1].end if segments else 0.0, words[first - 1]["end"] if first > 0 else 0.0)
        following = words[last + 1]["start"] if last + 1 < len(words) else footage_seconds
        start = max(previous_end, run[0]["start"] - PAD_BEFORE, 0.0)
        end = min(following, run[-1]["end"] + PAD_AFTER, footage_seconds)
        if end - start < MIN_SECONDS:
            end = min(following, footage_seconds, start + MIN_SECONDS)
            start = max(previous_end, 0.0, end - MIN_SECONDS)
        start, end = round(start, 2), round(min(end, start + MAX_SECONDS), 2)
        if end - start >= MIN_SECONDS:
            segments.append(Segment(start, end, tuple(run)))
        elif segments and end - segments[-1].start <= MAX_SECONDS:
            last = segments[-1]
            segments[-1] = Segment(last.start, end, last.words + tuple(run))
    kept, total = [], 0.0
    for segment in segments:
        if total + segment.seconds > MAX_TOTAL_SECONDS:
            break
        kept.append(segment)
        total += segment.seconds
    return kept


def title_text(topic: str) -> str:
    """The title scene's text: the video's topic, its `*marked*` words kept, shortened until it fits the title box (a
    cut that leaves a mark unpaired does not fit either, so it is shortened further)."""
    words = topic.split()[:MAX_TITLE_WORDS]
    while words and text_problem(" ".join(words), True):
        words = words[:-1]
    return " ".join(words)


def _clip_words(segment: Segment) -> list[dict]:
    """The segment's words in its clip's own seconds (the clip is cut from the segment's start)."""
    return [
        {
            "text": word["text"],
            "start": round(max(0.0, word["start"] - segment.start), 3),
            "end": round(max(0.0, word["end"] - segment.start), 3),
        }
        for word in segment.words
    ]


def make(
    db: DbSession,
    video: Video,
    sample: VideoReference,
    storage: DirectoryStorage,
    folder: Path,
    new_key: Callable[[str], str],
) -> int:
    """Cut the footage into the video's scenes; returns how many content scenes it made. Raises ReferenceError with a
    member message when there is nothing to cut by."""
    path = storage.path(sample.video_key)
    footage = check_sample(path)
    if not sample.words:
        sample.words = spoken_words(db, path, footage, folder, required=True)
        db.commit()
    segments = plan(sample.words, footage.seconds)
    if len(segments) < 2:
        raise ReferenceError(
            "Footage có quá ít lời nói để dựng: cần ít nhất hai đoạn nói, mỗi đoạn từ "
            f"{MIN_SECONDS} giây (đang có {len(segments)})"
        )
    title = title_text(video.topic)
    video.has_script = True
    video.hand_written = True  # no AI wrote these words, so no AI reviewed their safety
    video.title_options = [title] if title else []
    video.voice_enabled = False
    options = dict(video.options or {})
    options.update({"transition": "cut", "captions": "word", "ducking": True})
    video.options = options
    made = 0
    for position, segment in enumerate(segments):
        target = folder / f"part-{position:03d}.mp4"
        length = min(segment.seconds + CLIP_SPARE_SECONDS, footage.seconds - segment.start)
        try:
            clips.cut_part(path, footage, segment.start, length, target, sound=True)
            clip = clips.check_clip(target)
        except (clips.ClipError, UploadRejected) as err:
            raise ReferenceError(
                f"Không cắt được đoạn {segment.start:.1f}–{segment.end:.1f} giây của footage", str(err)
            ) from None
        key = new_key(f"footage-{position}")
        storage.save_file(key, target)
        is_title = position == 0
        db.add(
            Scene(
                video_id=video.id,
                is_title=is_title,
                position=position,
                text=title if is_title else "",
                # Tenths, as a member types them, never past the clip.
                seconds=max(MIN_SECONDS, math.floor(min(segment.seconds, clip.seconds) * 10) / 10),
                seconds_auto=False,
                keywords=[],
                keywords_en=[],
                voice_text=segment.text,
                video_key=key,
                video_seconds=round(clip.seconds, 3),
                video_start=0,
                video_speed=1,
                video_sound=True,
                words=_clip_words(segment),
            )
        )
        made += 0 if is_title else 1
    log.info("Footage %s cut into %d scenes for video %s", sample.id, len(segments), video.id)
    return made
