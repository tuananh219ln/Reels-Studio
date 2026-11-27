"""Phụ đề "Cộng dồn": phrases, steps, the Neon look, and what a render shows."""

from pathlib import Path

import pytest
from conftest import extract_frame, make_image, make_tone, needs_ffmpeg, script_data, write_script
from PIL import Image, ImageChops

from reels_render.captions import Word
from reels_render.cumulative import (
    KEY_SIZE,
    LEAD_SIZE,
    MAX_LINES,
    MAX_WORDS,
    TAIL_SIZE,
    chunks,
    estimate_words,
    known_words,
    plan_cumulative,
    render_cumulative,
)
from reels_render.options import RenderOptions
from reels_render.pc_text import PRESETS
from reels_render.render import render_video
from reels_render.script import load_script

TEXT = "Chuột *Logitech G304* không dây, bàn gọn hẳn. Giá chỉ *299 nghìn* thôi."


def test_words_share_the_narration_and_keep_the_marks():
    words = estimate_words(TEXT, 1.0, 6.0)
    assert words[0].start == pytest.approx(1.0) and words[-1].end == pytest.approx(7.0)
    assert all(a.end == pytest.approx(b.start) for a, b in zip(words, words[1:]))
    assert [word.text for word in words if word.key] == ["LOGITECH", "G304", "299", "NGHÌN"]
    assert words[0].text == "CHUỘT"  # always capitals


def test_marked_words_of_the_scene_text_stand_in_when_the_narration_has_no_marks():
    words = estimate_words("Chuột logitech g304 không dây", 0, 3, frozenset({"logitech", "g304"}))
    assert [word.key for word in words] == [False, True, True, False, False]


def test_phrases_end_at_punctuation_and_never_split_a_marked_run():
    phrases = chunks(estimate_words(TEXT, 0, 8))
    assert [" ".join(word.text for word in phrase) for phrase in phrases] == [
        "CHUỘT LOGITECH G304 KHÔNG DÂY,",
        "BÀN GỌN HẲN.",
        "GIÁ CHỈ 299 NGHÌN THÔI.",
    ]


def test_a_long_run_of_plain_words_is_cut_to_nine_words_and_three_lines():
    words = estimate_words(" ".join(["từ"] * 25), 0, 10)
    for phrase in chunks(words):
        assert len(phrase) <= MAX_WORDS
    long_words = estimate_words("một hai ba bốn năm sáu bảy tám chín mười", 0, 5)
    assert all(len(plan.lines) <= MAX_LINES for plan in plan_cumulative(long_words, 5))


def test_a_pause_in_the_voice_ends_the_phrase_and_a_long_one_clears_the_screen():
    words = known_words([Word("một", 0, 0.4), Word("hai", 0.45, 0.8), Word("ba", 1.5, 1.9), Word("bốn", 1.95, 2.3)])
    assert [len(phrase) for phrase in chunks(words)] == [2, 2]  # a 0.7 s pause
    steps = plan_cumulative(words, 3.0)
    assert steps[1].end == pytest.approx(0.8)  # cleared at the last word: the voice rests more than 0.6 s
    assert steps[-1].end == pytest.approx(3.0)  # the last phrase stays to the scene's end


def test_words_pile_up_in_the_order_said_and_the_last_phrase_ends_with_the_scene():
    steps = plan_cumulative(estimate_words(TEXT, 1.0, 6.0), 8.0)
    first = [[line.text for line in step.lines] for step in steps[:3]]
    assert first == [["CHUỘT"], ["CHUỘT", "LOGITECH G304"], ["CHUỘT", "LOGITECH G304", "KHÔNG"]]
    assert steps[-1].end == 8.0 and all(step.end <= 8.0 for step in steps)
    assert all(a.end <= b.start + 1e-9 for a, b in zip(steps, steps[1:]))  # one picture at a time


