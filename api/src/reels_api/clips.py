"""Scene video clips: checking an upload with ffprobe and taking one frame for previews.

The container type is read from the file's first bytes and then forced with `-f`, so FFmpeg never picks a
playlist or concat demuxer that would open other files named inside an uploaded file.
"""

import io
import json
import math
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .uploads import UploadRejected

# The web worker on Cloudflare buffers the whole request (128 MB of memory, 100 MB request limit), so clips stay
# well below both.
MAX_CLIP_BYTES = 50 * 1024 * 1024
MIN_CLIP_SECONDS = 1
MAX_CLIP_SECONDS = 60
MIN_SHORT_SIDE = 720
MAX_LONG_SIDE = 4096
CODECS = {"h264", "hevc", "vp9"}
# The headers ffprobe reads can lie: H.264 may switch to a huge size mid-stream. The decoder refuses any frame
# above this (4096×2304, a little over DCI 4K either way up), so a small upload can never decode gigabytes.
MAX_FRAME_PIXELS = 4096 * 2304
FFMPEG_SECONDS = 30
_REFUSED = "Video phải là MP4, MOV hoặc WebM (H.264, HEVC hoặc VP9) và không bị hỏng"


class ClipError(Exception):
    """FFmpeg is missing, timed out, or could not read a stored clip."""


@dataclass(frozen=True)
class Clip:
    extension: str
    seconds: float


def _container(head: bytes) -> tuple[str, str] | None:
    """The demuxer to force and the stored extension, from the file's first bytes."""
    if head[4:8] == b"ftyp":
        return "mov", "mp4"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "matroska", "webm"
    return None


def looks_like_clip(head: bytes) -> bool:
    """Whether a file's first bytes are an MP4/MOV or WebM container's (checked fully by check_clip)."""
    return _container(head) is not None


def _tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise ClipError(f"Máy chủ chưa cài {name}")
    return path


def _run(argv: list[str]) -> bytes:
    try:
        result = subprocess.run(
            argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=FFMPEG_SECONDS, check=False
        )
    except subprocess.TimeoutExpired:
        raise ClipError(f"{Path(argv[0]).name} chạy quá {FFMPEG_SECONDS} giây") from None
    if result.returncode != 0:
        raise ClipError(result.stderr.decode("utf-8", "replace").strip()[-500:])
    return result.stdout


def _demuxer(path: Path) -> tuple[str, str]:
    with open(path, "rb") as file:
        found = _container(file.read(8))
    if found is None:
        raise UploadRejected(_REFUSED)
    return found


def _probe(path: Path) -> tuple[str, str, dict]:
    """The demuxer, the stored extension and ffprobe's streams and format."""
    demuxer, extension = _demuxer(path)
    try:
        raw = _run(
            [_tool("ffprobe"), "-v", "error", "-f", demuxer, "-show_streams", "-show_format", "-of", "json", str(path)]
        )
        return demuxer, extension, json.loads(raw)
    except (ClipError, json.JSONDecodeError):
        raise UploadRejected(_REFUSED) from None


def _length(data: dict) -> float | None:
    """The first video stream's own length: the container's is the longest stream, often a longer audio track. WebM
    usually stores no per-stream length, and then the container's is all there is."""
    videos = [stream for stream in data.get("streams", []) if stream.get("codec_type") == "video"]
    own = _seconds(videos[0].get("duration")) if videos else None
    return own or _seconds(data.get("format", {}).get("duration"))


def first_part(path: Path, folder: Path) -> Path:
    """A clip taken from a link (a TikTok video often runs past a minute) cut to its first MAX_CLIP_SECONDS without
    re-encoding; a shorter clip, or a file that is not one, is returned as is for check_clip to judge."""
    try:
        demuxer, extension, data = _probe(path)
    except UploadRejected:
        return path
    seconds = _length(data)
    if seconds is None or seconds <= MAX_CLIP_SECONDS:
        return path
    target = folder / f"first-part.{extension}"
    # A stream copy ends on the first packet past -t, so it stops a little short of the limit.
    try:
        _cut(path, demuxer, extension, target)
    except ClipError:
        raise UploadRejected(_REFUSED) from None
    return target


def _cut(path: Path, demuxer: str, extension: str, target: Path) -> None:
    _run(
        [
            _tool("ffmpeg"),
            "-v",
            "error",
            "-nostdin",
            "-y",
            "-f",
            demuxer,
            "-i",
            str(path),
            "-t",
            f"{MAX_CLIP_SECONDS - 0.5:g}",
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-c",
            "copy",
            "-f",
            "mp4" if extension == "mp4" else "webm",
            str(target),
        ]
    )


def check_clip(path: Path) -> Clip:
    """Refuse anything that is not a 1–60 s MP4/MOV/WebM clip with a usable video stream."""
    _, extension, data = _probe(path)
    videos = [stream for stream in data.get("streams", []) if stream.get("codec_type") == "video"]
    if not videos:
        raise UploadRejected(_REFUSED)
    # Every video stream is checked, not only the first: a huge or unexpected extra stream must never be stored.
    for stream in videos:
        if stream.get("codec_name") not in CODECS:
            raise UploadRejected(_REFUSED)
        width, height = int(stream.get("width") or 0), int(stream.get("height") or 0)
        if min(width, height) < MIN_SHORT_SIDE or max(width, height) > MAX_LONG_SIDE:
            raise UploadRejected(
                f"Video phải có cạnh ngắn từ {MIN_SHORT_SIDE} px và cạnh dài tối đa {MAX_LONG_SIDE} px "
                f"(đang là {width}×{height})"
            )
    seconds = _length(data)
    if seconds is None:
        raise UploadRejected("Không đọc được độ dài video")
    if not MIN_CLIP_SECONDS <= seconds <= MAX_CLIP_SECONDS:
        raise UploadRejected(
            f"Video phải dài từ {MIN_CLIP_SECONDS} đến {MAX_CLIP_SECONDS} giây (đang là {seconds:.1f} giây)"
        )
    return Clip(extension, seconds)


