"""'Nhân bản y hệt': an exact copy of a (winning) video, named "… (copy)", with its own files and no MP4."""

import pytest
from conftest import login, make_user, make_video
from sqlalchemy import select

from reels_api.models import Job, Scene, SceneLayer, SceneSound, Video
from reels_api.videos import split_scenes

MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + bytes(2000)


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def scenes_of(db, video_id: int) -> list[Scene]:
    return db.scalars(
        select(Scene).where(Scene.video_id == video_id).order_by(Scene.is_title.desc(), Scene.position)
    ).all()


def test_duplicate_copies_the_video_exactly_with_its_own_files(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=2)
    an.post(f"/api/videos/{video.id}/music", files={"file": ("Windy Hill.mp3", MP3, "audio/mpeg")})
    _, scenes = split_scenes(db, video)
    db.add(SceneLayer(scene_id=scenes[0].id, kind="text", text="Ghi chú", position=0))
    db.add(SceneSound(scene_id=scenes[0].id, sound="pop", start=1.5))
    video.mp4_key, video.rendered_signature = f"videos/{video.id}/video-abc.mp4", "sig"
    storage.save_bytes(video.mp4_key, b"mp4")
    db.commit()

    response = an.post(f"/api/videos/{video.id}/duplicate")

    assert response.status_code == 201
    payload = response.json()
    copy = db.get(Video, payload["id"])
    assert copy.id != video.id and copy.created_by_id == me.id
    assert payload["name"] == "5 MÓN GIÚP XƯƠNG CHẮC KHỎE (copy)"
    # The title scene, drawn on the video, is unchanged: only the name in the app says "(copy)".
    assert payload["title"] == "5 MÓN GIÚP XƯƠNG CHẮC KHỎE"
    assert (copy.topic, copy.caption, copy.hashtags, copy.pinned_comment, copy.music_volume) == (
        video.topic,
        video.caption,
        video.hashtags,
        video.pinned_comment,
        video.music_volume,
    )
    # No LLM call, no job: the copy is ready to edit and render.
    assert db.scalars(select(Job).where(Job.video_id == copy.id)).all() == []
    # The MP4 is not copied: the copy is rendered before it is posted.
    assert copy.mp4_key is None and copy.rendered_signature is None

    source_scenes, copied = scenes_of(db, video.id), scenes_of(db, copy.id)
    assert [(s.is_title, s.position, s.text, s.seconds, s.keywords) for s in copied] == [
        (s.is_title, s.position, s.text, s.seconds, s.keywords) for s in source_scenes
    ]
    for source, scene in zip(source_scenes, copied, strict=True):
        assert scene.image_key.startswith(f"videos/{copy.id}/")
        assert storage.path(scene.image_key).read_bytes() == storage.path(source.image_key).read_bytes()
    assert [(layer.kind, layer.text) for layer in copied[1].layers] == [("text", "Ghi chú")]
    assert [(sound.sound, sound.start) for sound in copied[1].sounds] == [("pop", 1.5)]
    assert copy.music_key.startswith(f"videos/{copy.id}/")

    # Deleting the source leaves the copy's files in place.
    assert an.delete(f"/api/videos/{video.id}").status_code == 200
    assert all(storage.path(scene.image_key).is_file() for scene in scenes_of(db, copy.id))
    assert storage.path(copy.music_key).read_bytes() == MP3


def test_a_copy_of_a_copy_is_named_after_its_source(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    first = an.post(f"/api/videos/{video.id}/duplicate").json()
    second = an.post(f"/api/videos/{first['id']}/duplicate").json()
    assert second["name"] == "5 MÓN GIÚP XƯƠNG CHẮC KHỎE (copy) (copy)"


def test_lists_show_the_copy_by_its_name(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    copy_id = an.post(f"/api/videos/{video.id}/duplicate").json()["id"]
    rows = {row["id"]: row for row in an.get("/api/videos").json()}
    assert rows[copy_id]["name"] == "5 MÓN GIÚP XƯƠNG CHẮC KHỎE (copy)"
    assert rows[video.id]["name"] is None


def test_a_video_without_a_script_is_not_duplicated(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    video.has_script = False
    db.commit()
    response = an.post(f"/api/videos/{video.id}/duplicate")
    assert response.status_code == 409 and "chưa có kịch bản" in response.json()["message"]
    assert an.post("/api/videos/999999/duplicate").status_code == 404
