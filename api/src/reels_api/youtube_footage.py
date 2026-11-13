"""Bounded public YouTube search/download; no login, cookies, playlists or user-supplied commands."""

import json
import math
import re
import subprocess
import sys
from pathlib import Path

MAX_SECONDS = 90
SEARCH_SECONDS = 40
DOWNLOAD_SECONDS = 80
MAX_BYTES = 50 * 1024 * 1024
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")


class FootageError(Exception):
    pass


def _run(arguments: list[str], timeout: int) -> str:
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "yt_dlp",
                "--ignore-config",
                "--no-plugin-dirs",
                "--js-runtimes",
                "node",
                "--no-remote-components",
                "--no-warnings",
                "--socket-timeout",
                "8",
                "--retries",
                "0",
                "--extractor-retries",
                "0",
                *arguments,
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise FootageError("Không tìm hoặc tải được clip YouTube trong thời gian cho phép") from None
    if result.returncode or len(result.stdout) > 2 * 1024 * 1024:
        raise FootageError("YouTube không trả được clip công khai; đã chuyển sang nguồn khác")
    return result.stdout


def search(keyword: str) -> list[str]:
    """One query over ten results, at most three short, non-live videos. URLs come only from checked ids."""
    keyword = " ".join(keyword.split())[:100]
    if not keyword:
        return []
    try:
        data = json.loads(
            _run(["--flat-playlist", "--dump-single-json", "--skip-download", f"ytsearch10:{keyword}"], SEARCH_SECONDS)
        )
    except (ValueError, TypeError):
        raise FootageError("Không đọc được kết quả tìm clip YouTube") from None
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        raise FootageError("Không đọc được kết quả tìm clip YouTube")
    urls = []
    for item in data["entries"][:10]:
        if not isinstance(item, dict):
            continue
        video_id, duration = item.get("id"), item.get("duration")
        if (
            not isinstance(video_id, str)
            or not VIDEO_ID.fullmatch(video_id)
            or not isinstance(duration, (int, float))
            or not math.isfinite(duration)
            or not 2 <= duration <= MAX_SECONDS
            or item.get("live_status") in ("is_live", "is_upcoming")
        ):
            continue
        url = f"https://www.youtube.com/watch?v={video_id}"
        if url not in urls:
            urls.append(url)
        if len(urls) == 3:
            break
    return urls


def download(url: str, folder: Path) -> Path:
    """Download a single search result, at most 50 MB/90 s, inside an overall process timeout."""
    if not re.fullmatch(r"https://www\.youtube\.com/watch\?v=[A-Za-z0-9_-]{11}", url):
        raise FootageError("Link clip YouTube không hợp lệ")
    _run(
        [
            "--no-playlist",
            "--no-progress",
            "--no-part",
            "--max-filesize",
            str(MAX_BYTES),
            "--match-filter",
            f"duration <= {MAX_SECONDS} & !is_live",
            "--format",
            "best[ext=mp4][height<=1920]/best[height<=1920]",
            "--output",
            str(folder / "source.%(ext)s"),
            url,
        ],
        DOWNLOAD_SECONDS,
    )
    files = [path for path in folder.glob("source.*") if path.suffix in (".mp4", ".webm", ".mov")]
    if len(files) != 1 or not 0 < files[0].stat().st_size <= MAX_BYTES:
        raise FootageError("Clip YouTube quá lớn hoặc không tải được")
    return files[0]
