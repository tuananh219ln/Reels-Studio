"""'Tiếng gốc': a scene's clip keeps its own sound, and captions follow the words it says ("Edit từ footage")."""

import dataclasses
from pathlib import Path

import pytest
from conftest import make_clip, make_image, mean_volume, needs_ffmpeg, script_data, write_script

from reels_render.captions import Word, plan_word_captions
from reels_render.errors import InputError
from reels_render.graph import SceneInput, all_cuts, build_ffmpeg_args, build_filter_graph, clip_lead
from reels_render.options import DEFAULT_OPTIONS
from reels_render.render import placed_words, render_video
from reels_render.script import load_script
from reels_render.timeline import build_timeline

TIMELINE = build_timeline([3, 4, 4])
POSITIONS = [(100, 700), (60, 1100), (60, 1200)]
CUTS = dataclasses.replace(DEFAULT_OPTIONS, transition="cut")


def chains(graph: str) -> list[str]:
    return graph.split(";")


# --- The graph ---


def test_a_heard_clip_sound_goes_on_the_narration_track_from_its_own_input():
    graph = build_filter_graph(
        POSITIONS, TIMELINE, music_volume=None, clips=[True, True, False], clip_sounds=[True, False, False]
    )
    # The title's clip (input 0) is heard from its start: the first scene has no crossfade before it.
    assert (
        "[0:a]atrim=start=0.000000,asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,"
        "apad,atrim=end_sample=144000[vo0]"
    ) in chains(graph)
    assert "[2:a]" not in graph, "a clip without Tiếng gốc stays silent"
    assert "[vo0][vo1][vo2]concat=n=3:v=0:a=1[voice]" in graph
    assert graph.endswith("[bed][voice]amerge=inputs=2,pan=stereo|c0=c0+c2|c1=c1+c3[aout]")


def test_the_sound_skips_what_the_clip_shows_before_its_scene_at_its_speed():
    """With crossfades a clip starts half a crossfade before its scene; its sound must start that far in, or the
    lips run ahead of the voice. At 1.5× that is 0.3 s of clip, played back by atempo."""
    graph = build_filter_graph(
        POSITIONS,
        TIMELINE,
        music_volume=None,
        clips=[False, True, False],
        clip_sounds=[False, True, False],
        speeds=[1, 1.5, 1],
    )
    assert "[2:a]atrim=start=0.300000,asetpts=PTS-STARTPTS,atempo=1.5,aresample=48000" in graph


def test_with_hard_cuts_the_sound_starts_with_the_scene():
    graph = build_filter_graph(
        POSITIONS, TIMELINE, music_volume=None, clips=[True] * 3, clip_sounds=[True] * 3, options=CUTS
    )
    for source in (0, 2, 4):
        assert f"[{source}:a]atrim=start=0.000000," in graph


def test_narration_and_clip_sound_in_one_scene_are_added_together():
    graph = build_filter_graph(
        POSITIONS,
        TIMELINE,
        music_volume=0.25,
        voices=[False, True, False],
        clips=[False, True, False],
        clip_sounds=[False, True, False],
    )
    # Music is input 6, the narration input 7.
    assert "[7:a]aresample=48000,aformat=channel_layouts=stereo,adelay=200|200,apad,atrim=end_sample=192000[vn1]" in (
        chains(graph)
    )
    assert "[vn1][cs1]amerge=inputs=2,pan=stereo|c0=c0+c2|c1=c1+c3[vo1]" in chains(graph)


def test_the_music_ducks_under_a_clip_sound_as_under_a_voice():
    options = dataclasses.replace(DEFAULT_OPTIONS, ducking=True)
    graph = build_filter_graph(
        POSITIONS, TIMELINE, 0.25, clips=[True, False, False], clip_sounds=[True, False, False], options=options
    )
    assert "[bed][voicekey]sidechaincompress" in graph


def test_a_clip_sound_on_a_photo_scene_is_ignored_and_the_old_graphs_stay():
    assert build_filter_graph(POSITIONS, TIMELINE, None, clip_sounds=[True] * 3) == build_filter_graph(
        POSITIONS, TIMELINE, None
    )
    assert build_filter_graph(POSITIONS, TIMELINE, 0.25, clips=[True] * 3, clip_sounds=[False] * 3) == (
        build_filter_graph(POSITIONS, TIMELINE, 0.25, clips=[True] * 3)
    )


def test_ffmpeg_args_pass_each_scenes_sound():
    scenes = [SceneInput(Path(f"scene{i}.jpg"), Path(f"text{i}.png"), x, y) for i, (x, y) in enumerate(POSITIONS)]
    scenes[1] = SceneInput(Path("noi.mp4"), Path("text1.png"), 60, 1100, video_start=2.0, video_sound=True)
    argv = build_ffmpeg_args("ffmpeg", scenes, TIMELINE, None, 0.25, Path("out.mp4"))
    assert "[2:a]atrim=start=0.200000," in argv[argv.index("-filter_complex") + 1]


def test_a_clip_leads_its_scene_only_between_crossfades():
    assert clip_lead(0, cut=False) == 0 and clip_lead(1, cut=True) == 0
    assert clip_lead(1, cut=False) == pytest.approx(0.2)
    assert all_cuts(CUTS, [None, None, None]) and not all_cuts(CUTS, [None, "fade", None])
    assert not all_cuts(DEFAULT_OPTIONS, [None, None, None]) and all_cuts(DEFAULT_OPTIONS, [None, "cut", "cut"])


# --- Captions from the real words ---


