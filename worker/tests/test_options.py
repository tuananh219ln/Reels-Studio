"""Per-video render presets: transitions, motion, text style, narration level, ducking and captions."""

from fractions import Fraction

import pytest
from conftest import extract_frame, make_image, make_tone, mean_volume, needs_ffmpeg, script_data, write_script
from PIL import ImageStat

from reels_render.captions import plan_captions
from reels_render.errors import InputError
from reels_render.ffmpeg import probe
from reels_render.graph import CaptionInput, build_filter_graph, zoom_expression
from reels_render.options import DEFAULT_OPTIONS, RenderOptions
from reels_render.render import render_video
from reels_render.script import load_script
from reels_render.textbox import (
    PALETTES,
    SCENE_STYLE,
    Palette,
    layout_text,
    palette_for,
    render_box,
    title_palette,
)
from reels_render.timeline import build_timeline

BOXES = [(0, 0), (0, 0), (0, 0)]


def test_the_defaults_are_the_original_template():
    assert DEFAULT_OPTIONS == RenderOptions("fade", "zoom_in", "medium", "yellow", "off", 1.0, False)
    timeline = build_timeline([2, 2, 2])
    graph = build_filter_graph(BOXES, timeline, None)
    assert graph == build_filter_graph(BOXES, timeline, None, options=RenderOptions())
    assert "xfade=transition=fade" in graph and "concat=n=3:v=1" not in graph
    assert zoom_expression(60) == "1+0.1200*on/59"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("transition", "wipe"),
        ("motion", "spin"),
        ("zoom", "huge"),
        ("text_style", "pink"),
        ("text_color", "pink"),
        ("title_style", "pink"),
        ("captions", "all"),
    ],
)
def test_unknown_presets_are_refused(field, value):
    with pytest.raises(InputError, match=field):
        RenderOptions(**{field: value})


@pytest.mark.parametrize("volume", [-0.1, 1.5, True])
def test_voice_volume_must_be_between_0_and_1(volume):
    with pytest.raises(InputError, match="Âm lượng giọng đọc"):
        RenderOptions(voice_volume=volume)


def test_a_hard_cut_joins_scenes_end_to_end_at_their_own_length():
    timeline = build_timeline([2, 3, 2])
    graph = build_filter_graph(BOXES, timeline, None, options=RenderOptions(transition="cut"))
    assert "xfade" not in graph and "[v0][v1][v2]concat=n=3:v=1:a=0[x0]" in graph
    # Each photo runs exactly its scene's frames, not the half-transition overlaps of a crossfade.
    assert ":d=60:" in graph and ":d=90:" in graph


def test_slide_uses_the_slide_transition():
    graph = build_filter_graph(BOXES, build_timeline([2, 2, 2]), None, options=RenderOptions(transition="slide"))
    assert graph.count("xfade=transition=slideleft") == 2


def test_motion_presets():
    assert zoom_expression(31, "zoom_out", 1.06) == "1.0600-0.0600*on/30"
    assert zoom_expression(31, "pan", 1.18) == "1.1800"
    assert zoom_expression(31, "static") == "1"
    graph = build_filter_graph(BOXES, build_timeline([2, 2, 2]), None, options=RenderOptions(motion="pan"))
    assert "x='(iw-iw/zoom)*on/" in graph


def test_voice_level_and_ducking_only_touch_the_audio_with_narration_and_music():
    timeline = build_timeline([2, 2, 2])
    options = RenderOptions(voice_volume=0.5, ducking=True)
    graph = build_filter_graph(BOXES, timeline, 0.25, [True, False, True], options=options)
    assert "[voice]volume=0.5000[voicelevel]" in graph
    assert "[bed][voicekey]sidechaincompress" in graph and "[ducked][voicemix]amerge" in graph
    # Without music there is nothing to duck.
    assert "sidechaincompress" not in build_filter_graph(BOXES, timeline, None, [True, False, True], options=options)


def test_captions_are_overlaid_on_the_joined_video_in_their_time():
    caption = CaptionInput(image=None, x=100, y=900, start=2.5, end=3.25)
    graph = build_filter_graph(BOXES, build_timeline([2, 2, 2]), 0.25, [True, False, False], captions=[caption])
    # Inputs: 3 photos + 3 boxes, music (6), one narration (7), then the caption (8).
    assert "[x2][8:v]overlay=x=100:y=900:enable='between(t,2.500,3.250)'[c0]" in graph
    assert "[c0]format=yuv420p[vout]" in graph


