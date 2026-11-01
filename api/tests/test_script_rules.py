import unicodedata

import pytest

from reels_api.script_rules import SceneInput, banned_hits, check_script, count_words, text_problem

TITLE_TEXT = "5 MÓN GIÚP\n*XƯƠNG CHẮC KHỎE*"
SCENE_TEXT = "Cá nhỏ\nGiàu *canxi*"


def title(seconds=3.0, text=TITLE_TEXT, has_image=True):
    return SceneInput(id=0, is_title=True, text=text, seconds=seconds, has_image=has_image)


def scenes(count=5, seconds=4.0, text=SCENE_TEXT):
    return [SceneInput(id=n, is_title=False, text=text, seconds=seconds, has_image=True) for n in range(1, count + 1)]


def messages(issues, scene_id=None):
    return [issue.message for issue in issues if scene_id is None or issue.scene_id == scene_id]


def run(title_scene=None, content=None, posts=None, banned=()):
    return check_script(
        title_scene if title_scene is not None else title(),
        scenes() if content is None else content,
        posts or {},
        list(banned),
    )


def test_a_script_like_the_sample_passes_without_warnings():
    checks = run()
    assert checks.blocking == [] and checks.warnings == []


def test_words_ignore_markup_and_count_line_breaks_as_spaces():
    assert count_words("Cá nhỏ\nGiàu *canxi*, rẻ") == 5
    assert count_words("*  *") == 0


@pytest.mark.parametrize(("seconds", "blocked"), [(0.9, True), (1, False), (10, False), (10.1, True)])
def test_scene_seconds_bounds(seconds, blocked):
    content = scenes(4) + [SceneInput(9, False, SCENE_TEXT, seconds, True)]
    assert ("Số giây phải từ 1 đến 10" in messages(run(content=content).blocking, 9)) is blocked


@pytest.mark.parametrize(("seconds", "blocked"), [(0.9, True), (1, False), (10, False), (10.1, True)])
def test_title_scene_seconds_bounds(seconds, blocked):
    assert ("Số giây phải từ 1 đến 10" in messages(run(title(seconds)).blocking, 0)) is blocked


@pytest.mark.parametrize(("total", "blocked"), [(90, False), (91, True)])
def test_total_length_counts_the_title_scene(total, blocked):
    # 3-second title + 9 scenes: the title's seconds decide whether the total passes 90.
    per_scene = (total - 3) / 9
    checks = run(content=scenes(9, per_scene))
    assert any(issue.field == "total" for issue in checks.blocking) is blocked


@pytest.mark.parametrize(("count", "warned"), [(4, True), (5, False), (7, False), (8, True)])
def test_scene_count_warning(count, warned):
    checks = run(content=scenes(count, seconds=4))
    assert any(issue.field == "scenes" for issue in checks.warnings) is warned
    assert checks.blocking == []


@pytest.mark.parametrize(("total", "warned"), [(19, True), (20, False), (55, False), (56, True)])
def test_total_length_warning(total, warned):
    checks = run(content=scenes(7, (total - 3) / 7))
    assert any(issue.field == "total" for issue in checks.warnings) is warned
    assert checks.blocking == []


@pytest.mark.parametrize(("words", "warned"), [(10, False), (11, True)])
def test_scene_word_warning(words, warned):
    text = " ".join(["MÓN"] * words)
    checks = run(content=scenes(4) + [SceneInput(9, False, text, 4, True)])
    assert any("nên tối đa 10 từ" in message for message in messages(checks.warnings, 9)) is warned


@pytest.mark.parametrize(("words", "warned"), [(12, False), (13, True)])
def test_title_word_warning(words, warned):
    checks = run(title(text=" ".join(["ĂN"] * words)))
    assert any("nên tối đa 12 từ" in message for message in messages(checks.warnings, 0)) is warned


def test_no_content_scene_blocks():
    assert "Chưa có cảnh nội dung nào" in messages(run(content=[]).blocking)


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("Cá *nhỏ", "dấu * không đóng cặp"),
        ("Cá ** nhỏ", "có cặp ** rỗng"),
        ("Cá nhỏ\n\nGiàu canxi", "có dòng trống"),
        ("Cá nhỏ\n", "có dòng trống"),
        ("CÁ " * 60, "Chữ tràn hộp"),
    ],
)
def test_text_that_reels_render_refuses_blocks(text, reason):
    assert reason in text_problem(text, is_title=False)
    content = scenes(4) + [SceneInput(9, False, text, 4, True)]
    assert any(reason in message for message in messages(run(content=content).blocking, 9))


@pytest.mark.parametrize("text", ["", "   "])
def test_empty_text_is_a_scene_without_a_box_and_blocks_nothing(text):
    assert text_problem(text, is_title=True) is None
    assert run(title(text=text), scenes(4) + [SceneInput(9, False, text, 4, True)]).blocking == []


def test_missing_photo_blocks_for_title_and_scene():
    content = scenes(4) + [SceneInput(9, False, SCENE_TEXT, 4, False)]
    checks = run(title(has_image=False), content)
    assert "Cảnh chưa có ảnh" in messages(checks.blocking, 0)
    assert "Cảnh chưa có ảnh" in messages(checks.blocking, 9)


