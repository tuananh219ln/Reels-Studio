"""Part 2 of docs/specs/per-user-settings-ownership: a topic group holds several "Mẫu dựng" and names one for its new
videos, over its maker's own; a template chosen on the video itself wins over both."""

import pytest
from conftest import client_for, first_topic, login, make_user, make_video
from sqlalchemy import select
from test_mcp import GROUP_SCRIPT, call, grant, mcp_client  # noqa: F401 (mcp_client is a fixture)

from reels_api import autoedit
from reels_api.models import EditTemplate, KnowledgeTopic, SceneSound, Video
from reels_api.videos import split_scenes

X = {"transitions": ["circle"], "scene_sounds": [{"sound": "pop", "start": 0.0, "volume": "soft"}]}
Y = {"transitions": ["flash"], "scene_sounds": [{"sound": "ding", "start": 0.0, "volume": "soft"}]}


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


@pytest.fixture
def templates(db, me):
    x = EditTemplate(name="Mẫu X", data=X, created_by_id=me.id)
    y = EditTemplate(name="Mẫu Y", data=Y, created_by_id=me.id)
    db.add_all([x, y])
    db.commit()
    return x, y


def other_group(db) -> KnowledgeTopic:
    group = KnowledgeTopic(name="Nhóm B", script_prompt="Viết kịch bản", clone_prompt="Nhân bản")
    db.add(group)
    db.commit()
    return group


def topic_of(payload: dict, topic_id: int) -> dict:
    return next(topic for topic in payload["topics"] if topic["id"] == topic_id)


def hand_written(client, group_id: int) -> dict:
    made = client.post(
        "/api/videos",
        json={"topic": "rau mầm", "knowledge_topic_id": group_id, "mode": "manual", "script": "Một\n\nHai"},
    )
    assert made.status_code == 201, made.json()
    return made.json()


def attach(client, group_id: int, ids: list[int], default: object) -> dict:
    saved = client.patch(f"/api/knowledge/topics/{group_id}", json={"templates": ids, "edit_template_default": default})
    assert saved.status_code == 200, saved.json()
    return topic_of(saved.json(), group_id)


def test_a_group_holds_several_templates_and_names_one_for_its_new_videos(an, db, me, templates):
    x, y = templates
    group, plain = first_topic(db), other_group(db)
    assert topic_of(an.get("/api/knowledge").json(), group.id)["edit_template_default"] is None
    topic = attach(an, group.id, [x.id, y.id], x.id)
    assert (topic["templates"], topic["edit_template_default"]) == ([x.id, y.id], x.id)

    assert [scene["transition"] for scene in hand_written(an, group.id)["scenes"]] == ["circle", "circle"]
    # A group with no template falls to the maker's own (here none), as in part 1.
    assert [scene["transition"] for scene in hand_written(an, plain.id)["scenes"]] == [None, None]
    an.put("/api/edit-templates/default", json={"template": "app"})
    assert [scene["transition"] for scene in hand_written(an, plain.id)["scenes"]] == ["zoom", "slide"]
    # ...and the group's beats the maker's.
    assert [scene["transition"] for scene in hand_written(an, group.id)["scenes"]] == ["circle", "circle"]

    listing = an.get("/api/edit-templates").json()["templates"]
    assert next(item for item in listing if item["id"] == x.id)["topics"] == [{"id": group.id, "name": group.name}]


def test_a_groups_template_must_be_one_of_its_own_or_the_apps(an, db, templates):
    x, y = templates
    group = first_topic(db)
    refused = an.patch(f"/api/knowledge/topics/{group.id}", json={"templates": [x.id], "edit_template_default": y.id})
    assert refused.status_code == 422
    assert an.patch(f"/api/knowledge/topics/{group.id}", json={"templates": [9999]}).status_code == 422
    assert attach(an, group.id, [x.id], "app")["edit_template_default"] == "app"
    assert attach(an, group.id, [x.id], x.id)["edit_template_default"] == x.id
    # Taking the template off the group takes it off its new videos too.
    left = an.patch(f"/api/knowledge/topics/{group.id}", json={"templates": [y.id]}).json()
    assert topic_of(left, group.id)["edit_template_default"] is None
    # Removing a template takes it off every group.
    attach(an, group.id, [y.id], y.id)
    an.delete(f"/api/edit-templates/{y.id}")
    topic = topic_of(an.get("/api/knowledge").json(), group.id)
    assert (topic["templates"], topic["edit_template_default"]) == ([], None)


def test_a_template_chosen_on_the_video_replaces_the_groups(an, db, me, storage, templates):
    x, y = templates
    group = first_topic(db)
    attach(an, group.id, [x.id, y.id], x.id)
    video = make_video(db, storage, me, scene_count=2)
    autoedit.apply_default(db, video)
    db.commit()
    _, scenes = split_scenes(db, video)
    assert [scene.transition for scene in scenes] == ["circle", "circle"]

    applied = an.post("/api/edit-templates/apply", json={"video_id": video.id, "template": y.id})
    assert applied.status_code == 200, applied.json()
    content = applied.json()["scenes"]
    assert [scene["transition"] for scene in content] == ["flash", "flash"]
    # Only Y's sound is left: the group's template X was taken off as Y went on.
    assert all([sound["sound"] for sound in scene["sounds"]] == ["ding"] for scene in content)
    assert applied.json()["edit_template"] == {"id": y.id, "name": "Mẫu Y", "source": "video"}

    # Its scenes written again (a new script), the video keeps its own choice over the group's.
    autoedit.apply_default(db, video)
    db.commit()
    assert db.scalars(select(SceneSound.sound).where(SceneSound.scene_id == scenes[0].id)).all() == ["ding"]


def test_another_members_video_in_the_group_takes_the_groups_template_too(an, app, db, templates):
    x, _ = templates
    group = first_topic(db)
    attach(an, group.id, [x.id], x.id)
    make_user(db, email="binh@doi.vn", name="Trần Bình")
    binh = client_for(app)
    login(binh, email="binh@doi.vn")
    assert [scene["transition"] for scene in hand_written(binh, group.id)["scenes"]] == ["circle", "circle"]


def test_a_video_made_through_mcp_takes_its_groups_template(mcp_client, db):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    x = EditTemplate(name="Mẫu X", data=X, created_by_id=user.id)
    db.add(x)
    db.flush()
    group = first_topic(db)
    group.edit_templates.append(x)
    group.edit_template_default = x.id
    db.commit()
    made = call(
        mcp_client,
        tokens["access_token"],
        "create_video_from_group_prompt",
        topic="Rau xanh cho tim",
        knowledge_topic_id=group.id,
        script_json=__import__("json").dumps(GROUP_SCRIPT, ensure_ascii=False),
    )
    assert not made.get("isError"), made
    video = db.scalar(select(Video).where(Video.topic == "Rau xanh cho tim"))
    assert [scene.transition for scene in split_scenes(db, video)[1]] == ["circle", "circle"]
