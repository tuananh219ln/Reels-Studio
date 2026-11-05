"""Pure builders for the single FFmpeg filter graph and its argv.

Files are only ever passed with `-i` and referenced by stream label, so no path (with spaces,
drive colons or backslashes) is ever escaped into the graph.
"""

from dataclasses import dataclass
from pathlib import Path

from .effects import COLOR_PRESETS, SCENE_TRANSITIONS
from .options import DEFAULT_OPTIONS, RenderOptions
from .textbox import FRAME_HEIGHT, FRAME_WIDTH
from .timeline import FPS, VOICE_LEAD, XFADE_FRAMES, Timeline

ZOOM_END = 1.12
# Pre-scaling above the frame size keeps zoompan's integer crop steps sub-pixel in the output.
PRESCALE = 2
AUDIO_RATE = 48000
# A clip's headers can lie about its size (H.264 may switch mid-stream); the decoder refuses larger frames.
MAX_CLIP_PIXELS = 4096 * 2304
MUSIC_FADE_SECONDS = 1.5
# Ducking: the music drops to about a quarter while narration plays and comes back in 0.4 s.
DUCKING = "sidechaincompress=threshold=0.02:ratio=8:attack=20:release=400"


@dataclass(frozen=True)
class SceneInput:
    image: Path  # the photo, or the clip when video_start is set
    text_box: Path
    box_x: int
    box_y: int
    voice: Path | None = None
    video_start: float | None = None
    video_speed: float = 1.0
    transition: str | None = None  # into this scene (effects.SCENE_TRANSITIONS); None: the video's
    color: str | None = None  # effects.COLOR_PRESETS; None: as shot


@dataclass(frozen=True)
class CaptionInput:
    """One caption image shown from `start` to `end` seconds of the video."""

    image: Path
    x: int
    y: int
    start: float
    end: float


def zoom_expression(clip_frames: int, motion: str = "zoom_in", zoom_end: float = ZOOM_END) -> str:
    """zoom_in: linear from 1.00 on the clip's first frame to zoom_end on its last; zoom_out the reverse; pan
    holds zoom_end so there is room to travel sideways; static stays at 1.00."""
    if motion == "zoom_out":
        return f"{zoom_end:.4f}-{zoom_end - 1:.4f}*on/{clip_frames - 1}"
    if motion == "pan":
        return f"{zoom_end:.4f}"
    if motion == "static":
        return "1"
    return f"1+{zoom_end - 1:.4f}*on/{clip_frames - 1}"


def _pan_x(clip_frames: int, motion: str) -> str:
    """Centred, except a pan that travels from the left edge of the zoomed frame to the right."""
    if motion == "pan":
        return f"(iw-iw/zoom)*on/{clip_frames - 1}"
    return "iw/2-(iw/zoom/2)"


def _seconds(frames: int) -> str:
    return f"{frames / FPS:.6f}"


def _graded(color: str | None) -> str:
    """The scene's colour preset as a filter step, graded on the picture alone (the text box goes on after)."""
    return f"{COLOR_PRESETS[color].filter}," if color else ""


def _photo_chain(
    source: int, frames: int, label: str, options: RenderOptions = DEFAULT_OPTIONS, color: str | None = None
) -> str:
    scale_w, scale_h = FRAME_WIDTH * PRESCALE, FRAME_HEIGHT * PRESCALE
    zoom = zoom_expression(frames, options.motion, options.zoom_end)
    return (
        f"[{source}:v]scale={scale_w}:{scale_h}:force_original_aspect_ratio=increase:out_range=tv,"
        f"crop={scale_w}:{scale_h},format=yuv420p,setsar=1,"
        f"zoompan=z='{zoom}':x='{_pan_x(frames, options.motion)}':y='ih/2-(ih/zoom/2)'"
        f":d={frames}:s={FRAME_WIDTH}x{FRAME_HEIGHT}:fps={FPS},"
        f"{_graded(color)}format=yuv420p[{label}]"
    )