@pytest.mark.parametrize(
    ("has_image", "has_keywords", "warned"), [(False, False, True), (False, True, False), (True, False, False)]
)
def test_a_scene_without_photo_or_keywords_warns_on_the_keyword_field(has_image, has_keywords, warned):
    # A script that left out the keywords made "Tìm ảnh" fail with no hint at the scene itself.
    bare = SceneInput(9, False, SCENE_TEXT, 4, has_image, has_keywords=has_keywords)
    checks = run(content=scenes(4) + [bare])
    hint = "Cảnh chưa có từ khóa tìm ảnh: nhập từ khóa hoặc tải ảnh lên"
    assert (hint in messages(checks.warnings, 9)) == warned
    if warned:
        assert [issue.field for issue in checks.warnings if issue.message == hint] == ["keywords"]


@pytest.mark.parametrize(
    "text", ["CHỮA KHỎI đau lưng", "*chữa* khỏi", unicodedata.normalize("NFD", "chữa khỏi"), "chữa\nkhỏi"]
)
def test_banned_words_match_case_markup_and_unicode_forms(text):
    assert banned_hits(text, ["chữa khỏi"]) == ["chữa khỏi"]


def test_banned_word_warnings_do_not_block_and_point_at_the_field():
    content = scenes(4) + [SceneInput(9, False, "Đặc trị\n*đau* lưng", 4, True)]
    checks = run(
        title(text="KHẮC TINH CỦA BỆNH"),
        content,
        {"caption": "giúp chữa khỏi", "pinned_comment": "ok"},
        banned=["chữa khỏi", "đặc trị", "khắc tinh"],
    )
    assert checks.blocking == []
    assert messages(checks.warnings, 9) == ["Có từ cấm: “đặc trị”"]
    assert messages(checks.warnings, 0) == ["Có từ cấm: “khắc tinh”"]
    assert [(issue.field, issue.message) for issue in checks.warnings if issue.scene_id is None] == [
        ("caption", "Có từ cấm: “chữa khỏi”")
    ]


def test_narration_already_made_lengthens_the_total():
    # 3 s title + 9 scenes of 9 s = 84 s; narration of 9.5 s makes one scene 10.1 s and the total 85.1 s.
    content = scenes(8, 9.0) + [SceneInput(9, False, SCENE_TEXT, 9.0, True, "Lời đọc", 9.5)]
    assert run(content=content).blocking == []
    content = scenes(8, 9.0) + [SceneInput(9, False, SCENE_TEXT, 9.0, True, "Lời đọc", 15.5)]
    assert [issue.message for issue in run(content=content).blocking] == ["Tổng độ dài 91.1 giây, tối đa 90 giây"]


def test_a_lengthened_scene_is_not_blocked_by_the_10_second_limit():
    content = scenes(4) + [SceneInput(9, False, SCENE_TEXT, 4, True, "Lời đọc dài", 12.0)]
    assert run(content=content).blocking == []


def test_banned_words_in_narration_warn_on_the_voice_field():
    content = scenes(4) + [SceneInput(9, False, SCENE_TEXT, 4, True, "Món này đặc trị đau lưng")]
    checks = run(content=content, banned=["đặc trị"])
    assert checks.blocking == []
    assert [(issue.field, issue.message) for issue in checks.warnings if issue.scene_id == 9] == [
        ("voice", "Lời đọc có từ cấm: “đặc trị”")
    ]


@pytest.mark.parametrize(
    ("seconds", "voice_seconds", "warned"),
    [
        (3.0, None, True),
        (1.6, None, False),
        # A middle scene also plays 0.2 s into each crossfade: 1.7 + 0.4 needs more than the 2 s of clip.
        (1.7, None, True),
        # Narration lengthens the scene past what is left of the clip.
        (1.6, 2.0, True),
    ],
)
def test_a_scene_longer_than_its_clip_only_warns(seconds, voice_seconds, warned):
    """A middle scene: a crossfade on both sides."""
    clip = SceneInput(
        9, False, SCENE_TEXT, seconds, True, "lời đọc" if voice_seconds else "", voice_seconds, clip_seconds=2.0
    )
    checks = run(title(), scenes(2) + [clip] + scenes(2))
    assert ("Video ngắn hơn cảnh, khung cuối sẽ đứng yên" in messages(checks.warnings, 9)) is warned
    assert messages(checks.blocking, 9) == []


@pytest.mark.parametrize("place", ["title", "last"])
@pytest.mark.parametrize(("seconds", "warned"), [(1.8, False), (1.9, True)])
def test_the_title_and_the_last_scene_have_one_crossfade_to_cover(place, seconds, warned):
    clip = SceneInput(
        9 if place == "last" else 0,
        place == "title",
        TITLE_TEXT if place == "title" else SCENE_TEXT,
        seconds,
        True,
        clip_seconds=2.0,
    )
    checks = run(clip, scenes(4) + [clip]) if place == "last" else run(clip, scenes(4))
    assert ("Video ngắn hơn cảnh, khung cuối sẽ đứng yên" in messages(checks.warnings, clip.id)) is warned


@pytest.mark.parametrize("text", ["5 MÓN *GIÚP", "CÁ " * 60])
def test_title_text_that_reels_render_refuses_still_blocks(text):
    assert messages(run(title(text=text)).blocking, 0)
