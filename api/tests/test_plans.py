"""The 30-day topic plan: ideas on /knowledge, file import, the AI plan job and making videos from ideas."""

import json
import re
from datetime import datetime, timedelta

import pytest
from conftest import first_topic, login, make_user, make_video
from fake_services import plan_json
from sqlalchemy import select
from worker_helpers import add_user, committed, job_row  # noqa: F401  (fixtures)

from reels_api import analytics, jobs, plans
from reels_api.claude import build_script_prompt
from reels_api.models import Fanpage, Job, KnowledgeTopic, PostMetrics, Publication, TopicPlanItem, Video
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
    assert an.patch(path, json={"start_date": None}).json()["today_day"] is None


def test_ideas_per_day_go_from_1_to_10(an, topic_id):
    """Pages post 1-2 videos a day, so a plan may ask for as few as 1 idea a day, and up to 10."""
    path = f"/api/plans/{topic_id}"
    for per_day in (1, 2, 10):
        assert an.patch(path, json={"per_day": per_day}).json()["per_day"] == per_day
    for per_day in (0, 11):
        refused = an.patch(path, json={"per_day": per_day})
        assert (refused.status_code, refused.json()["message"]) == (422, "Số ý tưởng mỗi ngày phải từ 1 đến 10")
    assert an.get(path).json()["per_day"] == 10


def test_ideas_are_added_at_most_ten_a_day_and_never_twice(an, topic_id):
    for n in range(1, 11):
        assert add(an, topic_id, 2, f"Ý tưởng {n}", pain="sợ", hook="hook").status_code == 201
    full = add(an, topic_id, 2, "Ý tưởng 11")
    assert (full.status_code, full.json()["message"]) == (409, "Ngày 2 đã đủ 10 ý tưởng")
    twice = add(an, topic_id, 3, "  ý TƯỞNG   1 ")
    assert (twice.status_code, twice.json()["message"]) == (409, "Kế hoạch đã có chủ đề này (ngày 2)")
    assert add(an, topic_id, 31, "x").json()["message"] == "Ngày phải từ 1 đến 30"
    assert add(an, topic_id, 1, "  ").json()["message"] == "Thiếu chủ đề"
    plan = an.get(f"/api/plans/{topic_id}").json()
    assert ideas_of(plan, 2) == [f"Ý tưởng {n}" for n in range(1, 11)]
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


def test_a_plan_of_two_ideas_a_day_is_not_short_and_one_of_eleven_is_too_many(an, topic_id):
    two = json.dumps(sample_plan(per_day=2), ensure_ascii=False).encode()
    preview = an.post(f"/api/plans/{topic_id}/import", files={"file": ("plan.json", two)}).json()
    assert (len(preview["ideas"]), preview["errors"], preview["warnings"]) == (60, [], [])
    eleven = json.dumps(sample_plan(days=1, per_day=11), ensure_ascii=False).encode()
    preview = an.post(f"/api/plans/{topic_id}/import", files={"file": ("plan.json", eleven)}).json()
    assert "Ngày 1 có 11 ý tưởng, tối đa 10" in preview["errors"]


def test_a_plan_kept_at_four_a_day_is_unchanged(an, topic_id):
    path = f"/api/plans/{topic_id}"
    four = json.dumps(sample_plan(per_day=4), ensure_ascii=False).encode()
    preview = an.post(f"{path}/import", files={"file": ("plan.json", four)}).json()
    an.put(f"{path}/items", json={"ideas": preview["ideas"]})
    plan = an.patch(path, json={"per_day": 4}).json()
    assert plan["per_day"] == 4 and len(plan["items"]) == 120
    assert all(len(ideas_of(plan, day)) == 4 for day in range(1, 31))
    assert add(an, topic_id, 1, "Ý tưởng thứ năm").status_code == 201


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
        "Dòng 5: ngày không phải số",
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
        "File CSV cần dòng tiêu đề có cột chủ đề (topic), thêm cột ngày (day) nếu là kế hoạch"
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
        "suggested_post_at": None,  # the plan has no start date
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


