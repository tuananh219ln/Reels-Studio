"""'Bình luận ghim' of an article plan's scripts (decisions 2026-11-18, "pinned comments"): the checks, the file import
and its preview, the AI job, a member's edit, and the worker writing them under a posted article."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from conftest import first_topic, login, make_user
from fake_services import FACEBOOK_PAGE, FACEBOOK_TOKEN
from sqlalchemy import select

from reels_api import article_plans, fanpages, slot_comments
from reels_api.claude import ClaudeError
from reels_api.models import Article, ArticlePlan, ArticlePlanSlot, Job, PostComment, Publication

TEXTS = [
    "Cà rốt giàu beta-carotene, tốt cho đôi mắt và làn da của người ngoài 40 tuổi.",
    "Hấp hoặc xào nhẹ với chút dầu ăn để cơ thể hấp thu tốt hơn beta-carotene nhé.",
    "Mỗi ngày chỉ cần một củ vừa, ăn nhiều quá da có thể hơi ngả vàng đó bạn.",
    "Hợp với người hay làm việc với máy tính, mắt mỏi vào cuối ngày.",
    "Người đang dùng thuốc hoặc có bệnh nền nên hỏi bác sĩ trước khi ăn nhiều.",
]
TYPES = ["cong_dung", "cach_lam", "luu_y", "nen_dung", "han_che"]


def comments(count=5) -> list[dict]:
    return [{"type": TYPES[place], "text": TEXTS[place]} for place in range(count)]


# --- The checks (no database) ---


def test_five_good_comments_pass_with_the_pin_where_asked():
    checked = slot_comments.check(comments(), 2, "kien_thuc")
    assert checked.errors == [] and checked.warnings == []
    assert (len(checked.items), checked.pin_index) == (5, 2)


@pytest.mark.parametrize(
    "raw, fragment",
    [
        ("không phải mảng", "danh sách"),
        (comments(5) + [{"text": "x" * 30}], "Tối đa 5"),
        ([{"type": "cong_dung", "text": "   "}], "trống"),
        ([{"type": "cong_dung", "text": "x" * 1001}], "dài quá 1000"),
        ([{"type": "cong_dung", "text": "ngắn quá"}], "ngắn quá"),
        (["chuỗi thay vì object"], "dạng"),
    ],
)
def test_a_bad_list_is_an_error(raw, fragment):
    checked = slot_comments.check(raw)
    assert any(fragment in error for error in checked.errors), checked.errors


def test_pin_index_out_of_range_goes_to_zero_with_a_warning():
    checked = slot_comments.check(comments(), 7)
    assert checked.errors == [] and checked.pin_index == 0
    assert any("pin_index" in warning for warning in checked.warnings)


def test_an_unknown_label_and_fewer_than_five_only_warn():
    items = comments(3)
    items[1]["type"] = "la_hoac"
    checked = slot_comments.check(items)
    assert checked.errors == [] and len(checked.items) == 3
    assert any("la_hoac" in warning for warning in checked.warnings)
    assert "Thiếu 3/5" in checked.warnings


def test_a_promise_to_cure_is_warned_about():
    items = [{"type": "cong_dung", "text": "Món này chữa khỏi hẳn bệnh khớp sau vài tuần ăn đều đặn."}]
    assert any("chữa khỏi" in warning for warning in slot_comments.check(items).warnings)


def test_a_warning_post_uses_the_other_label_set():
    assert slot_comments.type_set("canh_bao") == slot_comments.TYPES_WARNING
    assert slot_comments.type_set("meo") == slot_comments.TYPES_FOOD
    assert slot_comments.type_set(None) == slot_comments.TYPES_FOOD


def test_a_csv_row_keeps_the_pin_on_its_column_when_a_cell_is_empty():
    record = {
        "cmt_1": TEXTS[0],
        "cmt_2": "",
        "cmt_3": TEXTS[2],
        "cmt_4": TEXTS[3],
        "cmt_5": "",
        "cmt_types": "cong_dung|cach_lam|luu_y|nen_dung|han_che",
        "pin_index": "2",
    }
    checked, _ = slot_comments.from_record(record)
    assert checked.errors == []
    assert [item["type"] for item in checked.items] == ["cong_dung", "luu_y", "nen_dung"]
    assert checked.pin_index == 1  # the third column, now second of three
    assert "Thiếu 3/5" in checked.warnings


def test_a_pin_on_an_empty_csv_cell_goes_to_the_first_comment():
    record = {"cmt_1": TEXTS[0], "cmt_2": "", "pin_index": "1"}
    checked, _ = slot_comments.from_record(record)
    assert checked.pin_index == 0 and any("pin_index" in warning for warning in checked.warnings)


def test_a_file_without_comments_has_none_and_no_warning():
    checked, shown = slot_comments.from_record({"hook": "Một câu mở"})
    assert (checked.items, checked.errors, checked.warnings, shown) == ([], [], [], [])


# --- The AI's answer (no database) ---


def answer(count=5, kind="kien_thuc") -> str:
    labels = slot_comments.type_set(kind)
    return json.dumps(
        {"pinned_comments": [{"type": labels[place], "text": TEXTS[place % 5]} for place in range(count)]},
        ensure_ascii=False,
    )


def test_the_answer_is_five_comments_in_the_order_of_the_label_set():
    parsed = slot_comments.parse_output(answer(kind="canh_bao"), "canh_bao")
    assert [item["type"] for item in parsed] == list(slot_comments.TYPES_WARNING)


def test_a_wrong_count_or_a_cure_promise_is_asked_again_and_the_third_failure_is_given_up():
    answers = iter([answer(4), answer().replace("tốt cho đôi mắt", "chữa khỏi đau mắt"), answer()])
    calls = []
    written = slot_comments.generate(
        "prompt", "kien_thuc", None, "job", lambda: calls.append(1), lambda *_: next(answers)
    )
    assert len(written) == 5 and len(calls) == 3
    with pytest.raises(ClaudeError) as error:
        slot_comments.generate("prompt", "kien_thuc", None, "job", lambda: None, lambda *_: answer(2))
    assert "3 lần" in error.value.message


def test_the_prompt_names_the_page_audience_and_label_set():
    prompt = slot_comments.build_prompt("Ăn Lành", "35–55 tuổi", "Cà rốt", "canh_bao", "Caption")
    assert 'Page "Ăn Lành"' in prompt and "35–55 tuổi" in prompt
    assert "tac_hai, thay_the, luu_y, can_tranh, an_it_hai" in prompt


# --- The plan: import, edit, bulk ---


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


def set_up(an, page) -> dict:
    response = an.put(
        f"/api/article-plans/{page}/settings",
        json={
            "start_date": article_plans.today().isoformat(),
            "per_day": 3,
            "post_times": ["07:00", "11:30", "20:00"],
            "audience": "35–55 tuổi",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def script(day, slot, hook, with_comments=True, **fields) -> dict:
    row = {"day": day, "slot": slot, "hook": hook, "body": "Nội dung bài viết", **fields}
    if with_comments:
        row["pinned_comments"] = comments()
    return row


def upload_json(an, page, rows, conflict="to_backlog"):
    return an.post(
        f"/api/article-plans/{page}/import",
        files={"file": ("ke-hoach.json", json.dumps(rows).encode(), "application/json")},
        data={"placement": "by_day_slot", "conflict": conflict},
    )


def apply_rows(an, page, preview, conflict="to_backlog"):
    return an.post(
        f"/api/article-plans/{page}/import/apply",
        json={"rows": preview["rows"], "placement": "by_day_slot", "conflict": conflict},
    )


def cell(plan: dict, day: int, slot: int) -> dict:
    return next(row for row in plan["slots"] if row["day"] == day and row["slot"] == slot)


def test_an_imported_script_keeps_its_five_comments_and_its_pin(an, page):
    set_up(an, page)
    rows = [script(3, 1, "Cà rốt giữ đôi mắt sáng", pin_index=2)]
    preview = upload_json(an, page, rows).json()
    row = preview["rows"][0]
    assert (row["action"], len(row["pinned_comments"]), row["check"]) == ("add", 5, "ok")
    saved = apply_rows(an, page, preview).json()
    slot = cell(saved, 3, 1)
    assert (slot["comments_count"], slot["pin_index"], slot["comments_source"]) == (5, 2, "import")
    assert slot["comments_edited"] is False
    assert [item["text"] for item in slot["pinned_comments"]] == TEXTS
    assert saved["plan"]["comments"] == {"full": 1, "total": 1}


def test_an_old_file_without_comments_still_imports(an, page):
    set_up(an, page)
    preview = upload_json(an, page, [script(1, 1, "Bài không bình luận", with_comments=False)]).json()
    assert preview["rows"][0]["pinned_comments"] == [] and preview["rows"][0]["check"] == "ok"
    slot = cell(apply_rows(an, page, preview).json(), 1, 1)
    assert (slot["comments_count"], slot["comments_source"]) == (0, None)


def test_the_preview_warns_of_fewer_than_five_and_stops_a_row_with_too_many(an, page):
    set_up(an, page)
    short = script(1, 1, "Ít bình luận")
    short["pinned_comments"] = comments(3)
    many = script(1, 2, "Quá nhiều")
    many["pinned_comments"] = comments() + comments(1)
    rows = upload_json(an, page, [short, many]).json()["rows"]
    assert (rows[0]["check"], "Thiếu 3/5" in rows[0]["warnings"]) == ("warning", True)
    assert rows[1]["check"] == "error" and any("Tối đa 5" in error for error in rows[1]["errors"])


def test_a_row_for_a_slot_with_an_article_is_skipped_and_the_slot_is_untouched(an, page, db):
    set_up(an, page)
    preview = upload_json(an, page, [script(2, 1, "Kịch bản cũ")]).json()
    plan = apply_rows(an, page, preview).json()
    slot_id = cell(plan, 2, 1)["id"]
    made = an.post("/api/articles", json={"plan_slot_id": slot_id})
    assert made.status_code == 201, made.text
    again = upload_json(an, page, [script(2, 1, "Kịch bản mới")]).json()
    assert (again["rows"][0]["action"], again["rows"][0]["target"]) == ("skip_used", "skip")
    after = apply_rows(an, page, again).json()
    assert cell(after, 2, 1)["hook"] == "Kịch bản cũ" and after["backlog"] == []


def test_saving_comments_by_hand_marks_them_edited_and_checks_them(an, page):
    set_up(an, page)
    slot_id = cell(apply_rows(an, page, upload_json(an, page, [script(1, 1, "Bài một")]).json()).json(), 1, 1)["id"]
    edited = [{"type": "cong_dung", "text": "Một bình luận do chính tay mình viết ra đây."}] + comments(4)[1:]
    saved = an.put(f"/api/article-plans/slots/{slot_id}/comments", json={"pinned_comments": edited, "pin_index": 1})
    assert saved.status_code == 200, saved.text
    slot = cell(saved.json(), 1, 1)
    assert (slot["comments_edited"], slot["comments_source"], slot["pin_index"]) == (True, "manual", 1)
    wrong = an.put(
        f"/api/article-plans/slots/{slot_id}/comments", json={"pinned_comments": [{"text": "ngắn"}], "pin_index": 0}
    )
    assert wrong.status_code == 422


def test_bulk_skips_what_was_edited_unless_overwrite_and_does_not_queue_twice(an, page, db):
    set_up(an, page)
    rows = [script(1, 1, "Đã sửa tay"), script(1, 2, "Chưa có", with_comments=False)]
    plan = apply_rows(an, page, upload_json(an, page, rows).json()).json()
    edited_id = cell(plan, 1, 1)["id"]
    an.put(f"/api/article-plans/slots/{edited_id}/comments", json={"pinned_comments": comments(), "pin_index": 0})
    count = an.get(f"/api/article-plans/{page}/comments/count", params={"scope": "unposted"}).json()
    assert (count["total"], count["edited"], count["will_run"]) == (2, 1, 1)
    first = an.post(f"/api/article-plans/{page}/comments/bulk", json={"scope": "unposted"}).json()
    assert (first["queued"], first["skipped_edited"], first["plan"]["comments_pending"]) == (1, 1, 1)
    second = an.post(f"/api/article-plans/{page}/comments/bulk", json={"scope": "unposted"}).json()
    assert second["queued"] == 0
    forced = an.post(f"/api/article-plans/{page}/comments/bulk", json={"scope": "unposted", "overwrite": True}).json()
    assert forced["queued"] == 1  # the edited one; the other already has a job
    assert db.query(Job).filter(Job.kind == "slot_comments").count() == 2


def test_the_ai_job_writes_five_comments_and_leaves_an_edited_script_alone(an, page, db):
    set_up(an, page)
    plan = apply_rows(an, page, upload_json(an, page, [script(1, 1, "Cà rốt", with_comments=False)]).json()).json()
    slot = db.get(ArticlePlanSlot, cell(plan, 1, 1)["id"])
    seen = []

    def call(prompt, label):
        seen.append(prompt)
        return answer()

    job = Job(kind="slot_comments", status="running", created_by_id=slot.created_by_id, plan_slot_id=slot.id, params={})
    db.add(job)
    db.commit()
    slot_comments.run_job(db, job, call, lambda: None)
    db.refresh(slot)
    assert (len(slot.pinned_comments), slot.comments_source, slot.comments_edited) == (5, "ai", False)
    assert 'Page "Ăn Ngon Sống Khỏe"' in seen[0] and "35–55 tuổi" in seen[0]
    # A script a member edited is skipped by a bulk job, but a member's own click writes it again.
    slot.comments_edited = True
    slot.pinned_comments = [{"text": "Bản sửa tay của thành viên, giữ nguyên nhé."}]
    db.commit()
    slot_comments.run_job(db, job, call, lambda: None)
    db.refresh(slot)
    assert slot.pinned_comments == [{"text": "Bản sửa tay của thành viên, giữ nguyên nhé."}]
    job.params = {"overwrite": True}
    slot_comments.run_job(db, job, call, lambda: None)
    db.refresh(slot)
    assert len(slot.pinned_comments) == 5


def test_one_comment_can_be_written_again_without_touching_the_others(an, page, db):
    set_up(an, page)
    plan = apply_rows(an, page, upload_json(an, page, [script(1, 1, "Cà rốt")]).json()).json()
    slot = db.get(ArticlePlanSlot, cell(plan, 1, 1)["id"])
    new = {"pinned_comments": [{"type": "cach_lam", "text": "Một cách làm hoàn toàn mới, ngon và dễ nấu hơn nhiều."}]}
    job = Job(
        kind="slot_comments",
        status="running",
        created_by_id=slot.created_by_id,
        plan_slot_id=slot.id,
        params={"index": 1, "overwrite": True},
    )
    db.add(job)
    db.commit()
    slot_comments.run_job(db, job, lambda *_: json.dumps(new, ensure_ascii=False), lambda: None)
    db.refresh(slot)
    texts = [item["text"] for item in slot.pinned_comments]
    assert texts[1].startswith("Một cách làm hoàn toàn mới") and texts[0] == TEXTS[0] and texts[2] == TEXTS[2]


# --- Writing them under a post ---


def live_article(db, user, fakes, pinned=None, pin_index=0, enabled=True):
    """An article made from a plan script, posted and live on the fake Facebook."""
    row = fanpages.save(db, FACEBOOK_PAGE, "Ăn Ngon Sống Khỏe", FACEBOOK_TOKEN, user.id)
    db.flush()
    plan = db.scalar(select(ArticlePlan).where(ArticlePlan.fanpage_id == row.id))
    if plan is None:
        plan = ArticlePlan(fanpage_id=row.id, start_date=article_plans.today(), created_by_id=user.id)
        db.add(plan)
        db.flush()
    article = Article(
        knowledge_topic_id=first_topic(db).id,
        kind="kien_thuc",
        topic="Cà rốt",
        caption="Cà rốt tốt cho mắt",
        post_comments_enabled=enabled,
        created_by_id=user.id,
    )
    db.add(article)
    db.flush()
    slot = ArticlePlanSlot(
        plan_id=plan.id,
        day=db.query(ArticlePlanSlot).filter_by(plan_id=plan.id).count() + 1,
        slot=1,
        hook="Cà rốt",
        article_id=article.id,
        pinned_comments=comments() if pinned is None else pinned,
        pin_index=pin_index,
        created_by_id=user.id,
    )
    db.add(slot)
    remote = f"{FACEBOOK_PAGE}_{len(fakes.page_posts) + 100}"
    fakes.page_posts[remote] = {"message": "x", "published": True, "scheduled": None, "photo": None, "edge": "feed"}
    post = Publication(
        article_id=article.id,
        platform="facebook",
        fanpage_id=row.id,
        status="published",
        remote_id=remote,
        published_at=datetime.now(UTC) - timedelta(minutes=5),
        created_by_id=user.id,
    )
    db.add(post)
    db.commit()
    return post, slot


def messages(fakes, post) -> list[str]:
    return [row["message"] for row in fakes.facebook_comments.values() if row["object"] == post.remote_id]


def step(db, post_id):
    """One round of the worker for the post, with every waiting comment due now."""
    for row in db.scalars(select(PostComment).where(PostComment.status == "pending")):
        row.due_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    slot_comments.write_post(db, post_id)


def rows(db, post_id) -> list[PostComment]:
    return list(
        db.scalars(
            select(PostComment)
            .where(PostComment.publication_id == post_id)
            .order_by(PostComment.order)
            .execution_options(populate_existing=True)
        )
    )


def test_the_first_round_only_makes_the_rows_and_waits_30_to_60_seconds(db, me, fakes):
    post, slot = live_article(db, me, fakes, pin_index=2)
    assert post.id in slot_comments.due_posts(db)
    slot_comments.write_post(db, post.id)
    made = rows(db, post.id)
    assert [row.text for row in made] == TEXTS and [row.is_pinned for row in made] == [False, False, True, False, False]
    assert messages(fakes, post) == []
    wait = made[2].due_at - datetime.now(UTC)
    assert timedelta(seconds=28) < wait <= timedelta(seconds=60)
    assert post.id not in slot_comments.due_posts(db)  # nothing due yet


def test_the_pinned_comment_goes_first_then_the_others_in_order_and_the_pin_waits_for_a_member(db, me, fakes):
    post, slot = live_article(db, me, fakes, pin_index=2)
    for _ in range(6):
        step(db, post.id)
    assert messages(fakes, post) == [TEXTS[2], TEXTS[0], TEXTS[1], TEXTS[3], TEXTS[4]]
    statuses = [row.status for row in rows(db, post.id)]
    assert statuses == ["posted", "posted", "need_manual_pin", "posted", "posted"]
    shown = slot_comments.post_payload(db, post)
    assert shown["need_manual_pin"] is True and shown["written"] == 5
    assert slot_comments.mark_pinned(db, post) is True
    db.commit()
    assert rows(db, post.id)[2].status == "pinned"
    assert slot_comments.mark_pinned(db, post) is False


def test_the_next_comment_is_due_20_to_40_seconds_after_the_one_before(db, me, fakes):
    post, _ = live_article(db, me, fakes)
    step(db, post.id)  # makes the rows
    step(db, post.id)  # writes the pinned one
    following = rows(db, post.id)[1]
    wait = following.due_at - datetime.now(UTC)
    assert timedelta(seconds=18) < wait <= timedelta(seconds=40)


def test_a_failure_at_the_third_comment_is_tried_again_without_writing_the_first_two_twice(db, me, fakes):
    post, _ = live_article(db, me, fakes)
    step(db, post.id)
    step(db, post.id)
    step(db, post.id)
    assert len(messages(fakes, post)) == 2
    fakes.facebook_comment_replies_lost = 1  # Facebook takes the third and the answer is lost
    step(db, post.id)
    third = rows(db, post.id)[2]
    assert (third.status, third.attempts, third.fb_comment_id) == ("pending", 1, None)
    assert timedelta(seconds=30) < third.due_at - datetime.now(UTC) <= timedelta(minutes=1)
    for _ in range(4):
        step(db, post.id)
    assert messages(fakes, post) == TEXTS  # five comments, none twice
    assert all(row.fb_comment_id for row in rows(db, post.id))


def test_a_refused_token_fails_the_rest_at_once_and_retry_writes_only_those(db, me, fakes):
    post, _ = live_article(db, me, fakes)
    fakes.facebook_comment_refused = True
    for _ in range(3):
        step(db, post.id)
    assert {row.status for row in rows(db, post.id)} == {"failed"}
    assert all("pages_manage_engagement" in row.error for row in rows(db, post.id))
    assert messages(fakes, post) == []
    fakes.facebook_comment_refused = False
    assert slot_comments.retry_failed(db, post) == 5
    db.commit()
    for _ in range(6):
        step(db, post.id)
    assert messages(fakes, post) == TEXTS


def test_a_comment_that_already_has_its_facebook_id_is_never_written_again(db, me, fakes):
    post, _ = live_article(db, me, fakes)
    step(db, post.id)
    step(db, post.id)
    first = rows(db, post.id)[0]
    first.status, first.error = "failed", "đã lỗi nhưng đã có id"
    db.commit()
    assert slot_comments.retry_failed(db, post) == 0  # it has an id: put back as written, not tried again
    db.expire_all()
    assert rows(db, post.id)[0].status == "need_manual_pin" and len(messages(fakes, post)) == 1


def test_a_post_that_is_gone_skips_what_is_left(db, me, fakes):
    post, _ = live_article(db, me, fakes)
    step(db, post.id)
    del fakes.page_posts[post.remote_id]
    step(db, post.id)
    assert {row.status for row in rows(db, post.id)} == {"skipped"}


def test_editing_the_script_after_posting_changes_nothing_already_made(db, me, fakes):
    post, slot = live_article(db, me, fakes)
    step(db, post.id)
    slot.pinned_comments = [{"type": "cong_dung", "text": "Bình luận mới viết sau khi bài đã được đăng lên rồi."}]
    db.commit()
    for _ in range(6):
        step(db, post.id)
    assert messages(fakes, post) == TEXTS


def test_a_script_before_the_post_is_live_uses_its_newest_comments(db, me, fakes):
    post, slot = live_article(db, me, fakes)
    slot.pinned_comments = comments(2)
    db.commit()
    step(db, post.id)
    assert len(rows(db, post.id)) == 2


def test_no_comments_or_the_switch_off_makes_no_rows(db, me, fakes):
    none, _ = live_article(db, me, fakes, pinned=[])
    step(db, none.id)
    assert rows(db, none.id) == [] and none.id not in slot_comments.due_posts(db)
    off, _ = live_article(db, me, fakes, enabled=False)
    assert off.id not in slot_comments.due_posts(db)
    slot_comments.write_post(db, off.id)
    assert rows(db, off.id) == []


def test_a_scheduled_post_is_written_under_only_once_it_is_live(db, me, fakes):
    post, _ = live_article(db, me, fakes)
    post.status, post.scheduled_at = "scheduled", datetime.now(UTC) + timedelta(hours=2)
    db.commit()
    assert post.id not in slot_comments.due_posts(db)
    post.scheduled_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    assert post.id in slot_comments.due_posts(db)


def test_the_article_endpoint_shows_the_comments_and_their_buttons(an, db, me, fakes):
    post, slot = live_article(db, me, fakes)
    for _ in range(2):
        step(db, post.id)
    shown = an.get(f"/api/articles/{post.article_id}").json()
    assert shown["post_comments_enabled"] is True and shown["plan_slot"]["comments_count"] == 5
    (item,) = shown["posts"]
    assert item["pinned_comments"]["need_manual_pin"] is True
    done = an.post(f"/api/articles/posts/{post.id}/pinned-comments/pinned")
    assert done.status_code == 200
    assert an.post(f"/api/articles/posts/{post.id}/pinned-comments/retry").status_code == 409
    off = an.patch(f"/api/articles/{post.article_id}", json={"post_comments_enabled": False})
    assert off.json()["post_comments_enabled"] is False
