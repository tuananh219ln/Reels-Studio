import json
import math
from dataclasses import dataclass
from pathlib import Path

from .errors import InputError
from .markup import MarkupError, Run, parse_scene_text

MIN_SCENE_SECONDS = 1


@dataclass(frozen=True)
class Scene:
    label: str
    lines: list[list[Run]]
    seconds: float
    image: Path


@dataclass(frozen=True)
class Script:
    title: Scene
    scenes: list[Scene]

    @property
    def all_scenes(self) -> list[Scene]:
        return [self.title, *self.scenes]


def load_script(path: Path) -> Script:
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise InputError(f"Không tìm thấy file kịch bản: {path}") from None
    except UnicodeDecodeError:
        raise InputError(f"{path}: file kịch bản không phải UTF-8") from None
    except OSError as err:
        raise InputError(f"Không đọc được file kịch bản {path}: {err}") from None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as err:
        raise InputError(f"{path}: JSON lỗi cú pháp ở dòng {err.lineno}, cột {err.colno}: {err.msg}") from None
    return parse_script(data, base_dir=path.parent)


def parse_script(data: object, base_dir: Path) -> Script:
    if not isinstance(data, dict):
        raise InputError("Kịch bản phải là một object JSON có trường \"title\" và \"scenes\"")
    if "title" not in data:
        raise InputError("Kịch bản thiếu trường \"title\" (cảnh tiêu đề)")
    if "scenes" not in data:
        raise InputError("Kịch bản thiếu trường \"scenes\" (các cảnh nội dung)")
    scenes = data["scenes"]
    if not isinstance(scenes, list):
        raise InputError("Trường \"scenes\" phải là một danh sách cảnh")
    if not scenes:
        raise InputError("Kịch bản không có cảnh nội dung nào trong \"scenes\"")

    title = _parse_scene(data["title"], "Cảnh tiêu đề", base_dir)
    return Script(
        title=title,
        scenes=[_parse_scene(item, f"Cảnh {number}", base_dir) for number, item in enumerate(scenes, start=1)],
    )


def _parse_scene(item: object, label: str, base_dir: Path) -> Scene:
    if not isinstance(item, dict):
        raise InputError(f"{label}: phải là một object có \"text\", \"seconds\", \"image\"")
    for field in ("text", "seconds", "image"):
        if field not in item:
            raise InputError(f"{label}: thiếu trường \"{field}\"")

    text, seconds, image = item["text"], item["seconds"], item["image"]
    if not isinstance(text, str):
        raise InputError(f"{label}: \"text\" phải là chuỗi")
    # bool is a subclass of int, so it has to be excluded explicitly.
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        raise InputError(f"{label}: \"seconds\" phải là số, ví dụ 4 hoặc 3.5")
    # JSON numbers are unbounded; absurd values would overflow the frame maths just like Infinity.
    if abs(seconds) > 1e9 or not math.isfinite(seconds):
        raise InputError(f"{label}: \"seconds\" phải là số hữu hạn")
    if seconds < MIN_SCENE_SECONDS:
        raise InputError(f"{label}: \"seconds\" phải từ {MIN_SCENE_SECONDS} trở lên (đang là {seconds})")
    if not isinstance(image, str):
        raise InputError(f"{label}: \"image\" phải là chuỗi đường dẫn ảnh")
    if not image.strip():
        raise InputError(f"{label}: thiếu ảnh (\"image\" đang trống)")

    try:
        lines = parse_scene_text(text)
    except MarkupError as err:
        raise InputError(f"{label}: {err}") from None

    image_path = base_dir / image
    if not image_path.is_file():
        raise InputError(f"{label}: không tìm thấy file ảnh {image_path}")
    return Scene(label=label, lines=lines, seconds=float(seconds), image=image_path)