def test_today_lists_the_ideas_of_today_for_groups_with_a_running_plan(an, db, me, topic_id):
    my_page(db, me, topic_id)
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


def test_today_tells_up_to_which_day_videos_are_made_ahead(an, db, me, storage, topic_id):
    my_page(db, me, topic_id)
    start = plans.today()
    an.patch(f"/api/plans/{topic_id}", json={"start_date": start.isoformat()})
    for day in (1, 2, 3):
        add(an, topic_id, day, f"Ngày {day}")
    [group] = an.get("/api/plans/today").json()
    assert group["prepared_through"] is None
    items = {item.topic: item for item in db.scalars(select(TopicPlanItem))}
    for name in ("Ngày 1", "Ngày 2"):
        items[name].video_id = make_video(db, storage, me, scene_count=1).id
    db.flush()
    [group] = an.get("/api/plans/today").json()
    assert group["prepared_through"] == 2


def my_page(db, owner, topic_id, name="Vườn nhà", active=True) -> Fanpage:
    row = page(db, name)
    row.owner_id, row.knowledge_topic_id, row.active = owner.id, topic_id, active
    db.flush()
    return row


def test_today_lists_only_the_groups_of_my_pages(client, db, topic_id):
    """A teammate's group with a running plan is not mine: no banner, no idea suggested for it."""
    an_ = make_user(db)
    binh = make_user(db, email="binh@doi.vn", name="Trần Thị Bình")
    other = KnowledgeTopic(name="Gan")
    db.add(other)
    db.flush()
    for group in (topic_id, other.id):
        db.add(TopicPlanItem(knowledge_topic_id=group, day=1, position=1, topic=f"Ý tưởng {group}"))
        db.get(KnowledgeTopic, group).plan_start_date = plans.today()
    my_page(db, an_, topic_id, "Trang An")
    my_page(db, binh, other.id, "Trang Bình")
    my_page(db, an_, other.id, "Trang cũ của An", active=False)  # a Page no longer used makes no group mine
    db.flush()
    login(client)
    assert [group["topic_id"] for group in client.get("/api/plans/today").json()] == [topic_id]
    login(client, "binh@doi.vn")
    assert [group["topic_id"] for group in client.get("/api/plans/today").json()] == [other.id]
    make_user(db, email="chi@doi.vn", name="Lê Chi")
    login(client, "chi@doi.vn")
    assert client.get("/api/plans/today").json() == []  # no Page, no banner


# --- The Backlog ---


def test_backlog_ideas_have_no_day_no_daily_limit_and_move_to_and_from_days(an, topic_id):
    for n in range(1, 13):
        assert add(an, topic_id, None, f"Để dành {n}").status_code == 201
    plan = an.get(f"/api/plans/{topic_id}").json()
    assert ideas_of(plan, None) == [f"Để dành {n}" for n in range(1, 13)]
    assert [item["position"] for item in plan["items"]] == list(range(1, 13))
    twice = add(an, topic_id, 4, "để dành 1")
    assert (twice.status_code, twice.json()["message"]) == (409, "Kế hoạch đã có chủ đề này (trong Backlog)")
    # A Backlog idea is not "made" in the 30-day progress.
    assert plan["made"] == 0

    first = plan["items"][0]["id"]
    moved = an.patch(f"/api/plans/items/{first}", json={"day": 3}).json()
    assert ideas_of(moved, 3) == ["Để dành 1"] and ideas_of(moved, None)[0] == "Để dành 2"
    assert [item["position"] for item in moved["items"] if item["day"] is None] == list(range(1, 12))
    back = an.patch(f"/api/plans/items/{first}", json={"day": None}).json()
    assert ideas_of(back, 3) == [] and ideas_of(back, None)[-1] == "Để dành 1"

    for n in range(1, 11):
        add(an, topic_id, 7, f"Ngày 7 số {n}")
    full = an.patch(f"/api/plans/items/{first}", json={"day": 7})
    assert (full.status_code, full.json()["message"]) == (409, "Ngày 7 đã đủ 10 ý tưởng")


