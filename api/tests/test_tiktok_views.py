"""TikTok views ("Bài đăng" part 4): read through an account connected with `video.list`, or entered by hand
("Nhập view") for an account that is not (metrics.measure_tiktok, routes_posts.enter_views)."""

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from conftest import login, make_user, make_video
from fake_services import TIKTOK_CODE
from sqlalchemy import select

from reels_api import metrics, tiktok
from reels_api.models import AffiliateAccount, PostMetricSnapshot, Publication, TikTokConnection

VIDEO_ID = "7301234567890123456"


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def connect(an, fakes, video_list: bool) -> TikTokConnection:
    """ "Kết nối TikTok" through the fake: TikTok grants video.list only when the app asked and was approved."""
    if video_list:
        fakes.tiktok_scope += ",video.list"
    start = an.get("/api/tiktok/oauth/start", follow_redirects=False).json()["url"]
    state = parse_qs(urlsplit(start).query)["state"][0]
    an.get(f"/api/tiktok/oauth/callback?code={TIKTOK_CODE}&state={state}", follow_redirects=False)


def tiktok_post(db, storage, user, account_id, **extra) -> Publication:
    video = make_video(db, storage, user, scene_count=1)
    post = Publication(
        video_id=video.id,
        platform="tiktok",
        source="manual_link",
        external_id=VIDEO_ID,
        post_url=f"https://www.tiktok.com/@an/video/{VIDEO_ID}",
        affiliate_account_id=account_id,
        created_by_id=user.id,
        **({"status": "published", "published_at": datetime.now(UTC) - timedelta(hours=2)} | extra),
    )
    db.add(post)
    db.commit()
    return post


def test_the_scope_is_asked_only_once_approved(fakes, monkeypatch):
    monkeypatch.delenv("TIKTOK_VIDEO_LIST", raising=False)
    assert "video.list" not in parse_qs(urlsplit(tiktok.authorize_url("s")).query)["scope"][0]
    monkeypatch.setenv("TIKTOK_VIDEO_LIST", "1")
    assert parse_qs(urlsplit(tiktok.authorize_url("s")).query)["scope"][0].endswith(",video.list")


def test_a_connected_account_s_videos_are_read_with_their_time(an, db, me, storage, fakes):
    connect(an, fakes, video_list=True)
    connection = db.scalar(select(TikTokConnection))
    post = tiktok_post(db, storage, me, connection.affiliate_account_id)
    fakes.tiktok_videos[VIDEO_ID] = {"view_count": 12_345, "create_time": 1763089200}
    due = metrics.due_posts(db, 40, "tiktok")
    assert [row.id for row in due] == [post.id]
    metrics.measure_tiktok(db, due)
    snapshot = db.scalar(select(PostMetricSnapshot).where(PostMetricSnapshot.publication_id == post.id))
    assert (snapshot.views, snapshot.likes, snapshot.comments, snapshot.shares) == (12_345, 40, 6, 2)
    assert post.published_at == datetime.fromtimestamp(1763089200, UTC) and post.published_at_source == "api"
    cell = an.get("/api/posts/board").json()["items"][0]["cells"]["tiktok"]
    assert (cell["source"], cell["views"], cell["hint"]) == ("oauth", 12_345, None)


def test_a_video_gone_twice_is_removed(an, db, me, storage, fakes):
    connect(an, fakes, video_list=True)
    connection = db.scalar(select(TikTokConnection))
    post = tiktok_post(db, storage, me, connection.affiliate_account_id)
    fakes.tiktok_videos_gone.add(VIDEO_ID)
    metrics.measure_tiktok(db, [post])
    assert post.status == "published" and post.gone_since is not None
    post.gone_since = datetime.now(UTC) - timedelta(hours=1.1)
    db.commit()
    metrics.measure_tiktok(db, [post])
    assert post.status == "deleted" and "TikTok không còn" in post.metrics_error


def test_an_account_without_video_list_is_not_read_and_says_so(an, db, me, storage, fakes):
    connect(an, fakes, video_list=False)
    connection = db.scalar(select(TikTokConnection))
    post = tiktok_post(db, storage, me, connection.affiliate_account_id)
    assert metrics.due_posts(db, 40, "tiktok") == []
    cell = an.get("/api/posts/board").json()["items"][0]["cells"]["tiktok"]
    assert (cell["source"], cell["hint"]) == ("manual_link", "Kết nối TikTok để tự cập nhật view")
    row = an.get(f"/api/posts/videos/{post.video_id}").json()["posts"][0]
    assert row["can_enter_views"] is True


def test_views_entered_by_hand_are_a_reading_and_set_the_marks(an, db, me, storage, fakes):
    account = AffiliateAccount(platform="tiktok", owner_id=me.id, name="@an", profile_url="https://www.tiktok.com/@an")
    db.add(account)
    db.commit()
    post = tiktok_post(db, storage, me, account.id, published_at=datetime.now(UTC) - timedelta(hours=30))
    at = post.published_at + timedelta(hours=24.5)
    response = an.post(f"/api/posts/{post.id}/metrics/manual", json={"views": 3000, "captured_at": at.isoformat()})
    assert response.status_code == 200
    snapshot = db.scalar(select(PostMetricSnapshot).where(PostMetricSnapshot.publication_id == post.id))
    assert snapshot.views == 3000 and snapshot.raw == {"manual": True}
    db.refresh(post)
    assert post.views_24h == 3000
    cell = an.get("/api/posts/board").json()["items"][0]["cells"]["tiktok"]
    assert cell["views"] == 3000


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"views": -1}, "không được âm"),
        ({"views": 1, "captured_at": "2099-01-01T00:00:00+00:00"}, "không hợp lệ"),
        ({"views": 1, "captured_at": "2020-01-01T00:00:00+00:00"}, "trước giờ đăng"),
    ],
)
def test_views_entered_by_hand_are_checked(an, db, me, storage, body, message):
    account = AffiliateAccount(platform="tiktok", owner_id=me.id, name="@an", profile_url="https://www.tiktok.com/@an")
    db.add(account)
    db.commit()
    post = tiktok_post(db, storage, me, account.id)
    response = an.post(f"/api/posts/{post.id}/metrics/manual", json=body)
    assert response.status_code == 422 and message in response.json()["message"]


def test_only_a_tiktok_post_takes_views_by_hand(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    post = Publication(
        video_id=video.id,
        platform="youtube",
        source="manual_link",
        external_id="dQw4w9WgXcQ",
        status="published",
        published_at=datetime.now(UTC),
        created_by_id=me.id,
    )
    db.add(post)
    db.commit()
    assert an.post(f"/api/posts/{post.id}/metrics/manual", json={"views": 5}).status_code == 404
