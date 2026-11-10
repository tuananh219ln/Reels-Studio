""" "Chữ & phụ đề" of a topic group: its own text look over its videos' makers' defaults, "AI gợi ý" (a job that
suggests looks for the group) and "AI chọn kiểu chữ cho từng video" (the script call picks each video's look)."""

import json

import pytest
from conftest import client_for, first_topic, login, make_user
from fake_services import text_looks_json
from sqlalchemy import select
from test_mcp import GROUP_SCRIPT, call, grant, mcp_client, payload  # noqa: F401  (fixture)
from worker_helpers import add_user, committed, job_row  # noqa: F401  (fixture)

from reels_api import jobs, text_looks
from reels_api.models import Job, KnowledgeTopic, UserVideoDefaults, Video
from reels_api.storage import DirectoryStorage


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def shown(response, group_id: int) -> dict:
    [topic] = [topic for topic in response.json()["topics"] if topic["id"] == group_id]
    return topic


def new_video(an, group_id: int) -> dict:
    made = an.post("/api/videos", json={"topic": "canh chua", "knowledge_topic_id": group_id})
    assert made.status_code == 201, made.json()
    return made.json()


# --- The group's own look ---


def test_a_group_has_no_look_of_its_own_until_one_is_saved(an, db, me):
    db.add(UserVideoDefaults(user_id=me.id, value={"text_size": "small"}))
    db.commit()
    knowledge = an.get("/api/knowledge")
    group = shown(knowledge, first_topic(db).id)
    assert (group["text_look"], group["text_ai"], group["text_suggestions"], group["text_job"]) == (
        None,
        False,
        None,
        None,
    )
    # A look of its own starts from the member's own "Chữ & phụ đề".
    start = knowledge.json()["default_text_look"]
    assert set(start) == set(text_looks.FIELDS) and start["text_size"] == "small"
    assert new_video(an, first_topic(db).id)["options"]["text_style"] == "yellow"


def test_the_groups_look_is_over_its_makers_defaults_and_null_gives_them_back(an, db, me):
    db.add(UserVideoDefaults(user_id=me.id, value={"text_size": "small", "transition": "cut"}))
    db.commit()
    group = first_topic(db).id
    saved = an.patch(f"/api/knowledge/topics/{group}", json={"text_look": {"text_style": "dark", "captions": "word"}})
    assert saved.status_code == 200, saved.json()
    assert shown(saved, group)["text_look"] == {"text_style": "dark", "captions": "word"}

    options = new_video(an, group)["options"]
    assert (options["text_style"], options["captions"]) == ("dark", "word")
    # What the group does not set stays the maker's.
    assert (options["text_size"], options["transition"]) == ("small", "cut")

    cleared = an.patch(f"/api/knowledge/topics/{group}", json={"text_look": None})
    assert shown(cleared, group)["text_look"] is None
    assert new_video(an, group)["options"]["text_style"] == "yellow"


@pytest.mark.parametrize(
    "look",
    [{"voice_id": "abc"}, {"text_style": "rainbow"}, {"text_color": "#12"}, {"text_position": [1, 2]}],
)
def test_a_look_with_a_field_or_value_outside_chu_phu_de_is_refused(an, db, look):
    group = first_topic(db).id
    refused = an.patch(f"/api/knowledge/topics/{group}", json={"text_look": look})
    assert refused.status_code == 422, refused.json()
    db.expire_all()
    assert db.get(KnowledgeTopic, group).text_look is None


def test_the_look_is_in_the_groups_history_and_behind_its_edit_lock(an, app, db, me):
    group = first_topic(db)
    group.created_by_id, group.team_edit = me.id, False
    db.commit()
    an.patch(f"/api/knowledge/topics/{group.id}", json={"text_look": {"text_case": "keep"}, "text_ai": True})
    history = an.get(f"/api/edit-logs?entity_type=knowledge_topic&entity_id={group.id}").json()["entries"]
    assert history[0]["changes"]["text_look"] == {"old": None, "new": {"text_case": "keep"}}
    assert history[0]["changes"]["text_ai"] == {"old": False, "new": True}

    make_user(db, email="binh@doi.vn", name="Bình")
    binh = client_for(app)
    login(binh, email="binh@doi.vn")
    assert binh.patch(f"/api/knowledge/topics/{group.id}", json={"text_ai": False}).status_code == 403
    assert binh.post(f"/api/knowledge/topics/{group.id}/text-suggestions").status_code == 403


# --- "AI gợi ý" ---


def test_ai_suggestions_queue_one_job_at_a_time_and_can_be_cancelled_and_retried(an, db):
    group = first_topic(db).id
    queued = an.post(f"/api/knowledge/topics/{group}/text-suggestions")
    assert queued.status_code == 200, queued.json()
    assert shown(queued, group)["text_job"]["status"] == "queued"
    again = an.post(f"/api/knowledge/topics/{group}/text-suggestions")
    assert (again.status_code, again.json()["message"]) == (409, "Nhóm đang có gợi ý kiểu chữ chờ hoặc đang tạo")
    # The plan's own "Tạo bằng AI" is not held up by it.
    assert an.post(f"/api/plans/{group}/generate").status_code == 200

    [row] = [row for row in an.get("/api/jobs").json() if row["kind"] == "text_look"]
    assert (row["video_title"], row["kind_label"]) == ("Chữ & phụ đề · Sức khỏe", "AI gợi ý kiểu chữ")
    [plan] = [row for row in an.get("/api/jobs").json() if row["kind"] == "plan"]
    assert plan["video_title"] == "Kế hoạch 30 ngày · Sức khỏe"

    cancelled = an.post(f"/api/jobs/{row['id']}/cancel")
    assert shown(cancelled, group)["text_job"] is None
    job = db.get(Job, row["id"])
    job.status = "failed"
    db.flush()
    retried = an.post(f"/api/jobs/{row['id']}/retry")
    assert shown(retried, group)["text_job"]["status"] == "queued"


