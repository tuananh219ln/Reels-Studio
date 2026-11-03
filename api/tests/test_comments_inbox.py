""" "Bình luận" (comments_inbox.py, routes_comments.py): reading visitors' comments, answering and hiding them."""

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


def test_load_new_comments_makes_every_followed_post_due(an, db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    comments_inbox.read(db, post)
    assert an.post(f"{URL}/refresh").status_code == 200
    assert reads(db) == [post.id]


# Answering


def test_a_reply_is_sent_once_by_the_worker(an, db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    visitor = fakes.add_visitor_comment(post.remote_id, "Mua nồi ở đâu ạ?")
    comments_inbox.read(db, post)
    (comment,) = stored(db)

    row = an.post(f"{URL}/{comment.id}/reply", json={"text": "  Link trong bình luận ghim ạ  "}).json()
    assert row["state"] == "sending" and row["reply_text"] == "Link trong bình luận ghim ạ"
    assert fakes.facebook_comments[visitor]["message"] == "Mua nồi ở đâu ạ?", "a request never calls Facebook"

    (due,) = comments_inbox.due_sends(db)
    comments_inbox.send(db, due)
    replies = [c for c in fakes.facebook_comments.values() if c["object"] == visitor]
    assert [reply["message"] for reply in replies] == ["Link trong bình luận ghim ạ"]
    assert comments_inbox.due_sends(db) == []
    assert open_list(an) == [], "an answered comment leaves the open list"
    (row,) = an.get(f"{URL}?state=all").json()["comments"]
    assert row["state"] == "answered" and row["handled_by"] == me.name
    refused = an.post(f"{URL}/{comment.id}/reply", json={"text": "Lần nữa"})
    assert refused.status_code == 409


def test_a_failed_reply_stays_open_with_its_reason_and_is_not_resent_by_itself(an, db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    fakes.add_visitor_comment(post.remote_id, "Hỏi chút ạ")
    comments_inbox.read(db, post)
    (comment,) = stored(db)
    an.post(f"{URL}/{comment.id}/reply", json={"text": "Dạ"})
    fakes.facebook_comment_refused = True
    comments_inbox.send(db, comments_inbox.due_sends(db)[0])
    assert comments_inbox.due_sends(db) == []
    (row,) = open_list(an)
    assert row["state"] == "open" and "pages_manage_engagement" in row["error"]


def test_a_reply_whose_answer_was_lost_is_not_written_twice_on_retry(an, db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    visitor = fakes.add_visitor_comment(post.remote_id, "Hỏi chút ạ")
    comments_inbox.read(db, post)
    (comment,) = stored(db)
    an.post(f"{URL}/{comment.id}/reply", json={"text": "Dạ cô"})
    fakes.facebook_comment_replies_lost = 1
    comments_inbox.send(db, comments_inbox.due_sends(db)[0])
    an.post(f"{URL}/{comment.id}/reply", json={"text": "Dạ cô"})
    comments_inbox.send(db, comments_inbox.due_sends(db)[0])
    assert [c["message"] for c in fakes.facebook_comments.values() if c["object"] == visitor] == ["Dạ cô"]
    assert stored(db)[0].reply_id


def test_an_empty_or_long_reply_is_refused(an, db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    fakes.add_visitor_comment(post.remote_id, "Hỏi")
    comments_inbox.read(db, post)
    (comment,) = stored(db)
    assert an.post(f"{URL}/{comment.id}/reply", json={"text": "  "}).status_code == 422
    assert an.post(f"{URL}/{comment.id}/reply", json={"text": "x" * 2001}).status_code == 422
    assert an.post(f"{URL}/999999/reply", json={"text": "Dạ"}).status_code == 404


# Hiding and setting aside


def test_hide_sends_once_and_the_comment_leaves_the_list(an, db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    spam = fakes.add_visitor_comment(post.remote_id, "Kiếm tiền online inbox mình")
    comments_inbox.read(db, post)
    (comment,) = stored(db)
    assert an.post(f"{URL}/{comment.id}/hide").json()["state"] == "sending"
    comments_inbox.send(db, comments_inbox.due_sends(db)[0])
    assert fakes.facebook_comments[spam]["hidden"] is True
    assert open_list(an) == [] and comments_inbox.due_sends(db) == []


def test_dismiss_sets_a_comment_aside_and_back(an, db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    fakes.add_visitor_comment(post.remote_id, "❤️")
    comments_inbox.read(db, post)
    (comment,) = stored(db)
    assert an.post(f"{URL}/{comment.id}/dismiss", json={"dismissed": True}).json()["state"] == "dismissed"
    assert open_list(an) == []
    an.post(f"{URL}/{comment.id}/dismiss", json={"dismissed": False})
    (row,) = open_list(an)
    assert row["post"]["fanpage"] == "Trang Dưỡng Sinh" and row["post"]["reel_url"].endswith(post.remote_id)


def test_comments_need_a_login(client):
    assert client.get(URL).status_code == 401


def test_the_worker_round_sends_and_reads(committed, fakes, tmp_path):  # noqa: F811
    from reels_api.storage import DirectoryStorage

    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    with committed() as db:
        post = add_post(db, storage, user, fakes)
        fakes.add_visitor_comment(post.remote_id, "Hay quá")
    comments_inbox.run_round(committed)
    with committed() as db:
        assert [row.message for row in db.scalars(select(PageComment))] == ["Hay quá"]
        db.execute(PageComment.__table__.delete())
        db.commit()
