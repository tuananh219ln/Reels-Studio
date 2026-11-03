"""The 30-day topic plan: ideas on /knowledge, file import, the AI plan job and making videos from ideas."""

import json
import re
from datetime import timedelta

import pytest
from conftest import first_topic, login, make_user, make_video
from fake_services import plan_json
from sqlalchemy import select
from worker_helpers import add_user, committed, job_row  # noqa: F401  (fixtures)

from reels_api import jobs, plans
from reels_api.claude import build_script_prompt
from reels_api.models import Job, KnowledgeTopic, TopicPlanItem, Video
from reels_api.storage import DirectoryStorage


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


@pytest.fixture
def topic_id(db):
    return first_topic(db).id


def sample_plan(days=30, per_day=4) -> dict:
    """The shape of ke_hoach_30_ngay.json: 30 days of 4 ideas, with Vietnamese keys."""
    return {
        "ke_hoach": [
            {
                "ngay": day,
                "y_tuong": [
                    {
                        "chu_de": f"5 món giúp ngủ ngon ngày {day} số {n}",
                        "nhom_noi_dau": "Mất ngủ",
                        "noi_dau": "Trằn trọc đến 2 giờ sáng",
                        "goc_hook": "Thức giấc lúc 2 giờ không phải do tuổi",
                    }
                    for n in range(1, per_day + 1)
                ],
            }
            for day in range(1, days + 1)
        ]
    }


def add(an, topic_id, day, topic, **fields):
    return an.post(f"/api/plans/{topic_id}/items", json={"day": day, "topic": topic, **fields})


def ideas_of(plan, day):
    return [item["topic"] for item in plan["items"] if item["day"] == day]


# --- The plan and its ideas ---


def test_a_group_starts_with_an_empty_plan_and_the_default_prompt(an, topic_id):
    plan = an.get(f"/api/plans/{topic_id}").json()
    assert plan["items"] == [] and plan["made"] == 0
    assert plan["start_date"] is None and plan["today_day"] is None and plan["per_day"] == 4
    assert plan["prompt"] == plans.default_prompt() == plan["default_prompt"]
    assert "[Chủ đề nhóm]" in plan["prompt"] and "[Số video mỗi ngày]" in plan["prompt"]
    assert plan["job"] is None and plan["draft"] is None
    assert an.get("/api/plans/999999").status_code == 404


def test_the_plan_prompt_is_saved_and_restoring_the_default_follows_later_defaults(an, db, topic_id):
    path = f"/api/plans/{topic_id}"
    assert (
        an.patch(path, json={"prompt": "  Kế hoạch cho [Chủ đề nhóm]  "}).json()["prompt"]
        == "Kế hoạch cho [Chủ đề nhóm]"
    )
    assert an.patch(path, json={"prompt": " "}).json()["message"] == "Prompt không được để trống"
    restored = an.patch(path, json={"prompt": plans.default_prompt()}).json()
    assert restored["prompt"] == plans.default_prompt()
    assert db.get(KnowledgeTopic, topic_id).plan_prompt == ""


def test_start_date_tells_which_day_today_is(an, topic_id):
    path = f"/api/plans/{topic_id}"
    start = plans.today() - timedelta(days=2)
    plan = an.patch(path, json={"start_date": start.isoformat(), "per_day": 5}).json()
    assert (plan["start_date"], plan["today_day"], plan["per_day"]) == (start.isoformat(), 3, 5)
    assert an.patch(path, json={"per_day": 6}).json()["message"] == "Số ý tưởng mỗi ngày phải từ 3 đến 5"
    assert an.patch(path, json={"start_date": None}).json()["today_day"] is None