def test_palettes_colour_the_box_and_the_marked_words():
    from reels_render.markup import parse_scene_text

    layout = layout_text(parse_scene_text("Cá nhỏ\nGiàu *canxi*"), SCENE_STYLE)
    yellow = render_box(layout)
    dark = render_box(layout, PALETTES["dark"])
    corner = (layout.width // 2, 4)
    assert yellow.getpixel(corner)[:3] == (255, 214, 10)
    assert dark.getpixel(corner) == (17, 17, 17, 224)


def colours(image) -> set[tuple[int, int, int]]:
    """The solid colours drawn (anti-aliased edges left out)."""
    return {pixel[:3] for pixel in image.getdata() if pixel[3] == 255}


def test_no_box_draws_outlined_letters_on_a_clear_background():
    from reels_render.markup import parse_scene_text

    layout = layout_text(parse_scene_text("Cá nhỏ\nGiàu *canxi*"), SCENE_STYLE)
    plain = render_box(layout, palette_for("none"))
    assert plain.getpixel((layout.width // 2, 4))[3] == 0
    assert {(255, 255, 255), (0, 0, 0), (255, 214, 10)} <= colours(plain)
    # Black letters get a white outline and red marked words.
    black = render_box(layout, palette_for("none", "black"))
    assert {(17, 17, 17), (255, 255, 255), (225, 6, 0)} <= colours(black)


def test_a_text_colour_recolours_the_words_and_keeps_the_marked_words_apart():
    assert palette_for("yellow", "auto") == PALETTES["yellow"]
    assert palette_for("yellow", "red") == Palette("#FFD60A", "#E10600", "#111111")
    assert palette_for("dark", "yellow") == Palette((17, 17, 17, 224), "#FFD60A", "#FFFFFF")
    assert palette_for("red", "black").text == "#111111"
    # A colour faint on its box is drawn as chosen too (the page warns): the named colours are the hex ones.
    for style, colour, hex_colour in (("yellow", "white", "#FFFFFF"), ("dark", "black", "#111111")):
        assert palette_for(style, colour).text == hex_colour
        assert palette_for(style, colour) == palette_for(style, hex_colour)


def test_a_custom_text_colour_is_drawn_as_chosen_even_where_it_is_faint():
    # Members may pick any colour; the page warns about faint ones instead of refusing them.
    assert palette_for("yellow", "#FFFFFF") == Palette("#FFD60A", "#FFFFFF", "#E10600")
    assert palette_for("dark", "#1D4ED8").text == "#1D4ED8"
    # The marked words move off the text's own colour, to one still readable on the box.
    assert palette_for("yellow", "#E10600").accent == "#111111"
    assert palette_for("dark", "#FFD60A").accent == "#FFFFFF"


def test_a_custom_box_colour_keeps_the_styles_opacity_and_outlines_letters_without_a_box():
    assert palette_for("yellow", box_color="#16A34A").box == "#16A34A"
    assert palette_for("dark", box_color="#1D4ED8").box == (29, 78, 216, 224)
    assert palette_for("none", box_color="#E10600") == Palette(None, "#FFFFFF", "#FFD60A", "#E10600")
    # Red marked words would vanish into a red box: they take another colour that reads on it.
    assert palette_for("yellow", box_color="#E10600").accent == "#FFD60A"
    # Near-black letters without a box get a white outline, and marked words that read on it.
    assert palette_for("none", "#0A0A0A") == Palette(None, "#0A0A0A", "#E10600", "#FFFFFF")
    assert palette_for("none", "#1D4ED8") == Palette(None, "#1D4ED8", "#FFD60A", "#000000")


def test_a_custom_marked_word_colour_is_drawn_as_chosen():
    assert palette_for("yellow", accent_color="#1D4ED8").accent == "#1D4ED8"
    assert palette_for("none", "black", accent_color="#FF7A00") == Palette(None, "#111111", "#FF7A00", "#FFFFFF")
    assert title_palette("red", "auto", "same", "#16A34A", "#FFFFFF") == Palette("#16A34A", "#FFFFFF", "#FFFFFF")
    # The yellow title box stays the original whatever the scenes use.
    assert title_palette("red", "#1D4ED8", "yellow", "#16A34A", "#FFFFFF") == PALETTES["yellow"]


def test_colours_are_named_presets_or_six_digit_hex():
    RenderOptions(text_color="#1d4ed8", box_color="#FFFFFF", accent_color="auto")
    for name, value in (("text_color", "#12345"), ("box_color", "blue"), ("accent_color", "#GGGGGG")):
        with pytest.raises(InputError):
            RenderOptions(**{name: value})


def test_the_title_can_keep_the_yellow_box_while_the_scenes_use_outlined_letters():
    scenes = palette_for("none", "yellow")
    assert scenes == Palette(None, "#FFD60A", "#E10600", "#000000")
    assert title_palette("none", "yellow", "yellow") == PALETTES["yellow"]
    assert title_palette("none", "yellow", "same") == scenes


def yellow_pixels(image) -> int:
    return sum(r > 220 and g > 180 and b < 60 for r, g, b in image.convert("RGB").getdata())


@needs_ffmpeg
def test_a_yellow_title_box_renders_over_a_video_of_outlined_scenes(tmp_path):
    make_image(tmp_path / "a.jpg", (1000, 1600), (240, 200, 205))
    data = script_data(scene_count=1, image="a.jpg", seconds=2)
    data["scenes"][0].update(image="a.jpg", seconds=2)
    script = load_script(write_script(tmp_path, data))
    options = RenderOptions(text_style="none", text_color="yellow", title_style="yellow")
    output = render_video(script, tmp_path / "out.mp4", options=options)
    title = extract_frame(output, 0.0, tmp_path / "title.png")
    scene = extract_frame(output, 3.0, tmp_path / "scene.png")
    # The box fills its area with yellow; outlined letters only colour their strokes.
    assert yellow_pixels(title) > 2 * yellow_pixels(scene) > 0


def test_captions_split_into_short_phrases_timed_across_the_narration():
    cues = plan_captions("Cá nhỏ chiên giòn giàu canxi, tốt cho xương.", 1.0, 4.0, "phrase")
    assert [sum(len(line) for line in cue.lines) for cue in cues] == [4, 2, 3]
    assert cues[0].start == 1.0 and cues[-1].end == pytest.approx(5.0)
    assert all(a.end == pytest.approx(b.start) for a, b in zip(cues, cues[1:]))
    words = plan_captions("Cá nhỏ chiên giòn", 0.0, 2.0, "word")
    assert [cue.lit for cue in words] == [0, 1, 2, 3] and words[0].lines == [["Cá", "nhỏ", "chiên", "giòn"]]
    assert plan_captions("Cá nhỏ", 0, 2, "off") == [] and plan_captions("  ", 0, 2, "word") == []


@needs_ffmpeg
def test_every_preset_together_renders_a_playable_mp4(tmp_path):
    make_image(tmp_path / "a.jpg", (1000, 1600), (240, 200, 205))
    make_tone(tmp_path / "voice.wav", 1.6)
    make_tone(tmp_path / "music.wav", 3.0)
    data = script_data(scene_count=2, image="a.jpg", seconds=1.5)
    for item in data["scenes"]:
        item.update(image="a.jpg", seconds=2, voice="voice.wav", voice_text="Cá nhỏ chiên giòn giàu canxi")
    script = load_script(write_script(tmp_path, data))
    options = RenderOptions(
        transition="cut",
        motion="pan",
        zoom="strong",
        text_style="dark",
        captions="word",
        voice_volume=0.8,
        ducking=True,
    )
    output = render_video(script, tmp_path / "out.mp4", music=tmp_path / "music.wav", options=options)

    info = probe("ffprobe", output)
    video = next(stream for stream in info["streams"] if stream["codec_type"] == "video")
    assert Fraction(video["r_frame_rate"]) == 30
    # Title 1.5 s + two scenes lengthened to fit their 1.6 s narration (0.2 lead + 0.4 tail): 1.5 + 2.2 + 2.2.
    assert float(info["format"]["duration"]) == pytest.approx(5.9, abs=0.05)
    assert mean_volume(output, 2.0, 1.0) > -60
    # A caption shows above the dark text box while the first scene is narrated.
    frame = extract_frame(output, 2.2, tmp_path / "frame.png")
    band = frame.crop((90, 1000, 990, 1150))
    assert ImageStat.Stat(band.convert("L")).mean < ImageStat.Stat(frame.crop((90, 300, 990, 450)).convert("L")).mean


def test_auto_marked_words_stay_bright_on_a_custom_box():
    # Red would vanish into blue and black reads poorly on it: white is taken.
    assert palette_for("yellow", "#FFD60A", "#1D4ED8").accent == "#FFFFFF"
