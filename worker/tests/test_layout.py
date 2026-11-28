"""Where text, captions and the logo go (docs/decisions/2026-11-28-safe-layout.md)."""

import pytest

from reels_render.captions import plan_captions
from reels_render.cumulative import Line, render_cumulative
from reels_render.layout import CAPTION_GAP, PROFILES, Profile, caption_top, logo_box, place_box
from reels_render.markup import parse_scene_text
from reels_render.options import RenderOptions
from reels_render.pc_text import PAD
from reels_render.render import tier_corner, tier_picture
from reels_render.textbox import FRAME_HEIGHT, FRAME_WIDTH, layout_sized, render_caption

BALANCED, UNIVERSAL = PROFILES["balanced"], PROFILES["universal"]
EVERY = pytest.mark.parametrize("profile", [BALANCED, UNIVERSAL], ids=["balanced", "universal"])
LONG = "Năm món đồ công nghệ\nnên mua ngay"


def test_the_two_profiles_hold_the_specs_numbers():
    assert BALANCED == Profile(BALANCED.label, 290, 65, 1015, 1530, 192, 750, 660, 130)
    assert UNIVERSAL == Profile(UNIVERSAL.label, 290, 65, 888, 1248, 192, 750, 660, 130)
    assert BALANCED.subtitle_width == UNIVERSAL.subtitle_width == 696
    assert RenderOptions().layout_profile == "balanced"


@pytest.mark.parametrize(("height", "centre_y"), [(120, 350), (260, 420), (350, 465)])
def test_a_text_nobody_placed_starts_290_down_whatever_its_height(height, centre_y):
    """The spec's table: the box's centre is 290 + half its height, for the title and a scene alike."""
    for is_title in (True, False):
        x, y = place_box(810, height, None, is_title)
        assert (x, y) == ((FRAME_WIDTH - 810) // 2, 290)
        assert y + height // 2 == centre_y


@EVERY
@pytest.mark.parametrize("is_title", [True, False])
def test_a_dragged_text_stays_inside_the_profiles_edges(profile, is_title):
    for centre in [(0, 0), (1080, 1920), (540, 100), (5, 1000), (1075, 1700)]:
        x, y = place_box(600, 200, centre, is_title, profile)
        assert profile.text_left <= x and x + 600 <= profile.text_right
        assert profile.text_top_min <= y and y + 200 <= profile.subtitle_bottom


def test_a_dragged_text_is_centred_on_its_point_and_the_title_moves_only_up_and_down():
    assert place_box(400, 200, (500, 700), is_title=False) == (300, 600)
    assert place_box(400, 200, (100, 500), is_title=True) == ((FRAME_WIDTH - 400) // 2, 400)


def test_a_wide_title_moves_left_of_the_middle_when_the_buttons_column_asks_for_it():
    x, _ = place_box(810, 260, None, True, UNIVERSAL)
    assert x == UNIVERSAL.text_right - 810  # centred on 540 would end at 945, past 888


def test_a_box_too_tall_for_the_room_keeps_its_top_in_the_zone():
    assert place_box(400, 1500, (540, 960), False, UNIVERSAL)[1] == 290


def test_the_compact_texts_clear_margin_may_leave_the_edges_but_what_is_drawn_does_not():
    x, y = place_box(600, 200, (0, 0), False, BALANCED, inset=40)
    assert (x + 40, y + 40) == (BALANCED.text_left, BALANCED.text_top_min)


@EVERY
@pytest.mark.parametrize("is_title", [True, False])
@pytest.mark.parametrize("size", ["large", "medium", "small"])
def test_a_text_box_is_never_wider_than_the_profiles_room(profile, is_title, size):
    layout = layout_sized(parse_scene_text(LONG), size, is_title, "be_vietnam", profile.text_width)
    assert layout.width <= profile.text_width


@EVERY
@pytest.mark.parametrize("zone", [None, "bottom", "top"])
def test_the_compact_text_keeps_inside_the_edges(profile, zone):
    options = RenderOptions(
        title_layout="three_tier",
        scene_text_layout="two_tier",
        layout_profile=next(name for name, value in PROFILES.items() if value == profile),
    )
    lines = parse_scene_text("3. MÀN HÌNH CONG ĐỒ HOẠ SIÊU RỘNG\nnét căng cả ngày dài\n[[-50%]]")
    for index in (0, 1):
        picture = tier_picture(lines, index, 3, options)
        x, y = tier_corner(picture, index, None, zone, profile)
        assert profile.text_left <= x + PAD and x + picture.width - PAD <= profile.text_right
        assert profile.text_top_min <= y + PAD and y + picture.height - PAD <= profile.subtitle_bottom
        low = index == 1 and zone == "bottom"
        assert (y + PAD == profile.text_top_min) is not low


@EVERY
def test_captions_end_on_the_floor_and_stay_in_the_middle_696_px(profile):
    cues = plan_captions(LONG, 0.0, 8.0, "phrase", profile.subtitle_width)
    assert cues
    for cue in cues:
        picture = render_caption(cue.lines, cue.lit)
        assert picture.width <= 696
        assert caption_top(picture.height, profile) + picture.height == profile.subtitle_bottom


def test_a_caption_goes_over_a_text_that_is_still_there_and_would_be_under_it():
    # The text near the top never meets the captions.
    assert caption_top(100, BALANCED, (290, 550)) == 1430
    # Dragged low and still on screen: the caption sits just over it.
    assert caption_top(100, BALANCED, (1300, 1500)) == 1300 - CAPTION_GAP - 100
    # Gone by the time the captions start: they take the floor.
    assert caption_top(100, BALANCED, (1300, 1500), text_stays=False) == 1430
    # No room over it either: the floor.
    assert caption_top(100, BALANCED, (300, 1500)) == 1430


@EVERY
def test_the_logo_defaults_to_the_specs_place_and_is_kept_inside_the_edges(profile):
    assert logo_box(profile) == (750, 660, 130)
    for position in [(0, 0), (1080, 1920)]:
        x, y, size = logo_box(profile, position, 200)
        assert profile.text_left <= x and x + size <= profile.text_right
        assert profile.text_top_min <= y and y + size <= profile.subtitle_bottom


@EVERY
@pytest.mark.parametrize("zone", [None, "top"])
def test_cumulative_captions_keep_between_the_top_and_the_floor_and_clear_of_the_buttons(profile, zone):
    lines = (Line("MỘT HAI BA BỐN", 58, False), Line("LOGITECH G304", 100, True), Line("NĂM SÁU BẢY", 72, False))
    picture, (x, y) = render_cumulative(lines, "neon_game", zone, profile)
    assert profile.text_top_min <= y + PAD and y + picture.height - PAD <= profile.subtitle_bottom
    assert picture.width - 2 * PAD <= profile.subtitle_width
    assert abs(x + picture.width / 2 - FRAME_WIDTH / 2) <= 1
    if zone is None and profile == BALANCED:
        assert y + PAD == round(FRAME_HEIGHT * 0.62)  # where they have always started


@pytest.mark.parametrize(
    "options",
    [{"layout_profile": "shorts"}, {"logo_position": [1, 2, 3]}, {"logo_position": [1.5, 2]}, {"logo_size": "big"}],
)
def test_a_bad_profile_or_logo_place_is_refused(options):
    from reels_render.errors import InputError

    with pytest.raises(InputError):
        RenderOptions(**options)


def test_a_logo_place_read_from_a_render_machines_manifest_is_kept_as_a_pair():
    assert RenderOptions(logo_position=[100, 700]).logo_position == (100, 700)
