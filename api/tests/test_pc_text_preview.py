"""The studio's previews and the thumbnail draw PC Shopee's tiers and "Cộng dồn" captions as the MP4 does."""

import io

from PIL import Image, ImageChops

from reels_api import frames
from reels_render.options import RenderOptions

BLUE = (30, 90, 160)
TIERS = RenderOptions(title_layout="three_tier", scene_text_layout="two_tier")


def _changed(frame: Image.Image, box: tuple[int, int, int, int]) -> bool:
    plain = Image.new("RGB", frame.size, BLUE)
    return max(high for _, high in ImageChops.difference(frame.crop(box), plain.crop(box)).getextrema()) > 60


def _photo() -> Image.Image:
    return Image.new("RGB", (1080, 1920), BLUE)


def test_the_title_preview_and_thumbnail_are_three_tiers_in_the_upper_part_with_no_box():
    text = "BLACK FRIDAY\n5 MÓN PC ĐÁNG SĂN\nGIẢM THẬT 100%"
    frame = frames.compose_frame(_photo(), text, True, TIERS)
    assert _changed(frame, (0, 200, 1080, 660))  # centred 22% down
    assert not _changed(frame, (0, 900, 1080, 1700))  # the old box sat in the middle
    thumbnail = Image.open(io.BytesIO(frames.thumbnail_bytes(_photo(), text, TIERS)))
    assert thumbnail.size == frames.THUMBNAIL_SIZE
    # Without the option the title is the original box in the middle of the frame.
    old = frames.compose_frame(_photo(), text, True)
    assert _changed(old, (0, 700, 1080, 1250))


def test_a_content_scene_is_two_tiers_in_the_lower_zone_or_the_upper_one_and_the_last_keeps_its_box():
    text = "3. *Logitech G304*\nkhông dây"
    lower = frames.compose_frame(_photo(), text, False, TIERS)
    assert _changed(lower, (0, 1130, 1080, 1480)) and not _changed(lower, (0, 200, 1080, 660))
    upper = frames.compose_frame(_photo(), text, False, TIERS, zone="top")
    assert _changed(upper, (0, 200, 1080, 660)) and not _changed(upper, (0, 1130, 1080, 1480))
    last = frames.compose_frame(_photo(), "DEAL HẤP DẪN\nMÌNH ĐỂ DƯỚI BÌNH LUẬN", False, TIERS, last=True)
    assert _changed(last, (0, 700, 1080, 1440))  # the call to action stays a box
    # A framed photo is laid out around the tiers' height, which is below the 15% of the frame the spec allows.
    height = frames.text_height(text, False, TIERS)
    assert height == frames.tier_box(text, False, TIERS, None, False, None)[0].height <= 0.15 * 1920 + 2 * 46


def test_cumulative_captions_replace_the_scene_text_with_the_first_phrase_drawn_still():
    options = RenderOptions(captions="cumulative", scene_text_layout="two_tier")
    narration = "Chuột *Logitech G304* không dây"
    frame = frames.compose_frame(_photo(), "3. *Logitech G304*", False, options, narration=narration)
    assert _changed(frame, (0, 1130, 1080, 1560))  # the phrase, from 62% down
    # A scene with nothing to read keeps its own text; the last scene keeps its box.
    silent = frames.compose_frame(_photo(), "3. *Logitech G304*", False, options)
    assert _changed(silent, (0, 1130, 1080, 1480))
    assert not frames.captioned(options, False, True, narration)
    assert not frames.captioned(RenderOptions(), False, False, narration)


def test_a_broken_mark_in_a_tiered_text_draws_nothing_instead_of_failing():
    frame = frames.compose_frame(_photo(), "3. *Logitech", False, TIERS)
    assert not _changed(frame, (0, 0, 1080, 1920))


# --- The group's own look: PC Shopee's fields belong to that group only ---


def test_pc_shopee_fields_and_cumulative_captions_are_kept_for_that_group_only():
    import pytest

    from reels_api import text_looks, video_options
    from reels_api.models import KnowledgeTopic

    pc, other = KnowledgeTopic(name="PC Shopee"), KnowledgeTopic(name="Sức khỏe")
    look = {"captions": "cumulative", "text_hold_sec": 3.5, "pc_style": "brand_navy", "scene_text_layout": "two_tier"}
    assert text_looks.clean_look(look, pc) == look
    with pytest.raises(video_options.OptionError, match="PC Shopee"):
        text_looks.clean_look({"text_hold_sec": 2.5}, other)
    with pytest.raises(video_options.OptionError, match="PC Shopee"):
        text_looks.clean_look({"captions": "cumulative"}, other)
    assert text_looks.clean_look({"captions": "word"}, other) == {"captions": "word"}  # an ordinary look is fine
    # Read back: another group's stored look drops them, the group's own keeps them.
    pc.text_look = other.text_look = look | {"text_style": "none"}
    assert text_looks.group_look(pc) == look | {"text_style": "none"}
    assert text_looks.group_look(other) == {"text_style": "none"}
    # The AI is never asked for them, and never writes them.
    assert "cumulative" not in text_looks.LOOK_RULES and "text_hold_sec" not in text_looks.LOOK_RULES
    assert text_looks.loose_look({"captions": "cumulative", "pc_style": "brand_navy", "text_size": "small"}) == {
        "text_size": "small"
    }


# --- The studio's player: the words of "Cộng dồn" come in over the scene ---


def test_the_player_gets_the_steps_with_their_seconds_and_places_and_no_sample_phrase_in_the_picture():
    steps = frames.cumulative_pictures("Chuột *Logitech G304* không dây", (), 2.0, 5.0, frozenset(), "neon_game", None)
    assert len(steps) >= 3
    starts = [step[0] for step in steps]
    assert (
        starts == sorted(starts) and starts[0] >= 0.2 and steps[-1][1] == 5.0
    )  # after the voice lead, to the scene's end
    for start, end, png, left, top, width, _height in steps:
        assert end > start and png.startswith(b"\x89PNG") and 0 <= left and left + width <= 1080 and top > 1100
    # The real seconds of ElevenLabs' words are used when they match the text.
    real = frames.cumulative_pictures(
        "một hai ba", (("một", 0.0, 0.5), ("hai", 0.6, 1.1), ("ba", 1.2, 1.7)), 2.0, 4.0, frozenset(), "neon_game", None
    )
    assert [round(step[0], 2) for step in real] == [0.2, 0.8, 1.4]
    # "live": the player lays the words itself, so the picture has the scene's text hidden and no phrase drawn.
    options = RenderOptions(captions="cumulative")
    live = frames.compose_frame(_photo(), "3. *Logitech*", False, options, narration="Chuột *Logitech*", live=True)
    assert not _changed(live, (0, 0, 1080, 1920))


def test_the_preview_route_keeps_its_arguments_in_order_for_the_assistants_connection():
    import inspect

    from reels_api import routes_videos

    # mcp_server calls scene_preview(scene_id, me, db, storage) by position: `live` must stay after them.
    assert list(inspect.signature(routes_videos.scene_preview).parameters)[:4] == ["scene_id", "me", "db", "storage"]


def test_the_title_layout_and_look_are_part_of_what_the_thumbnail_is_drawn_with():
    from reels_api import video_options
    from reels_api.models import Video

    before = video_options.text_look(Video(options=video_options.DEFAULTS))
    for change in ({"title_layout": "three_tier"}, {"pc_title_style": "neon_game"}):
        assert video_options.text_look(Video(options=video_options.DEFAULTS | change)) != before, change
