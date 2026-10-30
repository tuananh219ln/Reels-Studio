import io
import json
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import pytest
from PIL import Image

from reels_render import env, stock

# Captured before the autouse fixture below hides them, for the opt-in live smoke test.
REAL_FETCH = stock.fetch
REAL_DEFAULT_CACHE_DIR = stock.default_cache_dir
REAL_DOTENV_PATH = env.DOTENV_PATH
REAL_PIXABAY_KEY = env.read_env("PIXABAY_API_KEY")
PIXABAY_TEST_KEY = "SECRET-KEY-123"

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe không có trên PATH")


@pytest.fixture(autouse=True)
def offline(tmp_path, monkeypatch):
    """No test reads the developer's key, touches the shared cache or reaches the network by accident."""
    monkeypatch.delenv("PIXABAY_API_KEY", raising=False)
    monkeypatch.setattr(env, "DOTENV_PATH", tmp_path / "no.env")
    monkeypatch.setattr(stock, "default_cache_dir", lambda: tmp_path / "search-cache")

    def no_network(url, timeout, max_bytes):
        pytest.fail(f"unexpected network request: {url}")

    monkeypatch.setattr(stock, "fetch", no_network)


def jpeg_bytes(size: tuple[int, int] = (64, 48), color: tuple[int, int, int] = (200, 120, 60)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, "JPEG")
    return buffer.getvalue()


class FakePixabay:
    """Stands in for stock.fetch. `results[keyword]` is a list of image URLs, an exception, or a
    tuple of per-call outcomes; `files[url]` is bytes or an exception (default: a valid JPEG)."""

    def __init__(self):
        self.results: dict[str, object] = {}
        self.files: dict[str, object] = {}
        self.searches: list[dict[str, str]] = []
        self.downloads: list[str] = []
        self.limits: list[tuple[str, float, int]] = []  # (search|download, timeout, max_bytes)

    def __call__(self, url, timeout, max_bytes):
        self.limits.append(("search" if url.startswith(stock.API_URL) else "download", timeout, max_bytes))
        if url.startswith(stock.API_URL):
            query = dict(parse_qsl(urlsplit(url).query))
            self.searches.append(query)
            outcome = self.results.get(query["q"], [])
            if isinstance(outcome, tuple):
                outcome, rest = outcome[0], outcome[1:]
                self.results[query["q"]] = rest if rest else outcome
            if isinstance(outcome, Exception):
                raise outcome
            hits = [{"webformatURL": f"{item}?w=640", "largeImageURL": item} for item in outcome]
            return json.dumps({"total": len(hits), "hits": hits}).encode()
        self.downloads.append(url)
        outcome = self.files.get(url) or jpeg_bytes()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    @property
    def keywords(self) -> list[str]:
        return [query["q"] for query in self.searches]


@pytest.fixture
def pixabay(monkeypatch):
    """Fake Pixabay behind a configured key."""
    fake = FakePixabay()
    monkeypatch.setattr(stock, "fetch", fake)
    monkeypatch.setenv("PIXABAY_API_KEY", PIXABAY_TEST_KEY)
    return fake


def urls(prefix: str, count: int) -> list[str]:
    return [f"https://cdn.pixabay.com/{prefix}-{n}.jpg" for n in range(1, count + 1)]


def make_image(path: Path, size: tuple[int, int], color: tuple[int, int, int] = (190, 215, 240)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


def write_script(directory: Path, data: object) -> Path:
    path = directory / "script.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def scene(text: str = "Cá nhỏ\nGiàu *canxi*", seconds: float = 1, image: str = "a.jpg", **extra) -> dict:
    return {"text": text, "seconds": seconds, "image": image, **extra}


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


def make_clip(path: Path, seconds: float, size: str = "1280x720", rate: int = 25) -> Path:
    """A test-pattern clip with a loud tone, so a test can tell whether the clip's own sound leaks into the MP4."""
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate={rate}:duration={seconds}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", str(path)],
        check=True,
    )
    return path
