"""'Từ video mẫu': a new video learned from a sample video (a pasted link or an uploaded file).

The worker prepares the sample once: downloads a link, keeps the file in storage, takes up to MAX_FRAMES stills at
even steps and has ElevenLabs write down what is said. The LLM sees the stills as images, with the words and their
seconds, and writes a script in the app's usual format, plus the stretch of the sample to show behind each scene;
those stretches are cut from the stored file and become the scenes' clips. A scene without one is left to "Tự tìm
ảnh" like any scene without a photo.

Four ways (`Video.reference_mode`), chosen when the video is made:
- quick: one call sees the stills and writes the analysis and the script together;
- twostep: one call analyses the sample (with the stills), a second writes from the analysis without them;
- review: the analysis is written first and the job stops; a member edits it, then "Viết kịch bản" writes;
- reuse: a sample analysed before writes another video, without downloading or analysing it again.
"""

import logging
import math
import secrets
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session as DbSession

from . import clips, knowledge, remote_media, source_keys, stt
from .claude import (
    ClaudeError,
    GeneratedScript,
    ScriptOutputError,
    build_analyze_prompt,
    build_learn_prompt,
    json_object,
    parse_output,
)
from .models import KnowledgeTopic, Scene, VideoReference
from .script_rules import CROSSFADE_SIDE_SECONDS
from .sessions import now
from .storage import DirectoryStorage
from .tts import TtsError
from .uploads import UploadRejected

log = logging.getLogger(__name__)

MODES = ("quick", "twostep", "review", "reuse")
MIN_SAMPLE_SECONDS = 3
MAX_SAMPLE_SECONDS = 180
MAX_FRAMES = 16
FRAME_STEP_SECONDS = 2
FRAME_WIDTH = 540
MIN_CLIP_SECONDS = 1.5
MAX_CLIP_SECONDS = 10
# A clip a little longer than its scene, so the narration may stretch the scene ("Tự khớp lời đọc") a bit without
# the clip ending on a held frame.
CLIP_SPARE_SECONDS = 2.0
MAX_ANALYSIS_LENGTH = 8000

# (prompt, label, images) -> the answer's text
SeeingCall = Callable[[str, str, Sequence[bytes]], str]


class ReferenceError(Exception):
    """`message` is shown to members, `detail` is diagnostic."""

    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.message = message
        self.detail = detail


def source_key(reference_id: int, extension: str) -> str:
    return f"references/{reference_id}/source-{secrets.token_hex(6)}.{extension}"


def is_prepared(reference: VideoReference) -> bool:
    return bool(reference.video_key and reference.frames)


def is_analyzed(reference: VideoReference) -> bool:
    return bool(reference.analysis.strip())


# --- Preparing the sample ---


def prepare(db: DbSession, reference: VideoReference, storage: DirectoryStorage, folder: Path) -> None:
    """Download (a link), stills and words, once per sample; a retried job skips what is already stored."""
    if is_prepared(reference):
        return
    if not reference.video_key:
        if not reference.source_url:
            raise ReferenceError("Video mẫu không còn file, hãy tạo lại từ link hoặc tải lên lại")
        try:
            path = remote_media.download_sample(reference.source_url, folder)
        except remote_media.RemoteMediaError as err:
            raise ReferenceError(str(err)) from None
        sample = check_sample(path)
        key = source_key(reference.id, sample.extension)
        storage.save_file(key, path)
        reference.video_key, reference.seconds = key, round(sample.seconds, 3)
        db.commit()
    path = storage.path(reference.video_key)
    sample = check_sample(path)
    reference.seconds = round(sample.seconds, 3)
    reference.transcript = _transcript(db, path, sample, folder)
    reference.frames = _frames(storage, reference, path, sample)
    db.commit()


def check_sample(path: Path) -> clips.Sample:
    try:
        sample = clips.probe_sample(path)
    except UploadRejected as err:
        raise ReferenceError(str(err)) from None
    if not MIN_SAMPLE_SECONDS <= sample.seconds <= MAX_SAMPLE_SECONDS:
        raise ReferenceError(
            f"Video mẫu phải dài từ {MIN_SAMPLE_SECONDS} giây đến {MAX_SAMPLE_SECONDS // 60} phút "
            f"(đang là {sample.seconds:.0f} giây)"
        )
    return sample


def frame_seconds(seconds: float) -> list[float]:
    """Evenly spread moments: one every FRAME_STEP_SECONDS, at most MAX_FRAMES, each in the middle of its stretch."""
    count = max(1, min(MAX_FRAMES, math.ceil(seconds / FRAME_STEP_SECONDS)))
    step = seconds / count
    return [round(step * (n + 0.5), 1) for n in range(count)]


