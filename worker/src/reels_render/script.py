import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .errors import InputError
from .markup import MarkupError, Run, parse_scene_text
from .textbox import FRAME_HEIGHT, FRAME_WIDTH

MIN_SCENE_SECONDS = 1
MAX_KEYWORD_LENGTH = 100


@dataclass(frozen=True)
class Scene:
    label: str
    number: int  # 0 for the title scene, 1-based for content scenes
    first_line: str
    lines: list[list[Run]]  # empty: the scene has no text box
    seconds: float
    image: Path | None
    keywords: tuple[str, ...]
    missing_image: str | None = None  # the "image" value whose file does not exist
    voice: Path | None = None  # narration audio, read over the scene
    video: Path | None = None  # a clip shown instead of a photo
    video_start: float = 0.0  # seconds into the clip where the scene starts
    voice_text: str = ""  # what the narration says, for captions
    text_position: tuple[int, int] | None = None  # the text box's centre in the frame; None: the template's place


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
        raise InputError('Kịch bản phải là một object JSON có trường "title" và "scenes"')
    if "title" not in data:
        raise InputError('Kịch bản thiếu trường "title" (cảnh tiêu đề)')
    if "scenes" not in data:
        raise InputError('Kịch bản thiếu trường "scenes" (các cảnh nội dung)')
    scenes = data["scenes"]
    if not isinstance(scenes, list):
        raise InputError('Trường "scenes" phải là một danh sách cảnh')
    if not scenes:
        raise InputError('Kịch bản không có cảnh nội dung nào trong "scenes"')

    title = _parse_scene(data["title"], 0, base_dir)
    return Script(
        title=title,
        scenes=[_parse_scene(item, number, base_dir) for number, item in enumerate(scenes, start=1)],
    )


def _parse_scene(item: object, number: int, base_dir: Path) -> Scene:
    label = "Cảnh tiêu đề" if number == 0 else f"Cảnh {number}"
    if not isinstance(item, dict):
        raise InputError(f'{label}: phải là một object có "text", "seconds"')
    for field in ("text", "seconds"):
        if field not in item:
            raise InputError(f'{label}: thiếu trường "{field}"')

    text, seconds, image, voice = item["text"], item["seconds"], item.get("image", ""), item.get("voice", "")
    if not isinstance(text, str):
        raise InputError(f'{label}: "text" phải là chuỗi')
    # bool is a subclass of int, so it has to be excluded explicitly.
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        raise InputError(f'{label}: "seconds" phải là số, ví dụ 4 hoặc 3.5')
    # JSON numbers are unbounded; absurd values would overflow the frame maths just like Infinity.
    if abs(seconds) > 1e9 or not math.isfinite(seconds):
        raise InputError(f'{label}: "seconds" phải là số hữu hạn')
    if seconds < MIN_SCENE_SECONDS:
        raise InputError(f'{label}: "seconds" phải từ {MIN_SCENE_SECONDS} trở lên (đang là {seconds})')
    if not isinstance(image, str):
        raise InputError(f'{label}: "image" phải là chuỗi đường dẫn ảnh')
    if not isinstance(voice, str):
        raise InputError(f'{label}: "voice" phải là chuỗi đường dẫn file lời đọc')
    voice_text = item.get("voice_text", "")
    if not isinstance(voice_text, str):
        raise InputError(f'{label}: "voice_text" phải là chuỗi')
    if voice.strip() and not (base_dir / voice).is_file():
        raise InputError(f"{label}: không tìm thấy file lời đọc {voice}")
    video, video_start = _parse_video(item, label, base_dir)
    text_position = _parse_position(item.get("text_position"), label)
    if video is not None and image.strip():
        raise InputError(f'{label}: chỉ dùng một trong "image" hoặc "video"')
    keywords = _parse_keywords(item.get("keywords"), label)

    lines = []
    if text.strip():
        try:
            lines = parse_scene_text(text)
        except MarkupError as err:
            raise InputError(f"{label}: {err}") from None

    first_line = next(iter(text.splitlines()), "").replace("*", "").strip()
    # The title's first line ("5 MÓN GIÚP") is not a food name, so it is never searched for.
    if not keywords and number > 0 and first_line:
        keywords = (first_line[:MAX_KEYWORD_LENGTH],)

    image_path, missing_image = None, None
    if image.strip():
        if (base_dir / image).is_file():
            image_path = base_dir / image
        else:
            missing_image = image
    return Scene(
        label=label,
        number=number,
        first_line=first_line,
        lines=lines,
        seconds=float(seconds),
        image=image_path,
        keywords=keywords,
        missing_image=missing_image,
        voice=base_dir / voice if voice.strip() else None,
        video=video,
        video_start=video_start,
        voice_text=voice_text,
        text_position=text_position,
    )


def _parse_position(value: object, label: str) -> tuple[int, int] | None:
    if value is None:
        return None
    if (
        not isinstance(value, list)
        or len(value) != 2
        or not all(isinstance(number, int) and not isinstance(number, bool) for number in value)
        or not (0 <= value[0] <= FRAME_WIDTH and 0 <= value[1] <= FRAME_HEIGHT)
    ):
        raise InputError(f'{label}: "text_position" phải là [x, y] trong khung {FRAME_WIDTH}×{FRAME_HEIGHT}')
    return value[0], value[1]


def _parse_video(item: dict, label: str, base_dir: Path) -> tuple[Path | None, float]:
    video, start = item.get("video", ""), item.get("video_start", 0)
    if not isinstance(video, str):
        raise InputError(f'{label}: "video" phải là chuỗi đường dẫn video')
    if isinstance(start, bool) or not isinstance(start, (int, float)) or not math.isfinite(start) or start < 0:
        raise InputError(f'{label}: "video_start" phải là số giây từ 0 trở lên')
    if not video.strip():
        return None, 0.0
    if not (base_dir / video).is_file():
        raise InputError(f"{label}: không tìm thấy file video {video}")
    return base_dir / video, float(start)


def _parse_keywords(value: object, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise InputError(f'{label}: "keywords" phải là danh sách từ khóa, ví dụ ["cá kho tộ", "món cá"]')
    keywords = []
    for position, keyword in enumerate(value, start=1):
        if not isinstance(keyword, str):
            raise InputError(f'{label}: từ khóa thứ {position} trong "keywords" phải là chuỗi')
        keyword = keyword.strip()
        if not keyword:
            raise InputError(f'{label}: từ khóa thứ {position} trong "keywords" đang trống')
        if len(keyword) > MAX_KEYWORD_LENGTH:
            raise InputError(f'{label}: từ khóa thứ {position} trong "keywords" dài quá {MAX_KEYWORD_LENGTH} ký tự')
        keywords.append(keyword)
    return tuple(keywords)


def write_scene_image(path: Path, number: int, image: str) -> None:
    """Set one scene's "image" in the script file, replacing the file atomically."""
    data = json.loads(path.read_text(encoding="utf-8"))
    target = data["title"] if number == 0 else data["scenes"][number - 1]
    target["image"] = image
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as file:
            file.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise
