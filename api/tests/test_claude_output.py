import json

import pytest

from reels_api.claude import (
    OUTPUT_FORMAT,
    ClaudeError,
    ScriptOutputError,
    build_clone_prompt,
    build_script_prompt,
    generate_script,
    parse_output,
)
from reels_api.knowledge import default_script_prompt
from reels_api.script_rules import TOTAL_SECONDS_RANGE, count_words


def valid(**changes) -> dict:
    data = {
        "titles": ["A", "B", "C", "D", "E"],
        "title_keywords": ["món ăn giàu canxi"],
        "scenes": [{"text": "Cá nhỏ\nGiàu *canxi*", "seconds": 4, "keywords": ["cá cơm"], "image_prompt": "cá"}],
        "caption": "caption",
        "hashtags": ["#a", "#b"],
        "affiliates": ["Sữa hạt", "Vừng"],
        "pinned_comment": "ghim",
        "self_review": ["x → y"],
        "music_suggestions": ["Windy Hill"],
    }
    data.update(changes)
    return data


def test_a_valid_answer_keeps_every_part():
    script = parse_output("Đây là kịch bản:\n```json\n" + json.dumps(valid(), ensure_ascii=False) + "\n```")
    assert script.titles == ["A", "B", "C", "D", "E"]
    assert script.title_keywords == ["món ăn giàu canxi"]
    assert script.scenes[0].text == "Cá nhỏ\nGiàu *canxi*"
    assert (script.scenes[0].seconds, script.scenes[0].keywords, script.scenes[0].image_prompt) == (4, ["cá cơm"], "cá")
    assert (script.caption, script.pinned_comment) == ("caption", "ghim")
    assert script.hashtags == ["#a", "#b"] and script.affiliates == ["Sữa hạt", "Vừng"]
    assert script.self_review == ["x → y"] and script.music_suggestions == ["Windy Hill"]


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("không có JSON", "không có object JSON"),
        ('{"titles": ["A"], "scenes": [', "không có object JSON"),
        ('{"titles": ["A",], "scenes": []}', "JSON lỗi cú pháp"),
        (json.dumps(valid(titles=[])), "thiếu tiêu đề"),
        (json.dumps(valid(titles=None)), "thiếu tiêu đề"),
        (json.dumps(valid(scenes=[])), "không có cảnh"),
        (json.dumps(valid(scenes="cảnh 1")), "không có cảnh"),
    ],
)
def test_unusable_answers_raise(raw, reason):
    with pytest.raises(ScriptOutputError, match=reason):
        parse_output(raw)


@pytest.mark.parametrize(("seconds", "saved"), [(0.5, 4), (0, 4), (-2, 4), ("4", 4), (True, 4), (1, 1), (12, 12)])
def test_seconds_below_one_or_not_a_number_become_four(seconds, saved):
    script = parse_output(json.dumps(valid(scenes=[{"text": "x", "seconds": seconds}])))
    assert script.scenes[0].seconds == saved


def test_keywords_are_cut_to_100_characters():
    script = parse_output(json.dumps(valid(scenes=[{"text": "x", "seconds": 4, "keywords": ["a" * 150, " ", "b"]}])))
    assert script.scenes[0].keywords == ["a" * 100, "b"]


def test_missing_music_and_title_keywords_stay_empty_and_fewer_titles_are_kept():
    data = valid(titles=["A", "B"])
    del data["music_suggestions"], data["title_keywords"]
    script = parse_output(json.dumps(data))
    assert script.titles == ["A", "B"]
    assert script.music_suggestions == [] and script.title_keywords == []


def test_english_keywords_are_parsed_and_kept():
    data = valid()
    data["title_keywords_en"] = ["calcium rich food"]
    data["scenes"][0]["keywords_en"] = ["small fish"]
    script = parse_output(json.dumps(data))
    assert script.title_keywords_en == ["calcium rich food"]
    assert script.scenes[0].keywords_en == ["small fish"]


