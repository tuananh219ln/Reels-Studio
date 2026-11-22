"""A video that is out on Facebook at its slot is posted by the worker's round to the Instagram account linked to its
Page, when the Page's owner turned the switch on. Instagram has no scheduled time, so the round is the clock."""

from datetime import timedelta

import pytest
from conftest import login, make_user, make_video
from fake_services import FACEBOOK_PAGE, FACEBOOK_TOKEN, FACEBOOK_USER_TOKEN
from sqlalchemy import select

from reels_api import fanpages, hashtags, instagram
from reels_api.jobs import queue_instagram_auto_posts
from reels_api.models import Fanpage, Job, Publication
from reels_api.sessions import now

URL = "/api/fanpages"
INSTAGRAM_USER = "17841400000000001"


@pytest.fixture
def me(db):
    return make_user(db)


def page_with_instagram(db, me, auto=True, linked=True):
    page = fanpages.save(db, FACEBOOK_PAGE, "Tiệm Đọc Comment", FACEBOOK_TOKEN, me.id)
    page.owner_id = me.id
    page.instagram_auto = auto
    if linked:
        page.instagram_user_id, page.instagram_username = INSTAGRAM_USER, "tiemdoccomment"
    db.commit()
    return page


def due_post(db, storage, me, page, status="scheduled", minutes_ago=5, count=1):
    video = make_video(db, storage, me)
    video.mp4_key = f"videos/{video.id}/video-x.mp4"
    for _ in range(count):
        db.add(
            Publication(
                video_id=video.id,
                platform="facebook",
                fanpage_id=page.id,
                status=status,
                scheduled_at=None if minutes_ago is None else now() - timedelta(minutes=minutes_ago),
                created_by_id=me.id,
            )
        )
    db.commit()
    return video


def instagram_posts(db, video):
    return db.scalars(
        select(Publication).where(Publication.video_id == video.id, Publication.platform == "instagram")
    ).all()


def run(db):
    queue_instagram_auto_posts(db)
    db.commit()


def test_a_due_facebook_post_posts_to_instagram(db, me, storage):
    page = page_with_instagram(db, me)
    video = due_post(db, storage, me, page)
    run(db)
    (post,) = instagram_posts(db, video)
    assert (post.status, post.fanpage_id, post.created_by_id, post.scheduled_at) == ("pending", page.id, me.id, None)
    assert post.remote_mp4_key == video.mp4_key
    assert post.post_text == instagram.caption(hashtags.post_text(video.caption, video.hashtags))
    job = db.scalar(select(Job).where(Job.video_id == video.id, Job.kind == "ig_publish"))
    assert (job.status, job.publication_id, job.created_by_id) == ("queued", post.id, me.id)


def test_a_published_facebook_post_counts_too(db, me, storage):
    video = due_post(db, storage, me, page_with_instagram(db, me), status="published")
    run(db)
    assert len(instagram_posts(db, video)) == 1


def test_a_page_with_the_switch_off_posts_nothing(db, me, storage):
    video = due_post(db, storage, me, page_with_instagram(db, me, auto=False))
    run(db)
    assert instagram_posts(db, video) == []


def test_a_page_without_instagram_posts_nothing(db, me, storage):
    video = due_post(db, storage, me, page_with_instagram(db, me, linked=False))
    run(db)
    assert instagram_posts(db, video) == []


def test_a_page_without_an_owner_posts_nothing(db, me, storage):
    page = page_with_instagram(db, me)
    video = due_post(db, storage, me, page)
    page.owner_id = None
    db.commit()
    run(db)
    assert instagram_posts(db, video) == []


@pytest.mark.parametrize("existing", ["pending", "scheduled", "published", "failed"])
def test_a_video_already_on_instagram_is_not_posted_again(db, me, storage, existing):
    video = due_post(db, storage, me, page_with_instagram(db, me))
    db.add(Publication(video_id=video.id, platform="instagram", status=existing, created_by_id=me.id))
    db.commit()
    run(db)
    assert len(instagram_posts(db, video)) == 1


def test_a_cancelled_instagram_post_does_not_block_it(db, me, storage):
    video = due_post(db, storage, me, page_with_instagram(db, me))
    db.add(Publication(video_id=video.id, platform="instagram", status="cancelled", created_by_id=me.id))
    db.commit()
    run(db)
    assert len(instagram_posts(db, video)) == 2


def test_a_busy_video_waits_for_the_next_round(db, me, storage):
    video = due_post(db, storage, me, page_with_instagram(db, me))
    job = Job(video_id=video.id, kind="check", status="running", created_by_id=me.id)
    db.add(job)
    db.commit()
    run(db)
    assert instagram_posts(db, video) == []
    job.status = "done"
    db.commit()
    run(db)
    assert len(instagram_posts(db, video)) == 1