def test_lines_are_sized_lead_key_and_tail_or_all_medium_without_a_marked_word():
    lines = plan_cumulative(estimate_words("Chuột *Logitech G304* không dây", 0, 4), 4)[-1].lines
    assert [line.size for line in lines] == [LEAD_SIZE, KEY_SIZE, TAIL_SIZE]
    plain = plan_cumulative(estimate_words("Chuột không dây rất nhẹ", 0, 4), 4)[-1].lines
    assert {line.size for line in plain} == {TAIL_SIZE}


def test_the_neon_look_has_aqua_keywords_a_dark_outline_and_all_the_vietnamese_marks():
    steps = plan_cumulative(estimate_words("Ổ cứng *ĐÁNG SĂN* màn hình Ị Ự Ơ Ư", 0, 5), 5)
    picture, corner = render_cumulative(next(step for step in steps if any(line.key for line in step.lines)).lines)
    assert picture.mode == "RGBA" and 0 <= corner[0] and corner[1] > 1920 * 0.58
    colours = {pixel[:3] for pixel in picture.get_flattened_data() if pixel[3] == 255}
    assert (0x5E, 0xF2, 0xD0) in colours and (255, 255, 255) in colours and (0x0B, 0x1E, 0x2B) in colours


@needs_ffmpeg
def test_a_render_shows_the_words_so_far_and_no_scene_text_in_a_content_scene(tmp_path):
    make_image(tmp_path / "a.jpg", (1080, 1920), (30, 90, 160))
    make_tone(tmp_path / "voice.wav", 2.0)
    data = script_data(scene_count=2, image="a.jpg")
    for item in data["scenes"]:
        item["seconds"] = 3
    data["scenes"][0].update(text="CHỮ CẢNH *bị tắt*", voice="voice.wav", voice_text="Chuột *Logitech* không dây")
    plain = Image.new("RGB", (1080, 1920), (30, 90, 160))
    script = load_script(write_script(tmp_path, data))
    output = render_video(script, tmp_path / "out.mp4", options=RenderOptions(captions="cumulative"))

    def changed(second: float, box: tuple[int, int, int, int]) -> bool:
        frame = extract_frame(output, second, tmp_path / f"f{second}.png")
        difference = ImageChops.difference(frame.crop(box), plain.crop(box))
        return max(high for _, high in difference.getextrema()) > 60

    # Scene 1 runs from 1 s to 3.4 s. Its narration is on the lower zone (62–78%); nothing in the old text place.
    assert changed(3.0, (0, 1190, 1080, 1500))
    assert not changed(3.0, (0, 780, 1080, 1140))
    # The last scene is the call to action: its own text stays and no caption is drawn there.
    assert changed(5.6, (0, 700, 1080, 1250))


@needs_ffmpeg
def test_a_scene_with_no_narration_keeps_its_own_text_under_cumulative(tmp_path):
    make_image(tmp_path / "a.jpg", (1080, 1920), (30, 90, 160))
    data = script_data(scene_count=2, image="a.jpg")
    for item in data["scenes"]:
        item["seconds"] = 3
    plain = Image.new("RGB", (1080, 1920), (30, 90, 160))
    script = load_script(write_script(tmp_path, data))
    output = render_video(script, tmp_path / "out.mp4", options=RenderOptions(captions="cumulative"))
    frame = extract_frame(output, 2.0, tmp_path / "f.png")  # scene 1: nothing to say, so nothing replaces its text
    box = (0, 700, 1080, 1250)
    difference = ImageChops.difference(frame.crop(box), plain.crop(box))
    assert max(high for _, high in difference.getextrema()) > 60


def test_real_word_seconds_replace_the_estimate_when_the_words_match():
    from reels_render.cumulative import voiced_words

    spoken = [Word("Chuột", 0.0, 0.4), Word("Logitech", 0.5, 1.2), Word("nhẹ", 1.3, 1.6)]
    words = voiced_words("Chuột *Logitech* nhẹ", spoken, 10.0)
    assert [(w.text, w.start, w.end, w.key) for w in words] == [
        ("CHUỘT", 10.0, 10.4, False),
        ("LOGITECH", 10.5, 11.2, True),
        ("NHẸ", 10.0 + 1.3, 10.0 + 1.6, False),
    ]
    # Another number of words (the text was edited after the narration): no real seconds, the caller estimates.
    assert voiced_words("Chuột Logitech nhẹ thôi", spoken, 10.0) == []


