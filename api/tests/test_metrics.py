"""A post's numbers on Facebook (metrics.py): when the worker reads them, what it keeps, and how they are shown."""

from datetime import UTC, datetime, timedelta

import pytest
from conftest import login, make_user, make_video
from fake_services import FACEBOOK_PAGE, FACEBOOK_TOKEN
from sqlalchemy import select
from worker_helpers import add_user, committed  # noqa: F401  (fixtures)

from reels_api import facebook, fanpages, metrics
from reels_api.models import PostMetrics, Publication


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def hours_ago(hours: float) -> datetime:
    return datetime.now(UTC) - timedelta(hours=hours)


def add_post(db, storage, user, live_hours_ago: float, remote_id: str = "1000", **fields) -> Publication:
    page = db.scalar(select(fanpages.Fanpage).where(fanpages.Fanpage.page_id == FACEBOOK_PAGE))
    if page is None:
        page = fanpages.save(db, FACEBOOK_PAGE, "Trang Dưỡng Sinh", FACEBOOK_TOKEN, user.id)
        db.flush()
    video = make_video(db, storage, user, scene_count=1)
    fields = {"status": "published", "published_at": hours_ago(live_hours_ago)} | fields
    post = Publication(
        video_id=video.id, platform="facebook", created_by_id=user.id, fanpage_id=page.id, remote_id=remote_id, **fields
    )
    db.add(post)
    db.commit()
    return post


def due(db) -> list[int]:
    return [post.id for post in metrics.due_posts(db, limit=100)]


def windows(post: Publication) -> dict[str, PostMetrics]:
    return {row.window: row for row in post.metrics}


# When a post is due


def test_a_post_is_first_read_an_hour_after_it_went_live(db, me, storage, fakes):
    fresh = add_post(db, storage, me, 0.5)
    hour_old = add_post(db, storage, me, 2, remote_id="1001")
    assert due(db) == [hour_old.id], "Facebook has few numbers to give in the first hour"
    assert fresh.id not in due(db)


def test_a_read_post_is_read_again_a_day_later(db, me, storage, fakes):
    post = add_post(db, storage, me, 5)
    metrics.measure(db, post)
    assert due(db) == []
    post.metrics_tried_at = datetime.now(UTC) - timedelta(hours=23)
    db.commit()
    assert due(db) == []
    post.metrics_tried_at = datetime.now(UTC) - timedelta(hours=25)
    db.commit()
    assert due(db) == [post.id]


def test_a_post_is_followed_for_fourteen_days_only(db, me, storage, fakes):
    add_post(db, storage, me, 15 * 24)
    assert due(db) == []


@pytest.mark.parametrize(
    "fields",
    [
        {"status": "scheduled", "scheduled_at": datetime.now(UTC) + timedelta(hours=3)},
        {"status": "cancelled"},
        {"status": "pending"},
        {"status": "published", "remote_id": None},
    ],
)
def test_a_post_not_public_on_facebook_is_never_read(db, me, storage, fakes, fields):
    add_post(db, storage, me, 5, **fields)
    assert due(db) == []


def test_a_scheduled_post_is_read_once_its_time_has_passed(db, me, storage, fakes):
    post = add_post(db, storage, me, 5, status="scheduled", scheduled_at=hours_ago(2))
    assert due(db) == [post.id]


def test_a_deleted_post_is_no_longer_read_and_keeps_its_numbers(an, db, me, storage, fakes):
    post = add_post(db, storage, me, 5)
    metrics.measure(db, post)
    post.status = "deleted"
    post.metrics_tried_at = hours_ago(48)
    db.commit()
    assert due(db) == []
    (row,) = an.get("/api/posts").json()
    assert row["metrics"]["latest"]["views"] == 1200


