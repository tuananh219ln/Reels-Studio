"""Affiliate comment sets ("Bộ bình luận", aff_sets.py): which sets a reel gets, what their comments say, and the
worker writing them after the food comments with the Page's own rests."""

from datetime import UTC, datetime, timedelta

import pytest
from conftest import first_topic, login, make_user
from sqlalchemy import select
from test_post_comments import PINNED, add_post, comments_on, due

from reels_api import aff_sets, post_comments
from reels_api.aff_sets import Candidate
from reels_api.models import AffCommentSet, AffiliateProduct, Fanpage, Publication, Video

AT = datetime(2026, 11, 19, 12, tzinfo=UTC)
SETTINGS = aff_sets.settings_of(None)


def ago(days: float) -> datetime:
    return AT - timedelta(days=days)


# Choosing the sets (no database)


def test_a_set_whose_tags_are_in_the_video_comes_first_then_the_longest_unused():
    sets = [
        Candidate(1, 3, ago(10), ["trà"], 10),
        Candidate(2, 3, ago(5), ["lạc vừng", "đậu"], 10),
        Candidate(3, 3, None, ["hạt chia"], 10),
    ]
    text = aff_sets.normalize("5 thực phẩm người sống thọ: khoai lang, ĐẬU, cá, lạc vừng")
    assert aff_sets.choose(sets, text, SETTINGS, AT, seed=1) == [2, 3]


def test_a_tag_is_matched_as_whole_words():
    assert aff_sets.matches("cá", "ăn cá mỗi tuần")
    assert not aff_sets.matches("cá", "các món ngon")


def test_videos_made_one_after_another_take_the_fresh_sets_in_turn():
    # Before any goes up, every video saw the same two sets (the never used, by priority then id).
    sets = [Candidate(n, 3, None, [], 10) for n in range(1, 7)]
    picks = [aff_sets.choose(sets, "", SETTINGS, AT, seed=video) for video in (101, 102, 103)]
    assert sorted(set_id for pair in picks for set_id in pair) == [1, 2, 3, 4, 5, 6]
    assert picks[0] == aff_sets.choose(sets, "", SETTINGS, AT, seed=101), "the same video, the same sets"


def test_without_a_match_the_fresh_sets_cycle_higher_priority_first():
    sets = [
        Candidate(1, 3, ago(4), ["trà"], 10),
        Candidate(2, 5, None, [], 10),
        Candidate(3, 1, None, [], 10),
    ]
    one = SETTINGS | {"sets_per_post": 1}
    assert [aff_sets.choose(sets, "bữa sáng", one, AT, seed=video) for video in (0, 1, 2)] == [[2], [1], [3]]


def test_a_set_used_within_the_days_comes_back_only_when_nothing_else_is_left():
    sets = [Candidate(1, 5, ago(1), ["đậu"], 10), Candidate(2, 1, ago(10), [], 10)]
    one = SETTINGS | {"sets_per_post": 1}
    assert aff_sets.choose(sets, "đậu đen", one, AT, seed=1) == [2], "the match was used yesterday"
    assert aff_sets.choose(sets, "đậu đen", SETTINGS, AT, seed=1) == [2, 1], "not enough others: it comes back"


def test_disabled_sets_and_sets_with_too_few_usable_products_are_never_chosen():
    sets = [Candidate(1, 3, None, [], 2), Candidate(2, 3, None, [], 10, enabled=False), Candidate(3, 3, None, [], 3)]
    assert aff_sets.choose(sets, "", SETTINGS, AT, seed=1) == [3]


def test_random_draws_the_same_sets_for_the_same_video():
    sets = [Candidate(n, n, None, [], 10) for n in range(1, 6)]
    settings = SETTINGS | {"strategy": "random"}
    first = aff_sets.choose(sets, "", settings, AT, seed=7)
    assert first == aff_sets.choose(sets, "", settings, AT, seed=7) and len(set(first)) == 2


# What a comment says (no database)


def test_a_comment_is_the_opening_the_numbered_lines_and_the_closing():
    text = aff_sets.render(
        "👉 Nhà mình hay dùng:",
        "Giá có thể thay đổi.",
        [("Hạt chia 500g", "https://s.shopee.vn/a"), ("Đậu đen 1kg", "https://s.shopee.vn/b")],
        SETTINGS["line_format"],
    )
    assert text == (
        "👉 Nhà mình hay dùng:\n1. Hạt chia 500g 👉 https://s.shopee.vn/a\n"
        "2. Đậu đen 1kg 👉 https://s.shopee.vn/b\nGiá có thể thay đổi."
    )


