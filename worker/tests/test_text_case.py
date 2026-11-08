""" "Dạng chữ": the text is drawn as typed ("keep") or in capitals ("upper", the original template)."""

import unicodedata

import pytest
from conftest import script_data

from reels_render.errors import InputError
from reels_render.layers import Layer, render_layer
from reels_render.markup import Run, cased, parse_scene_text
from reels_render.options import DEFAULT_OPTIONS, TEXT_CASES, RenderOptions
from reels_render.render import scene_lines
from reels_render.script import parse_script

TEXT = "Cá nhỏ ăn cả xương\nGiàu *canxi*, rẻ"


def test_kept_text_is_drawn_as_typed_marked_words_included():
    assert parse_scene_text(TEXT, case="keep") == [
        [Run("Cá nhỏ ăn cả xương", False)],
        [Run("Giàu ", False), Run("canxi", True), Run(", rẻ", False)],
    ]


def test_capitals_stay_the_default_and_match_the_original_template():
    assert DEFAULT_OPTIONS.text_case == "upper" and DEFAULT_OPTIONS.title_text_case == "upper"
    assert parse_scene_text(TEXT) == parse_scene_text(TEXT, case="upper")
    assert cased(parse_scene_text(TEXT, case="keep"), "upper") == [
        [Run("CÁ NHỎ ĂN CẢ XƯƠNG", False)],
        [Run("GIÀU ", False), Run("CANXI", True), Run(", RẺ", False)],
    ]


def test_kept_text_is_still_nfc():
    lines = parse_scene_text(unicodedata.normalize("NFD", "tuổi xương"), case="keep")
    assert lines == [[Run("tuổi xương", False)]]
    assert unicodedata.is_normalized("NFC", lines[0][0].text)


@pytest.mark.parametrize("field", ["text_case", "title_text_case"])
def test_unknown_cases_are_refused(field):
    assert TEXT_CASES == ("upper", "keep")
    with pytest.raises(InputError, match=field):
        RenderOptions(**{field: "lower"})


@pytest.mark.parametrize(
    ("text_case", "title_text_case", "title_text", "scene_text"),
    [
        ("upper", "upper", "5 MÓN", "CÁ NHỎ"),
        ("keep", "upper", "5 MÓN", "Cá nhỏ"),
        ("upper", "keep", "5 món", "CÁ NHỎ"),
        ("keep", "keep", "5 món", "Cá nhỏ"),
    ],
)
def test_the_title_and_the_scenes_each_follow_their_own_case(
    tmp_path, text_case, title_text_case, title_text, scene_text
):
    script = parse_script(script_data(), base_dir=tmp_path)
    options = RenderOptions(text_case=text_case, title_text_case=title_text_case)
    title, first = scene_lines(script, options)
    assert title[0][0].text == title_text and title[1][0] == Run(title[1][0].text, True)
    assert first[0][0].text == scene_text and first[1][1] == Run("canxi" if text_case == "keep" else "CANXI", True)


def test_a_scene_without_text_has_no_lines(tmp_path):
    data = script_data()
    data["scenes"][0]["text"] = ""
    script = parse_script(data, base_dir=tmp_path)
    assert scene_lines(script, RenderOptions(text_case="keep"))[1] == []


def test_a_text_layer_follows_the_case_it_is_given():
    layer = Layer(kind="text", text="Giàu *canxi*")
    assert render_layer(layer).tobytes() == render_layer(layer, case="upper").tobytes()
    assert render_layer(layer, case="keep").tobytes() != render_layer(layer).tobytes()
