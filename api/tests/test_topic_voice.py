"""A topic group's own narration voice ("Giọng mặc định của nhóm"): a new video of the group starts with it, over its
maker's defaults (brief docs/specs/semi-auto-posting, "Bổ sung 1")."""

import pytest
from conftest import first_topic, login, make_user
from sqlalchemy import update

from reels_api.models import Job, KnowledgeTopic, Video

MINE = "/api/settings/my-video-defaults"
CHI = "vieneu:Huyền My"


@pytest.fixture
def an(client, db):
    make_user(db)
    login(client)
    return client


def set_voice(client, topic_id: int, voice: str):
    return client.patch(f"/api/knowledge/topics/{topic_id}", json={"voice_id": voice})


def new_video(client, topic_id: int) -> dict:
    response = client.post("/api/videos", json={"topic": "tim mạch", "knowledge_topic_id": topic_id})
    assert response.status_code == 201, response.text
    return response.json()


def test_a_group_has_no_voice_until_one_is_set(an, db):
    topic = first_topic(db)
    listed = next(row for row in an.get("/api/knowledge").json()["topics"] if row["id"] == topic.id)
    assert listed["voice_id"] == ""


def test_a_new_video_of_a_group_takes_the_groups_voice_over_its_makers_defaults(an, db):
    topic = first_topic(db)
    an.put(MINE, json={"values": {"voice_id": "elevenAdam01"}})
    saved = set_voice(an, topic.id, CHI)
    assert saved.status_code == 200, saved.text
    assert next(row for row in saved.json()["topics"] if row["id"] == topic.id)["voice_id"] == CHI

    video = new_video(an, topic.id)
    assert video["options"]["voice_id"] == CHI


def test_without_a_group_voice_the_makers_defaults_stay(an, db):
    topic = first_topic(db)
    an.put(MINE, json={"values": {"voice_id": "elevenAdam01"}})
    assert new_video(an, topic.id)["options"]["voice_id"] == "elevenAdam01"


def test_the_group_voice_reaches_only_its_own_groups_videos(an, db):
    topic = first_topic(db)
    other = KnowledgeTopic(name="Già Mà Khỏe", script_prompt="Viết kịch bản về [Chủ đề]")
    db.add(other)
    db.commit()
    set_voice(an, other.id, CHI)
    assert new_video(an, topic.id)["options"]["voice_id"] == ""
    assert new_video(an, other.id)["options"]["voice_id"] == CHI


def test_a_videos_own_voice_wins_and_existing_videos_never_change(an, db):
    topic = first_topic(db)
    before = new_video(an, topic.id)
    set_voice(an, topic.id, CHI)
    assert db.get(Video, before["id"], populate_existing=True).options["voice_id"] == ""

    video = new_video(an, topic.id)
    # The script job a new video queues locks it; as if it had finished.
    db.execute(update(Job).where(Job.video_id == video["id"]).values(status="done"))
    db.commit()
    changed = an.patch(f"/api/videos/{video['id']}", json={"options": {"voice_id": "elevenAdam01"}})
    assert changed.status_code == 200, changed.text
    assert db.get(Video, video["id"], populate_existing=True).options["voice_id"] == "elevenAdam01"


def test_clearing_the_group_voice_goes_back_to_the_makers_defaults(an, db):
    topic = first_topic(db)
    set_voice(an, topic.id, CHI)
    cleared = set_voice(an, topic.id, "")
    assert cleared.status_code == 200, cleared.text
    assert new_video(an, topic.id)["options"]["voice_id"] == ""


def test_a_wrong_voice_id_is_refused(an, db):
    topic = first_topic(db)
    assert set_voice(an, topic.id, "hai  dấu cách").status_code == 422
    assert db.get(KnowledgeTopic, topic.id, populate_existing=True).voice_id == ""
