"""Instagram Reels through the Facebook Page they are linked to (docs/specs/instagram-posting/brief.md): the Page check
reading the account, the endpoint (now or at a time, only by the Page's owner), the job in process against the fake
Instagram, the round that starts a post at its time, and Facebook's code leaving Instagram posts alone."""

from datetime import UTC, datetime, timedelta

import pytest
from conftest import login, make_user, make_video
from fake_services import FACEBOOK_PAGE, FACEBOOK_TOKEN, INSTAGRAM_USER, INSTAGRAM_USERNAME
from sqlalchemy import delete, select
from worker_helpers import add_job, add_user, committed, job_row  # noqa: F401  (fixtures)

from reels_api import fanpages, ig_publish, instagram, jobs, worker
from reels_api.models import Fanpage, Job, Publication, Video
from reels_api.storage import DirectoryStorage
from reels_api.videos import render_signature, split_scenes

MP4 = b"fake mp4 bytes " * 100


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def mp4_video(db, storage, user) -> Video:
    video = make_video(db, storage, user, scene_count=1)
    video.caption, video.hashtags = "Ăn vừng đen mỗi sáng", ["#vungden"]
    video.mp4_key = f"videos/{video.id}/video-x.mp4"
    storage.save_bytes(video.mp4_key, MP4)
    title, scenes = split_scenes(db, video)
    video.rendered_signature = render_signature(video, title, scenes)
    db.commit()
    return video


def linked_page(db, user, linked=True) -> Fanpage:
    row = fanpages.save(db, FACEBOOK_PAGE, "Trang Dưỡng Sinh", FACEBOOK_TOKEN, user.id)
    if linked:
        row.instagram_user_id, row.instagram_username = INSTAGRAM_USER, INSTAGRAM_USERNAME
    db.commit()
    return row


def in_minutes(minutes: float) -> str:
    return (datetime.now(UTC) + timedelta(minutes=minutes)).isoformat()


def post_to(an, video, page, scheduled_at=None):
    return an.post(
        f"/api/instagram/videos/{video.id}/publish", json={"fanpage_id": page.id, "scheduled_at": scheduled_at}
    )


# --- The Page's account ---


def test_the_page_check_reads_its_instagram_account(db, me, fakes):
    row = linked_page(db, me, linked=False)
    fanpages.check(db, row)
    assert (row.instagram_user_id, row.instagram_username) == (INSTAGRAM_USER, INSTAGRAM_USERNAME)

    fakes.instagram_refusal = 10
    fanpages.check(db, row)
    assert row.instagram_user_id == INSTAGRAM_USER, "a token without Instagram's permission keeps what was read"
    assert row.check_error is None, "the Page itself still works"
    assert "Không đọc được Instagram" in row.instagram_error

    fakes.instagram_refusal, fakes.instagram_account = None, None
    fanpages.check(db, row)
    assert (row.instagram_user_id, row.instagram_username) == (None, None)


def test_the_account_is_found_when_only_its_username_cannot_be_read(db, me, fakes):
    fakes.instagram_username_refused = True
    row = linked_page(db, me, linked=False)
    fanpages.check(db, row)
    assert (row.instagram_user_id, row.instagram_username, row.instagram_error) == (INSTAGRAM_USER, None, None)


def test_an_account_linked_as_connected_instagram_account_counts(db, me, fakes):
    fakes.instagram_link_field = "connected_instagram_account"
    row = linked_page(db, me, linked=False)
    fanpages.check(db, row)
    assert (row.instagram_user_id, row.instagram_username) == (INSTAGRAM_USER, INSTAGRAM_USERNAME)


def test_why_the_account_was_not_read_shows_on_the_pages_list(an, db, me, fakes):
    fakes.instagram_refusal = 10
    row = linked_page(db, me, linked=False)
    fanpages.check(db, row)
    (listed,) = an.get("/api/fanpages").json()
    assert listed["instagram"] is None
    assert listed["instagram_error"].startswith("Không đọc được Instagram")


def test_the_pages_list_and_the_video_show_the_linked_account(an, db, me, storage):
    page = linked_page(db, me)
    video = mp4_video(db, storage, me)
    (row,) = an.get("/api/fanpages").json()
    assert row["instagram"] == {"id": INSTAGRAM_USER, "username": INSTAGRAM_USERNAME}
    (shown,) = an.get(f"/api/videos/{video.id}").json()["fanpages"]
    assert (shown["id"], shown["instagram_username"]) == (page.id, INSTAGRAM_USERNAME)


