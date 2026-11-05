"""Sound effects made by FFmpeg itself, a scene's own music level, and where the song starts."""

import pytest
from conftest import make_image, make_tone, mean_volume, needs_ffmpeg, scene, script_data, write_script

from reels_render.errors import InputError
from reels_render.graph import SoundInput, build_ffmpeg_args, build_filter_graph, music_level_expression
from reels_render.render import render_video
from reels_render.script import load_script
from reels_render.sounds import MUSIC_LEVELS, SOUND_VOLUMES, SOUNDS, make_sound
from reels_render.timeline import build_timeline

BOXES = [(0, 0), (0, 0), (0, 0)]


def test_every_preset_has_a_vietnamese_label():
    for presets in (SOUNDS, SOUND_VOLUMES, MUSIC_LEVELS):
        assert all(item.label and item.label[0].isupper() for item in presets.values())


@needs_ffmpeg
@pytest.mark.parametrize("name", list(SOUNDS))
def test_every_sound_is_made_and_heard(tmp_path, name):
    path = make_sound(name, tmp_path / f"{name}.mp3")
    assert mean_volume(path, 0, SOUNDS[name].seconds) > -40


def test_a_sound_is_mixed_in_at_its_second_and_level_without_changing_the_length():
    timeline = build_timeline([2, 2, 2])
    sounds = [SoundInput("ding", 2.5, 1.6), SoundInput("whoosh", 0.25, 0.5)]
    graph = build_filter_graph(BOXES, timeline, None, sounds=sounds)
    assert f"{SOUNDS['ding'].source}" in graph and f"{SOUNDS['whoosh'].source}" in graph
    assert "volume=1.6000,adelay=2500|2500,apad,atrim=end_sample=288000[fx0]" in graph
    assert "adelay=250|250" in graph
    # Each sound is added to the mix at full level, as the narration is.
    assert "[mix0][fx1]amerge=inputs=2,pan=stereo|c0=c0+c2|c1=c1+c3[aout]" in graph


def test_without_sounds_the_audio_is_the_one_from_before():
    timeline = build_timeline([2, 2, 2])
    assert build_filter_graph(BOXES, timeline, 0.25, [True, False, True]) == build_filter_graph(
        BOXES, timeline, 0.25, [True, False, True], sounds=[], music_levels=[None] * 3
    )


def test_a_scenes_music_level_holds_for_its_seconds():
    timeline = build_timeline([2, 2, 2])
    assert music_level_expression(timeline, [None, "off", "high"]) == (
        "if(between(t,2.000000,4.000000),0.0000,1)*if(between(t,4.000000,6.000000),1.6000,1)"
    )
    assert music_level_expression(timeline, [None, None, None]) is None
    graph = build_filter_graph(BOXES, timeline, 0.25, music_levels=[None, "low", None])
    assert "volume='if(between(t,2.000000,4.000000),0.4000,1)':eval=frame" in graph


def test_the_song_starts_where_the_member_chose(tmp_path):
    from reels_render.graph import SceneInput

    scenes = [SceneInput(tmp_path / f"{n}.jpg", tmp_path / f"{n}.png", 0, 0) for n in range(2)]
    argv = build_ffmpeg_args(
        "ffmpeg", scenes, build_timeline([2, 2]), tmp_path / "m.mp3", 0.25, tmp_path / "o.mp4", music_start=12.5
    )
    at = argv.index(str(tmp_path / "m.mp3"))
    assert argv[at - 5 : at] == ["-stream_loop", "-1", "-ss", "12.500", "-i"]
    plain = build_ffmpeg_args("ffmpeg", scenes, build_timeline([2, 2]), tmp_path / "m.mp3", 0.25, tmp_path / "o.mp4")
    assert "-ss" not in plain


def test_the_script_takes_sounds_and_a_music_level(tmp_path):
    make_image(tmp_path / "a.jpg", (1080, 1920))
    data = script_data(1)
    data["scenes"][0] |= {"sounds": [{"sound": "pop", "start": 0.5, "volume": "loud"}], "music_level": "off"}
    (only,) = load_script(write_script(tmp_path, data)).scenes
    assert ([(s.sound, s.start, s.volume) for s in only.sounds], only.music_level) == ([("pop", 0.5, "loud")], "off")
    for bad in ({"sound": "laugh"}, {"sound": "pop", "volume": "max"}, {"sound": "pop", "start": -1}):
        data["scenes"][0]["sounds"] = [bad]
        with pytest.raises(InputError, match="Cảnh 1, âm 1"):
            load_script(write_script(tmp_path, data))
    data["scenes"][0] |= {"sounds": [], "music_level": "max"}
    with pytest.raises(InputError, match='"music_level"'):
        load_script(write_script(tmp_path, data))


@needs_ffmpeg
def test_a_boom_is_heard_at_its_second_and_a_scene_without_music_is_quiet(tmp_path):
    make_image(tmp_path / "a.jpg", (1080, 1920))
    tone = make_tone(tmp_path / "tone.wav", 1)
    data = {
        "title": scene("TIÊU ĐỀ", 1),
        "scenes": [scene("", 2, music_level="off"), scene("", 2, sounds=[{"sound": "boom", "start": 0.5}])],
    }
    output = render_video(load_script(write_script(tmp_path, data)), tmp_path / "out.mp4", music=tone)
    # Scene 1 (1–3 s) has no music; scene 2 (3–5 s) has music and a boom from 3.5 s.
    assert mean_volume(output, 1.4, 1.2) < -60
    with_music = mean_volume(output, 4.4, 0.3)
    assert mean_volume(output, 3.5, 0.3) > with_music + 3
