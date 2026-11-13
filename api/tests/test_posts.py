from datetime import UTC, datetime, timedelta

import pytest
from conftest import login, make_user, make_video
from fake_services import FACEBOOK_PAGE, FACEBOOK_TOKEN

from reels_api import fanpages
from reels_api.models import Job, Publication, Video
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


def add_publish_job(db, post, user, status, error=None) -> Job:
    job = Job(video_id=post.video_id, kind="publish", status=status, created_by_id=user.id, error=error)
    db.add(job)
    db.commit()
    return job


def test_a_post_on_its_way_to_facebook_is_listed_as_being_posted(an, db, me, storage):
    post = add_post(db, storage, me, status="pending")
    add_publish_job(db, post, me, "running")
    (row,) = an.get("/api/posts").json()
    assert (row["status"], row["url"]) == ("pending", None)
    assert row["attempt"] == {"state": "working", "job_id": None, "error": None}


def test_a_post_names_the_topic_group_of_its_video(an, db, me, storage):
    post = add_post(db, storage, me, status="pending")
    (row,) = an.get("/api/posts").json()
    assert row["knowledge_topic_id"] == db.get(Video, post.video_id).knowledge_topic_id is not None


def test_cập_nhật_view_asks_for_the_numbers_of_the_posts_of_one_group_only(an, db, me, storage):
    from reels_api.models import KnowledgeTopic

    mine = add_post(db, storage, me, status="published", remote_id="1", published_at=in_hours(-5))
    other_group = KnowledgeTopic(name="Nhóm khác", created_by_id=me.id)
    db.add(other_group)
    db.commit()
    other = add_post(db, storage, me, status="published", remote_id="2", published_at=in_hours(-5))
    db.get(Video, other.video_id).knowledge_topic_id = other_group.id
    unposted = add_post(db, storage, me, status="pending")
    db.commit()
    topic_id = db.get(Video, mine.video_id).knowledge_topic_id
    assert an.post(f"/api/posts/refresh?knowledge_topic_id={topic_id}").json() == {"asked": 1}
    db.refresh(mine)
    db.refresh(other)
    db.refresh(unposted)
    assert mine.metrics_requested_at is not None
    assert other.metrics_requested_at is None and unposted.metrics_requested_at is None
    # Asked again before the worker read it: nothing new to ask for.
    assert an.post(f"/api/posts/refresh?knowledge_topic_id={topic_id}").json() == {"asked": 0}


def test_a_post_whose_publish_failed_gives_the_reason_and_the_job_to_retry(an, db, me, storage):
    post = add_post(db, storage, me, status="pending", remote_id="1000")
    add_publish_job(db, post, me, "failed", "Token cũ")
    job = add_publish_job(db, post, me, "failed", "Facebook đang lỗi (HTTP 500), thử lại sau")
    (row,) = an.get("/api/posts").json()
    assert row["attempt"] == {"state": "failed", "job_id": job.id, "error": "Facebook đang lỗi (HTTP 500), thử lại sau"}


def test_a_retry_on_its_way_replaces_the_failure(an, db, me, storage):
    post = add_post(db, storage, me, status="pending")
    add_publish_job(db, post, me, "failed", "Token cũ")
    add_publish_job(db, post, me, "queued")
    (row,) = an.get("/api/posts").json()
    assert row["attempt"]["state"] == "working"


def test_a_post_on_facebook_has_no_attempt(an, db, me, storage):
    post = add_post(db, storage, me, status="published", remote_id="1000", published_at=in_hours(-1))
    add_publish_job(db, post, me, "failed", "Token cũ")
    (row,) = an.get("/api/posts").json()
    assert row["attempt"] is None


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
