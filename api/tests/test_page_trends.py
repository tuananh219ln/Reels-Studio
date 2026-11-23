"""What the Page's numbers say beyond a figure: a drop in views, the same video on two platforms, the best hours."""

from datetime import UTC, datetime, timedelta

import pytest
from conftest import login, make_user, make_video
from fake_services import FACEBOOK_PAGE, FACEBOOK_TOKEN, INSTAGRAM_USER
from worker_helpers import add_user, committed  # noqa: F401  (fixtures)

from reels_api import analytics, fanpages, page_dashboard
from reels_api.models import FanpageInsights, InstagramInsights, PostMetrics, PostMetricSnapshot, Publication

URL = "/api/fanpages"


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


@pytest.fixture
def page(db, me, fakes):
    row = fanpages.save(db, FACEBOOK_PAGE, "Trang Dưỡng Sinh", FACEBOOK_TOKEN, me.id)
    row.instagram_user_id = INSTAGRAM_USER
    db.commit()
    return row


def day(n: int):
    """The Vietnam day `n` days ago."""
    return datetime.now(UTC).astimezone(analytics.VIETNAM).date() - timedelta(days=n)


def week(db, model, page, start_ago: int, views: int, days: int = 7):
    for n in range(days):
        db.add(model(fanpage_id=page.id, day=day(start_ago - n), views=views))
    db.commit()


# --- A drop in views


def test_views_that_fell_by_half_against_the_week_before_are_an_alert(an, db, page):
    week(db, FanpageInsights, page, 15, 100)  # the week before: 700 (days 15..9 ago)
    week(db, FanpageInsights, page, 8, 20)  # the last week: 140 (days 8..2 ago)
    (row,) = an.get(URL).json()
    assert row["alerts"] == [{"platform": "facebook", "current": 140, "previous": 700, "change": -0.8}]


def test_a_week_that_only_fell_a_little_is_not_an_alert(an, db, page):
    week(db, FanpageInsights, page, 15, 100)
    week(db, FanpageInsights, page, 8, 60)
    assert an.get(URL).json()[0]["alerts"] == []


def test_too_few_views_before_or_too_few_days_now_are_not_an_alert(an, db, page):
    week(db, FanpageInsights, page, 15, 10)  # 70 views the week before: nothing to compare with
    week(db, FanpageInsights, page, 8, 0)
    assert an.get(URL).json()[0]["alerts"] == []
    week(db, InstagramInsights, page, 15, 100)
    week(db, InstagramInsights, page, 8, 0, days=3)  # only 3 days with a number
    assert an.get(URL).json()[0]["alerts"] == []


def test_each_platform_has_its_own_alert(an, db, page):
    for model in (FanpageInsights, InstagramInsights):
        week(db, model, page, 15, 100)
        week(db, model, page, 8, 10)
    assert [alert["platform"] for alert in an.get(URL).json()[0]["alerts"]] == ["facebook", "instagram"]


# --- The same video on both platforms


def post_both(db, me, storage, page, facebook_views=2000, instagram_views=900):
    video = make_video(db, storage, me, scene_count=1)
    live = datetime.now(UTC) - timedelta(hours=5)
    fb = Publication(
        video_id=video.id,
        platform="facebook",
        status="published",
        created_by_id=me.id,
        fanpage_id=page.id,
        remote_id="fb-reel-1",
        published_at=live,
    )
    ig = Publication(
        video_id=video.id,
        platform="instagram",
        status="published",
        created_by_id=me.id,
        fanpage_id=page.id,
        external_id="ig-media-1",
        post_url="https://www.instagram.com/reel/C1a2B3c4D5e/",
        published_at=live,
    )
    db.add_all([fb, ig])
    db.flush()
    fb.metrics.append(
        PostMetrics(
            window="latest", views=facebook_views, reach=1500, reactions=80, comments=10, shares=20, measured_at=live
        )
    )
    db.add(
        PostMetricSnapshot(
            publication_id=ig.id,
            captured_at=live,
            views=instagram_views,
            likes=60,
            raw={
                "source": "instagram",
                "numbers": {"views": instagram_views, "reach": 700, "interactions": 86, "avg_watch_ms": 6200},
            },
        )
    )
    db.commit()
    return video


def test_one_video_on_both_platforms_is_one_row(an, db, me, storage, page):
    video = post_both(db, me, storage, page)
    (row,) = an.get(f"{URL}/{page.id}/compare").json()["videos"]
    assert row["video"]["id"] == video.id
    assert (row["facebook"]["views"], row["facebook"]["reach"], row["facebook"]["interactions"]) == (2000, 1500, 110)
    assert (row["instagram"]["views"], row["instagram"]["reach"], row["instagram"]["interactions"]) == (900, 700, 86)
    assert row["instagram"]["url"] == "https://www.instagram.com/reel/C1a2B3c4D5e/"


def test_a_video_on_one_platform_has_none_for_the_other(an, db, me, storage, page):
    post_both(db, me, storage, page)
    ig_only = make_video(db, storage, me, scene_count=1)
    db.add(
        Publication(
            video_id=ig_only.id,
            platform="instagram",
            status="published",
            created_by_id=me.id,
            fanpage_id=page.id,
            external_id="ig-media-2",
            published_at=datetime.now(UTC) - timedelta(hours=1),
        )
    )
    db.commit()
    rows = an.get(f"{URL}/{page.id}/compare").json()["videos"]
    assert [row["video"]["id"] for row in rows][0] == ig_only.id, "newest first"
    assert rows[0]["facebook"] is None and rows[0]["instagram"]["views"] is None, "no reading yet"


def test_the_instagram_content_tab_lists_reels_with_their_reading(an, db, me, storage, page):
    post_both(db, me, storage, page)
    (row,) = an.get(f"{URL}/{page.id}/instagram-content?days=7").json()["posts"]
    assert row["numbers"]["views"] == 900 and row["numbers"]["avg_watch_seconds"] == 6.2
    assert row["url"] == "https://www.instagram.com/reel/C1a2B3c4D5e/"


# --- The best hours


def test_too_few_posts_do_not_name_an_hour():
    assert page_dashboard._best_hours([(18, 1000)] * 5) == {"posts": 5, "hours": [], "enough": False}


def test_the_best_hours_are_the_ones_watched_most_and_need_two_posts_each():
    samples = [(18, 1000), (18, 3000), (11, 500), (11, 700), (7, 9000), (21, 100), (21, 300)]
    result = page_dashboard._best_hours(samples)
    assert result["enough"] and result["posts"] == 7
    assert result["hours"] == [
        {"hour": 18, "average_views": 2000, "posts": 2},
        {"hour": 11, "average_views": 600, "posts": 2},
        {"hour": 21, "average_views": 200, "posts": 2},
    ], "hour 7 has one post: it does not count"


def test_the_best_times_endpoint_reads_each_platform_on_its_own(an, db, me, storage, page):
    post_both(db, me, storage, page)
    body = an.get(f"{URL}/{page.id}/best-times").json()
    assert body["facebook"]["posts"] == 1 and body["facebook"]["enough"] is False
    assert body["instagram"]["posts"] == 1
    page.instagram_user_id = None
    db.commit()
    assert an.get(f"{URL}/{page.id}/best-times").json()["instagram"] is None