@pytest.mark.parametrize(
    ("style", "key", "plain", "outline"),
    [
        ("neon_game", (0x5E, 0xF2, 0xD0), (255, 255, 255), (0x0B, 0x1E, 0x2B)),
        ("brand_navy", (0xFF, 0xC8, 0x16), (0xFE, 0xFF, 0xFA), (0x10, 0x19, 0x5E)),
        ("halftone_purple", (0x11, 0x11, 0x14), (0xED, 0xED, 0xF2), (0x1A, 0x15, 0x30)),
    ],
)
def test_each_look_draws_its_own_colours_with_every_vietnamese_mark(style, key, plain, outline):
    from reels_render.cumulative import Line

    lines = (Line("ĐÁNG SĂN Ổ CỨNG", 100, True), Line("MÀN HÌNH Ị Ự Ơ Ư", 72, False))
    picture, corner = render_cumulative(lines, style)
    solid = {pixel[:3] for pixel in picture.get_flattened_data() if pixel[3] == 255}
    near = lambda colour: any(max(abs(a - b) for a, b in zip(colour, pixel)) <= 12 for pixel in solid)  # noqa: E731
    assert near(outline) and near(plain)
    if style != "brand_navy":
        assert near(key)
    else:
        assert any(pixel[0] > 240 and 170 < pixel[1] < 225 and pixel[2] < 60 for pixel in solid)  # the key's gold
    assert picture.width <= 1080 and corner[1] > 1100


# --- Tiers: the title in three tiers, a content scene's text in two ---


def test_the_title_splits_into_small_main_sub_and_a_label():
    from reels_render.markup import parse_scene_text
    from reels_render.tiers import parse_title

    lines = parse_scene_text("black friday\n5 món PC đáng săn\nGiảm thật 100%\n[[-50%]]")
    tiers = parse_title(lines)
    assert (tiers.small, tiers.main, tiers.sub, tiers.label) == (
        "BLACK FRIDAY",
        "5 MÓN PC ĐÁNG SĂN",
        "GIẢM THẬT 100%",
        "-50%",
    )
    two = parse_title(parse_scene_text("5 món\nGiảm thật"))
    assert (two.small, two.main, two.sub) == ("", "5 MÓN", "GIẢM THẬT")
    assert parse_title(parse_scene_text("Một dòng")).main == "MỘT DÒNG"


def test_a_scene_text_splits_into_a_number_the_main_marked_words_and_a_sub():
    from reels_render.markup import parse_scene_text
    from reels_render.tiers import parse_scene

    tiers = parse_scene(parse_scene_text("3. *Logitech G304*\nkhông dây"))
    assert (tiers.number, tiers.main, tiers.sub) == ("3", "LOGITECH G304", "KHÔNG DÂY")
    assert parse_scene(parse_scene_text("Chuột nhẹ\nbàn gọn")).main == "CHUỘT NHẸ"  # nothing marked: the first line


def test_the_tiers_stay_inside_their_share_of_the_frame_even_when_a_line_is_too_long():
    from reels_render.markup import parse_scene_text
    from reels_render.pc_text import PAD
    from reels_render.tiers import parse_scene, parse_title, render_scene, render_title, title_problems

    title = parse_title(
        parse_scene_text("BLACK FRIDAY SIÊU HỘI\n5 MÓN PC ĐÁNG SĂN NHẤT NĂM NAY\nGIẢM THẬT 100% CHO MỌI NGƯỜI")
    )
    assert title_problems(title)  # over 14 characters: the page warns
    picture = render_title(title)
    assert picture.width <= 1080 and (picture.height - 2 * PAD) / 1920 <= 0.22
    scene = render_scene(parse_scene(parse_scene_text("3. *Logitech G304 không dây bàn gọn*\nrất nhẹ")))
    assert scene.width <= 1080 and (scene.height - 2 * PAD) / 1920 <= 0.15


