"""The affiliate comment the worker writes under a posted reel (post_comments.py): when, what it says, never twice."""

from datetime import UTC, datetime, timedelta

import pytest
from conftest import first_topic, login, make_user, make_video
from fake_services import FACEBOOK_PAGE, FACEBOOK_TOKEN
from sqlalchemy import select
from worker_helpers import add_user, committed  # noqa: F401  (fixtures)

from reels_api import fanpages, post_comments
from reels_api.models import AffiliateProduct, Fanpage, Publication, Scene, Video, VideoAffiliateProduct


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def ago(minutes: float) -> datetime:
    return datetime.now(UTC) - timedelta(minutes=minutes)


def add_post(db, storage, user, fakes, live_minutes_ago: float = 10, auto: bool = True, **fields) -> Publication:
    page = db.scalar(select(Fanpage).where(Fanpage.page_id == FACEBOOK_PAGE))
    if page is None:
        page = fanpages.save(db, FACEBOOK_PAGE, "Trang Dưỡng Sinh", FACEBOOK_TOKEN, user.id)
        db.flush()
    video = make_video(db, storage, user, scene_count=1)
    video.pinned_comment = "Món nào nhà bạn hay nấu nhất?"
    remote_id = f"reel-{video.id}"
    fakes.reels[remote_id] = {"uploaded": True, "state": "published"}
    fields = {"status": "published", "published_at": ago(live_minutes_ago)} | fields
    post = Publication(
        video_id=video.id,
        platform="facebook",
        created_by_id=user.id,
        fanpage_id=page.id,
        remote_id=remote_id,
        auto_comment=auto,
        **fields,
    )
    db.add(post)
    db.commit()
    return post


def attach(db, post: Publication, name: str = "Nồi hầm mini", status: str = "approved", **fields) -> AffiliateProduct:
    product = AffiliateProduct(
        knowledge_topic_id=first_topic(db).id,
        name=name,
        url=f"https://s.shopee.vn/{len(name)}",
        shop_name="Shop",
        shop_type="mall",
        rating=4.9,
        sold=1000,
        price=200000,
        commission_rate=8,
        status=status,
        created_by_id=post.created_by_id,
        **fields,
    )
    db.add(product)
    db.flush()
    db.add(VideoAffiliateProduct(video_id=post.video_id, product_id=product.id))
    db.commit()
    return product


def due(db) -> list[int]:
    return [post.id for post in post_comments.due_posts(db, limit=100)]


def comments_on(fakes, post: Publication) -> list[dict]:
    return [comment for comment in fakes.facebook_comments.values() if comment["object"] == post.remote_id]


# When a post is due


def test_a_live_post_made_with_auto_comment_is_due_after_a_moment(db, me, storage, fakes):
    fresh = add_post(db, storage, me, fakes, live_minutes_ago=0.5)
    ready = add_post(db, storage, me, fakes, live_minutes_ago=5)
    assert due(db) == [ready.id]
    assert fresh.id not in due(db)


def test_posts_made_without_auto_comment_or_before_it_existed_are_left_alone(db, me, storage, fakes):
    add_post(db, storage, me, fakes, auto=False)
    assert due(db) == []


def test_a_scheduled_post_waits_for_its_time(db, me, storage, fakes):
    later = add_post(db, storage, me, fakes, status="scheduled", scheduled_at=datetime.now(UTC) + timedelta(hours=2))
    assert due(db) == []
    later.scheduled_at = ago(5)
    db.commit()
    assert due(db) == [later.id]


def test_a_cancelled_or_deleted_post_gets_no_comment(db, me, storage, fakes):
    add_post(db, storage, me, fakes, status="deleted")
    assert due(db) == []


# What is written


