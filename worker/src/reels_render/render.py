import os
import tempfile
from pathlib import Path

from . import ffmpeg
from .errors import InputError, OutputNotReplacedError
from .graph import SceneInput, build_ffmpeg_args
from .images import normalize_image
from .script import Script
from .textbox import (
    SCENE_STYLE,
    TITLE_STYLE,
    TextFitError,
    layout_text,
    render_box,
    scene_box_position,
    title_box_position,
)
from .timeline import build_timeline

DEFAULT_MUSIC_VOLUME = 0.25
NEW_NAME_ATTEMPTS = 9


def render_video(
    script: Script,
    output: Path,
    music: Path | None = None,
    music_volume: float = DEFAULT_MUSIC_VOLUME,
) -> Path:
    """Render the script to an MP4 and return the output path.

    Raises a RenderError subclass for every expected failure. Inputs are fully checked before
    FFmpeg runs and the output is only replaced after a successful render.
    """
    output = Path(output)
    tools = ffmpeg.find_tools()
    if output.is_dir():
        raise InputError(f"Đường dẫn đầu ra là một thư mục, cần tên file .mp4: {output}")
    if isinstance(music_volume, bool) or not isinstance(music_volume, (int, float)) or not 0 <= music_volume <= 1:
        raise InputError(f"Âm lượng nhạc phải là số từ 0 đến 1 (đang là {music_volume})")
    if music is not None:
        music = Path(music)
        if not music.is_file():
            raise InputError(f"Không tìm thấy file nhạc: {music}")

    layouts = []
    for index, scene in enumerate(script.all_scenes):
        try:
            layouts.append(layout_text(scene.lines, TITLE_STYLE if index == 0 else SCENE_STYLE))
        except TextFitError as err:
            raise InputError(f"{scene.label}: {err}") from None
    timeline = build_timeline([scene.seconds for scene in script.all_scenes])

    with tempfile.TemporaryDirectory(prefix="reels_render_") as work:
        work_dir = Path(work)
        inputs = []
        for index, (scene, layout) in enumerate(zip(script.all_scenes, layouts)):
            image = work_dir / f"scene-{index:02d}.jpg"
            normalize_image(scene.image, image, scene.label)
            box = work_dir / f"text-{index:02d}.png"
            render_box(layout).save(box)
            place = title_box_position if index == 0 else scene_box_position
            box_x, box_y = place(layout.width, layout.height)
            inputs.append(SceneInput(image=image, text_box=box, box_x=box_x, box_y=box_y))

        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            handle, temp_name = tempfile.mkstemp(prefix=f".{output.stem}.", suffix=".tmp", dir=output.parent)
        except OSError as err:
            raise InputError(f"Không tạo được file đầu ra trong thư mục {output.parent}: {err}") from None
        os.close(handle)
        temp = Path(temp_name)
        argv = build_ffmpeg_args(
            tools.ffmpeg,
            inputs,
            timeline,
            music.resolve() if music is not None else None,
            music_volume,
            temp.resolve(),
        )
        try:
            ffmpeg.run(argv, "FFmpeg render lỗi")
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
    return _publish(temp, output)


def _publish(temp: Path, output: Path) -> Path:
    try:
        os.replace(temp, output)
        return output
    except OSError as err:
        target_error = err

    last_error: OSError = target_error
    for attempt in range(1, NEW_NAME_ATTEMPTS + 1):
        suffix = ".new" if attempt == 1 else f".new-{attempt}"
        candidate = output.with_name(f"{output.stem}{suffix}{output.suffix}")
        try:
            os.replace(temp, candidate)
        except OSError as err:
            last_error = err
            continue
        raise OutputNotReplacedError(
            f"Không thay được {output}: file đích đang bị mở ({target_error}). "
            f"Bản render mới đã lưu tại: {candidate}",
            kept_path=candidate,
        )
    raise OutputNotReplacedError(
        f"Không lưu được video vào {output} ({target_error}) hay các tên .new…: {last_error}. "
        f"Bản render vẫn còn ở file tạm: {temp}",
        kept_path=temp,
    )
