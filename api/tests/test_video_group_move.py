"""Moving a video to another topic group ("Chuyển sang nhóm khác" on the video page)."""

import pytest
from conftest import first_topic, login, make_user, make_video
from sqlalchemy import select

from reels_api.models import Job, KnowledgeTopic, TopicPlanItem, Video


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


@pytest.fixture
def other_group(db):
    group = KnowledgeTopic(name="Già Mà Khỏe", script_prompt="Viết về [Chủ đề]")
    db.add(group)
    db.commit()
    return group


def test_a_video_moves_to_another_group_and_leaves_its_old_plan_idea(an, db, me, storage, other_group):
    video = make_video(db, storage, me)
    idea = TopicPlanItem(
        knowledge_topic_id=video.knowledge_topic_id, day=1, position=1, topic="Ý tưởng", video_id=video.id
    )
    db.add(idea)
    db.commit()

    answer = an.put(f"/api/videos/{video.id}/group", json={"knowledge_topic_id": other_group.id})

    assert answer.status_code == 200
    assert answer.json()["knowledge_topic_id"] == other_group.id
    assert answer.json()["knowledge_topic"] == "Già Mà Khỏe"
    db.expire_all()
    assert db.get(Video, video.id).knowledge_topic_id == other_group.id
    # The old group's idea is free again, so its plan shows it as still to make.
    assert db.get(TopicPlanItem, idea.id).video_id is None
    assert [row["id"] for row in an.get(f"/api/videos?knowledge_topic_id={other_group.id}").json()] == [video.id]


def test_only_the_videos_maker_moves_it(client, db, me, storage, other_group):
    video = make_video(db, storage, me)
    make_user(db, email="binh@doi.vn", name="Trần Thị Bình")
    login(client, "binh@doi.vn")

    answer = client.put(f"/api/videos/{video.id}/group", json={"knowledge_topic_id": other_group.id})

    assert answer.status_code == 403
    db.expire_all()
    assert db.get(Video, video.id).knowledge_topic_id == first_topic(db).id


def test_moving_to_a_missing_group_or_its_own_group_is_refused(an, db, me, storage):
    video = make_video(db, storage, me)

    assert an.put(f"/api/videos/{video.id}/group", json={"knowledge_topic_id": 999999}).status_code == 404
    same = an.put(f"/api/videos/{video.id}/group", json={"knowledge_topic_id": video.knowledge_topic_id})
    assert same.status_code == 422
    assert "đã ở nhóm" in same.json()["message"]


def test_a_video_being_rendered_is_not_moved(an, db, me, storage, other_group):
    video = make_video(db, storage, me)
    db.add(Job(video_id=video.id, kind="render", status="running", created_by_id=me.id))
    db.commit()

    assert an.put(f"/api/videos/{video.id}/group", json={"knowledge_topic_id": other_group.id}).status_code == 409
    assert db.scalar(select(Video.knowledge_topic_id).where(Video.id == video.id)) == first_topic(db).id


def _group_maker(client, db, video):
    """A teammate who made the group the video sits in, and is signed in."""
    maker = make_user(db, email="binh@doi.vn", name="Trần Thị Bình")
    first_topic(db).created_by_id = maker.id
    db.commit()
    login(client, "binh@doi.vn")
    return maker


def test_a_groups_maker_sends_a_teammates_video_back_to_a_group_its_maker_made(client, db, me, storage, other_group):
    video = make_video(db, storage, me)
    _group_maker(client, db, video)
    other_group.created_by_id = me.id
    db.commit()

    answer = client.put(f"/api/videos/{video.id}/group", json={"knowledge_topic_id": other_group.id})

    assert answer.status_code == 200
    db.expire_all()
    assert db.get(Video, video.id).knowledge_topic_id == other_group.id
    assert client.get(f"/api/videos/{video.id}").json()["knowledge_topic_owner_id"] == me.id


def test_a_groups_maker_only_sends_the_video_to_a_group_of_the_videos_maker(client, db, me, storage, other_group):
    video = make_video(db, storage, me)
    maker = _group_maker(client, db, video)
    other_group.created_by_id = maker.id  # the group maker's own group, not the video maker's
    db.commit()

    answer = client.put(f"/api/videos/{video.id}/group", json={"knowledge_topic_id": other_group.id})

    assert answer.status_code == 403
    db.expire_all()
    assert db.get(Video, video.id).knowledge_topic_id == first_topic(db).id