def test_ideas_are_added_at_most_five_a_day_and_never_twice(an, topic_id):
    for n in range(1, 6):
        assert add(an, topic_id, 2, f"Ý tưởng {n}", pain="sợ", hook="hook").status_code == 201
    full = add(an, topic_id, 2, "Ý tưởng 6")
    assert (full.status_code, full.json()["message"]) == (409, "Ngày 2 đã đủ 5 ý tưởng")
    twice = add(an, topic_id, 3, "  ý TƯỞNG   1 ")
    assert (twice.status_code, twice.json()["message"]) == (409, "Kế hoạch đã có chủ đề này (ngày 2)")
    assert add(an, topic_id, 31, "x").json()["message"] == "Ngày phải từ 1 đến 30"
    assert add(an, topic_id, 1, "  ").json()["message"] == "Thiếu chủ đề"
    plan = an.get(f"/api/plans/{topic_id}").json()
    assert ideas_of(plan, 2) == [f"Ý tưởng {n}" for n in range(1, 6)]
    item = plan["items"][0]
    assert (item["position"], item["pain"], item["hook"], item["status"], item["status_label"]) == (
        1,
        "sợ",
        "hook",
        "idea",
        "Ý tưởng",
    )


def test_ideas_are_edited_moved_between_days_and_deleted(an, topic_id):
    for n in range(1, 4):
        add(an, topic_id, 1, f"A{n}")
    plan = add(an, topic_id, 2, "B1").json()
    a1, a2, a3, b1 = (item["id"] for item in plan["items"])

    edited = an.patch(f"/api/plans/items/{a2}", json={"topic": "A2 mới", "pain_group": "Tim", "hook": "h"}).json()
    assert ideas_of(edited, 1) == ["A1", "A2 mới", "A3"]
    assert an.patch(f"/api/plans/items/{a2}", json={"topic": "B1"}).status_code == 409

    moved = an.patch(f"/api/plans/items/{a1}", json={"day": 2, "position": 1}).json()
    assert ideas_of(moved, 1) == ["A2 mới", "A3"] and ideas_of(moved, 2) == ["A1", "B1"]
    assert [item["position"] for item in moved["items"]] == [1, 2, 1, 2]
    reordered = an.patch(f"/api/plans/items/{a3}", json={"position": 1}).json()
    assert ideas_of(reordered, 1) == ["A3", "A2 mới"]

    after = an.delete(f"/api/plans/items/{b1}").json()
    assert ideas_of(after, 2) == ["A1"] and after["items"][-1]["position"] == 1
    assert an.delete(f"/api/plans/items/{b1}").status_code == 404


# --- Import ---


def test_a_120_idea_json_file_is_previewed_then_saved(an, topic_id):
    data = json.dumps(sample_plan(), ensure_ascii=False).encode()
    preview = an.post(f"/api/plans/{topic_id}/import", files={"file": ("ke_hoach_30_ngay.json", data)}).json()
    assert len(preview["ideas"]) == 120 and preview["errors"] == [] and preview["warnings"] == []
    assert preview["ideas"][0] == {
        "day": 1,
        "topic": "5 món giúp ngủ ngon ngày 1 số 1",
        "pain_group": "Mất ngủ",
        "pain": "Trằn trọc đến 2 giờ sáng",
        "hook": "Thức giấc lúc 2 giờ không phải do tuổi",
    }
    # A preview saves nothing.
    assert an.get(f"/api/plans/{topic_id}").json()["items"] == []

    saved = an.put(f"/api/plans/{topic_id}/items", json={"ideas": preview["ideas"]}).json()
    assert len(saved["items"]) == 120
    assert [item["position"] for item in saved["items"] if item["day"] == 30] == [1, 2, 3, 4]


def test_a_csv_file_reports_the_rows_it_cannot_read(an, topic_id):
    rows = [
        "Ngày;Chủ đề;Nhóm nỗi đau;Nỗi đau;Góc hook",
        "1;7 món tốt cho tim;Tim mạch;Sợ tai biến;Đừng bỏ qua",
        "",
        "2;;Tim mạch;x;y",
        "ba;Món B;;;",
        "1;7 MÓN tốt cho tim;;;",
    ]
    data = "\n".join(rows).encode("utf-8-sig")
    preview = an.post(f"/api/plans/{topic_id}/import", files={"file": ("plan.csv", data)}).json()
    assert [idea["topic"] for idea in preview["ideas"]] == ["7 món tốt cho tim", "7 MÓN tốt cho tim"]
    assert preview["errors"] == [
        "Dòng 4: thiếu chủ đề",
        "Dòng 5: thiếu ngày hoặc ngày không phải số",
        "Chủ đề trùng: “7 MÓN tốt cho tim” (ngày 1 và ngày 1)",
    ]
    assert preview["warnings"][0].startswith("Chưa có ý tưởng cho ngày 2, 3")
    refused = an.put(f"/api/plans/{topic_id}/items", json={"ideas": preview["ideas"]})
    assert (refused.status_code, refused.json()["message"]) == (
        422,
        "Chủ đề trùng: “7 MÓN tốt cho tim” (ngày 1 và ngày 1)",
    )


