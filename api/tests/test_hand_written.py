"""A video written by hand ("Tự viết"): no AI call, the pasted script split into scenes, editable at once."""

import pytest
from conftest import first_topic, login, make_user
from sqlalchemy import select

from reels_api.models import Job, KnowledgeTopic, Scene, TopicPlanItem, Video


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def scenes_of(db, video_id) -> list[Scene]:
    return list(
        db.scalars(select(Scene).where(Scene.video_id == video_id).order_by(Scene.is_title.desc(), Scene.position))
    )


def create(an, db, **body):
    return an.post("/api/videos", json={"knowledge_topic_id": first_topic(db).id, "mode": "manual", **body})


def test_a_hand_written_video_queues_no_job_and_is_ready_to_edit(an, db):
    reply = create(an, db, topic="  6 món  *bổ xương* ")
    assert reply.status_code == 201
    video = reply.json()
    assert (video["active_job"], video["locked"], video["hand_written"]) == (None, False, True)
    assert db.scalar(select(Job).where(Job.video_id == video["id"])) is None, "no LLM call is ever made"
    title, scene = scenes_of(db, video["id"])
    assert (title.is_title, title.text, title.seconds) == (True, "6 món *bổ xương*", 3)
    assert (scene.is_title, scene.text, scene.voice_text, scene.seconds) == (False, "", "", 4)
    assert video["title_options"] == ["6 món *bổ xương*"]
    assert video["script_by"] is None


def test_a_pasted_script_becomes_one_scene_per_paragraph_with_its_voice_lines(an, db):
    script = (
        "Vừng đen\n*giàu canxi*\nĐọc: Vừng đen giàu canxi, giúp xương chắc khỏe hơn mỗi ngày.\n"
        "\n\n"
        "  Cá hồi  \n"
        "đọc:Omega 3 trong cá hồi giảm đau khớp.\n"
        "\n"
        "Đọc: Chỉ có lời đọc, không có chữ."
    )
    video = create(an, db, topic="xương khớp", script=script).json()
    _, *scenes = scenes_of(db, video["id"])
    assert [(scene.position, scene.text, scene.voice_text) for scene in scenes] == [
        (1, "Vừng đen\n*giàu canxi*", "Vừng đen giàu canxi, giúp xương chắc khỏe hơn mỗi ngày."),
        (2, "Cá hồi", "Omega 3 trong cá hồi giảm đau khớp."),
        (3, "", "Chỉ có lời đọc, không có chữ."),
    ]


def test_a_new_scene_can_be_added_to_a_hand_written_video_at_once(an, db):
    video = create(an, db, topic="tim mạch").json()
    reply = an.post(f"/api/videos/{video['id']}/scenes")
    assert reply.status_code == 201
    assert len(reply.json()["scenes"]) == 2


def test_a_group_without_a_script_prompt_can_still_make_a_hand_written_video(an, db):
    group = KnowledgeTopic(name="Nhóm trống", script_prompt="", clone_prompt="", banned_words=[])
    db.add(group)
    db.commit()
    ai = an.post("/api/videos", json={"topic": "x", "knowledge_topic_id": group.id})
    assert ai.status_code == 422, "the AI still needs the group's prompt"
    manual = an.post("/api/videos", json={"topic": "x", "knowledge_topic_id": group.id, "mode": "manual"})
    assert manual.status_code == 201


def test_a_hand_written_video_still_needs_a_group_and_a_topic(an, db):
    assert an.post("/api/videos", json={"topic": "x", "mode": "manual"}).json()["message"] == "Hãy chọn nhóm chủ đề"
    assert create(an, db, topic="  ").json()["message"] == "Hãy nhập chủ đề"


def test_a_script_too_long_or_with_too_many_scenes_is_refused(an, db):
    too_long = create(an, db, topic="x", script="chữ " * 2000)
    assert (too_long.status_code, too_long.json()["message"]) == (422, "Kịch bản dài quá 5000 ký tự")
    many = create(an, db, topic="x", script="\n\n".join(f"Cảnh {n}" for n in range(21)))
    assert (many.status_code, many.json()["message"]) == (422, "Kịch bản có quá 20 cảnh")
    assert db.scalar(select(Video)) is None


def test_a_plan_idea_can_be_made_by_hand(an, db):
    group = first_topic(db)
    idea = TopicPlanItem(knowledge_topic_id=group.id, day=1, position=1, topic="đau gối")
    db.add(idea)
    db.commit()
    video = create(an, db, topic="đau gối", plan_item_id=idea.id).json()
    db.refresh(idea)
    assert idea.video_id == video["id"]


def test_an_ai_video_is_not_hand_written(an, db):
    video = an.post("/api/videos", json={"topic": "tim", "knowledge_topic_id": first_topic(db).id}).json()
    assert video["hand_written"] is False