def test_voice_text_drops_markup_stars_and_extra_spaces_and_may_be_missing():
    script = parse_output(
        json.dumps(
            valid(
                title_voice="  Bạn đã ăn\n đủ *5 món* này chưa? ",
                scenes=[
                    {"text": "x", "seconds": 4, "voice": "Giàu *canxi*  lắm"},
                    {"text": "y", "seconds": 4, "voice": 3},
                ],
            )
        )
    )
    assert script.title_voice == "Bạn đã ăn đủ 5 món này chưa?"
    assert [scene.voice for scene in script.scenes] == ["Giàu canxi lắm", ""]
    assert parse_output(json.dumps(valid())).title_voice == ""


def test_banned_words_cover_the_voice_text():
    assert "chữ trên màn hình, lời đọc, caption" in build_script_prompt("[Chủ đề]", "x", ["đặc trị"])


def test_topic_replaces_the_placeholder_and_banned_words_and_format_follow():
    prompt = build_script_prompt("Viết về: [Chủ đề] cho người 50+", "xương khớp", ["chữa khỏi", "đặc trị"])
    assert prompt.startswith("Viết về: xương khớp cho người 50+")
    assert "[Chủ đề]" not in prompt
    assert '"chữa khỏi", "đặc trị"' in prompt
    assert prompt.endswith(OUTPUT_FORMAT)


def test_topic_is_appended_when_the_placeholder_was_removed():
    prompt = build_script_prompt("Viết kịch bản 5 món.", "tim mạch", [])
    assert prompt.startswith("Viết kịch bản 5 món.\n\nChủ đề: tim mạch\n\n")


def test_default_prompt_has_the_topic_placeholder():
    assert "Chủ đề: [Chủ đề]" in default_script_prompt()
    assert default_script_prompt().startswith("Bạn là biên tập viên kênh Reels dưỡng sinh cho người 40+.")


def test_format_example_is_valid_json_with_every_field_and_no_image_paths():
    example = json.loads(OUTPUT_FORMAT[OUTPUT_FORMAT.index("{") :])
    assert set(example) == {
        "titles",
        "title_voice",
        "title_keywords",
        "title_keywords_en",
        "title_image_prompt",
        "scenes",
        "caption",
        "hashtags",
        "affiliates",
        "pinned_comment",
        "self_review",
        "music_suggestions",
    }
    assert all(
        set(scene) == {"text", "seconds", "voice", "image_prompt", "keywords", "keywords_en"}
        for scene in example["scenes"]
    )
    assert parse_output(OUTPUT_FORMAT).titles[0] == "5 MÓN GIÚP XƯƠNG CHẮC KHỎE SAU TUỔI 50"


def test_the_format_leaves_the_caption_length_to_the_editable_prompt():
    assert '"caption": caption theo yêu cầu trong prompt' in OUTPUT_FORMAT
    assert "80–120" not in OUTPUT_FORMAT


def test_the_format_and_its_example_give_narration_room_for_detail():
    assert "không quá 150 từ" in OUTPUT_FORMAT and "6–12 từ" not in OUTPUT_FORMAT
    assert "8–15 từ" in OUTPUT_FORMAT
    example = parse_output(OUTPUT_FORMAT)
    voices = [count_words(scene.voice) for scene in example.scenes]
    # The model copies the example's length, so it shows the fuller voice text the format asks for.
    assert min(voices) >= 12 and max(voices) <= 15
    assert count_words(example.title_voice) + sum(voices) <= 150


def test_the_example_names_the_dish_in_every_voice_text():
    # Only the voice text is read, and the model copies the example, so a listener must hear what the scene is about.
    for scene in parse_output(OUTPUT_FORMAT).scenes:
        dish = " ".join(scene.text.split()[:2])
        assert scene.voice.startswith(dish), scene.voice


def test_the_format_says_a_voiced_scene_reads_only_its_voice_text():
    assert "không đọc chữ trên màn hình" in OUTPUT_FORMAT
    assert "chữ trên màn hình trước" not in OUTPUT_FORMAT


def test_a_full_length_script_is_not_warned_about_its_length():
    assert 150 / 2.9 < TOTAL_SECONDS_RANGE[1]


