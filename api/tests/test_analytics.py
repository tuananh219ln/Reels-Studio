"""The median views, how far a post is from it and the weekly KPIs (analytics.py), from the posts' 48-hour numbers.

There is no "Video thắng" flag: it was dropped on 2026-11-03 (docs/decisions.md)."""

from datetime import UTC, datetime, timedelta

import pytest
from conftest import login, make_user, make_video

from reels_api import analytics, fanpages
from reels_api.models import PostMetrics, Publication

# A Wednesday, 10:00 in Vietnam.
NOW = datetime(2026, 11, 4, 3, 0, tzinfo=UTC)


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


@pytest.fixture
def frozen(monkeypatch):
    monkeypatch.setattr(analytics, "now", lambda: NOW)
    return NOW


def page(db, user, page_id: str = "1234567") -> int:
    row = fanpages.save(db, page_id, f"Trang {page_id}", "token", user.id)
    db.flush()
    return row.id


def marked(db, storage, user, fanpage: int, views: int | None, shares: int | None = 0, live=None) -> Publication:
    """A published post with its 48-hour numbers."""
    video = make_video(db, storage, user, scene_count=1)
    live = live or NOW - timedelta(days=3)
    post = Publication(
        video_id=video.id,
        platform="facebook",
        created_by_id=user.id,
        fanpage_id=fanpage,
        remote_id=str(video.id),
        status="published",
        published_at=live,
    )
    db.add(post)
    db.flush()
    db.add(PostMetrics(publication_id=post.id, window="48h", views=views, shares=shares, measured_at=live))
    db.add(PostMetrics(publication_id=post.id, window="latest", views=views, shares=shares, measured_at=live))
    db.commit()
    db.refresh(post)
    return post


def analysis_of(an, post: Publication) -> dict:
    rows = {row["id"]: row for row in an.get("/api/posts").json()}
    return rows[post.id]["metrics"]["analysis"]


def test_a_post_is_measured_against_its_pages_median(an, db, me, storage, frozen):
    fanpage = page(db, me)
    for views in (900, 1000, 1000, 1100):
        marked(db, storage, me, fanpage, views)
    high = marked(db, storage, me, fanpage, 12000)
    usual = marked(db, storage, me, fanpage, 1000)
    assert analytics.medians(db)[fanpage] == analytics.Median(1000, 6)
    assert analysis_of(an, high) | {"share_rate": None} == {
        "median_views": 1000,
        "samples": 6,
        "times_median": 12.0,
        "share_rate": None,
    }
    assert analysis_of(an, usual)["times_median"] == 1.0


def test_under_five_measured_posts_nothing_is_compared(an, db, me, storage, frozen):
    fanpage = page(db, me)
    for views in (100, 100, 100):
        marked(db, storage, me, fanpage, views)
    huge = marked(db, storage, me, fanpage, 1_000_000)
    analysis = analysis_of(an, huge)
    assert (analysis["samples"], analysis["times_median"]) == (4, None)
    assert an.get("/api/posts/kpis").json()["enough_data"] is False


def test_each_page_is_compared_with_its_own_median(an, db, me, storage, frozen):
    big, small = page(db, me, "111"), page(db, me, "222")
    for _ in range(5):
        marked(db, storage, me, big, 100_000)
        marked(db, storage, me, small, 1_000)
    star = marked(db, storage, me, small, 20_000)
    assert analysis_of(an, star)["times_median"] == 20.0, "20× its small Page, though under the big Page's usual"
    assert analytics.medians(db)[big].views == 100_000


def test_the_median_counts_only_the_last_sixty_days(db, me, storage, frozen):
    fanpage = page(db, me)
    for _ in range(5):
        marked(db, storage, me, fanpage, 50, live=NOW - timedelta(days=70))
    for _ in range(5):
        marked(db, storage, me, fanpage, 5000)
    assert analytics.medians(db)[fanpage] == analytics.Median(5000, 5)


def test_a_post_without_views_at_48_hours_is_left_out(db, me, storage, frozen):
    fanpage = page(db, me)
    marked(db, storage, me, fanpage, None)
    for _ in range(5):
        marked(db, storage, me, fanpage, 10)
    assert analytics.medians(db)[fanpage].samples == 5


@pytest.mark.parametrize("status", ["deleted", "cancelled"])
def test_a_post_taken_down_leaves_its_pages_median(an, db, me, storage, frozen, status):
    # Four reels Facebook hid from viewers (about 1 view at 48 hours) were deleted: their numbers measure the fault,
    # not the content, so they must not drag the Page's median down. Their own 48-hour numbers stay as history.
    fanpage = page(db, me)
    gone = [marked(db, storage, me, fanpage, 1) for _ in range(4)]
    for post in gone:
        post.status = status
    for views in (900, 1000, 1000, 1100, 1200):
        marked(db, storage, me, fanpage, views)
    db.commit()
    assert analytics.medians(db)[fanpage] == analytics.Median(1000, 5)
    row = {row["id"]: row for row in an.get("/api/posts").json()}[gone[0].id]
    assert row["metrics"]["at_48h"]["views"] == 1


