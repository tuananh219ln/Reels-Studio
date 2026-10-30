from pathlib import Path

import pytest

from reels_render.graph import SceneInput, build_ffmpeg_args, build_filter_graph, zoom_expression
from reels_render.timeline import build_timeline

TIMELINE = build_timeline([3, 4, 4])
POSITIONS = [(100, 700), (60, 1100), (60, 1200)]


def evaluate_zoom(expression: str, frame: int) -> float:
    return eval(expression.replace("on", str(frame)), {"__builtins__": {}})


@pytest.mark.parametrize("frames", [30, 96, 132])
def test_zoom_runs_from_1_to_1_12_over_the_clip(frames):
    expression = zoom_expression(frames)
    assert evaluate_zoom(expression, 0) == pytest.approx(1.00, abs=1e-9)
    assert evaluate_zoom(expression, frames - 1) == pytest.approx(1.12, abs=0.01)


def test_graph_chains_scenes_with_centred_crossfades():
    graph = build_filter_graph(POSITIONS, TIMELINE, music_volume=None)
    assert "[0:v]" in graph and "[1:v]" in graph and "[5:v]" in graph
    assert "zoompan=z='1+0.1200*on/95'" in graph
    assert "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'" in graph  # zoom around the centre
    assert "overlay=x=60:y=1100" in graph
    assert "xfade=transition=fade:duration=0.400000:offset=2.800000" in graph
    assert "offset=6.800000" in graph
    assert graph.endswith("[aout]")


def test_graph_without_music_has_silent_track_of_full_length():
    graph = build_filter_graph(POSITIONS, TIMELINE, music_volume=None)
    assert "anullsrc=r=48000:cl=stereo,atrim=duration=11.000000[aout]" in graph
    assert "[6:a]" not in graph


def test_graph_with_music_sets_volume_trims_and_fades_out():
    graph = build_filter_graph(POSITIONS, TIMELINE, music_volume=0.25)
    assert "[6:a]" in graph
    assert "volume=0.2500" in graph
    assert "atrim=duration=11.000000" in graph
    assert "afade=t=out:st=9.500000:d=1.5" in graph
    assert "anullsrc" not in graph


def test_graph_mixes_narration_segments_onto_the_bed():
    graph = build_filter_graph(POSITIONS, TIMELINE, music_volume=None, voices=[False, True, True])
    assert "anullsrc=r=48000:cl=stereo,atrim=duration=11.000000[bed]" in graph
    # The title has no narration: silence for its 3 s (90 frames × 1600 samples).
    assert "anullsrc=r=48000:cl=stereo,atrim=end_sample=144000[vo0]" in graph
    assert "[6:a]aresample=48000,aformat=channel_layouts=stereo,adelay=200|200,apad,atrim=end_sample=192000[vo1]" in graph
    assert "[7:a]" in graph and "[8:a]" not in graph
    assert "[vo0][vo1][vo2]concat=n=3:v=0:a=1[voice]" in graph
    assert graph.endswith("[bed][voice]amerge=inputs=2,pan=stereo|c0=c0+c2|c1=c1+c3[aout]")


def test_narration_inputs_come_after_the_music():
    graph = build_filter_graph(POSITIONS, TIMELINE, music_volume=0.25, voices=[True, False, False])
    assert "[6:a]aresample=48000,aformat=channel_layouts=stereo,volume=0.2500" in graph
    assert "[7:a]aresample=48000,aformat=channel_layouts=stereo,adelay=200|200" in graph


def test_graph_without_narration_keeps_its_old_audio_chain():
    assert build_filter_graph(POSITIONS, TIMELINE, None, voices=[False] * 3) == \
        build_filter_graph(POSITIONS, TIMELINE, None)


@pytest.mark.parametrize("music", [None, Path("C:/Users/Young Sheldon/nhạc nền/bài 1.mp3")])
def test_files_are_inputs_and_never_inside_the_graph(music):
    folder = Path("C:/Users/Young Sheldon/tmp dir")
    scenes = [
        SceneInput(folder / f"scene {i}.jpg", folder / f"text {i}.png", x, y, folder / f"lời đọc {i}.mp3")
        for i, (x, y) in enumerate(POSITIONS)
    ]
    output = folder / "out video.mp4"
    argv = build_ffmpeg_args("ffmpeg", scenes, TIMELINE, music, 0.25, output)

    graph = argv[argv.index("-filter_complex") + 1]
    paths = [str(p) for s in scenes for p in (s.image, s.text_box, s.voice)] + ([str(music)] if music else [])
    for path in paths:
        assert argv[argv.index(path) - 1] == "-i"
        assert path not in graph
    assert str(output) not in graph
    assert "\\" not in graph and ":/" not in graph and "Young Sheldon" not in graph
    assert argv[-1] == str(output)
    if music:
        assert argv[argv.index(str(music)) - 3 : argv.index(str(music))] == ["-stream_loop", "-1", "-i"]


def test_clip_scene_has_no_zoom_and_is_cut_to_its_exact_frames():
    graph = build_filter_graph(POSITIONS, TIMELINE, music_volume=None, clips=[True, False, False])
    clip = graph.split(";")[0]
    # The title is 3 s plus half a crossfade: 96 frames.
    assert clip == (
        "[0:v]setpts=PTS-STARTPTS,fps=30,scale=1080:1920:force_original_aspect_ratio=increase:out_range=tv,"
        "crop=1080:1920,format=yuv420p,setsar=1,tpad=stop_mode=clone:stop_duration=3.200000,"
        "trim=end_frame=96,setpts=PTS-STARTPTS[bg0]"
    )
    assert graph.count("zoompan") == 2
    assert "[0:a]" not in graph, "tiếng gốc của video không bao giờ được dùng"


def test_graph_without_clips_is_unchanged():
    assert build_filter_graph(POSITIONS, TIMELINE, None, clips=[False] * 3) == \
        build_filter_graph(POSITIONS, TIMELINE, None)


def test_clip_is_seeked_to_its_start_before_its_input():
    scenes = [SceneInput(Path(f"scene{i}.jpg"), Path(f"text{i}.png"), x, y) for i, (x, y) in enumerate(POSITIONS)]
    scenes[1] = SceneInput(Path("vuon.mp4"), Path("text1.png"), 60, 1100, video_start=1.5)
    argv = build_ffmpeg_args("ffmpeg", scenes, TIMELINE, None, 0.25, Path("out.mp4"))
    at = argv.index("vuon.mp4")
    assert argv[at - 5 : at] == ["-ss", "1.500", "-max_pixels", "9437184", "-i"]
    assert argv.count("-ss") == 1
    assert "[2:v]setpts=PTS-STARTPTS,fps=30" in argv[argv.index("-filter_complex") + 1]


def test_a_clip_starting_at_zero_is_still_a_clip():
    """0 is every new clip's start: it must not read as "no clip"."""
    scenes = [SceneInput(Path(f"scene{i}.jpg"), Path(f"text{i}.png"), x, y) for i, (x, y) in enumerate(POSITIONS)]
    scenes[0] = SceneInput(Path("vuon.mp4"), Path("text0.png"), 100, 700, video_start=0.0)
    argv = build_ffmpeg_args("ffmpeg", scenes, TIMELINE, None, 0.25, Path("out.mp4"))
    assert argv[argv.index("vuon.mp4") - 5 : argv.index("vuon.mp4")][:2] == ["-ss", "0.000"]
    graph = argv[argv.index("-filter_complex") + 1]
    assert graph.startswith("[0:v]setpts=PTS-STARTPTS,fps=30") and graph.count("zoompan") == 2
