"""Part 4 of docs/specs/per-user-settings-ownership: what a member made, only they delete. Another member is refused
(403) and the thing stays; the maker still deletes it as before. No exception for anyone."""

import json

import pytest
from conftest import client_for, first_topic, login, make_user, make_video
from sqlalchemy import select
from test_article_posts import add_article, add_product
from test_fanpage_checks import add_page
from test_mcp import call, grant, mcp_client  # noqa: F401 (mcp_client is a fixture)

from reels_api.models import (
    AffiliateProduct,
    Article,
    EditTemplate,
    KnowledgeTopic,
    MediaItem,
    MusicTrack,
    Publication,
    RenderNode,
    Scene,
    TopicPlanItem,
    Video,
    VideoNote,
    VideoReference,
)
from reels_api.videos import split_scenes


@pytest.fixture
def an_user(db):
    return make_user(db)


@pytest.fixture
def binh_user(db):
    return make_user(db, email="binh@doi.vn", name="Trần Bình")


@pytest.fixture
def an(client, an_user):
    login(client)
    return client


@pytest.fixture
def binh(app, binh_user):
    client = client_for(app)
    login(client, email="binh@doi.vn")
    return client


def refused(response) -> None:
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "not_owner"


def test_a_video_and_its_scenes_are_deleted_only_by_their_maker(an, binh, db, an_user, storage):
    video = make_video(db, storage, an_user, scene_count=2)
    _, scenes = split_scenes(db, video)
    refused(binh.delete(f"/api/scenes/{scenes[0].id}"))
    refused(binh.delete(f"/api/videos/{video.id}"))
    assert db.get(Video, video.id) is not None and db.get(Scene, scenes[0].id) is not None
    assert an.delete(f"/api/scenes/{scenes[0].id}").status_code == 200
    assert an.delete(f"/api/videos/{video.id}").status_code == 200


def test_a_video_holding_a_teammates_post_or_note_is_not_deleted(an, binh, db, an_user, binh_user, storage):
    video = make_video(db, storage, an_user, scene_count=1)
    db.add(Publication(video_id=video.id, platform="youtube", created_by_id=binh_user.id))
    db.commit()
    blocked = an.delete(f"/api/videos/{video.id}")
    assert blocked.status_code == 409 and "thành viên khác" in blocked.json()["message"]
    db.execute(Publication.__table__.delete().where(Publication.video_id == video.id))
    db.add(VideoNote(video_id=video.id, at=1, text="sửa cảnh 1", created_by_id=binh_user.id))
    db.commit()
    assert an.delete(f"/api/videos/{video.id}").status_code == 409


def test_a_topic_group_is_deleted_only_by_its_maker_and_never_with_a_teammates_work_in_it(an, binh, db, binh_user):
    made = an.post("/api/knowledge/topics", json={"name": "Nhóm của An"}).json()
    group = next(topic for topic in made["topics"] if topic["name"] == "Nhóm của An")
    assert group["created_by_id"] is not None
    refused(binh.delete(f"/api/knowledge/topics/{group['id']}"))

    # A teammate's idea in its plan stops it, with the reason.
    db.add(
        TopicPlanItem(
            knowledge_topic_id=group["id"], day=None, position=1, topic="Ý của Bình", created_by_id=binh_user.id
        )
    )
    db.commit()
    blocked = an.delete(f"/api/knowledge/topics/{group['id']}")
    assert blocked.status_code == 409 and "thành viên khác" in blocked.json()["message"]
    db.execute(TopicPlanItem.__table__.delete().where(TopicPlanItem.knowledge_topic_id == group["id"]))
    db.commit()
    assert an.delete(f"/api/knowledge/topics/{group['id']}").status_code == 200
    assert db.get(KnowledgeTopic, group["id"]) is None


def test_a_topic_group_with_a_teammates_video_says_so(an, db, an_user, binh_user, storage):
    made = an.post("/api/knowledge/topics", json={"name": "Nhóm có video"}).json()
    group_id = next(topic["id"] for topic in made["topics"] if topic["name"] == "Nhóm có video")
    video = make_video(db, storage, binh_user, scene_count=1)
    video.knowledge_topic_id = group_id
    db.commit()
    blocked = an.delete(f"/api/knowledge/topics/{group_id}")
    assert blocked.status_code == 409 and "1 video của thành viên khác" in blocked.json()["message"]


def test_a_plan_idea_is_deleted_only_by_whoever_added_it(an, binh, db):
    group = first_topic(db)
    saved = an.post(
        f"/api/plans/{group.id}/items",
        json={"day": None, "topic": "Ngâm chân", "pain_group": "", "pain": "", "hook": ""},
    )
    assert saved.status_code == 201, saved.text
    item = db.scalar(select(TopicPlanItem).where(TopicPlanItem.topic == "Ngâm chân"))
    refused(binh.delete(f"/api/plans/items/{item.id}"))
    assert an.delete(f"/api/plans/items/{item.id}").status_code == 200


def test_replacing_a_plan_never_deletes_a_teammates_ideas(an, binh, db, binh_user):
    group = first_topic(db)
    db.add(
        TopicPlanItem(knowledge_topic_id=group.id, day=1, position=1, topic="Ý của Bình", created_by_id=binh_user.id)
    )
    db.commit()
    ideas = [{"day": 1, "topic": "Ý mới", "pain_group": "", "pain": "", "hook": ""}]
    blocked = an.put(f"/api/plans/{group.id}/items", json={"ideas": ideas})
    assert blocked.status_code == 409 and "thành viên khác" in blocked.json()["message"]
    assert binh.put(f"/api/plans/{group.id}/items", json={"ideas": ideas}).status_code == 200


