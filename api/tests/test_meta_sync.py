"""Reels posted on a Page outside the app (Meta Business Suite): imported, matched, followed, and sorted out on
"Chưa khớp" ("Bài đăng" part 3: meta_sync.py, posts_board.unmatched_posts, routes_posts, routes_channels)."""

from datetime import UTC, datetime, timedelta

import pytest
from conftest import login, make_user, make_video
from fake_services import FACEBOOK_PAGE, FACEBOOK_TOKEN
from sqlalchemy import select

from reels_api import fanpages, meta_sync, metrics
from reels_api.models import AffiliateAccount, Publication


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


@pytest.fixture
def page(db, me):
    row = fanpages.save(db, FACEBOOK_PAGE, "Trang Dưỡng Sinh", FACEBOOK_TOKEN, me.id)
    row.owner_id = me.id
    db.commit()
    return row


def graph_time(hours_ago: float) -> str:
    return (datetime.now(UTC) - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%S+0000")


def reel(reel_id: str, description: str, hours_ago: float = 2, **fields) -> dict:
    return {
        "id": reel_id,
        "description": description,
        "created_time": graph_time(hours_ago),
        "length": 30.0,
        "picture": f"https://scontent.fb/{reel_id}.jpg",
        **fields,
    }


def rendered(db, storage, user, title, days_ago=1.0):
    video = make_video(db, storage, user, scene_count=1, title_text=title)
    video.mp4_key, video.rendered_at = f"videos/{video.id}/v.mp4", datetime.now(UTC) - timedelta(days=days_ago)
    video.mp4_seconds = 30.0
    db.commit()
    return video


def imported(db) -> list[Publication]:
    return list(db.scalars(select(Publication).where(Publication.source == "meta_suite").order_by(Publication.id)))


# --- The import ---


def test_new_reels_are_imported_matched_and_read_at_once(db, me, storage, fakes, page):
    video = rendered(db, storage, me, "5 MÓN GIÚP XƯƠNG CHẮC KHỎE")
    rendered(db, storage, me, "RAU MẦM TỐT CHO TIM")
    fakes.page_reels[FACEBOOK_PAGE] = [
        reel("901", "5 món giúp xương chắc khỏe #suckhoe"),
        reel("902", "Một clip khác hẳn, không có video nào giống", length=99.0),
        reel("903", "chưa đăng", published=False),
        reel("904", "quá cũ", hours_ago=31 * 24),
    ]
    assert meta_sync.sync_page(db, page) == 2
    matched, unmatched = imported(db)
    assert (matched.remote_id, matched.video_id, matched.match_status) == ("901", video.id, "confirmed")
    assert matched.match_score >= 0.85 and matched.published_at_source == "api" and matched.duration_sec == 30.0
    assert (unmatched.video_id, unmatched.match_status) == (None, "unmatched")
    assert unmatched.thumbnail_url == "https://scontent.fb/902.jpg" and unmatched.created_by_id == me.id
    assert page.last_synced_at is not None and page.sync_error is None
    # Both are read as soon as they are in, matched or not.
    assert {post.id for post in metrics.due_posts(db, 10)} == {matched.id, unmatched.id}


def test_a_reel_the_app_has_is_skipped(db, me, storage, fakes, page):
    video = rendered(db, storage, me, "VIDEO CỦA APP")
    db.add(
        Publication(
            video_id=video.id,
            platform="facebook",
            fanpage_id=page.id,
            status="published",
            remote_id="901",
            created_by_id=me.id,
        )
    )
    db.commit()
    fakes.page_reels[FACEBOOK_PAGE] = [reel("901", "VIDEO CỦA APP")]
    assert meta_sync.sync_page(db, page) == 0
    assert meta_sync.sync_page(db, page) == 0, "and again: an imported one is never imported twice"


def test_a_close_guess_is_suggested_not_confirmed(db, me, storage, fakes, page):
    first = rendered(db, storage, me, "5 MÓN GIÚP XƯƠNG CHẮC KHỎE")
    second = rendered(db, storage, me, "5 MÓN GIÚP XƯƠNG CHẮC KHỎE HƠN")
    fakes.page_reels[FACEBOOK_PAGE] = [reel("901", "5 món giúp xương chắc khỏe")]
    meta_sync.sync_page(db, page)
    (post,) = imported(db)
    assert post.match_status == "suggested" and post.video_id is None
    assert post.suggested_video_id in {first.id, second.id}, "two near-equal videos: none is taken by itself"


def test_pages_are_imported_hourly_or_when_asked_and_not_when_off(an, db, me, fakes, page):
    assert meta_sync.due_pages(db) == [page]
    page.sync_tried_at = datetime.now(UTC) - timedelta(minutes=30)
    db.commit()
    assert meta_sync.due_pages(db) == [], "imported half an hour ago"
    assert an.post(f"/api/channels/fanpage/{page.id}/sync-now").json() == {"asked": True}
    assert meta_sync.due_pages(db) == [page], "Đồng bộ ngay"
    page.sync_tried_at, page.sync_requested_at = datetime.now(UTC) - timedelta(hours=2), None
    db.commit()
    assert an.put(f"/api/channels/fanpage/{page.id}/sync", json={"enabled": False}).status_code == 200
    db.refresh(page)
    assert meta_sync.due_pages(db) == [], "off: only Đồng bộ ngay imports it"


def test_only_the_page_owner_turns_the_import_off(an, db, me, fakes, page, client):
    make_user(db, email="binh@doi.vn", name="Bình")
    login(client, "binh@doi.vn")
    assert client.put(f"/api/channels/fanpage/{page.id}/sync", json={"enabled": False}).status_code == 403


def test_a_failed_import_is_said_and_keeps_its_last_time(db, me, fakes, page):
    fakes.page_reels_error = True
    assert meta_sync.sync_page(db, page) == 0
    assert page.sync_error and page.last_synced_at is None and page.sync_tried_at is not None


# --- "Chưa khớp" ---


def unmatched_post(db, page, me, **fields) -> Publication:
    post = Publication(
        platform="facebook",
        fanpage_id=page.id,
        status="published",
        source="meta_suite",
        remote_id=fields.pop("remote_id", "777"),
        external_id=fields.pop("external_id", "777"),
        caption="Một reel đăng ngoài app",
        published_at=datetime.now(UTC) - timedelta(hours=3),
        created_by_id=me.id,
        **({"match_status": "unmatched"} | fields),
    )
    db.add(post)
    db.commit()
    return post


def test_the_tab_lists_imported_reels_and_counts_them(an, db, me, storage, page):
    video = rendered(db, storage, me, "VIDEO GỢI Ý")
    post = unmatched_post(db, page, me, match_status="suggested", suggested_video_id=video.id, match_score=0.7)
    rows = an.get("/api/posts/unmatched").json()
    assert [(row["id"], row["suggested"]["id"], row["suggested"]["score"]) for row in rows] == [(post.id, video.id, 70)]
    board = an.get("/api/posts/board").json()
    assert board["counts"]["unmatched"] == 1
    assert an.get("/api/posts/board", params={"tab": "unmatched"}).json()["items"] == []


def test_confirm_all_takes_each_suggestion(an, db, me, storage, page):
    video = rendered(db, storage, me, "VIDEO GỢI Ý")
    suggested = unmatched_post(db, page, me, match_status="suggested", suggested_video_id=video.id)
    alone = unmatched_post(db, page, me, remote_id="778", external_id="778")
    result = an.post("/api/posts/unmatched/confirm", json={"post_ids": [suggested.id, alone.id]}).json()
    assert result == {"confirmed": 1}
    db.refresh(suggested)
    db.refresh(alone)
    assert (suggested.video_id, suggested.match_status) == (video.id, "confirmed")
    assert alone.video_id is None and alone.match_status == "unmatched"


def test_choose_another_video_then_unmatch(an, db, me, storage, page):
    video = rendered(db, storage, me, "VIDEO KHÁC")
    post = unmatched_post(db, page, me)
    assert an.patch(f"/api/posts/{post.id}", json={"video_id": video.id}).status_code == 200
    db.refresh(post)
    assert (post.video_id, post.match_status) == (video.id, "confirmed")
    cell = an.get("/api/posts/board").json()["items"][0]["cells"]["facebook"]
    assert cell["source"] == "meta_suite"
    assert an.patch(f"/api/posts/{post.id}", json={"video_id": None}).status_code == 200
    db.refresh(post)
    assert (post.video_id, post.match_status) == (None, "unmatched")


def test_external_is_a_row_of_its_own_and_ignored_is_hidden_and_not_read(an, db, me, page):
    external = unmatched_post(db, page, me)
    ignored = unmatched_post(db, page, me, remote_id="778", external_id="778")
    assert an.patch(f"/api/posts/{external.id}", json={"match_status": "external"}).status_code == 200
    assert an.patch(f"/api/posts/{ignored.id}", json={"match_status": "ignored"}).status_code == 200
    board = an.get("/api/posts/board").json()
    (row,) = board["items"]
    assert row["video"]["external"] is True and row["video"]["id"] is None
    assert row["video"]["name"] == "Một reel đăng ngoài app"
    assert row["cells"]["facebook"]["state"] == "published"
    assert board["counts"]["unmatched"] == 0
    assert ignored.id not in [post.id for post in metrics.due_posts(db, 10)]
    assert external.id in [post.id for post in metrics.due_posts(db, 10)]


def test_a_post_with_its_video_cannot_be_marked_external(an, db, me, storage, page):
    video = rendered(db, storage, me, "VIDEO")
    post = unmatched_post(db, page, me, video_id=video.id, match_status="confirmed")
    assert an.patch(f"/api/posts/{post.id}", json={"match_status": "ignored"}).status_code == 422


def test_an_imported_reel_is_removed_by_its_page_owner(an, db, me, page):
    post = unmatched_post(db, page, me)
    assert an.delete(f"/api/posts/{post.id}").status_code == 200
    assert db.get(Publication, post.id) is None


def test_a_pasted_link_may_be_a_video_of_its_own(an, db, me, fakes):
    account = AffiliateAccount(
        platform="tiktok", owner_id=me.id, name="@anngon", profile_url="https://www.tiktok.com/@anngon"
    )
    db.add(account)
    db.commit()
    item = {
        "url": "https://www.tiktok.com/@anngon/video/7301234567890123456",
        "external": True,
        "channel_id": account.id,
    }
    assert an.post("/api/posts/links", json={"items": [item]}).status_code == 200
    post = db.scalar(select(Publication))
    assert (post.video_id, post.match_status, post.source) == (None, "external", "manual_link")
    (row,) = an.get("/api/posts/board").json()["items"]
    assert row["video"]["external"] is True and row["cells"]["tiktok"]["state"] == "published"