def test_the_comment_holds_the_pinned_comment_and_the_usable_products_links(db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    attach(db, post, "Nồi hầm mini")
    attach(db, post, "Bát giữ nhiệt", status="draft")
    post_comments.write(db, post)
    (comment,) = comments_on(fakes, post)
    assert comment["message"] == "Món nào nhà bạn hay nấu nhất?\nNồi hầm mini: https://s.shopee.vn/12"
    assert (post.comment_id, post.comment_error, post.comment_text) == (
        next(iter(fakes.facebook_comments)),
        None,
        comment["message"],
    )
    assert post.commented_at is not None
    assert due(db) == [], "one comment per post"


def test_the_comment_opens_with_the_pinned_template_filled_from_the_scenes_as_they_are_now(db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    video = db.get(Video, post.video_id)
    video.pinned_comment = "{items}\nMón nào nhà bạn hay nấu nhất?"
    scene = db.scalar(select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)))
    scene.text = "Canh *hến*\nTốt cho tim"
    db.commit()
    post_comments.write(db, post)
    (comment,) = comments_on(fakes, post)
    assert comment["message"] == "1. Canh hến – Tốt cho tim\nMón nào nhà bạn hay nấu nhất?"


def test_nothing_to_say_is_recorded_without_calling_facebook(db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    db.get(Video, post.video_id).pinned_comment = ""
    db.commit()
    post_comments.write(db, post)
    assert fakes.facebook_comments == {}
    assert post.comment_error == post_comments.NOTHING_TO_SAY
    assert due(db) == []


def test_a_refused_comment_says_which_permission_and_waits_for_a_member(db, me, storage, fakes):
    fakes.facebook_comment_refused = True
    post = add_post(db, storage, me, fakes)
    post_comments.write(db, post)
    assert "pages_manage_engagement" in post.comment_error
    assert due(db) == [], "a failed comment never loops"


def test_a_lost_answer_is_not_written_again_when_a_member_retries(an, db, me, storage, fakes):
    fakes.facebook_comment_replies_lost = 1
    post = add_post(db, storage, me, fakes)
    post_comments.write(db, post)
    assert post.comment_error and post.comment_id is None
    assert len(comments_on(fakes, post)) == 1, "Facebook kept it although the answer was lost"

    assert an.post(f"/api/posts/{post.id}/comment").status_code == 200
    db.expire_all()
    post = db.get(Publication, post.id)
    assert due(db) == [post.id]
    post_comments.write(db, post)
    assert len(comments_on(fakes, post)) == 1
    assert post.comment_id == next(iter(fakes.facebook_comments)) and post.comment_error is None


def test_a_comment_is_edited_not_written_again(an, db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    post_comments.write(db, post)
    db.get(Video, post.video_id).pinned_comment = "Lưu lại và gửi cho bố mẹ nhé!"
    db.commit()
    an.post(f"/api/posts/{post.id}/comment")
    db.expire_all()
    post = db.get(Publication, post.id)
    post_comments.write(db, post)
    (comment,) = comments_on(fakes, post)
    assert comment["message"] == "Lưu lại và gửi cho bố mẹ nhé!" and comment["edits"] == 1


def test_changing_the_products_updates_a_written_comment(an, db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    post_comments.write(db, post)
    product = attach(db, post, "Nồi hầm mini")
    db.execute(VideoAffiliateProduct.__table__.delete())
    db.commit()

    response = an.put(f"/api/affiliate-products/videos/{post.video_id}", json={"product_ids": [product.id]})
    assert response.status_code == 200, response.text
    db.expire_all()
    post = db.get(Publication, post.id)
    assert due(db) == [post.id]
    post_comments.write(db, post)
    (comment,) = comments_on(fakes, post)
    assert comment["message"].endswith("Nồi hầm mini: https://s.shopee.vn/12") and comment["edits"] == 1


# "Bình luận thêm": more comments of the Page under the reel, after the first


def test_extra_comments_follow_the_first_in_order_once_each(db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    db.get(Video, post.video_id).extra_comments = ["Bố mẹ nhà bạn thích món nào?", "Lưu lại nấu cuối tuần nhé!"]
    db.commit()
    post_comments.write(db, post)
    messages = [comment["message"] for comment in comments_on(fakes, post)]
    assert messages == ["Món nào nhà bạn hay nấu nhất?", "Bố mẹ nhà bạn thích món nào?", "Lưu lại nấu cuối tuần nhé!"]
    assert len(post.extra_comment_ids) == 2 and post.comment_error is None
    assert due(db) == [], "written once"


def test_an_edited_extra_comment_is_edited_and_a_new_one_is_added(an, db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    db.get(Video, post.video_id).extra_comments = ["Một"]
    db.commit()
    post_comments.write(db, post)
    db.get(Video, post.video_id).extra_comments = ["Một, sửa lại", "Hai"]
    db.commit()
    an.post(f"/api/posts/{post.id}/comment")
    db.expire_all()
    post = db.get(Publication, post.id)
    post_comments.write(db, post)
    extras = comments_on(fakes, post)[1:]
    assert [(comment["message"], comment["edits"]) for comment in extras] == [("Một, sửa lại", 1), ("Hai", 0)]


def test_extra_comments_alone_are_something_to_say(db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    video = db.get(Video, post.video_id)
    video.pinned_comment, video.extra_comments = "", ["Chia sẻ cho bạn bè nhé!"]
    db.commit()
    post_comments.write(db, post)
    assert [comment["message"] for comment in comments_on(fakes, post)] == ["Chia sẻ cho bạn bè nhé!"]
    assert post.comment_error is None


def test_extra_comments_are_saved_trimmed_and_at_most_five(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    saved = an.patch(f"/api/videos/{video.id}", json={"extra_comments": [" Một ", "", "Hai"]})
    assert saved.status_code == 200 and saved.json()["extra_comments"] == ["Một", "Hai"]
    too_many = an.patch(f"/api/videos/{video.id}", json={"extra_comments": [str(n) for n in range(6)]})
    assert too_many.status_code == 422


# The post's payload and "Bình luận ngay"


def test_the_post_shows_its_comment_state(an, db, me, storage, fakes):
    post = add_post(db, storage, me, fakes, live_minutes_ago=0.5)
    (row,) = an.get("/api/posts").json()
    assert row["comment"]["state"] == "waiting" and row["comment"]["auto"] is True
    post_comments.write(db, post)
    (row,) = an.get("/api/posts").json()
    assert row["comment"]["state"] == "done" and row["comment"]["text"] == "Món nào nhà bạn hay nấu nhất?"
    row = an.post(f"/api/posts/{post.id}/comment").json()
    assert row["comment"]["state"] == "pending"


def test_comment_now_needs_a_live_post(an, db, me, storage, fakes):
    post = add_post(db, storage, me, fakes, status="scheduled", scheduled_at=datetime.now(UTC) + timedelta(hours=2))
    assert an.post(f"/api/posts/{post.id}/comment").status_code == 409
    assert an.post("/api/posts/999999/comment").status_code == 404


def test_publishing_keeps_the_members_choice(an, db, me, storage, fakes, monkeypatch):
    from reels_api import routes_videos

    calls = []
    monkeypatch.setattr(routes_videos, "_enqueue", lambda db, video, kind, me: calls.append(kind))
    monkeypatch.setattr(routes_videos, "render_signature", lambda *args: "same")
    page = fanpages.save(db, FACEBOOK_PAGE, "Trang Dưỡng Sinh", FACEBOOK_TOKEN, me.id)
    video = make_video(db, storage, me, scene_count=1)
    video.mp4_key, video.rendered_signature = "video.mp4", "same"
    db.commit()
    an.post(f"/api/videos/{video.id}/publish", json={"fanpage_id": page.id, "auto_comment": False})
    post = db.scalar(select(Publication).where(Publication.video_id == video.id))
    assert post.auto_comment is False and calls == ["publish"]


def test_the_worker_round_writes_due_comments_and_survives_a_failure(committed, fakes, tmp_path, monkeypatch):  # noqa: F811
    from reels_api.storage import DirectoryStorage

    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    with committed() as db:
        good = add_post(db, storage, user, fakes).id
        bad = add_post(db, storage, user, fakes).id

    def write(db, post):
        if post.id == bad:
            raise RuntimeError("database hiccup")
        real_write(db, post)

    real_write = post_comments.write
    monkeypatch.setattr(post_comments, "write", write)
    post_comments.write_due(committed)
    with committed() as db:
        assert db.get(Publication, good).comment_id