@needs_ffmpeg
def test_a_render_draws_the_title_in_tiers_and_a_scene_text_in_two_with_no_box(tmp_path):
    make_image(tmp_path / "a.jpg", (1080, 1920), (30, 90, 160))
    data = script_data(scene_count=2, image="a.jpg", text="BLACK FRIDAY\n5 MÓN PC\nGIẢM THẬT")
    data["title"]["seconds"] = 2
    data["scenes"][0].update(text="3. *Logitech G304*\nkhông dây", seconds=2)
    plain = Image.new("RGB", (1080, 1920), (30, 90, 160))
    script = load_script(write_script(tmp_path, data))
    options = RenderOptions(title_layout="three_tier", scene_text_layout="two_tier")
    output = render_video(script, tmp_path / "out.mp4", options=options)

    def region(second: float, box: tuple[int, int, int, int]) -> Image.Image:
        frame = extract_frame(output, second, tmp_path / f"f{second}.png")
        return ImageChops.difference(frame.crop(box), plain.crop(box))

    # The title sits about 22% down (a block of at most 22% of the frame), with no yellow box behind it.
    title = region(1.0, (0, 200, 1080, 660))
    assert max(high for _, high in title.getextrema()) > 60
    assert max(high for _, high in region(1.0, (0, 900, 1080, 1700)).getextrema()) < 40
    # The content scene's text sits in the lower zone, the title's place is clear.
    assert max(high for _, high in region(3.0, (0, 1130, 1080, 1480)).getextrema()) > 60
    assert max(high for _, high in region(3.0, (0, 200, 1080, 660)).getextrema()) < 40


def test_a_scene_set_to_top_puts_the_captions_and_tiers_in_the_upper_zone():
    from reels_render.cumulative import Line
    from reels_render.markup import parse_scene_text
    from reels_render.render import tier_corner
    from reels_render.script import parse_script
    from reels_render.tiers import parse_scene, render_scene

    lines = (Line("CHUỘT", 72, False),)
    _, lower = render_cumulative(lines)
    _, upper = render_cumulative(lines, zone="top")
    assert lower[1] > 1920 * 0.55 and upper[1] < 1920 * 0.2  # 62–78% and 14–30%
    picture = render_scene(parse_scene(parse_scene_text("3. *Logitech*\nkhông dây")))
    assert tier_corner(picture, 1, None, "top")[1] < 1920 * 0.2 < 1920 * 0.55 < tier_corner(picture, 1, None)[1]
    assert tier_corner(picture, 1, (100, 100), "top")[0] == 0  # a place a member moved it to wins, kept on the frame
    assert (
        parse_script(
            {"title": {"text": "A", "seconds": 1}, "scenes": [{"text": "B", "seconds": 1, "text_zone": "top"}]},
            Path("."),
        )
        .scenes[0]
        .text_zone
        == "top"
    )


def test_with_two_lines_the_first_is_the_product_whatever_is_marked_and_the_rest_the_description():
    from reels_render.markup import parse_scene_text
    from reels_render.tiers import parse_scene

    # The team's convention: the name on the first line, the benefit on the second with its keyword marked.
    tiers = parse_scene(parse_scene_text("3. Chuột Logitech G304\n*Không dây, bàn gọn hẳn*"))
    assert (tiers.number, tiers.main, tiers.sub) == ("3", "CHUỘT LOGITECH G304", "KHÔNG DÂY, BÀN GỌN HẲN")
    # The marked benefit in the middle of the second line changes nothing; a third line joins the sub.
    more = parse_scene(parse_scene_text("Chuột G304\nrất *nhẹ* và êm\nbàn gọn"))
    assert (more.main, more.sub) == ("CHUỘT G304", "RẤT NHẸ VÀ ÊM BÀN GỌN")
    # One line: marked words are the name, the rest the description; nothing marked is all name.
    one = parse_scene(parse_scene_text("*Logitech G304* không dây"))
    assert (one.main, one.sub) == ("LOGITECH G304", "KHÔNG DÂY")
    assert parse_scene(parse_scene_text("Chuột nhẹ")).sub == ""


