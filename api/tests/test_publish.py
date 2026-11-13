import io
from datetime import UTC, datetime, timedelta

import pytest
from conftest import clip_bytes, login, make_user, make_video, needs_ffmpeg
from fake_services import FACEBOOK_PAGE, FACEBOOK_TOKEN
from PIL import Image
from sqlalchemy import select, update
from worker_helpers import add_job, add_user, committed, job_row  # noqa: F401  (fixtures)

from reels_api import facebook, fanpages
from reels_api.models import Fanpage, Job, Publication, Video
from reels_api.storage import DirectoryStorage
from reels_api.videos import render_signature, split_scenes


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def add_mp4(db, storage, video) -> None:
    video.mp4_key = f"videos/{video.id}/video-x.mp4"
    storage.save_bytes(video.mp4_key, b"mp4 bytes")
    title, scenes = split_scenes(db, video)
    video.rendered_signature = render_signature(video, title, scenes)
    db.commit()


def fanpage_id(db, user) -> int:
    row = fanpages.save(db, FACEBOOK_PAGE, "Trang Dưỡng Sinh", FACEBOOK_TOKEN, user.id)
    db.commit()
    return row.id


def in_minutes(minutes: float) -> str:
    return (datetime.now(UTC) + timedelta(minutes=minutes)).isoformat()


# --- The endpoint ---


def test_publish_queues_a_job_and_locks_the_video(an, db, me, storage):
    video = make_video(db, storage, me)
    add_mp4(db, storage, video)
    payload = an.post(f"/api/videos/{video.id}/publish", json={"fanpage_id": fanpage_id(db, me)}).json()
    assert payload["active_job"]["kind"] == "publish"
    assert payload["status_label"] == "Chờ thứ 1"
    post = payload["publication"]
    assert (post["status"], post["fanpage"], post["scheduled_at"], post["url"], post["closed_at"]) == (
        "pending",
        "Trang Dưỡng Sinh",
        None,
        None,
        None,
    )
    assert payload["publications"] == [post]
    refused = an.patch(f"/api/videos/{video.id}", json={"caption": "khác"})
    assert (refused.status_code, refused.json()["message"]) == (409, "Video đang đăng lên Facebook, chưa lưu")


def test_publish_needs_a_current_mp4(an, db, me, storage):
    video = make_video(db, storage, me)
    missing = an.post(f"/api/videos/{video.id}/publish", json={"fanpage_id": fanpage_id(db, me)})
    assert (missing.status_code, missing.json()["message"]) == (409, "Video chưa có MP4, hãy render trước")

    add_mp4(db, storage, video)
    title, scenes = split_scenes(db, video)
    scenes[0].text = "Chữ đã sửa"
    db.commit()
    outdated = an.post(f"/api/videos/{video.id}/publish", json={"fanpage_id": fanpage_id(db, me)})
    assert (outdated.status_code, outdated.json()["code"]) == (409, "mp4_outdated")
    assert db.scalar(select(Job).where(Job.video_id == video.id)) is None


@pytest.mark.parametrize("minutes", [14, 29 * 24 * 60 + 5])
def test_scheduled_time_must_be_one_facebook_accepts(an, db, me, storage, minutes):
    video = make_video(db, storage, me)
    add_mp4(db, storage, video)
    refused = an.post(
        f"/api/videos/{video.id}/publish", json={"fanpage_id": fanpage_id(db, me), "scheduled_at": in_minutes(minutes)}
    )
    assert (refused.status_code, refused.json()["message"]) == (
        422,
        "Giờ hẹn phải sau ít nhất 15 phút và trong vòng 29 ngày tới",
    )


@pytest.mark.parametrize("minutes", [16, 29 * 24 * 60 - 5])
def test_a_time_inside_the_limits_is_accepted_and_shown_as_scheduled_once_done(an, db, me, storage, minutes):
    video = make_video(db, storage, me)
    add_mp4(db, storage, video)
    assert (
        an.post(
            f"/api/videos/{video.id}/publish",
            json={"fanpage_id": fanpage_id(db, me), "scheduled_at": in_minutes(minutes)},
        ).status_code
        == 200
    )
    post = db.scalar(select(Publication).where(Publication.video_id == video.id))
    db.execute(update(Job).where(Job.video_id == video.id).values(status="done"))
    post.status, post.remote_id = "scheduled", "1000"
    db.commit()
    shown = an.get(f"/api/videos/{video.id}").json()["publication"]
    assert (shown["status"], shown["url"]) == ("scheduled", None), "not public yet: no link"


def test_scheduled_time_needs_a_time_zone(an, db, me, storage):
    video = make_video(db, storage, me)
    add_mp4(db, storage, video)
    refused = an.post(
        f"/api/videos/{video.id}/publish",
        json={"fanpage_id": fanpage_id(db, me), "scheduled_at": "2030-01-01T11:00:00"},
    )
    assert (refused.status_code, refused.json()["message"]) == (422, "Giờ đăng phải kèm múi giờ")


@pytest.mark.parametrize("status", ["scheduled", "published"])
def test_the_same_mp4_goes_to_a_fanpage_only_once(an, db, me, storage, status):
    video = make_video(db, storage, me)
    add_mp4(db, storage, video)
    scheduled_at = datetime.now(UTC) + timedelta(days=1)
    page = fanpage_id(db, me)
    db.add(
        Publication(
            video_id=video.id,
            platform="facebook",
            status=status,
            remote_id="1000",
            remote_mp4_key=video.mp4_key,
            fanpage_id=page,
            scheduled_at=scheduled_at if status == "scheduled" else None,
            created_by_id=me.id,
        )
    )
    db.commit()
    assert an.get(f"/api/videos/{video.id}").json()["posted_fanpage_ids"] == [page]
    refused = an.post(f"/api/videos/{video.id}/publish", json={"fanpage_id": page})
    assert (refused.status_code, refused.json()["code"]) == (409, "already_published")


def add_post(db, video, user, page, **fields) -> Publication:
    fields = {"status": "published", "remote_id": "1000", "remote_mp4_key": video.mp4_key} | fields
    post = Publication(video_id=video.id, platform="facebook", fanpage_id=page, created_by_id=user.id, **fields)
    db.add(post)
    db.commit()
    return post


def test_a_new_render_can_be_posted_again_and_keeps_the_old_post(an, db, me, storage):
    video = make_video(db, storage, me)
    add_mp4(db, storage, video)
    page = fanpage_id(db, me)
    old = add_post(db, video, me, page, remote_mp4_key="videos/1/video-old.mp4")
    payload = an.post(f"/api/videos/{video.id}/publish", json={"fanpage_id": page}).json()
    assert [post["status"] for post in payload["publications"]] == ["pending", "published"]
    assert payload["publications"][1]["id"] == old.id
    assert payload["publication"]["status"] == "pending"


def test_the_same_mp4_can_go_to_another_fanpage(an, db, me, storage):
    video = make_video(db, storage, me)
    add_mp4(db, storage, video)
    add_post(db, video, me, fanpage_id(db, me))
    other = fanpages.save(db, "222", "Trang Hai", FACEBOOK_TOKEN, me.id)
    db.commit()
    assert an.post(f"/api/videos/{video.id}/publish", json={"fanpage_id": other.id}).status_code == 200


def test_an_mp4_taken_off_a_fanpage_can_go_there_again(an, db, me, storage):
    video = make_video(db, storage, me)
    add_mp4(db, storage, video)
    page = fanpage_id(db, me)
    add_post(db, video, me, page, status="deleted")
    assert an.post(f"/api/videos/{video.id}/publish", json={"fanpage_id": page}).status_code == 200


def test_cancelling_a_post_facebook_never_received_stops_its_job(an, db, me, storage):
    video = make_video(db, storage, me)
    add_mp4(db, storage, video)
    payload = an.post(f"/api/videos/{video.id}/publish", json={"fanpage_id": fanpage_id(db, me)}).json()
    done = an.post(f"/api/posts/{payload['publication']['id']}/take-down").json()
    assert done["active_job"] is None
    (post,) = done["publications"]
    assert (post["status"], post["closed_by"]) == ("cancelled", "Nguyễn Văn An")
    assert post["closed_at"] and done["publication"] is None
    assert db.scalar(select(Job).where(Job.video_id == video.id)).status == "cancelled"


def test_taking_down_a_post_on_facebook_queues_a_job_for_it(an, db, me, storage):
    video = make_video(db, storage, me)
    add_mp4(db, storage, video)
    post = add_post(db, video, me, fanpage_id(db, me))
    payload = an.post(f"/api/posts/{post.id}/take-down").json()
    assert payload["active_job"]["kind"] == "unpublish"
    assert payload["status_label"] == "Chờ thứ 1"
    assert db.scalar(select(Job).where(Job.video_id == video.id)).publication_id == post.id
    assert payload["publication"]["status"] == "published", "still on Facebook until the job has run"


def test_a_queued_retry_of_a_reel_on_facebook_gives_way_to_taking_it_down(an, db, me, storage):
    video = make_video(db, storage, me)
    add_mp4(db, storage, video)
    post = add_post(db, video, me, fanpage_id(db, me), status="pending")
    db.add(Job(video_id=video.id, kind="publish", status="queued", created_by_id=me.id))
    db.commit()
    assert an.post(f"/api/posts/{post.id}/take-down").json()["active_job"]["kind"] == "unpublish"


def test_a_running_job_must_finish_before_taking_a_post_down(an, db, me, storage):
    video = make_video(db, storage, me)
    add_mp4(db, storage, video)
    post = add_post(db, video, me, fanpage_id(db, me), status="pending")
    db.add(Job(video_id=video.id, kind="publish", status="running", created_by_id=me.id))
    db.commit()
    refused = an.post(f"/api/posts/{post.id}/take-down")
    assert (refused.status_code, refused.json()["code"]) == (409, "video_locked")


@pytest.mark.parametrize("status", ["cancelled", "deleted"])
def test_a_closed_post_cannot_be_taken_down_again(an, db, me, storage, status):
    video = make_video(db, storage, me)
    post = add_post(db, video, me, fanpage_id(db, me), status=status)
    refused = an.post(f"/api/posts/{post.id}/take-down")
    assert (refused.status_code, refused.json()["code"]) == (409, "post_closed")


def test_taking_down_needs_a_post_and_a_login(client, an):
    assert an.post("/api/posts/999/take-down").status_code == 404
    an.post("/api/auth/logout")
    assert client.post("/api/posts/999/take-down").status_code == 401


def test_a_scheduled_post_counts_as_published_once_its_time_has_passed(an, db, me, storage):
    video = make_video(db, storage, me)
    db.add(
        Publication(
            video_id=video.id,
            platform="facebook",
            status="scheduled",
            remote_id="1000",
            scheduled_at=datetime.now(UTC) - timedelta(minutes=1),
            created_by_id=me.id,
        )
    )
    db.commit()
    post = an.get(f"/api/videos/{video.id}").json()["publication"]
    assert (post["status"], post["url"]) == ("published", "https://www.facebook.com/reel/1000")


def test_a_failed_publish_can_be_sent_again_with_a_new_time(an, db, me, storage):
    video = make_video(db, storage, me)
    add_mp4(db, storage, video)
    db.add(Publication(video_id=video.id, platform="facebook", scheduled_at=datetime.now(UTC), created_by_id=me.id))
    db.commit()
    db.add(Job(video_id=video.id, kind="publish", status="failed", created_by_id=me.id))
    db.commit()
    when = in_minutes(60)
    payload = an.post(
        f"/api/videos/{video.id}/publish", json={"fanpage_id": fanpage_id(db, me), "scheduled_at": when}
    ).json()
    assert payload["active_job"]["kind"] == "publish"
    assert datetime.fromisoformat(payload["publication"]["scheduled_at"]) == datetime.fromisoformat(when)


def test_publishing_needs_a_fanpage_in_use(an, db, me, storage):
    video = make_video(db, storage, me)
    add_mp4(db, storage, video)
    page = fanpage_id(db, me)
    db.get(Fanpage, page).active = False
    db.commit()
    refused = an.post(f"/api/videos/{video.id}/publish", json={"fanpage_id": page})
    assert (refused.status_code, refused.json()["message"]) == (422, "Hãy chọn một Fanpage đang dùng")
    assert an.post(f"/api/videos/{video.id}/publish", json={"fanpage_id": 999}).status_code == 422


def test_a_reel_already_uploaded_stays_on_its_fanpage(an, db, me, storage):
    video = make_video(db, storage, me)
    add_mp4(db, storage, video)
    first = fanpage_id(db, me)
    other = fanpages.save(db, "222", "Trang Hai", FACEBOOK_TOKEN, me.id)
    db.flush()
    db.add(Publication(video_id=video.id, platform="facebook", remote_id="1000", fanpage_id=first, created_by_id=me.id))
    db.commit()
    refused = an.post(f"/api/videos/{video.id}/publish", json={"fanpage_id": other.id})
    assert (refused.status_code, refused.json()["code"]) == (409, "other_fanpage")


def test_the_video_shows_which_fanpage_it_went_to(an, db, me, storage):
    video = make_video(db, storage, me)
    db.add(
        Publication(
            video_id=video.id,
            platform="facebook",
            status="published",
            remote_id="1000",
            fanpage_id=fanpage_id(db, me),
            created_by_id=me.id,
        )
    )
    db.commit()
    assert an.get(f"/api/videos/{video.id}").json()["publication"]["fanpage"] == "Trang Dưỡng Sinh"


def test_a_failed_publish_is_not_shown_as_a_failed_render(an, db, me, storage):
    video = make_video(db, storage, me)
    add_mp4(db, storage, video)
    db.add(
        Job(
            video_id=video.id,
            kind="publish",
            status="failed",
            error="Facebook từ chối đăng video này",
            created_by_id=me.id,
        )
    )
    db.commit()
    payload = an.get(f"/api/videos/{video.id}").json()
    assert payload["rerender_failed"] is False
    assert payload["failed_job"]["kind"] == "publish"


# --- The job, in process ---


@pytest.fixture
def ready(committed, tmp_path, fakes):
    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    with committed() as db:
        video = make_video(db, storage, user, scene_count=1)
        video.caption, video.hashtags = "Ăn vừng đen mỗi sáng", ["#vungden", "#suckhoe"]
        add_mp4(db, storage, video)
        db.add(
            Publication(video_id=video.id, platform="facebook", created_by_id=user.id, fanpage_id=fanpage_id(db, user))
        )
        db.commit()
    return user, storage, video.id


def run_publish(factory, storage, video_id, user_id) -> Job:
    from reels_api import jobs

    job_id = add_job(factory, video_id, user_id, kind="publish", status="running")
    jobs.run_job(job_id, factory, storage)
    return job_row(factory, job_id)


def post_of(factory, video_id) -> Publication:
    with factory() as db:
        return db.scalar(select(Publication).where(Publication.video_id == video_id))


def only_reel(fakes) -> dict:
    (reel,) = fakes.reels.values()
    return reel


def live_sibling(committed, fakes, user, storage, ready) -> str:
    """Another reel of the same Page that Facebook has live: what lets a lost answer for this reel mean "deleted"."""
    _, _, video_id = ready
    with committed() as db:
        page_id = db.scalar(select(Publication.fanpage_id).where(Publication.video_id == video_id))
        other = make_video(db, storage, user, scene_count=1)
        db.add(
            Publication(
                video_id=other.id,
                platform="facebook",
                status="published",
                remote_id="9001",
                fanpage_id=page_id,
                created_by_id=user.id,
            )
        )
        db.commit()
    fakes.reels["9001"] = {"uploaded": True, "bytes": 0, "finishes": 1, "state": "published"}
    return "9001"


def test_hashtags_already_in_the_caption_are_not_posted_twice(committed, ready, fakes):
    """Scripts often end the caption with the same hashtags the Hashtag field holds (issue #71's screenshot)."""
    user, storage, video_id = ready
    with committed() as db:
        video = db.get(Video, video_id)
        video.caption = "Ăn vừng đen mỗi sáng\n#VungDen #suckhoe"
        video.hashtags = ["#vungden", "#suckhoe", "#reels"]
        db.commit()
    job = run_publish(committed, storage, video_id, user.id)
    assert job.status == "done", (job.error, job.error_detail)
    assert only_reel(fakes)["description"] == "Ăn vừng đen mỗi sáng\n#VungDen #suckhoe\n\n#reels"


def test_publishing_sends_the_mp4_with_the_caption_and_hashtags(committed, ready, fakes):
    user, storage, video_id = ready
    job = run_publish(committed, storage, video_id, user.id)
    assert job.status == "done", (job.error, job.error_detail)
    reel = only_reel(fakes)
    assert reel["bytes"] == len(b"mp4 bytes")
    assert reel["description"] == "Ăn vừng đen mỗi sáng\n\n#vungden #suckhoe"
    assert reel["video_state"] == "PUBLISHED"
    post = post_of(committed, video_id)
    assert post.status == "published" and post.remote_id and post.published_at


def test_a_post_keeps_where_each_scene_falls_in_the_mp4_it_sent(committed, ready, fakes):
    """The retention curve is drawn against the posted render's scenes, which later edits must not move."""
    user, storage, video_id = ready
    job = run_publish(committed, storage, video_id, user.id)
    assert job.status == "done", (job.error, job.error_detail)
    assert post_of(committed, video_id).scene_marks == [
        {"label": "Tiêu đề", "start": 0.0, "end": 3.0},
        {"label": "Cảnh 1", "start": 3.0, "end": 7.0},
    ]


def test_an_mp4_without_a_readable_frame_posts_with_facebooks_own_cover(committed, ready, fakes):
    user, storage, video_id = ready
    job = run_publish(committed, storage, video_id, user.id)
    assert job.status == "done", (job.error, job.error_detail)
    assert "cover" not in only_reel(fakes)


@needs_ffmpeg
def test_the_reel_cover_is_the_mp4s_first_frame(committed, ready, fakes, tmp_path):
    user, storage, video_id = ready
    with committed() as db:
        storage.save_bytes(db.get(Video, video_id).mp4_key, clip_bytes(tmp_path, seconds=2, size="1080x1920"))
    job = run_publish(committed, storage, video_id, user.id)
    assert job.status == "done", (job.error, job.error_detail)
    reel = only_reel(fakes)
    assert reel["cover_preferred"] == "true"
    with Image.open(io.BytesIO(reel["cover"])) as cover:
        assert (cover.format, cover.size) == ("JPEG", (1080, 1920))


@needs_ffmpeg
def test_a_cover_facebook_refuses_still_posts_the_reel(committed, ready, fakes, tmp_path):
    user, storage, video_id = ready
    fakes.facebook_cover_refusals = 1
    with committed() as db:
        storage.save_bytes(db.get(Video, video_id).mp4_key, clip_bytes(tmp_path, seconds=2, size="1080x1920"))
    job = run_publish(committed, storage, video_id, user.id)
    assert job.status == "done", (job.error, job.error_detail)
    assert "cover" not in only_reel(fakes)
    assert post_of(committed, video_id).status == "published"


def test_a_page_facebook_refuses_gets_a_reason_a_member_can_act_on():
    error = facebook._http_error(400, '{"error":{"message":"Unsupported post request","code":100,"error_subcode":33}}')
    assert error.message == "Facebook không cho token này truy cập Page, hãy dán token mới trong Kết nối Fanpage"