def test_a_comment_drops_its_last_products_past_facebooks_length():
    rows = [(f"Sản phẩm {n}", "https://s.shopee.vn/" + "x" * 1500) for n in range(10)]
    text = aff_sets.render("Mở", "", rows, SETTINGS["line_format"])
    assert len(text) <= 8000 and text.count("\n") == 5


def test_settings_are_checked_and_keep_their_defaults():
    saved = aff_sets.clean_settings({"sets_per_post": 1, "first_delay": [60, 120]})
    assert saved["sets_per_post"] == 1 and saved["first_delay"] == [60, 120] and saved["delay"] == [180, 420]
    for wrong in ({"sets_per_post": 4}, {"line_format": "{stt}. {short_name}"}, {"delay": [400, 200]}):
        with pytest.raises(aff_sets.ApiError):
            aff_sets.clean_settings(wrong)


class Item:
    def __init__(self, n: int, category: str | None):
        self.id, self.category = n, category


def test_splitting_by_group_keeps_each_group_apart_and_mixed_deals_them_out():
    items = [Item(n, "hạt" if n < 12 else "trà") for n in range(15)]
    by_group = aff_sets.split(items, "by_category", 10)
    assert [len(group) for group in by_group] == [10, 2, 3]
    mixed = aff_sets.split(items, "mixed", 10)
    assert {item.category for item in mixed[0]} == {"hạt", "trà"} and sum(map(len, mixed)) == 15


# The database: the tab, a video's plan and the worker


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def product(db, user, name: str, tags: list[str] | None = None, **fields) -> AffiliateProduct:
    row = AffiliateProduct(
        knowledge_topic_id=first_topic(db).id,
        name=name,
        short_name=name[:20],
        tags=tags or [],
        url=f"https://s.shopee.vn/{abs(hash(name)) % 10**6}",
        shop_name="Shop",
        shop_type="mall",
        rating=4.9,
        sold=1000,
        price=100000,
        commission_rate=8,
        status="approved",
        created_by_id=user.id,
        **fields,
    )
    db.add(row)
    db.flush()
    return row


def make_set(an, page_id: int, name: str, products: list[AffiliateProduct], **fields) -> dict:
    body = {"fanpage_id": page_id, "name": name, "intro_text": f"Mở {name}", "product_ids": [p.id for p in products]}
    saved = an.post("/api/aff-sets", json=body | fields)
    assert saved.status_code == 201, saved.text
    return saved.json()