# --- The endpoint ---


def test_posting_now_queues_the_job_with_the_caption(an, db, me, storage):
    page = linked_page(db, me)
    video = mp4_video(db, storage, me)
    response = post_to(an, video, page)
    assert response.status_code == 201, response.text
    assert response.json()["active_job"]["kind"] == "ig_publish"
    post = db.scalar(select(Publication).where(Publication.platform == "instagram"))
    assert (post.status, post.fanpage_id, post.created_by_id, post.remote_mp4_key, post.scheduled_at) == (
        "pending",
        page.id,
        me.id,
        video.mp4_key,
        None,
    )
    assert post.post_text == "Ăn vừng đen mỗi sáng\n\n#vungden"
    job = db.scalar(select(Job).where(Job.video_id == video.id))
    assert (job.kind, job.publication_id) == ("ig_publish", post.id)
    refused = an.patch(f"/api/videos/{video.id}", json={"caption": "khác"})
    assert (refused.status_code, refused.json()["message"]) == (409, "Video đang đăng lên Instagram, chưa lưu")


def test_a_post_for_later_waits_without_a_job_and_is_not_out_yet(an, db, me, storage):
    page = linked_page(db, me)
    video = mp4_video(db, storage, me)
    response = post_to(an, video, page, in_minutes(60))
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["active_job"] is None
    (shown,) = payload["manual_posts"]
    assert (shown["platform"], shown["status"], shown["source"], shown["fanpage"]) == (
        "instagram",
        "scheduled",
        "app_api",
        "Trang Dưỡng Sinh",
    )
    assert shown["scheduled_at"] is not None
    assert "instagram" not in payload["posted_on"]
    assert db.scalar(select(Job).where(Job.video_id == video.id)) is None


@pytest.mark.parametrize("minutes", [14, 29 * 24 * 60 + 5])
def test_the_time_follows_facebooks_limits(an, db, me, storage, minutes):
    page = linked_page(db, me)
    video = mp4_video(db, storage, me)
    refused = post_to(an, video, page, in_minutes(minutes))
    assert (refused.status_code, refused.json()["message"]) == (
        422,
        "Giờ hẹn phải sau ít nhất 15 phút và trong vòng 29 ngày tới",
    )


def test_only_the_pages_owner_posts(client, db, me, storage):
    page = linked_page(db, me)
    video = mp4_video(db, storage, me)
    make_user(db, email="binh@doi.vn", name="Bình")
    login(client, "binh@doi.vn")
    refused = post_to(client, video, page)
    assert (refused.status_code, refused.json()["code"]) == (403, "not_page_owner")


def test_a_page_without_instagram_is_refused(an, db, me, storage):
    page = linked_page(db, me, linked=False)
    video = mp4_video(db, storage, me)
    refused = post_to(an, video, page)
    assert refused.status_code == 422
    assert "chưa liên kết tài khoản Instagram" in refused.json()["message"]


def test_the_same_mp4_goes_to_the_account_once(an, db, me, storage):
    page = linked_page(db, me)
    video = mp4_video(db, storage, me)
    assert post_to(an, video, page, in_minutes(60)).status_code == 201
    again = post_to(an, video, page, in_minutes(120))
    assert (again.status_code, again.json()["code"]) == (409, "instagram_already_posted")


def test_a_post_for_later_is_cancelled_before_its_time(an, db, me, storage):
    page = linked_page(db, me)
    video = mp4_video(db, storage, me)
    post_to(an, video, page, in_minutes(60))
    post = db.scalar(select(Publication).where(Publication.platform == "instagram"))
    response = an.post(f"/api/instagram/posts/{post.id}/cancel")
    assert response.status_code == 200, response.text
    assert response.json()["manual_posts"] == []
    db.refresh(post)
    assert post.status == "cancelled"
    assert an.post(f"/api/instagram/posts/{post.id}/cancel").status_code == 409


def test_facebooks_take_down_and_check_leave_instagram_posts_alone(an, db, me, storage):
    page = linked_page(db, me)
    video = mp4_video(db, storage, me)
    post_to(an, video, page, in_minutes(60))
    post = db.scalar(select(Publication).where(Publication.platform == "instagram"))
    post.remote_id = "17900000000001"
    db.commit()
    assert an.post(f"/api/posts/{post.id}/take-down").status_code == 404
    assert an.post(f"/api/posts/{post.id}/check").status_code == 409


