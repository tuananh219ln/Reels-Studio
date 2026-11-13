"""Posting a TikTok version through TikTok's Content Posting API (issue #46): the endpoint, then the job in process,
against the fake TikTok."""

from datetime import UTC, datetime, timedelta

import pytest
from conftest import client_for, login, make_user, make_video
from fake_services import TIKTOK_CODE, TIKTOK_OPEN_ID
from sqlalchemy import delete, select
from worker_helpers import add_job, add_user, committed, job_row  # noqa: F401  (fixtures)

from reels_api import crypto, tiktok, tiktok_connections, tiktok_publish
from reels_api.models import (
    AffiliateAccount,
    Job,
    KnowledgeTopic,
    Publication,
    TikTokConnection,
    TikTokOAuthState,
    Video,
)
from reels_api.storage import DirectoryStorage

MP4 = b"fake mp4 bytes " * 100


def _tokens(open_id=TIKTOK_OPEN_ID, hours=24) -> tiktok.Tokens:
    moment = datetime.now(UTC)
    return tiktok.Tokens(
        open_id=open_id,
        scope="user.info.basic,video.upload,video.publish",
        access_token=f"access-{open_id}",
        refresh_token=f"refresh-{open_id}",
        access_expires_at=moment + timedelta(hours=hours),
        refresh_expires_at=moment + timedelta(days=365),
    )


def _user(open_id=TIKTOK_OPEN_ID, username="anlanhsk") -> tiktok.User:
    return tiktok.User(open_id=open_id, username=username, display_name="An Lành SK", avatar_url=None)


def tiktok_video(db, storage, user, platform="tiktok", mp4=True) -> Video:
    video = make_video(db, storage, user, scene_count=1)
    video.platform = platform
    video.caption, video.hashtags = "Ăn vừng đen mỗi sáng", ["#vungden", "#suckhoe"]
    if mp4:
        video.mp4_key = f"videos/{video.id}/video-x.mp4"
        storage.save_bytes(video.mp4_key, MP4)
    db.commit()
    return video


def connected_account(db, user, open_id=TIKTOK_OPEN_ID, username="anlanhsk", tokens=None) -> AffiliateAccount:
    connection = tiktok_connections.connect(db, user.id, tokens or _tokens(open_id), _user(open_id, username))
    db.commit()
    return db.get(AffiliateAccount, connection.affiliate_account_id)


# --- The endpoint ---


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def test_publish_queues_a_draft_and_locks_the_video(an, db, me, storage):
    video = tiktok_video(db, storage, me)
    account = connected_account(db, me)
    response = an.post(f"/api/tiktok/videos/{video.id}/publish", json={"account_id": account.id})
    assert response.status_code == 201, response.text
    post = db.scalar(select(Publication).where(Publication.video_id == video.id))
    assert (post.platform, post.status, post.publish_mode, post.privacy_level) == ("tiktok", "pending", "draft", None)
    assert (post.affiliate_account_id, post.created_by_id) == (account.id, me.id)
    job = db.scalar(select(Job).where(Job.video_id == video.id))
    assert (job.kind, job.status, job.publication_id) == ("tiktok_publish", "queued", post.id)
    payload = response.json()
    assert payload["locked"] is True
    # The video's group has no TikTok set, so its TikTok caption is the bare caption text.
    assert payload["tiktok_caption"] == "Ăn vừng đen mỗi sáng"
    assert payload["tiktok_posts"][0]["mode"] == "draft" and payload["tiktok_posts"][0]["status"] == "pending"


def test_a_direct_post_defaults_to_self_only(an, db, me, storage):
    video = tiktok_video(db, storage, me)
    account = connected_account(db, me)
    an.post(f"/api/tiktok/videos/{video.id}/publish", json={"account_id": account.id, "mode": "direct"})
    post = db.scalar(select(Publication).where(Publication.video_id == video.id))
    assert (post.publish_mode, post.privacy_level) == ("direct", "SELF_ONLY")
    other = tiktok_video(db, storage, me)
    response = an.post(
        f"/api/tiktok/videos/{other.id}/publish",
        json={"account_id": account.id, "mode": "direct", "privacy_level": "EVERYONE_PLEASE"},
    )
    assert response.status_code == 422


def test_publish_takes_any_videos_mp4_but_needs_one(an, db, me, storage):
    # A Facebook video's MP4 goes to TikTok too (docs/decisions.md, 2026-11-08); until then only a TikTok version did.
    account = connected_account(db, me)
    facebook = tiktok_video(db, storage, me, platform="facebook")
    sent = an.post(f"/api/tiktok/videos/{facebook.id}/publish", json={"account_id": account.id})
    assert sent.status_code == 201, sent.text
    assert db.scalar(select(Publication).where(Publication.video_id == facebook.id)).platform == "tiktok"
    no_mp4 = tiktok_video(db, storage, me, mp4=False)
    response = an.post(f"/api/tiktok/videos/{no_mp4.id}/publish", json={"account_id": account.id})
    assert response.json()["message"] == "Video chưa render MP4 để đăng"


