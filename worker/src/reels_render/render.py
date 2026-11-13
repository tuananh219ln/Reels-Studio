import os
import tempfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from . import ffmpeg
from .captions import Word, plan_captions, plan_word_captions
from .errors import FFmpegError, InputError, MissingImagesError, OutputNotReplacedError
from .graph import (
    MAX_CLIP_PIXELS,
    CaptionInput,
    InsetInput,
    LayerInput,
    LogoInput,
    SceneInput,
    SoundInput,
    all_cuts,
    build_ffmpeg_args,
    clip_lead,
)
from .images import normalize_image
from .layers import layer_corner, render_layer
from .logo import TEXT_TOP_MIN, corner_placement
from .markup import Run, cased
from .options import DEFAULT_OPTIONS, RenderOptions
from .script import Scene, Script
from .sounds import SOUND_VOLUMES
from .stock import find_stock_images
from .textbox import (
    CAPTION_GAP,
    FRAME_WIDTH,
    SCENE_BOX_BOTTOM,
    TextFitError,
    caption_y,
    empty_box,
    layout_sized,
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
    for index, (scene, lines) in enumerate(zip(script.all_scenes, scene_lines(script, options))):
        try:
            size = options.title_text_size if index == 0 else options.text_size
            layouts.append(layout_sized(lines, size, is_title=index == 0) if lines else None)
        except TextFitError as err:
            raise InputError(f"{scene.label}: {err}") from None
    # A scene with narration is lengthened to fit it; its seconds are the minimum.
    spoken = [voice_seconds(tools.ffprobe, scene) for scene in script.all_scenes]
    timeline = build_timeline([fit_seconds(scene.seconds, voice) for scene, voice in zip(script.all_scenes, spoken)])
    if options.backdrop:
        script = with_backdrop(script)
    palette, first_palette = options.scene_palette(), options.title_palette()
    heard = [clip_sound_heard(tools.ffprobe, scene, on_warning) for scene in script.all_scenes]
    cut = all_cuts(options, [scene.transition for scene in script.all_scenes])

    with tempfile.TemporaryDirectory(prefix="reels_render_") as work:
        work_dir = Path(work)
        loop_seconds = None
        if options.backdrop:
            script = trim_backdrop(tools.ffmpeg, script, work_dir)
            loop_seconds = backdrop_clip_seconds(tools.ffprobe, script.title)
        found = find_stock_images(script, work_dir, on_warning=on_warning)
        if found.missing:
            raise MissingImagesError([scene.label for scene in found.missing])
        script = found.script
        inputs, captions, layers, sounds = [], [], [], []
        scene_start = 0
        for index, (scene, layout) in enumerate(zip(script.all_scenes, layouts)):
            if scene.video is not None:
                image, video_start = scene.video.resolve(), scene.video_start
                if options.backdrop:
                    video_start = backdrop_start(scene, scene_start, loop_seconds)
            elif options.backdrop and index > 0:
                # One photo under every scene: normalized once, for the title scene.
                image, video_start = work_dir / "scene-00.jpg", None
            else:
                image, video_start = work_dir / f"scene-{index:02d}.jpg", None
                normalize_image(scene.image, image, scene.label)
            box = work_dir / f"text-{index:02d}.png"
            if layout is None:
                empty_box().save(box)
                box_x, box_y = 0, 0
            else:
                render_box(layout, first_palette if index == 0 else palette).save(box)
                # Room for the corner badge's row on the content scenes; the title scene has no logo.
                min_top = TEXT_TOP_MIN if script.logo is not None and index > 0 else None
                box_x, box_y = place_box(
                    layout.width, layout.height, scene.text_position, is_title=index == 0, min_top=min_top
                )
            # Captions sit just above a content scene's text box; the title scene keeps its hook box alone. The
            # narration's are timed by estimate; a clip's own sound has each word's real seconds.
            cues = []
            if index > 0 and spoken[index] is not None and scene.voice_text.strip():
                start = scene_start / FPS + VOICE_LEAD
                cues = plan_captions(scene.voice_text, start, spoken[index], options.captions)
            elif index > 0 and heard[index] and scene.words:
                scene_end = (scene_start + timeline.scene_frames[index]) / FPS
                placed = placed_words(scene, scene_start / FPS, scene_end, clip_lead(index, cut))
                cues = plan_word_captions(placed, options.captions)
            if cues:
                bottom = box_y - CAPTION_GAP if layout is not None else SCENE_BOX_BOTTOM
                box_bottom = box_y + layout.height if layout is not None else SCENE_BOX_BOTTOM
                for number, cue in enumerate(cues):
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
            insets = []
            for number, layer in enumerate(scene.layers):
                start = scene_start / FPS + layer.start
                # A photo layer ("Ảnh món") is kept on a slide video but shown only over a backdrop.
                if start >= scene_end or (layer.kind == "photo" and not layer.half and not options.backdrop):
                    continue
                picture = render_layer(layer, options.text_case)
                path = work_dir / f"layer-{index:02d}-{number:02d}.png"
                picture.save(path)
                if layer.half:
                    # Under the scene's text box, in the seconds of the scene's own picture.
                    lead = clip_lead(index, cut)
                    end = min(start + layer.seconds, scene_end) - scene_start / FPS
                    left, top = layer_corner(picture.width, picture.height, (layer.x, layer.y))
                    insets.append(InsetInput(path, top, layer.start + lead, end + lead, left))
                    continue
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
                    video_sound=heard[index],
                    loop=options.backdrop and video_start is not None,
                    blur=scene.video_blur if video_start is not None else (),
                    insets=tuple(insets),
                    motion_span=(
                        (scene_start - timeline.scene_frames[index], timeline.total_frames)
                        if options.backdrop and video_start is None
                        else None
                    ),
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
            logo_input(script.logo, timeline),
        )
        try:
            ffmpeg.run(argv, "FFmpeg render lỗi")
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
    return _publish(temp, output)


