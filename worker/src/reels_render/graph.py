"""Pure builders for the single FFmpeg filter graph and its argv.

Files are only ever passed with `-i` and referenced by stream label, so no path (with spaces,
drive colons or backslashes) is ever escaped into the graph.
"""

from dataclasses import dataclass
from pathlib import Path

from .textbox import FRAME_HEIGHT, FRAME_WIDTH
from .timeline import FPS, XFADE_FRAMES, Timeline

ZOOM_END = 1.12
# Pre-scaling above the frame size keeps zoompan's integer crop steps sub-pixel in the output.
PRESCALE = 2
AUDIO_RATE = 48000
MUSIC_FADE_SECONDS = 1.5


@dataclass(frozen=True)
class SceneInput:
    image: Path
    text_box: Path
    box_x: int
    box_y: int


def zoom_expression(clip_frames: int) -> str:
    """Linear zoom from 1.00 on the clip's first frame to ZOOM_END on its last frame."""
    return f"1+{ZOOM_END - 1:.4f}*on/{clip_frames - 1}"


def _seconds(frames: int) -> str:
    return f"{frames / FPS:.6f}"


def build_filter_graph(
    box_positions: list[tuple[int, int]],
    timeline: Timeline,
    music_volume: float | None,
) -> str:
    """Inputs are ordered image 0, text box 0, image 1, text box 1, …, then the music if any."""
    scale_w, scale_h = FRAME_WIDTH * PRESCALE, FRAME_HEIGHT * PRESCALE
    chains: list[str] = []
    for index, ((box_x, box_y), frames) in enumerate(zip(box_positions, timeline.clip_frames)):
        image, box = 2 * index, 2 * index + 1
        chains.append(
            f"[{image}:v]scale={scale_w}:{scale_h}:force_original_aspect_ratio=increase:out_range=tv,"
            f"crop={scale_w}:{scale_h},format=yuv420p,setsar=1,"
            f"zoompan=z='{zoom_expression(frames)}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={frames}:s={FRAME_WIDTH}x{FRAME_HEIGHT}:fps={FPS},"
            f"format=yuv420p[bg{index}]"
        )
        chains.append(f"[bg{index}][{box}:v]overlay=x={box_x}:y={box_y},format=yuv420p,setsar=1[v{index}]")

    previous = "v0"
    for index, offset in enumerate(timeline.xfade_offsets, start=1):
        label = f"x{index}"
        chains.append(
            f"[{previous}][v{index}]xfade=transition=fade:duration={_seconds(XFADE_FRAMES)}"
            f":offset={_seconds(offset)}[{label}]"
        )
        previous = label
    chains.append(f"[{previous}]format=yuv420p[vout]")

    total = _seconds(timeline.total_frames)
    if music_volume is None:
        # A silent bed instead of no audio stream; a later TTS track is mixed onto this bed.
        chains.append(f"anullsrc=r={AUDIO_RATE}:cl=stereo,atrim=duration={total}[aout]")
    else:
        music = 2 * len(box_positions)
        fade_start = max(0.0, timeline.total_seconds - MUSIC_FADE_SECONDS)
        chains.append(
            f"[{music}:a]aresample={AUDIO_RATE},aformat=channel_layouts=stereo,"
            f"volume={music_volume:.4f},atrim=duration={total},"
            f"afade=t=out:st={fade_start:.6f}:d={MUSIC_FADE_SECONDS}[aout]"
        )
    return ";".join(chains)


def build_ffmpeg_args(
    ffmpeg: str,
    scenes: list[SceneInput],
    timeline: Timeline,
    music: Path | None,
    music_volume: float,
    output: Path,
) -> list[str]:
    argv = [ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-y"]
    for scene in scenes:
        argv += ["-i", str(scene.image), "-i", str(scene.text_box)]
    if music is not None:
        argv += ["-stream_loop", "-1", "-i", str(music)]
    graph = build_filter_graph(
        [(scene.box_x, scene.box_y) for scene in scenes],
        timeline,
        music_volume if music is not None else None,
    )
    argv += [
        "-filter_complex", graph,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "160k", "-ar", str(AUDIO_RATE), "-ac", "2",
        "-t", _seconds(timeline.total_frames),
        "-movflags", "+faststart",
        "-f", "mp4", str(output),
    ]
    return argv