def test_publish_needs_the_members_own_connected_account(an, db, me, storage, app):
    video = tiktok_video(db, storage, me)
    binh = make_user(db, email="binh@doi.vn", name="Bình")
    theirs = connected_account(db, binh, open_id="tt-open-binh", username="binh")
    response = an.post(f"/api/tiktok/videos/{video.id}/publish", json={"account_id": theirs.id})
    assert (response.status_code, response.json()["message"]) == (422, "Hãy chọn một tài khoản TikTok của bạn")
    by_hand = AffiliateAccount(
        platform="tiktok", owner_id=me.id, name="Kênh tay", profile_url="https://www.tiktok.com/@kenhtay"
    )
    db.add(by_hand)
    db.commit()
    response = an.post(f"/api/tiktok/videos/{video.id}/publish", json={"account_id": by_hand.id})
    assert response.status_code == 422 and "chưa kết nối TikTok" in response.json()["message"]
    assert db.scalar(select(Publication).where(Publication.video_id == video.id)) is None


def test_publish_refuses_a_connection_that_must_be_made_again(an, db, me, storage):
    video = tiktok_video(db, storage, me)
    account = connected_account(db, me)
    tiktok_connections.of_account(db, account.id).last_error = "Kết nối TikTok đã hết hạn, hãy kết nối lại"
    db.commit()
    response = an.post(f"/api/tiktok/videos/{video.id}/publish", json={"account_id": account.id})
    assert response.status_code == 422 and "đã hết hạn" in response.json()["message"]


def test_a_post_on_its_way_to_tiktok_blocks_a_second_one(an, db, me, storage):
    video = tiktok_video(db, storage, me)
    account = connected_account(db, me)
    an.post(f"/api/tiktok/videos/{video.id}/publish", json={"account_id": account.id})
    # Its job failed after TikTok was given the post: "Thử lại", not a second post.
    job = db.scalar(select(Job).where(Job.video_id == video.id))
    job.status = "failed"
    db.scalar(select(Publication).where(Publication.video_id == video.id)).remote_id = "v_pub_file~v2-1"
    db.commit()
    response = an.post(f"/api/tiktok/videos/{video.id}/publish", json={"account_id": account.id})
    assert response.status_code == 409 and "Thử lại" in response.json()["message"]


def test_a_post_that_never_reached_tiktok_is_replaced(an, db, me, storage):
    video = tiktok_video(db, storage, me)
    account = connected_account(db, me)
    an.post(f"/api/tiktok/videos/{video.id}/publish", json={"account_id": account.id})
    db.scalar(select(Job).where(Job.video_id == video.id)).status = "failed"
    db.commit()
    response = an.post(f"/api/tiktok/videos/{video.id}/publish", json={"account_id": account.id, "mode": "direct"})
    assert response.status_code == 201, response.text
    posts = db.scalars(select(Publication).where(Publication.video_id == video.id).order_by(Publication.id)).all()
    assert [(post.status, post.publish_mode) for post in posts] == [("cancelled", "draft"), ("pending", "direct")]


def test_the_link_of_a_post_sent_through_the_api_is_added_once_by_its_author(an, db, me, storage, app):
    video = tiktok_video(db, storage, me)
    account = connected_account(db, me)
    post = Publication(
        video_id=video.id,
        platform="tiktok",
        status="pending",
        created_by_id=me.id,
        affiliate_account_id=account.id,
        publish_mode="draft",
        remote_id="v_pub_file~v2-1",
    )
    db.add(post)
    db.commit()
    url = "https://www.tiktok.com/@anlanhsk/video/7300000000000000001"
    assert an.post(f"/api/tiktok/posts/{post.id}/url", json={"url": url}).status_code == 409  # not on TikTok yet
    post.status = "published"
    db.commit()
    make_user(db, email="binh@doi.vn", name="Bình")
    other = client_for(app)
    login(other, email="binh@doi.vn")
    assert other.post(f"/api/tiktok/posts/{post.id}/url", json={"url": url}).status_code == 403
    assert an.post(f"/api/tiktok/posts/{post.id}/url", json={"url": "https://example.com/x"}).status_code == 422
    response = an.post(f"/api/tiktok/posts/{post.id}/url", json={"url": url})
    assert response.status_code == 200, response.text
    assert response.json()["tiktok_posts"][0]["url"] == url
    assert an.post(f"/api/tiktok/posts/{post.id}/url", json={"url": url}).status_code == 409


# --- The job, in process ---


