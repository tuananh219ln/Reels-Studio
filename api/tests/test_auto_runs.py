"""Semi-automatic posting ("Bán tự động", brief docs/specs/semi-auto-posting): the worker's round makes today's plan
ideas into videos waiting for the Page owner's approval; approving schedules the Facebook post and the TikTok draft.
Jobs are not run here: their outcome is set by hand, as the worker would leave it."""

from datetime import datetime, timedelta

import pytest
from conftest import client_for, first_topic, login, make_user, make_video
from sqlalchemy import func, select
from test_page_queue import add_mp4, page
from test_tiktok_publish import connected_account

from reels_api import auto_runs, plans
from reels_api.analytics import VIETNAM
from reels_api.models import AutoRun, Job, Publication, Scene, TopicPlanItem, Video

DAY = datetime(2026, 11, 10, tzinfo=VIETNAM).date()
EIGHT = datetime(2026, 11, 10, 8, 0, tzinfo=VIETNAM)


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def plan(db, ideas=("5 món sáng giúp ổn định huyết áp",), start=DAY, day=1):
    topic = first_topic(db)
    topic.plan_start_date = start
    items = [
        TopicPlanItem(knowledge_topic_id=topic.id, day=day, position=n, topic=name)
        for n, name in enumerate(ideas, start=1)
    ]
    db.add_all(items)
    db.commit()
    return items


def auto_page(db, user, times=("20:00",), **fields):
    row = page(db, user, times=list(times))
    row.auto_prepare = True
    for name, value in fields.items():
        setattr(row, name, value)
    db.commit()
    return row


def runs(db) -> list[AutoRun]:
    db.expire_all()
    return list(db.scalars(select(AutoRun).order_by(AutoRun.id)))


def finish(db, job_id: int, status="done", error=None) -> None:
    job = db.get(Job, job_id)
    job.status, job.error = status, error
    db.commit()


def ready_video(db, storage, user, idea: TopicPlanItem, mp4=True) -> Video:
    """The idea's video with its script and photos; with its MP4 when `mp4`."""
    video = make_video(db, storage, user, scene_count=3)
    idea.video_id = video.id
    db.commit()
    if mp4:
        add_mp4(db, storage, video)
    return video


# --- Preparing ---


def test_at_its_preparing_time_a_page_makes_todays_idea_into_a_video_once(db, me):
    [idea] = plan(db)
    auto_page(db, me)

    auto_runs.step(db, EIGHT - timedelta(minutes=1))
    assert runs(db) == []

    auto_runs.step(db, EIGHT)
    [run] = runs(db)
    assert (run.day, run.status, run.stage, run.plan_item_id, run.idea_topic) == (
        DAY,
        "preparing",
        "script",
        idea.id,
        "5 món sáng giúp ổn định huyết áp",
    )
    video = db.get(Video, run.video_id)
    assert (video.topic, video.created_by_id) == ("5 món sáng giúp ổn định huyết áp", me.id)
    assert db.get(TopicPlanItem, idea.id).video_id == video.id
    script = db.get(Job, run.job_id)
    assert (script.kind, script.status, script.video_id) == ("script", "queued", video.id)

    # A second round the same day makes nothing new.
    auto_runs.step(db, EIGHT + timedelta(hours=2))
    assert len(runs(db)) == 1
    assert db.scalar(select(func.count()).select_from(Video)) == 1


def test_a_page_makes_as_many_videos_as_the_day_has_ideas(db, me):
    plan(db, ideas=("Ý tưởng một", "Ý tưởng hai"))
    auto_page(db, me)
    auto_runs.step(db, EIGHT)
    assert [run.idea_topic for run in runs(db)] == ["Ý tưởng một", "Ý tưởng hai"]
    assert db.scalar(select(func.count()).select_from(Video)) == 2


def test_a_day_without_an_idea_makes_nothing_and_says_why(db, me):
    plan(db, day=2)
    auto_page(db, me)
    auto_runs.step(db, EIGHT)
    [run] = runs(db)
    assert (run.status, run.reason, run.video_id) == ("skipped", auto_runs.NO_IDEA, None)
    assert db.scalar(select(func.count()).select_from(Video)) == 0
    auto_runs.step(db, EIGHT + timedelta(hours=1))
    assert len(runs(db)) == 1


def test_a_group_without_a_script_prompt_is_skipped_with_why(db, me):
    plan(db)
    first_topic(db).script_prompt = ""
    auto_page(db, me)
    auto_runs.step(db, EIGHT)
    [run] = runs(db)
    assert run.status == "skipped" and "chưa có prompt viết kịch bản" in run.reason