@dataclass(frozen=True)
class Sample:
    """A sample video ("Từ video mẫu", reference.py) as ffprobe read it."""

    demuxer: str
    extension: str
    seconds: float
    has_audio: bool


def probe_sample(path: Path) -> Sample:
    """A sample video's container, length and whether it has sound; anything but a readable MP4/MOV/WebM with a
    usable video stream is refused like an upload. Its size and length are judged by the caller."""
    demuxer, extension, data = _probe(path)
    streams = data.get("streams", [])
    videos = [stream for stream in streams if stream.get("codec_type") == "video"]
    if not videos or videos[0].get("codec_name") not in CODECS:
        raise UploadRejected(_REFUSED)
    width, height = int(videos[0].get("width") or 0), int(videos[0].get("height") or 0)
    if not width or not height or width * height > MAX_FRAME_PIXELS:
        raise UploadRejected(_REFUSED)
    seconds = _length(data)
    if seconds is None:
        raise UploadRejected("Không đọc được độ dài video")
    has_audio = any(stream.get("codec_type") == "audio" for stream in streams)
    return Sample(demuxer, extension, seconds, has_audio)


def has_sound(path: Path) -> bool:
    """Whether a stored clip has a sound track to be heard ("Tiếng gốc")."""
    try:
        return probe_sample(path).has_audio
    except (UploadRejected, OSError):
        return False


def still_jpeg(path: Path, sample: Sample, second: float, width: int) -> bytes:
    """The frame at `second`, at most `width` pixels wide, as JPEG."""
    return _run(
        [
            _tool("ffmpeg"),
            "-v",
            "error",
            "-nostdin",
            "-ss",
            f"{second:.3f}",
            "-max_pixels",
            str(MAX_FRAME_PIXELS),
            "-f",
            sample.demuxer,
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-frames:v",
            "1",
            "-vf",
            f"scale='min({width},iw)':-2",
            "-q:v",
            "4",
            "-f",
            "image2pipe",
            "-c:v",
            "mjpeg",
            "-",
        ]
    )


def sound_mp3(path: Path, sample: Sample, target: Path) -> None:
    """The first audio stream as a small mono MP3, enough for speech-to-text."""
    _run(
        [
            _tool("ffmpeg"),
            "-v",
            "error",
            "-nostdin",
            "-y",
            "-f",
            sample.demuxer,
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "48k",
            str(target),
        ]
    )


def cut_part(path: Path, sample: Sample, start: float, length: float, target: Path, *, sound: bool = False) -> None:
    """`length` seconds from `start` as an H.264 MP4, its short side raised to MIN_SHORT_SIDE when smaller (a YouTube
    video may come at 360p), so it passes check_clip like any scene clip. Re-encoded, not copied: a copy can only
    start on a keyframe, seconds away from the chosen moment. Without sound unless `sound` ("Edit từ footage") and
    the sample has some, then as AAC cut at the same frame."""
    short = MIN_SHORT_SIDE
    audio = (
        ["-map", "0:a:0", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2"]
        if sound and sample.has_audio
        else ["-an"]
    )
    _run(
        [
            _tool("ffmpeg"),
            "-v",
            "error",
            "-nostdin",
            "-y",
            "-ss",
            f"{start:.3f}",
            "-max_pixels",
            str(MAX_FRAME_PIXELS),
            "-f",
            sample.demuxer,
            "-i",
            str(path),
            "-t",
            f"{length:.3f}",
            "-map",
            "0:v:0",
            *audio,
            "-vf",
            f"scale=w='if(lte(iw,ih),max(iw,{short}),-2)':h='if(lte(iw,ih),-2,max(ih,{short}))',setsar=1",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-f",
            "mp4",
            str(target),
        ]
    )


def _seconds(value: object) -> float | None:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    return seconds if math.isfinite(seconds) and seconds > 0 else None


def frame_at(path: Path, start: float) -> Image.Image:
    """The frame the render starts the clip on: the same input seeking as the renderer's `-ss` before `-i`."""
    try:
        demuxer, _ = _demuxer(path)
    except (OSError, UploadRejected):
        raise ClipError(f"Không đọc được video {path.name}") from None
    # The first video stream, as the render's `[N:v]` takes; FFmpeg's own choice would be the largest one.
    data = _run(
        [
            _tool("ffmpeg"),
            "-v",
            "error",
            "-nostdin",
            "-ss",
            f"{start:.3f}",
            "-max_pixels",
            str(MAX_FRAME_PIXELS),
            "-f",
            demuxer,
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-c:v",
            "png",
            "-",
        ]
    )
    try:
        with Image.open(io.BytesIO(data)) as image:
            return image.convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ClipError(f"Video {path.name} không có khung hình ở giây {start:g}") from None