@pytest.fixture
def ready(committed, tmp_path, fakes, monkeypatch):
    """A TikTok version with its MP4, and its author's TikTok account connected through the fake TikTok."""
    monkeypatch.setattr(tiktok_publish, "POLL_SECONDS", 0)
    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    with committed() as db:
        video = tiktok_video(db, storage, user)
        tokens = tiktok.exchange_code(TIKTOK_CODE)
        connection = tiktok_connections.connect(db, user.id, tokens, tiktok.user_info(tokens.access_token))
        db.commit()
        account_id, connection_id = connection.affiliate_account_id, connection.id
    fakes.tiktok_calls.clear()
    yield user, storage, video.id, account_id, connection_id
    with committed() as db:
        db.execute(delete(TikTokConnection))
        db.execute(delete(TikTokOAuthState))
        db.execute(delete(Publication))
        db.execute(delete(Video))
        db.execute(delete(AffiliateAccount))
        db.commit()


def send(committed, ready, mode="draft", privacy=None, retry_of=None) -> tuple[Job, Publication]:
    """Queue the post as the endpoint does (or reuse the pending one, as "Thử lại" does) and run its job."""
    from reels_api import jobs

    user, storage, video_id, account_id, _ = ready
    with committed() as db:
        post = db.scalar(select(Publication).where(Publication.video_id == video_id, Publication.status == "pending"))
        if post is None:
            post = Publication(
                video_id=video_id,
                platform="tiktok",
                status="pending",
                created_by_id=user.id,
                affiliate_account_id=account_id,
                publish_mode=mode,
                privacy_level=privacy,
            )
            db.add(post)
            db.commit()
        post_id = post.id
    job_id = add_job(
        committed,
        video_id,
        user.id,
        kind="tiktok_publish",
        status="running",
        publication_id=post_id,
        retry_of_id=retry_of,
    )
    jobs.run_job(job_id, committed, storage)
    with committed() as db:
        return job_row(committed, job_id), db.get(Publication, post_id)


def inits(fakes) -> list[str]:
    return [call for call in fakes.tiktok_calls if call.endswith("/init/")]


def test_a_draft_goes_to_the_inbox_and_the_post_is_published(committed, ready, fakes):
    job, post = send(committed, ready)
    assert job.status == "done", (job.error, job.error_detail)
    assert (post.status, post.publish_mode) == ("published", "draft")
    assert post.published_at is not None and post.remote_id in fakes.tiktok_posts
    sent = fakes.tiktok_posts[post.remote_id]
    assert sent["mode"] == "draft" and sent["post_info"] == {}  # a draft carries no caption
    assert sent["bytes"] == len(MP4)
    assert sent["source_info"] == {
        "source": "FILE_UPLOAD",
        "video_size": len(MP4),
        "chunk_size": len(MP4),
        "total_chunk_count": 1,
    }
    assert fakes.tiktok_calls == [
        "/v2/post/publish/inbox/video/init/",
        "upload",
        "/v2/post/publish/status/fetch/",
    ]


def test_the_publish_id_is_saved_before_the_upload(committed, ready, fakes):
    fakes.tiktok_upload_fails = 1
    job, post = send(committed, ready)
    assert job.status == "failed"
    assert post.status == "pending" and post.remote_id in fakes.tiktok_posts


def test_a_direct_post_carries_the_tiktok_caption_and_the_ai_label(committed, ready, fakes):
    # The video's group posts to TikTok: the title is its TikTok caption, not its Facebook hashtags.
    _, _, video_id, _, _ = ready
    with committed() as db:
        video = db.get(Video, video_id)
        db.get(KnowledgeTopic, video.knowledge_topic_id).name = "Ăn Lành Sống Khỏe – Sức khỏe"
        db.commit()
    job, post = send(committed, ready, mode="direct", privacy="SELF_ONLY")
    assert job.status == "done", (job.error, job.error_detail)
    assert post.status == "published"
    assert fakes.tiktok_posts[post.remote_id]["post_info"] == {
        "title": "Ăn vừng đen mỗi sáng\n\n#suckhoe #songkhoe #anlanh #meosuckhoe",
        "privacy_level": "SELF_ONLY",
        "disable_comment": False,
        "disable_duet": False,
        "disable_stitch": False,
        "is_aigc": True,
    }
    assert fakes.tiktok_calls[0] == "/v2/post/publish/creator_info/query/"


def test_a_privacy_level_tiktok_does_not_offer_fails_before_anything_is_sent(committed, ready, fakes):
    fakes.tiktok_privacy_options = ["SELF_ONLY"]
    job, post = send(committed, ready, mode="direct", privacy="PUBLIC_TO_EVERYONE")
    assert job.status == "failed"
    assert (
        job.error
        == "TikTok không cho tài khoản này đăng ở mức riêng tư PUBLIC_TO_EVERYONE; các mức được phép: SELF_ONLY"
    )
    assert inits(fakes) == [] and post.remote_id is None