def test_scheduling_lets_facebook_publish_at_the_time(committed, ready, fakes):
    user, storage, video_id = ready
    when = datetime.now(UTC).replace(microsecond=0) + timedelta(hours=2)
    with committed() as db:
        db.scalar(select(Publication).where(Publication.video_id == video_id)).scheduled_at = when
        db.commit()
    assert run_publish(committed, storage, video_id, user.id).status == "done"
    reel = only_reel(fakes)
    assert reel["video_state"] == "SCHEDULED"
    assert reel["scheduled_publish_time"] == str(int(when.timestamp()))
    assert post_of(committed, video_id).status == "scheduled"


def test_a_time_gone_by_fails_before_anything_is_uploaded(committed, ready, fakes):
    user, storage, video_id = ready
    with committed() as db:
        post = db.scalar(select(Publication).where(Publication.video_id == video_id))
        post.scheduled_at = datetime.now(UTC) + timedelta(minutes=2)
        db.commit()
    job = run_publish(committed, storage, video_id, user.id)
    assert (job.status, job.error) == (
        "failed",
        "Giờ hẹn đã qua hoặc còn dưới 10 phút, hãy chọn giờ khác rồi bấm đăng lại",
    )
    assert fakes.reels == {}


def test_a_retry_after_a_failed_finish_finishes_the_same_reel(committed, ready, fakes):
    user, storage, video_id = ready
    fakes.facebook_finish_fails = 1
    job = run_publish(committed, storage, video_id, user.id)
    assert (job.status, job.error) == ("failed", "Facebook đang lỗi (HTTP 500), thử lại sau")
    assert post_of(committed, video_id).status == "pending"

    assert run_publish(committed, storage, video_id, user.id).status == "done"
    reel = only_reel(fakes)
    assert reel["finishes"] == 2 and reel["state"] == "published"


def test_a_retry_after_a_lost_answer_posts_nothing_new(committed, ready, fakes):
    user, storage, video_id = ready
    fakes.facebook_finish_replies_lost = 1
    assert run_publish(committed, storage, video_id, user.id).status == "failed"

    assert run_publish(committed, storage, video_id, user.id).status == "done"
    assert only_reel(fakes)["finishes"] == 1, "the reel was already live: nothing is sent again"
    assert post_of(committed, video_id).status == "published"


def test_a_retry_after_a_cut_upload_uploads_again(committed, ready, fakes, monkeypatch):
    user, storage, video_id = ready

    def cut(page, upload_url, path):
        raise facebook.FacebookError("Không kết nối được Facebook, kiểm tra mạng rồi thử lại")

    with monkeypatch.context() as patch:
        patch.setattr(facebook, "upload", cut)
        assert run_publish(committed, storage, video_id, user.id).status == "failed"
    assert run_publish(committed, storage, video_id, user.id).status == "done"
    finished = [reel for reel in fakes.reels.values() if reel["finishes"]]
    assert len(finished) == 1 and finished[0]["bytes"] == len(b"mp4 bytes")


def test_a_failed_status_read_never_posts_a_second_reel(committed, ready, fakes):
    user, storage, video_id = ready
    fakes.facebook_finish_replies_lost = 1
    assert run_publish(committed, storage, video_id, user.id).status == "failed"

    fakes.facebook_status_fails = 1
    job = run_publish(committed, storage, video_id, user.id)
    assert job.status == "failed" and job.error.startswith("Không đọc được trạng thái reel")
    assert len(fakes.reels) == 1
    assert run_publish(committed, storage, video_id, user.id).status == "done"
    assert len(fakes.reels) == 1 and only_reel(fakes)["finishes"] == 1


def test_a_failed_status_read_while_waiting_fails_and_the_retry_finds_the_reel_live(committed, ready, fakes):
    user, storage, video_id = ready
    fakes.facebook_status_fails = 1
    assert run_publish(committed, storage, video_id, user.id).status == "failed"
    assert run_publish(committed, storage, video_id, user.id).status == "done"
    assert len(fakes.reels) == 1 and only_reel(fakes)["finishes"] == 1


def test_a_reel_facebook_really_lost_is_sent_again(committed, ready, fakes):
    user, storage, video_id = ready
    fakes.facebook_finish_fails = 1
    assert run_publish(committed, storage, video_id, user.id).status == "failed"
    # Lost only counts while the token still reads another reel of the Page (`facebook._gone`).
    live_sibling(committed, fakes, user, storage, ready)
    fakes.reels[post_of(committed, video_id).remote_id]["lost"] = True
    assert run_publish(committed, storage, video_id, user.id).status == "done"
    assert [reel["state"] for reel in fakes.reels.values()] == ["draft", "published", "published"]


def re_render(factory, storage, video_id, data=b"mp4 moi hon"):
    with factory() as db:
        video = db.get(Video, video_id)
        title, scenes = split_scenes(db, video)
        scenes[0].text = "Chữ đã sửa"
        video.mp4_key = f"videos/{video.id}/video-y.mp4"
        storage.save_bytes(video.mp4_key, data)
        video.rendered_signature = render_signature(video, title, scenes)
        db.commit()


def test_a_new_render_after_a_lost_answer_on_a_live_reel_posts_nothing_new(committed, ready, fakes):
    user, storage, video_id = ready
    fakes.facebook_finish_replies_lost = 1
    assert run_publish(committed, storage, video_id, user.id).status == "failed"
    re_render(committed, storage, video_id)
    assert run_publish(committed, storage, video_id, user.id).status == "done"
    assert len(fakes.reels) == 1 and only_reel(fakes)["bytes"] == len(b"mp4 bytes")
    assert post_of(committed, video_id).status == "published"


def test_a_new_render_waits_for_a_reel_facebook_may_still_publish(committed, ready, fakes):
    user, storage, video_id = ready
    fakes.facebook_finish_fails = 1
    assert run_publish(committed, storage, video_id, user.id).status == "failed"
    re_render(committed, storage, video_id)
    job = run_publish(committed, storage, video_id, user.id)
    assert (job.status, job.error) == (
        "failed",
        "Facebook có thể vẫn đang đăng bản trước, hãy xem Page, đợi 30 phút rồi Thử lại",
    )
    assert len(fakes.reels) == 1

    with committed() as db:
        post = db.scalar(select(Publication).where(Publication.video_id == video_id))
        post.finish_sent_at -= timedelta(minutes=31)
        db.commit()
    assert run_publish(committed, storage, video_id, user.id).status == "done"
    assert [reel["state"] for reel in fakes.reels.values()] == ["draft", "published"]