def test_files_that_cannot_be_a_plan_are_refused(an, topic_id):
    path = f"/api/plans/{topic_id}/import"
    assert an.post(path, files={"file": ("a.json", b"{ broken")}).json()["message"].startswith("JSON lỗi cú pháp")
    assert an.post(path, files={"file": ("a.csv", "Tên,Giá\nx,1".encode())}).json()["message"] == (
        "File CSV cần dòng tiêu đề có cột ngày và chủ đề (day, topic)"
    )
    assert an.post(path, files={"file": ("a.csv", "ngày\xff".encode("latin-1"))}).json()["message"] == (
        "File phải là văn bản UTF-8 (JSON hoặc CSV)"
    )
    big = an.post(path, files={"file": ("a.csv", b"x" * (plans.MAX_FILE_BYTES + 1))})
    assert big.status_code == 413


def test_other_json_shapes_are_read_too():
    flat = [{"day": 2, "topic": "B"}, {"Ngày": "1", "Chủ đề": "A", "Góc hook": ["h1", "h2"]}]
    ideas, errors = plans.parse_file("x.json", json.dumps(flat).encode())
    assert errors == [] and [(idea.day, idea.topic, idea.hook) for idea in ideas] == [(1, "A", "h1; h2"), (2, "B", "")]
    by_key = {"Ngày 1": [{"topic": "A"}], "2": [{"topic": "B"}, "x"]}
    ideas, errors = plans.parse_file("x.json", json.dumps(by_key).encode())
    assert [idea.day for idea in ideas] == [1, 2] and errors == ["Ngày 2, ý 2: không phải object"]


def test_saving_a_new_plan_keeps_the_video_of_an_idea_with_the_same_topic(an, db, me, storage, topic_id):
    plan = add(an, topic_id, 1, "Món A").json()
    video = make_video(db, storage, me)
    db.get(TopicPlanItem, plan["items"][0]["id"]).video_id = video.id
    db.flush()
    ideas = [{"day": 5, "topic": "món  a"}, {"day": 1, "topic": "Món mới"}]
    saved = an.put(f"/api/plans/{topic_id}/items", json={"ideas": ideas}).json()
    linked = {item["topic"]: item["video_id"] for item in saved["items"]}
    assert linked == {"Món mới": None, "món a": video.id}


# --- Videos from ideas ---


def test_a_video_made_from_an_idea_is_linked_and_its_status_follows_the_video(an, db, topic_id):
    item_id = add(an, topic_id, 1, "5 món tốt cho tim", pain="Sợ tai biến", hook="Đừng bỏ qua").json()["items"][0]["id"]
    body = {"topic": "5 món tốt cho tim", "knowledge_topic_id": topic_id, "plan_item_id": item_id}
    video = an.post("/api/videos", json=body).json()
    assert video["plan_idea"] == {
        "id": item_id,
        "knowledge_topic_id": topic_id,
        "day": 1,
        "topic": "5 món tốt cho tim",
        "pain_group": "",
        "pain": "Sợ tai biến",
        "hook": "Đừng bỏ qua",
    }
    assert an.get(f"/api/plans/items/{item_id}").json()["status"] == "started"
    again = an.post("/api/videos", json=body)
    assert (again.status_code, again.json()["message"]) == (409, "Ý tưởng này đã có video")

    row = db.get(Video, video["id"])
    row.has_script = True
    db.flush()
    assert an.get(f"/api/plans/items/{item_id}").json()["status_label"] == "Đã viết kịch bản"
    row.mp4_key = "videos/x/video.mp4"
    db.flush()
    plan = an.get(f"/api/plans/{topic_id}").json()
    assert (plan["items"][0]["status"], plan["made"]) == ("done", 1)

    db.execute(select(Job).where(Job.video_id == row.id)).scalar_one().status = "cancelled"
    db.flush()
    assert an.delete(f"/api/videos/{row.id}").status_code == 200
    db.expire_all()  # the database unlinked the idea; a new request would read it fresh
    item = an.get(f"/api/plans/items/{item_id}").json()
    assert (item["status"], item["video_id"]) == ("idea", None)