def _clip_chain(source: int, frames: int, label: str, speed: float = 1.0, color: str | None = None) -> str:
    """A clip already moves, so it gets no zoom. `setpts` first plays it at its speed, then `fps` turns it, like
    phone footage with a variable frame rate, into constant 30 fps; `tpad` holds the last frame when the clip ends
    before the scene, and `trim` cuts it to the timeline's exact frame count so the crossfade offsets stay
    frame-exact. No `setpts` may follow `fps`: FFmpeg 7.1's setpts marks the frame rate unknown, and xfade then
    refuses to join the clip to a 30 fps scene. None is needed, since the clip already starts at 0."""
    timing = "PTS-STARTPTS" if speed == 1 else f"(PTS-STARTPTS)/{speed:g}"
    return (
        f"[{source}:v]setpts={timing},fps={FPS},"
        f"scale={FRAME_WIDTH}:{FRAME_HEIGHT}:force_original_aspect_ratio=increase:out_range=tv,"
        f"crop={FRAME_WIDTH}:{FRAME_HEIGHT},format=yuv420p,setsar=1,{_graded(color)}"
        f"tpad=stop_mode=clone:stop_duration={_seconds(frames)},trim=end_frame={frames}"
        f"[{label}]"
    )


def _boundary_transitions(count: int, options: RenderOptions, transitions: list[str | None]) -> list[str]:
    """The transition at each boundary, into scenes 1…count-1: the scene's own, else the video's."""
    return [transitions[index] or options.transition for index in range(1, count)]


def build_filter_graph(
    box_positions: list[tuple[int, int]],
    timeline: Timeline,
    music_volume: float | None,
    voices: list[bool] | None = None,
    clips: list[bool] | None = None,
    options: RenderOptions = DEFAULT_OPTIONS,
    captions: list[CaptionInput] | None = None,
    speeds: list[float] | None = None,
    transitions: list[str | None] | None = None,
    colors: list[str | None] | None = None,
) -> str:
    """Inputs are ordered image 0, text box 0, image 1, text box 1, …, then the music if any, then the
    narration of each scene that has one (`voices` says which do), then the caption images. A scene that `clips`
    marks has a video clip in its image's place, played at its `speeds` entry; the clip's own sound is never used.
    A scene's `transitions` entry replaces the video's transition into it, and its `colors` entry grades it."""
    count = len(box_positions)
    clips = clips or [False] * count
    speeds = speeds or [1.0] * count
    colors = colors or [None] * count
    boundaries = _boundary_transitions(count, options, transitions or [None] * count)
    captions = captions or []
    # When every boundary is a hard cut the scenes join end to end, so each clip is exactly its scene; otherwise
    # every clip overlaps half a transition on each side of a boundary, and a cut among them is a one-frame fade at
    # the same offset, so the total length and every narration stay where the timeline put them.
    cut = all(name == "cut" for name in boundaries)
    lengths = timeline.scene_frames if cut else timeline.clip_frames
    chains: list[str] = []
    for index, ((box_x, box_y), frames) in enumerate(zip(box_positions, lengths)):
        image, box = 2 * index, 2 * index + 1
        if clips[index]:
            chains.append(_clip_chain(image, frames, f"bg{index}", speeds[index], colors[index]))
        else:
            chains.append(_photo_chain(image, frames, f"bg{index}", options, colors[index]))
        chains.append(f"[bg{index}][{box}:v]overlay=x={box_x}:y={box_y},format=yuv420p,setsar=1[v{index}]")

    if cut:
        joined = "".join(f"[v{index}]" for index in range(count))
        chains.append(f"{joined}concat=n={count}:v=1:a=0[x0]")
        previous = "x0"
    else:
        previous = "v0"
        for index, (offset, name) in enumerate(zip(timeline.xfade_offsets, boundaries), start=1):
            label = f"x{index}"
            xfade = SCENE_TRANSITIONS[name].xfade
            chains.append(
                f"[{previous}][v{index}]xfade=transition={xfade or 'fade'}"
                f":duration={_seconds(XFADE_FRAMES if xfade else 1)}:offset={_seconds(offset)}[{label}]"
            )
            previous = label
    first_caption = 2 * len(box_positions) + (music_volume is not None) + sum(voices or [])
    for index, caption in enumerate(captions):
        label = f"c{index}"
        chains.append(
            f"[{previous}][{first_caption + index}:v]overlay=x={caption.x}:y={caption.y}"
            f":enable='between(t,{caption.start:.3f},{caption.end:.3f})'[{label}]"
        )
        previous = label
    chains.append(f"[{previous}]format=yuv420p[vout]")

    total = _seconds(timeline.total_frames)
    bed = "aout" if not any(voices or []) else "bed"
    if music_volume is None:
        # A silent bed instead of no audio stream, so the narration always has something to be mixed onto.
        chains.append(f"anullsrc=r={AUDIO_RATE}:cl=stereo,atrim=duration={total}[{bed}]")
    else:
        music = 2 * len(box_positions)
        fade_start = max(0.0, timeline.total_seconds - MUSIC_FADE_SECONDS)
        chains.append(
            f"[{music}:a]aresample={AUDIO_RATE},aformat=channel_layouts=stereo,"
            f"volume={music_volume:.4f},atrim=duration={total},"
            f"afade=t=out:st={fade_start:.6f}:d={MUSIC_FADE_SECONDS}[{bed}]"
        )
    if bed == "bed":
        chains += _voice_chains(voices, timeline, 2 * len(box_positions) + (music_volume is not None))
        voice = "voice"
        if options.voice_volume != 1:
            chains.append(f"[voice]volume={options.voice_volume:.4f}[voicelevel]")
            voice = "voicelevel"
        if options.ducking and music_volume is not None:
            chains.append(f"[{voice}]asplit=2[voicemix][voicekey]")
            chains.append(f"[bed][voicekey]{DUCKING}[ducked]")
            bed, voice = "ducked", "voicemix"
        # amerge + pan adds the two tracks at full level; amix would halve both (FFmpeg 4.3 has no normalize=0).
        chains.append(f"[{bed}][{voice}]amerge=inputs=2,pan=stereo|c0=c0+c2|c1=c1+c3[aout]")
    return ";".join(chains)


