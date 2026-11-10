""" "Loại nội dung" picked by the AI that writes the script (decisions 2026-11-10): one of the team's types when one
fits, a short new one otherwise; members still change it by hand."""

import json

from conftest import make_video
from fake_services import script_json
from test_ai_effects import write_script
from worker_helpers import add_user, committed  # noqa: F401  (fixture)

from reels_api.claude import OUTPUT_FORMAT, build_clone_prompt, build_script_prompt, parse_output
from reels_api.models import Video
from reels_api.storage import DirectoryStorage


def answer(**changes) -> str:
    return json.dumps(script_json("rau mầm", scene_count=1) | changes, ensure_ascii=False)


def test_the_answer_s_content_type_is_kept_tidied_and_cut_to_40_characters():
    assert parse_output(answer(content_type="  Danh sách   món ")).content_type == "Danh sách món"
    assert parse_output(answer(content_type="x" * 60)).content_type == "x" * 40
    assert parse_output(answer()).content_type == "", "an answer without one leaves it empty"
    assert parse_output(answer(content_type=["Mẹo"])).content_type == "", "only text counts"


def test_the_format_asks_for_a_content_type_and_its_example_has_one():
    example = json.loads(OUTPUT_FORMAT[OUTPUT_FORMAT.index("{") :])
    assert example["content_type"] and '"content_type"' in OUTPUT_FORMAT[: OUTPUT_FORMAT.index("{")]


def test_the_team_s_types_come_before_the_format_and_none_adds_nothing():
    prompt = build_script_prompt("[Chủ đề]", "rau", [], content_types=["Mẹo", "Danh sách món"])
    assert 'Loại nội dung đội đang dùng: "Mẹo", "Danh sách món"' in prompt
    assert prompt.endswith(OUTPUT_FORMAT)
    assert "Loại nội dung đội đang dùng" not in build_script_prompt("[Chủ đề]", "rau", [])
    source = {"title": "T", "topic": "rau", "script": "S", "request": "R"}
    assert '"Mẹo"' in build_clone_prompt("[tiêu đề]", source, [], content_types=["Mẹo"])


def test_a_script_job_is_told_the_team_s_types_and_saves_the_one_picked(committed, tmp_path):  # noqa: F811
    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    with committed() as db:
        make_video(db, storage, db.merge(user), scene_count=1).content_type = "Cảnh báo"
        db.commit()
    reply = script_json("rau mầm", scene_count=1) | {"content_type": "Danh sách món"}
    video_id, prompts = write_script(committed, storage, user, False, reply)
    assert '"Cảnh báo"' in prompts[0]
    with committed() as db:
        assert db.get(Video, video_id).content_type == "Danh sách món"