def test_saving_a_plan_keeps_the_backlog_but_takes_an_idea_it_now_plans(an, db, me, storage, topic_id):
    add(an, topic_id, None, "Còn để dành")
    plan = add(an, topic_id, None, "Sẽ vào ngày 2").json()
    video = make_video(db, storage, me, scene_count=1)
    db.get(TopicPlanItem, plan["items"][1]["id"]).video_id = video.id
    db.flush()
    add(an, topic_id, 1, "Ngày 1 cũ")
    ideas = [{"day": 1, "topic": "Ngày 1 mới"}, {"day": 2, "topic": "sẽ vào ngày 2"}]
    saved = an.put(f"/api/plans/{topic_id}/items", json={"ideas": ideas}).json()
    assert {item["topic"]: (item["day"], item["video_id"]) for item in saved["items"]} == {
        "Ngày 1 mới": (1, None),
        "sẽ vào ngày 2": (2, video.id),
        "Còn để dành": (None, None),
    }
    undated = an.put(f"/api/plans/{topic_id}/items", json={"ideas": [{"topic": "Không ngày"}]})
    assert undated.json()["message"] == "1 ý tưởng chưa có ngày (chỉ thêm được vào Backlog), ví dụ “Không ngày”"


def test_a_file_without_days_goes_into_the_backlog_skipping_topics_already_there(an, topic_id):
    add(an, topic_id, 1, "Món A")
    data = "Chủ đề;Góc hook\nMón A;h\nMón B;h2\nmón b;\nMón C;".encode()
    preview = an.post(f"/api/plans/{topic_id}/import", files={"file": ("y.csv", data)}).json()
    assert [idea["day"] for idea in preview["ideas"]] == [None, None, None, None]
    assert preview["errors"][0].startswith("4 ý tưởng chưa có ngày") and preview["can_backlog"] is True
    added = an.post(f"/api/plans/{topic_id}/backlog", json={"ideas": preview["ideas"]}).json()
    assert (added["added"], added["skipped"]) == (2, 2)
    assert ideas_of(added, None) == ["Món B", "Món C"] and ideas_of(added, 1) == ["Món A"]
    # A day in the file does not matter for the Backlog.
    dated = an.post(f"/api/plans/{topic_id}/backlog", json={"ideas": [{"day": 5, "topic": "Món D"}]}).json()
    assert ideas_of(dated, None) == ["Món B", "Món C", "Món D"]
    broken = "Chủ đề;Ngày\nMón E;ba".encode()
    assert an.post(f"/api/plans/{topic_id}/import", files={"file": ("y.csv", broken)}).json()["can_backlog"] is False


# --- Posting times and the status of posts ---


def test_posting_times_are_checked_and_sorted(an, topic_id):
    path = f"/api/plans/{topic_id}"
    assert an.get(path).json()["post_times"] == ["07:00", "11:30", "17:00", "20:00", "21:30"]
    assert an.patch(path, json={"post_times": ["20:00", "7:05"]}).json()["post_times"] == ["07:05", "20:00"]
    assert an.patch(path, json={"post_times": ["25:00"]}).json()["message"] == "Giờ đăng “25:00” phải có dạng HH:MM"
    assert an.patch(path, json={"post_times": []}).json()["message"] == "Cần từ 1 đến 10 giờ đăng"
    eleven = [f"{hour:02d}:00" for hour in range(6, 17)]
    assert an.patch(path, json={"post_times": eleven}).json()["message"] == "Cần từ 1 đến 10 giờ đăng"
    assert len(an.patch(path, json={"post_times": eleven[:10]}).json()["post_times"]) == 10