def test_captions_start_only_after_the_text_has_gone():
    from reels_render.captions import Cue, after_hold

    cues = [Cue(1.0, 2.0, [["một"]], None), Cue(2.5, 3.5, [["hai"]], 0), Cue(3.5, 4.5, [["ba"]], 0)]
    kept = after_hold(cues, 3.0)  # a text held 2.5 s + 0.25 s fade, 0.25 s into a scene starting at 0
    assert [(cue.start, cue.end) for cue in kept] == [(3.0, 3.5), (3.5, 4.5)]
    assert after_hold(cues, 0.0) == cues


@needs_ffmpeg
def test_a_scene_with_a_held_text_shows_no_caption_while_its_text_is_up(tmp_path):
    make_image(tmp_path / "a.jpg", (1080, 1920), (30, 90, 160))
    make_tone(tmp_path / "voice.wav", 3.0)
    data = script_data(scene_count=2, image="a.jpg")
    data["scenes"][0].update(
        text="3. Chuột G304\n*Không dây*",
        seconds=4,
        voice="voice.wav",
        voice_text="Chuột không dây rất nhẹ",
        text_hold_sec=1.5,
    )
    data["scenes"][1]["seconds"] = 2
    plain = Image.new("RGB", (1080, 1920), (30, 90, 160))
    script = load_script(write_script(tmp_path, data))
    options = RenderOptions(captions="word", scene_text_layout="two_tier", text_hold=True)
    output = render_video(script, tmp_path / "out.mp4", options=options)

    def region(second: float, box: tuple[int, int, int, int]) -> bool:
        frame = extract_frame(output, second, tmp_path / f"f{second}.png")
        difference = ImageChops.difference(frame.crop(box), plain.crop(box))
        return max(high for _, high in difference.getextrema()) > 60

    # Scene 1 runs 1–5 s: its text is up until 1 + 1.5 + 0.25 = 2.75 s, the captions (bottom on y = 1440) start then.
    assert region(1.9, (0, 1130, 1080, 1480)) and not region(1.9, (0, 1000, 1080, 1130))
    assert not region(1.9, (0, 1000, 1080, 1100))  # no caption yet
    assert region(3.5, (0, 1330, 1080, 1440))  # the caption, once the text has gone
    assert not region(3.5, (0, 1000, 1080, 1300)) and not region(3.5, (0, 1445, 1080, 1700))


def test_a_title_written_on_one_line_is_cut_at_its_punctuation_into_three_tiers():
    from reels_render.markup import parse_scene_text
    from reels_render.tiers import parse_title

    tiers = parse_title(parse_scene_text("BLACK FRIDAY: 5 MÓN PC ĐÁNG SĂN, XEM TRƯỚC KHI MUA"))
    assert (tiers.small, tiers.main, tiers.sub) == ("BLACK FRIDAY", "5 MÓN PC ĐÁNG SĂN", "XEM TRƯỚC KHI MUA")
    # Two parts: a short one before a longer one is the small line, else main and sub.
    short = parse_title(parse_scene_text("Black Friday: 5 món PC đáng săn"))
    assert (short.small, short.main, short.sub) == ("BLACK FRIDAY", "5 MÓN PC ĐÁNG SĂN", "")
    long = parse_title(parse_scene_text("5 món PC đáng săn nhất năm nay, xem trước khi mua"))
    assert (long.small, long.main, long.sub) == ("", "5 MÓN PC ĐÁNG SĂN NHẤT NĂM NAY", "XEM TRƯỚC KHI MUA")
    # No punctuation: all the main line. A label line still comes out of the text.
    plain = parse_title(parse_scene_text("5 món PC đáng săn\n[[-50%]]"))
    assert (plain.small, plain.main, plain.sub, plain.label) == ("", "5 MÓN PC ĐÁNG SĂN", "", "-50%")