def test_the_post_read_longest_ago_comes_first_and_asked_posts_before_all(db, me, storage, fakes):
    old = add_post(db, storage, me, 50)
    new = add_post(db, storage, me, 30, remote_id="1001")
    asked = add_post(db, storage, me, 20 * 24, remote_id="1002", metrics_requested_at=hours_ago(0.01))
    new.metrics_tried_at = hours_ago(30)
    old.metrics_tried_at = hours_ago(40)
    db.commit()
    assert due(db) == [asked.id, old.id, new.id]
    assert [post.id for post in metrics.due_posts(db)] == [asked.id, old.id, new.id][: metrics.BATCH]


# What a reading keeps


def test_a_reading_saves_the_numbers_facebook_gives(db, me, storage, fakes):
    post = add_post(db, storage, me, 5)
    fakes.facebook_insights["1000"] = {"views": 54321, "shares": 120, "comments": 33, "reactions": 900}
    metrics.measure(db, post)
    latest = windows(post)["latest"]
    assert (latest.views, latest.shares, latest.comments, latest.reactions) == (54321, 120, 33, 900)
    assert post.metrics_error is None and post.metrics_tried_at is not None
    assert "48h" not in windows(post), "5 hours is too early for the 48-hour mark"


def test_a_number_facebook_leaves_out_is_none_not_zero(db, me, storage, fakes):
    post = add_post(db, storage, me, 5)
    fakes.facebook_insights["1000"] = {"views": 10}
    metrics.measure(db, post)
    latest = windows(post)["latest"]
    assert (latest.views, latest.shares, latest.comments, latest.reactions) == (10, None, None, None)


def test_a_reading_keeps_watch_time_reach_replays_follows_and_the_retention_curve(db, me, storage, fakes):
    post = add_post(db, storage, me, 5)
    fakes.facebook_insights["1000"] = {
        "views": 1500,
        "plays": 1200,
        "replays": 300,
        "reach": 900,
        "avg_watch_ms": 8450,
        "view_time_ms": 12675000,
        "followers": 7,
        "retention": {"0": 1, "1": 0.8, "2": 0.55, "3": 0.4},
    }
    metrics.measure(db, post)
    latest = windows(post)["latest"]
    assert (latest.plays, latest.replays, latest.reach, latest.followers) == (1200, 300, 900, 7)
    assert (latest.avg_watch_ms, latest.view_time_ms) == (8450, 12675000)
    assert latest.retention == [1.0, 0.8, 0.55, 0.4]


def test_a_retention_curve_in_percent_or_out_of_order_is_kept_as_fractions_in_order(db, me, storage, fakes):
    post = add_post(db, storage, me, 5)
    fakes.facebook_insights["1000"] = {"views": 10, "retention": {"2": 50, "0": 100, "10": 5, "1": 75}}
    metrics.measure(db, post)
    assert windows(post)["latest"].retention == [1.0, 0.75, 0.5, 0.05]


def test_numbers_facebook_does_not_give_for_an_older_reel_stay_none(db, me, storage, fakes):
    post = add_post(db, storage, me, 5)
    fakes.facebook_insights["1000"] = {"views": 10}
    metrics.measure(db, post)
    latest = windows(post)["latest"]
    assert (latest.plays, latest.replays, latest.reach, latest.avg_watch_ms, latest.retention) == (
        None,
        None,
        None,
        None,
        None,
    )


def test_the_list_shows_watch_time_against_the_posted_length_and_the_scenes(an, db, me, storage, fakes):
    marks = [{"label": "Tiêu đề", "start": 0.0, "end": 3.0}, {"label": "Cảnh 1", "start": 3.0, "end": 20.0}]
    post = add_post(db, storage, me, 5, scene_marks=marks)
    fakes.facebook_insights["1000"] = {"views": 100, "avg_watch_ms": 8000, "retention": {"0": 1, "1": 0.5}}
    metrics.measure(db, post)
    shown = an.get("/api/posts").json()[0]["metrics"]
    assert shown["latest"]["avg_watch_seconds"] == 8.0
    assert shown["latest"]["watch_ratio"] == 0.4, "8 of the 20 seconds posted"
    assert shown["latest"]["retention"] == [1.0, 0.5]
    assert (shown["length_seconds"], shown["scenes"]) == (20.0, marks)