def test_word_captions_light_each_word_until_the_next_starts():
    words = [Word("Xin", 1.0, 1.2), Word("chào.", 1.3, 1.6), Word("Hôm", 2.0, 2.2)]
    cues = plan_word_captions(words, "word")
    assert [(cue.start, cue.end, cue.lit) for cue in cues] == [(1.0, 1.3, 0), (1.3, 1.6, 1), (2.0, 2.2, 0)]
    assert cues[0].lines == [["Xin", "chào."]] and cues[2].lines == [["Hôm"]]


def test_phrase_captions_last_from_the_first_word_to_the_last_and_off_has_none():
    words = [Word("Xin", 1.0, 1.2), Word("chào", 1.3, 1.6), Word("các", 1.7, 1.8), Word("bạn", 1.8, 2.0)]
    cues = plan_word_captions(words, "phrase")
    assert [(cue.start, cue.end, cue.lit) for cue in cues] == [(1.0, 2.0, None)]
    assert plan_word_captions(words, "off") == []
    assert plan_word_captions([Word("", 1, 2), Word("ờ", 2, 2)], "word") == []


def test_words_are_placed_in_the_videos_seconds():
    """A clip trimmed to start at 2 s, at 2× speed, in a scene from 10 s that it leads by 0.2 s."""
    clip = Path("noi.mp4")
    scene = load_scene(
        video=clip,
        video_start=2.0,
        video_speed=2.0,
        words=(
            Word("trước", 1.0, 1.5),  # before the trimmed start
            Word("một", 2.4, 2.8),
            Word("hai", 3.0, 3.6),
            Word("sau", 20.0, 21.0),  # after the scene
        ),
    )
    placed = placed_words(scene, 10.0, 12.0, 0.2)
    assert [(word.text, round(word.start, 3), round(word.end, 3)) for word in placed] == [
        ("một", 10.0, 10.2),
        ("hai", 10.3, 10.6),
    ]


def load_scene(**fields):
    from reels_render.script import Scene

    return Scene(label="Cảnh 1", number=1, first_line="", lines=[], seconds=2, image=None, keywords=(), **fields)


# --- The script ---


def test_the_script_reads_the_sound_and_the_words(tmp_path):
    make_clip(tmp_path / "noi.mp4", 2)
    make_image(tmp_path / "a.jpg", (900, 1600))
    data = script_data(scene_count=1)
    data["scenes"][0].update(
        image="", video="noi.mp4", video_sound=True, words=[{"text": "Xin", "start": 0.1, "end": 0.4}]
    )
    scene = load_script(write_script(tmp_path, data)).scenes[0]
    assert scene.video_sound is True and scene.words == (Word("Xin", 0.1, 0.4),)
    assert load_script(write_script(tmp_path, script_data(scene_count=1))).scenes[0].video_sound is False


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"video_sound": True}, '"video_sound" chỉ dùng cho cảnh có "video"'),
        ({"video_sound": "có"}, '"video_sound" phải là true hoặc false'),
        ({"words": "Xin chào"}, '"words" phải là danh sách'),
        ({"words": [{"text": "Xin", "start": 1}]}, '"end" phải là số'),
        ({"words": [{"text": "Xin", "start": 1, "end": 0.5}]}, '"end" phải từ 1 đến'),
    ],
)
def test_the_script_refuses_a_bad_sound_or_words(tmp_path, override, message):
    make_image(tmp_path / "a.jpg", (900, 1600))
    data = script_data(scene_count=1)
    data["scenes"][0].update(override)
    with pytest.raises(InputError, match=message):
        load_script(write_script(tmp_path, data))


# --- A real render ---


@needs_ffmpeg
def test_a_clip_with_tieng_goc_is_heard_and_the_others_stay_silent(tmp_path):
    make_clip(tmp_path / "noi.mp4", 3)
    make_image(tmp_path / "a.jpg", (900, 1600))
    data = script_data(scene_count=2, image="a.jpg", seconds=1)
    data["scenes"][0].update(
        image="",
        video="noi.mp4",
        seconds=2,
        video_sound=True,
        words=[{"text": "Xin", "start": 0.3, "end": 0.6}, {"text": "chào", "start": 0.7, "end": 1.1}],
    )
    data["scenes"][1].update(image="", video="noi.mp4", seconds=1)
    options = dataclasses.replace(CUTS, captions="word")
    output = render_video(load_script(write_script(tmp_path, data)), tmp_path / "video.mp4", options=options)
    assert mean_volume(output, 1.2, 1.5) > -40, "tiếng gốc của cảnh 1 phải nghe được"
    assert mean_volume(output, 0.1, 0.8) < -60, "cảnh tiêu đề là ảnh, không có tiếng"
    assert mean_volume(output, 3.1, 0.8) < -60, "clip không bật tiếng gốc thì vẫn im"


@needs_ffmpeg
def test_a_clip_without_a_sound_track_renders_silent_with_a_warning(tmp_path):
    import subprocess

    silent = tmp_path / "cam.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=720x1280:rate=25:duration=2",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(silent),
        ],
        check=True,
    )
    make_image(tmp_path / "a.jpg", (900, 1600))
    data = script_data(scene_count=1, image="a.jpg", seconds=1)
    data["scenes"][0].update(image="", video="cam.mp4", seconds=1, video_sound=True)
    warnings = []
    output = render_video(load_script(write_script(tmp_path, data)), tmp_path / "video.mp4", on_warning=warnings.append)
    assert output.exists() and warnings == ["Cảnh 1: video không có tiếng, cảnh này không có tiếng gốc"]
