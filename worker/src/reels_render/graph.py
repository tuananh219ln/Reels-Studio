"""Pure builders for the single FFmpeg filter graph and its argv.

Files are only ever passed with `-i` and referenced by stream label, so no path (with spaces,
drive colons or backslashes) is ever escaped into the graph.
"""

from dataclasses import dataclass
from pathlib import Path

from .effects import COLOR_PRESETS, SCENE_TRANSITIONS
from .layers import ANIMATION_SECONDS, SLIDE_UP_PX
from .options import DEFAULT_OPTIONS, RenderOptions
from .sounds import MUSIC_LEVELS, SOUNDS
from .textbox import FRAME_HEIGHT, FRAME_WIDTH
from .timeline import FPS, HALF_XFADE, VOICE_LEAD, XFADE_FRAMES, Timeline

ZOOM_END = 1.12
# Pre-scaling above the frame size keeps zoompan's integer crop steps sub-pixel in the output.
PRESCALE = 2
AUDIO_RATE = 48000
# A clip's headers can lie about its size (H.264 may switch mid-stream); the decoder refuses larger frames.
MAX_CLIP_PIXELS = 4096 * 2304
MUSIC_FADE_SECONDS = 1.5
# "Video xuyên suốt": each text box fades in and out over this, as the backdrop never changes.
TEXT_FADE_SECONDS = 0.3
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
    music_level: str | None = None  # sounds.MUSIC_LEVELS; None: the video's level
    video_sound: bool = False  # the clip's own sound is heard (the clip must have an audio stream)
    loop: bool = False  # the clip starts again from its beginning when it ends (a backdrop clip)
    # A backdrop photo's motion runs once over the whole video: (frames before this scene, frames of the video).
    motion_span: tuple[int, int] | None = None


@dataclass(frozen=True)
class CaptionInput:
    """One caption image shown from `start` to `end` seconds of the video."""

    image: Path
    x: int
    y: int
    start: float
    end: float


@dataclass(frozen=True)
class SoundInput:
    """One sound effect (sounds.SOUNDS) heard from `start` seconds of the video, at `gain`."""

    sound: str
    start: float
    gain: float = 1.0


@dataclass(frozen=True)
class LayerInput:
    """One layer's picture laid at (x, y) from `start` to `end` seconds of the video, coming in by `animation`."""

    image: Path | None
    x: int
    y: int
    start: float
    end: float
    animation: str = "fade"


def _layer_chains(layers: list[LayerInput], first_input: int, previous: str) -> tuple[list[str], str]:
    """Each layer over the video in order, after the captions. Its picture is looped for as long as it is shown, so
    an entrance can fade its alpha in; a slide moves the overlay's position over the same ANIMATION_SECONDS."""
    chains = []
    for index, layer in enumerate(layers):
        start, end, length = f"{layer.start:.3f}", f"{layer.end:.3f}", f"{ANIMATION_SECONDS:.3f}"
        fade = f",fade=t=in:st={start}:d={length}:alpha=1" if layer.animation != "none" else ""
        chains.append(f"[{first_input + index}:v]format=rgba{fade}[l{index}]")
        progress = f"min(1,max(0,(t-{start})/{length}))"
        x, y = str(layer.x), str(layer.y)
        if layer.animation == "slide_left":
            x = f"'{layer.x}-({layer.x}+w)*(1-{progress})'"
        elif layer.animation == "slide_up":
            y = f"'{layer.y}+{SLIDE_UP_PX}*(1-{progress})'"
        label = f"o{index}"
        chains.append(f"[{previous}][l{index}]overlay=x={x}:y={y}:enable='between(t,{start},{end})'[{label}]")
        previous = label
    return chains, previous


def _progress(clip_frames: int, span: tuple[int, int] | None) -> str:
    """How far the motion has travelled at output frame `on`: over the clip, or from `span`'s first frame over its
    whole length, so a backdrop photo split into scenes moves as one."""
    if span is None:
        return f"on/{clip_frames - 1}"
    offset, total = span
    return f"(on+{offset})/{max(total - 1, 1)}"


def zoom_expression(
    clip_frames: int, motion: str = "zoom_in", zoom_end: float = ZOOM_END, span: tuple[int, int] | None = None
) -> str:
    """zoom_in: linear from 1.00 on the clip's first frame to zoom_end on its last; zoom_out the reverse; pan
    holds zoom_end so there is room to travel sideways; static stays at 1.00. With `span`, over the whole video."""
    progress = _progress(clip_frames, span)
    if motion == "zoom_out":
        return f"{zoom_end:.4f}-{zoom_end - 1:.4f}*{progress}"
    if motion == "pan":
        return f"{zoom_end:.4f}"
    if motion == "static":
        return "1"
    return f"1+{zoom_end - 1:.4f}*{progress}"