def run_suggestions(factory, tmp_path, user, replies) -> Job:
    prompts = []

    def llm(prompt, label):
        prompts.append(prompt)
        return replies.pop(0)

    with factory() as db:
        group = first_topic(db)
        group.text_suggestions = {"job_id": 0, "created_at": "", "options": [{"name": "Cũ", "look": {}}]}
        job = Job(knowledge_topic_id=group.id, kind="text_look", status="running", created_by_id=user.id)
        db.add(job)
        db.commit()
    jobs.run_job(job.id, factory, DirectoryStorage(tmp_path / "storage"), llm)
    return job_row(factory, job.id), prompts


def test_the_suggestion_job_keeps_the_valid_looks_for_the_group_and_leaves_its_look_alone(committed, tmp_path):
    user = add_user(committed)
    job, prompts = run_suggestions(
        committed, tmp_path, user, ["Đây là gợi ý:\n" + json.dumps(text_looks_json(), ensure_ascii=False)]
    )
    assert (job.status, job.claude_calls) == ("done", 1)
    assert "Sức khỏe" in prompts[0] and "Ảnh của nhóm" in prompts[0]
    with committed() as db:
        group = first_topic(db)
        options = group.text_suggestions["options"]
        assert group.text_suggestions["job_id"] == job.id
        assert [option["name"] for option in options] == ["Ấm áp dễ đọc", "Nổi bật", "Tối giản"]
        # A named box style becomes a box of its colours; a colour the AI gave itself is kept.
        assert options[1]["look"] == {
            "text_style": "box",
            "box_color": "#E10600",
            "text_color": "#FFFFFF",
            "accent_color": "#FFD400",
            "captions": "word",
        }
        # A value the app does not have is left out of its look.
        assert options[2]["look"] == {"text_style": "none"}
        assert group.text_look is None


def test_an_unusable_answer_is_asked_again_once_then_the_job_fails(committed, tmp_path):
    user = add_user(committed)
    job, _ = run_suggestions(committed, tmp_path, user, ["không có JSON", '{"options": [{"look": {"x": 1}}]}'])
    assert (job.status, job.claude_calls) == ("failed", 2)
    assert "gợi ý kiểu chữ" in job.error
    with committed() as db:
        # The last suggestions stay until a job brings new ones.
        assert first_topic(db).text_suggestions["options"][0]["name"] == "Cũ"


def test_the_suggestion_prompt_reads_the_groups_name_prompt_photo_hint_and_look():
    group = KnowledgeTopic(
        name="Già Mà Khỏe", script_prompt="Viết cho người trên 50 tuổi", photo_hint="Ảnh người cao tuổi"
    )
    prompt = text_looks.suggest_prompt(group, {"text_style": "box"})
    assert "Già Mà Khỏe" in prompt and "người trên 50 tuổi" in prompt and "Ảnh người cao tuổi" in prompt
    assert "'text_style': 'box'" in prompt and text_looks.LOOK_RULES in prompt


# --- "AI chọn kiểu chữ cho từng video" ---


def test_the_ai_picks_each_videos_look_only_when_the_group_asks(mcp_client, db):
    _, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    group = first_topic(db)
    group.text_look = {"text_style": "white", "text_size": "medium"}
    db.commit()
    script = json.dumps({**GROUP_SCRIPT, "text_look": {"text_style": "dark", "captions": "word", "x": 1}})

    def make(topic: str) -> Video:
        made = call(
            mcp_client,
            token,
            "create_video_from_group_prompt",
            topic=topic,
            knowledge_topic_id=group.id,
            script_json=script,
        )
        assert not made.get("isError"), made
        return db.scalar(select(Video).where(Video.topic == topic))

    prompt = payload(call(mcp_client, token, "get_script_prompt", topic="Rau", knowledge_topic_id=group.id))["prompt"]
    assert text_looks.SCRIPT_FORMAT not in prompt
    off = make("Tắt")
    assert (off.options["text_style"], off.options["captions"]) == ("white", "off")

    group.text_ai = True
    db.commit()
    prompt = payload(call(mcp_client, token, "get_script_prompt", topic="Rau", knowledge_topic_id=group.id))["prompt"]
    assert text_looks.SCRIPT_FORMAT in prompt
    on = make("Bật")
    # The AI's pick over the group's, the group's where the AI said nothing.
    assert (on.options["text_style"], on.options["box_color"], on.options["box_opacity"]) == ("box", "#111111", "soft")
    assert (on.options["captions"], on.options["text_size"]) == ("word", "medium")
    assert "x" not in on.options
