import argparse
import sys
import time
from pathlib import Path

from .errors import RenderError
from .render import DEFAULT_MUSIC_VOLUME, render_video
from .script import load_script


def _volume(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"phải là số từ 0 đến 1, nhận được {value!r}") from None


def main(argv: list[str] | None = None) -> int:
    # Piped output on Windows defaults to the ANSI code page, which cannot encode Vietnamese.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(prog="reels_render", description="Render video dọc 9:16 từ kịch bản JSON.")
    parser.add_argument("script", type=Path, help="file kịch bản JSON")
    parser.add_argument("-o", "--output", type=Path, required=True, help="file MP4 đầu ra")
    parser.add_argument("--music", type=Path, help="file nhạc nền (tùy chọn)")
    parser.add_argument(
        "--music-volume", type=_volume, default=DEFAULT_MUSIC_VOLUME, help="âm lượng nhạc từ 0 đến 1 (mặc định 0.25)"
    )
    args = parser.parse_args(argv)

    started = time.perf_counter()
    try:
        script = load_script(args.script)
        output = render_video(script, args.output, music=args.music, music_volume=args.music_volume)
    except RenderError as err:
        print(f"Lỗi: {err}", file=sys.stderr)
        return 1
    print(f"Đã render: {output}")
    print(f"Thời gian render: {time.perf_counter() - started:.1f}s")
    return 0