def _pan_x(clip_frames: int, motion: str, span: tuple[int, int] | None = None) -> str:
    """Centred, except a pan that travels from the left edge of the zoomed frame to the right."""
    if motion == "pan":
        return f"(iw-iw/zoom)*{_progress(clip_frames, span)}"
    return "iw/2-(iw/zoom/2)"


def _seconds(frames: int) -> str:
    return f"{frames / FPS:.6f}"


def _graded(color: str | None) -> str:
    """The scene's colour preset as a filter step, graded on the picture alone (the text box goes on after)."""
    return f"{COLOR_PRESETS[color].filter}," if color else ""


def _photo_chain(
    source: int,
    frames: int,
    label: str,
    options: RenderOptions = DEFAULT_OPTIONS,
    color: str | None = None,
    span: tuple[int, int] | None = None,
) -> str:
    scale_w, scale_h = FRAME_WIDTH * PRESCALE, FRAME_HEIGHT * PRESCALE
    zoom = zoom_expression(frames, options.motion, options.zoom_end, span)
    return (
        f"[{source}:v]scale={scale_w}:{scale_h}:force_original_aspect_ratio=increase:out_range=tv,"
        f"crop={scale_w}:{scale_h},format=yuv420p,setsar=1,"
        f"zoompan=z='{zoom}':x='{_pan_x(frames, options.motion, span)}':y='ih/2-(ih/zoom/2)'"
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


def all_cuts(options: RenderOptions, transitions: list[str | None]) -> bool:
    """Whether every boundary is a hard cut, so the scenes join end to end and no clip plays before its scene; a
    backdrop video ("Video xuyên suốt") is always joined so."""
    return options.backdrop or all(
        name == "cut" for name in _boundary_transitions(len(transitions), options, transitions)
    )


def clip_lead(index: int, cut: bool) -> float:
    """Seconds a scene's clip plays before the scene starts: half a crossfade, unless it is first or all are cuts."""
    return 0.0 if index == 0 or cut else HALF_XFADE / FPS


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
    layers: list[LayerInput] | None = None,
    sounds: list[SoundInput] | None = None,
    music_levels: list[str | None] | None = None,
    clip_sounds: list[bool] | None = None,
    spans: list[tuple[int, int] | None] | None = None,
) -> str:
    """Inputs are ordered image 0, text box 0, image 1, text box 1, …, then the music if any, then the
    narration of each scene that has one (`voices` says which do), then the caption images. A scene that `clips`
    marks has a video clip in its image's place, played at its `speeds` entry; the clip's own sound is heard only
    when `clip_sounds` marks the scene, on the narration's track, so the music ducks under it as under a voice.
    A scene's `transitions` entry replaces the video's transition into it, and its `colors` entry grades it.
    The `layers` pictures come last among the inputs and go on top, after the captions. The `sounds` are made in
    the graph itself and mixed over the music and narration; a scene's `music_levels` entry sets the music's level
    for its seconds. With `options.backdrop` ("Video xuyên suốt") the scenes join by hard cuts whatever their
    transitions, a `spans` entry runs a photo's motion over the whole video, and each text box (looped for its
    scene's seconds) fades in, except the title's, which is the cover, and out, except the last scene's."""
    count = len(box_positions)
    clips = clips or [False] * count
    speeds = speeds or [1.0] * count
    colors = colors or [None] * count
    boundaries = _boundary_transitions(count, options, transitions or [None] * count)
    captions = captions or []
    # When every boundary is a hard cut the scenes join end to end, so each clip is exactly its scene; otherwise
    # every clip overlaps half a transition on each side of a boundary, and a cut among them is a one-frame fade at
    # the same offset, so the total length and every narration stay where the timeline put them.
    cut = options.backdrop or all(name == "cut" for name in boundaries)
    lengths = timeline.scene_frames if cut else timeline.clip_frames
    spans = spans or [None] * count
    chains: list[str] = []
    for index, ((box_x, box_y), frames) in enumerate(zip(box_positions, lengths)):
        image, box = 2 * index, 2 * index + 1
        if clips[index]:
            chains.append(_clip_chain(image, frames, f"bg{index}", speeds[index], colors[index]))
        else:
            chains.append(_photo_chain(image, frames, f"bg{index}", options, colors[index], spans[index]))
        text = f"{box}:v"
        fades = _text_fades(index, count, frames) if options.backdrop else []
        if fades:
            chains.append(f"[{box}:v]format=rgba,{','.join(fades)}[t{index}]")
            text = f"t{index}"
        chains.append(f"[bg{index}][{text}]overlay=x={box_x}:y={box_y},format=yuv420p,setsar=1[v{index}]")

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
    layer_chains, previous = _layer_chains(layers or [], first_caption + len(captions), previous)
    chains += layer_chains
    chains.append(f"[{previous}]format=yuv420p[vout]")

    total = _seconds(timeline.total_frames)
    # With sound effects the mix of music and narration is "base", and each effect is added on top of it.
    out = "base" if sounds else "aout"
    voices = voices or [False] * count
    clip_sounds = [bool(clips[index] and (clip_sounds or [False] * count)[index]) for index in range(count)]
    bed = out if not (any(voices) or any(clip_sounds)) else "bed"
    if music_volume is None:
        # A silent bed instead of no audio stream, so the narration always has something to be mixed onto.
        chains.append(f"anullsrc=r={AUDIO_RATE}:cl=stereo,atrim=duration={total}[{bed}]")
    else:
        music = 2 * len(box_positions)
        fade_start = max(0.0, timeline.total_seconds - MUSIC_FADE_SECONDS)
        levels = music_level_expression(timeline, music_levels or [None] * count)
        chains.append(
            f"[{music}:a]aresample={AUDIO_RATE},aformat=channel_layouts=stereo,"
            f"volume={music_volume:.4f},{f"volume='{levels}':eval=frame," if levels else ''}atrim=duration={total},"
            f"afade=t=out:st={fade_start:.6f}:d={MUSIC_FADE_SECONDS}[{bed}]"
        )
    if bed == "bed":
        chains += _voice_chains(
            voices,
            timeline,
            2 * len(box_positions) + (music_volume is not None),
            clip_sounds,
            [speeds[index] for index in range(count)],
            cut,
        )
        voice = "voice"
        if options.voice_volume != 1:
            chains.append(f"[voice]volume={options.voice_volume:.4f}[voicelevel]")
            voice = "voicelevel"
        if options.ducking and music_volume is not None:
            chains.append(f"[{voice}]asplit=2[voicemix][voicekey]")
            chains.append(f"[bed][voicekey]{DUCKING}[ducked]")
            bed, voice = "ducked", "voicemix"
        # amerge + pan adds the two tracks at full level; amix would halve both (FFmpeg 4.3 has no normalize=0).
        chains.append(f"[{bed}][{voice}]amerge=inputs=2,pan=stereo|c0=c0+c2|c1=c1+c3[{out}]")
    chains += _sound_chains(sounds or [], timeline.total_frames * AUDIO_RATE // FPS)
    return ";".join(chains)


def _text_fades(index: int, count: int, frames: int) -> list[str]:
    """A backdrop video's text box fades in at its scene's start (not the title's: the first frame is the cover) and
    out before its end (not the last scene's, which the video ends on)."""
    length = f"{TEXT_FADE_SECONDS:.3f}"
    fades = [f"fade=t=in:st=0:d={length}:alpha=1"] if index > 0 else []
    if index < count - 1:
        fades.append(f"fade=t=out:st={max(0.0, frames / FPS - TEXT_FADE_SECONDS):.3f}:d={length}:alpha=1")
    return fades


def music_level_expression(timeline: Timeline, levels: list[str | None]) -> str | None:
    """The music's level over time: each scene with its own level multiplies the video's for its seconds."""
    parts, start = [], 0
    for frames, level in zip(timeline.scene_frames, levels):
        if level is not None:
            parts.append(
                f"if(between(t,{_seconds(start)},{_seconds(start + frames)}),{MUSIC_LEVELS[level].gain:.4f},1)"
            )
        start += frames
    return "*".join(parts) or None


def _sound_chains(sounds: list[SoundInput], samples: int) -> list[str]:
    """Each effect made by its source filter, at its level, delayed to its second and as long as the video, then
    added to the mix at full level as the narration is (amerge + pan, see above)."""
    chains, previous = [], "base"
    for index, item in enumerate(sounds):
        delay = round(item.start * 1000)
        chains.append(
            f"{SOUNDS[item.sound].source},aformat=sample_rates={AUDIO_RATE}:channel_layouts=stereo,"
            f"volume={item.gain:.4f},adelay={delay}|{delay},apad,atrim=end_sample={samples}[fx{index}]"
        )
        label = "aout" if index == len(sounds) - 1 else f"mix{index}"
        chains.append(f"[{previous}][fx{index}]amerge=inputs=2,pan=stereo|c0=c0+c2|c1=c1+c3[{label}]")
        previous = label
    return chains


def _clip_sound_chain(source: int, index: int, samples: int, speed: float, cut: bool, label: str) -> str:
    """A clip's own sound for its scene's segment. The clip's picture starts `clip_lead` before the scene, so its
    sound is taken from that far in (at the clip's speed) to stay in step with the lips; `atempo` plays it at the
    clip's speed (0.5–2×, atempo's own range), and it is padded or cut to the segment's exact samples."""
    skip = clip_lead(index, cut) * speed
    tempo = f"atempo={speed:g}," if speed != 1 else ""
    return (
        f"[{source}:a]atrim=start={skip:.6f},asetpts=PTS-STARTPTS,{tempo}aresample={AUDIO_RATE},"
        f"aformat=channel_layouts=stereo,apad,atrim=end_sample={samples}[{label}]"
    )


def _voice_chains(
    voices: list[bool],
    timeline: Timeline,
    first_input: int,
    clip_sounds: list[bool] | None = None,
    speeds: list[float] | None = None,
    cut: bool = False,
) -> list[str]:
    """One narration track as long as the video: each scene's segment holds its narration, delayed past the
    crossfade and padded with silence, its clip's own sound when it is heard, both added together, or only silence.
    Segment lengths are exact sample counts of the scene's frames, so the narration stays on its scene however long
    the video is. A scene's clip is its input 2 × index (see build_filter_graph)."""
    clip_sounds = clip_sounds or [False] * len(voices)
    speeds = speeds or [1.0] * len(voices)
    chains, labels, voice_input = [], [], first_input
    for index, (frames, has_voice) in enumerate(zip(timeline.scene_frames, voices)):
        samples = frames * AUDIO_RATE // FPS
        heard = clip_sounds[index]
        voice_label = f"vn{index}" if heard else f"vo{index}"
        if has_voice:
            delay = round(VOICE_LEAD * 1000)
            chains.append(
                f"[{voice_input}:a]aresample={AUDIO_RATE},aformat=channel_layouts=stereo,"
                f"adelay={delay}|{delay},apad,atrim=end_sample={samples}[{voice_label}]"
            )
            voice_input += 1
        if heard:
            sound_label = f"cs{index}" if has_voice else f"vo{index}"
            chains.append(_clip_sound_chain(2 * index, index, samples, speeds[index], cut, sound_label))
            if has_voice:
                chains.append(f"[vn{index}][cs{index}]amerge=inputs=2,pan=stereo|c0=c0+c2|c1=c1+c3[vo{index}]")
        elif not has_voice:
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
    layers: list[LayerInput] | None = None,
    sounds: list[SoundInput] | None = None,
    music_start: float = 0.0,
) -> list[str]:
    argv = [ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-y"]
    for scene, frames in zip(scenes, timeline.scene_frames):
        if scene.video_start is not None:
            if scene.loop:
                argv += ["-stream_loop", "-1"]
            # Input seeking: the clip's first decoded frame is the one at the start time, as in the preview.
            argv += ["-ss", f"{scene.video_start:.3f}", "-max_pixels", str(MAX_CLIP_PIXELS)]
        argv += ["-i", str(scene.image)]
        if options.backdrop:
            # Looped for the scene's seconds, so the text box has frames to fade on.
            argv += ["-loop", "1", "-framerate", str(FPS), "-t", _seconds(frames)]
        argv += ["-i", str(scene.text_box)]
    if music is not None:
        # Looped, and from where the member chose in the song.
        argv += ["-stream_loop", "-1", *(["-ss", f"{music_start:.3f}"] if music_start else []), "-i", str(music)]
    for scene in scenes:
        if scene.voice is not None:
            argv += ["-i", str(scene.voice)]
    for caption in captions or []:
        argv += ["-i", str(caption.image)]
    for layer in layers or []:
        # Looped up to where it leaves, so its entrance has frames to fade in on.
        argv += ["-loop", "1", "-framerate", str(FPS), "-t", f"{layer.end:.3f}", "-i", str(layer.image)]
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
        layers,
        sounds,
        [scene.music_level for scene in scenes],
        [scene.video_sound for scene in scenes],
        [scene.motion_span for scene in scenes],
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