def test_a_new_render_after_a_refused_finish_posts_the_new_mp4(committed, ready, fakes):
    user, storage, video_id = ready
    fakes.facebook_finish_refusals = 1
    assert run_publish(committed, storage, video_id, user.id).status == "failed"
    re_render(committed, storage, video_id)
    assert run_publish(committed, storage, video_id, user.id).status == "done"
    live = [reel for reel in fakes.reels.values() if reel["state"] == "published"]
    assert len(live) == 1 and live[0]["bytes"] == len(b"mp4 moi hon")


def test_a_retry_refuses_an_mp4_out_of_date_with_the_edits(committed, ready, fakes):
    user, storage, video_id = ready
    fakes.facebook_finish_fails = 1
    assert run_publish(committed, storage, video_id, user.id).status == "failed"
    with committed() as db:
        _, scenes = split_scenes(db, db.get(Video, video_id))
        scenes[0].text = "Chữ đã sửa"
        db.commit()
    job = run_publish(committed, storage, video_id, user.id)
    assert (job.status, job.error) == ("failed", "MP4 chưa cập nhật theo bản sửa, hãy render lại rồi đăng")
    assert only_reel(fakes)["state"] == "draft"


def test_facebook_decides_the_state_after_a_lost_answer(committed, ready, fakes):
    user, storage, video_id = ready
    when = datetime.now(UTC).replace(microsecond=0) + timedelta(hours=2)
    with committed() as db:
        db.scalar(select(Publication).where(Publication.video_id == video_id)).scheduled_at = when
        db.commit()
    fakes.facebook_finish_replies_lost = 1
    assert run_publish(committed, storage, video_id, user.id).status == "failed"
    # The member changes their mind to "Đăng ngay", but the reel is already scheduled on Facebook.
    with committed() as db:
        db.scalar(select(Publication).where(Publication.video_id == video_id)).scheduled_at = None
        db.commit()
    assert run_publish(committed, storage, video_id, user.id).status == "done"
    post = post_of(committed, video_id)
    assert (post.status, post.scheduled_at) == ("scheduled", when)
    assert only_reel(fakes)["finishes"] == 1


def test_a_scheduled_time_gone_by_does_not_matter_for_a_reel_already_scheduled(committed, ready, fakes):
    user, storage, video_id = ready
    with committed() as db:
        db.scalar(select(Publication).where(Publication.video_id == video_id)).scheduled_at = datetime.now(
            UTC
        ) + timedelta(hours=1)
        db.commit()
    fakes.facebook_finish_replies_lost = 1
    assert run_publish(committed, storage, video_id, user.id).status == "failed"
    with committed() as db:
        db.scalar(select(Publication).where(Publication.video_id == video_id)).scheduled_at = datetime.now(
            UTC
        ) + timedelta(minutes=1)
        db.commit()
    assert run_publish(committed, storage, video_id, user.id).status == "done"


def test_a_reel_still_processing_is_waited_for_and_not_finished_again(committed, ready, fakes, monkeypatch):
    monkeypatch.setattr(facebook, "PROCESSING_SECONDS", 0)
    user, storage, video_id = ready
    fakes.facebook_finish_fails = 1
    assert run_publish(committed, storage, video_id, user.id).status == "failed"
    fakes.facebook_processing = "busy"
    job = run_publish(committed, storage, video_id, user.id)
    assert (job.status, job.error) == ("failed", "Facebook xử lý video quá lâu, hãy xem Page rồi bấm Thử lại")
    assert only_reel(fakes)["finishes"] == 1
    assert post_of(committed, video_id).status == "pending"


def test_a_retry_while_facebook_still_processes_waits_until_the_reel_is_live(committed, ready, fakes, monkeypatch):
    monkeypatch.setattr(facebook, "POLL_SECONDS", 0)
    user, storage, video_id = ready
    fakes.facebook_finish_replies_lost = 1
    assert run_publish(committed, storage, video_id, user.id).status == "failed"
    fakes.facebook_busy_reads = 3
    assert run_publish(committed, storage, video_id, user.id).status == "done"
    assert only_reel(fakes)["finishes"] == 1
    assert fakes.facebook_busy_reads == 0


def test_a_reel_never_finished_is_finished_even_while_it_processes(committed, ready, fakes):
    user, storage, video_id = ready
    fakes.facebook_finish_refusals = 1
    assert run_publish(committed, storage, video_id, user.id).status == "failed"
    fakes.facebook_busy_reads = 1
    assert run_publish(committed, storage, video_id, user.id).status == "done"
    assert only_reel(fakes)["finishes"] == 2


def test_a_status_answer_without_a_status_posts_nothing_new(committed, ready, fakes):
    user, storage, video_id = ready
    fakes.facebook_finish_replies_lost = 1
    assert run_publish(committed, storage, video_id, user.id).status == "failed"
    fakes.facebook_empty_status = True
    job = run_publish(committed, storage, video_id, user.id)
    assert job.status == "failed" and job.error.startswith("Không đọc được trạng thái reel")
    assert len(fakes.reels) == 1


def test_a_resend_keeps_the_reel_of_the_attempt_before(an, db, me, storage):
    video = make_video(db, storage, me)
    add_mp4(db, storage, video)
    page = fanpage_id(db, me)
    db.add(
        Publication(
            video_id=video.id,
            platform="facebook",
            remote_id="1000",
            remote_mp4_key=video.mp4_key,
            fanpage_id=page,
            created_by_id=me.id,
        )
    )
    db.commit()
    assert (
        an.post(
            f"/api/videos/{video.id}/publish", json={"fanpage_id": page, "scheduled_at": in_minutes(60)}
        ).status_code
        == 200
    )
    post = db.scalar(select(Publication).where(Publication.video_id == video.id))
    assert (post.remote_id, post.remote_mp4_key) == ("1000", video.mp4_key)


def test_facebooks_time_wins_over_the_time_asked_last(committed, ready, fakes):
    user, storage, video_id = ready
    when = datetime.now(UTC).replace(microsecond=0) + timedelta(hours=2)
    with committed() as db:
        db.scalar(select(Publication).where(Publication.video_id == video_id)).scheduled_at = when
        db.commit()
    fakes.facebook_finish_replies_lost = 1
    assert run_publish(committed, storage, video_id, user.id).status == "failed"
    with committed() as db:
        db.scalar(select(Publication).where(Publication.video_id == video_id)).scheduled_at = when + timedelta(days=1)
        db.commit()
    assert run_publish(committed, storage, video_id, user.id).status == "done"
    assert post_of(committed, video_id).scheduled_at == when


