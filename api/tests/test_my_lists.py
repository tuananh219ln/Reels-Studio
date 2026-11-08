"""Every list can show a member's own work first (brief docs/specs/chu-thuong-ca-nhan-hoa, the rule over part B): the
lists say whose each row is, and the paged or capped ones (jobs, comments) filter on the server."""

from datetime import UTC, datetime

import pytest
from conftest import first_topic, login, make_user, make_video
from test_comments_inbox import add_post
from worker_helpers import add_user, committed  # noqa: F401  (fixtures)

from reels_api import fanpages
from reels_api.models import Job, PageComment, Publication


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def binh(db):
    return make_user(db, email="binh@doi.vn", name="Trần Bình")


@pytest.fixture
def an(client, me):
    login(client)
    return client


def test_videos_say_who_made_them(an, db, storage, me, binh):
    mine = make_video(db, storage, me, scene_count=1)
    theirs = make_video(db, storage, binh, scene_count=1)
    rows = {row["id"]: row["created_by_id"] for row in an.get("/api/videos").json()}
    assert rows == {mine.id: me.id, theirs.id: binh.id}


def test_articles_say_who_made_them(an, db, me):
    made = an.post("/api/articles", json={"knowledge_topic_id": first_topic(db).id, "kind": "kien_thuc", "topic": "x"})
    (row,) = an.get("/api/articles").json()["articles"]
    assert row["id"] == made.json()["id"] and row["created_by_id"] == me.id


def test_posts_say_who_posted_them_and_whose_page_they_are_on(an, db, storage, me, binh, fakes):
    post = add_post(db, storage, binh, fakes)
    (row,) = an.get("/api/posts").json()
    assert (row["created_by_id"], row["fanpage_owner_id"]) == (binh.id, binh.id)
    db.get(type(post.fanpage), post.fanpage_id).owner_id = me.id
    db.commit()
    (row,) = an.get("/api/posts").json()
    assert (row["created_by_id"], row["fanpage_owner_id"]) == (binh.id, me.id)


def test_my_jobs_are_those_i_started(an, db, storage, me, binh):
    mine = make_video(db, storage, me, scene_count=1)
    theirs = make_video(db, storage, binh, scene_count=1)
    db.add_all(
        [
            Job(video_id=mine.id, kind="render", status="done", created_by_id=me.id),
            Job(video_id=theirs.id, kind="render", status="done", created_by_id=binh.id),
        ]
    )
    db.commit()

    every = an.get("/api/jobs").json()
    assert sorted(row["created_by_id"] for row in every) == sorted([me.id, binh.id])
    assert [row["video_id"] for row in an.get("/api/jobs?whose=mine").json()] == [mine.id]
    assert an.get("/api/jobs?whose=nobody").status_code == 422


def comment_on(db, post: Publication, remote_id: str) -> None:
    db.add(PageComment(publication_id=post.id, remote_id=remote_id, message="Hay quá", created_at=datetime.now(UTC)))
    db.commit()


def test_my_comments_are_those_on_my_posts_or_my_pages(an, db, storage, me, binh, fakes):
    on_my_page = add_post(db, storage, binh, fakes)  # Bình posts on the one Page, mine
    on_my_page.fanpage.owner_id = me.id
    other = fanpages.save(db, "999", "Trang của Bình", "token-2", binh.id)
    db.flush()
    theirs = add_post(db, storage, binh, fakes)
    theirs.fanpage_id = other.id
    my_post = add_post(db, storage, me, fakes)
    my_post.fanpage_id = other.id
    db.commit()
    comment_on(db, on_my_page, "c1")
    comment_on(db, theirs, "c2")
    comment_on(db, my_post, "c3")

    every = an.get("/api/comments?state=all").json()["comments"]
    assert len(every) == 3
    mine = an.get("/api/comments?state=all&whose=mine").json()["comments"]
    assert sorted(row["post"]["id"] for row in mine) == sorted([on_my_page.id, my_post.id])
    assert an.get("/api/comments?whose=nobody").status_code == 422
