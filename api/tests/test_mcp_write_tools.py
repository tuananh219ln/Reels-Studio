"""MCP write tools for running the team's flow from an assistant: a Page's queue taken from or reordered, plan ideas
added and edited, a video's channel and logo, the member's own failed or waiting jobs, and the TikTok version; each
goes through the web's own handler (decisions 2026-11-15)."""

from conftest import first_topic, make_user, make_video
from sqlalchemy import select
from test_mcp import call, grant, mcp_client, payload  # noqa: F401  (mcp_client is a fixture)
from test_mcp_duplicate_schedule import brand
from test_page_queue import page

from reels_api.models import Job, PageQueueItem, TopicPlanItem, Video


def queued(db, page_row, user, *videos):
    for position, video in enumerate(videos, start=1):
        db.add(PageQueueItem(fanpage_id=page_row.id, video_id=video.id, position=position, added_by_id=user.id))
    db.commit()


def test_a_video_is_taken_out_of_the_queue_and_the_rest_reordered(mcp_client, db, storage):  # noqa: F811
    me, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    mine = page(db, me, "Ăn Ngon Mỗi Ngày", page_id="999")
    first, second, third = (make_video(db, storage, me, scene_count=1) for _ in range(3))
    queued(db, mine, me, first, second, third)

    taken = call(mcp_client, token, "unschedule_video", video_id=second.id)
    assert not taken.get("isError"), taken
    assert [row["video_id"] for row in payload(taken)["queue"]] == [first.id, third.id]

    moved = call(mcp_client, token, "reorder_queue", fanpage_id=mine.id, video_ids=[third.id, first.id])
    assert not moved.get("isError"), moved
    assert [row["video_id"] for row in payload(moved)["queue"]] == [third.id, first.id]

    stale = call(mcp_client, token, "reorder_queue", fanpage_id=mine.id, video_ids=[third.id])
    assert stale["isError"] and "không khớp hàng chờ" in str(stale)
    assert call(mcp_client, token, "unschedule_video", video_id=second.id)["isError"]


def test_a_teammates_queue_is_not_changed(mcp_client, db, storage):  # noqa: F811
    _, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    teammate = make_user(db, email="binh@doi.vn", name="Trần Bình")
    theirs = page(db, teammate, "Trang của Bình", page_id="888")
    one, two = (make_video(db, storage, teammate, scene_count=1) for _ in range(2))
    queued(db, theirs, teammate, one, two)

    assert "Chỉ người thêm video" in str(call(mcp_client, token, "unschedule_video", video_id=one.id))
    assert "Chỉ chủ của Fanpage" in str(
        call(mcp_client, token, "reorder_queue", fanpage_id=theirs.id, video_ids=[two.id, one.id])
    )
    assert db.scalar(select(PageQueueItem.id).where(PageQueueItem.video_id == one.id)) is not None


def test_plan_ideas_are_added_and_edited_with_the_plans_rules(mcp_client, db):  # noqa: F811
    _, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    group = first_topic(db)

    added = call(
        mcp_client, token, "add_plan_idea", knowledge_topic_id=group.id, topic="Canh chua cá lóc", day=3, hook="Mẹo"
    )
    assert not added.get("isError"), added
    idea = payload(added)["idea"]
    assert (idea["topic"], idea["day"], idea["hook"]) == ("Canh chua cá lóc", 3, "Mẹo")
    again = call(mcp_client, token, "add_plan_idea", knowledge_topic_id=group.id, topic="Canh chua cá lóc")
    assert again["isError"]

    edited = call(mcp_client, token, "update_plan_idea", item_id=idea["id"], pain="Cá tanh", day=5)
    assert not edited.get("isError"), edited
    assert (payload(edited)["idea"]["pain"], payload(edited)["idea"]["day"]) == ("Cá tanh", 5)
    shelved = payload(call(mcp_client, token, "update_plan_idea", item_id=idea["id"], to_backlog=True))
    assert shelved["idea"]["day"] is None
    db.expire_all()
    assert db.get(TopicPlanItem, idea["id"]).pain == "Cá tanh"


def test_a_videos_channel_and_logo_are_set_from_its_page(mcp_client, db, storage):  # noqa: F811
    me, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    target = page(db, me, "Ăn Ngon Mỗi Ngày", page_id="999")
    mine = brand(db, me, "Ăn Ngon Mỗi Ngày", fanpage=target)
    video = make_video(db, storage, me, scene_count=1)

    done = call(mcp_client, token, "set_video_options", video_id=video.id, logo_fanpage_id=target.id)
    assert not done.get("isError"), done
    db.expire_all()
    assert (video.options["brand_id"], video.options["logo_enabled"]) == (mine.id, True)

    off = call(mcp_client, token, "set_video_options", video_id=video.id, logo_enabled=False)
    assert not off.get("isError"), off
    db.expire_all()
    assert video.options["logo_enabled"] is False

    teammate = make_user(db, email="binh@doi.vn", name="Trần Bình")
    theirs = brand(db, teammate, "Kênh của Bình")
    refused = call(mcp_client, token, "set_video_options", video_id=video.id, brand_id=theirs.id)
    assert refused["isError"] and "không có quyền dùng kênh" in str(refused)


def test_only_the_members_own_jobs_are_retried_or_cancelled(mcp_client, db, storage):  # noqa: F811
    me, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    teammate = make_user(db, email="binh@doi.vn", name="Trần Bình")
    video = make_video(db, storage, me, scene_count=1)
    other = make_video(db, storage, me, scene_count=1)
    waiting = Job(video_id=other.id, kind="render", status="queued", created_by_id=me.id)
    theirs = Job(video_id=other.id, kind="render", status="failed", created_by_id=teammate.id)
    failed = Job(video_id=video.id, kind="render", status="failed", error="FFmpeg lỗi", created_by_id=me.id)
    db.add_all([waiting, theirs, failed])
    db.commit()

    assert "do bạn tạo" in str(call(mcp_client, token, "retry_job", job_id=theirs.id))
    retried = call(mcp_client, token, "retry_job", job_id=failed.id)
    assert not retried.get("isError"), retried
    again = db.scalar(select(Job).where(Job.retry_of_id == failed.id))
    assert (again.kind, again.status, again.created_by_id) == ("render", "queued", me.id)
    assert "Chỉ thử lại được job bị lỗi" in str(call(mcp_client, token, "retry_job", job_id=waiting.id))

    cancelled = call(mcp_client, token, "cancel_job", job_id=waiting.id)
    assert not cancelled.get("isError"), cancelled
    db.expire_all()
    assert db.get(Job, waiting.id).status == "cancelled"
    assert "do bạn tạo" in str(call(mcp_client, token, "cancel_job", job_id=theirs.id))


def test_the_tiktok_version_is_queued_as_the_webs_button_makes_it(mcp_client, db, storage):  # noqa: F811
    me, _, tokens, _ = grant(mcp_client, db)
    source = make_video(db, storage, me, scene_count=1)

    made = call(mcp_client, tokens["access_token"], "make_tiktok_version", video_id=source.id)

    assert not made.get("isError"), made
    version = db.get(Video, payload(made)["id"])
    assert version.platform == "tiktok" and version.variant_of_id == source.id
    job = db.scalar(select(Job).where(Job.video_id == version.id))
    assert (job.kind, job.status, job.created_by_id) == ("clone", "queued", me.id)
    assert "Viết lại cho TikTok" in version.clone_source["request"]