def test_a_post_from_before_scene_marks_has_no_watch_ratio(an, db, me, storage, fakes):
    post = add_post(db, storage, me, 5)
    fakes.facebook_insights["1000"] = {"views": 100, "avg_watch_ms": 8000}
    metrics.measure(db, post)
    shown = an.get("/api/posts").json()[0]["metrics"]
    assert (shown["latest"]["avg_watch_seconds"], shown["latest"]["watch_ratio"]) == (8.0, None)
    assert (shown["length_seconds"], shown["scenes"]) == (None, [])


def test_a_new_reading_rewrites_latest(db, me, storage, fakes):
    post = add_post(db, storage, me, 5)
    metrics.measure(db, post)
    fakes.facebook_insights["1000"] = {"views": 5000, "shares": 9, "comments": 1, "reactions": 2}
    metrics.measure(db, post)
    assert db.scalar(select(PostMetrics.views).where(PostMetrics.publication_id == post.id)) == 5000
    assert len(post.metrics) == 1


def test_the_first_reading_after_48_hours_is_kept_as_the_48_hour_mark(db, me, storage, fakes):
    post = add_post(db, storage, me, 49)
    post.metrics_tried_at = hours_ago(10)  # read at 39 hours: not due as a daily reading yet
    db.commit()
    assert due(db) == [post.id], "the 48-hour mark does not wait for the daily reading"
    fakes.facebook_insights["1000"] = {"views": 800, "shares": 2, "comments": 0, "reactions": 10}
    metrics.measure(db, post)
    assert windows(post)["48h"].views == 800
    fakes.facebook_insights["1000"] = {"views": 9000, "shares": 20, "comments": 4, "reactions": 50}
    post.metrics_tried_at = hours_ago(25)
    db.commit()
    metrics.measure(db, post)
    assert (windows(post)["48h"].views, windows(post)["latest"].views) == (800, 9000), "the mark is never rewritten"


def test_a_post_past_the_48_hour_mark_by_over_a_day_gets_no_mark(db, me, storage, fakes):
    """A post older than this feature, or one Facebook would not answer for in time, is not compared at a wrong age."""
    post = add_post(db, storage, me, 80)
    metrics.measure(db, post)
    assert set(windows(post)) == {"latest"}


def test_facebook_without_read_insights_says_so_and_keeps_the_last_numbers(db, me, storage, fakes):
    post = add_post(db, storage, me, 5)
    metrics.measure(db, post)
    fakes.facebook_insights_refused = True
    metrics.measure(db, post)
    assert post.metrics_error == (
        "Token Facebook chưa có quyền đọc chỉ số (read_insights), hãy dán token mới trong Kết nối Fanpage"
    )
    assert windows(post)["latest"].views == 1200
    assert due(db) == [], "a failed reading waits a day, never loops"


def test_a_reading_that_works_again_clears_the_error(db, me, storage, fakes):
    post = add_post(db, storage, me, 5)
    fakes.facebook_insights_refused = True
    metrics.measure(db, post)
    fakes.facebook_insights_refused = False
    metrics.measure(db, post)
    assert post.metrics_error is None


def test_a_bad_token_fails_with_the_token_message(db, me, storage, fakes):
    post = add_post(db, storage, me, 5)
    with pytest.raises(facebook.FacebookError) as err:
        facebook.reel_insights(facebook.Page(FACEBOOK_PAGE, "wrong"), "1000")
    assert err.value.message.startswith("Token Facebook hết hạn")
    assert post.metrics == []


def test_a_reel_facebook_no_longer_has_is_said_plainly(db, me, storage, fakes):
    post = add_post(db, storage, me, 5)
    fakes.facebook_insights_gone.add("1000")
    metrics.measure(db, post)
    assert post.metrics_error == "Facebook không còn reel này hoặc chưa có chỉ số"


# The worker and the api


