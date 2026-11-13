"""A video that is out on Facebook at its slot is sent to TikTok by the worker's round: a draft into the member's TikTok
inbox, or (once the Page's owner flips it) a public post. Approval on Facebook still gates everything."""

from datetime import timedelta

import pytest
from conftest import first_topic, login, make_user, make_video
from fake_services import FACEBOOK_PAGE, FACEBOOK_TOKEN
from sqlalchemy import select

from reels_api import fanpages
from reels_api.jobs import queue_tiktok_posts
from reels_api.models import AffiliateAccount, Article, Fanpage, Job, Publication
from reels_api.sessions import now


@pytest.fixture
def me(db):
    return make_user(db)


def page_with_tiktok(db, me, mode=None, linked=True):
    page = fanpages.save(db, FACEBOOK_PAGE, "Ăn Lành", FACEBOOK_TOKEN, me.id)
    page.owner_id = me.id
    if mode:
        page.tiktok_auto_mode = mode
    if linked:
        account = AffiliateAccount(platform="tiktok", owner_id=me.id, name="@anlanhsk")
        db.add(account)
        db.flush()
        page.tiktok_account_id = account.id
    db.commit()
    return page


def due_post(db, storage, me, page, status="scheduled", minutes_ago=5):
    video = make_video(db, storage, me)
    video.mp4_key = f"videos/{video.id}/video-x.mp4"
    post = Publication(
        video_id=video.id,
        platform="facebook",
        fanpage_id=page.id,
        status=status,
        scheduled_at=now() - timedelta(minutes=minutes_ago),
        remote_id="reel-1",
        created_by_id=me.id,
    )
    db.add(post)
    db.commit()
    return video


def tiktok_posts(db, video):
    return db.scalars(
        select(Publication).where(Publication.video_id == video.id, Publication.platform == "tiktok")
    ).all()


def test_a_due_facebook_post_sends_a_draft_to_tiktok(db, me, storage):
    page = page_with_tiktok(db, me)
    video = due_post(db, storage, me, page)
    queue_tiktok_posts(db)
    db.commit()
    (post,) = tiktok_posts(db, video)
    assert (post.status, post.publish_mode, post.privacy_level, post.created_by_id) == ("pending", "draft", None, me.id)
    assert post.affiliate_account_id == page.tiktok_account_id
    job = db.scalar(select(Job).where(Job.video_id == video.id, Job.kind == "tiktok_publish"))
    assert (job.status, job.publication_id, job.created_by_id) == ("queued", post.id, me.id)


def test_a_published_facebook_post_counts_too(db, me, storage):
    video = due_post(db, storage, me, page_with_tiktok(db, me), status="published")
    queue_tiktok_posts(db)
    db.commit()
    assert len(tiktok_posts(db, video)) == 1


def test_the_direct_mode_of_the_page_posts_publicly(db, me, storage):
    video = due_post(db, storage, me, page_with_tiktok(db, me, mode="direct"))
    queue_tiktok_posts(db)
    db.commit()
    (post,) = tiktok_posts(db, video)
    assert (post.publish_mode, post.privacy_level) == ("direct", "PUBLIC_TO_EVERYONE")


def test_a_page_without_a_tiktok_account_sends_nothing(db, me, storage):
    video = due_post(db, storage, me, page_with_tiktok(db, me, linked=False))
    queue_tiktok_posts(db)
    db.commit()
    assert tiktok_posts(db, video) == []


@pytest.mark.parametrize("existing", ["pending", "scheduled", "published"])
def test_a_video_already_on_tiktok_is_not_sent_again(db, me, storage, existing):
    page = page_with_tiktok(db, me)
    video = due_post(db, storage, me, page)
    db.add(Publication(video_id=video.id, platform="tiktok", status=existing, created_by_id=me.id))
    db.commit()
    queue_tiktok_posts(db)
    db.commit()
    assert len(tiktok_posts(db, video)) == 1


def test_a_cancelled_tiktok_post_does_not_block_it(db, me, storage):
    page = page_with_tiktok(db, me)
    video = due_post(db, storage, me, page)
    db.add(Publication(video_id=video.id, platform="tiktok", status="cancelled", created_by_id=me.id))
    db.commit()
    queue_tiktok_posts(db)
    db.commit()
    assert len(tiktok_posts(db, video)) == 2