def test_an_idea_makes_videos_only_in_its_own_group(an, topic_id):
    other = an.post("/api/knowledge/topics", json={"name": "Gan"}).json()["topics"][1]
    an.patch(f"/api/knowledge/topics/{other['id']}", json={"script_prompt": "Viết về [Chủ đề]"})
    item_id = add(an, topic_id, 1, "Món A").json()["items"][0]["id"]
    wrong = an.post("/api/videos", json={"topic": "Món A", "knowledge_topic_id": other["id"], "plan_item_id": item_id})
    assert (wrong.status_code, wrong.json()["message"]) == (422, "Ý tưởng này thuộc nhóm chủ đề khác")
    gone = an.post("/api/videos", json={"topic": "Món A", "knowledge_topic_id": topic_id, "plan_item_id": 999999})
    assert gone.status_code == 404
    # Without an idea a video is made as before.
    assert an.post("/api/videos", json={"topic": "Ngoài kế hoạch", "knowledge_topic_id": topic_id}).status_code == 201


def test_today_lists_the_ideas_of_today_for_groups_with_a_running_plan(an, topic_id):
    add(an, topic_id, 1, "Hôm qua")
    add(an, topic_id, 2, "Hôm nay 1")
    add(an, topic_id, 2, "Hôm nay 2")
    assert an.get("/api/plans/today").json() == []
    start = plans.today() - timedelta(days=1)
    an.patch(f"/api/plans/{topic_id}", json={"start_date": start.isoformat()})
    [group] = an.get("/api/plans/today").json()
    assert (group["topic_id"], group["name"], group["day"]) == (topic_id, "Sức khỏe", 2)
    assert [idea["topic"] for idea in group["ideas"]] == ["Hôm nay 1", "Hôm nay 2"]
    assert group["topics"] == ["Hôm qua", "Hôm nay 1", "Hôm nay 2"]
    an.patch(f"/api/plans/{topic_id}", json={"start_date": (plans.today() - timedelta(days=30)).isoformat()})
    assert an.get("/api/plans/today").json() == []


def test_the_script_prompt_carries_the_pain_and_hook_of_the_idea():
    template = "Chủ đề: [Chủ đề]\nNỗi đau: [Nỗi đau]"
    prompt = build_script_prompt(template, "Món A", [], ("Tim mạch", "Sợ tai biến", ""))
    assert prompt.startswith("Chủ đề: Món A\nNỗi đau: Sợ tai biến\n\nNhóm nỗi đau: Tim mạch\n\n")
    assert "Góc hook" not in prompt.split("ĐỊNH DẠNG ĐẦU RA")[0]
    assert "Nỗi đau" not in build_script_prompt("Chủ đề: [Chủ đề]", "Món A", []).split("ĐỊNH DẠNG ĐẦU RA")[0]


# --- "Tạo bằng AI" ---