def test_a_caption_of_a_compact_text_scene_sits_on_the_safe_zone_floor_unless_the_text_stays_under_it():
    from reels_render.render import tier_caption_y
    from reels_render.textbox import CAPTION_GAP, SCENE_BOX_BOTTOM

    # The text goes before the captions start (a hold): the caption's bottom is y = 1440, wherever the text was dragged.
    assert tier_caption_y(1190, 1400, 100, text_stays=False) == SCENE_BOX_BOTTOM - 100
    assert tier_caption_y(1300, 1440, 100, text_stays=False) == SCENE_BOX_BOTTOM - 100
    # The text stays the whole scene: a caption that would land on it goes over it, as before.
    assert tier_caption_y(1190, 1400, 100, text_stays=True) == 1190 - CAPTION_GAP - 100
    assert tier_caption_y(1300, 1440, 100, text_stays=True) == 1300 - CAPTION_GAP - 100
    # Text dragged high does not meet the caption: it stays on the floor.
    assert tier_caption_y(300, 500, 100, text_stays=True) == SCENE_BOX_BOTTOM - 100


@needs_ffmpeg
def test_the_last_scene_is_in_tiers_and_its_captions_sit_on_the_floor_too(tmp_path):
    make_image(tmp_path / "a.jpg", (1080, 1920), (30, 90, 160))
    make_tone(tmp_path / "voice.wav", 3.0)
    data = script_data(scene_count=1, image="a.jpg")
    data["title"]["seconds"] = 1
    data["scenes"][0].update(
        text="DEAL HẤP DẪN\nMÌNH ĐỂ DƯỚI BÌNH LUẬN",
        seconds=4,
        voice="voice.wav",
        voice_text="Túi tiền là của bạn",
        text_position=[540, 520],
    )
    plain = Image.new("RGB", (1080, 1920), (30, 90, 160))
    script = load_script(write_script(tmp_path, data))
    options = RenderOptions(captions="word", scene_text_layout="two_tier")
    output = render_video(script, tmp_path / "out.mp4", options=options)
    frame = extract_frame(output, 2.5, tmp_path / "f.png")
    floor = (0, 1330, 1080, 1440)
    difference = ImageChops.difference(frame.crop(floor), plain.crop(floor))
    assert max(high for _, high in difference.getextrema()) > 60


@needs_ffmpeg
def test_the_last_scene_text_is_in_tiers_with_no_box_like_the_others(tmp_path):
    make_image(tmp_path / "a.jpg", (1080, 1920), (30, 90, 160))
    data = script_data(scene_count=1, image="a.jpg")
    data["title"]["seconds"] = 1
    data["scenes"][0].update(text="DEAL HẤP DẪN\nMÌNH ĐỂ DƯỚI BÌNH LUẬN", seconds=3)
    script = load_script(write_script(tmp_path, data))
    output = render_video(script, tmp_path / "out.mp4", options=RenderOptions(scene_text_layout="two_tier"))
    frame = extract_frame(output, 2.5, tmp_path / "f.png")
    plain = Image.new("RGB", (1080, 1920), (30, 90, 160))
    # No yellow box across the lower third (it spans the box width and 700+ px); the tiers sit in the 62–78% zone.
    wide = (0, 700, 1080, 1130)
    difference = ImageChops.difference(frame.crop(wide), plain.crop(wide))
    assert max(high for _, high in difference.getextrema()) < 30
    zone = (0, 1190, 1080, 1500)
    difference = ImageChops.difference(frame.crop(zone), plain.crop(zone))
    assert max(high for _, high in difference.getextrema()) > 60


@pytest.mark.parametrize("style", PRESETS)
def test_each_title_preset_draws_vietnamese_marks_within_the_frame(style):
    from reels_render.tiers import TitleTiers, render_title

    picture = render_title(TitleTiers("BLACK FRIDAY", "GIÁ RẺ BẤT NGỜ", "MÁY TÍNH ĐỒ HOẠ", ""), style)
    assert picture.getbbox() is not None
    assert picture.width <= 1080