def test_a_busy_video_waits_for_the_next_round(db, me, storage):
    video = due_post(db, storage, me, page_with_tiktok(db, me))
    db.add(Job(video_id=video.id, kind="check", status="running", created_by_id=me.id))
    db.commit()
    queue_tiktok_posts(db)
    db.commit()
    assert tiktok_posts(db, video) == []


@pytest.mark.parametrize("status", ["pending", "cancelled", "deleted"])
def test_only_a_reel_that_is_out_or_scheduled_counts(db, me, storage, status):
    video = due_post(db, storage, me, page_with_tiktok(db, me), status=status)
    queue_tiktok_posts(db)
    db.commit()
    assert tiktok_posts(db, video) == []


def test_a_slot_still_ahead_sends_nothing(db, me, storage):
    video = due_post(db, storage, me, page_with_tiktok(db, me), minutes_ago=-30)
    queue_tiktok_posts(db)
    db.commit()
    assert tiktok_posts(db, video) == []


def test_a_slot_older_than_a_day_is_left_alone(db, me, storage):
    video = due_post(db, storage, me, page_with_tiktok(db, me), minutes_ago=25 * 60)
    queue_tiktok_posts(db)
    db.commit()
    assert tiktok_posts(db, video) == []


def test_a_video_without_an_mp4_sends_nothing(db, me, storage):
    video = due_post(db, storage, me, page_with_tiktok(db, me))
    video.mp4_key = None
    db.commit()
    queue_tiktok_posts(db)
    db.commit()
    assert tiktok_posts(db, video) == []


@pytest.mark.parametrize("fault", ["inactive", "other_owner", "wrong_platform", "no_owner"])
def test_an_account_that_cannot_post_for_the_owner_sends_nothing(db, me, storage, fault):
    page = page_with_tiktok(db, me)
    account = db.get(AffiliateAccount, page.tiktok_account_id)
    if fault == "inactive":
        account.active = False
    if fault == "other_owner":
        account.owner_id = make_user(db, email="binh@doi.vn", name="Trần Bình").id
    if fault == "wrong_platform":
        account.platform = "shopee"
    if fault == "no_owner":
        page.owner_id = None
    video = due_post(db, storage, me, page)
    queue_tiktok_posts(db)
    db.commit()
    assert tiktok_posts(db, video) == []


def test_an_article_post_is_never_swept(db, me, storage):
    page = page_with_tiktok(db, me)
    article = Article(knowledge_topic_id=first_topic(db).id, kind="kien_thuc", topic="Ngủ đủ giấc", created_by_id=me.id)
    db.add(article)
    db.flush()
    db.add(
        Publication(
            article_id=article.id,
            platform="facebook",
            fanpage_id=page.id,
            status="scheduled",
            scheduled_at=now() - timedelta(minutes=5),
            created_by_id=me.id,
        )
    )
    db.commit()
    queue_tiktok_posts(db)
    db.commit()
    assert db.scalar(select(Job).where(Job.kind == "tiktok_publish")) is None


def test_the_round_does_not_queue_twice(db, me, storage):
    video = due_post(db, storage, me, page_with_tiktok(db, me))
    queue_tiktok_posts(db)
    db.commit()
    queue_tiktok_posts(db)
    db.commit()
    assert len(tiktok_posts(db, video)) == 1


def test_the_owner_sets_the_auto_mode(client, db, me):
    page = page_with_tiktok(db, me)
    login(client)
    (row,) = [r for r in client.put(f"/api/fanpages/{page.id}/tiktok-auto-mode", json={"mode": "direct"}).json()]
    assert row["tiktok_auto_mode"] == "direct"
    assert db.get(Fanpage, page.id).tiktok_auto_mode == "direct"


def test_the_auto_mode_is_draft_or_direct_only(client, db, me):
    page = page_with_tiktok(db, me)
    login(client)
    assert client.put(f"/api/fanpages/{page.id}/tiktok-auto-mode", json={"mode": "public"}).status_code == 422
    assert client.put("/api/fanpages/9999/tiktok-auto-mode", json={"mode": "draft"}).status_code == 404


def test_only_the_owner_sets_the_auto_mode(client, db, me):
    page = page_with_tiktok(db, me)
    other = make_user(db, email="binh@doi.vn", name="Trần Bình")
    login(client, email=other.email)
    refused = client.put(f"/api/fanpages/{page.id}/tiktok-auto-mode", json={"mode": "direct"})
    assert refused.status_code == 403