def test_a_set_holds_at_most_ten_products_in_the_order_given(an, db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    items = [product(db, me, f"Hạt {n}") for n in range(11)]
    db.commit()
    too_many = an.post(
        "/api/aff-sets", json={"fanpage_id": post.fanpage_id, "name": "Bộ", "product_ids": [p.id for p in items]}
    )
    assert too_many.status_code == 422
    saved = make_set(an, post.fanpage_id, "Bộ 01", list(reversed(items[:3])))
    assert [row["name"] for row in saved["products"]] == ["Hạt 2", "Hạt 1", "Hạt 0"]
    moved = an.put(f"/api/aff-sets/{saved['id']}", json={"name": "Bộ 01", "product_ids": [items[0].id, items[2].id]})
    assert [row["name"] for row in moved.json()["products"]] == ["Hạt 0", "Hạt 2"]


def test_generating_from_the_stock_previews_then_makes_sets_with_different_openings(an, db, me, storage, fakes):
    page = add_post(db, storage, me, fakes).fanpage
    page.knowledge_topic_id = first_topic(db).id
    for n in range(25):
        product(db, me, f"Món {n}", category="hạt" if n % 2 else "trà")
    db.commit()
    body = {"fanpage_id": page.id, "split": "by_category", "per_set": 10}
    preview = an.post("/api/aff-sets/generate", json=body).json()
    assert preview["created"] == 0 and [len(one["products"]) for one in preview["sets"]] == [10, 2, 10, 3]
    made = an.post("/api/aff-sets/generate", json=body | {"dry_run": False}).json()
    assert made["created"] == 4
    sets = db.scalars(select(AffCommentSet).where(AffCommentSet.fanpage_id == page.id)).all()
    assert len({one.intro_text for one in sets}) == 4


def write_run(db, post: Publication, limit: int = 30) -> list[str]:
    """Write until the run is over, letting every rest pass at once; what each turn rested before the next."""
    rests = []
    for _ in range(limit):
        post_comments.write(db, post)
        db.refresh(post)
        if post.comment_requested_at is None or post.comment_sent_at >= post.comment_requested_at:
            return rests
        rests.append((post.comment_requested_at - datetime.now(UTC)).total_seconds())
        db.get(Fanpage, post.fanpage_id).comments_next_at = None
        post.comment_requested_at = datetime.now(UTC)
        db.commit()
    raise AssertionError("the run never ended")


@pytest.fixture
def shortest(monkeypatch):
    monkeypatch.setattr(post_comments.random, "uniform", lambda low, high: low)


def test_set_comments_follow_the_food_comments_minutes_apart(an, db, me, storage, fakes, shortest):
    post = add_post(db, storage, me, fakes)
    db.get(Video, post.video_id).extra_comments = ["Món này ngon lắm"]
    first = [product(db, me, f"Đậu {n}", tags=["đậu"]) for n in range(3)]
    second = [product(db, me, f"Trà {n}") for n in range(3)]
    db.commit()
    make_set(an, post.fanpage_id, "Trà", second)
    matched = make_set(an, post.fanpage_id, "Đậu", first)
    db.get(Video, post.video_id).topic = "Ăn đậu mỗi ngày"
    db.commit()

    rests = write_run(db, post)
    messages = [comment["message"] for comment in comments_on(fakes, post)]
    assert messages[:2] == [PINNED, "Món này ngon lắm"]
    assert messages[2].startswith("Mở Đậu\n1. Đậu 0 👉 https://s.shopee.vn/") and messages[3].startswith("Mở Trà")
    assert [round(rest) for rest in rests] == [45, 300, 180], "45 s, then 5 minutes, then 3 minutes"
    assert post.aff_set_ids == [matched["id"], matched["id"] - 1]
    used = db.get(AffCommentSet, matched["id"])
    assert used.use_count == 1 and used.last_used_at is not None
    assert due(db) == [], "written once"


def test_a_video_turned_off_or_a_page_turned_off_gets_no_set_comment(an, db, me, storage, fakes, shortest):
    post = add_post(db, storage, me, fakes)
    make_set(an, post.fanpage_id, "Bộ", [product(db, me, f"Hạt {n}") for n in range(3)])
    assert an.put(f"/api/aff-sets/videos/{post.video_id}", json={"off": True}).json()["pages"][0]["planned"] == []
    write_run(db, post)
    assert [comment["message"] for comment in comments_on(fakes, post)] == [PINNED]

    other = add_post(db, storage, me, fakes)
    an.put(f"/api/aff-sets/settings/{other.fanpage_id}", json={"enabled": False})
    write_run(db, other)
    assert [comment["message"] for comment in comments_on(fakes, other)] == [PINNED]


def test_a_video_may_choose_its_own_set_and_unusable_products_are_left_out(an, db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    items = [product(db, me, f"Hạt {n}") for n in range(4)]
    items[1].status = "draft"
    db.commit()
    make_set(an, post.fanpage_id, "Một", items)
    chosen = make_set(an, post.fanpage_id, "Hai", items)
    plan = an.put(f"/api/aff-sets/videos/{post.video_id}", json={"set_ids": [chosen["id"]]}).json()
    (page,) = [one for one in plan["pages"] if one["fanpage_id"] == post.fanpage_id]
    (planned,) = page["planned"]
    assert planned["set_id"] == chosen["id"]
    assert [line.split(" 👉")[0] for line in planned["text"].splitlines()[1:]] == ["1. Hạt 0", "2. Hạt 2", "3. Hạt 3"]


def test_a_renamed_product_edits_the_set_comment_already_written(an, db, me, storage, fakes, shortest):
    post = add_post(db, storage, me, fakes)
    items = [product(db, me, f"Hạt {n}") for n in range(3)]
    db.commit()
    make_set(an, post.fanpage_id, "Bộ", items)
    write_run(db, post)
    assert an.patch(f"/api/aff-sets/products/{items[0].id}", json={"short_name": "Hạt chia Úc"}).status_code == 200
    db.expire_all()
    post = db.get(Publication, post.id)
    db.get(Fanpage, post.fanpage_id).comments_next_at = None  # the minute's rest after a run
    db.commit()
    assert due(db) == [post.id]
    write_run(db, post)
    comment = comments_on(fakes, post)[-1]
    assert "1. Hạt chia Úc 👉" in comment["message"] and comment["edits"] == 1


def test_the_tab_lists_the_pages_sets_and_its_groups_products(an, db, me, storage, fakes):
    page = add_post(db, storage, me, fakes).fanpage
    page.knowledge_topic_id = first_topic(db).id
    item = product(db, me, "Hạt chia Úc Organic 500g")
    db.commit()
    make_set(an, page.id, "Bộ", [item])
    listed = an.get(f"/api/aff-sets?fanpage_id={page.id}").json()
    assert listed["settings"]["sets_per_post"] == 2
    assert listed["sets"][0]["warnings"], "fewer than 3 usable products"
    assert [(row["name"], row["set_count"]) for row in listed["products"]] == [("Hạt chia Úc Organic 500g", 1)]


def test_a_failed_set_comment_is_tried_again_after_one_three_and_ten_minutes(an, db, me, storage, fakes, shortest):
    post = add_post(db, storage, me, fakes)
    make_set(an, post.fanpage_id, "Bộ", [product(db, me, f"Hạt {n}") for n in range(3)])
    db.commit()
    post_comments.write(db, post)  # the pinned comment
    fakes.facebook_comment_refused = True
    waits = []
    for _ in range(4):
        db.get(Fanpage, post.fanpage_id).comments_next_at = None
        post.comment_requested_at = datetime.now(UTC)
        db.commit()
        post_comments.write(db, post)
        db.refresh(post)
        asked = post.comment_requested_at > post.comment_sent_at
        waits.append(round((post.comment_requested_at - datetime.now(UTC)).total_seconds() / 60) if asked else None)
    assert waits == [1, 3, 10, None], "three tries by itself, then it waits for a member"
    assert post.comment_error.startswith("Bình luận aff 1:") and due(db) == []

    fakes.facebook_comment_refused = False
    plan = an.post(f"/api/aff-sets/posts/{post.id}/now")
    assert plan.status_code == 200, plan.text
    (page,) = [one for one in plan.json()["pages"] if one["fanpage_id"] == post.fanpage_id]
    assert [(row["post_id"], row["count"], row["total"]) for row in page["posts"]] == [(post.id, 0, 1)]
    db.expire_all()
    post = db.get(Publication, post.id)
    assert post.aff_retries == 0 and due(db) == [post.id]
    post_comments.write(db, post)
    assert comments_on(fakes, post)[-1]["message"].startswith("Mở Bộ") and post.comment_error is None


def test_writing_the_set_comments_now_skips_the_pages_wait(an, db, me, storage, fakes, shortest):
    post = add_post(db, storage, me, fakes)
    make_set(an, post.fanpage_id, "Bộ", [product(db, me, f"Hạt {n}") for n in range(3)])
    db.commit()
    post_comments.write(db, post)
    db.refresh(post)
    plan = an.get(f"/api/aff-sets/videos/{post.video_id}").json()
    (row,) = [one for one in plan["pages"] if one["fanpage_id"] == post.fanpage_id][0]["posts"]
    assert row["next_at"] is not None, "five minutes after the last food comment"
    assert due(db) == []

    assert an.post(f"/api/aff-sets/posts/{post.id}/now").status_code == 200
    db.get(Fanpage, post.fanpage_id).comments_next_at = None  # the Page's own minute still holds
    db.commit()
    assert due(db) == [post.id]
    assert an.post(f"/api/aff-sets/posts/{post.id}/now").status_code == 200
    db.get(Video, post.video_id).aff_comments_off = True
    db.commit()
    assert an.post(f"/api/aff-sets/posts/{post.id}/now").status_code == 409


def test_the_pages_card_counts_its_sets_and_the_usable_ones(an, db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    full = [product(db, me, f"Hạt {n}") for n in range(3)]
    short = product(db, me, "Trà")
    db.commit()
    make_set(an, post.fanpage_id, "Đủ", full)
    make_set(an, post.fanpage_id, "Thiếu", [short])
    (row,) = [one for one in an.get("/api/fanpages").json() if one["id"] == post.fanpage_id]
    assert row["aff_sets"] == {"enabled": True, "sets": 2, "usable": 1, "per_post": 2}
    an.put(f"/api/aff-sets/settings/{post.fanpage_id}", json={"enabled": False})
    (row,) = [one for one in an.get("/api/fanpages").json() if one["id"] == post.fanpage_id]
    assert row["aff_sets"]["enabled"] is False


def test_a_short_name_or_group_is_one_line():
    with pytest.raises(Exception, match="một dòng"):
        aff_sets.clean_labels("Hạt\nchia", None, [])
    assert aff_sets.clean_labels("  Hạt chia ", "", ["Hạt", "hạt"]) == ("Hạt chia", None, ["hạt"])
    assert aff_sets.split_tags("rau, Hạt giống ;rau|") == ["rau", " Hạt giống ", "rau"]
