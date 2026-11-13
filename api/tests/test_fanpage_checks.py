"""Checking each connected Page (fanpages.check): whether its token still works, its current name and its followers,
read by the worker between jobs, and how /fanpages shows it."""

from datetime import UTC, date, datetime, timedelta

import pytest
from conftest import login, make_user, make_video
from fake_services import FACEBOOK_PAGE, FACEBOOK_TOKEN, FACEBOOK_USER_TOKEN
from sqlalchemy import select
from worker_helpers import add_user, committed  # noqa: F401  (fixtures)

from reels_api import analytics, crypto, fanpages
from reels_api.models import Fanpage, FanpageFollowers, FanpageInsights, Publication

URL = "/api/fanpages"


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def add_page(db, user, token: str = FACEBOOK_TOKEN, page_id: str = FACEBOOK_PAGE, name: str = "Trang Dưỡng Sinh"):
    page = fanpages.save(db, page_id, name, token, user.id)
    db.commit()
    return page


def due(db) -> list[int]:
    return [page.id for page in fanpages.due_checks(db, limit=100)]


def ago(hours: float) -> datetime:
    return datetime.now(UTC) - timedelta(hours=hours)


# When a Page is due


def test_a_new_page_is_checked_at_once_then_twice_a_day(db, me, fakes):
    page = add_page(db, me)
    assert due(db) == [page.id]
    fanpages.check(db, page)
    assert due(db) == []
    page.checked_at = ago(11)
    db.commit()
    assert due(db) == []
    page.checked_at = ago(13)
    db.commit()
    assert due(db) == [page.id]


def test_a_stopped_page_is_not_checked(db, me, fakes):
    page = add_page(db, me)
    page.active = False
    db.commit()
    assert due(db) == []


def test_a_new_token_is_checked_again_at_once(db, me, fakes):
    page = add_page(db, me, token="dead-token")
    fanpages.check(db, page)
    assert page.check_error
    add_page(db, me)
    assert (page.checked_at, page.check_error) == (None, None), "the old token's result says nothing of the new one"
    assert due(db) == [page.id]


# What a check records


def test_a_working_token_records_the_followers_and_the_pages_name(db, me, fakes):
    fakes.facebook_pages = [{"id": FACEBOOK_PAGE, "name": "Dưỡng Sinh Mỗi Ngày", "tasks": ["CREATE_CONTENT"]}]
    fakes.facebook_followers = 1520
    page = add_page(db, me)
    changed_at, changed_by = page.updated_at, page.updated_by_id

    fanpages.check(db, page)

    db.refresh(page)
    assert (page.check_error, page.followers_count, page.name) == (None, 1520, "Dưỡng Sinh Mỗi Ngày")
    assert page.checked_at is not None
    assert (page.updated_at, page.updated_by_id) == (changed_at, changed_by), "a check is not a member's change"
    today = datetime.now(analytics.VIETNAM).date()
    assert [(row.day, row.followers) for row in db.scalars(select(FanpageFollowers))] == [(today, 1520)]


def test_a_check_keeps_the_pages_profile_picture_and_the_list_shows_it(an, db, me, fakes):
    fakes.facebook_picture = "https://scontent.example/page-avatar.jpg?oe=1"
    page = add_page(db, me)
    (row,) = an.get(URL).json()
    assert row["picture"] is None, "none before the first check"

    fanpages.check(db, page)
    (row,) = an.get(URL).json()
    assert row["picture"] == "https://scontent.example/page-avatar.jpg?oe=1"

    # Facebook's links expire: the next check brings the new one.
    fakes.facebook_picture = "https://scontent.example/page-avatar.jpg?oe=2"
    fanpages.check(db, page)
    assert an.get(URL).json()[0]["picture"].endswith("oe=2")


@pytest.mark.parametrize("picture", [None, "javascript:alert(1)", "http://insecure.example/a.jpg"])
def test_a_missing_or_unsafe_picture_keeps_the_last_good_one(db, me, fakes, picture):
    fakes.facebook_picture = "https://scontent.example/good.jpg"
    page = add_page(db, me)
    fanpages.check(db, page)
    fakes.facebook_picture = picture
    fanpages.check(db, page)
    db.refresh(page)
    assert page.picture_url == "https://scontent.example/good.jpg"


def test_a_failed_check_keeps_the_picture(db, me, fakes):
    fakes.facebook_picture = "https://scontent.example/good.jpg"
    page = add_page(db, me)
    fanpages.check(db, page)
    fakes.facebook_page_info_refused = True
    fanpages.check(db, page)
    db.refresh(page)
    assert page.check_error and page.picture_url == "https://scontent.example/good.jpg"


def test_a_second_check_on_the_same_day_keeps_one_count_for_the_day(db, me, fakes):
    page = add_page(db, me)
    fakes.facebook_followers = 10
    fanpages.check(db, page)
    fakes.facebook_followers = 12
    fanpages.check(db, page)
    assert [row.followers for row in db.scalars(select(FanpageFollowers))] == [12]


