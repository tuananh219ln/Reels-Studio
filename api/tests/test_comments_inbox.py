"""Visitors' comments (comments_inbox.py, routes_comments.py): the worker reads them for an article that answers one.
The "Bình luận" page that answered, hid and set them aside is gone (decisions 2026-11-10)."""

from datetime import UTC, datetime, timedelta

import pytest
from conftest import login, make_user, make_video
from fake_services import FACEBOOK_PAGE, FACEBOOK_TOKEN
from sqlalchemy import select
from worker_helpers import add_user, committed  # noqa: F401  (fixtures)

from reels_api import comments_inbox, fanpages
from reels_api.models import Fanpage, PageComment, Publication

URL = "/api/comments"


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def add_post(db, storage, user, fakes, live_days_ago: float = 1, **fields) -> Publication:
    page = db.scalar(select(Fanpage).where(Fanpage.page_id == FACEBOOK_PAGE))
    if page is None:
        page = fanpages.save(db, FACEBOOK_PAGE, "Trang Dưỡng Sinh", FACEBOOK_TOKEN, user.id)
        db.flush()
    video = make_video(db, storage, user, scene_count=1)
    remote_id = f"reel-{video.id}"
    fakes.reels[remote_id] = {"uploaded": True, "state": "published"}
    fields = {"status": "published", "published_at": datetime.now(UTC) - timedelta(days=live_days_ago)} | fields
    post = Publication(
        video_id=video.id, platform="facebook", created_by_id=user.id, fanpage_id=page.id, remote_id=remote_id, **fields
    )
    db.add(post)
    db.commit()
    return post


def reads(db) -> list[int]:
    return [post.id for post in comments_inbox.due_reads(db, limit=100)]


def stored(db) -> list[PageComment]:
    db.expire_all()
    return list(db.scalars(select(PageComment).order_by(PageComment.id)))


def open_list(an) -> list[dict]:
    return an.get(URL).json()["comments"]


# Reading


def test_a_live_post_of_the_last_two_weeks_is_read_every_half_hour(db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    add_post(db, storage, me, fakes, live_days_ago=15)
    add_post(db, storage, me, fakes, status="scheduled", scheduled_at=datetime.now(UTC) + timedelta(hours=1))
    assert reads(db) == [post.id]
    comments_inbox.read(db, post)
    assert reads(db) == []
    post.comments_read_at = datetime.now(UTC) - timedelta(minutes=31)
    db.commit()
    assert reads(db) == [post.id]


def test_reading_keeps_visitors_comments_but_not_the_pages_own(db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    fakes.add_visitor_comment(post.remote_id, "Canh bí đao nấu với gì ngon ạ?", "Cô Lan")
    fakes._comment(post.remote_id, {"access_token": FACEBOOK_TOKEN, "message": "Link sản phẩm"}, True)
    comments_inbox.read(db, post)
    (comment,) = stored(db)
    assert (comment.author_name, comment.message, comment.answered) == (
        "Cô Lan",
        "Canh bí đao nấu với gì ngon ạ?",
        False,
    )
    assert comment.created_at == datetime(2026, 11, 3, 7, 0, tzinfo=UTC)


def test_reading_again_adds_new_comments_and_sees_answers_made_on_facebook(db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    first = fakes.add_visitor_comment(post.remote_id, "Hay quá")
    comments_inbox.read(db, post)
    fakes._comment(first, {"access_token": FACEBOOK_TOKEN, "message": "Cảm ơn cô"}, True)
    fakes.add_visitor_comment(post.remote_id, "Mua ở đâu ạ?")
    comments_inbox.read(db, post)
    assert [(row.message, row.answered) for row in stored(db)] == [("Hay quá", True), ("Mua ở đâu ạ?", False)]


def test_a_reading_refused_is_recorded_and_shown(an, db, me, storage, fakes):
    fakes.facebook_comment_refused = True
    post = add_post(db, storage, me, fakes)
    comments_inbox.read(db, post)
    assert "pages_read_user_content" in post.comments_error
    assert reads(db) == [], "a failed reading waits like any other"
    assert an.get(URL).json()["read_errors"] == [{"fanpage": "Trang Dưỡng Sinh", "error": post.comments_error}]


def test_a_live_reel_whose_comments_cannot_be_read_blames_the_token_not_the_reel(db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    fakes.facebook_comments_unreadable.add(post.remote_id)
    comments_inbox.read(db, post)
    assert "không còn reel" not in post.comments_error
    assert "token" in post.comments_error and "Kết nối Fanpage" in post.comments_error


def test_a_reel_facebook_no_longer_has_is_named_gone(db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    add_post(db, storage, me, fakes)  # another reel the token still reads: what makes "lost" mean deleted
    fakes.reels[post.remote_id]["lost"] = True
    comments_inbox.read(db, post)
    assert post.comments_error == "Facebook không còn reel này"


def test_answering_hiding_and_setting_aside_are_gone(an, db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    fakes.add_visitor_comment(post.remote_id, "Mua ở đâu ạ?")
    comments_inbox.read(db, post)
    (comment,) = stored(db)
    for path, body in (("reply", {"text": "Dạ"}), ("hide", None), ("dismiss", {"dismissed": True})):
        assert an.post(f"{URL}/{comment.id}/{path}", json=body).status_code in (404, 405), path
    for path in ("refresh", "freshen"):
        assert an.post(f"{URL}/{path}").status_code in (404, 405), path


def test_the_comment_list_stays_for_an_article_that_answers_one(an, db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    fakes.add_visitor_comment(post.remote_id, "Canh bí đao nấu với gì ngon ạ?", "Cô Lan")
    comments_inbox.read(db, post)
    (row,) = an.get(f"{URL}?state=all").json()["comments"]
    assert (row["author"], row["message"]) == ("Cô Lan", "Canh bí đao nấu với gì ngon ạ?")
    assert row["post"]["fanpage"] == "Trang Dưỡng Sinh" and row["post"]["reel_url"].endswith(post.remote_id)


def test_comments_need_a_login(client):
    assert client.get(URL).status_code == 401


def test_the_worker_round_reads_and_sends_nothing(committed, fakes, tmp_path):  # noqa: F811
    from reels_api.storage import DirectoryStorage

    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    with committed() as db:
        post = add_post(db, storage, user, fakes)
        visitor = fakes.add_visitor_comment(post.remote_id, "Hay quá")
    comments_inbox.run_round(committed)
    with committed() as db:
        (row,) = db.scalars(select(PageComment))
        assert row.message == "Hay quá"
        # A reply asked for on the old "Bình luận" page, before it went, is never sent.
        row.reply_text, row.reply_requested_at = "Cảm ơn cô", datetime.now(UTC)
        db.commit()
    comments_inbox.run_round(committed)
    assert [c for c in fakes.facebook_comments.values() if c["object"] == visitor] == []
    with committed() as db:
        db.execute(PageComment.__table__.delete())
        db.commit()
