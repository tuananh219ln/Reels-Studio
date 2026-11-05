"""One Page's dashboard (`GET /api/fanpages/{id}/dashboard`): its numbers over 7, 28 or 90 days in Vietnam time, each
against the period before it, from the Page Insights, followers and post numbers the app already keeps."""

from datetime import UTC, date, datetime, timedelta

import pytest
from conftest import login, make_user, make_video

from reels_api import fanpages, page_dashboard
from reels_api.models import FanpageFollowers, FanpageInsights, PostMetrics, Publication

URL = "/api/fanpages"
# 12:00 on 5 November in Vietnam.
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


@pytest.fixture
def page(db, me):
    row = fanpages.save(db, "1234567", "Trang Dưỡng Sinh", "page-token", me.id)
    row.followers_count = 1300
    db.commit()
    return row


def day(days_ago: int) -> date:
    return TODAY - timedelta(days=days_ago)


def insights(db, page, days_ago: int, views=None, reach=None, engagements=None):
    db.add(FanpageInsights(fanpage_id=page.id, day=day(days_ago), views=views, reach=reach, engagements=engagements))
    db.commit()


def post(db, storage, me, page, at: datetime, status="published", **numbers) -> Publication:
    video = make_video(db, storage, me, scene_count=1)
    row = Publication(
        video_id=video.id,
        platform="facebook",
        fanpage_id=page.id,
        status=status,
        created_by_id=me.id,
        remote_id=f"r{video.id}",
        scheduled_at=at,
        published_at=at if status == "published" else None,
    )
    db.add(row)
    db.flush()
    if numbers:
        db.add(PostMetrics(publication_id=row.id, window="latest", measured_at=NOW, **numbers))
    db.commit()
    return row


def get(an, page, days=7):
    response = an.get(f"{URL}/{page.id}/dashboard", params={"days": days})
    assert response.status_code == 200, response.text
    return response.json()


def test_the_period_is_the_last_days_in_vietnam_time_today_included(an, page):
    body = get(an, page, days=7)
    assert (body["start"], body["end"]) == ("2026-10-30", "2026-11-05")
    assert [row["day"] for row in body["series"]][0] == "2026-10-30"
    assert len(body["series"]) == 7
    assert len(get(an, page, days=28)["series"]) == 28
    assert len(get(an, page, days=90)["series"]) == 90


def test_only_7_28_or_90_days(an, page):
    assert an.get(f"{URL}/{page.id}/dashboard", params={"days": 30}).status_code == 422


def test_an_unknown_page(an):
    assert an.get(f"{URL}/999/dashboard").status_code == 404


def test_needs_a_login(client, page):
    assert client.get(f"{URL}/{page.id}/dashboard").status_code == 401


def test_totals_compare_with_the_period_before(an, db, page):
    insights(db, page, 0, views=300, reach=200, engagements=30)
    insights(db, page, 6, views=100, reach=100, engagements=None)
    insights(db, page, 7, views=200, reach=150, engagements=20)  # the period before
    insights(db, page, 13, views=200, reach=None, engagements=None)
    insights(db, page, 14, views=9999, reach=9999, engagements=9999)  # before both
    totals = get(an, page)["totals"]
    assert totals["views"] == {"value": 400, "previous": 400, "change": 0.0}
    assert totals["reach"] == {"value": 300, "previous": 150, "change": 1.0}
    assert totals["engagements"] == {"value": 30, "previous": 20, "change": 0.5}


def test_a_day_without_numbers_is_null_and_nothing_to_compare_gives_no_change(an, db, page):
    insights(db, page, 2, views=50)
    body = get(an, page)
    assert body["totals"]["views"] == {"value": 50, "previous": None, "change": None}
    assert body["totals"]["reach"] == {"value": None, "previous": None, "change": None}
    by_day = {row["day"]: row for row in body["series"]}
    assert by_day["2026-11-03"]["views"] == 50
    assert by_day["2026-11-04"]["views"] is None


def test_followers_gain_counts_from_the_last_number_before_the_period(an, db, page):
    for days_ago, followers in ((15, 1000), (8, 1100), (3, 1250), (0, 1300)):
        db.add(FanpageFollowers(fanpage_id=page.id, day=day(days_ago), followers=followers))
    db.commit()
    body = get(an, page)
    assert body["followers"] == 1300
    assert body["totals"]["followers_gain"] == {"value": 200, "previous": 100, "change": 1.0}
    by_day = {row["day"]: row["followers"] for row in body["series"]}
    assert by_day["2026-11-02"] == 1250 and by_day["2026-11-01"] is None


