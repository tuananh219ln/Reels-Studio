"""The review gate: nothing is scheduled or posted until a member approves the MP4, and a new MP4 goes back to review
(docs/decisions/2026-11-26-review-gate.md)."""

import pytest
from conftest import login, make_user, make_video
from fake_services import FACEBOOK_PAGE, FACEBOOK_TOKEN
from sqlalchemy import select
from test_mcp import call, grant, mcp_client, payload  # noqa: F401  (mcp_client is a fixture)
from test_page_queue import page
from test_publish import add_mp4, fanpage_id
from worker_helpers import add_job, add_user, committed, job_row  # noqa: F401  (fixtures)

from reels_api import fanpages, jobs, review
from reels_api.models import Job, PageQueueItem, Publication, Video, VideoEvent
from reels_api.storage import DirectoryStorage


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def rendered(db, storage, user) -> Video:
    video = make_video(db, storage, user, scene_count=1)
    add_mp4(db, storage, video, approved=False)
    return video


def approve(an, video, acknowledge_qc=True):
    """The factory's video is short, so its script checks warn: members acknowledge them, as the web's "Vẫn duyệt"."""
    return an.post(f"/api/review/{video.id}/approve", json={"acknowledge_qc": acknowledge_qc})


def events(db, video) -> list[str]:
    return list(db.scalars(select(VideoEvent.type).where(VideoEvent.video_id == video.id).order_by(VideoEvent.id)))


# --- The gate ---


def test_a_new_video_waits_for_review_and_cannot_be_posted(an, db, me, storage):
    video = rendered(db, storage, me)
    assert video.review_status == "pending_review"
    refused = an.post(f"/api/videos/{video.id}/publish", json={"fanpage_id": fanpage_id(db, me)})
    assert (refused.status_code, refused.json()["code"]) == (409, "not_approved")
    assert db.scalar(select(Publication.id).where(Publication.video_id == video.id)) is None


def test_an_approved_video_can_be_posted_and_the_approval_is_recorded(an, db, me, storage):
    video = rendered(db, storage, me)
    answer = approve(an, video)
    assert answer.status_code == 200, answer.text
    assert answer.json()["review"]["status"] == "approved" and answer.json()["review"]["can_post"] is True
    db.expire_all()
    assert (video.approved_by_id, video.approved_via) == (me.id, "web")
    assert events(db, video) == ["approved"]
    posted = an.post(f"/api/videos/{video.id}/publish", json={"fanpage_id": fanpage_id(db, me)})
    assert posted.status_code == 200 and posted.json()["active_job"]["kind"] == "publish"


def test_the_other_posting_routes_are_gated_too(an, db, me, storage):
    video = rendered(db, storage, me)
    for path in ("/api/instagram/videos/%d/publish", "/api/tiktok/videos/%d/publish", "/api/youtube/videos/%d/upload"):
        refused = an.post(path % video.id, json={"fanpage_id": 1, "account_id": 1, "channel_id": 1, "title": "x"})
        assert (refused.status_code, refused.json().get("code")) == (409, "not_approved"), (path, refused.text)


def test_the_page_queue_refuses_a_video_that_is_not_approved(an, db, me, storage):
    video = rendered(db, storage, me)
    row = page(db, me, "Trang", page_id="1")
    refused = an.post("/api/queue", json={"video_id": video.id, "fanpage_id": row.id})
    assert (refused.status_code, refused.json()["message"]) == (409, review.NOT_APPROVED)
    approve(an, video)
    assert an.post("/api/queue", json={"video_id": video.id, "fanpage_id": row.id}).status_code == 200


def test_an_approval_does_not_hold_for_another_mp4(an, db, me, storage):
    video = rendered(db, storage, me)
    approve(an, video)
    video.rendered_signature = "another-mp4"
    db.commit()
    assert review.publish_blocker(video) == review.NOT_APPROVED


# --- Approving ---


