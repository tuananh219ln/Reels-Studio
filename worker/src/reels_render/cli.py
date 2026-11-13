import argparse
import itertools
import re
import shutil
import sys
import tempfile
import time
import unicodedata
from dataclasses import replace
from pathlib import Path

from .errors import InputError, MissingImagesError, RenderError
from .images import is_image
from .render import DEFAULT_MUSIC_VOLUME, render_video
from .script import Scene, Script, load_script, write_scene_image
from .stock import find_stock_images


class _Cancelled(Exception):
    pass


def _volume(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"phải là số từ 0 đến 1, nhận được {value!r}") from None


def _warn(message: str) -> None:
    print(f"Cảnh báo: {message}", file=sys.stderr)


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

    try:
        script = load_script(args.script)
        # Downloaded stock images live only for this render and are deleted with the folder.
        with tempfile.TemporaryDirectory(prefix="reels_render_stock_") as stock_dir:
            started = time.perf_counter()
            found = find_stock_images(script, Path(stock_dir), on_warning=_warn)
            search_seconds = time.perf_counter() - started
            script = found.script
            if found.missing:
                if sys.stdin is None or not sys.stdin.isatty():
                    raise MissingImagesError([scene.label for scene in found.missing])
                script = _ask_for_images(args.script, script, found.missing)

            started = time.perf_counter()
            output = render_video(
                script, args.output, music=args.music, music_volume=args.music_volume, on_warning=_warn
            )
            render_seconds = time.perf_counter() - started
    except RenderError as err:
        print(f"Lỗi: {err}", file=sys.stderr)
        return 1
    except _Cancelled:
        print("\nĐã dừng, chưa render. Ảnh đã nhập vẫn được lưu trong kịch bản.", file=sys.stderr)
        return 1
    print(f"Đã render: {output}")
    print(f"Tìm ảnh: {search_seconds:.1f}s ({found.api_calls} lượt gọi API) · Render: {render_seconds:.1f}s")
    return 0


def _ask_for_images(script_path: Path, script: Script, missing: list[Scene]) -> Script:
    images = {scene.number: _ask_for_image(script_path, scene) for scene in missing}

    def resolve(scene: Scene) -> Scene:
        return replace(scene, image=images[scene.number]) if scene.number in images else scene

    return Script(title=resolve(script.title), scenes=[resolve(scene) for scene in script.scenes], logo=script.logo)


def _ask_for_image(script_path: Path, scene: Scene) -> Path:
    while True:
        try:
            raw = input(f"{scene.label} ({scene.first_line}) chưa có ảnh. Kéo thả ảnh vào đây rồi nhấn Enter: ")
        except (EOFError, KeyboardInterrupt):
            raise _Cancelled from None
        source = dropped_path(raw)
        if source is None:
            print("Chưa nhập đường dẫn ảnh, hãy kéo thả một file ảnh vào cửa sổ này.", file=sys.stderr)
        elif not source.is_file():
            print(f"Không thấy file ảnh: {source}", file=sys.stderr)
        elif not is_image(source):
            print(f"File không phải ảnh hoặc ảnh hỏng: {source}", file=sys.stderr)
        else:
            break
    try:
        target = _copy_next_to_script(script_path, scene, source)
        write_scene_image(script_path, scene.number, target.relative_to(script_path.parent).as_posix())
    except OSError as err:
        raise InputError(f"{scene.label}: không lưu được ảnh vào kịch bản ({err})") from None
    return target


def dropped_path(raw: str) -> Path | None:
    """Undo the quoting cmd, PowerShell and Windows Terminal add to a dragged-in path."""
    text = raw.strip()
    if text.startswith("& "):
        text = text[2:].strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        quote, text = text[0], text[1:-1]
        if quote == "'":
            text = text.replace("''", "'")  # PowerShell doubles a quote inside '...'
    return Path(text) if text else None


def _copy_next_to_script(script_path: Path, scene: Scene, source: Path) -> Path:
    folder = script_path.parent / script_path.stem
    folder.mkdir(exist_ok=True)
    base = f"{scene.number:02d}-{_slug(scene.first_line)}"
    for attempt in itertools.count(1):
        target = folder / f"{base}{'' if attempt == 1 else f'-{attempt}'}{source.suffix}"
        try:
            with source.open("rb") as src, target.open("xb") as dst:
                shutil.copyfileobj(src, dst)
        except FileExistsError:
            continue
        return target


def _slug(text: str) -> str:
    text = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    text = "".join(char for char in text if not unicodedata.combining(char)).lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:60].strip("-") or "anh"
