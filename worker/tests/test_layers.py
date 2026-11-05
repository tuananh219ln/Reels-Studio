"""Text and sticker layers: drawn once as a picture, laid over a scene for their own seconds, with an entrance."""

import pytest
from conftest import extract_frame, make_image, needs_ffmpeg, scene, script_data, write_script

from reels_render.errors import InputError
from reels_render.graph import LayerInput, build_filter_graph
from reels_render.layers import ANIMATIONS, SIZES, STICKERS, TEXT_STYLES, Layer, layer_corner, render_layer
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