def test_one_worker_round_reads_a_few_due_posts(committed, storage, fakes):  # noqa: F811  (fixture)
    user = add_user(committed)
    with committed() as db:
        ids = [add_post(db, storage, user, 5 + index, remote_id=str(1000 + index)).id for index in range(5)]
    metrics.measure_due(committed)
    assert fakes.facebook_insights_calls == metrics.BATCH
    with committed() as db:
        read = db.scalars(select(PostMetrics.publication_id)).all()
    assert sorted(read) == ids[: metrics.BATCH], "never-read posts in the order they were posted; the rest next round"


def test_a_round_never_calls_facebook_when_nothing_is_due(committed, storage, fakes):  # noqa: F811  (fixture)
    user = add_user(committed)
    with committed() as db:
        add_post(db, storage, user, 0.2)
    metrics.measure_due(committed)
    assert fakes.facebook_insights_calls == 0


def test_the_list_shows_each_posts_numbers_and_when_they_were_read(an, db, me, storage, fakes):
    post = add_post(db, storage, me, 5)
    unread = add_post(db, storage, me, 6, remote_id="1001")
    metrics.measure(db, post)
    rows = {row["id"]: row["metrics"] for row in an.get("/api/posts").json()}
    latest = rows[post.id]["latest"]
    assert (latest["views"], latest["shares"], latest["comments"], latest["reactions"]) == (1200, 3, 5, 40)
    assert datetime.fromisoformat(latest["measured_at"]) == post.metrics_tried_at
    assert rows[post.id]["at_48h"] is None
    unread_metrics = rows[unread.id]
    assert (unread_metrics["latest"], unread_metrics["at_48h"], unread_metrics["error"]) == (None, None, None)
    assert unread_metrics["pending"] is False


def test_asking_for_new_numbers_only_marks_the_post(an, db, me, storage, fakes):
    post = add_post(db, storage, me, 20 * 24)
    reply = an.post(f"/api/posts/{post.id}/metrics")
    assert reply.status_code == 200
    assert reply.json()["metrics"]["pending"] is True
    assert fakes.facebook_insights_calls == 0, "a request never calls Facebook"
    assert due(db) == [post.id], "even past the days the worker follows"
    metrics.measure(db, post)
    assert an.get("/api/posts").json()[0]["metrics"]["pending"] is False


@pytest.mark.parametrize(
    "fields",
    [
        {"status": "scheduled", "scheduled_at": datetime.now(UTC) + timedelta(hours=3)},
        {"status": "cancelled"},
        {"status": "published", "remote_id": None},
    ],
)
def test_only_a_public_post_can_be_asked_for_numbers(an, db, me, storage, fakes, fields):
    post = add_post(db, storage, me, 5, **fields)
    reply = an.post(f"/api/posts/{post.id}/metrics")
    assert (reply.status_code, reply.json()["message"]) == (409, "Chỉ cập nhật view được cho bài đã đăng lên Facebook")


def test_opening_the_posts_page_asks_for_followed_posts_not_read_lately(an, db, me, storage, fakes):
    stale = add_post(db, storage, me, 30, metrics_tried_at=hours_ago(2))
    add_post(db, storage, me, 30, remote_id="1001", metrics_tried_at=hours_ago(0.1))
    add_post(db, storage, me, 0.5, remote_id="1002")
    add_post(db, storage, me, 24 * 20, remote_id="1003", metrics_tried_at=hours_ago(48))
    assert due(db) == []
    assert an.post("/api/posts/freshen").json() == {"asked": 1}, "not one read minutes ago, too new or past 14 days"
    assert due(db) == [stale.id]
    assert an.post("/api/posts/freshen").json() == {"asked": 0}, "a reading already asked for is not asked again"


def test_asking_for_a_missing_post_is_404(an):
    assert an.post("/api/posts/999999/metrics").status_code == 404


def test_asking_for_numbers_needs_a_login(client):
    assert client.post("/api/posts/1/metrics").status_code == 401
