"""What a group still lacks before it can make and post videos ("Sẵn sàng tạo video" on Kho kiến thức)."""

from datetime import date

import pytest
from conftest import login, make_user

from reels_api.models import AffiliateProduct, Fanpage, KnowledgeTopic, TopicDoc


@pytest.fixture
def me(db):
    return make_user(db)


def topic_of(client, topic_id) -> dict:
    return next(t for t in client.get("/api/knowledge").json()["topics"] if t["id"] == topic_id)


def new_topic(db, me, **fields) -> KnowledgeTopic:
    topic = KnowledgeTopic(name="Nhóm mới", created_by_id=me.id, **fields)
    db.add(topic)
    db.commit()
    return topic


def test_a_new_group_lacks_everything(client, db, me):
    topic = new_topic(db, me)
    login(client)
    assert topic_of(client, topic.id)["readiness"] == {"pages": 0, "docs": 0, "products": 0, "plan_started": False}


def test_each_step_counts_what_the_group_has(client, db, me):
    topic = new_topic(db, me, plan_start_date=date(2026, 11, 20))
    db.add(Fanpage(page_id="p1", name="A", token_encrypted="x", token_tail="x", knowledge_topic_id=topic.id))
    db.add(
        Fanpage(page_id="p2", name="B", token_encrypted="x", token_tail="x", knowledge_topic_id=topic.id, active=False)
    )
    db.add(TopicDoc(knowledge_topic_id=topic.id, section="job", name="van-hanh.md", body="x"))
    for status in ("approved", "draft"):
        db.add(
            AffiliateProduct(
                knowledge_topic_id=topic.id,
                name=status,
                shop_name="s",
                shop_type="mall",
                rating=5,
                sold=500,
                price=1000,
                commission_rate=5,
                status=status,
                created_by_id=me.id,
            )
        )
    db.commit()
    login(client)
    assert topic_of(client, topic.id)["readiness"] == {"pages": 1, "docs": 1, "products": 1, "plan_started": True}
