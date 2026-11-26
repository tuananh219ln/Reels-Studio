"""Uploading a video to YouTube private through the member's own connection
(docs/decisions/2026-11-17-youtube-private-upload.md): connecting, the endpoint, the job in process against the fake
Google and YouTube, and the readings that see the Short once its member made it public."""

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from conftest import login, make_user, make_video
from fake_services import FACEBOOK_PAGE, FACEBOOK_USER_TOKEN, GOOGLE_CODE, YOUTUBE_CHANNEL_ID
from sqlalchemy import delete, select
from worker_helpers import add_job, add_user, committed, job_row  # noqa: F401  (fixtures)

from reels_api import metrics, posts_board, youtube_connections, youtube_upload
from reels_api.models import (
    Channel,
    Fanpage,
    Job,
    KnowledgeTopic,
    Publication,
    Video,
    YouTubeConnection,
    YouTubeOAuthState,
)
from reels_api.storage import DirectoryStorage

MP4 = b"fake mp4 bytes " * 100
PLANNED = datetime(2030, 1, 2, 11, 0, tzinfo=UTC)


def _tokens(hours=1, refresh="refresh-yt") -> youtube_upload.Tokens:
    return youtube_upload.Tokens(
        scope=" ".join(youtube_upload.SCOPES),
        access_token="access-yt",
        refresh_token=refresh,
        access_expires_at=datetime.now(UTC) + timedelta(hours=hours),
    )


def _info(channel_id=YOUTUBE_CHANNEL_ID, title="Ăn Ngon Sống Khỏe", handle="@anngonsongkhoe"):
    return youtube_upload.ChannelInfo(channel_id=channel_id, title=title, handle=handle)


def mp4_video(db, storage, user, mp4=True) -> Video:
    video = make_video(db, storage, user, scene_count=1)
    video.caption, video.hashtags = "Ăn vừng đen mỗi sáng", ["#vungden"]
    if mp4:
        video.mp4_key = f"videos/{video.id}/video-x.mp4"
        storage.save_bytes(video.mp4_key, MP4)
        video.rendered_signature, video.approved_signature, video.review_status = "sig", "sig", "approved"
    db.commit()
    return video


def connected_channel(db, user, **info) -> Channel:
    connection = youtube_connections.connect(db, user.id, _tokens(), _info(**info))
    db.commit()
    return db.get(Channel, connection.channel_id)


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def upload(an, video, channel, title="Vừng đen buổi sáng", planned=PLANNED):
    body = {"channel_id": channel.id, "title": title, "planned_at": planned.isoformat() if planned else None}
    return an.post(f"/api/youtube/videos/{video.id}/upload", json=body)


# --- Connecting ---


def test_connecting_a_channel_through_google(an, db, me, fakes):
    started = an.get("/api/youtube/oauth/start")
    assert started.status_code == 200, started.text
    query = parse_qs(urlsplit(started.json()["url"]).query)
    assert query["access_type"] == ["offline"] and query["prompt"] == ["consent"]
    assert "https://www.googleapis.com/auth/youtube.upload" in query["scope"][0]
    back = an.get("/api/youtube/oauth/callback", params={"code": GOOGLE_CODE, "state": query["state"][0]})
    assert "youtube=connected" in back.text
    connection = db.scalar(select(YouTubeConnection))
    channel = db.get(Channel, connection.channel_id)
    assert (connection.owner_id, connection.google_channel_id) == (me.id, YOUTUBE_CHANNEL_ID)
    assert (channel.handle, channel.external_id, channel.name) == (
        "@anngonsongkhoe",
        YOUTUBE_CHANNEL_ID,
        "Ăn Ngon Sống Khỏe",
    )
    assert "g-access" not in connection.access_token_encrypted, "tokens are kept encrypted"
    mine = an.get("/api/youtube/connections").json()
    assert [(row["channel_id"], row["needs_reconnect"]) for row in mine] == [(channel.id, False)]
    assert not any("token" in key for key in mine[0])


