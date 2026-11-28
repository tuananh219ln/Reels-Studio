"""Channel logo: the badge made at upload, and its place on the finished video."""

import pytest
from conftest import extract_frame, make_image, needs_ffmpeg, scene, write_script
from PIL import Image

from reels_render.errors import InputError
from reels_render.logo import BADGE_SIZE, PAD, RING, badge_canvas, make_badge, placement
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


def ring_of(where):
    """The white ring's left, top, right and bottom for a badge laid as `where`."""
    scale = where.width / badge_canvas()
    pad, ring = round(BADGE_SIZE * PAD) * scale, (BADGE_SIZE + 2 * round(BADGE_SIZE * RING)) * scale
    return where.x + pad, where.y + pad, where.x + pad + ring, where.y + pad + ring


@pytest.mark.parametrize(
    ("position", "size", "expected"),
    [(None, None, (895, 160, 1015, 280)), ((100, 900), 200, (100, 900, 300, 1100))],
)
def test_the_ring_fills_the_specs_box_or_the_videos_own(position, size, expected):
    # Whole pixels: within one of each edge.
    assert all(abs(got - want) <= 1 for got, want in zip(ring_of(placement(position=position, size=size)), expected))


@needs_ffmpeg
def test_the_logo_is_on_the_content_scenes_only_and_off_without_one(tmp_path):
    make_image(tmp_path / "a.jpg", (1080, 1920), (30, 30, 200))
    badge = red_badge(tmp_path)
    data = {"title": scene("TIÊU ĐỀ", 2), "scenes": [scene("", 2)], "logo": badge.name}
    script = load_script(write_script(tmp_path, data))
    assert script.logo == badge.resolve()
    output = render_video(script, tmp_path / "out.mp4", options=RenderOptions(logo=True))

    title_frame = extract_frame(output, 0.5, tmp_path / "t.png")
    # The title scene (the cover) has no logo anywhere.
    assert not any(_is_red(title_frame.getpixel((x, y))) for x in range(0, 1080, 6) for y in range(0, 1920, 12))
    content = extract_frame(output, 3.0, tmp_path / "c.png")
    assert _is_red(content.getpixel((955, 220)))  # the middle of the logo's place
    assert not _is_red(content.getpixel((815, 725)))  # where it used to be

    plain = render_video(load_script(write_script(tmp_path, data | {"logo": None})), tmp_path / "plain.mp4")
    assert not _is_red(extract_frame(plain, 3.0, tmp_path / "p.png").getpixel((955, 220)))


def test_a_missing_logo_file_is_refused(tmp_path):
    data = {"title": scene("A", 1), "scenes": [scene("B", 1)], "logo": "nope.png"}
    with pytest.raises(InputError, match="logo"):
        load_script(write_script(tmp_path, data))


def _is_red(pixel):
    return pixel[0] > 180 and pixel[1] < 80 and pixel[2] < 80
