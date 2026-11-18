"""The affiliate comment the worker writes under a posted reel (post_comments.py): when, what it says, never twice."""

from datetime import UTC, datetime, timedelta

import pytest
from conftest import first_topic, login, make_user, make_video
from fake_services import FACEBOOK_PAGE, FACEBOOK_TOKEN
from sqlalchemy import select
from worker_helpers import add_user, committed  # noqa: F401  (fixtures)

from reels_api import fanpages, post_comments
from reels_api.models import AffiliateProduct, Fanpage, Publication, Scene, Video, VideoAffiliateProduct

# The pinned comment of a post made by add_post: the title, its one scene, then its survey line (pinned.py).
HEAD = "5 MÓN GIÚP XƯƠNG CHẮC KHỎE\n1. Cá nhỏ\n"
PINNED = HEAD + "Món nào nhà bạn hay nấu nhất?"


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
    video.pinned_survey = "Món nào nhà bạn hay nấu nhất?"
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


def say_nothing(db, video: Video) -> None:
    """A pinned comment with nothing in it: no title, no topic, no scene text and no survey line."""
    video.topic, video.pinned_survey = "", ""
    for scene in db.scalars(select(Scene).where(Scene.video_id == video.id)):
        scene.text = ""


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


def write_all(db, post: Publication, limit: int = 30) -> int:
    """Write until the run is over, letting each pause pass at once; how many times the worker wrote."""
    for turns in range(1, limit + 1):
        post_comments.write(db, post)
        db.refresh(post)
        if post.comment_requested_at is None or post.comment_sent_at >= post.comment_requested_at:
            return turns
        row = db.get(Fanpage, post.fanpage_id)
        row.comments_next_at, post.comment_requested_at = None, datetime.now(UTC)
        db.commit()
    raise AssertionError("the run never ended")


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
    assert comment["message"] == PINNED + "\nNồi hầm mini: https://s.shopee.vn/12"
    assert (post.comment_id, post.comment_error, post.comment_text) == (
        next(iter(fakes.facebook_comments)),
        None,
        comment["message"],
    )
    assert post.commented_at is not None
    assert due(db) == [], "one comment per post"


def test_the_comment_is_built_from_the_scenes_as_they_are_now(db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    video = db.get(Video, post.video_id)
    scene = db.scalar(select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)))
    scene.text = "1. Canh *hến*\nTốt cho tim"
    db.commit()
    post_comments.write(db, post)
    (comment,) = comments_on(fakes, post)
    assert comment["message"] == "5 MÓN GIÚP XƯƠNG CHẮC KHỎE\n1. Canh hến\nMón nào nhà bạn hay nấu nhất?"