def test_a_dead_token_is_recorded_and_not_checked_again_at_once(db, me, fakes):
    page = add_page(db, me, token="dead-token")
    fanpages.check(db, page)
    assert page.check_error == "Token Facebook hết hạn hoặc không hợp lệ, hãy dán token mới trong Kết nối Fanpage"
    assert page.checked_at is not None
    assert due(db) == [], "a broken token waits for the next round or a member, it never loops"
    assert db.scalars(select(FanpageFollowers)).all() == []


def test_a_token_that_cannot_read_the_page_says_which_permission(db, me, fakes):
    fakes.facebook_page_info_refused = True
    page = add_page(db, me)
    fanpages.check(db, page)
    assert "pages_read_engagement" in page.check_error


def test_a_token_that_cannot_be_decrypted_is_recorded(db, me, fakes):
    page = add_page(db, me)
    page.token_encrypted = "không-phải-token-mã-hoá"
    db.commit()
    fanpages.check(db, page)
    assert page.check_error.startswith("Không đọc được token")


def test_a_good_check_clears_the_last_error(db, me, fakes):
    page = add_page(db, me)
    page.check_error = "Token Facebook hết hạn hoặc không hợp lệ, hãy dán token mới trong Kết nối Fanpage"
    db.commit()
    fanpages.check(db, page)
    assert page.check_error is None


def test_the_worker_round_checks_due_pages_and_survives_a_failure(committed, fakes, monkeypatch):  # noqa: F811
    user = add_user(committed)
    with committed() as db:
        good = add_page(db, user).id
        other = add_page(db, user, page_id="7654321", name="Trang Hai").id

    def check(db, page):
        if page.id == other:
            raise RuntimeError("database hiccup")
        real_check(db, page)

    real_check = fanpages.check
    monkeypatch.setattr(fanpages, "check", check)
    fanpages.check_due(committed)

    with committed() as db:
        assert db.get(Fanpage, good).checked_at is not None


# On /fanpages


def test_the_list_shows_each_pages_check(an, db, me, fakes):
    fakes.facebook_followers = 300
    page = add_page(db, me)
    (row,) = an.get(URL).json()
    assert row["check"] == {
        "checked_at": None,
        "error": None,
        "pending": True,
        "followers": None,
        "followers_this_week": None,
    }
    fanpages.check(db, page)
    (row,) = an.get(URL).json()
    assert row["check"]["error"] is None and row["check"]["pending"] is False
    assert row["check"]["followers"] == 300 and row["check"]["checked_at"]
    assert FACEBOOK_TOKEN not in str(row)


def test_followers_this_week_count_from_the_last_number_before_monday(an, db, me, fakes):
    fakes.facebook_followers = 130
    page = add_page(db, me)
    monday = analytics.week_start(datetime.now(UTC)).astimezone(analytics.VIETNAM).date()
    db.add_all(
        [
            FanpageFollowers(fanpage_id=page.id, day=monday - timedelta(days=3), followers=90),
            FanpageFollowers(fanpage_id=page.id, day=monday - timedelta(days=1), followers=100),
        ]
    )
    db.commit()
    fanpages.check(db, page)
    (row,) = an.get(URL).json()
    assert row["check"]["followers_this_week"] == 30


def test_followers_this_week_wait_for_a_number_from_last_week(an, db, me, fakes):
    page = add_page(db, me)
    fanpages.check(db, page)
    (row,) = an.get(URL).json()
    assert row["check"]["followers"] is not None and row["check"]["followers_this_week"] is None


def test_the_list_counts_the_posts_waiting_on_each_page(an, db, me, storage, fakes):
    page = add_page(db, me)
    video = make_video(db, storage, me, scene_count=1)
    for status, at in (("scheduled", 24), ("scheduled", -24), ("published", -1)):
        db.add(
            Publication(
                video_id=video.id,
                platform="facebook",
                created_by_id=me.id,
                fanpage_id=page.id,
                status=status,
                remote_id=f"r{at}",
                scheduled_at=datetime.now(UTC) + timedelta(hours=at),
            )
        )
    db.commit()
    (row,) = an.get(URL).json()
    assert row["scheduled_posts"] == 1, "only posts still waiting for their time"


def test_check_now_asks_the_worker_and_the_check_answers_it(an, db, me, fakes):
    page = add_page(db, me)
    fanpages.check(db, page)
    assert due(db) == []

    (row,) = an.post(f"{URL}/{page.id}/check").json()
    assert row["check"]["pending"] is True
    assert due(db) == [page.id]

    db.expire_all()
    fanpages.check(db, db.get(Fanpage, page.id))
    (row,) = an.get(URL).json()
    assert row["check"]["pending"] is False