def test_a_slot_older_than_a_day_is_left_alone(db, me, storage):
    video = due_post(db, storage, me, page_with_instagram(db, me), minutes_ago=25 * 60)
    run(db)
    assert instagram_posts(db, video) == []


def test_a_slot_still_ahead_posts_nothing(db, me, storage):
    video = due_post(db, storage, me, page_with_instagram(db, me), minutes_ago=-30)
    run(db)
    assert instagram_posts(db, video) == []


def test_a_post_now_without_a_slot_posts_nothing(db, me, storage):
    video = due_post(db, storage, me, page_with_instagram(db, me), status="published", minutes_ago=None)
    run(db)
    assert instagram_posts(db, video) == []


@pytest.mark.parametrize("status", ["pending", "cancelled", "deleted"])
def test_only_a_reel_that_is_out_or_scheduled_counts(db, me, storage, status):
    video = due_post(db, storage, me, page_with_instagram(db, me), status=status)
    run(db)
    assert instagram_posts(db, video) == []


def test_a_video_without_an_mp4_posts_nothing(db, me, storage):
    video = due_post(db, storage, me, page_with_instagram(db, me))
    video.mp4_key = None
    db.commit()
    run(db)
    assert instagram_posts(db, video) == []


def test_a_long_video_is_posted_like_any_other(db, me, storage):
    video = due_post(db, storage, me, page_with_instagram(db, me))
    video.duration = 113.2
    db.commit()
    run(db)
    assert len(instagram_posts(db, video)) == 1


def test_two_facebook_posts_of_a_video_make_one_instagram_post(db, me, storage):
    video = due_post(db, storage, me, page_with_instagram(db, me), count=2)
    run(db)
    assert len(instagram_posts(db, video)) == 1


def test_the_round_does_not_queue_twice(db, me, storage):
    video = due_post(db, storage, me, page_with_instagram(db, me))
    run(db)
    run(db)
    assert len(instagram_posts(db, video)) == 1


def test_a_failed_instagram_job_leaves_the_facebook_post_alone(db, me, storage):
    video = due_post(db, storage, me, page_with_instagram(db, me))
    run(db)
    (post,) = instagram_posts(db, video)
    post.status = "failed"
    db.commit()
    run(db)
    facebook = db.scalar(
        select(Publication).where(Publication.video_id == video.id, Publication.platform == "facebook")
    )
    assert (facebook.status, len(instagram_posts(db, video))) == ("scheduled", 1)


# The switch on the Page.


@pytest.fixture
def an(client, me):
    login(client)
    return client


def connect(an):
    (row,) = an.post(URL, json={"token": FACEBOOK_USER_TOKEN, "page_ids": [FACEBOOK_PAGE]}).json()
    return row


def test_a_new_page_has_the_switch_off(an, fakes):
    assert connect(an)["instagram_auto"] is False


def test_the_owner_turns_the_switch_on_and_off(an, db, fakes):
    row = connect(an)
    db.get(Fanpage, row["id"]).instagram_user_id = INSTAGRAM_USER
    db.commit()
    (on,) = an.put(f"{URL}/{row['id']}/instagram-auto", json={"auto": True}).json()
    assert on["instagram_auto"] is True
    (off,) = an.put(f"{URL}/{row['id']}/instagram-auto", json={"auto": False}).json()
    assert off["instagram_auto"] is False


def test_a_page_without_instagram_cannot_be_switched_on(an, fakes):
    row = connect(an)
    refused = an.put(f"{URL}/{row['id']}/instagram-auto", json={"auto": True})
    assert (refused.status_code, refused.json()["message"]) == (
        422,
        "Page chưa liên kết tài khoản Instagram, hãy liên kết rồi bật lại",
    )


def test_only_the_pages_owner_switches_it(an, client, db, fakes):
    row = connect(an)
    page = db.get(Fanpage, row["id"])
    page.instagram_user_id = INSTAGRAM_USER
    db.commit()
    make_user(db, email="binh@doi.vn", name="Trần Bình")
    login(client, "binh@doi.vn")
    refused = client.put(f"{URL}/{row['id']}/instagram-auto", json={"auto": True})
    assert (refused.status_code, refused.json()["message"]) == (
        403,
        "Chỉ chủ của Fanpage mới đổi được cách tự đăng Instagram",
    )
    assert db.get(Fanpage, row["id"]).instagram_auto is False