def test_a_state_is_used_once(an, db, me, fakes):
    state = parse_qs(urlsplit(an.get("/api/youtube/oauth/start").json()["url"]).query)["state"][0]
    an.get("/api/youtube/oauth/callback", params={"code": GOOGLE_CODE, "state": state})
    again = an.get("/api/youtube/oauth/callback", params={"code": GOOGLE_CODE, "state": state})
    assert "youtube=error" in again.text
    assert db.scalar(select(YouTubeOAuthState)) is None


def test_connecting_reuses_the_channel_added_from_its_link(an, db, me, fakes):
    added = an.post("/api/channels", json={"url": "https://www.youtube.com/@AnNgonSongKhoe"})
    assert added.status_code == 201, added.text
    channel = connected_channel(db, me)
    assert channel.id == added.json()["id"]
    assert channel.external_id == YOUTUBE_CHANNEL_ID
    assert len(db.scalars(select(Channel)).all()) == 1


def test_a_channel_connected_by_another_member_is_refused(db, me):
    connected_channel(db, me)
    binh = make_user(db, email="binh@doi.vn", name="Bình")
    with pytest.raises(youtube_connections.ConnectError):
        youtube_connections.connect(db, binh.id, _tokens(), _info())


def test_a_connected_channel_is_disconnected_before_it_is_removed(an, db, me, fakes):
    channel = connected_channel(db, me)
    refused = an.delete(f"/api/channels/youtube/{channel.id}")
    assert refused.status_code == 409 and "ngắt kết nối" in refused.json()["message"]
    connection = youtube_connections.of_channel(db, channel.id)
    assert an.delete(f"/api/youtube/connections/{connection.id}").status_code == 200
    db.expire_all()
    assert youtube_connections.of_channel(db, channel.id) is None
    assert an.delete(f"/api/channels/youtube/{channel.id}").status_code == 200


# --- The endpoint ---


def test_upload_queues_a_private_upload_and_locks_the_video(an, db, me, storage):
    video = mp4_video(db, storage, me)
    channel = connected_channel(db, me)
    response = upload(an, video, channel)
    assert response.status_code == 201, response.text
    post = db.scalar(select(Publication).where(Publication.video_id == video.id))
    assert (post.platform, post.status, post.channel_id, post.created_by_id) == (
        "youtube",
        "pending",
        channel.id,
        me.id,
    )
    assert post.scheduled_at == PLANNED and post.caption == "Vừng đen buổi sáng"
    assert post.post_text.startswith("Ăn vừng đen mỗi sáng") and post.remote_mp4_key == video.mp4_key
    job = db.scalar(select(Job).where(Job.video_id == video.id))
    assert (job.kind, job.status, job.publication_id) == ("youtube_publish", "queued", post.id)
    payload = response.json()
    assert payload["locked"] is True
    (shown,) = payload["manual_posts"]
    assert (shown["status"], shown["channel"], shown["planned_at"]) == ("pending", "Ăn Ngon Sống Khỏe", None)


def test_upload_needs_the_members_own_connected_channel(an, db, me, storage):
    video = mp4_video(db, storage, me)
    binh = make_user(db, email="binh@doi.vn", name="Bình")
    theirs = connected_channel(db, binh)
    refused = upload(an, video, theirs)
    assert (refused.status_code, refused.json()["message"]) == (422, "Hãy chọn một kênh YouTube bạn đã kết nối")


def test_upload_checks_its_title_time_and_mp4(an, db, me, storage):
    channel = connected_channel(db, me)
    video = mp4_video(db, storage, me)
    assert upload(an, video, channel, title=" <> ").json()["message"] == "Hãy nhập tiêu đề video YouTube"
    past = datetime.now(UTC) - timedelta(hours=1)
    assert "đã qua" in upload(an, video, channel, planned=past).json()["message"]
    no_mp4 = mp4_video(db, storage, me, mp4=False)
    assert upload(an, no_mp4, channel).json()["message"] == "Video chưa render MP4 để đăng"
    assert upload(an, video, channel, planned=None).status_code == 201