def test_opening_the_page_asks_for_a_check_only_when_the_last_one_is_old(an, db, me, fakes):
    page = add_page(db, me)
    fanpages.check(db, page)
    assert an.post(f"{URL}/freshen").json() == {"asked": 0}, "checked a moment ago"
    assert due(db) == []

    page.checked_at = datetime.now(UTC) - timedelta(hours=1)
    db.commit()
    assert an.post(f"{URL}/freshen").json() == {"asked": 1}
    assert due(db) == [page.id]
    assert an.post(f"{URL}/freshen").json() == {"asked": 0}, "a check already asked for is not asked again"


def test_opening_the_page_never_asks_for_a_stopped_page(an, db, me, fakes):
    page = add_page(db, me)
    fanpages.check(db, page)
    page.active, page.checked_at = False, datetime.now(UTC) - timedelta(hours=1)
    db.commit()
    assert an.post(f"{URL}/freshen").json() == {"asked": 0}


def test_check_now_needs_a_login(client):
    assert client.post(f"{URL}/1/check").status_code == 401


def test_check_now_needs_a_known_page(an):
    assert an.post(f"{URL}/999/check").status_code == 404


def test_a_stopped_page_cannot_be_checked(an, db, me, fakes):
    page = add_page(db, me)
    page.active = False
    db.commit()
    refused = an.post(f"{URL}/{page.id}/check")
    assert refused.status_code == 422


# Where members see a broken Page


def test_the_publish_dialog_knows_a_page_with_a_broken_token(an, db, me, storage, fakes):
    page = add_page(db, me, token="dead-token")
    fanpages.check(db, page)
    video = make_video(db, storage, me, scene_count=1)
    (listed,) = an.get(f"/api/videos/{video.id}").json()["fanpages"]
    assert listed == {
        "id": page.id,
        "name": "Trang Dưỡng Sinh",
        "owner": me.name,
        "owner_id": me.id,
        "knowledge_topic_id": None,
        "tiktok_account_id": None,
        "error": page.check_error,
    }


def test_connecting_with_a_user_token_keeps_the_pages_token_only(an, db, me, fakes):
    an.post(URL, json={"token": FACEBOOK_USER_TOKEN, "page_ids": [FACEBOOK_PAGE]})
    page = db.scalar(select(Fanpage))
    assert crypto.decrypt(page.token_encrypted) == FACEBOOK_TOKEN
    fanpages.check(db, page)
    assert page.check_error is None


def test_the_day_is_vietnam_time(db, me, fakes, monkeypatch):
    late_evening_utc = datetime(2026, 11, 3, 18, 30, tzinfo=UTC)  # 01:30 on 4 November in Vietnam
    monkeypatch.setattr(fanpages, "now", lambda: late_evening_utc)
    page = add_page(db, me)
    fanpages.check(db, page)
    assert [row.day for row in db.scalars(select(FanpageFollowers))] == [date(2026, 11, 4)]


# The Page's daily numbers (Page Insights)


def test_a_check_keeps_the_pages_daily_numbers(an, db, me, fakes):
    page = add_page(db, me)
    fanpages.check(db, page)
    rows = an.get(f"{URL}/{page.id}/insights").json()
    assert [(row["day"], row["views"], row["reach"], row["engagements"]) for row in rows] == [
        ("2026-11-01", 900, 600, 40),
        ("2026-11-02", 1100, 700, 55),
    ], "Facebook dates a day by its end"
    (listed,) = an.get(URL).json()
    assert listed["insights"]["error"] is None


def test_the_last_seven_days_are_summed_on_the_list(an, db, me, fakes, monkeypatch):
    monkeypatch.setattr(fanpages, "now", lambda: datetime(2026, 11, 3, 12, tzinfo=UTC))
    page = add_page(db, me)
    fanpages.check(db, page)
    (listed,) = an.get(URL).json()
    assert listed["insights"]["last_7_days"] == {"views": 2000, "reach": 1300, "engagements": 95}


def test_a_metric_meta_retired_loses_only_that_number(db, me, fakes):
    fakes.facebook_page_metrics_dropped = {"page_post_engagements"}
    page = add_page(db, me)
    fanpages.check(db, page)
    row = db.scalars(select(FanpageInsights).order_by(FanpageInsights.day)).first()
    assert (row.views, row.engagements) == (900, None)
    assert page.insights_error == "Facebook không trả số liệu page_post_engagements"
    assert page.check_error is None, "the token works"


def test_a_token_without_read_insights_is_not_a_broken_connection(db, me, fakes):
    fakes.facebook_page_insights_refused = True
    page = add_page(db, me)
    fanpages.check(db, page)
    assert page.check_error is None
    assert page.insights_error == "Token chưa có quyền đọc số liệu Page (read_insights)"


def test_a_later_check_rewrites_a_revised_day(db, me, fakes):
    page = add_page(db, me)
    fanpages.check(db, page)
    fakes.facebook_page_insights["page_media_view"]["2026-11-03T08:00:00+0000"] = 1500
    fanpages.check(db, page)
    assert sorted(row.views for row in db.scalars(select(FanpageInsights))) == [900, 1500]


def test_insights_of_an_unknown_page(an):
    assert an.get(f"{URL}/999/insights").status_code == 404