def test_followers_gain_waits_for_a_number_before_the_period(an, db, page):
    db.add(FanpageFollowers(fanpage_id=page.id, day=day(1), followers=1300))
    db.commit()
    assert get(an, page)["totals"]["followers_gain"]["value"] is None


def test_days_with_a_post_are_marked_by_their_vietnam_day(an, db, storage, me, page):
    # 23:30 on 2 November in Vietnam is still 2 November there, though 3 November has begun nowhere else.
    post(db, storage, me, page, datetime(2026, 11, 2, 16, 30, tzinfo=UTC))
    post(db, storage, me, page, datetime(2026, 11, 2, 1, tzinfo=UTC))
    post(db, storage, me, page, datetime(2026, 10, 25, 1, tzinfo=UTC))  # the period before
    post(db, storage, me, page, datetime(2026, 11, 3, 1, tzinfo=UTC), status="cancelled")
    body = get(an, page)
    by_day = {row["day"]: row["posts"] for row in body["series"]}
    assert by_day["2026-11-02"] == 2
    assert sum(by_day.values()) == 2
    assert body["totals"]["posts"] == {"value": 2, "previous": 1, "change": 1.0}


def test_post_numbers_are_summed_from_the_periods_posts(an, db, storage, me, page):
    post(
        db,
        storage,
        me,
        page,
        NOW - timedelta(days=1),
        views=1000,
        reactions=10,
        comments=4,
        shares=2,
        avg_watch_ms=4000,
    )
    post(
        db,
        storage,
        me,
        page,
        NOW - timedelta(days=2),
        views=3000,
        reactions=20,
        comments=None,
        shares=1,
        avg_watch_ms=8000,
    )
    post(
        db, storage, me, page, NOW - timedelta(days=9), views=500, reactions=15, comments=2, shares=0, avg_watch_ms=5000
    )
    numbers = get(an, page)["post_numbers"]
    assert numbers["reactions"] == {"value": 30, "previous": 15, "change": 1.0}
    assert numbers["comments"] == {"value": 4, "previous": 2, "change": 1.0}
    assert numbers["shares"]["value"] == 3
    # Weighted by views: (4 s × 1000 + 8 s × 3000) / 4000.
    assert numbers["avg_watch_seconds"] == {"value": 7.0, "previous": 5.0, "change": 0.4}


def test_the_latest_post_with_its_numbers_even_when_older_than_the_periods(an, db, storage, me, page):
    old = post(db, storage, me, page, NOW - timedelta(days=40), views=700, reach=500, reactions=9)
    latest = get(an, page)["latest_post"]
    assert latest["id"] == old.id
    assert latest["numbers"]["views"] == 700
    assert latest["video"]["title"]

    newer = post(db, storage, me, page, NOW - timedelta(hours=3))
    latest = get(an, page)["latest_post"]
    assert latest["id"] == newer.id and latest["numbers"] is None, "not read yet"


def test_a_scheduled_post_is_the_latest_only_once_its_time_has_come(an, db, storage, me, page):
    assert get(an, page)["latest_post"] is None
    post(db, storage, me, page, NOW + timedelta(hours=5), status="scheduled")
    assert get(an, page)["latest_post"] is None


def test_upcoming_lists_the_weeks_scheduled_posts_and_free_times(an, db, storage, me, page, monkeypatch):
    monkeypatch.setattr(page_dashboard.page_queue, "now", lambda: NOW, raising=False)
    page.post_times = ["20:00"]
    db.commit()
    soon = post(db, storage, me, page, datetime(2026, 11, 6, 13, tzinfo=UTC), status="scheduled")  # 20:00 on the 6th
    post(db, storage, me, page, NOW + timedelta(days=8), status="scheduled")  # past the week
    upcoming = get(an, page)["upcoming"]
    assert [row["id"] for row in upcoming["posts"]] == [soon.id]
    assert upcoming["post_times"] == ["20:00"]
    # 20:00 each evening from the 5th to the 11th, but the 6th, taken by the scheduled post; the 12th is past the week.
    assert [slot[:10] for slot in upcoming["free_slots"]] == [
        "2026-11-05",
        "2026-11-07",
        "2026-11-08",
        "2026-11-09",
        "2026-11-10",
        "2026-11-11",
    ]


def test_the_page_part_carries_the_token_check(an, db, page):
    body = get(an, page)
    assert body["page"]["name"] == "Trang Dưỡng Sinh"
    assert body["page"]["check"]["checked_at"] is None and body["page"]["check"]["pending"] is True
    assert "token" not in str(body["page"]).replace("token_tail", "")