def test_the_hollow_price_preset_leaves_its_letters_clear_and_audiowide_falls_back_for_vietnamese():
    from reels_render.pc_text import FONTS, line_style, render_line

    hollow = line_style("neon_outline_price", True, 1)
    assert hollow.fill is None
    picture = render_line("III", 120, hollow)
    centre = picture.getpixel((picture.width // 2, picture.height // 2))
    assert centre[3] < 255  # the middle of a stem is not painted
    teal = line_style("neon_tech_teal", True, 1)
    assert teal.font == FONTS / "Audiowide-Regular.ttf" and teal.vi is not None
    assert render_line("GIÁ RẺ", 100, teal).getbbox() is not None  # drawn with Saira, not missing boxes


def test_a_preset_title_keeps_its_line_proportions_when_one_line_is_too_wide():
    from reels_render.tiers import TitleTiers, render_title

    short = render_title(TitleTiers("PC", "GIÁ RẺ", "MUA NGAY", ""), "gold_metal")
    wide = render_title(TitleTiers("PC", "GIÁ RẺ BẤT NGỜ CHƯA TỪNG CÓ HÔM NAY", "MUA NGAY", ""), "gold_metal")
    assert wide.width <= 1080 and wide.height < short.height  # the whole block got smaller, not only the wide line


def test_the_esports_price_draws_its_prefix_small_and_raised():
    from reels_render.tiers import TitleTiers, render_title

    plain = render_title(TitleTiers("GAMING", "PC", "PHP 14,999", ""), "esports_blue")
    raised = render_title(TitleTiers("GAMING", "PC", "^PHP 14,999", ""), "esports_blue")
    assert raised.getbbox() is not None and raised.width <= 1080
    assert raised.size != plain.size  # a different picture, not the prefix as plain text


def test_the_title_effects_filter_only_the_title_scene_and_only_when_on():
    from reels_render.graph import build_filter_graph
    from reels_render.timeline import build_timeline

    timeline = build_timeline([2, 3])
    on = build_filter_graph(
        [(0, 0)] * 2, timeline, None, options=RenderOptions(pc_title_style="grunge_rainbow", title_effects=True)
    )
    assert "rgbashift" in on and "vignette" in on and on.count("rgbashift") == 1
    assert on.index("rgbashift") < on.index("[v0]")
    off = build_filter_graph([(0, 0)] * 2, timeline, None, options=RenderOptions(pc_title_style="grunge_rainbow"))
    other = build_filter_graph(
        [(0, 0)] * 2, timeline, None, options=RenderOptions(pc_title_style="gold_metal", title_effects=True)
    )
    assert "rgbashift" not in off and "rgbashift" not in other


@needs_ffmpeg
def test_the_title_effects_chain_is_a_valid_ffmpeg_filter(tmp_path):
    import subprocess

    from reels_render.ffmpeg import find_tools
    from reels_render.pc_text import FRAME_EFFECTS

    out = tmp_path / "frame.png"
    subprocess.run(
        [find_tools().ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=gray:s=1080x1920:d=1", "-vf",
         f"{FRAME_EFFECTS['grunge_rainbow']},format=yuv420p", "-frames:v", "1", str(out)],
        check=True, capture_output=True,
    )  # fmt: skip
    assert Image.open(out).size == (1080, 1920)


def test_a_preset_wraps_a_line_that_would_shrink_too_far_and_gold_has_sparkles_only_when_on():
    from reels_render.tiers import TitleTiers, render_title

    one = render_title(TitleTiers("", "GIÁ RẺ", "MUA NGAY", ""), "gold_metal", effects=False)
    long = render_title(
        TitleTiers("", "GIÁ RẺ BẤT NGỜ CHƯA TỪNG CÓ TRONG NĂM NAY", "MUA NGAY", ""), "gold_metal", effects=False
    )
    assert long.width <= 1080 and long.height > 0.8 * one.height  # wrapped in two, not shrunk to a sliver
    on = render_title(TitleTiers("", "GIÁ RẺ", "MUA NGAY", ""), "gold_metal", effects=True)
    assert on.size == one.size and on.tobytes() != one.tobytes()  # the stars are inside the same picture
    assert (
        render_title(TitleTiers("", "GIÁ RẺ", "MUA NGAY", ""), "esports_blue", effects=True).size
        == render_title(TitleTiers("", "GIÁ RẺ", "MUA NGAY", ""), "esports_blue", effects=False).size
    )
