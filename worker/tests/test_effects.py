"""Per-scene effects: the transition into a scene and its colour preset."""

import pytest
from conftest import extract_frame, make_image, needs_ffmpeg, scene, script_data, write_script
from PIL import ImageStat

from reels_render.effects import COLOR_PRESETS, SCENE_TRANSITIONS
from reels_render.errors import InputError
from reels_render.graph import build_filter_graph
from reels_render.options import RenderOptions
from reels_render.render import render_video
from reels_render.script import load_script
from reels_render.timeline import build_timeline

BOXES = [(0, 0), (0, 0), (0, 0)]


def test_a_scene_transition_replaces_the_video_one_at_its_own_boundary_only():
    timeline = build_timeline([2, 2, 2])
    graph = build_filter_graph(BOXES, timeline, None, transitions=[None, "circle", None])
    first, second = timeline.xfade_offsets
    assert f"[v0][v1]xfade=transition=circleopen:duration=0.400000:offset={first / 30:.6f}[x1]" in graph
    assert f"[x1][v2]xfade=transition=fade:duration=0.400000:offset={second / 30:.6f}[x2]" in graph


def test_without_scene_effects_the_graph_is_the_one_from_before():
    timeline = build_timeline([2, 2, 2])
    for options in (RenderOptions(), RenderOptions(transition="cut"), RenderOptions(transition="slide")):
        assert build_filter_graph(BOXES, timeline, None, options=options) == build_filter_graph(
            BOXES, timeline, None, options=options, transitions=[None] * 3, colors=[None] * 3
        )


def test_every_boundary_a_cut_joins_the_scenes_end_to_end():
    graph = build_filter_graph(BOXES, build_timeline([2, 3, 2]), None, transitions=[None, "cut", "cut"])
    assert "xfade" not in graph and "[v0][v1][v2]concat=n=3:v=1:a=0[x0]" in graph


def test_a_cut_among_transitions_is_a_one_frame_fade_at_the_same_offset():
    timeline = build_timeline([2, 2, 2])
    graph = build_filter_graph(
        BOXES, timeline, None, options=RenderOptions(transition="cut"), transitions=[None, None, "flash"]
    )
    first, second = timeline.xfade_offsets
    # The total length stays the timeline's: every boundary keeps its crossfade offset.
    assert f"[v0][v1]xfade=transition=fade:duration=0.033333:offset={first / 30:.6f}[x1]" in graph
    assert f"xfade=transition=fadewhite:duration=0.400000:offset={second / 30:.6f}[x2]" in graph
    assert "concat=n=3:v=1" not in graph


def test_a_colour_preset_grades_only_its_scene_before_the_text_box_goes_on():
    graph = build_filter_graph(BOXES, build_timeline([2, 2, 2]), None, colors=[None, "mono", None])
    mono = COLOR_PRESETS["mono"].filter
    assert graph.count(mono) == 1
    chain = next(part for part in graph.split(";") if part.endswith("[bg1]"))
    assert chain.endswith(f",{mono},format=yuv420p[bg1]")


def test_a_clip_scene_takes_its_colour_too():
    graph = build_filter_graph(BOXES, build_timeline([2, 2, 2]), None, clips=[False, True, False], colors=["warm"] * 3)
    clip = next(part for part in graph.split(";") if part.endswith("[bg1]"))
    assert "setpts=" in clip and COLOR_PRESETS["warm"].filter in clip


def test_every_preset_has_a_vietnamese_label():
    for presets in (SCENE_TRANSITIONS, COLOR_PRESETS):
        assert all(item.label and item.label[0].isupper() for item in presets.values())


def test_the_script_takes_a_scene_transition_and_colour_but_not_a_transition_into_the_title(tmp_path):
    make_image(tmp_path / "a.jpg", (1080, 1920))
    data = script_data(2)
    data["scenes"][1] |= {"transition": "zoom", "color": "cinematic"}
    data["title"]["color"] = "warm"
    script = load_script(write_script(tmp_path, data))
    assert (script.scenes[1].transition, script.scenes[1].color) == ("zoom", "cinematic")
    assert (script.title.transition, script.title.color) == (None, "warm")

    for field, value in (("transition", "spin"), ("color", "neon")):
        data = script_data(1)
        data["scenes"][0][field] = value
        with pytest.raises(InputError, match=f'Cảnh 1: "{field}"'):
            load_script(write_script(tmp_path, data))
    data = script_data(1, transition="fade")
    with pytest.raises(InputError, match="Cảnh tiêu đề"):
        load_script(write_script(tmp_path, data))


@needs_ffmpeg
def test_a_render_with_a_scene_transition_and_a_black_and_white_scene(tmp_path):
    make_image(tmp_path / "a.jpg", (1080, 1920), (220, 60, 40))
    data = {
        "title": scene("TIÊU ĐỀ", 1),
        "scenes": [scene("", 2, transition="circle", color="mono"), scene("", 2, transition="cut")],
    }
    output = render_video(load_script(write_script(tmp_path, data)), tmp_path / "out.mp4")
    grey = extract_frame(output, 2.0, tmp_path / "grey.png")
    red = extract_frame(output, 4.0, tmp_path / "red.png")
    # Black and white: the channels match; the next scene keeps its red.
    r, g, b = ImageStat.Stat(grey).mean
    assert abs(r - g) < 4 and abs(g - b) < 4
    r, g, b = ImageStat.Stat(red).mean
    assert r > g + 80