def logo_input(badge: Path | None, timeline) -> LogoInput | None:
    """The channel badge, in the corner from the second the title scene ends; None without a logo."""
    if badge is None:
        return None
    return LogoInput(badge, corner_placement(), timeline.scene_frames[0] / FPS)


def scene_lines(script: Script, options: RenderOptions) -> list[list[list[Run]]]:
    """Each scene's text lines (empty without text) in the letter case chosen for it: the title's, or the scenes'."""
    return [
        cased(scene.lines, options.title_text_case if index == 0 else options.text_case)
        for index, scene in enumerate(script.all_scenes)
    ]


def clip_sound_heard(ffprobe: str, scene: Scene, on_warning: Callable[[str], None] | None) -> bool:
    """A scene's clip sound is heard when it is asked for and the clip has a sound track; a clip without one is
    rendered silent, with a warning, rather than failing the render."""
    if not scene.video_sound or scene.video is None:
        return False
    try:
        streams = ffmpeg.probe(ffprobe, scene.video).get("streams", [])
    except FFmpegError:
        streams = []
    if any(stream.get("codec_type") == "audio" for stream in streams):
        return True
    if on_warning is not None:
        on_warning(f"{scene.label}: video không có tiếng, cảnh này không có tiếng gốc")
    return False


def placed_words(scene: Scene, scene_start: float, scene_end: float, lead: float) -> list[Word]:
    """The clip's words in the video's seconds: the clip's picture starts `lead` before the scene, at the clip's
    video_start, and plays at its speed. Words outside the scene are left out and the last is cut at its end."""
    placed = []
    for word in scene.words:
        start = scene_start - lead + (word.start - scene.video_start) / scene.video_speed
        end = scene_start - lead + (word.end - scene.video_start) / scene.video_speed
        if start < scene_start - 0.05 or start >= scene_end:
            continue
        placed.append(Word(word.text, max(start, scene_start), min(end, scene_end)))
    return placed


def with_backdrop(script: Script) -> Script:
    """ "Video xuyên suốt": the title scene's photo or clip under every scene, which keep their own text, narration
    and layers. A scene's own photo stays only in its photo layers; transitions and colours are not used, and the
    backdrop is always silent, so no scene's "Tiếng gốc" or clip words come with it."""
    title = script.title
    if title.image is None and title.video is None:
        raise InputError("Cảnh tiêu đề chưa có ảnh hoặc video để làm nền chung cho cả video")
    title = replace(title, color=None, video_sound=False, words=())
    scenes = [
        replace(
            scene,
            image=title.image,
            missing_image=None,
            video=title.video,
            video_start=title.video_start,
            video_speed=title.video_speed,
            video_blur=title.video_blur,
            transition=None,
            color=None,
            video_sound=False,
            words=(),
        )
        for scene in script.scenes
    ]
    return Script(title=title, scenes=scenes, logo=script.logo)


def trim_backdrop(ffmpeg_path: str, script: Script, work_dir: Path) -> Script:
    """A backdrop clip starting past its first second is cut there first, so it loops back to the title scene's
    start rather than to the clip's own beginning; every scene then reads it from 0."""
    title = script.title
    if title.video is None or title.video_start <= 0:
        return script
    cut = work_dir / "backdrop.mp4"
    ffmpeg.run(
        [
            ffmpeg_path, "-hide_banner", "-nostdin", "-v", "error", "-y",
            "-ss", f"{title.video_start:.3f}", "-max_pixels", str(MAX_CLIP_PIXELS), "-i", str(title.video),
            "-map", "0:v:0", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p",
            str(cut),
        ],
        "FFmpeg không cắt được video nền",
    )  # fmt: skip
    moved = [replace(scene, video=cut, video_start=0.0) for scene in script.all_scenes]
    return Script(title=moved[0], scenes=moved[1:], logo=script.logo)


def backdrop_clip_seconds(ffprobe: str, title: Scene) -> float | None:
    """How long the backdrop clip is, to wrap each scene's start into it; None for a photo or an unreadable length."""
    if title.video is None:
        return None
    try:
        seconds = float(ffmpeg.probe(ffprobe, title.video)["format"]["duration"])
    except (FFmpegError, KeyError, TypeError, ValueError):
        return None
    return seconds if seconds > 0 else None


def backdrop_start(scene: Scene, scene_start: int, loop_seconds: float | None) -> float:
    """Where in the backdrop clip a scene starting at frame `scene_start` picks up, so the scenes join as one
    unbroken clip; past the clip's end it starts over, as the clip loops."""
    start = scene.video_start + scene_start / FPS * scene.video_speed
    if loop_seconds:
        start %= loop_seconds
    return round(start, 3)


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
