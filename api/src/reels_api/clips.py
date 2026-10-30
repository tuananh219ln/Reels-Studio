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


def _tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise ClipError(f"Máy chủ chưa cài {name}")
    return path


def _run(argv: list[str]) -> bytes:
    try:
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=FFMPEG_SECONDS,
                                check=False)
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


def check_clip(path: Path) -> Clip:
    """Refuse anything that is not a 1–60 s MP4/MOV/WebM clip with a usable video stream."""
    demuxer, extension = _demuxer(path)
    try:
        raw = _run([_tool("ffprobe"), "-v", "error", "-f", demuxer, "-show_streams", "-show_format",
                    "-of", "json", str(path)])
        data = json.loads(raw)
    except (ClipError, json.JSONDecodeError):
        raise UploadRejected(_REFUSED) from None
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
    video = videos[0]
    # The video stream's own length: the container's is the longest stream, often a longer audio track. WebM
    # usually stores no per-stream length, and then the container's is all there is.
    seconds = _seconds(video.get("duration")) or _seconds(data.get("format", {}).get("duration"))
    if seconds is None:
        raise UploadRejected("Không đọc được độ dài video")
    if not MIN_CLIP_SECONDS <= seconds <= MAX_CLIP_SECONDS:
        raise UploadRejected(f"Video phải dài từ {MIN_CLIP_SECONDS} đến {MAX_CLIP_SECONDS} giây "
                             f"(đang là {seconds:.1f} giây)")
    return Clip(extension, seconds)


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
    data = _run([_tool("ffmpeg"), "-v", "error", "-nostdin", "-ss", f"{start:.3f}", "-max_pixels",
                 str(MAX_FRAME_PIXELS), "-f", demuxer, "-i", str(path),
                 "-map", "0:v:0", "-frames:v", "1", "-f", "image2pipe", "-c:v", "png", "-"])
    try:
        with Image.open(io.BytesIO(data)) as image:
            return image.convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ClipError(f"Video {path.name} không có khung hình ở giây {start:g}") from None