def test_approving_needs_a_finished_up_to_date_render(an, db, me, storage):
    plain = make_video(db, storage, me, scene_count=1)
    answer = approve(an, plain)
    assert (answer.status_code, answer.json()["code"]) == (409, "render_not_done")
    video = rendered(db, storage, me)
    video.rendered_signature = "old"
    db.commit()
    answer = approve(an, video)
    assert (answer.status_code, answer.json()["code"]) == (409, "qc_blocker")
    assert "chưa cập nhật" in answer.json()["message"]


def test_a_warning_needs_an_acknowledgement(an, db, me, storage):
    video = rendered(db, storage, me)
    video.qc = {"status": "fail", "checks": [{"status": "fail", "detail": "Âm lượng quá nhỏ"}]}
    db.commit()
    detail = an.get(f"/api/videos/{video.id}").json()["review"]["qc"]
    assert detail["passed"] is False and detail["items"][0]["level"] == "warn"
    answer = approve(an, video, acknowledge_qc=False)
    assert (answer.status_code, answer.json()["code"]) == (409, "qc_not_acknowledged")
    assert approve(an, video).status_code == 200


def test_a_video_cannot_be_approved_twice(an, db, me, storage):
    video = rendered(db, storage, me)
    approve(an, video)
    again = approve(an, video)
    assert (again.status_code, again.json()["code"]) == (409, "not_pending")


# --- Rejecting ---


def test_a_rejected_video_leaves_the_queue_and_can_be_restored(an, db, me, storage):
    video = rendered(db, storage, me)
    row = page(db, me, "Trang", page_id="1")
    approve(an, video)
    an.post("/api/queue", json={"video_id": video.id, "fanpage_id": row.id})
    assert db.scalar(select(PageQueueItem.id).where(PageQueueItem.video_id == video.id)) is not None
    answer = an.post(f"/api/review/{video.id}/reject", json={"reason": "hình xấu"})
    assert answer.status_code == 200 and answer.json()["review"]["status"] == "rejected"
    db.expire_all()
    assert db.scalar(select(PageQueueItem.id).where(PageQueueItem.video_id == video.id)) is None
    assert approve(an, video).json()["code"] == "not_pending"
    assert an.post(f"/api/review/{video.id}/restore").json()["review"]["status"] == "pending_review"
    assert events(db, video) == ["approved", "rejected", "restored"]


def test_a_video_with_a_post_cannot_be_rejected(an, db, me, storage):
    video = rendered(db, storage, me)
    approve(an, video)
    an.post(f"/api/videos/{video.id}/publish", json={"fanpage_id": fanpage_id(db, me)})
    db.execute(Job.__table__.delete().where(Job.video_id == video.id))
    db.commit()
    answer = an.post(f"/api/review/{video.id}/reject", json={})
    assert (answer.status_code, answer.json()["code"]) == (409, "already_posted")


def test_the_pending_count_is_the_videos_with_an_mp4_waiting(an, db, me, storage):
    rendered(db, storage, me)
    make_video(db, storage, me, scene_count=1)  # no MP4: nothing to review yet
    done = rendered(db, storage, me)
    approve(an, done)
    assert an.get("/api/review/pending-count").json() == {"count": 1}


# --- The gate switched off (docs/decisions/2026-11-27-review-gate-off.md) ---


def test_with_the_gate_off_a_video_posts_without_approval_and_shows_no_review(an, db, me, storage, monkeypatch):
    monkeypatch.setenv("REVIEW_GATE", "")
    video = rendered(db, storage, me)
    detail = an.get(f"/api/videos/{video.id}").json()
    assert detail["review"]["enabled"] is False and detail["review_label"] == ""
    assert an.get("/api/review/pending-count").json() == {"count": 0}
    posted = an.post(f"/api/videos/{video.id}/publish", json={"fanpage_id": fanpage_id(db, me)})
    assert posted.status_code == 200 and posted.json()["active_job"]["kind"] == "publish"


# --- A new render ---


