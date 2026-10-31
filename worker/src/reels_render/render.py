import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from . import ffmpeg
from .errors import FFmpegError, InputError, MissingImagesError, OutputNotReplacedError
from .graph import SceneInput, build_ffmpeg_args
from .images import normalize_image
from .script import Scene, Script
from .stock import find_stock_images
from .textbox import (
    SCENE_STYLE,
    TITLE_STYLE,
    TextFitError,
    empty_box,
    layout_text,
    render_box,
    scene_box_position,
    title_box_position,
)
from .timeline import build_timeline, fit_seconds

DEFAULT_MUSIC_VOLUME = 0.25
NEW_NAME_ATTEMPTS = 9


def render_video(
    script: Script,
    output: Path,
    music: Path | None = None,
    music_volume: float = DEFAULT_MUSIC_VOLUME,
    on_warning: Callable[[str], None] | None = None,
) -> Path:
    """Render the script to an MP4 and return the output path.

    Scenes without a usable image get a Pixabay photo; scenes still without one raise
    MissingImagesError. Raises a RenderError subclass for every expected failure. Inputs are fully
    checked before FFmpeg runs and the output is only replaced after a successful render.
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
            style = TITLE_STYLE if index == 0 else SCENE_STYLE
            layouts.append(layout_text(scene.lines, style) if scene.lines else None)
        except TextFitError as err:
            raise InputError(f"{scene.label}: {err}") from None
    # A scene with narration is lengthened to fit it; its seconds are the minimum.
    timeline = build_timeline([
        fit_seconds(scene.seconds, voice_seconds(tools.ffprobe, scene)) for scene in script.all_scenes
    ])

    with tempfile.TemporaryDirectory(prefix="reels_render_") as work:
        work_dir = Path(work)
        found = find_stock_images(script, work_dir, on_warning=on_warning)
        if found.missing:
            raise MissingImagesError([scene.label for scene in found.missing])
        script = found.script
        inputs = []
        for index, (scene, layout) in enumerate(zip(script.all_scenes, layouts)):
            if scene.video is not None:
                image, video_start = scene.video.resolve(), scene.video_start
            else:
                image, video_start = work_dir / f"scene-{index:02d}.jpg", None
                normalize_image(scene.image, image, scene.label)
            box = work_dir / f"text-{index:02d}.png"
            if layout is None:
                empty_box().save(box)
                box_x, box_y = 0, 0
            else:
                render_box(layout).save(box)
                place = title_box_position if index == 0 else scene_box_position
                box_x, box_y = place(layout.width, layout.height)
            voice = scene.voice.resolve() if scene.voice is not None else None
            inputs.append(SceneInput(image=image, text_box=box, box_x=box_x, box_y=box_y, voice=voice,
                                     video_start=video_start))

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


def voice_seconds(ffprobe: str, scene: Scene) -> float | None:
    if scene.voice is None:
        return None
    try:
        seconds = ffmpeg.audio_seconds(ffprobe, scene.voice)
    except FFmpegError:
        seconds = None
    if seconds is None:
        raise InputError(f"{scene.label}: file lời đọc không đọc được: {scene.voice.name}")
    return seconds


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
