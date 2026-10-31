from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select, update

from conftest import login, make_user, make_video
from fake_services import FACEBOOK_PAGE, FACEBOOK_TOKEN
from reels_api import facebook, page_settings
from reels_api.models import Job, Publication, Setting, Video
from reels_api.storage import DirectoryStorage
from reels_api.videos import render_signature, split_scenes
from worker_helpers import add_job, add_user, committed, job_row  # noqa: F401  (fixtures)


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


def in_minutes(minutes: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


# --- The endpoint ---

def test_publish_queues_a_job_and_locks_the_video(an, db, me, storage):
    video = make_video(db, storage, me)
    add_mp4(db, storage, video)
    payload = an.post(f"/api/videos/{video.id}/publish", json={}).json()
    assert payload["active_job"]["kind"] == "publish"
    assert payload["status_label"] == "Chờ thứ 1"
    assert payload["publication"] == {"status": "pending", "scheduled_at": None, "url": None}
    refused = an.patch(f"/api/videos/{video.id}", json={"caption": "khác"})
    assert (refused.status_code, refused.json()["message"]) == (409, "Video đang đăng lên Facebook, chưa lưu")


def test_publish_needs_a_current_mp4(an, db, me, storage):
    video = make_video(db, storage, me)
    missing = an.post(f"/api/videos/{video.id}/publish", json={})
    assert (missing.status_code, missing.json()["message"]) == (409, "Video chưa có MP4, hãy render trước")

    add_mp4(db, storage, video)
    title, scenes = split_scenes(db, video)
    scenes[0].text = "Chữ đã sửa"
    db.commit()
    outdated = an.post(f"/api/videos/{video.id}/publish", json={})
    assert (outdated.status_code, outdated.json()["code"]) == (409, "mp4_outdated")
    assert db.scalar(select(Job).where(Job.video_id == video.id)) is None


@pytest.mark.parametrize("minutes", [14, 29 * 24 * 60 + 5])
def test_scheduled_time_must_be_one_facebook_accepts(an, db, me, storage, minutes):
    video = make_video(db, storage, me)
    add_mp4(db, storage, video)
    refused = an.post(f"/api/videos/{video.id}/publish", json={"scheduled_at": in_minutes(minutes)})
    assert (refused.status_code, refused.json()["message"]) == (
        422, "Giờ hẹn phải sau ít nhất 15 phút và trong vòng 29 ngày tới")


@pytest.mark.parametrize("minutes", [16, 29 * 24 * 60 - 5])
def test_a_time_inside_the_limits_is_accepted_and_shown_as_scheduled_once_done(an, db, me, storage, minutes):
    video = make_video(db, storage, me)
    add_mp4(db, storage, video)
    assert an.post(f"/api/videos/{video.id}/publish", json={"scheduled_at": in_minutes(minutes)}).status_code == 200
    post = db.scalar(select(Publication).where(Publication.video_id == video.id))
    db.execute(update(Job).where(Job.video_id == video.id).values(status="done"))
    post.status, post.remote_id = "scheduled", "1000"
    db.commit()
    shown = an.get(f"/api/videos/{video.id}").json()["publication"]
    assert (shown["status"], shown["url"]) == ("scheduled", None), "not public yet: no link"


def test_scheduled_time_needs_a_time_zone(an, db, me, storage):
    video = make_video(db, storage, me)
    add_mp4(db, storage, video)
    refused = an.post(f"/api/videos/{video.id}/publish", json={"scheduled_at": "2030-01-01T11:00:00"})
    assert (refused.status_code, refused.json()["message"]) == (422, "Giờ đăng phải kèm múi giờ")


@pytest.mark.parametrize("status", ["scheduled", "published"])
def test_a_video_is_posted_only_once(an, db, me, storage, status):
    video = make_video(db, storage, me)
    add_mp4(db, storage, video)
    scheduled_at = datetime.now(timezone.utc) + timedelta(days=1)
    db.add(Publication(video_id=video.id, platform="facebook", status=status, remote_id="1000",
                       scheduled_at=scheduled_at if status == "scheduled" else None, created_by_id=me.id))
    db.commit()
    refused = an.post(f"/api/videos/{video.id}/publish", json={})
    assert (refused.status_code, refused.json()["code"]) == (409, "already_published")


def test_a_scheduled_post_counts_as_published_once_its_time_has_passed(an, db, me, storage):
    video = make_video(db, storage, me)
    db.add(Publication(video_id=video.id, platform="facebook", status="scheduled", remote_id="1000",
                       scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=1), created_by_id=me.id))
    db.commit()
    post = an.get(f"/api/videos/{video.id}").json()["publication"]
    assert (post["status"], post["url"]) == ("published", "https://www.facebook.com/reel/1000")


