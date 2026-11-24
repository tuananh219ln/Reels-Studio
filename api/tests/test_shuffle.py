"""'Nhân bản xáo cảnh': copies with the content scenes in other orders, their list numbers following their new
places, and a reminder to change the title (docs/decisions/2026-11-17-shuffle-copies.md)."""

import random

import pytest
from conftest import login, make_user, make_video
from sqlalchemy import select

from reels_api.models import Job, Scene, Video
from reels_api.shuffle import distinct_orders, generate_orders, renumber
from reels_api.videos import split_scenes

DISHES = ["Chuối xanh om đậu phụ", "Chuối xanh nấu cá", "Chuối xanh om thịt ba chỉ", "Chuối xanh nấu ốc", "Om sườn"]


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def numbered_video(db, storage, me, count=5):
    video = make_video(db, storage, me, scene_count=count)
    _, scenes = split_scenes(db, video)
    for number, scene in enumerate(scenes, start=1):
        scene.text = f"{number}. {DISHES[number - 1]}\nCó 5 loại chất xơ"
        scene.voice_text = f"{number}. {DISHES[number - 1]} bổ sung 50 gam chất xơ"
    db.commit()
    return video, [scene.id for scene in scenes]


def content(db, video_id: int) -> list[Scene]:
    db.expire_all()  # what the api saved, not what this session read before
    return db.scalars(
        select(Scene).where(Scene.video_id == video_id, Scene.is_title.is_(False)).order_by(Scene.position)
    ).all()


# --- renumber ---


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("5. Chuối xanh om sườn", "1. Chuối xanh om sườn"),
        ("2) Rau muống", "1) Rau muống"),
        ("3: Cà rốt", "1: Cà rốt"),
        ("4 - Bí đỏ", "1 - Bí đỏ"),
        ("#6. Đậu", "#1. Đậu"),
        ("Số 7: Gừng", "Số 1: Gừng"),
        ("Cách 8. Ngâm", "Cách 1. Ngâm"),
        ("  9.  Cá\n2. dòng sau", "  1.  Cá\n2. dòng sau"),
        # Not list numbers: a number in the sentence, a decimal, a range, or no number at all.
        ("50 tuổi nên ăn gì", "50 tuổi nên ăn gì"),
        ("1.5 kg mỗi ngày", "1.5 kg mỗi ngày"),
        ("3-4 lần mỗi tuần", "3-4 lần mỗi tuần"),
        ("Ăn 5 loại rau", "Ăn 5 loại rau"),
        ("Không có số", "Không có số"),
    ],
)
def test_renumber_changes_only_a_list_number_at_the_start(text, expected):
    assert renumber(text, 1) == expected


# --- generate_orders ---


def test_orders_differ_from_the_original_and_from_one_another():
    orders = generate_orders([1, 2, 3, 4, 5], set(), 20, rng=random.Random(7))
    assert len(orders) == 20
    assert len({tuple(order) for order in orders}) == 20
    assert all(sorted(order) == [1, 2, 3, 4, 5] and order != [1, 2, 3, 4, 5] for order in orders)
    # From 4 scenes on, most scenes move.
    assert all(sum(a != b for a, b in zip(order, [1, 2, 3, 4, 5], strict=True)) >= 3 for order in orders)


def test_orders_keep_a_locked_scene_and_stop_at_k_factorial_minus_one():
    assert distinct_orders(2) == 1 and distinct_orders(3) == 5 and distinct_orders(5) == 119
    orders = generate_orders([1, 2, 3, 4], {3}, 20, rng=random.Random(1))
    assert len(orders) == 5 and all(order[3] == 4 for order in orders)
    assert generate_orders([1, 2], set(), 5) == [[2, 1]]
    assert generate_orders([1], set(), 5) == []


def test_orders_leave_out_those_already_taken():
    orders = generate_orders([1, 2, 3], set(), 10, taken={(2, 1, 3), (3, 2, 1)})
    assert sorted(map(tuple, orders)) == [(1, 3, 2), (2, 3, 1), (3, 1, 2)]


def test_many_scenes_are_drawn_rather_than_listed():
    orders = generate_orders(list(range(10)), {9}, 20, rng=random.Random(3))
    assert len({tuple(order) for order in orders}) == 20 and all(order[9] == 9 for order in orders)


# --- api ---


