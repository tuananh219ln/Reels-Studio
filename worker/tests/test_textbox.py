import pytest

from reels_render.layout import place_box
from reels_render.markup import parse_scene_text
from reels_render.textbox import (
    FRAME_HEIGHT,
    FRAME_WIDTH,
    MAX_BOX_WIDTH,
    PALETTES,
    SCENE_STYLE,
    SHADE_ALPHA,
    SHADE_FADE,
    TITLE_STYLE,
    TextFitError,
    layout_text,
    render_box,
    shade_alpha,
    shade_band,
    with_shade,
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
    assert MAX_BOX_WIDTH == 950  # between the text's side edges, 65 and 1015
    assert (TITLE_STYLE.max_size, TITLE_STYLE.min_size, TITLE_STYLE.max_lines) == (96, 64, 5)
    assert (SCENE_STYLE.max_size, SCENE_STYLE.min_size, SCENE_STYLE.max_lines) == (84, 60, 3)


def test_text_that_only_fits_near_minimum_size_is_accepted():
    result = layout("Cá nhỏ ăn cả xương\nGiàu canxi, rẻ, dễ tìm, ăn ngon mỗi ngày")
    assert result.font_size <= 66
    assert len(result.lines) == 3
    assert result.width <= 950


def test_shrinking_reaches_the_exact_minimum_before_failing():
    # A word of 19 H fits only at 60px; one more H fits nowhere.
    assert layout("H" * 19).font_size == 60
    with pytest.raises(TextFitError):
        layout("H" * 20)
    assert layout("H" * 17 + "II", TITLE_STYLE).font_size == 64
    with pytest.raises(TextFitError):
        layout("H" * 17 + "III", TITLE_STYLE)


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


def test_the_shade_is_45_percent_at_the_text_and_fades_out_either_side():
    assert SHADE_ALPHA == round(0.45 * 255)
    assert shade_alpha(600, 500, 900) == SHADE_ALPHA  # over the text
    assert shade_alpha(500, 500, 900) == shade_alpha(900, 500, 900) == SHADE_ALPHA  # at its edges
    above = [shade_alpha(500 - step, 500, 900) for step in range(0, SHADE_FADE + 1, 20)]
    assert above == sorted(above, reverse=True) and above[0] == SHADE_ALPHA and above[-1] == 0
    assert shade_alpha(500 - SHADE_FADE, 500, 900) == shade_alpha(900 + SHADE_FADE, 500, 900) == 0


def test_the_shade_band_spans_the_frame_width_and_is_cut_at_the_frame_edges():
    band, first = shade_band(100, 400)
    assert first == 0 and band.size == (FRAME_WIDTH, 400 + SHADE_FADE)
    assert band.getpixel((0, 250))[3] == band.getpixel((FRAME_WIDTH - 1, 250))[3] == SHADE_ALPHA
    assert band.getpixel((5, 5))[:3] == (0, 0, 0)
    band, first = shade_band(1500, 1900)
    assert first == 1500 - SHADE_FADE and first + band.height == FRAME_HEIGHT


def test_a_box_over_its_shade_is_one_picture_that_keeps_the_box_where_it_was():
    box = render_box(layout_text(parse_scene_text("Một hai ba"), SCENE_STYLE), PALETTES["yellow"])
    x, y = place_box(box.width, box.height, None, is_title=False)
    shaded, (left, top) = with_shade(box, x, y)
    assert left == 0 and shaded.width == FRAME_WIDTH and top == max(0, y - SHADE_FADE)
    # The box's own pixels are where they were, the band's alpha is round it, and the corner is plain shade.
    inside = (x + box.width // 2, y + box.height // 2)
    assert (
        shaded.getpixel((inside[0] - left, inside[1] - top))[:3] == box.getpixel((box.width // 2, box.height // 2))[:3]
    )
    assert shaded.getpixel((2, y - top))[3] == SHADE_ALPHA
