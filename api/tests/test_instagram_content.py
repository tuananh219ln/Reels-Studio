"""An Instagram Reel's numbers: read through its Page's token, kept as readings, and listed on the Page's dashboard."""

from datetime import UTC, datetime, timedelta

import pytest
from conftest import login, make_user, make_video
from fake_services import FACEBOOK_PAGE, FACEBOOK_TOKEN, INSTAGRAM_USER, INSTAGRAM_USERNAME
from sqlalchemy import select
from worker_helpers import add_user, committed  # noqa: F401  (fixtures)

from reels_api import fanpages, instagram, metrics
from reels_api.models import PostMetricSnapshot, Publication

URL = "/api/fanpages"
MEDIA = "17900000000000001"


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


@pytest.fixture
def reel(db, me, storage, fakes):
    """A Reel the app posted to the Page's linked Instagram, live three hours ago."""
    page = fanpages.save(db, FACEBOOK_PAGE, "Trang Dưỡng Sinh", FACEBOOK_TOKEN, me.id)
    page.instagram_user_id, page.instagram_username = INSTAGRAM_USER, INSTAGRAM_USERNAME
    video = make_video(db, storage, me, scene_count=1)
    post = Publication(
        video_id=video.id,
        platform="instagram",
        status="published",
        created_by_id=me.id,
        fanpage_id=page.id,
        external_id=MEDIA,
        post_url="https://www.instagram.com/reel/C1a2B3c4D5e/",
        published_at=datetime.now(UTC) - timedelta(hours=3),
    )
    db.add(post)
    db.commit()
    fakes.instagram_media.append({"id": MEDIA, "permalink": post.post_url})
    return page, post


def test_a_reel_is_read_with_its_page_token_and_kept_as_a_reading(db, reel, fakes):
    _, post = reel
    assert [one.id for one in metrics.due_posts(db, platform="instagram")] == [post.id]
    metrics.measure_instagram(db, post)
    snap = db.scalars(select(PostMetricSnapshot)).one()
    assert (snap.views, snap.likes, snap.comments, snap.shares) == (1000, 60, 5, 9)
    assert snap.raw["source"] == "instagram"
    assert snap.raw["numbers"] == {
        "views": 1000,
        "reach": 800,
        "likes": 60,
        "comments": 5,
        "shares": 9,
        "saves": 12,
        "interactions": 86,
        "avg_watch_ms": 6200,
    }
    assert post.metrics_error is None and post.next_snapshot_at is not None
    assert metrics.due_posts(db, platform="instagram") == [], "read again later, not at once"


def test_a_metric_a_reel_lacks_is_none_and_the_rest_are_read(db, reel, fakes):
    _, post = reel
    fakes.instagram_media_dropped = {"ig_reels_avg_watch_time"}
    metrics.measure_instagram(db, post)
    numbers = db.scalars(select(PostMetricSnapshot)).one().raw["numbers"]
    assert numbers["avg_watch_ms"] is None and numbers["views"] == 1000 and numbers["saves"] == 12


def test_a_reel_every_metric_refuses_is_tried_again_in_an_hour(db, reel, fakes):
    _, post = reel
    fakes.instagram_media_gone = {MEDIA}
    metrics.measure_instagram(db, post)
    assert db.scalars(select(PostMetricSnapshot)).all() == []
    assert post.metrics_error and post.next_snapshot_at > datetime.now(UTC) + timedelta(minutes=50)


def test_a_token_without_instagram_manage_insights_says_so_on_the_post(db, reel, fakes):
    _, post = reel
    fakes.instagram_insights_refused = True
    metrics.measure_instagram(db, post)
    assert post.metrics_error == instagram.NO_INSIGHTS_PERMISSION


def test_the_worker_round_reads_due_reels(committed, storage, fakes):
    with committed() as db:
        user = make_user(db)
        page = fanpages.save(db, FACEBOOK_PAGE, "Trang Dưỡng Sinh", FACEBOOK_TOKEN, user.id)
        page.instagram_user_id = INSTAGRAM_USER
        video = make_video(db, storage, user, scene_count=1)
        db.add(
            Publication(
                video_id=video.id,
                platform="instagram",
                status="published",
                created_by_id=user.id,
                fanpage_id=page.id,
                external_id=MEDIA,
                published_at=datetime.now(UTC) - timedelta(hours=3),
            )
        )
        db.commit()
    fakes.instagram_media.append({"id": MEDIA, "permalink": "https://www.instagram.com/reel/C1a2B3c4D5e/"})
    metrics.measure_due(committed)
    with committed() as db:
        assert db.scalars(select(PostMetricSnapshot)).one().views == 1000
