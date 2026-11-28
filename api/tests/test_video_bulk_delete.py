"""Delete many videos at once (docs/decisions/2026-11-28-bulk-delete-videos.md)."""

import pytest
from conftest import client_for, login, make_user, make_video

from reels_api.models import Job, Publication, Video


@pytest.fixture
def an_user(db):
    return make_user(db)


@pytest.fixture
def an(client, an_user):
    login(client)
    return client


@pytest.fixture
def binh_user(db):
    return make_user(db, email="binh@doi.vn", name="Trần Bình")


def reasons(answer) -> dict[int, str]:
    return {item["id"]: item["reason"] for item in answer["skipped"]}


def test_many_videos_are_deleted_at_once(an, db, an_user, storage):
    videos = [make_video(db, storage, an_user, scene_count=1) for _ in range(3)]
    ids = [video.id for video in videos]

    answer = an.post("/api/video-bulk/delete", json={"ids": ids})

    assert answer.status_code == 200
    assert answer.json()["deleted"] == 3 and answer.json()["skipped"] == []
    db.expire_all()
    assert db.query(Video).filter(Video.id.in_(ids)).count() == 0


def test_a_posted_a_running_and_a_teammates_video_are_skipped_not_deleted(an, db, an_user, binh_user, storage):
    plain = make_video(db, storage, an_user, scene_count=1)
    posted = make_video(db, storage, an_user, scene_count=1)
    running = make_video(db, storage, an_user, scene_count=1)
    theirs = make_video(db, storage, binh_user, scene_count=1)
    held = make_video(db, storage, an_user, scene_count=1)
    db.add(Publication(video_id=posted.id, platform="facebook", status="published", created_by_id=an_user.id))
    db.add(Job(video_id=running.id, kind="render", status="running", created_by_id=an_user.id))
    db.add(Publication(video_id=held.id, platform="youtube", status="scheduled", created_by_id=binh_user.id))
    db.commit()
    ids = [plain.id, posted.id, running.id, theirs.id, held.id]

    answer = an.post("/api/video-bulk/delete", json={"ids": ids}).json()

    assert answer["deleted"] == 1
    assert reasons(answer) == {
        posted.id: "published",
        running.id: "rendering",
        theirs.id: "forbidden",
        held.id: "forbidden",
    }
    db.expire_all()
    assert {video.id for video in db.query(Video).filter(Video.id.in_(ids))} == {
        posted.id,
        running.id,
        theirs.id,
        held.id,
    }


def test_the_preview_counts_what_would_go_and_what_would_not(an, db, an_user, storage):
    plain = make_video(db, storage, an_user, scene_count=1)
    scheduled = make_video(db, storage, an_user, scene_count=1)
    posted = make_video(db, storage, an_user, scene_count=1)
    db.add(Publication(video_id=scheduled.id, platform="facebook", status="scheduled", created_by_id=an_user.id))
    db.add(Publication(video_id=posted.id, platform="facebook", status="published", created_by_id=an_user.id))
    db.commit()

    answer = an.post("/api/video-bulk/delete/preview", json={"ids": [plain.id, scheduled.id, posted.id]}).json()

    assert answer == {"count": 2, "scheduled": 1, "published": 1, "rendering": 0, "forbidden": 0}
    db.expire_all()
    assert db.query(Video).count() == 3


def test_ids_are_required_and_at_most_500(an):
    assert an.post("/api/video-bulk/delete", json={"ids": []}).status_code == 422
    assert an.post("/api/video-bulk/delete", json={"ids": list(range(1, 502))}).status_code == 422


def test_signing_in_is_required(app):
    assert client_for(app).post("/api/video-bulk/delete", json={"ids": [1]}).status_code == 401
