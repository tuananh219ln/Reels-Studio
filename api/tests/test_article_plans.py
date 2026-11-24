"""A Page's 30-day plan of article scripts (decisions 2026-11-15, "article plan"): its settings, the slots and the
Backlog, moving and deleting scripts, a CSV/JSON file previewed then saved, and an article made from a script."""

import json
from datetime import timedelta

import pytest
from conftest import first_topic, login, make_user
from fake_services import FACEBOOK_PAGE, FACEBOOK_TOKEN
from sqlalchemy import select

from reels_api import article_plans, fanpages
from reels_api.models import Article, ArticlePlan, ArticlePlanSlot, Publication

CSV_HEAD = "day,slot,hook,body,cta,hashtags,image_brief,format,topic_group\n"


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


@pytest.fixture
def page(db, me) -> int:
    row = fanpages.save(db, FACEBOOK_PAGE, "Ăn Ngon Sống Khỏe", FACEBOOK_TOKEN, me.id)
    db.commit()
    return row.id


def set_up(an, page, per_day=3, times=("07:00", "11:30", "20:00"), start=None) -> dict:
    start = start or article_plans.today()
    response = an.put(
        f"/api/article-plans/{page}/settings",
        json={"start_date": start.isoformat(), "per_day": per_day, "post_times": list(times)},
    )
    assert response.status_code == 200, response.text
    return response.json()


def add(an, page, hook, day=None, slot=None, **fields) -> dict:
    response = an.post(
        f"/api/article-plans/{page}/slots", json={"hook": hook, "body": "Nội dung", "day": day, "slot": slot, **fields}
    )
    assert response.status_code == 201, response.text
    return response.json()


def upload(an, page, text, name="ke-hoach.csv", placement="by_day_slot", conflict="to_backlog"):
    return an.post(
        f"/api/article-plans/{page}/import",
        files={"file": (name, text.encode(), "text/csv")},
        data={"placement": placement, "conflict": conflict},
    )


def cell_of(plan: dict, day: int, slot: int) -> dict | None:
    return next((row for row in plan["slots"] if row["day"] == day and row["slot"] == slot), None)


# --- Settings ---


def test_settings_make_the_plan_and_check_the_posting_times(an, page):
    before = an.get(f"/api/article-plans/{page}").json()
    assert before["plan"] is None and before["can_edit"] is True
    plan = set_up(an, page)["plan"]
    assert (plan["per_day"], plan["post_times"], plan["total"], plan["today_day"]) == (
        3,
        ["07:00", "11:30", "20:00"],
        90,
        1,
    )
    assert (plan["used"], plan["empty_days"], plan["backlog"]) == (0, 30, 0)
    for wrong in (
        {"per_day": 2, "post_times": ["07:00", "11:30", "20:00"]},
        {"per_day": 2, "post_times": ["20:00", "20:00"]},
        {"per_day": 11, "post_times": [f"{hour:02d}:00" for hour in range(11)]},
        {"per_day": 3, "post_times": ["07:00", "11:30", "20:00"], "start_date": None},
    ):
        body = {"start_date": article_plans.today().isoformat(), **wrong}
        assert an.put(f"/api/article-plans/{page}/settings", json=body).status_code == 422, wrong
    # Times typed out of order are kept in the order of the day.
    plan = set_up(an, page, per_day=2, times=("20:00", "07:00"))["plan"]
    assert plan["post_times"] == ["07:00", "20:00"]


def test_only_the_page_owner_changes_the_plan_but_everyone_reads_it(an, client, db, page):
    set_up(an, page)
    make_user(db, email="binh@doi.vn", name="Bình")
    login(client, "binh@doi.vn")
    shown = client.get(f"/api/article-plans/{page}").json()
    assert shown["can_edit"] is False and shown["plan"]["per_day"] == 3
    refused = client.post(f"/api/article-plans/{page}/slots", json={"hook": "Thử"})
    assert refused.status_code == 403 and "chủ Page" in refused.json()["message"]


def test_fewer_posts_a_day_moves_the_dropped_slots_to_the_backlog(an, page):
    set_up(an, page)
    add(an, page, "Khung ba", day=1, slot=3)
    add(an, page, "Khung một", day=1, slot=1)
    plan = set_up(an, page, per_day=2, times=("07:00", "20:00"))
    assert plan["moved_to_backlog"] == 1
    assert [row["hook"] for row in plan["backlog"]] == ["Khung ba"]
    assert cell_of(plan, 1, 1)["hook"] == "Khung một"
    assert plan["plan"]["post_times"] == ["07:00", "20:00"]


# --- Slots ---


