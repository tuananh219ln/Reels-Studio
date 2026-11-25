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
