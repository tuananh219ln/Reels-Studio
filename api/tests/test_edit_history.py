"""Edit history ("Lịch sử") of Kho kiến thức: every create, edit, delete and restore of a topic group is logged with
its values before and after, and any version of a prompt can be put back by any member
(docs/decisions/2026-11-09-edit-history.md)."""

import pytest
from conftest import first_topic, login, make_user

from reels_api.knowledge import default_script_prompt

LOGS = "/api/edit-logs"
RESTORE = "/api/edit-logs/restore"


@pytest.fixture
def an(client, db):
    make_user(db)
    login(client)
    return client


def topic_of(client, topic_id: int) -> dict:
    return next(row for row in client.get("/api/knowledge").json()["topics"] if row["id"] == topic_id)


def history(client, topic_id: int | None = None, field: str | None = None) -> list[dict]:
    params = {"entity_type": "knowledge_topic"}
    if topic_id is not None:
        params["entity_id"] = topic_id
    if field is not None:
        params["field"] = field
    response = client.get(LOGS, params=params)
    assert response.status_code == 200, response.text
    return response.json()["entries"]


def save(client, topic_id: int, **body) -> None:
    response = client.patch(f"/api/knowledge/topics/{topic_id}", json=body)
    assert response.status_code == 200, response.text


def test_saving_a_prompt_logs_who_and_the_whole_text_before_and_after(an, db):
    topic = first_topic(db)
    old = topic.script_prompt
    save(an, topic.id, script_prompt="Viết kịch bản mới về [Chủ đề]")

    [entry] = history(an, topic.id, "script_prompt")
    assert entry["action"] == "update"
    assert entry["user"]["name"] == "Nguyễn Văn An"
    assert entry["source"] == "web"
    assert entry["changes"] == {"script_prompt": {"old": old, "new": "Viết kịch bản mới về [Chủ đề]"}}
    assert topic_of(an, topic.id)["last_edit"]["id"] == entry["id"]


def test_a_save_that_changes_nothing_is_not_logged(an, db):
    topic = first_topic(db)
    save(an, topic.id, script_prompt=topic.script_prompt)
    assert history(an, topic.id) == []
    assert topic_of(an, topic.id)["last_edit"] is None


def test_banned_words_voice_and_plan_prompt_are_logged_by_field(an, db):
    topic = first_topic(db)
    save(an, topic.id, banned_words=["chữa khỏi"])
    save(an, topic.id, voice_id="vieneu:Huyền My")
    response = an.patch(f"/api/plans/{topic.id}", json={"prompt": "Lên kế hoạch 30 ngày cho [Nhóm]"})
    assert response.status_code == 200, response.text

    assert history(an, topic.id, "banned_words")[0]["changes"]["banned_words"]["new"] == ["chữa khỏi"]
    assert history(an, topic.id, "voice_id")[0]["changes"]["voice_id"]["new"] == "vieneu:Huyền My"
    assert history(an, topic.id, "plan_prompt")[0]["changes"]["plan_prompt"]["new"] == "Lên kế hoạch 30 ngày cho [Nhóm]"
    assert len(history(an, topic.id)) == 3


def test_creating_renaming_and_deleting_a_group_stay_in_the_lists_history(an, db):
    created = an.post("/api/knowledge/topics", json={"name": "Mẹo vặt"})
    assert created.status_code == 201, created.text
    topic_id = next(row["id"] for row in created.json()["topics"] if row["name"] == "Mẹo vặt")
    save(an, topic_id, name="Mẹo vặt nhà bếp", photo_hint="bếp gia đình")
    assert an.delete(f"/api/knowledge/topics/{topic_id}").status_code == 200

    actions = [(entry["action"], entry["label"]) for entry in history(an, field="name")]
    assert actions[:3] == [("delete", "Mẹo vặt nhà bếp"), ("update", "Mẹo vặt nhà bếp"), ("create", "Mẹo vặt")]
    deleted = history(an, field="name")[0]
    # What the group held is still readable after it is gone.
    assert deleted["changes"]["photo_hint"] == {"old": "bếp gia đình", "new": None}


