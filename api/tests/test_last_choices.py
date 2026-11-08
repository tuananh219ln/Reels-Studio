"""Each member's last choices, kept on the server by account (brief docs/specs/chu-thuong-ca-nhan-hoa, part B3): the
forms that pick a Page or a topic group start on them, never on a teammate's."""

import pytest
from conftest import first_topic, login, make_user, make_video
from test_fanpage_checks import add_page

from reels_api.models import KnowledgeTopic


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def test_a_member_without_choices_has_none(an):
    assert an.get("/api/me/last-choices").json() == {"fanpage_id": None, "knowledge_topic_id": None}


def test_each_choice_is_kept_on_its_own_and_only_for_its_member(an, client, db, me):
    group = first_topic(db)
    page = add_page(db, me)

    assert an.patch("/api/me/last-choices", json={"knowledge_topic_id": group.id}).json() == {
        "fanpage_id": None,
        "knowledge_topic_id": group.id,
    }
    # Saving the Page keeps the group.
    assert an.patch("/api/me/last-choices", json={"fanpage_id": page.id}).json() == {
        "fanpage_id": page.id,
        "knowledge_topic_id": group.id,
    }
    assert an.get("/api/me/last-choices").json() == {"fanpage_id": page.id, "knowledge_topic_id": group.id}

    make_user(db, email="binh@doi.vn", name="Trần Bình")
    login(client, email="binh@doi.vn")
    assert client.get("/api/me/last-choices").json() == {"fanpage_id": None, "knowledge_topic_id": None}


def test_a_page_or_group_that_is_not_there_is_refused(an, db):
    assert an.patch("/api/me/last-choices", json={"fanpage_id": 999999}).status_code == 404
    assert an.patch("/api/me/last-choices", json={"knowledge_topic_id": 999999}).status_code == 404
    assert an.get("/api/me/last-choices").json() == {"fanpage_id": None, "knowledge_topic_id": None}


def test_a_removed_group_is_no_longer_a_choice(an, db):
    garden = KnowledgeTopic(name="Vườn rau tại nhà")
    db.add(garden)
    db.commit()
    an.patch("/api/me/last-choices", json={"knowledge_topic_id": garden.id})

    db.delete(garden)
    db.commit()
    db.expire_all()

    assert an.get("/api/me/last-choices").json()["knowledge_topic_id"] is None


def test_last_choices_need_a_signed_in_member(client):
    assert client.get("/api/me/last-choices").status_code == 401
    assert client.patch("/api/me/last-choices", json={"fanpage_id": 1}).status_code == 401


def test_a_video_says_its_group_and_the_group_of_each_page(an, db, storage, me):
    group = first_topic(db)
    page = add_page(db, me)
    page.knowledge_topic_id = group.id
    db.commit()
    video = make_video(db, storage, me)

    detail = an.get(f"/api/videos/{video.id}").json()
    assert detail["knowledge_topic_id"] == video.knowledge_topic_id
    assert [(row["id"], row["knowledge_topic_id"]) for row in detail["fanpages"]] == [(page.id, group.id)]
