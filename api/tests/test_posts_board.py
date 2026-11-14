"""The "Bài đăng" board (posts_board.py, routes_posts.py, routes_channels.py): one row per rendered video with a cell
per platform, "Tải MP4" waiting for a link, pasting links, and the channels they are recorded on."""

from datetime import UTC, datetime, timedelta

import pytest
from conftest import login, make_user, make_video
from fake_services import FACEBOOK_PAGE, FACEBOOK_TOKEN
from sqlalchemy import select

from reels_api import fanpages, metrics
from reels_api.models import AffiliateAccount, Channel, PostMetrics, PostMetricSnapshot, Publication

TIKTOK_LINK = "https://www.tiktok.com/@anngon/video/7301234567890123456"
SHORTS_LINK = "https://www.youtube.com/shorts/dQw4w9WgXcQ"


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def rendered(db, storage, user, title="5 MÓN GIÚP XƯƠNG CHẮC KHỎE", days_ago=1.0):
    video = make_video(db, storage, user, scene_count=1, title_text=title)
    video.mp4_key, video.rendered_at = f"videos/{video.id}/video-x.mp4", datetime.now(UTC) - timedelta(days=days_ago)
    db.commit()
    return video


def page_of(db, user):
    page = db.scalar(select(fanpages.Fanpage).where(fanpages.Fanpage.page_id == FACEBOOK_PAGE))
    if page is None:
        page = fanpages.save(db, FACEBOOK_PAGE, "Trang Dưỡng Sinh", FACEBOOK_TOKEN, user.id)
        page.owner_id = user.id
        db.commit()
    return page


def tiktok_account(db, user, handle="anngon"):
    account = AffiliateAccount(
        platform="tiktok", owner_id=user.id, name=f"@{handle}", profile_url=f"https://www.tiktok.com/@{handle}"
    )
    db.add(account)
    db.commit()
    return account


def youtube_channel(db, user, handle="@anngon"):
    channel = Channel(
        platform="youtube",
        handle=handle,
        name="Ăn Ngon",
        url=f"https://www.youtube.com/{handle}",
        created_by_id=user.id,
    )
    db.add(channel)
    db.commit()
    return channel