def test_a_page_not_switched_on_or_set_later_is_left_alone(db, me):
    plan(db)
    page(db, me)  # not switched on
    other = make_user(db, email="binh@doi.vn", name="Trần Bình")
    late = page(db, other, name="Trang muộn", page_id="222")
    late.auto_prepare, late.prepare_time = True, "09:30"
    db.commit()
    auto_runs.step(db, EIGHT)
    assert runs(db) == []


def test_an_idea_whose_video_is_already_posted_is_skipped(db, me, storage):
    [idea] = plan(db)
    row = auto_page(db, me)
    video = ready_video(db, storage, me, idea)
    db.add(
        Publication(video_id=video.id, platform="facebook", fanpage_id=row.id, created_by_id=me.id, status="scheduled")
    )
    db.commit()
    auto_runs.step(db, EIGHT)
    [run] = runs(db)
    assert run.status == "skipped" and "đã có lượt đăng Facebook" in run.reason


# --- The chain ---


def test_an_existing_video_is_rendered_and_waits_for_approval(db, me, storage):
    [idea] = plan(db)
    auto_page(db, me)
    video = ready_video(db, storage, me, idea, mp4=False)

    auto_runs.step(db, EIGHT)
    [run] = runs(db)
    assert run.video_id == video.id and db.scalar(select(func.count()).select_from(Video)) == 1
    render = db.get(Job, run.job_id)
    assert (render.kind, render.status) == ("render", "queued")

    # While the render waits for a render machine, the run says so.
    render.status, render.node_stage = "running", "ready"
    db.commit()
    auto_runs.step(db, EIGHT + timedelta(minutes=1))
    assert runs(db)[0].reason == auto_runs.WAITING_FOR_MACHINE

    render.status, render.node_stage = "done", None
    db.commit()
    add_mp4(db, storage, db.get(Video, video.id))
    auto_runs.step(db, EIGHT + timedelta(minutes=2))
    [run] = runs(db)
    assert (run.status, run.reason, run.banned) == ("ready", None, [])


def test_scenes_without_photos_get_a_photo_search_first(db, me, storage):
    [idea] = plan(db)
    auto_page(db, me)
    video = ready_video(db, storage, me, idea, mp4=False)
    scene = db.scalar(select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)))
    scene.image_key = None
    db.commit()

    auto_runs.step(db, EIGHT)
    [run] = runs(db)
    assert db.get(Job, run.job_id).kind == "photos"


def test_a_failed_job_stops_the_run_with_why_and_nothing_is_posted(db, me):
    plan(db)
    auto_page(db, me)
    auto_runs.step(db, EIGHT)
    [run] = runs(db)
    finish(db, run.job_id, "failed", "Hết lượt gọi AI hôm nay")
    auto_runs.step(db, EIGHT + timedelta(minutes=5))
    [run] = runs(db)
    assert (run.status, run.reason) == ("failed", "Viết kịch bản lỗi: Hết lượt gọi AI hôm nay")
    assert db.scalar(select(func.count()).select_from(Publication)) == 0


def test_a_banned_word_still_waits_for_approval_but_is_flagged(db, me, storage):
    [idea] = plan(db)
    first_topic(db).banned_words = ["thần dược"]
    auto_page(db, me)
    video = ready_video(db, storage, me, idea, mp4=False)
    scene = db.scalar(select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)))
    scene.text = "Vừng đen là thần dược"
    db.commit()
    add_mp4(db, storage, db.get(Video, video.id))

    auto_runs.step(db, EIGHT)
    [run] = runs(db)
    assert run.status == "ready"
    assert run.banned == ["Có từ cấm: “thần dược”"]


# --- Approving ---


def waiting_run(db, storage, user, **page_fields) -> AutoRun:
    [idea] = plan(db)
    auto_page(db, user, **page_fields)
    ready_video(db, storage, user, idea)
    auto_runs.step(db, EIGHT)
    [run] = runs(db)
    assert run.status == "ready"
    return run


def test_approving_schedules_the_post_at_the_ideas_time_with_its_comment(db, me, storage):
    run = waiting_run(db, storage, me)
    auto_runs.approve(db, run, me.id, skip_tiktok=False, at=EIGHT + timedelta(hours=1))
    db.commit()
    post = db.get(Publication, run.publication_id)
    assert (post.platform, post.status, post.auto_comment) == ("facebook", "pending", True)
    assert post.scheduled_at == datetime(2026, 11, 10, 20, 0, tzinfo=VIETNAM)
    assert db.scalar(select(Job).where(Job.video_id == run.video_id, Job.status == "queued")).kind == "publish"
    assert (run.status, run.decided_by_id) == ("approved", me.id)
    # No TikTok account chosen for the Page: Facebook only, and the run says why.
    assert run.tiktok_state == "skipped" and run.tiktok_reason == "Page chưa chọn tài khoản TikTok"