def test_the_same_mp4_goes_to_a_channel_once(an, db, me, storage):
    video = mp4_video(db, storage, me)
    channel = connected_channel(db, me)
    upload(an, video, channel)
    post = db.scalar(select(Publication).where(Publication.video_id == video.id))
    post.status, post.external_id = "private", "ytUp0000001"
    db.scalar(select(Job).where(Job.video_id == video.id)).status = "done"
    db.commit()
    refused = upload(an, video, channel)
    assert refused.status_code == 409 and "đã tải lên kênh" in refused.json()["message"]


def test_an_upload_on_its_way_blocks_a_second_one_and_one_that_never_started_is_replaced(an, db, me, storage):
    video = mp4_video(db, storage, me)
    channel = connected_channel(db, me)
    upload(an, video, channel)
    db.scalar(select(Job).where(Job.video_id == video.id)).status = "failed"
    db.commit()
    assert upload(an, video, channel, title="Lần hai").status_code == 201
    posts = db.scalars(select(Publication).where(Publication.video_id == video.id).order_by(Publication.id)).all()
    assert [post.status for post in posts] == ["cancelled", "pending"]
    for job in db.scalars(select(Job).where(Job.video_id == video.id)):
        job.status = "failed"
    posts[1].upload_url = "https://upload.example/session"
    db.commit()
    refused = upload(an, video, channel)
    assert refused.status_code == 409 and "Thử lại" in refused.json()["message"]


def test_an_upload_on_its_way_cannot_be_removed(an, db, me, storage):
    video = mp4_video(db, storage, me)
    channel = connected_channel(db, me)
    upload(an, video, channel)
    post = db.scalar(select(Publication).where(Publication.video_id == video.id))
    refused = an.delete(f"/api/manual-posts/{post.id}")
    assert refused.status_code == 409


def test_a_private_upload_shows_its_planned_time_and_studio_link(an, db, me, storage):
    video = mp4_video(db, storage, me)
    channel = connected_channel(db, me)
    upload(an, video, channel)
    post = db.scalar(select(Publication).where(Publication.video_id == video.id))
    post.status, post.external_id = "private", "ytUp0000001"
    db.scalar(select(Job).where(Job.video_id == video.id)).status = "done"
    db.commit()
    (shown,) = an.get(f"/api/videos/{video.id}").json()["manual_posts"]
    assert shown["status"] == "private" and datetime.fromisoformat(shown["planned_at"]) == PLANNED
    assert shown["studio_url"] == "https://studio.youtube.com/video/ytUp0000001/edit"
    assert posts_board.state_of(post, failed=False) == "scheduled"


# --- A Page's YouTube channel ---


def test_a_pages_owner_sets_its_youtube_channel(an, db, me, fakes):
    (row,) = an.post("/api/fanpages", json={"token": FACEBOOK_USER_TOKEN, "page_ids": [FACEBOOK_PAGE]}).json()
    channel = connected_channel(db, me)
    (updated,) = an.put(f"/api/fanpages/{row['id']}/youtube-channel", json={"channel_id": channel.id}).json()
    assert updated["youtube_channel"] == {"id": channel.id, "name": "Ăn Ngon Sống Khỏe", "connected": True}
    assert db.get(Fanpage, row["id"]).youtube_channel_id == channel.id
    unconnected = Channel(
        platform="youtube", handle="@khac", name="Khác", url="https://www.youtube.com/@khac", created_by_id=me.id
    )
    db.add(unconnected)
    db.commit()
    refused = an.put(f"/api/fanpages/{row['id']}/youtube-channel", json={"channel_id": unconnected.id})
    assert refused.status_code == 422
    (cleared,) = an.put(f"/api/fanpages/{row['id']}/youtube-channel", json={"channel_id": None}).json()
    assert cleared["youtube_channel"] is None


