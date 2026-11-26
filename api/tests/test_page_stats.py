"""The "Thống kê" page (`GET /api/stats`): Pages side by side, each row the same numbers as the Page's own dashboard."""

from datetime import UTC, date, datetime, timedelta

import pytest
from conftest import login, make_user, make_video

from reels_api import fanpages, page_dashboard
from reels_api.models import FanpageInsights, PostMetrics, Publication

NOW = datetime(2026, 11, 5, 5, tzinfo=UTC)
TODAY = date(2026, 11, 5)


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me, monkeypatch):
    monkeypatch.setattr(page_dashboard, "now", lambda: NOW)
    login(client)
    return client


def add_page(db, me, page_id, name):
    row = fanpages.save(db, page_id, name, "page-token", me.id)
    db.commit()
    return row


def add_post(db, storage, me, page, **numbers):
    video = make_video(db, storage, me, scene_count=1)
    at = NOW - timedelta(days=2)
    row = Publication(
        video_id=video.id,
        platform="facebook",
        fanpage_id=page.id,
        status="published",
        created_by_id=me.id,
        remote_id=f"r{video.id}",
        scheduled_at=at,
        published_at=at,
    )
    db.add(row)
    db.flush()
    db.add(PostMetrics(publication_id=row.id, window="latest", measured_at=NOW, **numbers))
    db.commit()
    return row


def test_needs_a_login(client):
    assert client.get("/api/stats").status_code == 401


def test_only_7_28_or_90_days_and_known_platforms(an):
    assert an.get("/api/stats", params={"days": 30}).status_code == 422
    assert an.get("/api/stats", params={"platform": "tiktok"}).status_code == 422
    assert an.get("/api/stats", params={"page_ids": "a,b"}).status_code == 422


def test_one_row_per_page_asked_for_and_no_grand_total(an, db, me):
    one, two = add_page(db, me, "1111111", "Một"), add_page(db, me, "2222222", "Hai")
    add_page(db, me, "3333333", "Ba")
    body = an.get("/api/stats", params={"days": 7, "page_ids": f"{one.id},{two.id}"}).json()
    assert [row["page"]["name"] for row in body["rows"]] == ["Hai", "Một"]
    assert "total" not in body and "totals" not in body
    assert len(an.get("/api/stats").json()["rows"]) == 3


def test_a_row_agrees_with_the_pages_own_dashboard(an, db, me):
    page = add_page(db, me, "1111111", "Một")
    db.add(FanpageInsights(fanpage_id=page.id, day=TODAY, views=300, reach=200, engagements=30))
    db.commit()
    row = an.get("/api/stats", params={"days": 7, "page_ids": str(page.id)}).json()["rows"][0]
    dashboard = an.get(f"/api/fanpages/{page.id}/dashboard", params={"days": 7}).json()
    assert row["totals"]["views"] == dashboard["totals"]["views"] == {"value": 300, "previous": None, "change": None}
    assert row["gate"]["state"] == "measuring"
    assert row["best_times"]["enough"] is False


def test_watch_time_and_share_per_view_come_from_the_posts_and_stay_null_without_them(an, db, storage, me):
    empty = add_page(db, me, "1111111", "Trống")
    page = add_page(db, me, "2222222", "Có bài")
    add_post(db, storage, me, page, views=1000, shares=10, view_time_ms=60_000)
    add_post(db, storage, me, page, views=1000, shares=30, view_time_ms=None)
    rows = {row["page"]["id"]: row for row in an.get("/api/stats", params={"days": 7}).json()["rows"]}
    assert rows[page.id]["share_per_view"] == 0.02
    assert rows[page.id]["view_time_seconds"] == 60
    assert len(rows[page.id]["measuring"]) == 2
    assert rows[empty.id]["share_per_view"] is None and rows[empty.id]["view_time_seconds"] is None


def test_instagram_lists_only_pages_with_an_account(an, db, me):
    add_page(db, me, "1111111", "Không IG")
    linked = add_page(db, me, "2222222", "Có IG")
    linked.instagram_user_id, linked.instagram_username = "178", "coig"
    db.commit()
    body = an.get("/api/stats", params={"platform": "instagram"}).json()
    assert [row["page"]["name"] for row in body["rows"]] == ["Có IG"]
    assert body["rows"][0]["account"]["username"] == "coig"


