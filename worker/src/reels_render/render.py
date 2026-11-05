import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from . import ffmpeg
from .captions import plan_captions
from .errors import FFmpegError, InputError, MissingImagesError, OutputNotReplacedError
from .graph import CaptionInput, LayerInput, SceneInput, SoundInput, build_ffmpeg_args
from .images import normalize_image
from .layers import layer_corner, render_layer
from .options import DEFAULT_OPTIONS, RenderOptions
from .script import Scene, Script
from .sounds import SOUND_VOLUMES
from .stock import find_stock_images
from .textbox import (
    CAPTION_GAP,
    FRAME_WIDTH,
    SCENE_BOX_BOTTOM,
    SCENE_STYLE,
    TITLE_STYLE,
    TextFitError,
    caption_y,
    empty_box,
    layout_text,
    place_box,
    render_box,
    render_caption,
)
from .timeline import FPS, VOICE_LEAD, build_timeline, fit_seconds

DEFAULT_MUSIC_VOLUME = 0.25
NEW_NAME_ATTEMPTS = 9


def render_video(
    script: Script,
    output: Path,
    music: Path | None = None,
    music_volume: float = DEFAULT_MUSIC_VOLUME,
    on_warning: Callable[[str], None] | None = None,
    options: RenderOptions = DEFAULT_OPTIONS,
    music_start: float = 0.0,
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
    spoken = [voice_seconds(tools.ffprobe, scene) for scene in script.all_scenes]
    timeline = build_timeline([fit_seconds(scene.seconds, voice) for scene, voice in zip(script.all_scenes, spoken)])
    palette, first_palette = options.scene_palette(), options.title_palette()

    with tempfile.TemporaryDirectory(prefix="reels_render_") as work:
        work_dir = Path(work)
        found = find_stock_images(script, work_dir, on_warning=on_warning)
        if found.missing:
            raise MissingImagesError([scene.label for scene in found.missing])
        script = found.script
        inputs, captions, layers, sounds = [], [], [], []
        scene_start = 0
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
                render_box(layout, first_palette if index == 0 else palette).save(box)
                box_x, box_y = place_box(layout.width, layout.height, scene.text_position, is_title=index == 0)
            # Captions sit just above a content scene's text box; the title scene keeps its hook box alone.
            if index > 0 and spoken[index] is not None and scene.voice_text.strip():
                bottom = box_y - CAPTION_GAP if layout is not None else SCENE_BOX_BOTTOM
                box_bottom = box_y + layout.height if layout is not None else SCENE_BOX_BOTTOM
                start = scene_start / FPS + VOICE_LEAD
                for number, cue in enumerate(plan_captions(scene.voice_text, start, spoken[index], options.captions)):
                    path = work_dir / f"caption-{index:02d}-{number:03d}.png"
                    image_caption = render_caption(cue.lines, cue.lit)
                    image_caption.save(path)
                    captions.append(
                        CaptionInput(
                            image=path,
                            x=(FRAME_WIDTH - image_caption.width) // 2,
                            y=caption_y(bottom, box_bottom, image_caption.height),
                            start=cue.start,
                            end=cue.end,
                        )
                    )
            # Each layer from its start into the scene, for its seconds, but never past the scene's end.
            scene_end = (scene_start + timeline.scene_frames[index]) / FPS
            for number, layer in enumerate(scene.layers):
                start = scene_start / FPS + layer.start
                if start >= scene_end:
                    continue
                picture = render_layer(layer)
                path = work_dir / f"layer-{index:02d}-{number:02d}.png"
                picture.save(path)
                left, top = layer_corner(picture.width, picture.height, (layer.x, layer.y))
                layers.append(
                    LayerInput(path, left, top, start, min(start + layer.seconds, scene_end), layer.animation)
                )
            # Each sound effect from its second of the scene, unless that is past the scene's end.
            for sound in scene.sounds:
                if scene_start / FPS + sound.start < scene_end:
                    sounds.append(
                        SoundInput(sound.sound, scene_start / FPS + sound.start, SOUND_VOLUMES[sound.volume].gain)
                    )
            scene_start += timeline.scene_frames[index]
            voice = scene.voice.resolve() if scene.voice is not None else None
            inputs.append(
                SceneInput(
                    image=image,
                    text_box=box,
                    box_x=box_x,
                    box_y=box_y,
                    voice=voice,
                    video_start=video_start,
                    video_speed=scene.video_speed,
                    transition=scene.transition,
                    color=scene.color,
                    music_level=scene.music_level,
                )
            )

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
            options,
            captions,
            layers,
            sounds,
            music_start,
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
            f"Không thay được {output}: file đích đang bị mở ({target_error}). Bản render mới đã lưu tại: {candidate}",
            kept_path=candidate,
        )
    raise OutputNotReplacedError(
        f"Không lưu được video vào {output} ({target_error}) hay các tên .new…: {last_error}. "
        f"Bản render vẫn còn ở file tạm: {temp}",
        kept_path=temp,
    )