def test_a_post_taken_down_leaves_the_weekly_kpis(an, db, me, storage, frozen):
    fanpage = page(db, me)
    monday = datetime(2026, 11, 1, 17, 30, tzinfo=UTC)  # this week
    for _ in range(3):
        marked(db, storage, me, fanpage, 1, live=monday).status = "deleted"
    marked(db, storage, me, fanpage, 1000, shares=3, live=monday)
    db.commit()
    week = an.get("/api/posts/kpis").json()["this_week"]
    assert (week["measured"], week["median_views"], week["share_goal_met"]) == (1, 1000, 1)


def test_a_post_not_measured_at_48_hours_yet_shows_its_pages_median_only(an, db, me, storage, frozen):
    fanpage = page(db, me)
    for _ in range(5):
        marked(db, storage, me, fanpage, 300)
    video = make_video(db, storage, me, scene_count=1)
    fresh = Publication(
        video_id=video.id,
        platform="facebook",
        created_by_id=me.id,
        fanpage_id=fanpage,
        remote_id="77",
        status="published",
        published_at=NOW - timedelta(hours=5),
    )
    db.add(fresh)
    db.commit()
    assert analysis_of(an, fresh) == {
        "median_views": 300,
        "samples": 5,
        "times_median": None,
        "share_rate": None,
    }


def test_share_rate_is_shares_over_views_at_48_hours(an, db, me, storage, frozen):
    fanpage = page(db, me)
    post = marked(db, storage, me, fanpage, 2000, shares=5)
    assert analysis_of(an, post)["share_rate"] == pytest.approx(0.0025)
    assert analytics.share_rate(0, 3) is None
    assert analytics.share_rate(100, None) is None


def test_a_week_runs_monday_to_sunday_in_vietnam_time(frozen):
    # Monday 2026-11-02 00:00 in Vietnam is Sunday 17:00 UTC.
    assert analytics.week_start(NOW) == datetime(2026, 11, 1, 17, 0, tzinfo=UTC)
    assert analytics.week_start(datetime(2026, 11, 1, 16, 59, tzinfo=UTC)) == datetime(2026, 10, 25, 17, 0, tzinfo=UTC)


def test_the_kpis_of_this_week_and_last(an, db, me, storage, frozen):
    fanpage = page(db, me)
    monday = datetime(2026, 11, 1, 17, 30, tzinfo=UTC)  # Monday 00:30 in Vietnam: this week
    sunday = datetime(2026, 11, 1, 16, 30, tzinfo=UTC)  # Sunday 23:30 in Vietnam: last week
    for views in (1000, 1000, 1000, 1000):
        marked(db, storage, me, fanpage, views, shares=1, live=sunday)  # 0.1 %: under the goal
    marked(db, storage, me, fanpage, 1000, shares=3, live=monday)  # 0.3 %
    marked(db, storage, me, fanpage, 15000, shares=60, live=monday)  # 0.4 %
    marked(db, storage, me, fanpage, 2000, shares=None, live=monday)  # no share number: not rated
    kpis = an.get("/api/posts/kpis").json()
    assert kpis["this_week"] == {
        "start": "2026-11-02",
        "measured": 3,
        "median_views": 2000,
        "share_goal_met": 2,
        "share_goal_rate": 1.0,
    }
    assert kpis["last_week"] == {
        "start": "2026-10-26",
        "measured": 4,
        "median_views": 1000,
        "share_goal_met": 0,
        "share_goal_rate": 0.0,
    }
    assert kpis["rules"] == {"median_days": 60, "min_samples": 5, "share_goal": 0.002}
    assert kpis["enough_data"] is True


def test_an_empty_week_has_no_median(an, frozen):
    week = an.get("/api/posts/kpis").json()["this_week"]
    assert week == {
        "start": "2026-11-02",
        "measured": 0,
        "median_views": None,
        "share_goal_met": 0,
        "share_goal_rate": None,
    }


def test_the_kpis_need_a_login(client):
    assert client.get("/api/posts/kpis").status_code == 401


def test_the_video_page_shows_the_same_analysis(an, db, me, storage, frozen):
    fanpage = page(db, me)
    for _ in range(5):
        marked(db, storage, me, fanpage, 100)
    high = marked(db, storage, me, fanpage, 5000)
    (post,) = an.get(f"/api/videos/{high.video_id}").json()["publications"]
    assert post["metrics"]["analysis"] == analysis_of(an, high)
    assert post["metrics"]["analysis"]["times_median"] == 50.0