def test_a_slot_is_taken_once_moved_with_a_swap_skipped_and_deleted_unless_used(an, db, page):
    set_up(an, page)
    first = add(an, page, "Một", day=1, slot=1)
    assert an.post(f"/api/article-plans/{page}/slots", json={"hook": "Hai", "day": 1, "slot": 1}).status_code == 409
    second = add(an, page, "Hai", day=2, slot=1)
    one = cell_of(first, 1, 1)
    two = cell_of(second, 2, 1)
    swapped = an.patch(f"/api/article-plans/slots/{one['id']}", json={"day": 2, "slot": 1}).json()
    assert cell_of(swapped, 2, 1)["hook"] == "Một" and cell_of(swapped, 1, 1)["hook"] == "Hai"
    parked = an.patch(f"/api/article-plans/slots/{two['id']}", json={"day": None, "slot": None}).json()
    assert [row["hook"] for row in parked["backlog"]] == ["Hai"]
    skipped = an.patch(f"/api/article-plans/slots/{one['id']}", json={"skipped": True}).json()
    assert cell_of(skipped, 2, 1)["status_label"] == "Bỏ qua"

    made = an.post("/api/articles", json={"plan_slot_id": two["id"]}).json()
    removed = an.post(f"/api/article-plans/{page}/slots/delete", json={"ids": [one["id"], two["id"]]}).json()
    assert (removed["deleted"], removed["kept"]) == (1, 1)
    assert [row["article_id"] for row in removed["backlog"]] == [made["id"]]


def test_an_article_from_a_script_is_filled_from_it_and_freed_when_deleted(an, db, page):
    set_up(an, page)
    group = first_topic(db)
    shown = add(
        an,
        page,
        "Bữa sáng 10 phút cho dân văn phòng",
        day=1,
        slot=2,
        body="Sáng nào cũng vội?",
        cta="Bạn hay ăn sáng món gì?",
        hashtags=["ansang", "#suckhoe"],
        image_brief="Bàn ăn sáng gọn",
        kind="meo",
        knowledge_topic_id=group.id,
    )
    assert shown["next_slot_id"] == cell_of(shown, 1, 2)["id"]
    slot_id = cell_of(shown, 1, 2)["id"]
    made = an.post("/api/articles", json={"plan_slot_id": slot_id})
    assert made.status_code == 201, made.text
    article = made.json()
    assert article["caption"] == "Bữa sáng 10 phút cho dân văn phòng\n\nSáng nào cũng vội?\n\nBạn hay ăn sáng món gì?"
    assert (article["hashtags"], article["kind"], article["knowledge_topic_id"]) == (
        ["#ansang", "#suckhoe"],
        "meo",
        group.id,
    )
    assert article["image_query"] == "Bàn ăn sáng gọn"
    link = article["plan_slot"]
    assert (link["day"], link["slot"], link["fanpage_id"]) == (1, 2, page)
    assert link["post_at"].endswith("11:30:00+07:00")
    again = an.post("/api/articles", json={"plan_slot_id": slot_id})
    assert again.status_code == 409

    plan = an.get(f"/api/article-plans/{page}").json()
    assert cell_of(plan, 1, 2)["status_label"] == "Đã tạo bài" and plan["plan"]["used"] == 1
    assert plan["next_slot_id"] is None
    # Scheduled on Facebook: the slot follows its post.
    db.add(
        Publication(
            article_id=article["id"],
            platform="facebook",
            fanpage_id=page,
            status="scheduled",
            scheduled_at=article_plans.slot_time(db.scalar(select(ArticlePlan)), 1, 2) + timedelta(days=1),
            created_by_id=article["created_by_id"],
        )
    )
    db.commit()
    plan = an.get(f"/api/article-plans/{page}").json()
    assert cell_of(plan, 1, 2)["status_label"] == "Đã hẹn giờ" and plan["plan"]["scheduled"] == 1
    db.execute(Publication.__table__.delete())
    db.commit()
    assert an.delete(f"/api/articles/{article['id']}").json() == {"ok": True}
    assert cell_of(an.get(f"/api/article-plans/{page}").json(), 1, 2)["status_label"] == "Chưa dùng"


# --- Files ---


def test_a_file_is_previewed_with_its_errors_and_written_only_on_save(an, db, page):
    set_up(an, page)
    group = first_topic(db).name
    text = CSV_HEAD + "\n".join(
        [
            f"1,1,Ăn trưa no căng,Nội dung,,#suckhoe,,Kiến thức ngắn,{group}",
            f"1,2,3 loại rau,Nội dung,,,,Danh sách,{group}",
            "2,2,Thiếu body,,,,,Mẹo,",
            "2,2,Trùng ô,Nội dung,,,,Mẹo,",
            ",,Uống nước lúc nào?,Nội dung,,,,Kiến thức ngắn,",
            "3,1,Dạng lạ,Nội dung,,,,Thử thách,",
            "3,2,Nhóm lạ,Nội dung,,,,Mẹo,Không có",
        ]
    )
    preview = upload(an, page, text)
    assert preview.status_code == 200, preview.text
    rows = preview.json()["rows"]
    assert [row["check"] for row in rows] == ["ok", "ok", "error", "ok", "ok", "error", "error"]
    assert rows[2]["errors"] == ["Thiếu body"]
    assert rows[5]["errors"] == ["Dạng bài “Thử thách” không tồn tại"]
    assert rows[6]["errors"] == ["Nhóm chủ đề “Không có” không tồn tại"]
    assert rows[4]["target"] == "backlog"
    assert preview.json()["counts"] == {"ok": 4, "warning": 0, "error": 3, "backlog": 1}
    # Nothing is written by the preview.
    assert db.scalar(select(ArticlePlanSlot.id)) is None

    saved = an.post(f"/api/article-plans/{page}/import/apply", json={"rows": rows}).json()
    assert saved["report"] == {"placed": 3, "backlog": 1, "moved_to_backlog": 0, "replaced": 0, "skipped": 3}
    assert cell_of(saved, 1, 1)["kind"] == "kien_thuc" and cell_of(saved, 1, 2)["kind"] == "checklist"
    assert cell_of(saved, 1, 1)["hashtags"] == ["#suckhoe"] and cell_of(saved, 1, 1)["source"] == "import"
    assert [row["hook"] for row in saved["backlog"]] == ["Uống nước lúc nào?"]


