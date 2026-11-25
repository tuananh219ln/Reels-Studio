"""A group that several Pages post: its Pages are listed, and the group's videos and the revenue can be read for one."""

from datetime import UTC, datetime

import pytest
from conftest import login, make_user, make_video

from reels_api.models import (
    AffiliateAccount,
    AffiliateConversion,
    Fanpage,
    KnowledgeTopic,
    PageQueueItem,
    Publication,
)


@pytest.fixture
def me(db):
    return make_user(db)


def page(db, topic, name, active=True) -> Fanpage:
    row = Fanpage(
        page_id=f"fb-{name}", name=name, token_encrypted="x", token_tail="x", knowledge_topic_id=topic.id, active=active
    )
    db.add(row)
    db.commit()
    return row


def group(db, me) -> KnowledgeTopic:
    topic = KnowledgeTopic(name="Nhóm hai Page", created_by_id=me.id)
    db.add(topic)
    db.commit()
    return topic


def test_the_group_lists_its_active_pages(client, db, me):
    topic = group(db, me)
    a = page(db, topic, "Page A")
    page(db, topic, "Page tắt", active=False)
    b = page(db, topic, "Page B")
    login(client)
    found = next(t for t in client.get("/api/knowledge").json()["topics"] if t["id"] == topic.id)
    assert found["page_list"] == [{"id": a.id, "name": "Page A"}, {"id": b.id, "name": "Page B"}]


def test_a_groups_videos_can_be_kept_to_one_page(client, db, me, storage):
    topic = group(db, me)
    a, b = page(db, topic, "Page A"), page(db, topic, "Page B")
    posted_on_a = make_video(db, storage, me, scene_count=1)
    waiting_for_b = make_video(db, storage, me, scene_count=1)
    nowhere = make_video(db, storage, me, scene_count=1)
    for video in (posted_on_a, waiting_for_b, nowhere):
        video.knowledge_topic_id = topic.id
    db.add(
        Publication(
            video_id=posted_on_a.id,
            platform="facebook",
            status="published",
            remote_id="r1",
            fanpage_id=a.id,
            created_by_id=me.id,
            published_at=datetime.now(UTC),
        )
    )
    db.add(PageQueueItem(fanpage_id=b.id, video_id=waiting_for_b.id, position=1, added_by_id=me.id))
    db.commit()
    login(client)

    def ids(**params):
        rows = client.get("/api/videos", params={"knowledge_topic_id": topic.id, **params}).json()
        return {row["id"] for row in rows}

    assert ids() == {posted_on_a.id, waiting_for_b.id, nowhere.id}
    assert ids(fanpage_id=a.id) == {posted_on_a.id}
    assert ids(fanpage_id=b.id) == {waiting_for_b.id}


def test_revenue_can_be_read_for_one_page(client, db, me, storage):
    topic = group(db, me)
    a, b = page(db, topic, "Page A"), page(db, topic, "Page B")
    account = AffiliateAccount(platform="shopee", owner_id=me.id, name="Của tôi")
    db.add(account)
    db.commit()
    now = datetime.now(UTC)
    for n, (target, commission) in enumerate([(a, 1000), (a, 500), (b, 7000)]):
        db.add(
            AffiliateConversion(
                account_id=account.id,
                external_id=f"o{n}",
                fanpage_id=target.id,
                purchased_at=now,
                item_name="Món",
                commission=commission,
                status="PENDING",
                read_at=now,
            )
        )
    db.commit()
    login(client)
    everyone = client.get("/api/affiliate-accounts/revenue").json()
    assert (everyone["orders"], everyone["commission"]) == (3, 8500)
    assert {line["fanpage_id"] for line in everyone["lines"]} == {a.id, b.id}
    only_a = client.get("/api/affiliate-accounts/revenue", params={"fanpage_id": a.id}).json()
    assert (only_a["orders"], only_a["commission"]) == (2, 1500)