def _voice_chains(voices: list[bool], timeline: Timeline, first_input: int) -> list[str]:
    """One narration track as long as the video: each scene's segment holds its narration, delayed past the
    crossfade and padded with silence, or only silence. Segment lengths are exact sample counts of the
    scene's frames, so the narration stays on its scene however long the video is."""
    chains, labels, voice_input = [], [], first_input
    for index, (frames, has_voice) in enumerate(zip(timeline.scene_frames, voices)):
        samples = frames * AUDIO_RATE // FPS
        if has_voice:
            delay = round(VOICE_LEAD * 1000)
            chains.append(
                f"[{voice_input}:a]aresample={AUDIO_RATE},aformat=channel_layouts=stereo,"
                f"adelay={delay}|{delay},apad,atrim=end_sample={samples}[vo{index}]"
            )
            voice_input += 1
        else:
            chains.append(f"anullsrc=r={AUDIO_RATE}:cl=stereo,atrim=end_sample={samples}[vo{index}]")
        labels.append(f"[vo{index}]")
    chains.append(f"{''.join(labels)}concat=n={len(labels)}:v=0:a=1[voice]")
    return chains


def build_ffmpeg_args(
    ffmpeg: str,
    scenes: list[SceneInput],
    timeline: Timeline,
    music: Path | None,
    music_volume: float,
    output: Path,
    options: RenderOptions = DEFAULT_OPTIONS,
    captions: list[CaptionInput] | None = None,
) -> list[str]:
    argv = [ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-y"]
    for scene in scenes:
        if scene.video_start is not None:
            # Input seeking: the clip's first decoded frame is the one at the start time, as in the preview.
            argv += ["-ss", f"{scene.video_start:.3f}", "-max_pixels", str(MAX_CLIP_PIXELS)]
        argv += ["-i", str(scene.image), "-i", str(scene.text_box)]
    if music is not None:
        argv += ["-stream_loop", "-1", "-i", str(music)]
    for scene in scenes:
        if scene.voice is not None:
            argv += ["-i", str(scene.voice)]
    for caption in captions or []:
        argv += ["-i", str(caption.image)]
    graph = build_filter_graph(
        [(scene.box_x, scene.box_y) for scene in scenes],
        timeline,
        music_volume if music is not None else None,
        [scene.voice is not None for scene in scenes],
        [scene.video_start is not None for scene in scenes],
        options,
        captions,
        [scene.video_speed for scene in scenes],
        [scene.transition for scene in scenes],
        [scene.color for scene in scenes],
    )
    argv += [
        "-filter_complex",
        graph,
        "-map",
        "[vout]",
        "-map",
        "[aout]",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(FPS),
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-ar",
        str(AUDIO_RATE),
        "-ac",
        "2",
        "-t",
        _seconds(timeline.total_frames),
        "-movflags",
        "+faststart",
        "-f",
        "mp4",
        str(output),
    ]
    return argv
