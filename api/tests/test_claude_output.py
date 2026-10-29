import json

import pytest

from reels_api.claude import (
    OUTPUT_FORMAT,
    ClaudeError,
    ScriptOutputError,
    build_script_prompt,
    generate_script,
    parse_output,
)
from reels_api.knowledge import default_script_prompt


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
    example = json.loads(OUTPUT_FORMAT[OUTPUT_FORMAT.index("{"):])
    assert set(example) == {"titles", "title_keywords", "scenes", "caption", "hashtags", "affiliates",
                            "pinned_comment", "self_review", "music_suggestions"}
    assert all(set(scene) == {"text", "seconds", "keywords", "image_prompt"} for scene in example["scenes"])
    assert parse_output(OUTPUT_FORMAT).titles[0] == "5 MÓN GIÚP XƯƠNG CHẮC KHỎE SAU TUỔI 50"


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