# --- The job, in process ---


@pytest.fixture
def ready(committed, tmp_path, fakes):
    """A video with its MP4, and its author's YouTube channel connected through the fake Google."""
    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    with committed() as db:
        video = mp4_video(db, storage, user)
        tokens = youtube_upload.exchange_code(GOOGLE_CODE)
        connection = youtube_connections.connect(db, user.id, tokens, youtube_upload.my_channel(tokens.access_token))
        db.commit()
        channel_id, connection_id = connection.channel_id, connection.id
    fakes.youtube_upload_calls.clear()
    yield user, storage, video.id, channel_id, connection_id
    with committed() as db:
        db.execute(delete(YouTubeConnection))
        db.execute(delete(YouTubeOAuthState))
        db.execute(delete(Publication))
        db.execute(delete(Video))
        db.execute(delete(Channel))
        db.commit()


def send(committed, ready, retry_of=None) -> tuple[Job, Publication]:
    """Queue the upload as the endpoint does (or reuse the pending one, as "Thử lại" does) and run its job."""
    from reels_api import jobs

    user, storage, video_id, channel_id, _ = ready
    with committed() as db:
        post = db.scalar(select(Publication).where(Publication.video_id == video_id, Publication.status == "pending"))
        if post is None:
            video = db.get(Video, video_id)
            post = Publication(
                video_id=video_id,
                platform="youtube",
                status="pending",
                created_by_id=user.id,
                channel_id=channel_id,
                scheduled_at=PLANNED,
                remote_mp4_key=video.mp4_key,
                caption="Vừng đen <buổi sáng>",
                post_text="Ăn vừng đen mỗi sáng #vungden",
            )
            db.add(post)
            db.commit()
        post_id = post.id
    job_id = add_job(
        committed,
        video_id,
        user.id,
        kind="youtube_publish",
        status="running",
        publication_id=post_id,
        retry_of_id=retry_of,
    )
    jobs.run_job(job_id, committed, storage)
    with committed() as db:
        return job_row(committed, job_id), db.get(Publication, post_id)


def test_an_upload_goes_up_private_with_its_title_and_ai_label(committed, ready, fakes):
    job, post = send(committed, ready)
    assert job.status == "done", (job.error, job.error_detail)
    assert (post.status, post.external_id, post.upload_url) == ("private", "ytUp0000001", None)
    assert post.post_url == "https://www.youtube.com/shorts/ytUp0000001"
    assert post.scheduled_at == PLANNED, "the planned time stays as the reminder"
    (sent,) = fakes.youtube_uploads.values()
    assert sent["bytes"] == len(MP4)
    assert sent["body"]["status"] == {
        "privacyStatus": "private",
        "selfDeclaredMadeForKids": False,
        "containsSyntheticMedia": True,
    }
    assert sent["body"]["snippet"] == {
        "title": "Vừng đen buổi sáng",
        # Built at upload from the caption and the hashtags (the group has no "Mô tả YouTube"), not the post's snapshot.
        "description": "Ăn vừng đen mỗi sáng\n\n#vungden",
        "tags": ["vungden"],
    }
    assert fakes.youtube_upload_calls == ["init", "send"]


def test_a_caption_edited_after_the_post_was_made_reaches_youtube(committed, ready, fakes):
    """FoodDose 382 (2026-11-25): the description was the caption frozen when the post was made."""
    _, _, video_id, _, _ = ready
    with committed() as db:
        db.get(Video, video_id).caption = "Ăn vừng đen mỗi sáng, tóc đen và chắc hơn. Like and follow!"
        db.commit()
    job, post = send(committed, ready)
    assert job.status == "done", (job.error, job.error_detail)
    (sent,) = fakes.youtube_uploads.values()
    description = sent["body"]["snippet"]["description"]
    assert description == "Ăn vừng đen mỗi sáng, tóc đen và chắc hơn. Like and follow!\n\n#vungden"
    assert post.post_text == description, "the post keeps what YouTube got"