def test_any_member_puts_back_an_earlier_version_as_a_new_restore_entry(an, client, db):
    topic = first_topic(db)
    save(an, topic.id, script_prompt="Bản A về [Chủ đề]")
    save(an, topic.id, script_prompt="Bản B về [Chủ đề]")
    version_a = history(an, topic.id, "script_prompt")[1]

    make_user(db, email="binh@doi.vn", name="Trần Bình")
    login(client, email="binh@doi.vn")
    response = client.post(
        RESTORE,
        json={
            "entity_type": "knowledge_topic",
            "entity_id": topic.id,
            "field": "script_prompt",
            "log_id": version_a["id"],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["value"] == "Bản A về [Chủ đề]"
    assert topic_of(client, topic.id)["script_prompt"] == "Bản A về [Chủ đề]"

    entries = history(client, topic.id, "script_prompt")
    assert len(entries) == 3
    assert entries[0]["action"] == "restore"
    assert entries[0]["user"]["name"] == "Trần Bình"
    assert entries[0]["restored_from_id"] == version_a["id"]
    assert entries[0]["changes"]["script_prompt"] == {"old": "Bản B về [Chủ đề]", "new": "Bản A về [Chủ đề]"}


def test_the_version_from_before_the_history_began_can_be_put_back(an, db):
    topic = first_topic(db)
    original = topic.script_prompt
    save(an, topic.id, script_prompt="Bản mới về [Chủ đề]")
    first = history(an, topic.id, "script_prompt")[0]
    response = an.post(
        RESTORE,
        json={
            "entity_type": "knowledge_topic",
            "entity_id": topic.id,
            "field": "script_prompt",
            "log_id": first["id"],
            "side": "old",
        },
    )
    assert response.status_code == 200, response.text
    assert topic_of(an, topic.id)["script_prompt"] == original


def test_the_apps_default_prompt_is_a_version_of_its_own(an, db):
    topic = first_topic(db)
    save(an, topic.id, script_prompt="Bản riêng về [Chủ đề]", article_prompt="Viết bài riêng")
    for field, expected in (("script_prompt", default_script_prompt()), ("article_prompt", "")):
        response = an.post(
            RESTORE, json={"entity_type": "knowledge_topic", "entity_id": topic.id, "field": field, "log_id": None}
        )
        assert response.status_code == 200, response.text
        assert topic_of(an, topic.id)[field] == expected


def test_restoring_the_text_already_in_use_or_a_field_not_restorable_is_refused(an, db):
    topic = first_topic(db)
    save(an, topic.id, script_prompt="Bản A về [Chủ đề]")
    latest = history(an, topic.id, "script_prompt")[0]
    same = an.post(
        RESTORE,
        json={
            "entity_type": "knowledge_topic",
            "entity_id": topic.id,
            "field": "script_prompt",
            "log_id": latest["id"],
        },
    )
    assert same.status_code == 422
    assert same.json()["message"] == "Nội dung đang dùng đã giống bản này"

    save(an, topic.id, name="Sức khỏe mới")
    renamed = history(an, topic.id, "name")[0]
    name = an.post(
        RESTORE,
        json={"entity_type": "knowledge_topic", "entity_id": topic.id, "field": "name", "log_id": renamed["id"]},
    )
    assert name.status_code == 422
    assert topic_of(an, topic.id)["name"] == "Sức khỏe mới"


def test_an_entry_of_another_group_cannot_be_put_back_here(an, db):
    topic = first_topic(db)
    save(an, topic.id, script_prompt="Bản A về [Chủ đề]")
    entry = history(an, topic.id, "script_prompt")[0]
    created = an.post("/api/knowledge/topics", json={"name": "Nhóm khác"}).json()
    other = next(row["id"] for row in created["topics"] if row["name"] == "Nhóm khác")
    response = an.post(
        RESTORE,
        json={"entity_type": "knowledge_topic", "entity_id": other, "field": "script_prompt", "log_id": entry["id"]},
    )
    assert response.status_code == 404


def test_history_needs_a_login_and_a_known_kind(app, an):
    assert an.get(LOGS, params={"entity_type": "videos"}).status_code == 422
    an.post("/api/auth/logout")
    assert an.get(LOGS, params={"entity_type": "knowledge_topic"}).status_code == 401