def test_nothing_to_say_is_recorded_without_calling_facebook(db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    say_nothing(db, db.get(Video, post.video_id))
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
    db.get(Video, post.video_id).pinned_survey = "Lưu lại và gửi cho bố mẹ nhé!"
    db.commit()
    an.post(f"/api/posts/{post.id}/comment")
    db.expire_all()
    post = db.get(Publication, post.id)
    post_comments.write(db, post)
    (comment,) = comments_on(fakes, post)
    assert comment["message"] == HEAD + "Lưu lại và gửi cho bố mẹ nhé!" and comment["edits"] == 1


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
    write_all(db, post)
    messages = [comment["message"] for comment in comments_on(fakes, post)]
    assert messages == [PINNED, "Bố mẹ nhà bạn thích món nào?", "Lưu lại nấu cuối tuần nhé!"]
    assert len(post.extra_comment_ids) == 2 and post.comment_error is None
    assert due(db) == [], "written once"


def test_an_edited_extra_comment_is_edited_and_a_new_one_is_added(an, db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    db.get(Video, post.video_id).extra_comments = ["Một"]
    db.commit()
    write_all(db, post)
    db.get(Video, post.video_id).extra_comments = ["Một, sửa lại", "Hai"]
    db.commit()
    an.post(f"/api/posts/{post.id}/comment")
    db.expire_all()
    post = db.get(Publication, post.id)
    write_all(db, post)
    extras = comments_on(fakes, post)[1:]
    assert [(comment["message"], comment["edits"]) for comment in extras] == [("Một, sửa lại", 1), ("Hai", 0)]


def test_extra_comments_alone_are_something_to_say(db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    video = db.get(Video, post.video_id)
    say_nothing(db, video)
    video.extra_comments = ["Chia sẻ cho bạn bè nhé!"]
    db.commit()
    write_all(db, post)
    assert [comment["message"] for comment in comments_on(fakes, post)] == ["Chia sẻ cho bạn bè nhé!"]
    assert post.comment_error is None


def test_comments_typed_after_the_first_went_up_are_written_without_asking(an, db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    write_all(db, post)
    assert due(db) == []
    saved = an.patch(
        f"/api/videos/{post.video_id}",
        json={"pinned_survey": "Món nào nhà bạn nấu nhiều nhất?", "extra_comments": ["Lưu lại nhé!"]},
    )
    assert saved.status_code == 200
    db.expire_all()
    assert due(db) == [post.id], "no need to press Cập nhật bình luận"
    post = db.get(Publication, post.id)
    write_all(db, post)
    comments = comments_on(fakes, post)
    assert [(comment["message"], comment["edits"]) for comment in comments] == [
        (HEAD + "Món nào nhà bạn nấu nhiều nhất?", 1),
        ("Lưu lại nhé!", 0),
    ]


def test_saving_the_same_comments_or_a_hand_pasted_video_asks_nothing(an, db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    db.get(Video, post.video_id).extra_comments = ["Một"]
    db.commit()
    write_all(db, post)
    an.patch(f"/api/videos/{post.video_id}", json={"extra_comments": ["Một"], "caption": "Caption mới"})
    db.expire_all()
    assert due(db) == [], "nothing changed in the comments"
    db.get(Video, post.video_id).manual_comment = True
    db.commit()
    asked_at = db.get(Publication, post.id).comment_requested_at
    an.patch(f"/api/videos/{post.video_id}", json={"extra_comments": ["Một", "Hai"]})
    db.expire_all()
    assert db.get(Publication, post.id).comment_requested_at == asked_at, "links pasted by hand: the app keeps out"


def test_a_post_never_commented_is_not_started_by_an_edit(an, db, me, storage, fakes):
    post = add_post(db, storage, me, fakes, auto=False)
    an.patch(f"/api/videos/{post.video_id}", json={"extra_comments": ["Một"]})
    db.expire_all()
    assert due(db) == [], "a post without Tự bình luận waits for Bình luận ngay"


def test_extra_comments_are_saved_trimmed_and_at_most_twelve(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    saved = an.patch(f"/api/videos/{video.id}", json={"extra_comments": [" Một ", "", "Hai"]})
    assert saved.status_code == 200 and saved.json()["extra_comments"] == ["Một", "Hai"]
    too_many = an.patch(f"/api/videos/{video.id}", json={"extra_comments": [str(n) for n in range(13)]})
    assert too_many.status_code == 422


# Pacing: one comment at a time, the Page resting between them


@pytest.fixture
def shortest_rests(monkeypatch):
    monkeypatch.setattr(post_comments.random, "uniform", lambda low, high: low)


def test_a_run_of_extra_comments_goes_one_at_a_time_with_a_rest_between(db, me, storage, fakes, shortest_rests):
    post = add_post(db, storage, me, fakes)
    db.get(Video, post.video_id).extra_comments = ["Một", "Hai", "Ba"]
    db.commit()
    row = db.get(Fanpage, post.fanpage_id)

    post_comments.write(db, post)
    assert [c["message"] for c in comments_on(fakes, post)] == [PINNED]
    wait = (row.comments_next_at - datetime.now(UTC)).total_seconds()
    assert 40 < wait <= 45, "45 to 75 seconds after the first comment"
    assert due(db) == [], "nothing is written while the Page rests"

    for expected in (["Một"], ["Một", "Hai"]):
        row.comments_next_at, post.comment_sent_at, post.comment_requested_at = None, ago(2), ago(1)
        db.commit()
        assert due(db) == [post.id]
        post_comments.write(db, post)
        assert [c["message"] for c in comments_on(fakes, post)][1:] == expected
        wait = (row.comments_next_at - datetime.now(UTC)).total_seconds()
        assert 40 < wait <= 45, "45 to 75 seconds between the extras"

    row.comments_next_at, post.comment_sent_at, post.comment_requested_at = None, ago(2), ago(1)
    db.commit()
    post_comments.write(db, post)
    assert [c["message"] for c in comments_on(fakes, post)][1:] == ["Một", "Hai", "Ba"]
    assert post.commented_at is not None and post.comment_error is None
    assert 55 < (row.comments_next_at - datetime.now(UTC)).total_seconds() <= 60, "a minute before another video"
    assert due(db) == []


@pytest.fixture
def day_hours(monkeypatch):
    monkeypatch.setattr(post_comments, "in_day_hours", lambda at: True)


def test_an_older_reel_gets_one_new_comment_a_day_within_the_days_hours(
    db, me, storage, fakes, shortest_rests, day_hours
):
    post = add_post(db, storage, me, fakes, live_minutes_ago=30 * 60)
    db.get(Video, post.video_id).extra_comments = ["Một", "Hai"]
    db.commit()
    post_comments.write(db, post)  # the first comment, then a short rest
    post.comment_sent_at, post.comment_requested_at = ago(2), ago(1)
    db.get(Fanpage, post.fanpage_id).comments_next_at = None
    db.commit()
    post_comments.write(db, post)
    assert [c["message"] for c in comments_on(fakes, post)][1:] == ["Một"]
    tomorrow = post.comment_requested_at.astimezone(post_comments.VIETNAM_TIME)
    assert tomorrow.date() == post_comments._today() + timedelta(days=1) and tomorrow.hour == 9
    db.get(Fanpage, post.fanpage_id).comments_next_at = None
    db.commit()
    assert due(db) == [], "the next one waits for tomorrow"
    post.comment_sent_at, post.comment_requested_at = ago(2), ago(1)
    db.commit()
    post_comments.write(db, post)
    assert [c["message"] for c in comments_on(fakes, post)][1:] == ["Một", "Hai"]
    assert post.commented_at is not None


def test_an_older_reels_comment_outside_the_days_hours_waits_without_an_attempt(db, me, storage, fakes, monkeypatch):
    monkeypatch.setattr(post_comments, "in_day_hours", lambda at: False)
    post = add_post(db, storage, me, fakes, live_minutes_ago=30 * 60)
    write_all(db, post)
    db.get(Video, post.video_id).extra_comments = ["Một"]
    post.comment_requested_at = datetime.now(UTC)
    db.commit()
    sent = post.comment_sent_at
    post_comments.write(db, post)
    assert len(comments_on(fakes, post)) == 1 and post.comment_sent_at == sent
    assert post.comment_requested_at > datetime.now(UTC)


def test_a_reel_past_three_days_gets_no_new_comment_but_an_edit(db, me, storage, fakes, day_hours):
    post = add_post(db, storage, me, fakes)
    db.get(Video, post.video_id).extra_comments = ["Một"]
    db.commit()
    write_all(db, post)
    post.published_at = ago(4 * 24 * 60)
    db.get(Video, post.video_id).extra_comments = ["Một, sửa lại", "Hai"]
    db.commit()
    write_all(db, post)
    extras = comments_on(fakes, post)[1:]
    assert [(comment["message"], comment["edits"]) for comment in extras] == [("Một, sửa lại", 1)]


def test_another_video_waits_for_the_page_to_stop_resting(db, me, storage, fakes, shortest_rests):
    first = add_post(db, storage, me, fakes)
    db.get(Video, first.video_id).extra_comments = ["Một", "Hai"]
    db.commit()
    post_comments.write(db, first)
    second = add_post(db, storage, me, fakes)
    assert due(db) == []
    row = db.get(Fanpage, first.fanpage_id)
    row.comments_next_at = ago(0.01)
    db.commit()
    assert second.id in due(db)


def test_a_page_stops_at_its_daily_number_and_goes_on_the_next_day(db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    row = db.get(Fanpage, post.fanpage_id)
    row.comments_day, row.comments_count = post_comments._today(), post_comments.DAY_CAP
    db.commit()
    assert due(db) == []
    row.comments_day = post_comments._today() - timedelta(days=1)
    db.commit()
    assert due(db) == [post.id]
    post_comments.write(db, post)
    db.refresh(row)
    assert (row.comments_day, row.comments_count) == (post_comments._today(), 1)


# The post's payload and "Bình luận ngay"


def test_the_post_shows_its_comment_state(an, db, me, storage, fakes):
    post = add_post(db, storage, me, fakes, live_minutes_ago=0.5)
    (row,) = an.get("/api/posts").json()
    assert row["comment"]["state"] == "waiting" and row["comment"]["auto"] is True
    post_comments.write(db, post)
    (row,) = an.get("/api/posts").json()
    assert row["comment"]["state"] == "done" and row["comment"]["text"] == PINNED
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


# "Bình luận" on "Bài đăng" (comment_tracker.py): where each live reel's comments stand


def tracked(an) -> dict:
    response = an.get("/api/posts/comments")
    assert response.status_code == 200
    return {row["post_id"]: row for row in response.json()["posts"]}


def test_the_tracker_counts_what_is_up_and_what_is_left_in_the_workers_order(an, db, me, storage, fakes):
    first = add_post(db, storage, me, fakes)
    second = add_post(db, storage, me, fakes)
    for post in (first, second):
        db.get(Video, post.video_id).extra_comments = ["Một", "Hai"]
    db.commit()
    rows = tracked(an)
    assert (rows[first.id]["state"], rows[first.id]["left"], rows[first.id]["position"]) == ("queued", 3, 1)
    assert rows[second.id]["position"] == 2 and rows[second.id]["eta"] > rows[first.id]["eta"]
    write_all(db, first)
    row = tracked(an)[first.id]
    assert (row["state"], row["saved"], row["written"], row["left"], row["position"]) == ("done", 2, 2, 0, None)


def test_the_tracker_tells_a_post_never_asked_a_hand_pasted_video_and_skips_old_posts(an, db, me, storage, fakes):
    never = add_post(db, storage, me, fakes, auto=False)
    pasted = add_post(db, storage, me, fakes)
    old = add_post(db, storage, me, fakes, live_minutes_ago=4 * 24 * 60)
    for post in (never, pasted, old):
        db.get(Video, post.video_id).extra_comments = ["Một"]
    db.get(Video, pasted.video_id).manual_comment = True
    db.commit()
    rows = tracked(an)
    assert rows[never.id]["state"] == "not_asked" and rows[never.id]["left"] == 2
    assert (rows[pasted.id]["state"], rows[pasted.id]["left"]) == ("manual", 0)
    assert old.id not in rows


def test_the_tracker_shows_a_page_past_its_day_cap_finishing_the_next_day(an, db, me, storage, fakes):
    post = add_post(db, storage, me, fakes)
    db.get(Video, post.video_id).extra_comments = ["Một"]
    page = db.get(Fanpage, post.fanpage_id)
    page.comments_day, page.comments_count = post_comments._today(), post_comments.DAY_CAP
    db.commit()
    body = an.get("/api/posts/comments").json()
    assert body["pages"][0]["today"] == post_comments.DAY_CAP
    eta = datetime.fromisoformat(body["posts"][0]["eta"]).astimezone(post_comments.VIETNAM_TIME)
    assert eta.date() > post_comments._today()


def test_the_tracker_keeps_my_posts_and_pages_when_asked(an, db, me, storage, fakes):
    mine = add_post(db, storage, me, fakes)
    teammate = make_user(db, email="b@doi.vn", name="B")
    page = fanpages.save(db, "page-b", "Trang của B", FACEBOOK_TOKEN, teammate.id)
    db.flush()
    theirs = add_post(db, storage, teammate, fakes)
    theirs.fanpage_id = page.id
    db.commit()
    assert {mine.id, theirs.id} <= set(tracked(an))
    body = an.get("/api/posts/comments?owner=me").json()
    assert [row["post_id"] for row in body["posts"]] == [mine.id]
    assert [p["name"] for p in body["pages"]] == ["Trang Dưỡng Sinh"]