def test_the_groups_youtube_description_and_tags_replace_the_facebook_ones(committed, ready, fakes):
    _, _, video_id, channel_id, _ = ready
    with committed() as db:
        video = db.get(Video, video_id)
        video.caption, video.hashtags = "Ăn vừng đen mỗi sáng. #vungden #reels", ["#vungden", "#reels"]
        db.get(KnowledgeTopic, video.knowledge_topic_id).youtube_meta = {
            "hashtags": ["#FoodDose", "#Shorts"],
            "keywords": ["food is medicine"],
            "cta": "🔔 Subscribe to {channel}!",
            "disclaimer": "Not medical advice.",
        }
        channel_name = db.get(Channel, channel_id).name
        db.commit()
    try:
        job, post = send(committed, ready)
    finally:
        with committed() as db:
            db.get(KnowledgeTopic, db.get(Video, video_id).knowledge_topic_id).youtube_meta = None
            db.commit()
    assert job.status == "done", (job.error, job.error_detail)
    (sent,) = fakes.youtube_uploads.values()
    assert sent["body"]["snippet"]["description"] == (
        f"Ăn vừng đen mỗi sáng.\n\n🔔 Subscribe to {channel_name}!\n\nNot medical advice.\n\n#FoodDose #Shorts"
    )
    assert sent["body"]["snippet"]["tags"] == ["FoodDose", "Shorts", "food is medicine"]
    assert post.post_text == sent["body"]["snippet"]["description"]
    with committed() as db:
        assert db.get(Video, video_id).caption == "Ăn vừng đen mỗi sáng. #vungden #reels", "Facebook's caption stays"


def test_the_upload_carries_the_videos_hashtags_as_tags_cleaned_and_deduped(committed, ready, fakes):
    _, _, video_id, _, _ = ready
    with committed() as db:
        db.get(Video, video_id).hashtags = ["#threads", "#DocComment", "#threads", "#", "#xu<h>uong"]
        db.commit()
    job, _ = send(committed, ready)
    assert job.status == "done", (job.error, job.error_detail)
    (sent,) = fakes.youtube_uploads.values()
    assert sent["body"]["snippet"]["tags"] == ["threads", "DocComment", "xuhuong"]


def test_a_video_without_hashtags_is_uploaded_without_a_tags_field(committed, ready, fakes):
    _, _, video_id, _, _ = ready
    with committed() as db:
        db.get(Video, video_id).hashtags = []
        db.commit()
    job, _ = send(committed, ready)
    assert job.status == "done", (job.error, job.error_detail)
    (sent,) = fakes.youtube_uploads.values()
    assert "tags" not in sent["body"]["snippet"]


def test_the_tags_sent_stay_within_youtubes_500_characters(committed, ready, fakes):
    _, _, video_id, _, _ = ready
    with committed() as db:
        db.get(Video, video_id).hashtags = [f"#t{i:03d}{'x' * 20}" for i in range(40)]
        db.commit()
    job, _ = send(committed, ready)
    assert job.status == "done", (job.error, job.error_detail)
    (sent,) = fakes.youtube_uploads.values()
    tags = sent["body"]["snippet"]["tags"]
    assert 0 < len(tags) < 40 and sum(map(len, tags)) + len(tags) - 1 <= 500


def test_a_cut_upload_is_resumed_on_retry_and_never_doubled(committed, ready, fakes):
    fakes.youtube_upload_cuts = 1
    first, post = send(committed, ready)
    assert first.status == "failed" and "YouTube đang lỗi" in first.error
    assert post.status == "pending" and post.upload_url
    retry, again = send(committed, ready, retry_of=first.id)
    assert retry.status == "done", (retry.error, retry.error_detail)
    assert again.id == post.id and again.status == "private"
    assert len(fakes.youtube_uploads) == 1, "YouTube was never asked for a second video"
    assert fakes.youtube_upload_calls == ["init", "send", "query", "send"]


