import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .errors import FFmpegError, ToolNotFoundError

INSTALL_HINT = (
    "Cài FFmpeg rồi mở lại terminal: Windows `winget install Gyan.FFmpeg`, "
    "Debian/Ubuntu `sudo apt-get install ffmpeg`. Kiểm tra bằng `ffmpeg -version`."
)
STDERR_TAIL_LINES = 20


@dataclass(frozen=True)
class Tools:
    ffmpeg: str
    ffprobe: str


def find_tools() -> Tools:
    found = {name: shutil.which(name) for name in ("ffmpeg", "ffprobe")}
    missing = [name for name, path in found.items() if path is None]
    if missing:
        raise ToolNotFoundError(f"Không tìm thấy {' và '.join(missing)}. {INSTALL_HINT}")
    return Tools(ffmpeg=found["ffmpeg"], ffprobe=found["ffprobe"])


def run(argv: list[str], failure_message: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        tail = "\n".join(result.stderr.strip().splitlines()[-STDERR_TAIL_LINES:])
        raise FFmpegError(f"{failure_message} (mã thoát {result.returncode}):", tail)
    return result


def probe(ffprobe: str, path: Path) -> dict:
    result = run(
        [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        f"ffprobe không đọc được {path}",
    )
    return json.loads(result.stdout)
