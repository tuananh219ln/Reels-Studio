import os
import tempfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from PIL import Image

from . import ffmpeg
from .captions import Word, plan_captions, plan_word_captions
from .cumulative import Step, estimate_words, known_words, plan_cumulative, render_cumulative, voiced_words
from .errors import FFmpegError, InputError, MissingImagesError, OutputNotReplacedError
from .graph import (
    MAX_CLIP_PIXELS,
    CaptionInput,
    FramedInput,
    InsetInput,
    LayerInput,
    LogoInput,
    SceneInput,
    SoundInput,
    all_cuts,
    build_ffmpeg_args,
    clip_lead,
)
from .images import Fitted, fit_image, photo_is_framed
from .layers import card_corner, layer_corner, render_layer
from .logo import TEXT_TOP_MIN, corner_placement
from .markup import Run, cased
from .options import DEFAULT_OPTIONS, RenderOptions
from .script import Scene, Script
from .sounds import SOUND_VOLUMES
from .stock import find_stock_images
from .textbox import (
    CAPTION_GAP,
    FRAME_HEIGHT,
    FRAME_WIDTH,
    SCENE_BOX_BOTTOM,
    TextFitError,
    TextLayout,
    caption_y,
    empty_box,
    layout_sized,
    place_box,
    render_box,
    render_caption,
    with_shade,
)
from .tiers import SCENE_CENTRE, SCENE_CENTRE_TOP, TITLE_CENTRE, parse_scene, parse_title, render_scene, render_title
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

    # A scene with narration is lengthened to fit it; its seconds are the minimum.
    spoken = [voice_seconds(tools.ffprobe, scene) for scene in script.all_scenes]
    heard = [clip_sound_heard(tools.ffprobe, scene, on_warning) for scene in script.all_scenes]
    layouts = []
    tiers: dict[int, Image.Image] = {}
    last_scene = len(script.all_scenes) - 1
    for index, (scene, lines) in enumerate(zip(script.all_scenes, scene_lines(script, options, heard, spoken))):
        if lines and (picture := tier_picture(lines, index, last_scene, options)) is not None:
            # PC Shopee's compact text: a picture of its own, not a text box (tiers.py).
            tiers[index] = picture
            layouts.append(TextLayout(0, [], [], 0, 0, picture.width, picture.height))
            continue
        try:
            size = options.title_text_size if index == 0 else options.text_size
            layouts.append(layout_sized(lines, size, is_title=index == 0) if lines else None)
        except TextFitError as err:
            raise InputError(f"{scene.label}: {err}") from None
    timeline = build_timeline([fit_seconds(scene.seconds, voice) for scene, voice in zip(script.all_scenes, spoken)])
    if options.backdrop:
        script = with_backdrop(script)
    palette, first_palette = options.scene_palette(), options.title_palette()
    cut = all_cuts(options, [scene.transition for scene in script.all_scenes])

    with tempfile.TemporaryDirectory(prefix="reels_render_") as work:
        work_dir = Path(work)
        loop_seconds = None
        if options.backdrop:
            script = trim_backdrop(tools.ffmpeg, script, work_dir)
        else:
            script = trim_loops(tools.ffmpeg, script, work_dir)
            loop_seconds = backdrop_clip_seconds(tools.ffprobe, script.title)
        found = find_stock_images(script, work_dir, on_warning=on_warning)
        if found.missing:
            raise MissingImagesError([scene.label for scene in found.missing])
        script = found.script
        inputs, captions, layers, sounds = [], [], [], []
        scene_start = 0
        # Framed photos (framing.py) all start on one line, below the tallest text box of the video's framed scenes.
        framed_heights = [
            layout.height
            for scene, layout in zip(script.all_scenes, layouts)
            if layout is not None
            and scene.image is not None
            and scene.video is None
            and not (options.backdrop and scene is not script.title)
            and photo_is_framed(scene.image, scene.label, scene.image_fit)
        ]
        reserve = max(framed_heights, default=None)
        for index, (scene, layout) in enumerate(zip(script.all_scenes, layouts)):
            # Room for the corner badge's row on the content scenes; the title scene has no logo.
            min_top = TEXT_TOP_MIN if script.logo is not None and index > 0 else None
            # A framed photo (framing.py): where it puts the text when nobody placed it, and the photo laid over its
            # blurred copy; none for every other picture.
            fitted = Fitted()
            if scene.video is not None:
                image, video_start = scene.video.resolve(), scene.video_start
                if options.backdrop:
                    video_start = backdrop_start(scene, scene_start, loop_seconds)
            elif options.backdrop and index > 0:
                # One photo under every scene: normalized once, for the title scene.
                image, video_start = work_dir / "scene-00.jpg", None
            else:
                image, video_start = work_dir / f"scene-{index:02d}.jpg", None
                fitted = fit_image(
                    scene.image,
                    image,
                    scene.label,
                    scene.image_fit,
                    layout.height if layout is not None else 0,
                    scene.text_position,
                    min_top,
                    scene.image_crop_offset,
                    reserve,
                )
            box = work_dir / f"text-{index:02d}.png"
            if layout is None:
                empty_box().save(box)
                box_x, box_y = 0, 0
                overlay_x, overlay_y = 0, 0
            else:
                if index in tiers:
                    box_image = tiers[index]
                    box_x, box_y = tier_corner(box_image, index, scene.text_position, scene.text_zone)
                else:
                    box_image = render_box(layout, first_palette if index == 0 else palette)
                    box_x, box_y = place_box(
                        layout.width,
                        layout.height,
                        scene.text_position or fitted.text_centre,
                        is_title=index == 0,
                        min_top=min_top,
                    )
                # The shade is part of the picture laid over the scene, so it fades with the text; the captions
                # below still go by the box's own corner.
                if options.text_shade and index > 0:
                    box_image, (overlay_x, overlay_y) = with_shade(box_image, box_x, box_y)
                else:
                    overlay_x, overlay_y = box_x, box_y
                box_image.save(box)
            # Captions sit just above a content scene's text box; the title scene keeps its hook box alone. The
            # narration's are timed by estimate; a clip's own sound has each word's real seconds.
            cues = []
            scene_end = (scene_start + timeline.scene_frames[index]) / FPS
            if options.captions == "cumulative":
                if 0 < index < len(script.all_scenes) - 1:
                    for number, step in enumerate(
                        cumulative_steps(scene, index, scene_start, spoken, heard, cut, scene_end)
                    ):
                        picture, (left, top) = render_cumulative(step.lines, options.pc_style, scene.text_zone)
                        path = work_dir / f"cumulative-{index:02d}-{number:03d}.png"
                        picture.save(path)
                        captions.append(CaptionInput(path, left, top, step.start, step.end))
            elif index > 0 and spoken[index] is not None and scene.voice_text.strip():
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
                if start >= scene_end or (layer.kind == "photo" and not layer.inset and not options.backdrop):
                    continue
                picture = render_layer(layer, options.text_case)
                path = work_dir / f"layer-{index:02d}-{number:02d}.png"
                picture.save(path)
                if layer.inset:
                    # Under the scene's text box, in the seconds of the scene's own picture; a card hangs from its
                    # top edge.
                    lead = clip_lead(index, cut)
                    end = min(start + layer.seconds, scene_end) - scene_start / FPS
                    if layer.card:
                        left, top = card_corner(picture.width, picture.height, layer.y)
                    else:
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
                    gain = SOUND_VOLUMES[sound.volume].gain * 10 ** (sound.gain_db / 20)
                    sounds.append(SoundInput(sound.sound, scene_start / FPS + sound.start, gain))
            scene_start += timeline.scene_frames[index]
            voice = scene.voice.resolve() if scene.voice is not None else None
            inputs.append(
                SceneInput(
                    image=image,
                    text_box=box,
                    box_x=overlay_x,
                    box_y=overlay_y,
                    voice=voice,
                    video_start=video_start,
                    video_speed=scene.video_speed,
                    transition=scene.transition,
                    color=scene.color,
                    music_level=scene.music_level,
                    video_sound=heard[index],
                    loop=video_start is not None and (options.backdrop or scene.video_loop),
                    blur=scene.video_blur if video_start is not None else (),
                    insets=tuple(insets),
                    text_hold=scene.text_hold,
                    framed=FramedInput(fitted.picture, *fitted.box) if fitted.picture is not None else None,
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


def scene_lines(
    script: Script,
    options: RenderOptions,
    heard: list[bool] | None = None,
    spoken: list[float | None] | None = None,
) -> list[list[list[Run]]]:
    """Each scene's text lines (empty without text) in the letter case chosen for it: the title's, or the scenes'."""
    last = len(script.all_scenes) - 1
    heard = heard or [False] * (last + 1)
    spoken = spoken or [None] * (last + 1)
    return [
        # "Cộng dồn" replaces the content scenes' text (not the title's, nor the last scene's call to action), but only
        # where it has words to show: a scene with no narration (or clip words) keeps its own text.
        []
        if options.captions == "cumulative" and 0 < index < last and has_words(scene, index, heard, spoken)
        else cased(scene.lines, options.title_text_case if index == 0 else options.text_case)
        for index, scene in enumerate(script.all_scenes)
    ]


def tier_picture(lines: list[list[Run]], index: int, last: int, options: RenderOptions) -> Image.Image | None:
    """The title in three tiers, or a content scene's text in two (never the last scene's call to action), when the
    video asks for them; None for a scene drawn as a text box."""
    if index == 0 and options.title_layout == "three_tier":
        return render_title(parse_title(lines), options.pc_title_style)
    if 0 < index < last and options.scene_text_layout == "two_tier":
        return render_scene(parse_scene(lines), options.pc_style)
    return None


def tier_corner(
    picture: Image.Image, index: int, position: tuple[int, int] | None, zone: str | None = None
) -> tuple[int, int]:
    """Where a tiers picture goes: centred at its own place (the title 22% down, the scenes' 62–78% zone), or at the
    place a member moved it to, never off the frame."""
    centre_x, centre_y = position or (
        TITLE_CENTRE if index == 0 else SCENE_CENTRE_TOP if zone == "top" else SCENE_CENTRE
    )
    if index == 0:
        centre_x = FRAME_WIDTH // 2  # the title stays centred across, as every title does
    left = min(max(0, centre_x - picture.width // 2), FRAME_WIDTH - picture.width)
    top = min(max(0, centre_y - picture.height // 2), FRAME_HEIGHT - picture.height)
    return left, top


def has_words(scene: Scene, index: int, heard: list[bool], spoken: list[float | None]) -> bool:
    """A scene has words for "Cộng dồn": a narration to read, or a clip's own sound with its words."""
    return (spoken[index] is not None and bool(scene.voice_text.strip())) or (heard[index] and bool(scene.words))


def cumulative_steps(
    scene: Scene,
    index: int,
    scene_start: int,
    spoken: list[float | None],
    heard: list[bool],
    cut: bool,
    scene_end: float,
) -> list[Step]:
    """The "Cộng dồn" steps of a content scene: its narration's words (seconds estimated across the narration), or a
    clip's own words at their real seconds."""
    if spoken[index] is not None and scene.voice_text.strip():
        marked = frozenset(
            word.strip(",.!?:;…").casefold()
            for line in scene.lines
            for run in line
            if run.red
            for word in run.text.split()
        )
        begin = scene_start / FPS + VOICE_LEAD
        words = voiced_words(scene.voice_text, list(scene.voice_words), begin, marked) or estimate_words(
            scene.voice_text, begin, spoken[index], marked
        )
    elif heard[index] and scene.words:
        words = known_words(placed_words(scene, scene_start / FPS, scene_end, clip_lead(index, cut)))
    else:
        return []
    return plan_cumulative(words, scene_end)


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


def trim_loops(ffmpeg_path: str, script: Script, work_dir: Path) -> Script:
    """A looped clip ("Lặp clip") starting past its beginning is cut there first, like the backdrop clip, so it
    starts again from the scene's start time rather than from the clip's own beginning."""
    scenes = list(script.all_scenes)
    for index, scene in enumerate(scenes):
        if scene.video is None or not scene.video_loop or scene.video_start <= 0:
            continue
        cut = work_dir / f"loop-{index:02d}.mp4"
        ffmpeg.run(
            [
                ffmpeg_path, "-hide_banner", "-nostdin", "-v", "error", "-y",
                "-ss", f"{scene.video_start:.3f}", "-max_pixels", str(MAX_CLIP_PIXELS), "-i", str(scene.video),
                "-map", "0:v:0", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p",
                str(cut),
            ],
            f"FFmpeg không cắt được video của {scene.label} để lặp",
        )  # fmt: skip
        scenes[index] = replace(scene, video=cut, video_start=0.0)
    return Script(title=scenes[0], scenes=scenes[1:], logo=script.logo)


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