def test_approving_after_the_ideas_time_takes_the_pages_next_free_time(db, me, storage):
    run = waiting_run(db, storage, me)
    auto_runs.approve(db, run, me.id, skip_tiktok=True, at=datetime(2026, 11, 10, 19, 50, tzinfo=VIETNAM))
    post = db.get(Publication, run.publication_id)
    assert post.scheduled_at == datetime(2026, 11, 11, 20, 0, tzinfo=VIETNAM)


def test_an_approved_run_sends_its_tiktok_draft_once_the_facebook_job_is_done(db, me, storage):
    account = connected_account(db, me)
    run = waiting_run(db, storage, me, tiktok_account_id=account.id)
    auto_runs.approve(db, run, me.id, skip_tiktok=False, at=EIGHT)
    db.commit()
    assert run.tiktok_state == "waiting"

    auto_runs.step(db, EIGHT + timedelta(minutes=1))  # the publish job still holds the video
    assert runs(db)[0].tiktok_state == "waiting"

    publish = db.scalar(select(Job).where(Job.video_id == run.video_id, Job.kind == "publish"))
    finish(db, publish.id)
    auto_runs.step(db, EIGHT + timedelta(minutes=2))
    [run] = runs(db)
    draft = db.get(Publication, run.tiktok_publication_id)
    assert run.tiktok_state == "sent"
    assert (draft.platform, draft.publish_mode, draft.affiliate_account_id, draft.video_id) == (
        "tiktok",
        "draft",
        account.id,
        run.video_id,
    )
    job = db.scalar(select(Job).where(Job.publication_id == draft.id))
    assert (job.kind, job.status) == ("tiktok_publish", "queued")


def test_skipping_tiktok_posts_to_facebook_only(db, me, storage):
    account = connected_account(db, me)
    run = waiting_run(db, storage, me, tiktok_account_id=account.id)
    auto_runs.approve(db, run, me.id, skip_tiktok=True, at=EIGHT)
    db.commit()
    publish = db.scalar(select(Job).where(Job.video_id == run.video_id, Job.kind == "publish"))
    finish(db, publish.id)
    auto_runs.step(db, EIGHT + timedelta(minutes=1))
    [run] = runs(db)
    assert (run.tiktok_state, run.tiktok_publication_id) == ("skipped", None)
    assert db.scalar(select(func.count()).select_from(Publication).where(Publication.platform == "tiktok")) == 0


def test_the_api_lists_approves_and_rejects_for_the_pages_owner_only(an, db, me, app, storage):
    run = waiting_run(db, storage, me, times=[f"{hour:02d}:00" for hour in range(14, 24)])
    other = make_user(db, email="binh@doi.vn", name="Trần Bình")
    binh = client_for(app)
    login(binh, email=other.email)

    listed = an.get("/api/auto-runs", params={"knowledge_topic_id": first_topic(db).id}).json()
    assert [(row["id"], row["status"], row["can_decide"]) for row in listed] == [(run.id, "ready", True)]
    assert listed[0]["video"]["id"] == run.video_id
    assert listed[0]["video"]["mp4_url"].startswith(f"/api/videos/{run.video_id}/video.mp4?v=")
    assert binh.get("/api/auto-runs").json()[0]["can_decide"] is False

    refused = binh.post(f"/api/auto-runs/{run.id}/approve", json={"skip_tiktok": True})
    assert refused.status_code == 409 and refused.json()["message"] == "Chỉ chủ Page mới duyệt được video của Page"

    rejected = an.post(f"/api/auto-runs/{run.id}/reject")
    assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"
    assert db.scalar(select(func.count()).select_from(Publication)) == 0
    again = an.post(f"/api/auto-runs/{run.id}/approve", json={"skip_tiktok": True})
    assert again.status_code == 409


def test_the_api_approves(an, db, me, storage):
    # Every hour from now on as a posting time, so the test never depends on the clock.
    run = waiting_run(db, storage, me)
    run.day = plans.today()
    db.commit()
    page_row = db.get(auto_runs.Fanpage, run.fanpage_id)
    page_row.post_times = [f"{hour:02d}:00" for hour in range(0, 24, 3)][:10]
    db.commit()
    approved = an.post(f"/api/auto-runs/{run.id}/approve", json={"skip_tiktok": True})
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved" and approved.json()["post_at"] is not None
    assert approved.json()["tiktok_state"] == "skipped"


