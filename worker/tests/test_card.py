"""'Thẻ': a screenshot card kept whole over the scene's picture, hung from its top edge; and a card laid part by part."""

import pytest
from conftest import extract_frame, make_image, needs_ffmpeg, scene, write_script
from PIL import Image

from reels_render.errors import InputError
from reels_render.layers import (
    CARD,
    CARD_MAX_HEIGHT,
    Layer,
    card_corner,
    card_size,
    card_width,
    render_layer,
)
from reels_render.render import render_video
from reels_render.script import load_script


def test_a_card_keeps_its_picture_whole_at_its_width():
    # A tall Threads card, 1000 × 1400: at 90% of the frame (972 px) it is 1361 px tall, never cut or stretched.
    assert card_width() == 972
    assert card_size(1000, 1400) == (972, 1361)
    # At the full width it would be 1512 px tall: brought down to the room, a little narrower.
    assert card_size(1000, 1400, 100) == (1071, CARD_MAX_HEIGHT)


def test_a_card_taller_than_the_room_is_scaled_down_narrower():
    wide, tall = card_size(1000, 3000)
    assert tall == CARD_MAX_HEIGHT and wide == 500


def test_a_card_hangs_from_its_top_edge_centred_across():
    assert card_corner(972, 1000, 220) == (54, 220)
    # Never past the bottom edge: a card too low comes up.
    assert card_corner(972, 1000, 1500) == (54, 920)
    assert card_corner(972, 1000, -5) == (54, 0)


def test_a_card_keeps_its_own_transparency(tmp_path):
    picture = Image.new("RGBA", (500, 800), (255, 255, 255, 255))
    picture.paste((0, 0, 0, 0), (0, 400, 500, 800))
    picture.save(tmp_path / "card.png")
    drawn = render_layer(Layer(kind="photo", style=CARD, image=tmp_path / "card.png", height=90))
    assert drawn.size == card_size(500, 800)
    assert drawn.getpixel((drawn.width // 2, 50))[3] == 255
    assert drawn.getpixel((drawn.width // 2, drawn.height - 50))[3] == 0


def test_the_script_takes_a_card_and_its_width(tmp_path):
    make_image(tmp_path / "a.jpg", (1080, 1920))
    make_image(tmp_path / "c.png", (1000, 1400))
    card = {"kind": "photo", "style": "card", "image": "c.png", "y": 220, "height": 90}
    data = {"title": scene("TIÊU ĐỀ", 1), "scenes": [scene("", 2, layers=[card])]}
    (layer,) = load_script(write_script(tmp_path, data)).scenes[0].layers
    assert layer.card and layer.inset and layer.height == 90 and layer.y == 220
    data["scenes"][0]["layers"][0]["height"] = 30
    with pytest.raises(InputError):
        load_script(write_script(tmp_path, data))


@needs_ffmpeg
def test_a_card_shows_over_a_slide_videos_picture_from_its_top_edge(tmp_path):
    make_image(tmp_path / "a.jpg", (1080, 1920), (40, 80, 200))
    make_image(tmp_path / "c.png", (1000, 1000), (240, 240, 240))
    card = {"kind": "photo", "style": "card", "image": "c.png", "y": 300, "height": 90, "seconds": 60}
    data = {"title": scene("TIÊU ĐỀ", 1), "scenes": [scene("", 2, layers=[card])]}
    output = render_video(load_script(write_script(tmp_path, data)), tmp_path / "out.mp4")
    frame = extract_frame(output, 2.0, tmp_path / "frame.png")
    # 972 px wide and tall from y 300: white inside, the blue picture above it and at its sides.
    inside, above, side = frame.getpixel((540, 800)), frame.getpixel((540, 200)), frame.getpixel((20, 800))
    assert min(inside) > 200
    assert above[2] > 150 and above[0] < 100 and side[2] > 150 and side[0] < 100


@needs_ffmpeg
def test_a_card_laid_part_by_part_shows_a_part_only_from_its_start(tmp_path):
    # The render job lays a card shown part by part as one card per part, the rows below each part cleared.
    make_image(tmp_path / "a.jpg", (1080, 1920), (40, 80, 200))
    whole = Image.new("RGBA", (1000, 1000), (240, 240, 240, 255))
    whole.save(tmp_path / "part1.png")
    first = whole.copy()
    first.paste((0, 0, 0, 0), (0, 500, 1000, 1000))
    first.save(tmp_path / "part0.png")
    parts = [
        {"kind": "photo", "style": "card", "image": "part0.png", "y": 300, "height": 90, "start": 0, "seconds": 3},
        {"kind": "photo", "style": "card", "image": "part1.png", "y": 300, "height": 90, "start": 1.5, "seconds": 1.5},
    ]
    data = {"title": scene("TIÊU ĐỀ", 1), "scenes": [scene("", 3, layers=parts)]}
    output = render_video(load_script(write_script(tmp_path, data)), tmp_path / "out.mp4")
    # The scene starts at 1 s. The card is 972 px tall from y 300: its upper half ends near y 786.
    early = extract_frame(output, 1.8, tmp_path / "early.png")
    late = extract_frame(output, 3.2, tmp_path / "late.png")
    assert min(early.getpixel((540, 500))) > 200  # part 1 is in
    lower = early.getpixel((540, 1100))
    assert lower[2] > 150 and lower[0] < 100  # part 2 is not yet: the picture shows there, no faded card
    assert min(late.getpixel((540, 500))) > 200 and min(late.getpixel((540, 1100))) > 200  # both, part 1 where it was