def test_a_rows_error_is_found_again_when_saving(an, page):
    set_up(an, page)
    rows = upload(an, page, CSV_HEAD + "1,1,Hợp lệ,Nội dung,,,,,").json()["rows"]
    rows[0]["body"] = ""
    saved = an.post(f"/api/article-plans/{page}/import/apply", json={"rows": rows}).json()
    assert saved["report"]["skipped"] == 1 and saved["slots"] == []


def test_a_taken_slot_sends_the_old_script_to_the_backlog_by_default(an, page):
    set_up(an, page)
    add(an, page, "Cũ", day=1, slot=1)
    rows = upload(an, page, CSV_HEAD + "1,1,Mới,Nội dung,,,,,").json()["rows"]
    assert rows[0]["note"] == "Ô đã có kịch bản → cũ vào Backlog"
    saved = an.post(f"/api/article-plans/{page}/import/apply", json={"rows": rows}).json()
    assert cell_of(saved, 1, 1)["hook"] == "Mới" and [row["hook"] for row in saved["backlog"]] == ["Cũ"]
    rows = upload(an, page, CSV_HEAD + "1,1,Mới hơn,Nội dung,,,,,", conflict="overwrite").json()["rows"]
    saved = an.post(f"/api/article-plans/{page}/import/apply", json={"rows": rows, "conflict": "overwrite"}).json()
    assert cell_of(saved, 1, 1)["hook"] == "Mới hơn" and saved["report"]["replaced"] == 1
    rows = upload(an, page, CSV_HEAD + "1,1,Bỏ,Nội dung,,,,,", conflict="skip").json()["rows"]
    saved = an.post(f"/api/article-plans/{page}/import/apply", json={"rows": rows, "conflict": "skip"}).json()
    assert cell_of(saved, 1, 1)["hook"] == "Mới hơn" and saved["report"]["skipped"] == 1


def test_json_rows_fill_the_empty_slots_in_order(an, page):
    set_up(an, page, per_day=1, times=("07:00",))
    add(an, page, "Có sẵn", day=1, slot=1)
    data = json.dumps(
        [{"hook": f"Bài {n}", "body": "Nội dung", "hashtags": ["#a"], "format": "meo"} for n in range(1, 4)]
    )
    preview = an.post(
        f"/api/article-plans/{page}/import",
        files={"file": ("ke-hoach.json", data.encode(), "application/json")},
        data={"placement": "fill_empty"},
    ).json()
    assert [row["target"] for row in preview["rows"]] == ["2:1", "3:1", "4:1"]


def test_a_hook_like_a_recent_post_on_the_page_is_a_warning(an, db, me, page):
    set_up(an, page)
    article = Article(
        knowledge_topic_id=first_topic(db).id,
        kind="meo",
        caption="Bữa sáng 10 phút cho dân văn phòng\n\nNội dung",
        created_by_id=me.id,
    )
    db.add(article)
    db.flush()
    db.add(
        Publication(
            article_id=article.id, platform="facebook", fanpage_id=page, status="published", created_by_id=me.id
        )
    )
    db.commit()
    rows = upload(an, page, CSV_HEAD + "1,1,Bữa sáng 10 phút cho dân văn phòng!,Nội dung,,,,,").json()["rows"]
    assert rows[0]["check"] == "warning" and rows[0]["warnings"][0].startswith("Gần giống bài đăng")


def test_a_file_that_cannot_be_read_says_why(an, page):
    set_up(an, page)
    assert "hook" in upload(an, page, "a,b\n1,2").json()["message"]
    assert (
        "UTF-8"
        in an.post(
            f"/api/article-plans/{page}/import", files={"file": ("x.csv", "hook\n".encode("utf-16"), "text/csv")}
        ).json()["message"]
    )
    assert ".csv hoặc .json" in upload(an, page, "hook,body", name="x.xlsx").json()["message"]


def test_the_template_files_are_read_back_as_valid_scripts(an, page):
    set_up(an, page)
    for kind, name in (("csv", "mau.csv"), ("json", "mau.json")):
        template = an.get("/api/article-plans/import-template", params={"format": kind})
        assert template.status_code == 200
        preview = an.post(
            f"/api/article-plans/{page}/import", files={"file": (name, template.content, "text/plain")}
        ).json()
        assert [row["check"] for row in preview["rows"]] == ["ok", "ok"], preview
