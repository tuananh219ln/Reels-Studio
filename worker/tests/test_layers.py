"""Text, sticker and photo layers: drawn once as a picture, laid over a scene for their own seconds, with an entrance."""

import pytest
from conftest import extract_frame, make_image, needs_ffmpeg, scene, script_data, write_script
from PIL import Image

from reels_render.errors import InputError
from reels_render.graph import InsetInput, LayerInput, build_filter_graph
from reels_render.layers import (
    ANIMATIONS,
    HALF,
    SIZES,
    STICKERS,
    TEXT_STYLES,
    Layer,
    half_height,
    half_y,
    layer_corner,
    render_layer,
)
from reels_render.render import render_video
from reels_render.script import load_script
from reels_render.timeline import build_timeline


def test_a_text_layer_is_drawn_in_its_style_and_size():
    small = render_layer(Layer(kind="text", text="Giàu *canxi*", size="small", style="yellow"))
    large = render_layer(Layer(kind="text", text="Giàu *canxi*", size="large", style="yellow"))
    assert small.mode == "RGBA" and small.width < large.width and small.height < large.height
    # A box style fills its corners' inside; the outlined style leaves the box transparent.
    assert small.getpixel((small.width // 2, 4))[3] == 255
    outline = render_layer(Layer(kind="text", text="Giàu canxi", style="outline"))
    assert outline.getpixel((2, 2))[3] == 0


@pytest.mark.parametrize("name", list(STICKERS))
def test_every_sticker_is_drawn_at_each_size(name):
    sides = [max(render_layer(Layer(kind="sticker", sticker=name, size=size)).size) for size in SIZES]
    assert sides == sorted(sides) and sides[0] >= 120 and sides[-1] <= 420
    image = render_layer(Layer(kind="sticker", sticker=name))
    assert image.getbbox() is not None, "something is drawn"


def test_every_preset_has_a_vietnamese_label():
    for presets in (STICKERS, TEXT_STYLES, SIZES, ANIMATIONS):
        assert all(item.label and item.label[0].isupper() for item in presets.values())


def test_a_layer_stays_inside_the_frame():
    assert layer_corner(200, 100, (540, 960)) == (440, 910)
    assert layer_corner(200, 100, (10, 1900)) == (0, 1820)
    assert layer_corner(200, 100, (1075, 5)) == (880, 0)


def test_the_layers_go_on_after_the_captions_each_for_its_own_seconds():
    layers = [
        LayerInput(image=None, x=100, y=200, start=1.5, end=3.0, animation="fade"),
        LayerInput(image=None, x=300, y=400, start=2.0, end=2.5, animation="slide_left"),
    ]
    graph = build_filter_graph([(0, 0), (0, 0)], build_timeline([2, 2]), None, layers=layers)
    # Inputs: 2 pictures and 2 boxes, then the layers.
    assert "[4:v]format=rgba,fade=t=in:st=1.500:d=0.300:alpha=1[l0]" in graph
    assert "overlay=x=100:y=200:enable='between(t,1.500,3.000)'" in graph
    assert "[5:v]format=rgba,fade=t=in:st=2.000:d=0.300:alpha=1[l1]" in graph
    assert "x='300-(300+w)*(1-min(1,max(0,(t-2.000)/0.300)))'" in graph
    assert graph.index("[l0]overlay") < graph.index("[l1]overlay") < graph.index("[vout]")


def test_a_layer_without_an_entrance_just_appears():
    layers = [LayerInput(image=None, x=0, y=0, start=1, end=2, animation="none")]
    graph = build_filter_graph([(0, 0), (0, 0)], build_timeline([2, 2]), None, layers=layers)
    assert "[4:v]format=rgba[l0]" in graph and "fade=t=in" not in graph


def test_the_script_takes_a_scenes_layers_and_refuses_bad_ones(tmp_path):
    make_image(tmp_path / "a.jpg", (1080, 1920))
    data = script_data(1)
    data["scenes"][0]["layers"] = [
        {"kind": "text", "text": "Mới", "start": 0.5, "seconds": 1, "x": 540, "y": 600, "animation": "pop"},
        {"kind": "sticker", "sticker": "heart", "start": 0, "seconds": 2, "x": 200, "y": 300, "size": "large"},
    ]
    with pytest.raises(InputError, match='Cảnh 1, lớp 1: "animation"'):
        load_script(write_script(tmp_path, data))
    data["scenes"][0]["layers"][0]["animation"] = "fade"
    first, second = load_script(write_script(tmp_path, data)).scenes[0].layers
    assert (first.kind, first.text, first.style, first.size, first.animation) == (
        "text",
        "Mới",
        "outline",
        "medium",
        "fade",
    )
    assert (second.sticker, second.size, second.start, second.seconds) == ("heart", "large", 0, 2)
    for bad in ({"kind": "gif"}, {"kind": "sticker", "sticker": "unicorn"}, {"kind": "text", "text": " "}):
        data["scenes"][0]["layers"] = [{"start": 0, "seconds": 1, "x": 1, "y": 1} | bad]
        with pytest.raises(InputError, match="Cảnh 1, lớp 1"):
            load_script(write_script(tmp_path, data))


@needs_ffmpeg
def test_a_sticker_shows_only_during_its_own_seconds(tmp_path):
    make_image(tmp_path / "a.jpg", (1080, 1920), (40, 80, 200))
    heart = {"kind": "sticker", "sticker": "heart", "start": 1, "seconds": 1, "x": 540, "y": 960, "size": "large"}
    data = {"title": scene("TIÊU ĐỀ", 1), "scenes": [scene("", 3, layers=[heart])]}
    output = render_video(load_script(write_script(tmp_path, data)), tmp_path / "out.mp4")
    # The scene starts at 1 s: the heart (red) is on from 2 s to 3 s, in the frame's middle.
    before = extract_frame(output, 1.5, tmp_path / "before.png").getpixel((540, 960))
    during = extract_frame(output, 2.5, tmp_path / "during.png").getpixel((540, 960))
    after = extract_frame(output, 3.6, tmp_path / "after.png").getpixel((540, 960))
    assert during[0] > 180 and during[2] < 100
    assert before[2] > 150 and after[2] > 150


# --- "Ảnh chèn nửa khung": a photo layer of style "half" ---


@pytest.mark.parametrize("size", [(1600, 1200), (900, 1600)], ids=["landscape-4:3", "portrait-9:16"])
def test_an_inset_photo_is_a_rounded_square_narrower_than_the_frame(tmp_path, size):
    photo = make_image(tmp_path / "photo.jpg", size, (40, 160, 60))
    picture = render_layer(Layer(kind="photo", style=HALF, image=photo, y=1613))
    # 32% by default: 614 px on each side, so the backdrop shows on both sides of it.
    assert picture.size == (half_height(), half_height()) == (614, 614)
    # No border: the photo reaches each edge; only the rounded corners are see-through.
    for point in ((307, 0), (0, 307), (613, 307), (307, 613), (307, 307)):
        red, green, blue, alpha = picture.getpixel(point)
        assert alpha == 255 and green > 120 and red < 90, point
    for corner in ((0, 0), (613, 0), (0, 613), (613, 613)):
        assert picture.getpixel(corner)[3] == 0, corner


def test_an_inset_photos_size_is_30_to_45_percent_of_the_frames_height():
    assert (half_height(10), half_height(30), half_height(32), half_height(45), half_height(80)) == (
        576,
        576,
        614,
        864,
        864,
    )
    # Even the largest stays narrower than the 1080-pixel frame.
    assert half_height(45) < 1080


def test_an_inset_photo_is_cut_in_the_middle_never_stretched(tmp_path):
    # A wide photo: left third red, middle green, right third blue; the square keeps the middle at its own scale.
    wide = Image.new("RGB", (1842, 614), (220, 30, 30))
    wide.paste((30, 200, 30), (614, 0, 1228, 614))
    wide.paste((30, 30, 220), (1228, 0, 1842, 614))
    wide.save(tmp_path / "wide.png")
    picture = render_layer(Layer(kind="photo", style=HALF, image=tmp_path / "wide.png", y=1613))
    # max(614 / 1842, 614 / 614) = 1: the middle 614 pixels are kept, all green.
    assert picture.getpixel((307, 300))[:3] == (30, 200, 30)
    assert picture.getpixel((5, 300))[1] > 150 and picture.getpixel((608, 300))[1] > 150


def test_an_inset_photo_is_kept_inside_the_frame_from_the_top_edge_to_the_bottom_edge():
    assert (half_y(0), half_y(307), half_y(960), half_y(1613), half_y(1919)) == (307, 307, 960, 1613, 1613)
    assert half_y(0, 45) == 432 and half_y(1919, 30) == 1632 and half_y(0, 38) == 365


def test_a_half_frame_photo_goes_under_its_scenes_text_box():
    inset = InsetInput(image=None, top=1306, start=0.2, end=3.2, left=233)
    graph = build_filter_graph([(0, 0), (0, 0)], build_timeline([2, 3]), None, insets=[(), (inset,)])
    # Inputs: 2 pictures and 2 boxes, then the inset; it goes over scene 1's picture, centred across, then its box.
    assert "[bg1][4:v]overlay=x=233:y=1306:enable='between(t,0.200,3.200)'[bg1i0]" in graph
    assert "[bg1i0][3:v]overlay=" in graph


def test_the_script_takes_a_half_frame_photo(tmp_path):
    make_image(tmp_path / "a.jpg", (1080, 1920))
    make_image(tmp_path / "p.jpg", (800, 600))
    data = script_data(1)
    data["scenes"][0]["layers"] = [{"kind": "photo", "style": "half", "image": "p.jpg", "x": 540, "y": 480}]
    (layer,) = load_script(write_script(tmp_path, data)).scenes[0].layers
    assert layer.half and layer.image == tmp_path / "p.jpg"


@needs_ffmpeg
def test_a_half_frame_photo_shows_for_its_seconds_over_the_top_half_on_a_slide_video(tmp_path):
    make_image(tmp_path / "a.jpg", (1080, 1920), (40, 80, 200))
    make_image(tmp_path / "p.jpg", (1600, 1200), (230, 40, 40))
    photo = {"kind": "photo", "style": "half", "image": "p.jpg", "start": 1, "seconds": 1, "x": 900, "y": 300}
    data = {"title": scene("TIÊU ĐỀ", 1), "scenes": [scene("", 3, layers=[photo])]}
    output = render_video(load_script(write_script(tmp_path, data)), tmp_path / "out.mp4")
    # The scene starts at 1 s: the photo (red, a 614 px square) shows from 2 s to 3 s, flush with the top edge and
    # centred across (x is always 540), with the picture behind it on both sides.
    during = extract_frame(output, 2.5, tmp_path / "during.png")
    top, bottom = during.getpixel((540, 300)), during.getpixel((540, 1400))
    side = during.getpixel((100, 300))
    assert top[0] > 180 and top[2] < 100 and bottom[2] > 150 and side[2] > 150
    for at in (1.5, 3.6):
        assert extract_frame(output, at, tmp_path / "other.png").getpixel((540, 480))[2] > 150
