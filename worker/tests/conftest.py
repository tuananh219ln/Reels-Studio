import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe không có trên PATH")


def make_image(path: Path, size: tuple[int, int], color: tuple[int, int, int] = (190, 215, 240)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


def write_script(directory: Path, data: object) -> Path:
    path = directory / "script.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def scene(text: str = "Cá nhỏ\nGiàu *canxi*", seconds: float = 1, image: str = "a.jpg") -> dict:
    return {"text": text, "seconds": seconds, "image": image}


def script_data(scene_count: int = 1, **title) -> dict:
    return {
        "title": scene(**({"text": "5 món\n*xương chắc khỏe*"} | title)),
        "scenes": [scene() for _ in range(scene_count)],
    }


def extract_frame(video: Path, seconds: float, target: Path) -> Image.Image:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", f"{seconds:.3f}", "-i", str(video), "-frames:v", "1", str(target)],
        check=True,
    )
    return Image.open(target).convert("RGB")


def mean_volume(media: Path, start: float, duration: float) -> float:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(media),
         "-vn", "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, encoding="utf-8", errors="replace", check=True,
    )
    return float(re.search(r"mean_volume: (-?[\d.]+|-inf) dB", result.stderr).group(1))


def make_tone(path: Path, seconds: float) -> Path:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
         "-ac", "2", "-c:a", "pcm_s16le", str(path)],
        check=True,
    )
    return path