def test_a_token_about_to_end_is_refreshed_first_and_both_new_tokens_are_kept(committed, ready, fakes):
    _, _, _, _, connection_id = ready
    with committed() as db:
        connection = db.get(TikTokConnection, connection_id)
        connection.access_expires_at = datetime.now(UTC) + timedelta(minutes=2)
        old_refresh = crypto.decrypt(connection.refresh_token_encrypted)
        db.commit()
    job, _ = send(committed, ready)
    assert job.status == "done", (job.error, job.error_detail)
    assert fakes.tiktok_calls[0] == "/v2/oauth/token/"
    with committed() as db:
        connection = db.get(TikTokConnection, connection_id)
        new_refresh = crypto.decrypt(connection.refresh_token_encrypted)
        assert new_refresh != old_refresh and new_refresh in fakes.tiktok_refresh
        assert old_refresh not in fakes.tiktok_refresh  # TikTok spent it
        assert crypto.decrypt(connection.access_token_encrypted) in fakes.tiktok_access
        assert connection.access_expires_at > datetime.now(UTC) + timedelta(hours=23)


def test_a_revoked_connection_fails_the_job_and_asks_to_connect_again(committed, ready, fakes):
    _, _, _, _, connection_id = ready
    with committed() as db:
        db.get(TikTokConnection, connection_id).access_expires_at = datetime.now(UTC)
        db.commit()
    fakes.tiktok_refresh.clear()  # TikTok revoked the app's access
    job, post = send(committed, ready)
    assert job.status == "failed"
    assert job.error == tiktok_connections.RECONNECT
    assert "invalid_grant" in job.error_detail
    with committed() as db:
        connection = db.get(TikTokConnection, connection_id)
        assert connection.last_error and tiktok_connections.needs_reconnect(connection)
    assert inits(fakes) == [] and post.status == "pending"


def test_an_expired_access_token_on_a_call_is_named(committed, ready, fakes):
    fakes.tiktok_access.clear()
    job, _ = send(committed, ready)
    assert job.error == "Kết nối TikTok đã hết hạn, hãy kết nối lại"
    assert "access_token_invalid" in job.error_detail


def test_a_rate_limit_fails_the_job_without_trying_again(committed, ready, fakes):
    fakes.tiktok_init_error = "rate_limit_exceeded"
    job, post = send(committed, ready)
    assert job.error == "TikTok đang giới hạn tốc độ, thử lại sau"
    assert len(inits(fakes)) == 1 and post.remote_id is None


def test_an_unaudited_app_posting_publicly_is_explained(committed, ready, fakes):
    fakes.tiktok_unaudited = True
    job, _ = send(committed, ready, mode="direct", privacy="PUBLIC_TO_EVERYONE")
    assert job.error.startswith("App chưa qua duyệt TikTok")
    assert "unaudited_client_can_only_post_to_private_accounts" in job.error_detail


def test_a_post_still_processing_stays_pending_and_the_retry_goes_on_with_it(committed, ready, fakes, monkeypatch):
    monkeypatch.setattr(tiktok_publish, "WAIT_SECONDS", 0)
    fakes.tiktok_busy_reads = 100
    first, post = send(committed, ready)
    assert first.status == "failed" and first.error.startswith("TikTok xử lý video quá lâu")
    assert post.status == "pending" and post.remote_id
    fakes.tiktok_busy_reads = 0
    retry, post_again = send(committed, ready, retry_of=first.id)
    assert retry.status == "done", (retry.error, retry.error_detail)
    assert post_again.id == post.id and post_again.remote_id == post.remote_id
    assert post_again.status == "published"
    assert len(inits(fakes)) == 1  # TikTok was never asked for a second post
    with committed() as db:
        assert len(db.scalars(select(Publication)).all()) == 1


def test_a_retry_after_an_unfinished_upload_starts_over(committed, ready, fakes):
    fakes.tiktok_upload_fails = 1
    first, post = send(committed, ready)
    assert first.status == "failed"
    retry, post_again = send(committed, ready, retry_of=first.id)
    assert retry.status == "done", (retry.error, retry.error_detail)
    assert post_again.remote_id != post.remote_id and post_again.status == "published"
    assert len(inits(fakes)) == 2


def test_a_post_tiktok_failed_is_sent_again_on_retry(committed, ready, fakes):
    fakes.tiktok_post_fails = True
    first, post = send(committed, ready)
    assert first.status == "failed" and "video_pull_failed" in first.error
    fakes.tiktok_post_fails = False
    retry, post_again = send(committed, ready, retry_of=first.id)
    assert retry.status == "done" and post_again.remote_id != post.remote_id
