"""The text box's size: Lớn (the original template), Vừa or Nhỏ, for the content scenes and the title on their own."""

import pytest

from reels_render.errors import InputError
from reels_render.markup import parse_scene_text
from reels_render.options import RenderOptions
from reels_render.textbox import (
    SCENE_STYLE,
    TEXT_SIZES,
    TITLE_STYLE,
    TextFitError,
    box_style,
    layout_sized,
    layout_text,
)

LONG_TITLE = "NĂM LOẠI RAU MẦM DỄ TRỒNG NHẤT TẠI NHÀ CHO NGƯỜI MỚI BẮT ĐẦU TẬP LÀM VƯỜN TRÊN BAN CÔNG NHỎ XINH MỖI NGÀY"


def test_large_is_the_original_template_and_each_size_is_smaller_than_the_one_before():
    assert box_style("large", is_title=True) == TITLE_STYLE and box_style("large", is_title=False) == SCENE_STYLE
    for is_title in (True, False):
        sizes = [box_style(name, is_title) for name in ("large", "medium", "small")]
        assert [style.max_size for style in sizes] == sorted((style.max_size for style in sizes), reverse=True)
        assert [style.min_size for style in sizes] == sorted((style.min_size for style in sizes), reverse=True)
    assert all(item.label[0].isupper() for item in TEXT_SIZES.values())


def test_a_smaller_size_draws_a_smaller_box_and_fits_a_longer_title():
    lines = parse_scene_text("5 MÓN TỐT CHO\n*XƯƠNG KHỚP*")
    large, small = layout_text(lines, box_style("large", True)), layout_text(lines, box_style("small", True))
    assert small.font_size < large.font_size and small.height < large.height
    with pytest.raises(TextFitError):
        layout_text(parse_scene_text(LONG_TITLE), box_style("large", True))
    assert layout_text(parse_scene_text(LONG_TITLE), box_style("small", True)).font_size >= 44


def test_the_sizes_are_render_options_and_the_default_is_large():
    assert (RenderOptions().text_size, RenderOptions().title_text_size) == ("large", "large")
    for field in ("text_size", "title_text_size"):
        with pytest.raises(InputError, match=field):
            RenderOptions(**{field: "huge"})


def test_each_size_is_smaller_than_large_even_for_a_long_title_that_large_shrinks():
    """A long title already falls to a small font at Lớn; Vừa and Nhỏ must still come out smaller, not the same."""
    lines = parse_scene_text("5 LOẠI RAU MẦM DỄ TRỒNG\n*TẠI NHÀ* CHO NGƯỜI MỚI\nBẮT ĐẦU LÀM VƯỜN")
    fonts = [layout_sized(lines, size, is_title=True).font_size for size in ("large", "medium", "small")]
    assert fonts[0] > fonts[1] > fonts[2]
    short = parse_scene_text("Rau mầm cải")
    assert layout_sized(short, "large", is_title=False).font_size == SCENE_STYLE.max_size
    assert layout_sized(short, "medium", is_title=False).font_size == round(SCENE_STYLE.max_size * 0.82)