def test_a_public_reel_is_recorded_as_public_whatever_time_was_asked_last(committed, ready, fakes):
    user, storage, video_id = ready
    fakes.facebook_finish_replies_lost = 1
    assert run_publish(committed, storage, video_id, user.id).status == "failed"
    with committed() as db:
        db.scalar(select(Publication).where(Publication.video_id == video_id)).scheduled_at = datetime.now(
            UTC
        ) + timedelta(hours=1)
        db.commit()
    assert run_publish(committed, storage, video_id, user.id).status == "done"
    post = post_of(committed, video_id)
    assert (post.status, post.scheduled_at) == ("published", None)


def test_a_reel_refused_while_processing_is_replaced_on_retry(committed, ready, fakes):
    user, storage, video_id = ready
    fakes.facebook_finish_draft, fakes.facebook_processing = True, "rejected"
    job = run_publish(committed, storage, video_id, user.id)
    assert (job.status, job.error) == ("failed", "Facebook không xử lý được video này")

    only_reel(fakes)["rejected"] = True
    fakes.facebook_finish_draft, fakes.facebook_processing = False, "ok"
    assert run_publish(committed, storage, video_id, user.id).status == "done"
    assert [reel["state"] for reel in fakes.reels.values()] == ["draft", "published"]


def test_a_job_finding_the_post_already_done_does_nothing(committed, ready, fakes):
    user, storage, video_id = ready
    with committed() as db:
        db.scalar(select(Publication).where(Publication.video_id == video_id)).status = "published"
        db.commit()
    assert run_publish(committed, storage, video_id, user.id).status == "done"
    assert fakes.reels == {}


def test_a_bad_token_fails_with_a_clear_reason(committed, ready, fakes):
    user, storage, video_id = ready
    with committed() as db:
        fanpages.save(db, FACEBOOK_PAGE, "Trang Dưỡng Sinh", "het-han", user.id)
        db.commit()
    job = run_publish(committed, storage, video_id, user.id)
    assert (job.status, job.error) == (
        "failed",
        "Token Facebook hết hạn hoặc không hợp lệ, hãy dán token mới trong Kết nối Fanpage",
    )
    assert "het-han" not in (job.error_detail or "")


def test_a_post_without_a_fanpage_fails_with_a_clear_reason(committed, ready, fakes):
    user, storage, video_id = ready
    with committed() as db:
        db.scalar(select(Publication).where(Publication.video_id == video_id)).fanpage_id = None
        db.commit()
    job = run_publish(committed, storage, video_id, user.id)
    assert (job.status, job.error) == ("failed", "Video chưa chọn Fanpage, hãy chọn Fanpage rồi đăng lại")
    assert fakes.reels == {}


def test_a_stopped_fanpage_fails_with_a_clear_reason(committed, ready, fakes):
    user, storage, video_id = ready
    with committed() as db:
        db.scalar(select(Fanpage)).active = False
        db.commit()
    job = run_publish(committed, storage, video_id, user.id)
    assert (job.status, job.error) == (
        "failed",
        "Fanpage “Trang Dưỡng Sinh” đang ngừng dùng, hãy dùng lại trong Kết nối Fanpage",
    )
    assert fakes.reels == {}


def test_facebook_refusing_the_video_while_processing_fails_the_job(committed, ready, fakes):
    user, storage, video_id = ready
    fakes.facebook_processing = "error"
    fakes.facebook_finish_draft = True
    job = run_publish(committed, storage, video_id, user.id)
    assert (job.status, job.error) == ("failed", "Facebook không xử lý được video này")


def test_a_missing_mp4_file_fails_before_anything_is_sent(committed, ready, fakes):
    user, storage, video_id = ready
    with committed() as db:
        storage.delete(db.get(Video, video_id).mp4_key)
    job = run_publish(committed, storage, video_id, user.id)
    assert (job.status, job.error) == ("failed", "Không thấy file MP4 trong storage, hãy render lại rồi đăng")
    assert fakes.reels == {}


# --- Taking a post down, in process ---


def run_unpublish(factory, storage, post_id, video_id, user_id) -> Job:
    from reels_api import jobs

    job_id = add_job(factory, video_id, user_id, kind="unpublish", status="running")
    with factory() as db:
        db.get(Job, job_id).publication_id = post_id
        db.commit()
    jobs.run_job(job_id, factory, storage)
    return job_row(factory, job_id)


def schedule(factory, video_id, hours: float) -> None:
    with factory() as db:
        post = db.scalar(select(Publication).where(Publication.video_id == video_id))
        post.scheduled_at = datetime.now(UTC).replace(microsecond=0) + timedelta(hours=hours)
        db.commit()


def test_cancelling_a_scheduled_reel_deletes_it_so_facebook_never_publishes_it(committed, ready, fakes):
    user, storage, video_id = ready
    schedule(committed, video_id, 2)
    run_publish(committed, storage, video_id, user.id)
    post = post_of(committed, video_id)
    job = run_unpublish(committed, storage, post.id, video_id, user.id)
    assert job.status == "done", (job.error, job.error_detail)
    assert fakes.reels == {}
    post = post_of(committed, video_id)
    assert (post.status, post.closed_by_id) == ("cancelled", user.id)
    assert post.closed_at and post.remote_id, "the history keeps the reel's id"


def test_deleting_a_live_reel_ends_as_deleted(committed, ready, fakes):
    user, storage, video_id = ready
    run_publish(committed, storage, video_id, user.id)
    run_unpublish(committed, storage, post_of(committed, video_id).id, video_id, user.id)
    assert fakes.reels == {}
    assert post_of(committed, video_id).status == "deleted"


def test_a_scheduled_reel_past_its_time_ends_as_deleted(committed, ready, fakes):
    user, storage, video_id = ready
    schedule(committed, video_id, 2)
    run_publish(committed, storage, video_id, user.id)
    schedule(committed, video_id, -1)
    run_unpublish(committed, storage, post_of(committed, video_id).id, video_id, user.id)
    assert post_of(committed, video_id).status == "deleted"


def test_a_pending_post_that_reached_facebook_ends_as_deleted(committed, ready, fakes):
    """The answer to the publish was lost, so the app still has it pending, but people saw it."""
    user, storage, video_id = ready
    run_publish(committed, storage, video_id, user.id)
    with committed() as db:
        db.scalar(select(Publication).where(Publication.video_id == video_id)).status = "pending"
        db.commit()
    run_unpublish(committed, storage, post_of(committed, video_id).id, video_id, user.id)
    assert post_of(committed, video_id).status == "deleted"


