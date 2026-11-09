"""Kho kiến thức: a group's maker may turn off "Cho cả đội sửa" (2026-11-09, Part 4). On by default; off, only the
maker edits the group and its plan, while everyone still uses it. A group with no maker can be claimed."""

import pytest
from conftest import client_for, login, make_user

from reels_api.models import KnowledgeTopic, TopicPlanItem


@pytest.fixture
def an_user(db):
    return make_user(db)


@pytest.fixture
def binh_user(db):
    return make_user(db, email="binh@doi.vn", name="Trần Bình")


@pytest.fixture
def an(client, an_user):
    login(client)
    return client


@pytest.fixture
def binh(app, binh_user):
    client = client_for(app)
    login(client, email="binh@doi.vn")
    return client


@pytest.fixture
def group(db, an_user):
    topic = KnowledgeTopic(name="Già Mà Khỏe", created_by_id=an_user.id, script_prompt="Viết về [Chủ đề]")
    db.add(topic)
    db.flush()
    db.add(TopicPlanItem(knowledge_topic_id=topic.id, day=1, position=1, topic="Ý của An", created_by_id=an_user.id))
    db.commit()
    return topic


LOCKED = "Nhóm “Già Mà Khỏe” chỉ người tạo nhóm (Nguyễn Văn An) được sửa: đã tắt “Cho cả đội sửa”"


def locked(response) -> None:
    assert response.status_code == 403, response.text
    assert (response.json()["code"], response.json()["message"]) == ("group_locked", LOCKED)


def topic_of(client, topic_id: int) -> dict:
    return next(topic for topic in client.get("/api/knowledge").json()["topics"] if topic["id"] == topic_id)


def test_every_group_starts_open_to_the_team(binh, group):
    assert topic_of(binh, group.id)["team_edit"] is True
    assert binh.patch(f"/api/knowledge/topics/{group.id}", json={"banned_words": ["thuốc"]}).status_code == 200


def test_only_the_groups_maker_turns_team_editing_off_and_on(an, binh, group):
    refused = binh.patch(f"/api/knowledge/topics/{group.id}", json={"team_edit": False})
    assert (refused.status_code, refused.json()["code"]) == (403, "not_owner")
    assert an.patch(f"/api/knowledge/topics/{group.id}", json={"team_edit": False}).status_code == 200
    shown = topic_of(binh, group.id)
    assert (shown["team_edit"], shown["owner"]) == (False, "Nguyễn Văn An")
    assert an.patch(f"/api/knowledge/topics/{group.id}", json={"team_edit": True}).status_code == 200
    assert topic_of(binh, group.id)["team_edit"] is True


def test_a_locked_group_is_edited_by_its_maker_only(an, binh, db, group):
    an.patch(f"/api/knowledge/topics/{group.id}", json={"team_edit": False})
    item_id = db.query(TopicPlanItem.id).filter_by(knowledge_topic_id=group.id).scalar()
    for field, value in [
        ("name", "Khác"),
        ("script_prompt", "Prompt khác"),
        ("banned_words", ["x"]),
        ("photo_hint", "ảnh"),
        ("voice_id", ""),
        ("stock_order", ["pixabay"]),
        ("templates", []),
    ]:
        locked(binh.patch(f"/api/knowledge/topics/{group.id}", json={field: value}))
    locked(binh.patch(f"/api/plans/{group.id}", json={"per_day": 2}))
    locked(binh.post(f"/api/plans/{group.id}/items", json={"day": 2, "topic": "Ý mới"}))
    locked(binh.post(f"/api/plans/{group.id}/backlog", json={"ideas": [{"topic": "Để dành"}]}))
    locked(binh.put(f"/api/plans/{group.id}/items", json={"ideas": []}))
    locked(binh.post(f"/api/plans/{group.id}/generate"))
    locked(binh.delete(f"/api/plans/{group.id}/draft"))
    locked(binh.patch(f"/api/plans/items/{item_id}", json={"topic": "Sửa ý"}))
    locked(binh.post(f"/api/plans/{group.id}/import", files={"file": ("plan.json", b"{}", "application/json")}))
    restore = {"entity_type": "knowledge_topic", "entity_id": group.id, "field": "script_prompt", "log_id": None}
    locked(binh.post("/api/edit-logs/restore", json=restore))
    # The maker still edits it.
    assert an.patch(f"/api/knowledge/topics/{group.id}", json={"banned_words": ["thuốc"]}).status_code == 200
    assert an.patch(f"/api/plans/items/{item_id}", json={"topic": "Sửa ý"}).status_code == 200


def test_a_locked_group_is_still_used_by_everyone(binh, an, db, group):
    an.patch(f"/api/knowledge/topics/{group.id}", json={"team_edit": False})
    assert binh.get(f"/api/plans/{group.id}").status_code == 200
    made = binh.post(
        "/api/videos",
        json={"topic": "Ngủ ngon", "knowledge_topic_id": group.id, "mode": "manual", "script": "Một\n\nHai"},
    )
    assert made.status_code == 201, made.text


def test_a_group_without_a_maker_is_claimed_once(an, binh, db, group, binh_user):
    group.created_by_id = None
    db.commit()
    assert topic_of(binh, group.id)["owner"] is None
    assert binh.post(f"/api/knowledge/topics/{group.id}/owner").status_code == 200
    db.expire_all()
    assert db.get(KnowledgeTopic, group.id).created_by_id == binh_user.id
    taken = an.post(f"/api/knowledge/topics/{group.id}/owner")
    assert (taken.status_code, taken.json()["message"]) == (409, "Nhóm “Già Mà Khỏe” đã có người tạo")