def test_a_retry_after_the_upload_finished_takes_the_video_youtube_holds(committed, ready, fakes):
    first, post = send(committed, ready)
    with committed() as db:
        row = db.get(Publication, post.id)
        # As if the answer to the last send was lost: still pending, with its session.
        row.status, row.external_id, row.post_url = "pending", None, None
        row.upload_url = f"{fakes.url}/youtube-upload/session/s1"
        db.commit()
    retry, again = send(committed, ready, retry_of=first.id)
    assert retry.status == "done" and again.external_id == "ytUp0000001"
    assert len(fakes.youtube_uploads) == 1


def test_an_access_token_about_to_end_is_refreshed_first(committed, ready, fakes):
    _, _, _, _, connection_id = ready
    with committed() as db:
        db.get(YouTubeConnection, connection_id).access_expires_at = datetime.now(UTC) + timedelta(minutes=1)
        db.commit()
    count = fakes.google_token_count
    job, post = send(committed, ready)
    assert job.status == "done" and post.status == "private"
    assert fakes.google_token_count == count + 1


def test_a_revoked_connection_fails_the_job_and_asks_to_connect_again(committed, ready, fakes):
    _, _, _, _, connection_id = ready
    with committed() as db:
        db.get(YouTubeConnection, connection_id).access_expires_at = datetime.now(UTC)
        db.commit()
    fakes.google_refresh.clear()
    job, post = send(committed, ready)
    assert job.status == "failed" and job.error == youtube_connections.RECONNECT
    with committed() as db:
        assert db.get(YouTubeConnection, connection_id).last_error is not None
    assert post.status == "pending" and fakes.youtube_upload_calls == []


def test_the_upload_limit_is_named(committed, ready, fakes):
    fakes.youtube_upload_error = "uploadLimitExceeded"
    job, _ = send(committed, ready)
    assert job.status == "failed" and "đủ số video" in job.error


# --- The readings see it once it is public ---


def private_post(db, storage, user, planned) -> Publication:
    video = mp4_video(db, storage, user)
    channel = connected_channel(db, user)
    post = Publication(
        video_id=video.id,
        platform="youtube",
        status="private",
        external_id="ytUp0000001",
        post_url="https://www.youtube.com/shorts/ytUp0000001",
        channel_id=channel.id,
        scheduled_at=planned,
        created_by_id=user.id,
    )
    db.add(post)
    db.commit()
    return post


def test_a_private_upload_is_not_read_before_its_planned_time(db, me, storage, fakes):
    private_post(db, storage, me, datetime.now(UTC) + timedelta(hours=2))
    assert metrics.due_posts(db, 50, "youtube") == []


def test_a_private_upload_still_hidden_is_looked_at_again_in_an_hour(db, me, storage, fakes):
    post = private_post(db, storage, me, datetime.now(UTC) - timedelta(minutes=5))
    fakes.youtube_gone.add("ytUp0000001")
    assert metrics.due_posts(db, 50, "youtube") == [post]
    metrics.measure_youtube(db, [post])
    assert post.status == "private" and post.gone_since is None and post.metrics_error is None
    assert post.next_snapshot_at - post.metrics_tried_at == timedelta(hours=1)


def test_a_private_upload_made_public_is_published(db, me, storage, fakes):
    post = private_post(db, storage, me, datetime.now(UTC) - timedelta(minutes=5))
    fakes.youtube_videos["ytUp0000001"] = {"views": 12, "published_at": "2026-11-17T04:00:00Z"}
    metrics.measure_youtube(db, [post])
    assert (post.status, post.scheduled_at) == ("published", None)
    assert post.published_at == datetime(2026, 11, 17, 4, tzinfo=UTC) and post.published_at_source == "api"