def test_a_reel_already_gone_from_facebook_still_closes_the_post(committed, ready, fakes):
    user, storage, video_id = ready
    run_publish(committed, storage, video_id, user.id)
    live_sibling(committed, fakes, user, storage, ready)
    del fakes.reels[post_of(committed, video_id).remote_id]
    job = run_unpublish(committed, storage, post_of(committed, video_id).id, video_id, user.id)
    assert job.status == "done"
    assert post_of(committed, video_id).status == "deleted"


def test_a_refused_delete_fails_the_job_and_leaves_the_post(committed, ready, fakes):
    user, storage, video_id = ready
    run_publish(committed, storage, video_id, user.id)
    fakes.facebook_delete_refusals = 1
    job = run_unpublish(committed, storage, post_of(committed, video_id).id, video_id, user.id)
    assert job.status == "failed"
    assert job.error.startswith("Facebook từ chối xóa bài này")
    post = post_of(committed, video_id)
    assert (post.status, post.closed_at) == ("published", None)
    assert len(fakes.reels) == 1


def test_an_unknown_status_deletes_nothing(committed, ready, fakes):
    user, storage, video_id = ready
    run_publish(committed, storage, video_id, user.id)
    fakes.facebook_status_fails = 1
    job = run_unpublish(committed, storage, post_of(committed, video_id).id, video_id, user.id)
    assert job.status == "failed"
    assert len(fakes.reels) == 1


def test_retrying_a_failed_take_down_keeps_its_post(an, db, me, storage):
    video = make_video(db, storage, me)
    add_mp4(db, storage, video)
    post = add_post(db, video, me, fanpage_id(db, me))
    job = Job(video_id=video.id, kind="unpublish", status="failed", publication_id=post.id, created_by_id=me.id)
    db.add(job)
    db.commit()
    assert an.post(f"/api/jobs/{job.id}/retry").status_code == 200
    queued = db.scalar(select(Job).where(Job.video_id == video.id, Job.status == "queued"))
    assert queued.publication_id == post.id


def test_retrying_a_publish_job_after_the_post_was_cancelled_posts_nothing(committed, ready, fakes):
    user, storage, video_id = ready
    with committed() as db:
        db.scalar(select(Publication).where(Publication.video_id == video_id)).status = "cancelled"
        db.commit()
    assert run_publish(committed, storage, video_id, user.id).status == "done"
    assert fakes.reels == {}


def test_the_post_list_shows_who_cancelled_or_deleted_and_when(an, db, me, storage):
    video = make_video(db, storage, me)
    moment = datetime.now(UTC).replace(microsecond=0)
    add_post(db, video, me, None, status="cancelled", closed_at=moment, closed_by_id=me.id, remote_id=None)
    (row,) = an.get("/api/posts").json()
    assert (row["status"], row["closed_by"], row["url"], row["busy"]) == ("cancelled", "Nguyễn Văn An", None, False)
    assert datetime.fromisoformat(row["closed_at"]) == moment
    assert row["at"], "a post cancelled before its upload has no posting time of its own"


def test_a_deleted_reel_loses_its_link(an, db, me, storage):
    video = make_video(db, storage, me)
    add_post(db, video, me, None, status="deleted", published_at=datetime.now(UTC))
    assert an.get("/api/posts").json()[0]["url"] is None


# --- Checking a post against Facebook ---


def run_check(factory, storage, post_id, video_id, user_id) -> Job:
    from reels_api import jobs

    job_id = add_job(factory, video_id, user_id, kind="check", status="running", publication_id=post_id)
    jobs.run_job(job_id, factory, storage)
    return job_row(factory, job_id)


def scheduled_post(committed, storage, ready, hours: float) -> Publication:
    """A reel Facebook accepted for a time, then that time moved to `hours` from now."""
    user, storage, video_id = ready
    schedule(committed, video_id, 2)
    run_publish(committed, storage, video_id, user.id)
    schedule(committed, video_id, hours)
    return post_of(committed, video_id)


def queue_checks(factory) -> list[Job]:
    """One round of the worker's loop."""
    from reels_api import worker

    worker.queue_checks(factory)
    with factory() as db:
        return list(db.scalars(select(Job).where(Job.kind == "check")))


def test_a_scheduled_reel_cancelled_on_facebook_is_not_shown_as_posted_after_its_time(committed, ready, fakes):
    """The bug: Facebook dropped the reel, but once its time passed the app showed "Đã đăng" with a dead link."""
    user, storage, video_id = ready
    post = scheduled_post(committed, storage, ready, -1)
    live_sibling(committed, fakes, user, storage, ready)
    del fakes.reels[post.remote_id]
    (queued,) = queue_checks(committed)
    assert (queued.publication_id, queued.video_id, queued.status) == (post.id, video_id, "queued")
    with committed() as db:
        db.get(Job, queued.id).status = "running"
        db.commit()
    from reels_api import jobs

    jobs.run_job(queued.id, committed, storage)
    assert job_row(committed, queued.id).status == "done"
    post = post_of(committed, video_id)
    assert post.status == "deleted", "its time passed, so people may have seen it"
    assert (post.closed_by_id, post.closed_at is not None) == (None, True), "closed on Facebook, not by a member"


def test_a_post_is_checked_once_after_its_time_and_not_before(committed, ready, fakes):
    user, storage, video_id = ready
    scheduled_post(committed, storage, ready, 1)
    assert queue_checks(committed) == []
    schedule(committed, video_id, -0.05)
    assert queue_checks(committed) == [], "Facebook gets a few minutes to publish it"
    schedule(committed, video_id, -1)
    assert len(queue_checks(committed)) == 1
    with committed() as db:
        db.execute(update(Job).where(Job.kind == "check").values(status="failed"))
        db.commit()
    assert len(queue_checks(committed)) == 1, "a failed check is not queued again: a member can retry it"


def test_no_check_is_queued_while_the_video_has_a_job(committed, ready, fakes):
    user, storage, video_id = ready
    scheduled_post(committed, storage, ready, -1)
    add_job(committed, video_id, user.id, kind="render")
    assert queue_checks(committed) == []


def test_the_check_records_a_reel_facebook_published(committed, ready, fakes):
    user, storage, video_id = ready
    post = scheduled_post(committed, storage, ready, -1)
    only_reel(fakes)["state"] = "published"
    assert run_check(committed, storage, post.id, video_id, user.id).status == "done"
    post = post_of(committed, video_id)
    assert (post.status, post.closed_at, post.checked_at is not None) == ("published", None, True)