def test_the_caption_keeps_thirty_hashtags_and_2200_characters():
    tags = " ".join(f"#t{index}" for index in range(35))
    kept = instagram.caption(f"Vừng đen\n\n{tags}")
    assert kept.count("#") == 30 and "#t29" in kept and "#t30" not in kept
    assert len(instagram.caption("a" * 3000)) == 2200


# --- The job ---


@pytest.fixture
def ready(committed, tmp_path, fakes, monkeypatch):
    """A video with its MP4, on a Page linked to the fake Instagram account."""
    monkeypatch.setattr(ig_publish, "POLL_SECONDS", 0)
    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    with committed() as db:
        video = mp4_video(db, storage, user)
        page = linked_page(db, user)
        ids = video.id, page.id
    yield user, storage, *ids
    with committed() as db:
        db.execute(delete(Publication))
        db.execute(delete(Video))
        db.execute(delete(Fanpage))
        db.commit()


def send(committed, ready, retry_of=None) -> tuple[Job, Publication]:
    """Queue the post as the endpoint does (or reuse the pending one, as "Thử lại" does) and run its job."""
    user, storage, video_id, page_id = ready
    with committed() as db:
        post = db.scalar(select(Publication).where(Publication.video_id == video_id, Publication.status == "pending"))
        if post is None:
            video = db.get(Video, video_id)
            post = Publication(
                video_id=video_id,
                platform="instagram",
                status="pending",
                created_by_id=user.id,
                fanpage_id=page_id,
                remote_mp4_key=video.mp4_key,
                post_text="Ăn vừng đen mỗi sáng\n\n#vungden",
            )
            db.add(post)
            db.commit()
        post_id = post.id
    job_id = add_job(
        committed, video_id, user.id, kind="ig_publish", status="running", publication_id=post_id, retry_of_id=retry_of
    )
    jobs.run_job(job_id, committed, storage)
    with committed() as db:
        return job_row(committed, job_id), db.get(Publication, post_id)


def test_a_reel_goes_out_with_its_caption_and_link(committed, ready, fakes):
    fakes.instagram_busy_reads = 2
    job, post = send(committed, ready)
    assert job.status == "done", (job.error, job.error_detail)
    ((container_id, container),) = fakes.instagram_containers.items()
    (media,) = fakes.instagram_media
    assert (container["caption"], container["bytes"], container["state"]) == (
        "Ăn vừng đen mỗi sáng\n\n#vungden",
        len(MP4),
        "PUBLISHED",
    )
    assert (post.status, post.remote_id, post.external_id, post.post_url) == (
        "published",
        container_id,
        media["id"],
        media["permalink"],
    )
    assert post.finish_sent_at is not None and post.published_at is not None
    assert fakes.instagram_calls == ["container", "upload", "status", "status", "status", "publish", "permalink"]


def test_a_container_instagram_cannot_process_fails_and_a_retry_starts_over(committed, ready, fakes):
    fakes.instagram_container_error = True
    job, post = send(committed, ready)
    assert (job.status, job.error) == ("failed", "Instagram không xử lý được video (ERROR)")
    assert post.status == "pending" and post.finish_sent_at is None
    fakes.instagram_container_error = False
    retried, post = send(committed, ready, retry_of=job.id)
    assert retried.status == "done", (retried.error, retried.error_detail)
    assert len(fakes.instagram_containers) == 2 and len(fakes.instagram_media) == 1
    assert post.status == "published"


def test_a_lost_publish_answer_is_found_and_never_posted_twice(committed, ready, fakes):
    fakes.instagram_publish_replies_lost = 1
    job, post = send(committed, ready)
    assert job.status == "failed"
    assert post.status == "pending" and post.finish_sent_at is not None
    retried, post = send(committed, ready, retry_of=job.id)
    assert retried.status == "done", (retried.error, retried.error_detail)
    assert fakes.instagram_calls.count("publish") == 1 and fakes.instagram_calls.count("container") == 1
    (media,) = fakes.instagram_media
    assert (post.status, post.external_id) == ("published", media["id"])


def test_the_file_goes_to_the_uri_the_container_returned(committed, ready, fakes):
    job, _ = send(committed, ready)
    assert job.status == "done", (job.error, job.error_detail)
    (path,) = fakes.instagram_upload_paths
    assert path.startswith("/instagram-upload/ig-api-upload/v99.0/"), "the returned uri, not the built address"


