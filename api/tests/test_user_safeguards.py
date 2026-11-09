"""Quản lý người dùng safeguards (2026-11-09, Part 3, "no roles" kept): who disabled, enabled or set a temporary
password and when is kept and shown, and a disabled member's Pages, topic groups, plan ideas and templates can be
handed to an active member."""

import pytest
from conftest import first_topic, login, make_user

from reels_api.models import AffiliateAccount, EditTemplate, Fanpage, KnowledgeTopic, TopicPlanItem


@pytest.fixture
def me(client, db):
    user = make_user(db)
    login(client)
    return user


@pytest.fixture
def binh(db):
    return make_user(db, email="binh@doi.vn", name="Trần Bình")


@pytest.fixture
def chi(db):
    return make_user(db, email="chi@doi.vn", name="Lê Chi")


def row_for(client, user_id):
    return next(row for row in client.get("/api/users").json() if row["id"] == user_id)


def test_disabling_enabling_and_a_temp_password_are_kept_and_shown(client, db, me, binh):
    assert row_for(client, binh.id)["last_action"] is None
    client.post(f"/api/users/{binh.id}/disable", json={})
    last = row_for(client, binh.id)["last_action"]
    assert (last["action"], last["by"]) == ("disable", "Nguyễn Văn An") and last["at"]
    client.post(f"/api/users/{binh.id}/temp-password", json={"password": "tam-moi-1234"})
    assert row_for(client, binh.id)["last_action"]["action"] == "temp_password"
    client.post(f"/api/users/{binh.id}/enable")
    assert row_for(client, binh.id)["last_action"]["action"] == "enable"
    history = client.get(f"/api/edit-logs?entity_type=user&entity_id={binh.id}").json()["entries"]
    assert [list(entry["changes"]) for entry in history] == [["is_active"], ["temp_password"], ["is_active"]]
    # The password itself is never logged.
    assert "tam-moi-1234" not in str(history)
    assert all(entry["label"] == "Trần Bình" for entry in history)


def test_enabling_an_active_member_logs_nothing(client, db, me, binh):
    client.post(f"/api/users/{binh.id}/enable")
    assert client.get(f"/api/edit-logs?entity_type=user&entity_id={binh.id}").json()["entries"] == []


def owned_by(db, user):
    """A Page with Binh's own Shopee and TikTok accounts and semi-auto on, a group, a plan idea and a template."""
    shopee = AffiliateAccount(owner_id=user.id, platform="shopee", name="Shopee của Bình")
    tiktok = AffiliateAccount(owner_id=user.id, platform="tiktok", name="TikTok của Bình")
    db.add_all([shopee, tiktok])
    db.flush()
    group = KnowledgeTopic(name="Gan", created_by_id=user.id)
    db.add(group)
    db.flush()
    page = Fanpage(
        page_id="p-binh",
        name="Trang Bình",
        token_encrypted="x",
        token_tail="x",
        owner_id=user.id,
        shopee_account_id=shopee.id,
        tiktok_account_id=tiktok.id,
        auto_prepare=True,
        knowledge_topic_id=group.id,
    )
    idea = TopicPlanItem(
        knowledge_topic_id=first_topic(db).id, day=1, position=1, topic="Ý của Bình", created_by_id=user.id
    )
    template = EditTemplate(name="Mẫu Bình", data={}, created_by_id=user.id)
    db.add_all([page, idea, template])
    db.commit()
    return page, group, idea, template


def test_disabling_hands_the_members_things_to_a_chosen_active_member(client, db, me, binh, chi):
    page, group, idea, template = owned_by(db, binh)
    response = client.post(f"/api/users/{binh.id}/disable", json={"transfer_to": chi.id})
    assert response.status_code == 200, response.text
    db.expire_all()
    assert page.owner_id == group.created_by_id == idea.created_by_id == template.created_by_id == chi.id
    # Binh's own affiliate accounts are not Chi's: the Page drops them, and semi-auto waits for Chi to turn it on.
    assert (page.shopee_account_id, page.tiktok_account_id, page.auto_prepare) == (None, None, False)
    [entry] = client.get(f"/api/edit-logs?entity_type=user&entity_id={binh.id}").json()["entries"]
    assert entry["changes"]["transfer"]["new"] == "1 Page, 1 nhóm chủ đề, 1 ý tưởng, 1 mẫu dựng cho Lê Chi"


def test_without_a_choice_the_things_stay_the_disabled_members(client, db, me, binh):
    page, *_ = owned_by(db, binh)
    client.post(f"/api/users/{binh.id}/disable", json={})
    db.expire_all()
    assert page.owner_id == binh.id


@pytest.mark.parametrize("who", ["self", "binh", "disabled", "nobody"])
def test_things_go_only_to_another_active_member(client, db, me, binh, chi, who):
    owned_by(db, binh)
    client.post(f"/api/users/{chi.id}/disable", json={})
    target = {"self": me.id, "binh": binh.id, "disabled": chi.id, "nobody": 999999}[who]
    refused = client.post(f"/api/users/{binh.id}/disable", json={"transfer_to": target})
    if who == "self":
        assert refused.status_code == 200  # the one disabling may take them
        return
    assert refused.status_code == 422, refused.text
    assert refused.json()["message"] == "Hãy chọn một thành viên khác đang hoạt động để nhận"
    db.expire_all()
    assert db.get(type(binh), binh.id).is_active
