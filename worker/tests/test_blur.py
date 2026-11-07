""" "Làm mờ vùng": boxes of a clip blurred for the whole scene, checked when read, drawn by FFmpeg in the render and by
Pillow in the app's previews."""

import pytest
from conftest import extract_frame, make_clip, make_image, needs_ffmpeg, script_data, write_script
from PIL import Image, ImageFilter, ImageStat

from reels_render.blur import blur_image, ffmpeg_blur, parse_blur, pixel_boxes
from reels_render.errors import InputError
from reels_render.options import RenderOptions
from reels_render.render import render_video
from reels_render.script import load_script

# The top left of the frame, well away from the title's text box.
BOX = [0.05, 0.05, 0.4, 0.15]


def test_boxes_are_read_as_fractions_of_the_frame():
    assert parse_blur(None, "Cảnh 1") == ()
    assert parse_blur([BOX], "Cảnh 1") == ((0.05, 0.05, 0.4, 0.15),)


@pytest.mark.parametrize(
    "value",
    ["x", [[0.1, 0.1, 0.1]], [[0.1, 0.1, True, 0.1]], [[0.9, 0.1, 0.2, 0.1]], [[0.1, 0.1, 0, 0.1]], [BOX] * 11],
)
def test_bad_boxes_are_refused_with_the_scene_named(value):
    with pytest.raises(InputError, match="Cảnh 1"):
        parse_blur(value, "Cảnh 1")


def test_boxes_land_on_even_pixels_inside_the_frame():
    assert pixel_boxes(((0.05, 0.05, 0.4, 0.15),)) == [(54, 96, 432, 288)]
    left, top, width, height = pixel_boxes(((0.999, 0.999, 0.001, 0.001),))[0]
    assert left % 2 == top % 2 == width % 2 == height % 2 == 0
    assert left + width <= 1080 and top + height <= 1920 and width >= 8 and height >= 8


def test_each_box_is_cut_out_blurred_and_laid_back():
    graph = ffmpeg_blur("in", "out", ((0.05, 0.05, 0.4, 0.15), (0.5, 0.5, 0.1, 0.1)), "s0")
    assert graph.startswith("[in]split=3[s0m0][s0c0][s0c1]")
    assert "crop=432:288:54:96,boxblur=luma_radius=48:luma_power=2[s0b0]" in graph
    assert graph.endswith("[s0m1][s0b1]overlay=540:960[out]")


def test_a_clip_scene_alone_takes_boxes(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"")
    data = script_data(scene_count=1, image="", seconds=1)
    data["scenes"][0]["video_blur"] = [BOX]
    with pytest.raises(InputError, match='"video_blur" chỉ dùng cho cảnh có "video"'):
        load_script(write_script(tmp_path, data))


def sharpness(image: Image.Image, box: tuple[int, int, int, int]) -> float:
    return ImageStat.Stat(image.crop(box).convert("L").filter(ImageFilter.FIND_EDGES)).mean[0]


def test_the_preview_blurs_the_same_pixels():
    frame = Image.effect_noise((1080, 1920), 80).convert("RGB")
    blurred = blur_image(frame, ((0.05, 0.05, 0.4, 0.15),))
    inside, outside = (54, 96, 486, 384), (54, 1200, 486, 1488)
    assert sharpness(blurred, inside) < sharpness(frame, inside) / 3
    assert list(blurred.crop(outside).getdata()) == list(frame.crop(outside).getdata())


@needs_ffmpeg
def test_the_render_blurs_the_box_of_the_clip_for_the_whole_scene(tmp_path):
    make_clip(tmp_path / "vuon.mp4", 2, rate=25)
    make_image(tmp_path / "a.jpg", (720, 1280))
    renders = {}
    # testsrc2's checkerboard, on the right of the frame and clear of the title's text box.
    checkers = [0.86, 0.6, 0.14, 0.3]
    for name, blur in (("plain", None), ("blurred", [checkers])):
        data = script_data(scene_count=1, image="", video="vuon.mp4", seconds=1.5)
        if blur:
            data["title"]["video_blur"] = blur
        options = RenderOptions(clip_blur=bool(blur))
        output = render_video(load_script(write_script(tmp_path, data)), tmp_path / f"{name}.mp4", options=options)
        renders[name] = [extract_frame(output, second, tmp_path / f"{name}-{second}.png") for second in (0.2, 1.2)]
    # Inside the checkerboard's box, and testsrc2's small squares at the top right, outside it.
    inside, outside = (940, 1170, 1070, 1690), (930, 10, 1080, 150)
    for plain, blurred in zip(renders["plain"], renders["blurred"]):
        assert sharpness(blurred, inside) < sharpness(plain, inside) / 2
        assert sharpness(blurred, outside) == pytest.approx(sharpness(plain, outside), rel=0.05)
