import pytest

from reels_render.markup import parse_scene_text
from reels_render.textbox import (
    FRAME_HEIGHT,
    FRAME_WIDTH,
    MAX_BOX_WIDTH,
    SCENE_BOX_BOTTOM,
    SCENE_STYLE,
    TITLE_STYLE,
    TextFitError,
    layout_text,
    render_box,
    scene_box_position,
    title_box_position,
)

YELLOW = (0xFF, 0xD6, 0x0A)


def layout(text, style=SCENE_STYLE):
    return layout_text(parse_scene_text(text), style)


def is_yellow(pixel):
    return all(abs(a - b) <= 40 for a, b in zip(pixel[:3], YELLOW)) and pixel[3] == 255


def pixels(image):
    return [image.getpixel((x, y)) for y in range(image.height) for x in range(image.width)]


def is_red(pixel):
    r, g, b, a = pixel
    return a == 255 and r > 180 and g < 150 and b < 80


def is_dark(pixel):
    return pixel[3] == 255 and pixel[0] < 160


# Layout


def test_agreed_box_geometry():
    assert MAX_BOX_WIDTH == 960
    assert (TITLE_STYLE.max_size, TITLE_STYLE.min_size, TITLE_STYLE.max_lines) == (96, 64, 5)
    assert (SCENE_STYLE.max_size, SCENE_STYLE.min_size, SCENE_STYLE.max_lines) == (84, 60, 3)


def test_text_that_only_fits_near_minimum_size_is_accepted():
    result = layout("Cá nhỏ ăn cả xương\nGiàu canxi, rẻ, dễ tìm, ăn ngon mỗi ngày")
    assert result.font_size <= 66
    assert len(result.lines) == 3
    assert result.width <= 960


def test_shrinking_reaches_the_exact_minimum_before_failing():
    # A word of 19 H fits only at 60px; one more H fits nowhere.
    assert layout("H" * 19).font_size == 60
    with pytest.raises(TextFitError):
        layout("H" * 20)
    assert layout("H" * 18, TITLE_STYLE).font_size == 64
    with pytest.raises(TextFitError):
        layout("H" * 19, TITLE_STYLE)


def test_short_text_keeps_full_size():
    result = layout("Cá nhỏ\nGiàu *canxi*")
    assert result.font_size == SCENE_STYLE.max_size
    assert len(result.lines) == 2


def test_long_text_shrinks_until_it_fits():
    result = layout("Cá nhỏ ăn cả xương\nGiàu canxi, rẻ, dễ tìm, ăn ngon")
    assert SCENE_STYLE.min_size <= result.font_size < SCENE_STYLE.max_size
    assert len(result.lines) <= SCENE_STYLE.max_lines
    assert result.width <= MAX_BOX_WIDTH


def test_text_needing_more_than_three_lines_at_minimum_fails():
    with pytest.raises(TextFitError, match="tối đa 3 dòng"):
        layout("Rau cải xanh nấu canh ngon\nCó canxi và vitamin K tốt cho xương")


def test_word_wider_than_box_at_minimum_fails():
    with pytest.raises(TextFitError, match="từ quá dài"):
        layout("X" * 40)


def test_title_allows_five_lines_but_not_six():
    assert len(layout("a\nb\nc\nd\ne", TITLE_STYLE).lines) == 5
    with pytest.raises(TextFitError, match="tối đa 5 dòng"):
        layout("a\nb\nc\nd\ne\nf", TITLE_STYLE)


def test_scene_box_bottom_sits_on_lower_third_line_and_is_centred():
    result = layout("Cá nhỏ\nGiàu *canxi*")
    x, y = scene_box_position(result.width, result.height)
    assert y + result.height == SCENE_BOX_BOTTOM
    assert abs((x + result.width / 2) - FRAME_WIDTH / 2) <= 1


def test_title_box_is_centred_in_frame():
    result = layout("5 món giúp\n*xương chắc khỏe*\nsau tuổi 50", TITLE_STYLE)
    x, y = title_box_position(result.width, result.height)
    assert abs((y + result.height / 2) - FRAME_HEIGHT / 2) <= 2
    assert abs((x + result.width / 2) - FRAME_WIDTH / 2) <= 1


# Pillow rendering


def test_box_png_is_transparent_outside_and_yellow_inside():
    image = render_box(layout("Cá nhỏ\nGiàu canxi"))
    assert image.mode == "RGBA"
    assert image.width <= MAX_BOX_WIDTH
    assert image.getpixel((0, 0))[3] == 0
    assert is_yellow(image.getpixel((5, image.height // 2)))
    assert not any(is_red(pixel) for pixel in pixels(image))


def test_markup_draws_red_pixels():
    image = render_box(layout("Giàu *canxi*"))
    assert any(is_red(pixel) for pixel in pixels(image))


@pytest.mark.parametrize("style", [SCENE_STYLE, TITLE_STYLE])
def test_stacked_diacritics_are_not_clipped_or_touching(style):
    # Line 1 red, line 2 black, so each line's ink can be told apart.
    image = render_box(layout("*ỔẶỖ*\nỔẶỖ", style))
    width, height = image.size
    rows = [[image.getpixel((x, y)) for x in range(width)] for y in range(height)]

    red_rows = [y for y, row in enumerate(rows) if any(is_red(p) for p in row)]
    dark_rows = [y for y, row in enumerate(rows) if any(is_dark(p) for p in row)]
    assert red_rows[0] > 0, "dấu dòng 1 chạm mép trên hộp"

    line1_bottom, line2_top = red_rows[-1], dark_rows[0]
    gap = rows[line1_bottom + 1 : line2_top]
    assert gap, "dòng 1 và dấu dòng 2 dính nhau"
    assert any(all(is_yellow(p) for p in row[30:-30]) for row in gap)


def test_a_moved_box_is_centred_on_its_point_and_kept_inside_the_safe_zone():
    from reels_render.textbox import SAFE_ZONE, place_box

    left, top, right, bottom = SAFE_ZONE
    # Without a point a box sits where the template puts it.
    assert place_box(400, 200, None, is_title=False) == scene_box_position(400, 200)
    assert place_box(400, 200, None, is_title=True) == title_box_position(400, 200)
    # A point inside the zone centres the box on it.
    assert place_box(400, 200, (500, 700), is_title=False) == (300, 600)
    # Past an edge, the box stops at that edge: clear of the top bar, the buttons and the caption area.
    assert place_box(400, 200, (1080, 0), is_title=False) == (right - 400, top)
    assert place_box(400, 200, (0, 1920), is_title=False) == (left, bottom - 200)
    # A box wider than the zone stays centred across the frame.
    assert place_box(MAX_BOX_WIDTH, 200, (900, 700), is_title=False)[0] == (FRAME_WIDTH - MAX_BOX_WIDTH) // 2
    # The title moves only up and down, so the thumbnail stays centred.
    assert place_box(400, 200, (100, 500), is_title=True) == ((FRAME_WIDTH - 400) // 2, 400)


def test_captions_go_under_a_box_moved_to_the_top():
    from reels_render.textbox import CAPTION_GAP, SAFE_ZONE, caption_y

    assert caption_y(1200, 1400, 100) == 1100
    # Above a box near the top the captions would run under the top bar: they go below the box instead.
    assert caption_y(SAFE_ZONE[1] + 50, 600, 100) == 600 + CAPTION_GAP