def _frames(storage: DirectoryStorage, reference: VideoReference, path: Path, sample: clips.Sample) -> list[dict]:
    frames = []
    for second in frame_seconds(sample.seconds):
        try:
            data = clips.still_jpeg(path, sample, second, FRAME_WIDTH)
        except clips.ClipError as err:
            log.warning("Reference %s: no frame at %ss: %s", reference.id, second, err)
            continue
        if not data:
            continue
        key = f"references/{reference.id}/frame-{secrets.token_hex(6)}.jpg"
        storage.save_bytes(key, data)
        frames.append({"second": second, "key": key, "note": ""})
    if not frames:
        raise ReferenceError("Không lấy được khung hình nào từ video mẫu, hãy thử video khác")
    return frames


def _transcript(db: DbSession, path: Path, sample: clips.Sample, folder: Path) -> str:
    """What is said, or "" when the sample is silent, no ElevenLabs key is set or ElevenLabs will not write the words
    down: the stills alone still work."""
    if not sample.has_audio:
        return ""
    key = source_keys.get(db, "elevenlabs")
    if not key:
        log.info("No ElevenLabs key: the sample's words are not written down")
        return ""
    audio = folder / "sample-sound.mp3"
    try:
        clips.sound_mp3(path, sample, audio)
    except clips.ClipError as err:
        log.warning("Sample sound not extracted: %s", err)
        return ""
    try:
        return stt.transcribe(audio, key)
    except TtsError as err:
        # The words are optional (decisions 2026-11-05): a key without the speech_to_text permission, out of quota or
        # an ElevenLabs outage leaves the sample to its stills, as no key does, rather than failing the whole job.
        log.warning("The sample's words are not written down: %s %s", err.message, err.detail)
        return ""


def frame_lines(reference: VideoReference) -> str:
    """The stills as the prompt names them, in the order the images are sent."""
    lines = []
    for number, frame in enumerate(reference.frames, start=1):
        note = f": {frame['note']}" if frame.get("note") else ""
        lines.append(f"Khung {number} (ảnh thứ {number} gửi kèm, giây {frame['second']:g}){note}")
    return "\n".join(lines)


def frame_images(storage: DirectoryStorage, reference: VideoReference) -> list[bytes]:
    return [storage.path(frame["key"]).read_bytes() for frame in reference.frames if storage.exists(frame["key"])]


# --- The LLM ---


def _ask(call: Callable[[], str], parse: Callable[[str], object], on_call: Callable[[], None], label: str):
    """Ask once more when the answer is unusable, then give up with the raw answer as the detail."""
    for attempt in (1, 2):
        raw = call()
        on_call()
        try:
            return parse(raw)
        except ScriptOutputError as err:
            log.warning("LLM answer unusable for %s (attempt %d): %s\n%s", label, attempt, err, raw[:4000])
            problem = err
    raise ClaudeError(
        f"AI trả lời không đúng định dạng ({problem}), đã thử lại 1 lần", f"Câu trả lời thô:\n{raw[:8000]}"
    )


def _analysis_text(value: object) -> str:
    return value.strip()[:MAX_ANALYSIS_LENGTH] if isinstance(value, str) else ""


def analyze(
    reference: VideoReference,
    topic: KnowledgeTopic | None,
    storage: DirectoryStorage,
    call: SeeingCall,
    on_call: Callable[[], None],
    label: str,
) -> None:
    """The analysis on its own, with a short note on what each still shows (for a later call that does not see
    them)."""
    template = (topic.analyze_prompt if topic else "") or knowledge.default_analyze_prompt()
    prompt = build_analyze_prompt(template, reference.transcript, frame_lines(reference), len(reference.frames))
    images = frame_images(storage, reference)

    def parse(raw: str) -> tuple[str, list[str]]:
        data = json_object(raw)
        analysis = _analysis_text(data.get("phan_tich"))
        if not analysis:
            raise ScriptOutputError("thiếu phần phân tích")
        notes = data.get("khung_hinh")
        notes = [str(note).strip()[:300] if isinstance(note, (str, int, float)) else "" for note in notes or []]
        return analysis, notes if isinstance(notes, list) else []

    analysis, notes = _ask(lambda: call(prompt, label, images), parse, on_call, label)
    reference.analysis = analysis
    reference.analyzed_at = now()
    reference.frames = [
        {**frame, "note": notes[index] if index < len(notes) else frame.get("note", "")}
        for index, frame in enumerate(reference.frames)
    ]


