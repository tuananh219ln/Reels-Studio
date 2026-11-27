"""'Ẩn chữ sau X giây': a content scene's text box fades out after its hold; the title and the last scene keep theirs."""

import pytest
from conftest import extract_frame, make_image, needs_ffmpeg, scene, write_script
from PIL import Image, ImageChops

from reels_render.errors import InputError
from reels_render.graph import hold_seconds
from reels_render.render import render_video
from reels_render.script import load_script

FPS = 30


@pytest.mark.parametrize(
    ("hold", "index", "count", "seconds", "expected"),
    [
        (2.5, 1, 4, 6, 2.5),
        (None, 1, 4, 6, None),
        (2.5, 0, 4, 6, None),  # the title scene keeps its text
        (2.5, 3, 4, 6, None),  # the last scene (the call to action) keeps its text
        (5.7, 1, 4, 6, None),  # within 0.3 s of the scene's end: the whole scene
        (5.69, 1, 4, 6, 5.69),
    ],
)
def test_hold_seconds_skips_title_last_scene_and_holds_near_the_end(hold, index, count, seconds, expected):
    assert hold_seconds(hold, index, count, round(seconds * FPS)) == expected


@pytest.mark.parametrize("value", [0.5, 6.5, "2", True])
def test_a_hold_outside_one_to_six_seconds_is_refused(tmp_path, value):
    make_image(tmp_path / "a.jpg", (1080, 1920))
    data = {"title": scene(), "scenes": [scene(text_hold_sec=value)]}
    with pytest.raises(InputError, match="text_hold_sec"):
        load_script(write_script(tmp_path, data))


def _text_pixels(frame: Image.Image, plain: Image.Image) -> bool:
    # Compression leaves faint noise on a flat photo, so only a clear difference is text.
    return max(high for _, high in ImageChops.difference(frame, plain).getextrema()) > 60


@needs_ffmpeg
def test_the_text_fades_after_its_hold_and_the_scene_after_keeps_it(tmp_path):
    make_image(tmp_path / "a.jpg", (1080, 1920), (30, 90, 160))
    plain = Image.new("RGB", (1080, 1920), (30, 90, 160))
    data = {
        "title": scene("TIÊU ĐỀ", 1),
        "scenes": [
            scene("MỘT *chữ*", 4, text_hold_sec=1.5),
            scene("HAI *chữ*", 3),  # no hold: the text stays the whole scene
            scene("KẾT *chữ*", 3, text_hold_sec=1.5),  # the last scene ignores the hold
        ],
    }
    output = render_video(load_script(write_script(tmp_path, data)), tmp_path / "out.mp4")
    # Scene 1 runs from 1 s to 5 s: its text is up at 1.5 s, gone from 2.9 s (1 + 1.5 + 0.25 + margin).
    assert _text_pixels(extract_frame(output, 1.7, tmp_path / "a.png"), plain)
    assert not _text_pixels(extract_frame(output, 3.2, tmp_path / "b.png"), plain)
    assert _text_pixels(extract_frame(output, 7.0, tmp_path / "c.png"), plain)  # scene 2 keeps its text
    assert _text_pixels(extract_frame(output, 9.5, tmp_path / "d.png"), plain)  # so does the last scene
