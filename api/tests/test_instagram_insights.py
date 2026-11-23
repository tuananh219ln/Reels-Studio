"""A Page's Instagram numbers: read with the Page check (`instagram_manage_insights`), kept per day, and the
Instagram side of its dashboard."""

from datetime import UTC, datetime, timedelta

import pytest
from conftest import login, make_user
from fake_services import FACEBOOK_PAGE, FACEBOOK_TOKEN
from sqlalchemy import select
from worker_helpers import add_user, committed  # noqa: F401  (fixtures)

from reels_api import analytics, fanpages, instagram
from reels_api.models import Fanpage, InstagramInsights

URL = "/api/fanpages"


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def add_page(db, user):
    page = fanpages.save(db, FACEBOOK_PAGE, "Trang Dưỡng Sinh", FACEBOOK_TOKEN, user.id)
    db.commit()
    return page


def today():
    return datetime.now(UTC).astimezone(analytics.VIETNAM).date()


def test_a_check_keeps_the_last_seven_days_of_the_linked_account(db, me, fakes):
    page = add_page(db, me)
    fanpages.check(db, page)
    rows = {row.day: row for row in db.scalars(select(InstagramInsights))}
    assert sorted(rows) == [today() - timedelta(days=n) for n in range(6, -1, -1)]
    day = today()
    assert (rows[day].views, rows[day].reach, rows[day].interactions) == (1000 + day.day, 700 + day.day, 50 + day.day)
    assert rows[day].follows == day.day % 5
    assert page.instagram_followers_count == 1204
    assert page.instagram_insights_error is None and page.check_error is None


def test_a_token_without_instagram_manage_insights_is_not_a_broken_connection(db, me, fakes):
    fakes.instagram_insights_refused = True
    page = add_page(db, me)
    fanpages.check(db, page)
    assert page.check_error is None
    assert page.instagram_insights_error == instagram.NO_INSIGHTS_PERMISSION
    assert db.scalars(select(InstagramInsights)).all() == []
    assert page.instagram_user_id, "the account itself is still read"
    assert len(fakes.instagram_insights_calls) == 1, "it stops at the first refusal"


def test_a_metric_instagram_drops_leaves_the_others(db, me, fakes):
    fakes.instagram_metrics_dropped = {"reach"}
    page = add_page(db, me)
    fanpages.check(db, page)
    row = db.scalars(select(InstagramInsights).order_by(InstagramInsights.day.desc())).first()
    assert row.reach is None and row.views is not None and row.interactions is not None
    assert page.instagram_insights_error == "Instagram không trả số liệu reach"


def test_a_page_without_instagram_reads_no_numbers(db, me, fakes):
    fakes.instagram_account = None
    page = add_page(db, me)
    fanpages.check(db, page)
    assert fakes.instagram_insights_calls == []
    assert (page.instagram_user_id, page.instagram_insights_error, page.instagram_followers_count) == (None, None, None)


def test_a_later_check_rewrites_a_revised_day(db, me, fakes):
    page = add_page(db, me)
    fanpages.check(db, page)
    fakes.instagram_insights["views"] = {today().isoformat(): 9999}
    fanpages.check(db, page)
    row = db.scalars(select(InstagramInsights).where(InstagramInsights.day == today())).one()
    assert row.views == 9999
    assert len(db.scalars(select(InstagramInsights)).all()) == 7, "one row per day"


def test_a_read_that_fails_keeps_the_days_already_stored(db, me, fakes):
    page = add_page(db, me)
    fanpages.check(db, page)
    fakes.instagram_insights_refused = True
    fanpages.check(db, page)
    assert len(db.scalars(select(InstagramInsights)).all()) == 7
    assert page.instagram_insights_error == instagram.NO_INSIGHTS_PERMISSION


def test_the_instagram_dashboard_totals_each_period_against_the_one_before(an, db, me, fakes):
    page = add_page(db, me)
    fanpages.check(db, page)
    body = an.get(f"{URL}/{page.id}/instagram-dashboard?days=7").json()
    assert body["account"]["id"] and body["page"]["name"] == "Trang Dưỡng Sinh"
    assert len(body["series"]) == 7 and body["series"][-1]["day"] == today().isoformat()
    expected = sum(1000 + (today() - timedelta(days=n)).day for n in range(7))
    assert body["totals"]["views"]["value"] == expected
    assert body["totals"]["views"]["previous"] is None, "no numbers for the week before"
    assert body["totals"]["views"]["change"] is None
    assert body["followers"] == 1204 and body["insights_error"] is None


def test_a_day_without_a_number_is_none_not_zero(an, db, me, fakes):
    page = add_page(db, me)
    page.instagram_user_id = "17841400000000001"
    db.commit()
    body = an.get(f"{URL}/{page.id}/instagram-dashboard?days=28").json()
    assert len(body["series"]) == 28
    assert all(point["views"] is None for point in body["series"])
    assert body["totals"]["views"]["value"] is None


def test_the_dashboard_of_a_page_without_instagram_is_404(an, db, me, fakes):
    page = add_page(db, me)
    db.get(Fanpage, page.id).instagram_user_id = None
    db.commit()
    answer = an.get(f"{URL}/{page.id}/instagram-dashboard")
    assert answer.status_code == 404 and answer.json()["message"] == "Page này chưa liên kết tài khoản Instagram"


def test_the_instagram_dashboard_takes_only_the_three_periods(an, db, me, fakes):
    page = add_page(db, me)
    assert an.get(f"{URL}/{page.id}/instagram-dashboard?days=5").status_code == 422
    assert an.get(f"{URL}/999/instagram-dashboard").status_code == 404