def test_an_idea_is_suggested_to_go_out_on_its_day_at_the_time_of_its_place(an, db, topic_id):
    start = plans.today() + timedelta(days=1)
    an.patch(f"/api/plans/{topic_id}", json={"start_date": start.isoformat(), "post_times": ["08:00", "19:30"]})
    for n in range(1, 4):
        add(an, topic_id, 2, f"Ngày 2 số {n}")
    plan = add(an, topic_id, None, "Để dành").json()
    second_day = start + timedelta(days=1)
    at = {item["topic"]: item["suggested_post_at"] for item in plan["items"]}
    assert at == {
        "Ngày 2 số 1": datetime(*second_day.timetuple()[:3], 8, 0, tzinfo=plans.VIETNAM).isoformat(),
        "Ngày 2 số 2": datetime(*second_day.timetuple()[:3], 19, 30, tzinfo=plans.VIETNAM).isoformat(),
        # Past the posting times: the last one.
        "Ngày 2 số 3": datetime(*second_day.timetuple()[:3], 19, 30, tzinfo=plans.VIETNAM).isoformat(),
        "Để dành": None,
    }
    item = db.scalar(select(TopicPlanItem).where(TopicPlanItem.topic == "Ngày 2 số 1"))
    topic = db.get(KnowledgeTopic, topic_id)
    late = datetime(*second_day.timetuple()[:3], 9, 0, tzinfo=plans.VIETNAM)
    assert plans.suggested_post_at(topic, item, now=late) is None

    body = {"topic": "Ngày 2 số 1", "knowledge_topic_id": topic_id, "plan_item_id": item.id}
    video = an.post("/api/videos", json=body).json()
    assert video["plan_idea"]["suggested_post_at"] == at["Ngày 2 số 1"]


def test_an_idea_shows_when_its_video_is_scheduled_and_posted(an, db, me, storage, topic_id):
    plan = add(an, topic_id, 1, "Món A").json()
    video = make_video(db, storage, me, scene_count=1)
    db.get(TopicPlanItem, plan["items"][0]["id"]).video_id = video.id
    later = datetime(2030, 1, 2, 20, 0, tzinfo=plans.VIETNAM)
    post = Publication(
        video_id=video.id, platform="facebook", created_by_id=me.id, status="scheduled", scheduled_at=later
    )
    db.add(post)
    db.flush()
    item = an.get(f"/api/plans/{topic_id}").json()["items"][0]
    assert (item["status"], item["status_label"]) == ("scheduled", "Đã lên lịch")
    assert datetime.fromisoformat(item["post_at"]) == later
    post.status, post.published_at = "published", later
    db.flush()
    item = an.get(f"/api/plans/{topic_id}").json()["items"][0]
    assert (item["status"], item["status_label"], item["suggested_post_at"]) == ("posted", "Đã đăng", None)
    post.status = "cancelled"
    db.flush()
    assert an.get(f"/api/plans/{topic_id}").json()["items"][0]["status"] in ("started", "scripted", "done")


# --- 48-hour numbers on the cards, and the trial's video target ---


def page(db, name="Vườn nhà") -> Fanpage:
    row = Fanpage(page_id=f"p-{name}", name=name, token_encrypted="x", token_tail="x")
    db.add(row)
    db.flush()
    return row


def live_post(db, me, video, fanpage, views=None, shares=None, platform="facebook", days_ago=3) -> Publication:
    at = datetime.now(plans.VIETNAM) - timedelta(days=days_ago)
    post = Publication(
        video_id=video.id,
        platform=platform,
        fanpage_id=fanpage.id if fanpage else None,
        created_by_id=me.id,
        status="published",
        published_at=at,
    )
    db.add(post)
    db.flush()
    if views is not None:
        db.add(PostMetrics(publication_id=post.id, window="48h", views=views, shares=shares, measured_at=at))
        # `latest` must never stand in for the 48-hour reading.
        db.add(PostMetrics(publication_id=post.id, window="latest", views=views * 9, shares=0, measured_at=at))
        db.flush()
    return post


