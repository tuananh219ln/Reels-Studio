"""Channel logo: the badge made at upload, and its place on the finished video."""

import pytest
from conftest import extract_frame, make_image, needs_ffmpeg, scene, write_script
from PIL import Image

from reels_render.errors import InputError
from reels_render.logo import (
    BADGE_SIZE,
    CORNER_DIAMETER,
    TITLE_DIAMETER,
    badge_canvas,
    corner_placement,
    make_badge,
    title_placement,
)
from reels_render.options import RenderOptions
from reels_render.render import render_video
from reels_render.script import load_script


def red_badge(tmp_path):
    source = make_image(tmp_path / "logo.png", (300, 200), (220, 20, 20))
    make_badge(source, tmp_path / "badge.png")
    return tmp_path / "badge.png"


def test_the_badge_is_a_round_logo_with_a_white_ring_and_a_soft_shadow(tmp_path):
    badge = Image.open(red_badge(tmp_path))
    canvas = badge_canvas()
    assert badge.size == (canvas, canvas) and badge.mode == "RGBA"
    middle = badge.getpixel((canvas // 2, canvas // 2))
    assert middle[:3] == (220, 20, 20) and middle[3] == 255
    # The ring: white, just inside the circle's outer edge (pad 61 px, ring 26 px).
    ring = badge.getpixel((canvas // 2, 61 + 10))
    assert ring[:3] == (255, 255, 255) and ring[3] == 255
    # The shadow shows under the ring, dark and partly clear; the canvas corner is clear.
    below = badge.getpixel((canvas // 2, canvas - 61 + 6))
    assert 0 < below[3] < 255 and below[0] < 60
    assert badge.getpixel((0, 0))[3] == 0


def test_the_ring_is_five_percent_of_the_logo_at_both_sizes():
    for diameter, ring in ((TITLE_DIAMETER, 8.5), (CORNER_DIAMETER, 6.0)):
        assert abs(diameter * 0.05 - ring) < 1e-9


def test_a_corner_badge_fills_x_888_to_1020_and_y_200_to_332():
    placement = corner_placement()
    pad = round(BADGE_SIZE * 0.12) * CORNER_DIAMETER / BADGE_SIZE
    outer = CORNER_DIAMETER * 1.1
    # Whole pixels: within one of the spec's 888–1020 by 200–332.
    assert abs(placement.x + pad - 888) <= 1 and abs(placement.x + pad + outer - 1020) <= 1
    assert abs(placement.y + pad - 200) <= 1 and abs(placement.y + pad + outer - 332) <= 1


def test_a_title_badge_is_centred_on_the_boxs_top_edge_or_hangs_from_200():
    boxed = title_placement(500)
    assert boxed.x * 2 + boxed.width == 1080 and boxed.y + boxed.width / 2 == 500
    bare = title_placement(None)
    pad = round(BADGE_SIZE * 0.12) * TITLE_DIAMETER / BADGE_SIZE
    assert round(bare.y + pad) == 200


@needs_ffmpeg
def test_the_logo_sits_on_the_title_then_in_the_corner_and_stays_off_without_one(tmp_path):
    make_image(tmp_path / "a.jpg", (1080, 1920), (30, 30, 200))
    badge = red_badge(tmp_path)
    data = {"title": scene("TIÊU ĐỀ", 2), "scenes": [scene("", 2)], "logo": badge.name}
    script = load_script(write_script(tmp_path, data))
    assert script.logo == badge.resolve()
    output = render_video(script, tmp_path / "out.mp4", options=RenderOptions(logo=True))

    title_frame = extract_frame(output, 0.5, tmp_path / "t.png")
    # The title's box is centred in the frame; its logo hangs over the box's top edge, centred across.
    reds = [y for y in range(190, 900, 4) if _is_red(title_frame.getpixel((540, y)))]
    assert reds, "the title's logo is drawn"
    corner_frame = extract_frame(output, 3.0, tmp_path / "c.png")
    assert _is_red(corner_frame.getpixel((954, 266)))  # the centre of the corner badge
    assert not _is_red(corner_frame.getpixel((540, 266)))  # nothing on the title's place any more

    plain = render_video(load_script(write_script(tmp_path, data | {"logo": None})), tmp_path / "plain.mp4")
    assert not _is_red(extract_frame(plain, 3.0, tmp_path / "p.png").getpixel((954, 266)))


def test_a_missing_logo_file_is_refused(tmp_path):
    data = {"title": scene("A", 1), "scenes": [scene("B", 1)], "logo": "nope.png"}
    with pytest.raises(InputError, match="logo"):
        load_script(write_script(tmp_path, data))


def _is_red(pixel):
    return pixel[0] > 180 and pixel[1] < 80 and pixel[2] < 80