@dataclass(frozen=True)
class Learned:
    script: GeneratedScript
    title_clip: tuple[float, float] | None
    clips: list[tuple[float, float] | None]  # per content scene, in order
    analysis: str  # written in the same answer (quick); "" otherwise


def clip_range(value: object, seconds: float) -> tuple[float, float] | None:
    """A {"tu", "den"} (or [from, to]) stretch of the sample, kept inside it and between MIN_CLIP_SECONDS and
    MAX_CLIP_SECONDS long; anything unusable is None."""
    if isinstance(value, dict):
        value = (value.get("tu", value.get("from")), value.get("den", value.get("to")))
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        start, end = float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(start) and math.isfinite(end)):
        return None
    start = max(0.0, min(start, seconds - MIN_CLIP_SECONDS))
    end = min(seconds, max(end, start + MIN_CLIP_SECONDS), start + MAX_CLIP_SECONDS)
    return (round(start, 2), round(end, 2)) if end - start >= MIN_CLIP_SECONDS - 0.01 else None


def write(
    video_topic: str,
    reference: VideoReference,
    topic: KnowledgeTopic,
    storage: DirectoryStorage,
    call: SeeingCall,
    on_call: Callable[[], None],
    label: str,
    *,
    with_images: bool,
    with_analysis: bool,
) -> Learned:
    template = topic.learn_prompt or knowledge.default_learn_prompt()
    seconds = reference.seconds or 0.0
    prompt = build_learn_prompt(
        template,
        video_topic,
        reference.transcript,
        reference.analysis,
        frame_lines(reference),
        seconds,
        topic.banned_words,
        topic.photo_hint,
        with_analysis=with_analysis,
    )
    images = frame_images(storage, reference) if with_images else []

    def parse(raw: str) -> Learned:
        script = parse_output(raw)
        data = json_object(raw)
        items = data.get("scenes") if isinstance(data.get("scenes"), list) else []
        items = [item for item in items if isinstance(item, dict)]
        scene_clips = [clip_range(item.get("clip"), seconds) for item in items][: len(script.scenes)]
        scene_clips += [None] * (len(script.scenes) - len(scene_clips))
        return Learned(
            script,
            clip_range(data.get("title_clip"), seconds),
            scene_clips,
            _analysis_text(data.get("phan_tich")) if with_analysis else "",
        )

    return _ask(lambda: call(prompt, label, images), parse, on_call, label)


# --- Scene clips ---


def attach_clips(
    storage: DirectoryStorage,
    reference: VideoReference,
    title: Scene | None,
    scenes: list[Scene],
    learned: Learned,
    folder: Path,
    new_key: Callable[[str], str],
) -> int:
    """Cut each chosen stretch from the stored sample and make it the scene's clip; returns how many were attached.
    A cut that fails leaves its scene to "Tự tìm ảnh" instead of failing the script."""
    if not reference.video_key or not storage.exists(reference.video_key):
        return 0
    path = storage.path(reference.video_key)
    try:
        sample = clips.probe_sample(path)
    except UploadRejected:
        return 0
    pairs = [(title, learned.title_clip)] if title is not None else []
    pairs += list(zip(scenes, learned.clips, strict=False))
    attached = 0
    for scene, stretch in pairs:
        if scene is None or stretch is None:
            continue
        start, end = stretch
        sides = 1 if scene.is_title else 2
        wanted = scene.seconds + sides * CROSSFADE_SIDE_SECONDS + CLIP_SPARE_SECONDS
        length = min(max(end - start, wanted), sample.seconds - start)
        if length < MIN_CLIP_SECONDS:
            continue
        target = folder / f"scene-{scene.id}.mp4"
        try:
            clips.cut_part(path, sample, start, length, target)
            clip = clips.check_clip(target)
        except (clips.ClipError, UploadRejected) as err:
            log.warning("Scene %s: clip %s–%s not cut: %s", scene.id, start, end, err)
            continue
        key = new_key(f"clip-{scene.id}")
        storage.save_file(key, target)
        scene.video_key, scene.video_seconds, scene.video_start, scene.video_speed = key, round(clip.seconds, 3), 0, 1
        scene.image_key, scene.image_source, scene.image_error, scene.image_auto = None, None, None, False
        # The scene keeps its seconds while the clip is long enough for them.
        playable = clip.seconds - sides * CROSSFADE_SIDE_SECONDS
        if playable < scene.seconds:
            scene.seconds = max(1.0, math.floor(playable * 10) / 10)
        attached += 1
    return attached
