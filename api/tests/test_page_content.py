"""One Page's content library (`GET /api/fanpages/{id}/content`, the "Nội dung" tab of its dashboard): one row per
post the app made to the Page that went live in the period, with its latest numbers and its 48-hour views against the
Page's median."""

from datetime import UTC, datetime, timedelta

import pytest
from conftest import login, make_user, make_video

from reels_api import analytics, fanpages, page_dashboard, videos
from reels_api.models import PostMetrics, Publication

URL = "/api/fanpages"
# 12:00 on 5 November in Vietnam.
NOW = datetime(2026, 11, 5, 5, tzinfo=UTC)


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me, monkeypatch):
    for module in (page_dashboard, analytics, videos):
        monkeypatch.setattr(module, "now", lambda: NOW)
    login(client)
    return client


@pytest.fixture
def page(db, me):
    return fanpages.save(db, "1234567", "Trang Dưỡng Sinh", "page-token", me.id)


def post(db, storage, me, page, at: datetime, status="published", latest=None, mark=None, **fields) -> Publication:
    video = make_video(db, storage, me, scene_count=1)
    row = Publication(
        video_id=video.id,
        platform="facebook",
        fanpage_id=page.id,
        status=status,
        created_by_id=me.id,
        remote_id=f"r{video.id}",
        scheduled_at=at,
        published_at=at if status != "scheduled" else None,
        **fields,
    )
    db.add(row)
    db.flush()
    if latest is not None:
        db.add(PostMetrics(publication_id=row.id, window="latest", measured_at=NOW, **latest))
    if mark is not None:
        db.add(PostMetrics(publication_id=row.id, window="48h", measured_at=at + timedelta(hours=48), views=mark))
    db.commit()
    return row


def get(an, page, days=28):
    response = an.get(f"{URL}/{page.id}/content", params={"days": days})
    assert response.status_code == 200, response.text
    return response.json()


def test_one_row_per_post_that_went_live_in_the_period_newest_first(an, db, storage, me, page):
    old = post(db, storage, me, page, NOW - timedelta(days=3))
    new = post(db, storage, me, page, NOW - timedelta(hours=2))
    post(db, storage, me, page, NOW - timedelta(days=10))  # before the 7 days
    body = get(an, page, days=7)
    assert (body["start"], body["end"], body["days"]) == ("2026-10-30", "2026-11-05", 7)
    assert [row["id"] for row in body["posts"]] == [new.id, old.id]
    assert len(get(an, page, days=28)["posts"]) == 3


def test_the_period_starts_at_midnight_vietnam_time(an, db, storage, me, page):
    # 23:30 on 29 October in Vietnam is the day before the 7 days; 00:30 on 30 October is their first.
    post(db, storage, me, page, datetime(2026, 10, 29, 16, 30, tzinfo=UTC))
    inside = post(db, storage, me, page, datetime(2026, 10, 29, 17, 30, tzinfo=UTC))
    assert [row["id"] for row in get(an, page, days=7)["posts"]] == [inside.id]


def test_a_row_has_the_video_the_reel_and_its_latest_numbers(an, db, storage, me, page):
    numbers = dict(
        views=1200, reach=900, reactions=40, comments=6, shares=3, avg_watch_ms=7250, followers=5, plays=1100
    )
    row = post(db, storage, me, page, NOW - timedelta(days=3), latest=numbers)
    [got] = get(an, page)["posts"]
    assert got["status"] == "published"
    assert got["url"] == f"https://www.facebook.com/reel/{row.remote_id}"
    assert got["live_at"] == (NOW - timedelta(days=3)).isoformat()
    assert got["video"]["id"] == row.video_id
    assert got["video"]["title"]
    assert got["numbers"] == {
        "views": 1200,
        "reach": 900,
        "reactions": 40,
        "comments": 6,
        "shares": 3,
        "avg_watch_seconds": 7.2,
        "followers": 5,
        "measured_at": NOW.isoformat(),
    }
    assert got["can_refresh"] is True
    assert (got["pending"], got["error"]) == (False, None)


def test_a_post_not_read_yet_has_no_numbers(an, db, storage, me, page):
    post(db, storage, me, page, NOW - timedelta(minutes=20), metrics_requested_at=NOW - timedelta(minutes=1))
    [got] = get(an, page)["posts"]
    assert got["numbers"] is None
    assert got["pending"] is True


def test_48_hour_views_against_the_pages_median_once_it_has_enough_posts(an, db, storage, me, page):
    marks = [100, 200, 300, 400, 500]
    for days_ago, views in zip(range(3, 8), marks, strict=True):
        post(db, storage, me, page, NOW - timedelta(days=days_ago), mark=views)
    body = get(an, page)
    assert body["median"] == {"views": 300, "samples": 5, "min_samples": analytics.MIN_SAMPLES}
    by_views = {row["views_48h"]: row["times_median"] for row in body["posts"]}
    assert by_views == {100: 0.3, 200: 0.7, 300: 1.0, 400: 1.3, 500: 1.7}


def test_too_few_measured_posts_give_no_comparison(an, db, storage, me, page):
    post(db, storage, me, page, NOW - timedelta(days=3), mark=250)
    body = get(an, page)
    assert body["median"]["samples"] == 1
    [got] = body["posts"]
    assert (got["views_48h"], got["times_median"]) == (250, None)


def test_a_deleted_reel_stays_listed_without_its_link_or_refresh(an, db, storage, me, page):
    post(db, storage, me, page, NOW - timedelta(days=3), status="deleted", closed_at=NOW - timedelta(days=1))
    [got] = get(an, page)["posts"]
    assert got["status"] == "deleted"
    assert got["url"] is None
    assert got["can_refresh"] is False
    assert got["closed_at"] == (NOW - timedelta(days=1)).isoformat()


def test_posts_not_live_and_other_pages_are_left_out(an, db, storage, me, page):
    other = fanpages.save(db, "7654321", "Trang Khác", "page-token-2", me.id)
    post(db, storage, me, other, NOW - timedelta(days=1))
    post(db, storage, me, page, NOW + timedelta(hours=5), status="scheduled")  # not its time yet
    post(db, storage, me, page, NOW - timedelta(days=1), status="cancelled")
    post(db, storage, me, page, NOW - timedelta(days=1), status="pending")
    live = post(db, storage, me, page, NOW - timedelta(hours=1), status="scheduled")  # its time has come
    rows = get(an, page)["posts"]
    assert [(row["id"], row["status"]) for row in rows] == [(live.id, "published")]


def test_only_7_28_or_90_days(an, page):
    response = an.get(f"{URL}/{page.id}/content", params={"days": 30})
    assert response.status_code == 422


def test_an_unknown_page(an):
    assert an.get(f"{URL}/9999/content").status_code == 404


def test_needs_a_login(client, page):
    assert client.get(f"{URL}/{page.id}/content").status_code == 401