def board(an, **params):
    response = an.get("/api/posts/board", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def tiktok_posted(an, video) -> bool:
    """The video list's flag, which the video page's TikTok card reads too."""
    return next(row for row in an.get("/api/videos").json() if row["id"] == video.id)["tiktok_posted"]


def row_of(result, video):
    return next(item for item in result["items"] if item["video"]["id"] == video.id)


# --- The board ---


def test_a_rendered_video_with_no_post_is_unposted(an, db, me, storage):
    old = rendered(db, storage, me, title="VIDEO CŨ", days_ago=5)
    new = rendered(db, storage, me, title="VIDEO MỚI", days_ago=1)
    make_video(db, storage, me, scene_count=1, title_text="CHƯA RENDER")
    result = board(an, tab="unposted")
    assert [item["video"]["name"] for item in result["items"]] == ["VIDEO CŨ", "VIDEO MỚI"], "oldest render first"
    assert result["counts"]["unposted"] == 2 and result["counts"]["all"] == 2
    assert row_of(result, old)["video"]["unposted_days"] == 5, "over 3 days unposted says so"
    assert row_of(result, new)["video"]["unposted_days"] is None
    assert row_of(result, new)["cells"] == {"facebook": None, "tiktok": None, "youtube": None}


def test_a_published_facebook_post_shows_its_views_and_leaves_unposted(an, db, me, storage):
    video = rendered(db, storage, me)
    page = page_of(db, me)
    at = datetime.now(UTC) - timedelta(days=3)
    for remote, views, mark in (("111", 4000, 3500), ("222", 2789, 2420)):
        post = Publication(
            video_id=video.id,
            platform="facebook",
            fanpage_id=page.id,
            status="published",
            published_at=at,
            remote_id=remote,
            created_by_id=me.id,
        )
        db.add(post)
        db.flush()
        db.add(PostMetricSnapshot(publication_id=post.id, captured_at=at + timedelta(days=2), views=views))
        db.add(PostMetrics(publication_id=post.id, window="48h", views=mark, measured_at=at + timedelta(days=2)))
    db.commit()
    result = board(an, tab="published")
    cell = row_of(result, video)["cells"]["facebook"]
    assert (cell["state"], cell["views"], cell["views_48h"], cell["channel_label"]) == (
        "published",
        6789,
        5920,
        "2 Page",
    )
    assert cell["source"] == "app_api"
    assert row_of(result, video)["total_views"] == 6789
    assert result["counts"]["unposted"] == 0 and result["counts"]["published"] == 1


def test_download_for_tiktok_waits_for_a_link_and_goes_stale_after_a_day(an, db, me, storage):
    video = rendered(db, storage, me)
    assert an.post("/api/posts/pending", json={"video_id": video.id, "platform": "tiktok"}).json() == {"created": True}
    assert an.post("/api/posts/pending", json={"video_id": video.id, "platform": "tiktok"}).json() == {"created": False}
    result = board(an, tab="pending_link")
    cell = row_of(result, video)["cells"]["tiktok"]
    assert cell["state"] == "pending_link" and cell["pending_stale"] is False
    assert result["counts"]["unposted"] == 0, "waiting for a link is no longer unposted"
    post = db.scalar(select(Publication).where(Publication.video_id == video.id, Publication.platform == "tiktok"))
    post.mp4_downloaded_at = datetime.now(UTC) - timedelta(hours=25)
    db.commit()
    assert row_of(board(an), video)["cells"]["tiktok"]["pending_stale"] is True
    # Not out yet: the video page does not list it as a TikTok post.
    assert tiktok_posted(an, video) is False


def test_pending_needs_tiktok_or_youtube_and_an_mp4(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    assert an.post("/api/posts/pending", json={"video_id": video.id, "platform": "facebook"}).status_code == 422
    response = an.post("/api/posts/pending", json={"video_id": video.id, "platform": "youtube"})
    assert response.status_code == 422 and "chưa render" in response.json()["message"]


def test_cancelling_a_wait_returns_the_video_to_unposted(an, db, me, storage):
    video = rendered(db, storage, me)
    an.post("/api/posts/pending", json={"video_id": video.id, "platform": "youtube"})
    post = db.scalar(select(Publication).where(Publication.video_id == video.id))
    assert an.patch(f"/api/posts/{post.id}", json={"status": "cancelled"}).status_code == 200
    result = board(an, tab="unposted")
    assert row_of(result, video)["cells"]["youtube"] is None


def test_missing_on_and_platform_filters(an, db, me, storage):
    on_tiktok = rendered(db, storage, me, title="CÓ TIKTOK")
    nowhere = rendered(db, storage, me, title="CHƯA ĐĂNG")
    an.post("/api/posts/pending", json={"video_id": on_tiktok.id, "platform": "tiktok"})
    missing = board(an, missing_on="tiktok")
    assert [item["video"]["id"] for item in missing["items"]] == [nowhere.id]
    # With TikTok chosen, a video waiting on TikTok is not unposted; with YouTube chosen, it is.
    assert board(an, platform="tiktok")["counts"]["unposted"] == 1
    assert board(an, platform="youtube")["counts"]["unposted"] == 2


def test_owner_and_search_filters(an, db, me, storage):
    mine = rendered(db, storage, me, title="CỦA TÔI")
    other = make_user(db, email="binh@doi.vn", name="Bình")
    rendered(db, storage, other, title="CỦA BÌNH")
    assert [item["video"]["id"] for item in board(an, owner="me")["items"]] == [mine.id]
    assert [item["video"]["name"] for item in board(an, q="cua binh")["items"]] == ["CỦA BÌNH"]


def test_an_unknown_tab_is_refused(an):
    assert an.get("/api/posts/board", params={"tab": "x"}).status_code == 422


# --- Pasting links ---


def test_a_tiktok_link_on_a_known_account_matches_its_video(an, db, me, storage, fakes):
    video = rendered(db, storage, me)
    rendered(db, storage, me, title="RAU MẦM TỐT CHO TIM")
    tiktok_account(db, me)
    fakes.oembed[TIKTOK_LINK] = {"title": "5 món giúp xương chắc khỏe #suckhoe", "author_unique_id": "anngon"}
    items = an.post("/api/posts/links/preview", json={"urls": [TIKTOK_LINK + "?is_from_webapp=1"]}).json()["items"]
    row = items[0]
    assert (row["platform"], row["url"], row["result"]) == ("tiktok", TIKTOK_LINK, "matched")
    assert row["video"]["id"] == video.id and row["channel"]["name"] == "@anngon"
    assert row["message"] == f"Khớp {row['score']}%" and row["score"] >= 85


def test_preview_says_what_is_wrong_with_each_line(an, db, me, storage, fakes):
    rendered(db, storage, me)
    youtube_channel(db, me)
    fakes.oembed[SHORTS_LINK] = {"title": "khác hẳn", "author_url": "https://www.youtube.com/@anngon"}
    urls = [
        "https://www.tiktok.com/@kenhla/video/7301234567890123456",  # an account the team has not added
        "https://youtu.be/dQw4w9WgXcQ",
        SHORTS_LINK,  # the same post again
        "https://www.tiktok.com/@kenhla",
    ]
    fakes.oembed["https://www.tiktok.com/@kenhla/video/7301234567890123456"] = {
        "title": "x",
        "author_unique_id": "kenhla",
    }
    items = an.post("/api/posts/links/preview", json={"urls": urls}).json()["items"]
    assert [(row["result"], row["message"]) for row in items] == [
        ("unknown_channel", "Kênh chưa khai báo"),
        ("choose", "Cần chọn tay"),
        ("duplicate", "Trùng với link ở dòng trên"),
        ("invalid", "Link không hợp lệ"),
    ]
    assert items[1]["channel"]["name"] == "Ăn Ngon"


def test_a_removed_post_is_unreachable(an, db, me, storage, fakes):
    tiktok_account(db, me)
    fakes.oembed_gone.add(TIKTOK_LINK)
    items = an.post("/api/posts/links/preview", json={"urls": [TIKTOK_LINK]}).json()["items"]
    assert (items[0]["result"], items[0]["message"]) == ("unreachable", "Không truy cập được")


def test_saving_fills_the_wait_then_the_same_link_is_already_there(an, db, me, storage, fakes):
    video = rendered(db, storage, me)
    account = tiktok_account(db, me)
    an.post("/api/posts/pending", json={"video_id": video.id, "platform": "tiktok"})
    item = {"url": TIKTOK_LINK, "video_id": video.id, "channel_id": account.id}
    assert an.post("/api/posts/links", json={"items": [item]}).json()["saved"] == 1
    posts = db.scalars(select(Publication).where(Publication.video_id == video.id)).all()
    assert len(posts) == 1, "the post waiting for its link got it, no second post"
    post = posts[0]
    assert (post.status, post.source, post.external_id, post.affiliate_account_id) == (
        "published",
        "manual_link",
        "7301234567890123456",
        account.id,
    )
    assert post.published_at_source is None, "a time not typed: the platform's replaces it once read"
    cell = row_of(board(an), video)["cells"]["tiktok"]
    assert (cell["state"], cell["source"], cell["channel_label"]) == ("published", "manual_link", "@anngon")
    # Pasted again: refused on saving, and said so in the preview with the video it is on.
    again = an.post("/api/posts/links", json={"items": [item]})
    assert again.status_code == 409 and "đã có" in again.json()["message"]
    fakes.oembed[TIKTOK_LINK] = {"title": "x", "author_unique_id": "anngon"}
    row = an.post("/api/posts/links/preview", json={"urls": [TIKTOK_LINK]}).json()["items"][0]
    assert row["result"] == "duplicate" and row["existing_video"]["id"] == video.id
    # Now on the video page as a TikTok post.
    assert tiktok_posted(an, video) is True


def test_a_link_of_another_tiktok_account_is_refused(an, db, me, storage):
    video = rendered(db, storage, me)
    other = tiktok_account(db, me, handle="kenhkhac")
    item = {"url": TIKTOK_LINK, "video_id": video.id, "channel_id": other.id}
    response = an.post("/api/posts/links", json={"items": [item]})
    assert response.status_code == 422 and "không thuộc kênh" in response.json()["message"]


def test_a_reel_the_app_posted_is_already_there(an, db, me, storage, fakes):
    video = rendered(db, storage, me)
    page = page_of(db, me)
    db.add(
        Publication(
            video_id=video.id,
            platform="facebook",
            fanpage_id=page.id,
            status="published",
            remote_id="1234567890123",
            created_by_id=me.id,
        )
    )
    db.commit()
    row = an.post("/api/posts/links/preview", json={"urls": ["https://www.facebook.com/reel/1234567890123"]}).json()
    assert row["items"][0]["result"] == "duplicate"


def test_a_facebook_link_is_recorded_on_my_page_and_read_at_once(an, db, me, storage):
    video = rendered(db, storage, me)
    page = page_of(db, me)
    item = {"url": "https://www.facebook.com/reel/99887766554", "video_id": video.id, "channel_id": page.id}
    assert an.post("/api/posts/links", json={"items": [item]}).status_code == 200
    post = db.scalar(select(Publication).where(Publication.video_id == video.id))
    assert (post.remote_id, post.fanpage_id, post.source) == ("99887766554", page.id, "manual_link")
    assert post.metrics_requested_at is not None


def test_a_line_wrong_saves_nothing(an, db, me, storage):
    video = rendered(db, storage, me)
    account = tiktok_account(db, me)
    items = [
        {"url": TIKTOK_LINK, "video_id": video.id, "channel_id": account.id},
        {"url": "https://example.com/x", "video_id": video.id, "channel_id": account.id},
    ]
    response = an.post("/api/posts/links", json={"items": items})
    assert response.status_code == 422 and response.json()["message"].startswith("Dòng 2:")
    assert db.scalars(select(Publication)).all() == []


def test_a_recorded_post_is_edited_and_removed_only_by_whoever_recorded_it(an, db, me, storage, client):
    video = rendered(db, storage, me)
    channel = youtube_channel(db, me)
    item = {"url": SHORTS_LINK, "video_id": video.id, "channel_id": channel.id}
    post_id = an.post("/api/posts/links", json={"items": [item]}).json()["post_ids"][0]
    edited = an.patch(f"/api/posts/{post_id}", json={"url": "https://youtu.be/abcdefghijk"})
    assert edited.status_code == 200
    assert db.get(Publication, post_id).external_id == "abcdefghijk"
    wrong = an.patch(f"/api/posts/{post_id}", json={"url": TIKTOK_LINK})
    assert wrong.status_code == 422 and "không phải link YouTube" in wrong.json()["message"]
    make_user(db, email="binh@doi.vn", name="Bình")
    login(client, "binh@doi.vn")
    assert client.delete(f"/api/posts/{post_id}").status_code == 403
    login(client)
    assert client.delete(f"/api/posts/{post_id}").status_code == 200
    assert db.get(Publication, post_id) is None


def test_an_opened_row_lists_every_post_with_captions(an, db, me, storage):
    video = rendered(db, storage, me)
    an.post("/api/posts/pending", json={"video_id": video.id, "platform": "tiktok"})
    result = an.get(f"/api/posts/videos/{video.id}").json()
    assert [(post["platform"], post["state"]) for post in result["posts"]] == [("tiktok", "pending_link")]
    assert result["missing"] == ["facebook", "youtube"]
    assert set(result["captions"]) == {"facebook", "tiktok", "youtube"}
    assert result["mp4_download_url"].startswith(f"/api/videos/{video.id}/video.mp4")


# --- Channels ---


def test_channels_are_added_from_their_link(an, db, me):
    added = an.post("/api/channels", json={"url": "https://www.tiktok.com/@AnNgon?lang=vi"})
    assert added.status_code == 201 and added.json()["name"] == "@anngon"
    assert an.post("/api/channels", json={"url": "tiktok.com/@anngon"}).status_code == 409
    youtube = an.post("/api/channels", json={"url": "https://www.youtube.com/@AnNgon/shorts"})
    assert youtube.status_code == 201
    assert an.post("/api/channels", json={"url": "https://youtube.com/@anngon"}).status_code == 409
    by_id = an.post("/api/channels", json={"url": "https://www.youtube.com/channel/UCabcdefghijklmnopqrstuv"})
    assert by_id.status_code == 201
    assert an.post("/api/channels", json={"url": "https://example.com/@x"}).status_code == 422
    listed = an.get("/api/channels").json()
    assert [row["handle"] for row in listed["tiktok"]] == ["anngon"]
    assert sorted(row["handle"] for row in listed["youtube"]) == ["@anngon", "UCabcdefghijklmnopqrstuv"]
    channel = db.scalar(select(Channel).where(Channel.external_id == "UCabcdefghijklmnopqrstuv"))
    assert an.delete(f"/api/channels/youtube/{channel.id}").status_code == 200


# --- Snapshots ---


def test_every_facebook_reading_joins_the_time_series(db, me, storage, fakes):
    video = rendered(db, storage, me)
    page = page_of(db, me)
    post = Publication(
        video_id=video.id,
        platform="facebook",
        fanpage_id=page.id,
        status="published",
        published_at=datetime.now(UTC) - timedelta(hours=5),
        remote_id="1000",
        created_by_id=me.id,
    )
    db.add(post)
    db.commit()
    fakes.facebook_insights["1000"] = {"views": 54321, "shares": 120, "comments": 33, "reactions": 900}
    metrics.measure(db, post)
    metrics.measure(db, post)
    rows = db.scalars(select(PostMetricSnapshot).where(PostMetricSnapshot.publication_id == post.id)).all()
    assert len(rows) == 2
    assert (rows[0].views, rows[0].likes, rows[0].comments, rows[0].shares) == (54321, 900, 33, 120)
    assert 4.9 < rows[0].hours_since_publish < 5.1