def test_a_uri_on_another_host_is_not_trusted_with_the_token(monkeypatch):
    monkeypatch.setattr(
        instagram.config, "instagram_upload_url", lambda: "https://rupload.facebook.com/ig-api-upload/v26.0"
    )
    own = "https://rupload.facebook.com/ig-api-upload/v27.0/1"
    assert instagram.upload_target("1", own) == own
    assert (
        instagram.upload_target("1", "https://evil.example/x/1") == "https://rupload.facebook.com/ig-api-upload/v26.0/1"
    )
    assert instagram.upload_target("1") == "https://rupload.facebook.com/ig-api-upload/v26.0/1"


def test_a_multi_megabyte_file_is_uploaded_whole(committed, ready, fakes):
    _, storage, video_id, _ = ready
    with committed() as db:
        key = db.get(Video, video_id).mp4_key
    big = b"\x00" * (6 * 1024 * 1024)
    storage.save_bytes(key, big)
    job, _ = send(committed, ready)
    assert job.status == "done", (job.error, job.error_detail)
    ((_, container),) = fakes.instagram_containers.items()
    assert container["bytes"] == len(big)


def test_the_upload_servers_own_refusal_shows_in_the_job(committed, ready, fakes):
    fakes.instagram_upload_refused = True
    job, post = send(committed, ready)
    assert job.status == "failed"
    assert job.error == "Instagram không nhận file video (ProcessingFailedError: Request processing failed)"
    assert "debug_info" in job.error_detail
    assert post.status == "pending"


def test_the_job_log_carries_the_raw_error_detail(an, db, me, storage):
    video = mp4_video(db, storage, me)
    job = Job(
        video_id=video.id,
        kind="ig_publish",
        status="failed",
        created_by_id=me.id,
        error="Instagram không nhận file video (ProcessingFailedError: Request processing failed)",
        error_detail='HTTP 400: {"debug_info": {"type": "ProcessingFailedError"}}',
    )
    db.add(job)
    db.commit()
    row = next(row for row in an.get("/api/jobs").json() if row["id"] == job.id)
    assert row["error_detail"] == job.error_detail


def test_with_a_public_address_instagram_fetches_the_mp4_itself(committed, ready, fakes, monkeypatch):
    monkeypatch.setenv("INSTAGRAM_VIDEO_BASE_URL", "https://studio.example.com")
    job, post = send(committed, ready)
    assert job.status == "done", (job.error, job.error_detail)
    ((_, container),) = fakes.instagram_containers.items()
    link = container["video_url"]
    assert link.startswith("https://studio.example.com/api/instagram/media/") and link.endswith("/video.mp4")
    assert "upload" not in fakes.instagram_calls and fakes.instagram_upload_paths == []
    assert post.status == "published"


def test_without_a_public_address_the_file_is_uploaded(committed, ready, fakes, monkeypatch):
    monkeypatch.setenv("INSTAGRAM_VIDEO_BASE_URL", "")
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:3000")
    job, _ = send(committed, ready)
    assert job.status == "done", (job.error, job.error_detail)
    assert "upload" in fakes.instagram_calls
    ((_, container),) = fakes.instagram_containers.items()
    assert container["video_url"] == ""


def test_the_link_serves_one_pending_posts_mp4_to_anyone(client, db, me, storage, monkeypatch):
    monkeypatch.setenv("INSTAGRAM_VIDEO_BASE_URL", "https://studio.example.com")
    video = mp4_video(db, storage, me)
    page = linked_page(db, me)
    post = Publication(
        video_id=video.id,
        platform="instagram",
        status="pending",
        created_by_id=me.id,
        fanpage_id=page.id,
        remote_mp4_key=video.mp4_key,
    )
    db.add(post)
    db.commit()
    path = instagram.video_link(post.id).removeprefix("https://studio.example.com")
    got = client.get(path)  # not signed in
    assert (got.status_code, got.content, got.headers["content-type"]) == (200, MP4, "video/mp4")
    assert client.get("/api/instagram/media/not-a-token/video.mp4").status_code == 404
    assert instagram.link_post_id("not-a-token") is None
    post.status = "published"
    db.commit()
    assert client.get(path).status_code == 404, "once posted, the link no longer serves the file"


def test_a_token_without_instagrams_permission_says_so(committed, ready, fakes):
    fakes.instagram_refusal = 10
    job, post = send(committed, ready)
    assert (job.status, job.error) == ("failed", instagram.NO_PERMISSION)
    assert post.status == "pending"


# --- The round that starts a post at its time ---


