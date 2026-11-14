"""The schedule of a post's readings, its marks, YouTube's numbers and "Cập nhật view" ("Bài đăng" part 2: metrics.py,
youtube.py, routes_posts.refresh_views)."""

from datetime import UTC, datetime, timedelta

import pytest
from conftest import login, make_user, make_video
from fake_services import FACEBOOK_PAGE, FACEBOOK_TOKEN
from sqlalchemy import select

from reels_api import fanpages, metrics
from reels_api.models import Channel, PostMetricSnapshot, Publication

LIVE = datetime(2026, 11, 1, 3, 0, tzinfo=UTC)


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def hours_ago(hours: float) -> datetime:
    return datetime.now(UTC) - timedelta(hours=hours)


def at_hours(hours: float) -> float | None:
    following = metrics.next_reading(LIVE, LIVE + timedelta(hours=hours))
    return None if following is None else (following - LIVE).total_seconds() / 3600


# --- The schedule (pure) ---


@pytest.mark.parametrize(
    ("age", "next_age"),
    [
        (0, 1),  # the 1-hour mark
        (0.5, 1),
        (1, 2),  # hourly in the first 48 hours
        (23.5, 24),  # the 24-hour mark on the dot
        (47.2, 48),
        (48, 54),  # every 6 hours to 7 days
        (167, 168),  # the 7-day mark
        (168, 192),  # daily to 30 days
        (719.5, 720),
        (720, 888),  # weekly
        (90 * 24, None),  # never after 90 days
    ],
)
def test_the_schedule_follows_the_post_s_age_and_its_marks(age, next_age):
    assert at_hours(age) == pytest.approx(next_age) if next_age is not None else at_hours(age) is None


def test_a_trending_post_is_read_every_15_minutes_in_its_first_48_hours():
    at = LIVE + timedelta(hours=3)
    assert metrics.next_reading(LIVE, at, trending=True) == at + timedelta(minutes=15)
    assert metrics.is_trending(LIVE, at, 100, 150), "up 50 %"
    assert metrics.is_trending(LIVE, at, 10_000, 12_000), "up 2.000 views"
    assert not metrics.is_trending(LIVE, at, 10_000, 11_000)
    assert not metrics.is_trending(LIVE, LIVE + timedelta(hours=50), 1, 9_000), "past 48 hours"
    assert not metrics.is_trending(LIVE, at, None, 9_000), "no reading before"


# --- Facebook readings ---


@pytest.fixture
def fb(db, storage, me):
    """A Facebook reel live `hours` ago."""

    def make(hours: float, remote_id: str = "1000") -> Publication:
        page = db.scalar(select(fanpages.Fanpage).where(fanpages.Fanpage.page_id == FACEBOOK_PAGE))
        if page is None:
            page = fanpages.save(db, FACEBOOK_PAGE, "Trang Dưỡng Sinh", FACEBOOK_TOKEN, me.id)
            db.flush()
        video = make_video(db, storage, me, scene_count=1)
        post = Publication(
            video_id=video.id,
            platform="facebook",
            created_by_id=me.id,
            fanpage_id=page.id,
            remote_id=remote_id,
            status="published",
            published_at=hours_ago(hours),
        )
        db.add(post)
        db.commit()
        return post

    return make


def add_snapshot(db, post, hours: float, views: int):
    db.add(
        PostMetricSnapshot(
            publication_id=post.id,
            captured_at=post.published_at + timedelta(hours=hours),
            hours_since_publish=hours,
            views=views,
        )
    )
    db.commit()


def test_a_reading_on_the_mark_sets_it_once(db, fb, fakes):
    post = fb(24.5)
    fakes.facebook_insights["1000"] = {"views": 5000, "shares": 1, "comments": 1, "reactions": 1}
    metrics.measure(db, post)
    assert post.views_24h == 5000 and post.views_1h is None, "no reading near the first hour"
    assert post.marks_estimated == []
    fakes.facebook_insights["1000"] = {"views": 9000, "shares": 1, "comments": 1, "reactions": 1}
    metrics.measure(db, post)
    assert post.views_24h == 5000, "a mark once set is never taken again"


def test_a_mark_missed_is_taken_between_the_readings_around_it(db, fb, fakes):
    post = fb(30)
    add_snapshot(db, post, 20, 1000)
    add_snapshot(db, post, 28, 1800)
    fakes.facebook_insights["1000"] = {"views": 2000, "shares": 1, "comments": 1, "reactions": 1}
    metrics.measure(db, post)
    assert post.views_24h == 1400 and post.marks_estimated == ["24h"]


def test_a_mark_with_no_reading_on_one_side_stays_empty(db, fb, fakes):
    post = fb(30)
    fakes.facebook_insights["1000"] = {"views": 2000, "shares": 1, "comments": 1, "reactions": 1}
    metrics.measure(db, post)
    assert post.views_24h is None and post.views_1h is None


def test_a_post_up_by_half_is_read_again_in_15_minutes(db, fb, fakes):
    post = fb(5)
    add_snapshot(db, post, 4, 1000)
    fakes.facebook_insights["1000"] = {"views": 1600, "shares": 1, "comments": 1, "reactions": 1}
    metrics.measure(db, post)
    assert post.next_snapshot_at - post.metrics_tried_at == timedelta(minutes=15)


def test_a_failed_reading_is_tried_again_in_an_hour_and_never_removes_the_reel(db, fb, fakes):
    post = fb(5)
    fakes.facebook_insights_gone.add("1000")
    metrics.measure(db, post)
    assert post.next_snapshot_at - post.metrics_tried_at == timedelta(hours=1)
    assert post.status == "published", "only a check says a reel is gone (2026-11-13)"


# --- YouTube ---


