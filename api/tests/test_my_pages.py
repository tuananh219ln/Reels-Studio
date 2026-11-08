"""A member's own Pages and topic groups come first where they pick one (brief docs/specs/chu-thuong-ca-nhan-hoa,
part B2): "my" topic groups are those of the Pages they own and use."""

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


def test_my_topic_groups_are_those_of_the_pages_i_own_and_use(an, db, me):
    health = first_topic(db)
    garden = KnowledgeTopic(name="Vườn rau tại nhà")
    beauty = KnowledgeTopic(name="Làm đẹp")
    db.add_all([garden, beauty])
    db.flush()
    binh = make_user(db, email="binh@doi.vn", name="Trần Bình")
    mine = add_page(db, me, page_id="111", name="Trang của An")
    mine.knowledge_topic_id = garden.id
    stopped = add_page(db, me, page_id="222", name="Trang An ngừng")
    stopped.knowledge_topic_id, stopped.active = beauty.id, False
    theirs = add_page(db, binh, page_id="333", name="Trang của Bình")
    theirs.knowledge_topic_id = health.id
    db.commit()

    topics = {topic["name"]: topic["mine"] for topic in an.get("/api/knowledge").json()["topics"]}
    assert topics == {health.name: False, "Vườn rau tại nhà": True, "Làm đẹp": False}


def test_a_videos_pages_say_which_are_mine(an, db, me, storage):
    binh = make_user(db, email="binh@doi.vn", name="Trần Bình")
    add_page(db, me, page_id="111", name="Trang của An")
    add_page(db, binh, page_id="333", name="Trang của Bình")
    video = make_video(db, storage, me)
    pages = {page["name"]: page["owner_id"] for page in an.get(f"/api/videos/{video.id}").json()["fanpages"]}
    assert pages == {"Trang của An": me.id, "Trang của Bình": binh.id}