def scheduled_post(db, video_id, page_id, user_id, at) -> Publication:
    post = Publication(
        video_id=video_id,
        platform="instagram",
        status="scheduled",
        scheduled_at=at,
        created_by_id=user_id,
        fanpage_id=page_id,
        post_text="x",
    )
    db.add(post)
    db.commit()
    return post


def test_the_round_starts_a_post_at_its_time_only(committed, ready):
    user, _, video_id, page_id = ready
    with committed() as db:
        post = scheduled_post(db, video_id, page_id, user.id, datetime.now(UTC) + timedelta(minutes=10))
        jobs.queue_instagram_posts(db)
        db.commit()
        assert db.scalar(select(Job).where(Job.video_id == video_id)) is None
        post.scheduled_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
        jobs.queue_instagram_posts(db)
        db.commit()
        db.refresh(post)
        job = db.scalar(select(Job).where(Job.video_id == video_id))
        assert post.status == "pending"
        assert (job.kind, job.status, job.publication_id) == ("ig_publish", "queued", post.id)


def test_a_post_over_a_day_late_is_cancelled_with_the_reason(committed, ready):
    user, _, video_id, page_id = ready
    with committed() as db:
        post = scheduled_post(db, video_id, page_id, user.id, datetime.now(UTC) - timedelta(hours=25))
        jobs.queue_instagram_posts(db)
        db.commit()
        db.refresh(post)
        job = db.scalar(select(Job).where(Job.video_id == video_id))
        assert post.status == "cancelled"
        assert (job.kind, job.status) == ("ig_publish", "failed")
        assert "Quá giờ hẹn hơn 24 giờ" in job.error


def test_facebooks_round_of_checks_leaves_instagram_posts_alone(committed, ready):
    user, _, video_id, page_id = ready
    with committed() as db:
        post = scheduled_post(db, video_id, page_id, user.id, datetime.now(UTC) - timedelta(hours=1))
        post.remote_id = "17900000000001"
        db.commit()
        jobs.queue_post_checks(db)
        db.commit()
        assert db.scalar(select(Job).where(Job.kind == "check")) is None


# --- A worker restart in the middle of a post ---


def test_a_post_cut_off_by_a_worker_restart_is_queued_again_once_and_goes_out_once(committed, ready, fakes):
    user, storage, video_id, page_id = ready
    fakes.instagram_publish_replies_lost = 1  # the Reel went out, but the worker died before hearing so
    cut, post = send(committed, ready)
    with committed() as db:
        db.get(Job, cut.id).status, db.get(Job, cut.id).error = "running", None
        db.commit()

    worker.recover_interrupted(committed)

    with committed() as db:
        old = db.get(Job, cut.id)
        again = db.scalar(select(Job).where(Job.video_id == video_id, Job.status == "queued"))
        assert (old.status, old.error) == ("failed", worker.RESTARTED)
        assert (again.kind, again.publication_id, again.retry_of_id, again.created_by_id) == (
            "ig_publish",
            post.id,
            cut.id,
            user.id,
        )
        again_id = again.id
        again.status = "running"  # claimed, as the worker does with any queued job
        db.commit()
    jobs.run_job(again_id, committed, storage)
    done = job_row(committed, again_id)
    assert done.status == "done", (done.error, done.error_detail)
    assert fakes.instagram_calls.count("publish") == 1, "never posted twice"
    with committed() as db:
        assert db.get(Publication, post.id).status == "published"


def test_a_post_cut_off_twice_waits_for_thu_lai(committed, ready):
    user, _, video_id, _ = ready
    first = add_job(committed, video_id, user.id, kind="ig_publish", status="running", publication_id=1)
    worker.recover_interrupted(committed)
    with committed() as db:
        again = db.scalar(select(Job).where(Job.video_id == video_id, Job.status == "queued"))
        again.status = "running"
        db.commit()
        again_id = again.id

    worker.recover_interrupted(committed)

    with committed() as db:
        statuses = [(j.id, j.status) for j in db.scalars(select(Job).where(Job.video_id == video_id).order_by(Job.id))]
        assert statuses == [(first, "failed"), (again_id, "failed")], "a second restart does not queue it again"
        assert db.get(Job, again_id).error == worker.RESTARTED


def test_other_jobs_cut_off_by_a_restart_are_still_not_run_again(committed, ready):
    user, _, video_id, _ = ready
    add_job(committed, video_id, user.id, kind="publish", status="running")
    worker.recover_interrupted(committed)
    with committed() as db:
        assert [j.status for j in db.scalars(select(Job).where(Job.video_id == video_id))] == ["failed"]