def test_a_failed_publish_can_be_sent_again_with_a_new_time(an, db, me, storage):
    video = make_video(db, storage, me)
    add_mp4(db, storage, video)
    db.add(Publication(video_id=video.id, platform="facebook", scheduled_at=datetime.now(timezone.utc),
                       created_by_id=me.id))
    db.commit()
    db.add(Job(video_id=video.id, kind="publish", status="failed", created_by_id=me.id))
    db.commit()
    when = in_minutes(60)
    payload = an.post(f"/api/videos/{video.id}/publish", json={"scheduled_at": when}).json()
    assert payload["active_job"]["kind"] == "publish"
    assert datetime.fromisoformat(payload["publication"]["scheduled_at"]) == datetime.fromisoformat(when)


def test_a_failed_publish_is_not_shown_as_a_failed_render(an, db, me, storage):
    video = make_video(db, storage, me)
    add_mp4(db, storage, video)
    db.add(Job(video_id=video.id, kind="publish", status="failed", error="Facebook từ chối đăng video này",
               created_by_id=me.id))
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
        db.add(Publication(video_id=video.id, platform="facebook", created_by_id=user.id))
        page_settings.save(db, FACEBOOK_PAGE, FACEBOOK_TOKEN, user.id)
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


def test_scheduling_lets_facebook_publish_at_the_time(committed, ready, fakes):
    user, storage, video_id = ready
    when = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=2)
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
        post.scheduled_at = datetime.now(timezone.utc) + timedelta(minutes=2)
        db.commit()
    job = run_publish(committed, storage, video_id, user.id)
    assert (job.status, job.error) == ("failed", "Giờ hẹn đã qua hoặc còn dưới 10 phút, hãy chọn giờ khác rồi bấm đăng lại")
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
    only_reel(fakes)["lost"] = True
    assert run_publish(committed, storage, video_id, user.id).status == "done"
    assert [reel["state"] for reel in fakes.reels.values()] == ["draft", "published"]


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
        "failed", "Facebook có thể vẫn đang đăng bản trước, hãy xem Page, đợi 30 phút rồi Thử lại")
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
    when = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=2)
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
        db.scalar(select(Publication).where(Publication.video_id == video_id)).scheduled_at = (
            datetime.now(timezone.utc) + timedelta(hours=1))
        db.commit()
    fakes.facebook_finish_replies_lost = 1
    assert run_publish(committed, storage, video_id, user.id).status == "failed"
    with committed() as db:
        db.scalar(select(Publication).where(Publication.video_id == video_id)).scheduled_at = (
            datetime.now(timezone.utc) + timedelta(minutes=1))
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
    db.add(Publication(video_id=video.id, platform="facebook", remote_id="1000", remote_mp4_key=video.mp4_key,
                       created_by_id=me.id))
    db.commit()
    assert an.post(f"/api/videos/{video.id}/publish", json={"scheduled_at": in_minutes(60)}).status_code == 200
    post = db.scalar(select(Publication).where(Publication.video_id == video.id))
    assert (post.remote_id, post.remote_mp4_key) == ("1000", video.mp4_key)


def test_facebooks_time_wins_over_the_time_asked_last(committed, ready, fakes):
    user, storage, video_id = ready
    when = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=2)
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
        db.scalar(select(Publication).where(Publication.video_id == video_id)).scheduled_at = (
            datetime.now(timezone.utc) + timedelta(hours=1))
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
        page_settings.save(db, FACEBOOK_PAGE, "het-han", user.id)
        db.commit()
    job = run_publish(committed, storage, video_id, user.id)
    assert (job.status, job.error) == ("failed", "Token Facebook hết hạn hoặc không hợp lệ, hãy nhập lại trong Cài đặt")
    assert "het-han" not in (job.error_detail or "")


def test_missing_settings_fail_with_a_clear_reason(committed, ready, fakes):
    user, storage, video_id = ready
    with committed() as db:
        db.execute(delete(Setting))
        db.commit()
    job = run_publish(committed, storage, video_id, user.id)
    assert (job.status, job.error) == ("failed", "Chưa nhập Page ID và token, hãy vào Cài đặt")
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