def add_measured(db, storage, me, page, seconds, views, *, status="published", mp4=True):
    """A post of a video `seconds` long, read at 48 hours with `views`."""
    video = make_video(db, storage, me, scene_count=1)
    video.mp4_seconds = seconds if mp4 else None
    at = NOW - timedelta(days=3)
    row = Publication(
        video_id=video.id,
        platform="facebook",
        fanpage_id=page.id,
        status=status,
        created_by_id=me.id,
        remote_id=f"r{video.id}",
        scheduled_at=at,
        published_at=at,
    )
    db.add(row)
    db.flush()
    db.add(PostMetrics(publication_id=row.id, window="latest", measured_at=NOW, views=views))
    db.add(PostMetrics(publication_id=row.id, window="48h", measured_at=NOW, views=views))
    db.commit()
    return row


def buckets_of(an, page):
    row = an.get("/api/stats", params={"days": 7, "page_ids": str(page.id)}).json()["rows"][0]
    return {one["bucket"]: one for one in row["duration_buckets"]}


def test_duration_buckets_have_a_median_only_from_five_posts_and_the_best_one_is_marked(an, db, storage, me):
    page = add_page(db, me, "1111111", "Một")
    for views in (100, 200, 300, 400, 500):
        add_measured(db, storage, me, page, 50.0, views)
    for views in (10, 20, 30, 40, 50):
        add_measured(db, storage, me, page, 75.0, views)
    for views in (900, 900):
        add_measured(db, storage, me, page, 30.0, views)
    found = buckets_of(an, page)
    assert list(found) == ["<45s", "45–60s", ">60s"]
    assert found["45–60s"] == {"bucket": "45–60s", "videos": 5, "median_views_48h": 300, "best": True}
    assert found[">60s"]["median_views_48h"] == 30 and found[">60s"]["best"] is False
    assert found["<45s"] == {"bucket": "<45s", "videos": 2, "median_views_48h": None, "best": False}


def test_a_bucket_edge_belongs_to_the_longer_bucket(an, db, storage, me):
    page = add_page(db, me, "1111111", "Một")
    add_measured(db, storage, me, page, 45.0, 1)
    add_measured(db, storage, me, page, 60.0, 1)
    found = buckets_of(an, page)
    assert (found["<45s"]["videos"], found["45–60s"]["videos"], found[">60s"]["videos"]) == (0, 1, 1)


def test_no_best_with_one_bucket_and_a_tie_marks_every_tied_bucket(an, db, storage, me):
    page = add_page(db, me, "1111111", "Một")
    for _ in range(5):
        add_measured(db, storage, me, page, 50.0, 100)
    assert not any(one["best"] for one in buckets_of(an, page).values())
    for _ in range(5):
        add_measured(db, storage, me, page, 70.0, 100)
    found = buckets_of(an, page)
    assert found["45–60s"]["best"] and found[">60s"]["best"]


def test_deleted_posts_and_videos_without_a_length_are_left_out(an, db, storage, me):
    page = add_page(db, me, "1111111", "Một")
    for _ in range(4):
        add_measured(db, storage, me, page, 50.0, 100)
    add_measured(db, storage, me, page, 50.0, 100, status="deleted")
    add_measured(db, storage, me, page, 50.0, 100, mp4=False)
    found = buckets_of(an, page)
    assert found["45–60s"]["videos"] == 4 and found["45–60s"]["median_views_48h"] is None


def test_instagram_rows_have_no_duration_buckets_and_old_facebook_fields_stay(an, db, me):
    page = add_page(db, me, "1111111", "Một")
    page.instagram_user_id, page.instagram_username = "178", "coig"
    db.commit()
    assert "duration_buckets" not in an.get("/api/stats", params={"platform": "instagram"}).json()["rows"][0]
    row = an.get("/api/stats", params={"page_ids": str(page.id)}).json()["rows"][0]
    assert {"totals", "gate", "winners", "measuring", "best_times", "share_per_view"} <= set(row)
