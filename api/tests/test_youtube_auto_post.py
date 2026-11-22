"""A video that is out on Facebook at its slot is uploaded, private, by the worker's round to the YouTube channel of its
Page, when the Page's owner turned the switch on. YouTube's upload is the one of the "Tải lên YouTube" card."""

from datetime import UTC, datetime, timedelta

import pytest
from conftest import login, make_user, make_video
from fake_services import FACEBOOK_PAGE, FACEBOOK_TOKEN, FACEBOOK_USER_TOKEN
from sqlalchemy import select

from reels_api import fanpages, hashtags, youtube_connections, youtube_upload
from reels_api.jobs import queue_youtube_auto_posts
from reels_api.models import Channel, Fanpage, Job, Publication, YouTubeConnection
from reels_api.sessions import now
from reels_api.videos import split_scenes, title_of

URL = "/api/fanpages"


def connect_channel(db, user, channel_id="UCauto0000000000000000a", title="Tiệm Đọc Comment") -> Channel:
    tokens = youtube_upload.Tokens(
        scope=" ".join(youtube_upload.SCOPES),
        access_token="access-yt",
        refresh_token="refresh-yt",
        access_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    info = youtube_upload.ChannelInfo(channel_id=channel_id, title=title, handle="@tiemdoccomment")
    connection = youtube_connections.connect(db, user.id, tokens, info)
    db.commit()
    return db.get(Channel, connection.channel_id)


@pytest.fixture
def me(db):
    return make_user(db)


def page_with_channel(db, me, auto=True, channel=True):
    page = fanpages.save(db, FACEBOOK_PAGE, "Tiệm Đọc Comment", FACEBOOK_TOKEN, me.id)
    page.owner_id = me.id
    page.youtube_auto = auto
    if channel:
        page.youtube_channel_id = connect_channel(db, me).id
    db.commit()
    return page


def due_post(db, storage, me, page, status="scheduled", minutes_ago=5, count=1):
    video = make_video(db, storage, me)
    video.mp4_key = f"videos/{video.id}/video-x.mp4"
    video.caption, video.hashtags = "Ăn vừng đen mỗi sáng", ["#vungden"]
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


def youtube_posts(db, video):
    return db.scalars(
        select(Publication).where(Publication.video_id == video.id, Publication.platform == "youtube")
    ).all()


def run(db):
    queue_youtube_auto_posts(db)
    db.commit()


def test_a_due_facebook_post_uploads_to_youtube(db, me, storage):
    page = page_with_channel(db, me)
    video = due_post(db, storage, me, page)
    run(db)
    (post,) = youtube_posts(db, video)
    assert (post.status, post.fanpage_id, post.created_by_id, post.scheduled_at) == ("pending", page.id, me.id, None)
    assert (post.channel_id, post.remote_mp4_key) == (page.youtube_channel_id, video.mp4_key)
    title_scene, _ = split_scenes(db, video)
    assert post.caption == title_of(video, title_scene)
    assert post.post_text == hashtags.post_text(video.caption, video.hashtags)
    job = db.scalar(select(Job).where(Job.video_id == video.id, Job.kind == "youtube_publish"))
    assert (job.status, job.publication_id, job.created_by_id) == ("queued", post.id, me.id)


def test_a_published_facebook_post_counts_too(db, me, storage):
    video = due_post(db, storage, me, page_with_channel(db, me), status="published")
    run(db)
    assert len(youtube_posts(db, video)) == 1


def test_a_page_with_the_switch_off_uploads_nothing(db, me, storage):
    video = due_post(db, storage, me, page_with_channel(db, me, auto=False))
    run(db)
    assert youtube_posts(db, video) == []


def test_a_page_without_a_channel_uploads_nothing(db, me, storage):
    video = due_post(db, storage, me, page_with_channel(db, me, channel=False))
    run(db)
    assert youtube_posts(db, video) == []


def test_a_channel_dropped_after_the_switch_uploads_nothing(db, me, storage):
    page = page_with_channel(db, me)
    video = due_post(db, storage, me, page)
    page.youtube_channel_id = None
    db.commit()
    run(db)
    assert youtube_posts(db, video) == []


def test_a_page_without_an_owner_uploads_nothing(db, me, storage):
    page = page_with_channel(db, me)
    video = due_post(db, storage, me, page)
    page.owner_id = None
    db.commit()
    run(db)
    assert youtube_posts(db, video) == []


def test_a_channel_connected_by_someone_else_uploads_nothing(db, me, storage):
    page = page_with_channel(db, me)
    video = due_post(db, storage, me, page)
    binh = make_user(db, email="binh@doi.vn", name="Trần Bình")
    db.get(YouTubeConnection, db.scalar(select(YouTubeConnection.id))).owner_id = binh.id
    db.commit()
    run(db)
    assert youtube_posts(db, video) == []


def test_a_connection_that_ran_out_is_skipped_then_caught_up_once_renewed(db, me, storage):
    page = page_with_channel(db, me)
    video = due_post(db, storage, me, page)
    connection = youtube_connections.of_channel(db, page.youtube_channel_id)
    connection.last_error = "invalid_grant"
    db.commit()
    run(db)
    assert youtube_posts(db, video) == []
    assert db.scalars(select(Job).where(Job.video_id == video.id, Job.kind == "youtube_publish")).all() == []
    connection.last_error = None
    db.commit()
    run(db)
    assert len(youtube_posts(db, video)) == 1


@pytest.mark.parametrize("existing", ["pending", "private", "scheduled", "published", "failed"])
def test_a_video_already_on_the_channel_is_not_uploaded_again(db, me, storage, existing):
    page = page_with_channel(db, me)
    video = due_post(db, storage, me, page)
    db.add(
        Publication(
            video_id=video.id,
            platform="youtube",
            status=existing,
            channel_id=page.youtube_channel_id,
            created_by_id=me.id,
        )
    )
    db.commit()
    run(db)
    assert len(youtube_posts(db, video)) == 1


def test_a_cancelled_upload_does_not_block_it(db, me, storage):
    page = page_with_channel(db, me)
    video = due_post(db, storage, me, page)
    db.add(
        Publication(
            video_id=video.id,
            platform="youtube",
            status="cancelled",
            channel_id=page.youtube_channel_id,
            created_by_id=me.id,
        )
    )
    db.commit()
    run(db)
    assert len(youtube_posts(db, video)) == 2


def test_an_upload_to_another_channel_does_not_block_this_one(db, me, storage):
    page = page_with_channel(db, me)
    video = due_post(db, storage, me, page)
    other = Channel(
        platform="youtube", handle="@khac", name="Kênh khác", url="https://youtube.com/@khac", created_by_id=me.id
    )
    db.add(other)
    db.flush()
    db.add(
        Publication(video_id=video.id, platform="youtube", status="private", channel_id=other.id, created_by_id=me.id)
    )
    db.commit()
    run(db)
    assert len(youtube_posts(db, video)) == 2


def test_a_busy_video_waits_for_the_next_round(db, me, storage):
    video = due_post(db, storage, me, page_with_channel(db, me))
    job = Job(video_id=video.id, kind="ig_publish", status="running", created_by_id=me.id)
    db.add(job)
    db.commit()
    run(db)
    assert youtube_posts(db, video) == []
    job.status = "done"
    db.commit()
    run(db)
    assert len(youtube_posts(db, video)) == 1


def test_a_slot_older_than_a_day_is_left_alone(db, me, storage):
    video = due_post(db, storage, me, page_with_channel(db, me), minutes_ago=25 * 60)
    run(db)
    assert youtube_posts(db, video) == []


def test_a_slot_still_ahead_uploads_nothing(db, me, storage):
    video = due_post(db, storage, me, page_with_channel(db, me), minutes_ago=-30)
    run(db)
    assert youtube_posts(db, video) == []


def test_a_post_now_without_a_slot_uploads_nothing(db, me, storage):
    video = due_post(db, storage, me, page_with_channel(db, me), status="published", minutes_ago=None)
    run(db)
    assert youtube_posts(db, video) == []


@pytest.mark.parametrize("status", ["pending", "cancelled", "deleted"])
def test_only_a_reel_that_is_out_or_scheduled_counts(db, me, storage, status):
    video = due_post(db, storage, me, page_with_channel(db, me), status=status)
    run(db)
    assert youtube_posts(db, video) == []


def test_a_video_without_an_mp4_uploads_nothing(db, me, storage):
    video = due_post(db, storage, me, page_with_channel(db, me))
    video.mp4_key = None
    db.commit()
    run(db)
    assert youtube_posts(db, video) == []


def test_two_facebook_posts_of_a_video_make_one_upload(db, me, storage):
    video = due_post(db, storage, me, page_with_channel(db, me), count=2)
    run(db)
    assert len(youtube_posts(db, video)) == 1


def test_the_round_does_not_queue_twice(db, me, storage):
    video = due_post(db, storage, me, page_with_channel(db, me))
    run(db)
    run(db)
    assert len(youtube_posts(db, video)) == 1


# The switch on the Page.


@pytest.fixture
def an(client, me):
    login(client)
    return client


def connect(an):
    (row,) = an.post(URL, json={"token": FACEBOOK_USER_TOKEN, "page_ids": [FACEBOOK_PAGE]}).json()
    return row


def test_a_new_page_has_the_switch_off(an, fakes):
    assert connect(an)["youtube_auto"] is False


def test_the_owner_turns_the_switch_on_and_off(an, db, me, fakes):
    row = connect(an)
    db.get(Fanpage, row["id"]).youtube_channel_id = connect_channel(db, me).id
    db.commit()
    (on,) = an.put(f"{URL}/{row['id']}/youtube-auto", json={"auto": True}).json()
    assert on["youtube_auto"] is True
    (off,) = an.put(f"{URL}/{row['id']}/youtube-auto", json={"auto": False}).json()
    assert off["youtube_auto"] is False


def test_a_page_without_a_channel_cannot_be_switched_on(an, fakes):
    row = connect(an)
    refused = an.put(f"{URL}/{row['id']}/youtube-auto", json={"auto": True})
    assert (refused.status_code, refused.json()["message"]) == (
        422,
        "Page chưa chọn kênh YouTube, hãy chọn kênh rồi bật lại",
    )


def test_a_channel_that_ran_out_cannot_be_switched_on(an, db, me, fakes):
    row = connect(an)
    channel = connect_channel(db, me)
    db.get(Fanpage, row["id"]).youtube_channel_id = channel.id
    youtube_connections.of_channel(db, channel.id).last_error = "invalid_grant"
    db.commit()
    refused = an.put(f"{URL}/{row['id']}/youtube-auto", json={"auto": True})
    assert (refused.status_code, refused.json()["message"]) == (422, youtube_connections.RECONNECT)
    assert db.get(Fanpage, row["id"]).youtube_auto is False


def test_only_the_pages_owner_switches_it(an, client, db, me, fakes):
    row = connect(an)
    db.get(Fanpage, row["id"]).youtube_channel_id = connect_channel(db, me).id
    db.commit()
    make_user(db, email="binh@doi.vn", name="Trần Bình")
    login(client, "binh@doi.vn")
    refused = client.put(f"{URL}/{row['id']}/youtube-auto", json={"auto": True})
    assert (refused.status_code, refused.json()["message"]) == (
        403,
        "Chỉ chủ của Fanpage mới đổi được cách tự đăng YouTube",
    )
    assert db.get(Fanpage, row["id"]).youtube_auto is False