def test_the_check_takes_a_new_time_set_on_facebook(committed, ready, fakes):
    user, storage, video_id = ready
    post = scheduled_post(committed, storage, ready, -1)
    later = datetime.now(UTC).replace(microsecond=0) + timedelta(days=1)
    only_reel(fakes)["scheduled_publish_time"] = str(int(later.timestamp()))
    run_check(committed, storage, post.id, video_id, user.id)
    post = post_of(committed, video_id)
    assert (post.status, post.scheduled_at) == ("scheduled", later)


def test_the_check_closes_a_reel_facebook_will_not_publish_before_its_time(committed, ready, fakes):
    user, storage, video_id = ready
    post = scheduled_post(committed, storage, ready, 1)
    only_reel(fakes)["state"] = "draft"
    run_check(committed, storage, post.id, video_id, user.id)
    post = post_of(committed, video_id)
    assert (post.status, post.closed_by_id) == ("cancelled", None)
    assert len(fakes.reels) == 1, "a check never deletes anything"


def test_the_check_closes_a_live_reel_deleted_on_facebook(committed, ready, fakes):
    """A reel deleted in Meta Business Suite answers 400 (#100), not 404: it is deleted when the same token still reads
    another reel of the Page."""
    user, storage, video_id = ready
    run_publish(committed, storage, video_id, user.id)
    live_sibling(committed, fakes, user, storage, ready)
    del fakes.reels[post_of(committed, video_id).remote_id]
    job = run_check(committed, storage, post_of(committed, video_id).id, video_id, user.id)
    assert job.status == "done", (job.error, job.error_detail)
    post = post_of(committed, video_id)
    assert (post.status, post.closed_by_id) == ("deleted", None)


def test_a_reel_the_token_cannot_read_is_not_taken_for_deleted(committed, ready, fakes):
    """2026-11-13: the token still read the Page but no reel, and Facebook answered 400 (#100) for live reels, so both
    posts were marked deleted. Not one reel of the Page reads: nothing proves this one is gone."""
    user, storage, video_id = ready
    run_publish(committed, storage, video_id, user.id)
    live_sibling(committed, fakes, user, storage, ready)
    for reel in fakes.reels.values():
        reel["lost"] = True  # live, but this token is refused every reel
    job = run_check(committed, storage, post_of(committed, video_id).id, video_id, user.id)
    assert job.status == "failed"
    assert job.error.startswith("Không đọc được trạng thái reel")
    assert post_of(committed, video_id).status == "published"
    take_down = run_unpublish(committed, storage, post_of(committed, video_id).id, video_id, user.id)
    assert take_down.status == "failed"
    assert post_of(committed, video_id).status == "published"


def test_a_reel_with_no_other_reel_to_compare_stays_unknown(committed, ready, fakes):
    user, storage, video_id = ready
    run_publish(committed, storage, video_id, user.id)
    fakes.reels.clear()
    job = run_check(committed, storage, post_of(committed, video_id).id, video_id, user.id)
    assert job.status == "failed"
    assert post_of(committed, video_id).status == "published"


def test_a_deleted_post_that_is_live_on_facebook_goes_back_to_published(committed, ready, fakes):
    user, storage, video_id = ready
    run_publish(committed, storage, video_id, user.id)
    with committed() as db:
        post = db.scalar(select(Publication).where(Publication.video_id == video_id))
        post.status, post.closed_at, post.published_at = "deleted", datetime.now(UTC), None
        db.commit()
    job = run_check(committed, storage, post_of(committed, video_id).id, video_id, user.id)
    assert job.status == "done", (job.error, job.error_detail)
    post = post_of(committed, video_id)
    assert (post.status, post.closed_at, post.closed_by_id) == ("published", None, None)
    assert post.published_at is not None


def test_a_deleted_post_really_gone_from_facebook_stays_deleted(committed, ready, fakes):
    user, storage, video_id = ready
    run_publish(committed, storage, video_id, user.id)
    live_sibling(committed, fakes, user, storage, ready)
    del fakes.reels[post_of(committed, video_id).remote_id]
    with committed() as db:
        post = db.scalar(select(Publication).where(Publication.video_id == video_id))
        post.status = "deleted"
        db.commit()
    job = run_check(committed, storage, post_of(committed, video_id).id, video_id, user.id)
    assert job.status == "failed", "a post that stays deleted says why"
    assert job.error.startswith("Facebook không trả reel này")
    assert post_of(committed, video_id).status == "deleted"


def test_check_endpoint_accepts_a_deleted_post(an, db, me, storage):
    video = make_video(db, storage, me)
    add_mp4(db, storage, video)
    post = add_post(db, video, me, fanpage_id(db, me))
    post.status, post.remote_id = "deleted", "1000"
    db.commit()
    payload = an.post(f"/api/posts/{post.id}/check").json()
    assert payload["active_job"]["kind"] == "check"


def test_a_failed_check_leaves_the_post_as_it_was(committed, ready, fakes):
    user, storage, video_id = ready
    post = scheduled_post(committed, storage, ready, -1)
    fakes.facebook_status_fails = 1
    job = run_check(committed, storage, post.id, video_id, user.id)
    assert job.status == "failed"
    assert job.error.startswith("Không đọc được trạng thái reel")
    assert post_of(committed, video_id).status == "scheduled"


def test_check_endpoint_queues_a_check_of_the_post(an, db, me, storage):
    video = make_video(db, storage, me)
    add_mp4(db, storage, video)
    post = add_post(db, video, me, fanpage_id(db, me))
    payload = an.post(f"/api/posts/{post.id}/check").json()
    assert (payload["active_job"]["kind"], payload["status_label"]) == ("check", "Chờ thứ 1")
    job = db.scalar(select(Job).where(Job.video_id == video.id))
    assert job.publication_id == post.id
    refused = an.post(f"/api/posts/{post.id}/check")
    assert (refused.status_code, refused.json()["message"]) == (
        409,
        "Video đang có job chạy, hãy đợi xong rồi kiểm tra bài",
    )


@pytest.mark.parametrize("fields", [{"status": "cancelled"}, {"status": "pending", "remote_id": None}])
def test_only_a_post_facebook_holds_can_be_checked(an, db, me, storage, fields):
    video = make_video(db, storage, me)
    post = add_post(db, video, me, None, **fields)
    refused = an.post(f"/api/posts/{post.id}/check")
    assert (refused.status_code, refused.json()["code"]) == (409, "post_not_checkable")


def test_checking_needs_a_login_and_a_post(an, client):
    assert an.post("/api/posts/999/check").status_code == 404
    client.cookies.clear()
    assert client.post("/api/posts/999/check").status_code == 401