def test_cards_carry_the_48_hour_numbers_of_each_facebook_post(an, db, me, storage, topic_id, monkeypatch):
    garden = page(db)
    # Five other posts of the Page make its median meaningful: 100 views.
    for _ in range(5):
        live_post(db, me, make_video(db, storage, me, scene_count=1), garden, views=100, shares=1)
    ideas = {}
    for name in ("Đã đo", "Chưa đo", "Chưa đăng", "Không video"):
        ideas[name] = add(an, topic_id, 1, name).json()
    items = {item.topic: item for item in db.scalars(select(TopicPlanItem))}
    measured, waiting, unposted = (make_video(db, storage, me, scene_count=1) for _ in range(3))
    items["Đã đo"].video_id, items["Chưa đo"].video_id, items["Chưa đăng"].video_id = (
        measured.id,
        waiting.id,
        unposted.id,
    )
    db.flush()
    measured_post = live_post(db, me, measured, garden, views=1200, shares=6)
    live_post(db, me, measured, None, views=50, platform="tiktok")
    waiting_post = live_post(db, me, waiting, garden, days_ago=1)

    calls = []
    real = analytics.medians
    monkeypatch.setattr(analytics, "medians", lambda db: calls.append(1) or real(db))
    plan = an.get(f"/api/plans/{topic_id}").json()
    assert len(calls) == 1  # the medians are read once for the whole plan
    assert plan["share_goal"] == analytics.SHARE_GOAL
    posts = {item["topic"]: item["posts"] for item in plan["items"]}
    [done] = posts["Đã đo"]  # the TikTok post is left out
    assert done == {
        "publication_id": measured_post.id,
        "fanpage_name": "Vườn nhà",
        "views": 1200,
        "shares": 6,
        "latest_views": 10800,  # the newest reading, beside the 48-hour one, never in its place
        "measured_at": done["measured_at"],
        "median_views": 100,
        "samples": 6,  # the five others and this one
        "times_median": 12.0,
        "share_rate": 0.005,
    }
    [pending] = posts["Chưa đo"]
    assert pending["publication_id"] == waiting_post.id
    assert (pending["views"], pending["shares"], pending["times_median"], pending["share_rate"]) == (None,) * 4
    assert pending["latest_views"] is None
    assert posts["Chưa đăng"] == [] and posts["Không video"] == []


def test_the_video_target_is_set_cleared_and_counted(an, db, me, storage, topic_id):
    path = f"/api/plans/{topic_id}"
    plan = an.get(path).json()
    assert (plan["video_target"], plan["video_count"]) == (None, 0)
    for _ in range(2):
        make_video(db, storage, me, scene_count=1).knowledge_topic_id = topic_id
    db.flush()
    plan = an.patch(path, json={"video_target": 6}).json()
    assert (plan["video_target"], plan["video_count"]) == (6, 2)
    for wrong in (0, -1):
        refused = an.patch(path, json={"video_target": wrong})
        assert (refused.status_code, refused.json()["message"]) == (422, "Số video mục tiêu phải từ 1 trở lên")
    # Another field alone leaves the target as it is; null clears it.
    assert an.patch(path, json={"per_day": 3}).json()["video_target"] == 6
    assert an.patch(path, json={"video_target": None}).json()["video_target"] is None


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


def test_the_plan_job_writes_two_ideas_a_day_when_the_plan_asks_for_two(committed, tmp_path):
    user = add_user(committed)
    with committed() as db:
        first_topic(db).plan_per_day = 2
        db.commit()
    prompts = []
    job = run_plan(committed, tmp_path, user, plan_call(prompts))
    assert job.status == "done" and "mỗi ngày đúng 2 ý tưởng" in prompts[0]
    with committed() as db:
        ideas = first_topic(db).plan_draft["ideas"]
        assert len(ideas) == 60 and {idea["day"] for idea in ideas} == set(range(1, 31))