def test_preview_then_copies_in_the_previewed_orders_renumbered(an, db, me, storage):
    video, ids = numbered_video(db, storage, me)

    preview = an.post(f"/api/shuffle/videos/{video.id}/preview", json={"count": 3, "lock_last": True}).json()
    assert preview["numbered"] is True and preview["max_distinct"] == 20
    assert [scene["name"] for scene in preview["scenes"]] == DISHES
    orders = preview["orders"]
    assert len(orders) == 3 and all(order[-1] == ids[-1] for order in orders)

    response = an.post(f"/api/shuffle/videos/{video.id}/copies", json={"orders": orders, "lock_last": True})

    assert response.status_code == 201
    made = response.json()
    assert made["renumbered"] is True
    assert [copy["name"] for copy in made["videos"]] == [f"5 MÓN GIÚP XƯƠNG CHẮC KHỎE (xáo {n})" for n in (1, 2, 3)]
    source_text = {scene.id: scene.text for scene in content(db, video.id)}
    for copy, order in zip(made["videos"], orders, strict=True):
        scenes = content(db, copy["id"])
        assert [scene.source_scene_id for scene in scenes] == order
        for place, (scene, source_id) in enumerate(zip(scenes, order, strict=True), start=1):
            dish = DISHES[ids.index(source_id)]
            # The number follows the new place; the rest of the text, numbers in it too, is kept.
            assert scene.text == f"{place}. {dish}\nCó 5 loại chất xơ"
            assert scene.voice_text == f"{place}. {dish} bổ sung 50 gam chất xơ"
            assert source_text[source_id].endswith(scene.text[1:])
        row = db.get(Video, copy["id"])
        assert row.shuffled_from_id == video.id and row.scene_order == ",".join(map(str, order))
        assert row.mp4_key is None
        assert db.scalars(select(Job).where(Job.video_id == row.id)).all() == []
    # The source is untouched.
    assert [scene.id for scene in content(db, video.id)] == ids
    assert content(db, video.id)[0].text.startswith("1. ")


def test_copies_refuse_bad_orders(an, db, me, storage):
    video, ids = numbered_video(db, storage, me, count=3)
    url = f"/api/shuffle/videos/{video.id}/copies"
    assert an.post(url, json={"orders": [ids]}).status_code == 422  # the original order
    assert an.post(url, json={"orders": [ids[::-1], ids[::-1]]}).status_code == 422  # twice the same
    assert an.post(url, json={"orders": [[ids[1], ids[0], 999]]}).status_code == 409  # not its scenes
    locked = an.post(url, json={"orders": [[ids[2], ids[0], ids[1]]], "lock_last": True})
    assert locked.status_code == 422 and "Cảnh cuối" in locked.json()["message"]
    assert db.scalar(select(Video).where(Video.shuffled_from_id == video.id)) is None


def test_later_copies_take_other_orders_and_a_copy_of_a_copy_counts_from_the_first(an, db, me, storage):
    video, ids = numbered_video(db, storage, me, count=3)
    first = an.post(f"/api/shuffle/videos/{video.id}/preview", json={"count": 5}).json()["orders"]
    copies = an.post(f"/api/shuffle/videos/{video.id}/copies", json={"orders": first[:3]}).json()["videos"]

    later = an.post(f"/api/shuffle/videos/{video.id}/preview", json={"count": 5}).json()
    assert later["max_distinct"] == 2
    assert sorted(map(tuple, later["orders"])) == sorted(map(tuple, first[3:]))

    # From a copy, the orders are still told apart by the first video's scenes.
    copy_id = copies[0]["id"]
    from_copy = an.post(f"/api/shuffle/videos/{copy_id}/preview", json={"count": 5}).json()
    by_source = {scene.id: scene.source_scene_id for scene in content(db, copy_id)}
    assert sorted(tuple(by_source[i] for i in order) for order in from_copy["orders"]) == sorted(map(tuple, first[3:]))
    made = an.post(f"/api/shuffle/videos/{copy_id}/copies", json={"orders": from_copy["orders"][:1]}).json()
    assert db.get(Video, made["videos"][0]["id"]).shuffled_from_id == video.id
    assert made["videos"][0]["name"] == "5 MÓN GIÚP XƯƠNG CHẮC KHỎE (xáo 4)"


def test_scenes_without_numbers_keep_their_text(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=3, scene_text="Rau muống\n50 tuổi nên ăn")
    orders = an.post(f"/api/shuffle/videos/{video.id}/preview", json={"count": 1}).json()["orders"]
    made = an.post(f"/api/shuffle/videos/{video.id}/copies", json={"orders": orders}).json()
    assert made["renumbered"] is False and "Không phát hiện đánh số" in made["warnings"][0]
    assert all(scene.text == "Rau muống\n50 tuổi nên ăn" for scene in content(db, made["videos"][0]["id"]))


def test_a_copy_asks_for_a_new_title_until_it_changes_or_is_skipped(an, db, me, storage):
    video, _ = numbered_video(db, storage, me, count=3)
    orders = an.post(f"/api/shuffle/videos/{video.id}/preview", json={"count": 2}).json()["orders"]
    first, second = (
        copy["id"]
        for copy in an.post(f"/api/shuffle/videos/{video.id}/copies", json={"orders": orders}).json()["videos"]
    )

    detail = an.get(f"/api/videos/{first}").json()
    assert detail["title_review"] is True
    assert detail["shuffle"]["source"]["id"] == video.id and detail["shuffle"]["review"] is True
    assert {other["id"] for other in detail["shuffle"]["same_title"]} == {video.id, second}
    rows = {row["id"]: row for row in an.get("/api/videos").json()}
    assert rows[first]["title_review"] is True and rows[video.id]["title_review"] is False
    assert an.get(f"/api/videos/{video.id}").json()["shuffle"] is None

    title, _ = split_scenes(db, db.get(Video, first))
    an.patch(f"/api/scenes/{title.id}", json={"text": "TIÊU ĐỀ 2"})
    detail = an.get(f"/api/videos/{first}").json()
    assert detail["title_review"] is False and detail["shuffle"]["same_title"] == []

    assert an.get(f"/api/videos/{second}").json()["title_review"] is True
    skipped = an.delete(f"/api/shuffle/videos/{second}/title-review").json()
    assert skipped["title_review"] is False


