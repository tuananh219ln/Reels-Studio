from datetime import UTC, datetime, timedelta

import pytest
from conftest import login, make_user, make_video
from fake_services import FACEBOOK_PAGE, FACEBOOK_TOKEN

from reels_api import fanpages
from reels_api.models import Publication, Video
from reels_api.videos import render_signature, split_scenes


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def add_post(db, storage, user, **fields) -> Publication:
    video = make_video(db, storage, user, scene_count=1)
    post = Publication(video_id=video.id, platform="facebook", created_by_id=user.id, **fields)
    db.add(post)
    db.commit()
    return post


def in_hours(hours: float) -> datetime:
    return datetime.now(UTC).replace(microsecond=0) + timedelta(hours=hours)


def test_the_list_needs_a_login(client):
    assert client.get("/api/posts").status_code == 401


def test_a_post_not_on_facebook_yet_is_left_out(an, db, me, storage):
    add_post(db, storage, me, status="pending", remote_id="1000")
    assert an.get("/api/posts").json() == []


def test_a_post_shows_its_video_fanpage_and_who_posted_it(an, db, me, storage):
    page = fanpages.save(db, FACEBOOK_PAGE, "Trang Dưỡng Sinh", FACEBOOK_TOKEN, me.id)
    db.flush()
    when = in_hours(-1)
    post = add_post(db, storage, me, status="published", remote_id="1000", published_at=when, fanpage_id=page.id)
    (row,) = an.get("/api/posts").json()
    assert (row["video_id"], row["status"], row["fanpage"], row["created_by"]) == (
        post.video_id,
        "published",
        "Trang Dưỡng Sinh",
        "Nguyễn Văn An",
    )
    assert row["url"] == "https://www.facebook.com/reel/1000"
    assert datetime.fromisoformat(row["at"]) == when


def test_a_post_waiting_for_its_time_has_that_time_and_no_link(an, db, me, storage):
    when = in_hours(5)
    add_post(db, storage, me, status="scheduled", remote_id="1000", scheduled_at=when, published_at=in_hours(0))
    (row,) = an.get("/api/posts").json()
    assert (row["status"], row["url"]) == ("scheduled", None)
    assert datetime.fromisoformat(row["at"]) == when


def test_a_scheduled_post_counts_as_published_once_its_time_has_passed(an, db, me, storage):
    when = in_hours(-1)
    add_post(db, storage, me, status="scheduled", remote_id="1000", scheduled_at=when, published_at=in_hours(-5))
    (row,) = an.get("/api/posts").json()
    assert (row["status"], row["url"]) == ("published", "https://www.facebook.com/reel/1000")
    assert datetime.fromisoformat(row["at"]) == when


def test_the_poster_is_who_sent_it_last_after_a_failed_attempt(an, db, me, storage):
    other = make_user(db, email="binh@doi.vn", name="Trần Bình")
    video = make_video(db, storage, me, scene_count=1)
    title, scenes = split_scenes(db, video)
    video.mp4_key = f"videos/{video.id}/video-x.mp4"
    storage.save_bytes(video.mp4_key, b"mp4 bytes")
    video.rendered_signature = render_signature(video, title, scenes)
    post = Publication(video_id=video.id, platform="facebook", created_by_id=other.id)
    db.add(post)
    page = fanpages.save(db, FACEBOOK_PAGE, "Trang Dưỡng Sinh", FACEBOOK_TOKEN, me.id)
    db.commit()
    assert an.post(f"/api/videos/{video.id}/publish", json={"fanpage_id": page.id}).status_code == 200
    assert post.created_by_id == me.id


def test_the_latest_time_comes_first(an, db, me, storage):
    old = add_post(db, storage, me, status="published", remote_id="1", published_at=in_hours(-5))
    waiting = add_post(
        db, storage, me, status="scheduled", remote_id="2", scheduled_at=in_hours(5), published_at=in_hours(-9)
    )
    new = add_post(db, storage, me, status="published", remote_id="3", published_at=in_hours(-1))
    assert [row["video_id"] for row in an.get("/api/posts").json()] == [waiting.video_id, new.video_id, old.video_id]


def test_a_post_shows_its_videos_thumbnail(an, db, me, storage):
    with_frame = add_post(db, storage, me, status="published", remote_id="1000", published_at=in_hours(-2))
    db.get(Video, with_frame.video_id).thumbnail_key = "videos/1/thumbnail.jpg"
    add_post(db, storage, me, status="published", remote_id="1001", published_at=in_hours(-3))
    db.commit()
    first, second = an.get("/api/posts").json()
    assert first["thumbnail_url"].startswith(f"/api/videos/{with_frame.video_id}/thumbnail.jpg?v=")
    assert second["thumbnail_url"] is None