def test_an_unusable_plan_answer_is_asked_once_more_then_fails(committed, tmp_path):
    user = add_user(committed)
    missing_day = json.dumps(plan_json(1, 9))
    job = run_plan(committed, tmp_path, user, plan_call([], ["không phải JSON", missing_day]))
    assert (job.status, job.claude_calls) == ("failed", 2)
    assert job.error == "AI trả kế hoạch ngày 1–10 không đúng định dạng (thiếu ý tưởng cho ngày 10), đã thử lại 1 lần"
    with committed() as db:
        assert first_topic(db).plan_draft is None


def test_a_plan_answer_is_repaired_where_it_can_be():
    answer = plan_json(1, 10, per_day=11)
    answer["days"][0]["ideas"][0]["topic"] = "Đã có"
    answer["days"][1]["ideas"][0]["hook"] = "h" * 900
    answer["days"].append({"day": 11, "ideas": [{"topic": "Ngày khác"}]})
    ideas = plans.parse_output("Đây là kế hoạch: " + json.dumps(answer), 1, 10, {"đã có"})
    assert len(ideas) == 100 and "Đã có" not in [idea.topic for idea in ideas]
    assert max(len(idea.hook) for idea in ideas) == plans.MAX_HOOK_LENGTH
    assert all(idea.day <= 10 for idea in ideas)


# --- Import modes (brief docs/specs/nap-ke-hoach-tuy-chon) ---


def seed_days(an, topic_id, days, per_day=1) -> dict:
    """A plan whose `days` hold `per_day` ideas each, "Cũ d.n"."""
    ideas = [{"day": day, "topic": f"Cũ {day}.{n}"} for day in days for n in range(1, per_day + 1)]
    return an.put(f"/api/plans/{topic_id}/items", json={"ideas": ideas}).json()


def apply(an, topic_id, mode, ideas, fit=False):
    return an.post(f"/api/plans/{topic_id}/apply", json={"mode": mode, "ideas": ideas, "fit": fit})


def snapshot(plan, days) -> dict:
    """Every field of the ideas of `days`, to show they did not change by one character."""
    keep = ("id", "day", "position", "topic", "pain_group", "pain", "hook", "video_id")
    return {day: [{key: item[key] for key in keep} for item in plan["items"] if item["day"] == day] for day in days}


def test_overwrite_mode_saves_the_plan_exactly_as_lưu_kế_hoạch_does(an, topic_id):
    seed_days(an, topic_id, range(1, 15))
    ideas = [{"day": day, "topic": f"Mới {day}"} for day in range(1, 15)]
    response = apply(an, topic_id, "overwrite", ideas)
    assert response.status_code == 200, response.text
    plan = response.json()
    assert [(item["day"], item["topic"], item["position"]) for item in plan["items"]] == [
        (day, f"Mới {day}", 1) for day in range(1, 15)
    ]
    report = plan["report"]
    assert (report["mode"], report["replaced"], report["filled"], report["appended"]) == (
        "overwrite",
        list(range(1, 15)),
        [],
        [],
    )
    assert report["days"] == list(range(1, 15)) and report["duplicates"] == [] and report["not_loaded"] == []


def test_append_mode_adds_to_the_end_of_the_days_in_the_file_and_fills_empty_ones(an, topic_id):
    before = seed_days(an, topic_id, [day for day in range(1, 15) if day != 9])
    ideas = [
        {"day": 4, "topic": "Mới 4", "pain": "đau", "hook": "móc"},
        {"day": 7, "topic": "Mới 7a"},
        {"day": 7, "topic": "Mới 7b"},
        {"day": 9, "topic": "Mới 9"},
    ]
    plan = apply(an, topic_id, "append", ideas).json()
    assert ideas_of(plan, 4) == ["Cũ 4.1", "Mới 4"]
    assert ideas_of(plan, 7) == ["Cũ 7.1", "Mới 7a", "Mới 7b"]
    assert ideas_of(plan, 9) == ["Mới 9"]
    added = next(item for item in plan["items"] if item["topic"] == "Mới 4")
    assert (added["position"], added["pain"], added["hook"]) == (2, "đau", "móc")
    untouched = [day for day in range(1, 15) if day not in (4, 7, 9)]
    assert snapshot(plan, untouched) == snapshot(before, untouched)
    # The ideas already on days 4 and 7 keep their row and place.
    assert snapshot(plan, [4])[4][0] == snapshot(before, [4])[4][0]
    report = plan["report"]
    assert (report["filled"], report["appended"], report["days"]) == ([9], [4, 7], [4, 7, 9])