def test_a_new_render_goes_back_to_review_and_withdraws_what_was_planned(an, db, me, storage):
    video = rendered(db, storage, me)
    row = page(db, me, "Trang", page_id="1")
    approve(an, video)
    db.add(PageQueueItem(fanpage_id=row.id, video_id=video.id, position=1, added_by_id=me.id))
    waiting = Publication(
        video_id=video.id, platform="instagram", status="scheduled", fanpage_id=row.id, created_by_id=me.id
    )
    db.add(waiting)
    db.commit()
    review.after_render(db, video.id)
    db.expire_all()
    assert video.review_status == "pending_review" and video.approved_signature is None and video.approved_by_id is None
    assert waiting.status == "cancelled"
    assert db.scalar(select(PageQueueItem.id).where(PageQueueItem.video_id == video.id)) is None
    assert events(db, video) == ["approved", "review_requested"]


def test_a_post_already_on_facebook_is_taken_down_when_the_video_is_rendered_again(an, db, me, storage):
    video = rendered(db, storage, me)
    approve(an, video)
    post = Publication(
        video_id=video.id,
        platform="facebook",
        status="scheduled",
        remote_id="777",
        fanpage_id=fanpage_id(db, me),
        created_by_id=me.id,
    )
    db.add(post)
    db.commit()
    review.after_render(db, video.id)
    db.expire_all()
    job = db.scalar(select(Job).where(Job.video_id == video.id))
    assert (job.kind, job.status, job.publication_id) == ("unpublish", "queued", post.id)


# --- The jobs check again (R3) ---


@pytest.fixture
def queued(committed, tmp_path):
    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    with committed() as db:
        video = rendered(db, storage, user)
        row = fanpages.save(db, FACEBOOK_PAGE, "Trang Dưỡng Sinh", FACEBOOK_TOKEN, user.id)
        db.add(Publication(video_id=video.id, platform="facebook", created_by_id=user.id, fanpage_id=row.id))
        db.commit()
    return user, storage, video.id


@pytest.mark.parametrize("kind", review.POSTING_JOBS)
def test_a_posting_job_of_a_video_that_is_not_approved_does_not_run(committed, queued, kind):
    user, storage, video_id = queued
    job_id = add_job(committed, video_id, user.id, kind=kind, status="running")
    jobs.run_job(job_id, committed, storage)
    job = job_row(committed, job_id)
    assert (job.status, job.error) == ("failed", review.NOT_APPROVED)
    with committed() as db:
        assert db.scalar(select(VideoEvent.type).where(VideoEvent.video_id == video_id)) == "publish_skipped"


# --- Muse (MCP) ---


def test_muse_lists_approves_and_rejects(mcp_client, db, storage):  # noqa: F811
    me, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    first, second = rendered(db, storage, me), rendered(db, storage, me)
    listed = payload(call(mcp_client, token, "get_pending_videos"))
    assert {row["id"] for row in listed["videos"]} == {first.id, second.id} and listed["total"] == 2
    assert listed["videos"][0]["editor_url"].endswith(f"/videos/{listed['videos'][0]['id']}")
    refused = call(mcp_client, token, "approve_video", video_id=first.id)
    assert refused["isError"] is True and "xác nhận" in refused["content"][0]["text"]
    done = payload(call(mcp_client, token, "approve_video", video_id=first.id, acknowledge_qc=True))
    assert done["review"]["status"] == "approved" and done["published"] == "none"
    db.expire_all()
    assert first.approved_via == "muse_chat"
    gone = payload(call(mcp_client, token, "reject_video", video_id=second.id, reason="không hợp"))
    assert gone["review"]["status"] == "rejected"
    assert payload(call(mcp_client, token, "get_pending_videos"))["videos"] == []


def test_muse_cannot_approve_twice_or_without_a_page_to_post(mcp_client, db, storage):  # noqa: F811
    me, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    video = rendered(db, storage, me)
    asked = call(mcp_client, token, "approve_video", video_id=video.id, publish="now")
    assert asked["isError"] is True and "fanpage_id" in asked["content"][0]["text"]
    db.expire_all()
    assert video.review_status == "pending_review"
    call(mcp_client, token, "approve_video", video_id=video.id, acknowledge_qc=True)
    again = call(mcp_client, token, "approve_video", video_id=video.id, acknowledge_qc=True)
    assert again["isError"] is True and "đã được duyệt" in again["content"][0]["text"]
