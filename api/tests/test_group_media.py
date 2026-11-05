""" "Đã dùng trong nhóm": the photos and clips other videos of the same topic group use, found and copied into a scene."""

import pytest
from conftest import clip_bytes, login, make_user, make_video, needs_ffmpeg
from sqlalchemy import select

from reels_api.models import KnowledgeTopic, Scene


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def scenes_of(db, video) -> list[Scene]:
    return list(db.scalars(select(Scene).where(Scene.video_id == video.id).order_by(Scene.position)))


def with_keywords(db, scene: Scene, *keywords: str) -> None:
    scene.keywords = list(keywords)
    db.commit()


def test_the_groups_media_is_listed_best_match_first_without_this_video_or_other_groups(an, db, me, storage):
    mine = make_video(db, storage, me, scene_count=1)
    older = make_video(db, storage, me, scene_count=2)
    elsewhere = make_video(db, storage, me, scene_count=1)
    other_group = KnowledgeTopic(name="Làm đẹp")
    db.add(other_group)
    db.flush()
    elsewhere.knowledge_topic_id = other_group.id
    target = scenes_of(db, mine)[1]
    with_keywords(db, target, "cây cải bẹ", "rau")
    _, plain, match = scenes_of(db, older)
    with_keywords(db, match, "cải bẹ xanh")

    listed = an.get(f"/api/scenes/{target.id}/group-media").json()
    ids = [item["scene_id"] for item in listed["items"]]
    assert listed["total"] == 3 and len(ids) == 3, "the older video's title and two scenes; not mine, not elsewhere"
    assert ids[0] == match.id, "two words in common come first"
    first = listed["items"][0]
    assert (first["kind"], first["url"], first["video_id"]) == ("photo", f"/api/scenes/{match.id}/image", older.id)

    typed = an.get(f"/api/scenes/{target.id}/group-media", params={"q": "CAI BE"}).json()["items"]
    assert [item["scene_id"] for item in typed] == [match.id], "accents and case do not matter; every word must match"
    assert plain.id not in [item["scene_id"] for item in typed]


def test_using_a_photo_copies_it_with_its_source_and_leaves_the_original(an, db, me, storage):
    mine, older = make_video(db, storage, me, scene_count=1), make_video(db, storage, me, scene_count=1)
    target, source = scenes_of(db, mine)[1], scenes_of(db, older)[1]
    target.image_key = None
    db.commit()
    response = an.post(f"/api/scenes/{target.id}/reuse", json={"scene_id": source.id})
    assert response.status_code == 200, response.text
    db.expire_all()
    target, source = db.get(Scene, target.id), db.get(Scene, source.id)
    assert target.image_key and target.image_key != source.image_key
    assert storage.path(target.image_key).read_bytes() == storage.path(source.image_key).read_bytes()
    assert target.image_source == source.image_source and not target.image_auto


def test_media_of_another_group_is_not_used(an, db, me, storage):
    mine, elsewhere = make_video(db, storage, me, scene_count=1), make_video(db, storage, me, scene_count=1)
    other_group = KnowledgeTopic(name="Làm đẹp")
    db.add(other_group)
    db.flush()
    elsewhere.knowledge_topic_id = other_group.id
    db.commit()
    response = an.post(
        f"/api/scenes/{scenes_of(db, mine)[1].id}/reuse", json={"scene_id": scenes_of(db, elsewhere)[1].id}
    )
    assert response.status_code == 422 and "cùng nhóm" in response.json()["message"]


@needs_ffmpeg
def test_using_a_clip_copies_it_in_place_of_the_photo(an, db, me, storage, tmp_path):
    mine, older = make_video(db, storage, me, scene_count=1), make_video(db, storage, me, scene_count=1)
    target, source = scenes_of(db, mine)[1].id, scenes_of(db, older)[1].id
    uploaded = an.post(f"/api/scenes/{source}/video", files={"file": ("vuon.mp4", clip_bytes(tmp_path, seconds=3))})
    assert uploaded.status_code == 200, uploaded.text
    listed = an.get(f"/api/scenes/{target}/group-media").json()["items"]
    assert next(item for item in listed if item["scene_id"] == source)["kind"] == "clip"
    assert an.post(f"/api/scenes/{target}/reuse", json={"scene_id": source}).status_code == 200
    db.expire_all()
    copied, original = db.get(Scene, target), db.get(Scene, source)
    assert copied.video_key and copied.video_key != original.video_key and copied.image_key is None
    assert storage.exists(copied.video_key) and storage.exists(original.video_key)