def test_append_mode_skips_a_topic_the_plan_already_has_and_reports_it(an, db, me, storage, topic_id):
    seed_days(an, topic_id, [1, 2, 3])
    plan = add(an, topic_id, None, "Để dành").json()
    video = make_video(db, storage, me, scene_count=1)
    db.get(TopicPlanItem, next(item["id"] for item in plan["items"] if item["day"] is None)).video_id = video.id
    db.flush()
    ideas = [
        {"day": 1, "topic": "  cũ 1.1 "},  # the same day already has it
        {"day": 1, "topic": "Cũ 2.1"},  # day 2 has it: a topic is never twice in a plan
        {"day": 1, "topic": "Mới 1"},
        {"day": 3, "topic": "để dành", "hook": "móc mới"},  # from the Backlog onto day 3, with its video
    ]
    plan = apply(an, topic_id, "append", ideas).json()
    assert ideas_of(plan, 1) == ["Cũ 1.1", "Mới 1"]
    assert ideas_of(plan, 2) == ["Cũ 2.1"]
    assert ideas_of(plan, 3) == ["Cũ 3.1", "để dành"] and ideas_of(plan, None) == []
    moved = next(item for item in plan["items"] if item["day"] == 3 and item["position"] == 2)
    assert (moved["video_id"], moved["hook"]) == (video.id, "móc mới")
    assert plan["report"]["duplicates"] == [
        {"topic": "cũ 1.1", "day": 1, "where": "ngày 1"},
        {"topic": "Cũ 2.1", "day": 1, "where": "ngày 2"},
    ]
    assert plan["report"]["appended"] == [1, 3]


def test_append_mode_stops_at_ten_ideas_a_day_and_says_which_were_left_out(an, topic_id):
    seed_days(an, topic_id, [5], per_day=9)
    plan = apply(an, topic_id, "append", [{"day": 5, "topic": "Mới a"}, {"day": 5, "topic": "Mới b"}]).json()
    assert len(ideas_of(plan, 5)) == 10 and ideas_of(plan, 5)[-1] == "Mới a"
    assert plan["report"]["full"] == [{"topic": "Mới b", "day": 5}]


def test_next_empty_mode_fills_the_first_empty_days_in_the_files_order(an, topic_id):
    before = seed_days(an, topic_id, range(1, 15))
    ideas = [{"day": day, "topic": f"Đợt 2 ngày {day}"} for day in (3, 1, 2, 5, 4)]
    plan = apply(an, topic_id, "next_empty", ideas).json()
    assert {day: ideas_of(plan, day) for day in range(15, 21)} == {
        15: ["Đợt 2 ngày 1"],
        16: ["Đợt 2 ngày 2"],
        17: ["Đợt 2 ngày 3"],
        18: ["Đợt 2 ngày 4"],
        19: ["Đợt 2 ngày 5"],
        20: [],
    }
    assert snapshot(plan, range(1, 15)) == snapshot(before, range(1, 15))
    report = plan["report"]
    assert report["filled"] == [15, 16, 17, 18, 19]
    assert report["placed"] == [[1, 15], [2, 16], [3, 17], [4, 18], [5, 19]]


def test_next_empty_mode_uses_a_gap_first(an, topic_id):
    seed_days(an, topic_id, [1, 2, 4])
    plan = apply(an, topic_id, "next_empty", [{"day": 1, "topic": "A"}, {"day": 2, "topic": "B"}]).json()
    assert (ideas_of(plan, 3), ideas_of(plan, 5)) == (["A"], ["B"])