def test_a_broken_answer_is_asked_once_more():
    answers = iter(["hỏng", json.dumps(valid())])
    calls = []
    script = generate_script("p", "job 1", lambda: calls.append(1), lambda prompt, label: next(answers))
    assert script.titles[0] == "A" and len(calls) == 2


def test_two_broken_answers_fail_with_the_raw_answer_as_detail():
    calls = []
    with pytest.raises(ClaudeError) as caught:
        generate_script("p", "job 1", lambda: calls.append(1), lambda prompt, label: '{"titles": []}')
    assert len(calls) == 2
    assert "thiếu tiêu đề" in caught.value.message
    assert '{"titles": []}' in caught.value.detail


SOURCE = {
    "title": "5 MÓN BỔ XƯƠNG",
    "topic": "xương khớp",
    "script": "Cảnh 1 (4 giây): Cá nhỏ",
    "request": "đổi sang mốc 45 tuổi, tim mạch",
}


def test_clone_prompt_fills_every_placeholder():
    from reels_api.knowledge import default_clone_prompt

    prompt = build_clone_prompt(default_clone_prompt(), SOURCE, ["đặc trị"])
    assert prompt.startswith(
        'Video gốc: "5 MÓN BỔ XƯƠNG" — chủ đề: xương khớp.\nKịch bản gốc:\nCảnh 1 (4 giây): Cá nhỏ'
    )
    assert "theo yêu cầu sau:\nđổi sang mốc 45 tuổi, tim mạch" in prompt
    assert "[" + "tiêu đề]" not in prompt and "[yêu cầu đổi]" not in prompt
    assert '"đặc trị"' in prompt and prompt.endswith(OUTPUT_FORMAT)


def test_clone_prompt_appends_what_a_member_removed_from_the_template():
    prompt = build_clone_prompt("Viết một biến thể của [tiêu đề].", SOURCE, [])
    body = prompt.split("\n\n" + OUTPUT_FORMAT)[0]
    assert body == (
        "Viết một biến thể của 5 MÓN BỔ XƯƠNG.\n\n"
        "Chủ đề video gốc: xương khớp\n\n"
        "Kịch bản đã sửa của video gốc: Cảnh 1 (4 giây): Cá nhỏ\n\n"
        "Yêu cầu đổi: đổi sang mốc 45 tuổi, tim mạch"
    )


COOKING_WORDS = {"chiên", "rán", "luộc", "xào", "rang", "giã", "kho", "nấu", "hấp", "nướng", "om", "chế"}


def test_the_voice_rule_asks_for_the_benefit_and_a_short_eating_tip_not_how_to_cook():
    voice_rule = OUTPUT_FORMAT[OUTPUT_FORMAT.index('- "voice"') : OUTPUT_FORMAT.index('- "image_prompt"')]
    assert "công dụng" in voice_rule
    assert "mẹo ăn ngắn" in voice_rule and "còn chỗ" in voice_rule
    assert "không mô tả cách nấu" in voice_rule
    assert "lý do, cách ăn hoặc mẹo nhỏ" not in OUTPUT_FORMAT
    # Benefit talk slides easily into health promises (docs/content.md, Safety Rules).
    assert '"tốt cho"' in voice_rule and '"hỗ trợ"' in voice_rule
    assert "không hứa chữa bệnh" in voice_rule
    assert "không lặp lại nguyên văn chữ trên màn hình" in voice_rule


def test_the_example_voice_texts_tell_the_benefit_not_the_cooking():
    # The model copies the example closely, so its voice texts must not describe cooking steps.
    for scene in parse_output(OUTPUT_FORMAT).scenes:
        words = {word.strip(",.!?").lower() for word in scene.voice.split()}
        assert not words & COOKING_WORDS, scene.voice
        # The voice explains the label, it does not read it back.
        for line in scene.text.replace("*", "").split("\n")[1:]:
            assert line.lower() not in scene.voice.lower(), scene.voice


def test_the_example_voice_texts_use_no_banned_word():
    defaults = ["chữa khỏi", "thay thuốc", "diệt tế bào ung thư", "đặc trị", "khắc tinh"]
    for scene in parse_output(OUTPUT_FORMAT).scenes:
        assert not any(word in scene.voice.lower() for word in defaults), scene.voice