def test_reshuffle_a_copy_and_undo(an, db, me, storage):
    video, _ = numbered_video(db, storage, me, count=4)
    orders = an.post(f"/api/shuffle/videos/{video.id}/preview", json={"count": 1}).json()["orders"]
    copy_id = an.post(f"/api/shuffle/videos/{video.id}/copies", json={"orders": orders}).json()["videos"][0]["id"]
    before = [(scene.id, scene.text) for scene in content(db, copy_id)]

    shuffled = an.post(f"/api/shuffle/videos/{copy_id}/reshuffle", json={"lock_last": True}).json()

    assert shuffled["previous_order"] == [scene_id for scene_id, _ in before]
    after = content(db, copy_id)
    assert [scene.id for scene in after] != shuffled["previous_order"] and after[-1].id == before[-1][0]
    assert [scene.text[:2] for scene in after] == ["1.", "2.", "3.", "4."]
    assert db.get(Video, copy_id).scene_order == ",".join(str(scene.source_scene_id) for scene in after)

    undone = an.post(f"/api/shuffle/videos/{copy_id}/reshuffle", json={"order": shuffled["previous_order"]})
    assert undone.status_code == 200
    assert [(scene.id, scene.text) for scene in content(db, copy_id)] == before

    # Only a shuffled copy is shuffled again.
    refused = an.post(f"/api/shuffle/videos/{video.id}/reshuffle", json={})
    assert refused.status_code == 409


def test_an_exact_copy_of_a_shuffled_copy_is_not_a_shuffle(an, db, me, storage):
    video, _ = numbered_video(db, storage, me, count=3)
    orders = an.post(f"/api/shuffle/videos/{video.id}/preview", json={"count": 1}).json()["orders"]
    copy_id = an.post(f"/api/shuffle/videos/{video.id}/copies", json={"orders": orders}).json()["videos"][0]["id"]
    exact = an.post(f"/api/videos/{copy_id}/duplicate").json()
    row = db.get(Video, exact["id"])
    assert (row.shuffled_from_id, row.scene_order, row.review_title) == (None, None, None)


# --- pinned scenes ---


def test_pinned_scenes_keep_their_place(an, db, me, storage):
    video, ids = numbered_video(db, storage, me)
    pinned = [ids[1], ids[3]]
    preview = an.post(
        f"/api/shuffle/videos/{video.id}/preview", json={"count": 5, "pinned_scene_ids": [*pinned, 999]}
    ).json()
    # 3 free scenes: 3! - 1 orders; the unknown id is left out.
    assert preview["max_distinct"] == 5 and preview["pinned"] == pinned
    orders = preview["orders"]
    assert len(orders) == 5 and all(order[1] == ids[1] and order[3] == ids[3] for order in orders)

    made = an.post(
        f"/api/shuffle/videos/{video.id}/copies", json={"orders": orders[:1], "pinned_scene_ids": pinned}
    ).json()
    scenes = content(db, made["videos"][0]["id"])
    assert [scene.source_scene_id for scene in scenes] == orders[0]
    assert scenes[1].text.startswith("2. ") and scenes[3].text.startswith("4. ")

    moved = [ids[1], ids[0], ids[2], ids[3], ids[4]]
    refused = an.post(f"/api/shuffle/videos/{video.id}/copies", json={"orders": [moved], "pinned_scene_ids": pinned})
    assert refused.status_code == 422 and "ghim" in refused.json()["message"]
    gone = an.post(f"/api/shuffle/videos/{video.id}/copies", json={"orders": orders[1:2], "pinned_scene_ids": [999]})
    assert gone.status_code == 409


def test_reshuffle_keeps_pinned_scenes(an, db, me, storage):
    video, _ = numbered_video(db, storage, me, count=4)
    orders = an.post(f"/api/shuffle/videos/{video.id}/preview", json={"count": 1}).json()["orders"]
    copy_id = an.post(f"/api/shuffle/videos/{video.id}/copies", json={"orders": orders}).json()["videos"][0]["id"]
    before = [scene.id for scene in content(db, copy_id)]
    an.post(f"/api/shuffle/videos/{copy_id}/reshuffle", json={"pinned_scene_ids": [before[0]]})
    after = [scene.id for scene in content(db, copy_id)]
    assert after[0] == before[0] and after != before