@pytest.mark.parametrize("kind", ["template", "product", "media", "music", "article", "reference", "node"])
def test_the_teams_shared_things_are_deleted_only_by_whoever_added_them(an, binh, db, an_user, kind):
    if kind == "template":
        row = EditTemplate(name="Mẫu An", data={"transitions": ["circle"]}, created_by_id=an_user.id)
        url = "/api/edit-templates/{}"
    elif kind == "product":
        row = add_product(db, an_user)
        url = "/api/affiliate-products/{}"
    elif kind == "media":
        row = MediaItem(kind="photo", storage_key="media/x.png", name="x.png", created_by_id=an_user.id)
        url = "/api/media/{}"
    elif kind == "music":
        row = MusicTrack(name="Bài An", mood="piano", storage_key="music/x.mp3", created_by_id=an_user.id)
        url = "/api/music/{}"
    elif kind == "article":
        row = add_article(db, an_user)
        url = "/api/articles/{}"
    elif kind == "reference":
        row = VideoReference(source_name="mau.mp4", created_by_id=an_user.id)
        url = "/api/references/{}"
    else:
        row = RenderNode(name="Máy An", token_hash="x" * 64, created_by_id=an_user.id)
        url = "/api/render-nodes/{}"
    db.add(row)
    db.commit()
    refused(binh.delete(url.format(row.id)))
    assert db.get(type(row), row.id) is not None
    assert an.delete(url.format(row.id)).status_code == 200, kind


def test_a_note_is_deleted_only_by_whoever_wrote_it(an, binh, db, an_user, storage):
    video = make_video(db, storage, an_user, scene_count=1)
    note = binh.post("/api/notes", json={"video_id": video.id, "at": 1, "text": "đổi ảnh"}).json()["notes"][0]
    refused(an.delete(f"/api/notes/{note['id']}"))
    assert binh.delete(f"/api/notes/{note['id']}").status_code == 200


def test_a_page_is_stopped_and_removed_only_by_its_owner(an, binh, db, an_user, fakes):
    page = add_page(db, an_user)
    refused(binh.patch(f"/api/fanpages/{page.id}", json={"active": False}))
    assert an.patch(f"/api/fanpages/{page.id}", json={"active": False}).status_code == 200
    refused(binh.delete(f"/api/fanpages/{page.id}"))
    assert an.delete(f"/api/fanpages/{page.id}").status_code == 200


def test_a_post_is_taken_down_only_by_whoever_posted_it(an, binh, db, an_user, storage):
    video = make_video(db, storage, an_user, scene_count=1)
    post = Publication(video_id=video.id, platform="facebook", created_by_id=an_user.id, status="pending")
    db.add(post)
    db.commit()
    refused(binh.post(f"/api/posts/{post.id}/take-down"))
    assert an.post(f"/api/posts/{post.id}/take-down").status_code == 200


def test_an_article_post_is_taken_down_only_by_whoever_posted_it(an, binh, db, an_user):
    article = add_article(db, an_user)
    post = Publication(article_id=article.id, platform="facebook", created_by_id=an_user.id, status="pending")
    db.add(post)
    db.commit()
    refused(binh.post(f"/api/articles/posts/{post.id}/take-down"))
    assert an.post(f"/api/articles/posts/{post.id}/take-down").status_code == 200


def test_mcp_deletes_only_on_the_connected_members_own_videos(mcp_client, db, storage):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    other = make_user(db, email="binh@doi.vn", name="Trần Bình")
    theirs = make_video(db, storage, other, scene_count=2)
    mine = make_video(db, storage, user, scene_count=2)
    their_scene = split_scenes(db, theirs)[1][0]
    my_scene = split_scenes(db, mine)[1][0]
    answer = call(mcp_client, tokens["access_token"], "delete_scene", scene_id=their_scene.id)
    assert answer.get("isError"), answer
    assert "người tạo" in json.dumps(answer, ensure_ascii=False)
    assert db.get(Scene, their_scene.id) is not None
    assert not call(mcp_client, tokens["access_token"], "delete_scene", scene_id=my_scene.id).get("isError")


def test_payloads_say_who_made_each_thing(an, db, an_user, storage):
    video = make_video(db, storage, an_user, scene_count=1)
    assert an.get(f"/api/videos/{video.id}").json()["created_by_id"] == an_user.id
    product = add_product(db, an_user)
    listed = an.get("/api/affiliate-products").json()
    rows = listed if isinstance(listed, list) else listed.get("products", [])
    assert next(row for row in rows if row["id"] == product.id)["created_by_id"] == an_user.id
    db.add(EditTemplate(name="Mẫu An", data={"transitions": ["circle"]}, created_by_id=an_user.id))
    db.commit()
    templates = an.get("/api/edit-templates").json()["templates"]
    assert next(row for row in templates if row["name"] == "Mẫu An")["created_by_id"] == an_user.id
    assert all("created_by_id" in row for row in an.get("/api/knowledge").json()["topics"])
    assert AffiliateProduct and Article  # imported for the parametrized test