def test_generate_queues_one_plan_job_at_a_time(an, db, topic_id):
    plan = an.post(f"/api/plans/{topic_id}/generate").json()
    assert plan["job"]["status"] == "queued"
    again = an.post(f"/api/plans/{topic_id}/generate")
    assert (again.status_code, again.json()["message"]) == (409, "Nhóm chủ đề đang có kế hoạch chờ hoặc đang tạo")
    [row] = [row for row in an.get("/api/jobs").json() if row["kind"] == "plan"]
    assert (row["video_id"], row["knowledge_topic_id"]) == (None, topic_id)
    assert (row["video_title"], row["kind_label"]) == ("Kế hoạch 30 ngày · Sức khỏe", "Tạo kế hoạch 30 ngày")
    other = an.post("/api/knowledge/topics", json={"name": "Gan"}).json()["topics"][1]
    assert an.post(f"/api/plans/{other['id']}/generate").status_code == 200
    busy = an.delete(f"/api/knowledge/topics/{other['id']}")
    assert (busy.status_code, busy.json()["message"]) == (
        409,
        "Nhóm chủ đề đang tạo kế hoạch bằng AI nên chưa xoá được",
    )

    cancelled = an.post(f"/api/jobs/{row['id']}/cancel").json()
    assert cancelled["topic_id"] == topic_id and cancelled["job"] is None
    job = db.get(Job, row["id"])
    job.status = "failed"
    db.flush()
    retried = an.post(f"/api/jobs/{row['id']}/retry").json()
    assert retried["job"]["status"] == "queued"


def plan_call(prompts, replies=None):
    """An in-process LLM that answers plan prompts like the fake service, or with `replies` first."""

    def call(prompt, label):
        prompts.append(prompt)
        if replies:
            return replies.pop(0)
        first, last, per_day = (
            int(n) for n in re.search(r"ngày (\d+) đến ngày (\d+), mỗi ngày đúng (\d+)", prompt).groups()
        )
        return json.dumps(plan_json(first, last, per_day), ensure_ascii=False)

    return call


def run_plan(factory, tmp_path, user, call) -> Job:
    with factory() as db:
        job = Job(knowledge_topic_id=first_topic(db).id, kind="plan", status="running", created_by_id=user.id)
        db.add(job)
        db.commit()
    jobs.run_job(job.id, factory, DirectoryStorage(tmp_path / "storage"), call)
    return job_row(factory, job.id)


def test_the_plan_job_writes_the_month_in_three_calls_as_a_draft(committed, tmp_path):
    user = add_user(committed)
    prompts = []
    job = run_plan(committed, tmp_path, user, plan_call(prompts))
    assert (job.status, job.claude_calls) == ("done", 3)
    assert "ngày 1 đến ngày 10" in prompts[0] and "ngày 21 đến ngày 30" in prompts[2]
    assert "Sức khỏe" in prompts[0] and "mỗi ngày 4 ý tưởng" in prompts[0]
    # Each call is told the topics already chosen.
    assert "5 món tốt cho sức khỏe ngày 10 ý 2" in prompts[1] and "ngày 11 ý" not in prompts[1]
    with committed() as db:
        topic = first_topic(db)
        assert (len(topic.plan_draft["ideas"]), topic.plan_draft["errors"], topic.plan_draft["job_id"]) == (
            120,
            [],
            job.id,
        )
        # The saved plan is untouched until a member saves the draft.
        assert db.scalars(select(TopicPlanItem)).all() == []


def test_an_unusable_plan_answer_is_asked_once_more_then_fails(committed, tmp_path):
    user = add_user(committed)
    missing_day = json.dumps(plan_json(1, 9))
    job = run_plan(committed, tmp_path, user, plan_call([], ["không phải JSON", missing_day]))
    assert (job.status, job.claude_calls) == ("failed", 2)
    assert job.error == "AI trả kế hoạch ngày 1–10 không đúng định dạng (thiếu ý tưởng cho ngày 10), đã thử lại 1 lần"
    with committed() as db:
        assert first_topic(db).plan_draft is None


def test_a_plan_answer_is_repaired_where_it_can_be():
    answer = plan_json(1, 10, per_day=6)
    answer["days"][0]["ideas"][0]["topic"] = "Đã có"
    answer["days"][1]["ideas"][0]["hook"] = "h" * 900
    answer["days"].append({"day": 11, "ideas": [{"topic": "Ngày khác"}]})
    ideas = plans.parse_output("Đây là kế hoạch: " + json.dumps(answer), 1, 10, {"đã có"})
    assert len(ideas) == 50 and "Đã có" not in [idea.topic for idea in ideas]
    assert max(len(idea.hook) for idea in ideas) == plans.MAX_HOOK_LENGTH
    assert all(idea.day <= 10 for idea in ideas)
