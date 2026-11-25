"""Nhân bản nhóm: a new group with the prompts and settings of another, none of its videos, plan, documents or folder."""

import pytest
from conftest import login, make_user, make_video

from reels_api.models import KnowledgeTopic, TopicDoc


@pytest.fixture
def an(db):
    return make_user(db)


def source(db, maker) -> KnowledgeTopic:
    topic = KnowledgeTopic(
        name="Nhóm gốc",
        created_by_id=maker.id,
        script_prompt="Viết kịch bản ngắn",
        clone_prompt="Nhân bản",
        revise_prompt="Sửa",
        learn_prompt="Học",
        analyze_prompt="Phân tích",
        article_prompt="Bài viết",
        plan_prompt="Kế hoạch",
        banned_words=["cấm"],
        photo_hint="Ảnh món ăn",
        voice_id="voice-1",
        video_mode="single",
        no_people=True,
        outro_cta=True,
        team_edit=False,
        media_folder="Thư mục gốc",
    )
    db.add(topic)
    db.commit()
    return topic


def topics(client) -> list[dict]:
    return client.get("/api/knowledge").json()["topics"]


def test_a_copy_keeps_the_prompts_and_settings_and_nothing_else(client, db, an, storage):
    topic = source(db, an)
    video = make_video(db, storage, an, scene_count=1)
    video.knowledge_topic_id = topic.id
    db.add(TopicDoc(knowledge_topic_id=topic.id, section="job", name="a.md", body="x"))
    db.commit()
    login(client)
    response = client.post(f"/api/knowledge/topics/{topic.id}/duplicate")
    assert response.status_code == 201, response.text
    copy = next(t for t in response.json()["topics"] if t["name"] == "Nhóm gốc (bản sao)")
    assert copy["id"] != topic.id
    assert copy["script_prompt"] == "Viết kịch bản ngắn"
    assert (copy["clone_prompt"], copy["revise_prompt"], copy["learn_prompt"]) == ("Nhân bản", "Sửa", "Học")
    assert (copy["analyze_prompt"], copy["article_prompt"]) == ("Phân tích", "Bài viết")
    assert (copy["banned_words"], copy["photo_hint"], copy["voice_id"]) == (["cấm"], "Ảnh món ăn", "voice-1")
    assert (copy["video_mode"], copy["no_people"], copy["outro_cta"]) == ("single", True, True)
    # Its own: no videos, no documents, no linked folder, made by the member who copied it, open to the team.
    assert (copy["video_count"], copy["readiness"]["docs"], copy["media_folder"]) == (0, 0, None)
    assert (copy["created_by_id"], copy["team_edit"]) == (an.id, True)


def test_a_teammates_group_can_be_copied_and_a_second_copy_is_numbered(client, db, an):
    binh = make_user(db, email="binh@doi.vn", name="Bình")
    topic = source(db, binh)
    login(client)
    client.post(f"/api/knowledge/topics/{topic.id}/duplicate")
    second = client.post(f"/api/knowledge/topics/{topic.id}/duplicate")
    names = {t["name"] for t in second.json()["topics"]}
    assert {"Nhóm gốc (bản sao)", "Nhóm gốc (bản sao 2)"} <= names


def test_an_unknown_group_is_a_404(client, db, an):
    login(client)
    assert client.post("/api/knowledge/topics/999999/duplicate").status_code == 404