def test_the_page_owner_switches_it_on_and_chooses_its_tiktok_account(an, db, me, app):
    row = page(db, me)
    account = connected_account(db, me)
    saved = an.put(
        f"/api/fanpages/{row.id}/auto",
        json={
            "auto_prepare": True,
            "prepare_time": "7:30",
            "tiktok_account_id": account.id,
            "tiktok_own_version": False,
        },
    )
    assert saved.status_code == 200, saved.text
    mine = next(page for page in saved.json() if page["id"] == row.id)
    assert mine["auto"] == {
        "auto_prepare": True,
        "prepare_time": "07:30",
        "tiktok_account_id": account.id,
        "tiktok_own_version": False,
        "tiktok_problem": None,
    }
    assert an.put(f"/api/fanpages/{row.id}/auto", json={"prepare_time": "25:00"}).status_code == 422

    other = make_user(db, email="binh@doi.vn", name="Trần Bình")
    binh = client_for(app)
    login(binh, email=other.email)
    assert binh.put(f"/api/fanpages/{row.id}/auto", json={"auto_prepare": False}).status_code == 403
    theirs = connected_account(db, other, open_id="other-open-id", username="binh")
    assert an.put(f"/api/fanpages/{row.id}/auto", json={"tiktok_account_id": theirs.id}).status_code == 422


def test_a_page_with_its_own_tiktok_version_clones_one_and_drafts_it(db, me, storage):
    account = connected_account(db, me)
    [idea] = plan(db)
    auto_page(db, me, tiktok_account_id=account.id, tiktok_own_version=True)
    source = ready_video(db, storage, me, idea)

    auto_runs.step(db, EIGHT)
    parent, child = runs(db)
    assert (parent.status, parent.stage, child.role, child.parent_id) == ("preparing", "tiktok", "tiktok", parent.id)
    clone = db.get(Video, child.video_id)
    assert (clone.platform, clone.variant_of_id) == ("tiktok", source.id)
    assert db.get(Job, child.job_id).kind == "clone"

    # The clone is written, has its photos and is rendered: the parent then waits for approval.
    finish(db, child.job_id)
    clone = db.get(Video, child.video_id)
    for scene in db.scalars(select(Scene).where(Scene.video_id == source.id)):
        db.add(
            Scene(
                video_id=clone.id,
                is_title=scene.is_title,
                position=scene.position,
                text=scene.text,
                seconds=scene.seconds,
                keywords=[],
                keywords_en=[],
                image_prompt="",
                image_key=scene.image_key,
            )
        )
    clone.has_script = True
    db.commit()
    add_mp4(db, storage, clone)
    auto_runs.step(db, EIGHT + timedelta(minutes=1))
    parent, child = runs(db)
    assert (child.status, parent.status) == ("ready", "ready")

    auto_runs.approve(db, parent, me.id, skip_tiktok=False, at=EIGHT)
    db.commit()
    finish(db, db.scalar(select(Job).where(Job.video_id == source.id, Job.kind == "publish")).id)
    auto_runs.step(db, EIGHT + timedelta(minutes=2))
    parent = runs(db)[0]
    draft = db.get(Publication, parent.tiktok_publication_id)
    assert (draft.video_id, draft.platform) == (clone.id, "tiktok")
    # The Facebook post stays the source's own MP4.
    assert db.get(Publication, parent.publication_id).video_id == source.id


def test_ideas_past_the_videos_a_day_are_kept_as_backups_and_not_made(db, me):
    """A day given more ideas than its videos a day (an import in "Thêm vào cuối ngày") makes the first ones only."""
    plan(db, ideas=("Ý tưởng một", "Ý tưởng hai", "Ý tưởng ba"))
    first_topic(db).plan_per_day = 1
    db.commit()
    auto_page(db, me)
    auto_runs.step(db, EIGHT)
    assert [run.idea_topic for run in runs(db)] == ["Ý tưởng một"]
    assert db.scalar(select(func.count()).select_from(Video)) == 1


def test_a_backup_idea_is_not_made_while_the_first_idea_has_its_video(db, me, storage):
    first, _ = plan(db, ideas=("Ý tưởng một", "Ý tưởng hai"))
    first_topic(db).plan_per_day = 1
    db.commit()
    video = ready_video(db, storage, me, first)
    auto_page(db, me)
    auto_runs.step(db, EIGHT)
    [run] = runs(db)
    assert (run.idea_topic, run.video_id) == ("Ý tưởng một", video.id)
    assert db.scalar(select(func.count()).select_from(Video)) == 1
