"""'Lặp clip': a scene's clip shorter than the scene starts again from its start time instead of holding its last frame."""

import pytest
from conftest import extract_frame, make_clip, make_image, needs_ffmpeg, scene, write_script

from reels_render.errors import InputError
from reels_render.ffmpeg import probe
from reels_render.render import render_video, trim_loops
from reels_render.script import load_script


def test_the_loop_is_read_with_the_clip_and_ignored_without_one(tmp_path):
    make_image(tmp_path / "a.jpg", (40, 40))
    (tmp_path / "vuon.mp4").write_bytes(b"clip")
    data = {
        "title": scene(image="", video="vuon.mp4", video_loop=True),
        "scenes": [scene(video_loop=True), scene()],
    }
    script = load_script(write_script(tmp_path, data))
    assert [item.video_loop for item in script.all_scenes] == [True, False, False]


def test_a_loop_that_is_not_true_or_false_is_named(tmp_path):
    make_image(tmp_path / "a.jpg", (40, 40))
    (tmp_path / "vuon.mp4").write_bytes(b"clip")
    data = {"title": scene(), "scenes": [scene(image="", video="vuon.mp4", video_loop="yes")]}
    with pytest.raises(InputError, match='Cảnh 1: "video_loop" phải là true hoặc false'):
        load_script(write_script(tmp_path, data))


@needs_ffmpeg
def test_a_looped_clip_is_cut_at_its_start_so_it_loops_back_there(tmp_path):
    make_clip(tmp_path / "vuon.mp4", 3, "640x360")
    make_image(tmp_path / "a.jpg", (40, 40))
    data = {
        "title": scene(),
        "scenes": [
            scene("Ý một", 2, image="", video="vuon.mp4", video_start=1.0, video_loop=True),
            scene("Ý hai", 2, image="", video="vuon.mp4", video_start=1.0),
        ],
    }
    script = load_script(write_script(tmp_path, data))
    work = tmp_path / "work"
    work.mkdir()
    cut = trim_loops("ffmpeg", script, work)
    looped, plain = cut.scenes
    assert (looped.video, looped.video_start) == (work / "loop-01.mp4", 0.0)
    assert abs(float(probe("ffprobe", work / "loop-01.mp4")["format"]["duration"]) - 2) < 0.1
    # A scene without the loop keeps its clip and its start.
    assert (plain.video, plain.video_start) == (tmp_path / "vuon.mp4", 1.0)


@needs_ffmpeg
def test_a_short_looped_clip_keeps_moving_where_a_plain_one_would_hold(tmp_path):
    make_clip(tmp_path / "vuon.mp4", 1, "640x360")
    make_image(tmp_path / "a.jpg", (40, 40))
    data = {
        "title": scene(),
        "scenes": [scene("Ý một", 4, image="", video="vuon.mp4", video_loop=True)],
    }
    output = render_video(load_script(write_script(tmp_path, data)), tmp_path / "out.mp4")
    # Well past the clip's one second, two frames half a second apart still differ: the clip plays again.
    first = extract_frame(output, 3.0, tmp_path / "a.png")
    second = extract_frame(output, 3.5, tmp_path / "b.png")
    assert first.tobytes() != second.tobytes()