def youtube_post(db, storage, user, external_id="dQw4w9WgXcQ", **extra) -> Publication:
    channel = db.scalar(select(Channel)) or Channel(
        platform="youtube",
        handle="@anngon",
        name="Ăn Ngon",
        url="https://www.youtube.com/@anngon",
        created_by_id=user.id,
    )
    db.add(channel)
    db.flush()
    video = make_video(db, storage, user, scene_count=1)
    post = Publication(
        video_id=video.id,
        platform="youtube",
        source="manual_link",
        external_id=external_id,
        post_url=f"https://www.youtube.com/shorts/{external_id}",
        channel_id=channel.id,
        created_by_id=user.id,
        **({"status": "published", "published_at": hours_ago(2)} | extra),
    )
    db.add(post)
    db.commit()
    return post


def test_youtube_shorts_are_read_in_one_call_with_their_time(db, me, storage, fakes):
    first = youtube_post(db, storage, me)
    second = youtube_post(db, storage, me, external_id="abcdefghijk", published_at_source="user")
    fakes.youtube_videos["dQw4w9WgXcQ"] = {"views": 4321, "published_at": "2026-11-14T01:00:00Z"}
    due = metrics.due_posts(db, 50, "youtube")
    assert {post.id for post in due} == {first.id, second.id}
    metrics.measure_youtube(db, due)
    assert len(fakes.youtube_calls) == 1
    snapshot = db.scalar(select(PostMetricSnapshot).where(PostMetricSnapshot.publication_id == first.id))
    assert (snapshot.views, snapshot.likes, snapshot.comments, snapshot.shares) == (4321, 12, 3, None)
    assert first.published_at == datetime(2026, 11, 14, 1, tzinfo=UTC) and first.published_at_source == "api"
    assert second.published_at_source == "user", "a time the member typed is kept"
    assert first.next_snapshot_at is not None


def test_a_short_missing_twice_an_hour_apart_is_removed_and_comes_back(db, me, storage, fakes):
    post = youtube_post(db, storage, me)
    fakes.youtube_gone.add("dQw4w9WgXcQ")
    metrics.measure_youtube(db, [post])
    assert post.status == "published" and post.gone_since is not None
    assert post.next_snapshot_at - post.metrics_tried_at == timedelta(hours=1)
    post.gone_since = hours_ago(1.1)
    db.commit()
    metrics.measure_youtube(db, [post])
    assert post.status == "deleted" and post.closed_by_id is None
    assert "YouTube không còn" in post.metrics_error
    assert post.next_snapshot_at - post.metrics_tried_at == timedelta(hours=24), "looked at daily for a week"
    fakes.youtube_gone.clear()
    metrics.measure_youtube(db, [post])
    assert post.status == "published" and post.closed_at is None and post.gone_since is None


def test_youtube_out_of_quota_changes_nothing_and_waits_an_hour(db, me, storage, fakes):
    post = youtube_post(db, storage, me)
    fakes.youtube_error = 403
    metrics.measure_youtube(db, [post])
    assert post.status == "published" and post.gone_since is None
    assert "quota" in post.metrics_error
    assert post.next_snapshot_at - post.metrics_tried_at == timedelta(hours=1)


def test_tiktok_posts_are_not_read_yet(db, me, storage, fakes):
    video = make_video(db, storage, me, scene_count=1)
    db.add(
        Publication(
            video_id=video.id,
            platform="tiktok",
            external_id="7301234567890123456",
            status="published",
            published_at=hours_ago(2),
            created_by_id=me.id,
        )
    )
    db.commit()
    assert metrics.due_posts(db, 50, "tiktok") == []


# --- "Cập nhật view" and the opened row ---


def test_refresh_asks_the_shown_videos_posts_once_per_five_minutes(an, db, me, storage, fakes):
    post = youtube_post(db, storage, me, metrics_tried_at=hours_ago(1))
    result = an.post("/api/posts/metrics/refresh", json={"video_ids": [post.video_id]})
    assert result.json() == {"asked": 1}
    db.refresh(post)
    assert post.metrics_requested_at is not None
    board = an.get("/api/posts/board").json()
    assert board["items"][0]["cells"]["youtube"]["refreshing"] is True
    again = an.post("/api/posts/metrics/refresh", json={"video_ids": [post.video_id]})
    assert again.status_code == 429 and "thử lại sau 5 phút" in again.json()["message"]


def test_the_opened_row_shows_the_marks_missed_estimated_and_the_trend(an, db, me, storage, fakes):
    post = youtube_post(db, storage, me, published_at=hours_ago(30), views_24h=1400, marks_estimated=["24h"])
    for hours, views in ((1, 10), (10, 500), (29, 1900)):
        add_snapshot(db, post, hours, views)
    row = an.get(f"/api/posts/videos/{post.video_id}").json()["posts"][0]
    assert (row["views_24h"], row["marks_estimated"], row["marks_missed"]) == (1400, ["24h"], [])
    assert row["sparkline"] == [10, 500, 1900]
    post.published_at = hours_ago(60)
    db.commit()
    row = an.get(f"/api/posts/videos/{post.video_id}").json()["posts"][0]
    assert row["marks_missed"] == ["48h"], "past 48 hours and its tolerance with no value: n/a"


def test_a_typed_time_moves_the_readings_ages(an, db, me, storage, fakes):
    post = youtube_post(db, storage, me)
    add_snapshot(db, post, 2, 100)
    later = post.published_at + timedelta(hours=1)
    assert an.patch(f"/api/posts/{post.id}", json={"published_at": later.isoformat()}).status_code == 200
    snapshot = db.scalar(select(PostMetricSnapshot).where(PostMetricSnapshot.publication_id == post.id))
    db.refresh(snapshot)
    assert float(snapshot.hours_since_publish) == pytest.approx(1.0)