def test_next_empty_mode_without_room_asks_first_and_fits_only_when_told(an, topic_id):
    before = seed_days(an, topic_id, range(1, 29))
    ideas = [{"day": day, "topic": f"Đợt 2 ngày {day}"} for day in range(1, 6)]
    refused = apply(an, topic_id, "next_empty", ideas)
    assert (refused.status_code, refused.json()["message"]) == (
        409,
        "Còn 2 ngày trống, file có 5 ngày",
    )
    assert an.get(f"/api/plans/{topic_id}").json()["items"] == before["items"]

    plan = apply(an, topic_id, "next_empty", ideas, fit=True).json()
    assert (ideas_of(plan, 29), ideas_of(plan, 30)) == (["Đợt 2 ngày 1"], ["Đợt 2 ngày 2"])
    assert plan["report"]["not_loaded"] == [3, 4, 5]


def test_replace_days_mode_replaces_only_the_days_in_the_file_and_keeps_their_videos(an, db, me, storage, topic_id):
    before = seed_days(an, topic_id, range(1, 15), per_day=2)
    four = next(item for item in before["items"] if item["topic"] == "Cũ 4.1")
    seven = next(item for item in before["items"] if item["topic"] == "Cũ 7.2")
    made = make_video(db, storage, me, scene_count=1)
    kept = make_video(db, storage, me, scene_count=1)
    db.get(TopicPlanItem, four["id"]).video_id = made.id
    db.get(TopicPlanItem, seven["id"]).video_id = kept.id
    db.flush()
    ideas = [
        {"day": 4, "topic": "Thay 4"},
        {"day": 7, "topic": "cũ 7.2", "hook": "móc mới"},  # the same topic keeps its video
        {"day": 7, "topic": "Thay 7"},
        {"day": 9, "topic": "Thay 9"},
        {"day": 9, "topic": "Cũ 10.1"},  # day 10 is not replaced and keeps it
    ]
    plan = apply(an, topic_id, "replace_days", ideas).json()
    assert ideas_of(plan, 4) == ["Thay 4"]
    assert ideas_of(plan, 7) == ["cũ 7.2", "Thay 7"]
    assert ideas_of(plan, 9) == ["Thay 9"]
    assert next(item for item in plan["items"] if item["day"] == 7)["video_id"] == kept.id
    untouched = [day for day in range(1, 15) if day not in (4, 7, 9)]
    assert snapshot(plan, untouched) == snapshot(before, untouched)
    # Loading a plan never deletes a video: the one of the replaced idea stays in the library.
    db.expire_all()
    assert db.get(Video, made.id) is not None
    report = plan["report"]
    assert (report["replaced"], report["days"]) == ([4, 7, 9], [4, 7, 9])
    assert report["duplicates"] == [{"topic": "Cũ 10.1", "day": 9, "where": "ngày 10"}]


def test_replace_days_mode_does_not_delete_a_teammates_ideas(client, db, topic_id):
    make_user(db)
    make_user(db, email="binh@doi.vn", name="Bình")
    login(client)
    seed_days(client, topic_id, [4])
    login(client, "binh@doi.vn")
    refused = apply(client, topic_id, "replace_days", [{"day": 4, "topic": "Thay 4"}])
    assert refused.status_code == 409
    assert ideas_of(client.get(f"/api/plans/{topic_id}").json(), 4) == ["Cũ 4.1"]


def test_a_mode_checks_the_file_as_saving_a_plan_does(an, topic_id):
    assert apply(an, topic_id, "sideways", [{"day": 1, "topic": "A"}]).status_code == 422
    twice = apply(an, topic_id, "append", [{"day": 1, "topic": "A"}, {"day": 2, "topic": "a"}])
    assert twice.status_code == 422 and twice.json()["message"].startswith("Chủ đề trùng")
    undated = apply(an, topic_id, "next_empty", [{"topic": "A"}])
    assert undated.status_code == 422
