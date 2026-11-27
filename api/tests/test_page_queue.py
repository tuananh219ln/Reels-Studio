from datetime import datetime, timedelta

import pytest
from conftest import client_for, first_topic, login, make_user, make_video
from sqlalchemy import select

from reels_api import fanpages, page_queue
from reels_api.analytics import VIETNAM
from reels_api.models import Fanpage, Job, KnowledgeTopic, PageQueueItem, Publication, TopicPlanItem
from reels_api.storage import DirectoryStorage
from reels_api.videos import render_signature, split_scenes

# 08:00 in Vietnam: the group's default times (07:00, 11:30, 17:00, 20:00, 21:30) leave 11:30 as the next one.
MORNING = datetime(2026, 11, 10, 8, 0, tzinfo=VIETNAM)


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def add_mp4(db, storage: DirectoryStorage, video) -> None:
    video.mp4_key = f"videos/{video.id}/video-x.mp4"
    storage.save_bytes(video.mp4_key, b"mp4 bytes")
    title, scenes = split_scenes(db, video)
    video.rendered_signature = render_signature(video, title, scenes)
    video.review_status, video.approved_signature = "approved", video.rendered_signature
    db.commit()


def page(db, user, name="Trang Dưỡng Sinh", page_id="111", topic=True, times=None) -> Fanpage:
    row = fanpages.save(db, page_id, name, "EAAB-token-" + page_id, user.id)
    row.knowledge_topic_id = first_topic(db).id if topic else None
    row.post_times = times
    db.commit()
    return row


def rendered(db, storage, user):
    video = make_video(db, storage, user)
    add_mp4(db, storage, video)
    return video


def queue_item(db, page_row, video, user, position=1) -> PageQueueItem:
    item = PageQueueItem(fanpage_id=page_row.id, video_id=video.id, position=position, added_by_id=user.id)
    db.add(item)
    db.commit()
    return item


# --- Adding a video ---


def test_a_video_goes_to_the_members_own_page_of_its_topic_group(an, db, me, storage):
    other = make_user(db, email="binh@doi.vn", name="Trần Bình")
    page(db, other, "Trang của Bình", page_id="222")  # same group, someone else's Page
    page(db, me, "Trang không chủ đề", page_id="333", topic=False)
    mine = page(db, me, "Trang của An", page_id="111")
    video = rendered(db, storage, me)

    answer = an.post("/api/queue", json={"video_id": video.id})

    assert answer.status_code == 200
    item = answer.json()["item"]
    assert (item["fanpage_id"], item["fanpage"], item["added_by"], item["error"]) == (
        mine.id,
        "Trang của An",
        "Nguyễn Văn An",
        None,
    )
    assert an.get(f"/api/queue/videos/{video.id}").json()["item"]["id"] == item["id"]


def test_without_a_page_of_the_group_the_member_is_asked_to_choose(an, db, me, storage):
    page(db, me, topic=False)
    video = rendered(db, storage, me)

    refused = an.post("/api/queue", json={"video_id": video.id})

    assert (refused.status_code, refused.json()["code"]) == (409, "no_page_for_topic")
    assert refused.json()["message"] == f"Bạn chưa có Page cho nhóm “{first_topic(db).name}”, hãy chọn Page"
    chosen = an.post("/api/queue", json={"video_id": video.id, "fanpage_id": db.scalar(select(Fanpage.id))})
    assert chosen.status_code == 200


def test_only_a_current_mp4_goes_in_and_only_once(an, db, me, storage):
    page(db, me)
    video = make_video(db, storage, me)
    missing = an.post("/api/queue", json={"video_id": video.id})
    assert (missing.status_code, missing.json()["message"]) == (409, "Video chưa có MP4, hãy render trước")

    add_mp4(db, storage, video)
    title, scenes = split_scenes(db, video)
    scenes[0].text = "Chữ đã sửa"
    db.commit()
    outdated = an.post("/api/queue", json={"video_id": video.id})
    assert outdated.json()["message"] == "MP4 chưa cập nhật theo bản sửa, hãy render lại"

    add_mp4(db, storage, video)
    assert an.post("/api/queue", json={"video_id": video.id}).status_code == 200
    again = an.post("/api/queue", json={"video_id": video.id})
    assert (again.status_code, again.json()["code"]) == (409, "already_queued")


def test_a_tiktok_version_is_queued_for_facebook_too(an, db, me, storage):
    # Any video's MP4 may go to any platform (docs/decisions.md, 2026-11-08); until then a TikTok version was refused.
    page(db, me)
    video = rendered(db, storage, me)
    video.platform = "tiktok"
    db.commit()

    queued = an.post("/api/queue", json={"video_id": video.id})

    assert queued.status_code == 200, queued.text


# --- A Page's settings and order ---


def test_the_owner_sets_the_pages_group_and_times(an, db, me, storage):
    row = page(db, me, topic=False)
    topic = first_topic(db)

    answer = an.patch(f"/api/queue/pages/{row.id}", json={"knowledge_topic_id": topic.id, "post_times": ["20:00"]})

    shown = next(p for p in answer.json()["pages"] if p["id"] == row.id)
    assert (shown["topic"], shown["post_times"], shown["own_times"]) == (
        {"id": topic.id, "name": topic.name},
        ["20:00"],
        True,
    )
    back = an.patch(f"/api/queue/pages/{row.id}", json={"post_times": None}).json()
    shown = next(p for p in back["pages"] if p["id"] == row.id)
    assert (shown["post_times"], shown["own_times"], shown["topic"]["id"]) == (
        list(topic.plan_post_times),
        False,
        topic.id,
    )
    wrong = an.patch(f"/api/queue/pages/{row.id}", json={"post_times": ["25:00"]})
    assert (wrong.status_code, wrong.json()["message"]) == (422, "Giờ đăng “25:00” phải có dạng HH:MM")


def test_only_the_owner_changes_a_pages_queue(app, an, db, me, storage):
    other = make_user(db, email="binh@doi.vn", name="Trần Bình")
    theirs = page(db, other, "Trang của Bình", page_id="222")
    item = queue_item(db, theirs, rendered(db, storage, other), other)

    assert an.patch(f"/api/queue/pages/{theirs.id}", json={"post_times": ["20:00"]}).status_code == 403
    assert an.post(f"/api/queue/pages/{theirs.id}/order", json={"ids": [item.id]}).status_code == 403
    assert an.delete(f"/api/queue/items/{item.id}").status_code == 403

    binh = client_for(app)
    login(binh, email="binh@doi.vn")
    assert binh.delete(f"/api/queue/items/{item.id}").status_code == 200
    assert db.get(PageQueueItem, item.id) is None


def test_the_owner_reorders_the_whole_queue(an, db, me, storage):
    row = page(db, me)
    first = queue_item(db, row, rendered(db, storage, me), me, position=1)
    second = queue_item(db, row, rendered(db, storage, me), me, position=2)

    answer = an.post(f"/api/queue/pages/{row.id}/order", json={"ids": [second.id, first.id]})

    shown = next(p for p in answer.json()["pages"] if p["id"] == row.id)
    assert [item["id"] for item in shown["items"]] == [second.id, first.id]
    stale = an.post(f"/api/queue/pages/{row.id}/order", json={"ids": [first.id]})
    assert (stale.status_code, stale.json()["code"]) == (409, "queue_changed")


# --- Filling the Pages' times ---


def test_the_worker_schedules_the_first_video_at_the_next_free_time(db, me, storage):
    row = page(db, me)
    first = rendered(db, storage, me)
    second = rendered(db, storage, me)
    queue_item(db, row, first, me, position=1)
    queue_item(db, row, second, me, position=2)

    assert page_queue.fill(db, at=MORNING) == 1

    post = db.scalar(select(Publication).where(Publication.video_id == first.id))
    assert (post.fanpage_id, post.status, post.scheduled_at, post.created_by_id, post.auto_comment) == (
        row.id,
        "pending",
        MORNING.replace(hour=11, minute=30),
        me.id,
        True,
    )
    job = db.scalar(select(Job).where(Job.video_id == first.id))
    assert (job.kind, job.status) == ("publish", "queued")
    assert [item.video_id for item in page_queue.items_of(db, row.id)] == [second.id]

    # The next round takes the next time: 11:30 is now held by the first video's post.
    assert page_queue.fill(db, at=MORNING) == 1
    later = db.scalar(select(Publication).where(Publication.video_id == second.id))
    assert later.scheduled_at == MORNING.replace(hour=17, minute=0)


def test_a_time_held_by_a_post_made_by_hand_is_skipped(db, me, storage):
    row = page(db, me, times=["11:30", "20:00"])
    by_hand = rendered(db, storage, me)
    db.add(
        Publication(
            video_id=by_hand.id,
            platform="facebook",
            fanpage_id=row.id,
            status="scheduled",
            scheduled_at=MORNING.replace(hour=11, minute=45),
            created_by_id=me.id,
        )
    )
    video = rendered(db, storage, me)
    queue_item(db, row, video, me)

    page_queue.fill(db, at=MORNING)

    post = db.scalar(select(Publication).where(Publication.video_id == video.id))
    assert post.scheduled_at == MORNING.replace(hour=20, minute=0)


def test_a_video_that_cannot_go_keeps_its_reason_and_the_next_one_goes(db, me, storage):
    row = page(db, me)
    stuck = rendered(db, storage, me)
    title, scenes = split_scenes(db, stuck)
    scenes[0].text = "Sửa sau khi xếp hàng"
    db.commit()
    ready = rendered(db, storage, me)
    stuck_item = queue_item(db, row, stuck, me, position=1)
    queue_item(db, row, ready, me, position=2)

    assert page_queue.fill(db, at=MORNING) == 1

    db.refresh(stuck_item)
    assert (stuck_item.error, stuck_item.tried_at) == ("MP4 chưa cập nhật theo bản sửa, hãy render lại", MORNING)
    assert db.scalar(select(Publication).where(Publication.video_id == stuck.id)) is None
    assert db.scalar(select(Publication).where(Publication.video_id == ready.id)) is not None


def test_nothing_is_scheduled_past_48_hours_or_on_a_broken_page(db, me, storage):
    early = page(db, me, "Trang đăng 7 giờ", page_id="111", times=["07:00"])
    broken = page(db, me, "Trang lỗi token", page_id="222")
    broken.check_error = "Token hết hạn"
    db.commit()
    for position in (1, 2, 3):
        queue_item(db, early, rendered(db, storage, me), me, position=position)
    queue_item(db, broken, rendered(db, storage, me), me)

    # From 08:00, the next 48 hours hold 07:00 tomorrow and the day after, not a third one.
    assert [page_queue.fill(db, at=MORNING) for _ in range(3)] == [1, 1, 0]
    scheduled = db.scalars(select(Publication.scheduled_at).where(Publication.fanpage_id == early.id)).all()
    assert sorted(scheduled) == [MORNING.replace(hour=7) + timedelta(days=n) for n in (1, 2)]
    assert len(page_queue.items_of(db, early.id)) == 1
    assert db.scalar(select(Publication).where(Publication.fanpage_id == broken.id)) is None


def test_a_page_without_a_group_or_times_waits(db, me, storage):
    row = page(db, me, topic=False)
    queue_item(db, row, rendered(db, storage, me), me)

    assert page_queue.fill(db, at=MORNING) == 0
    assert page_queue.post_times(db, row) == []


def test_the_queue_page_lists_free_times_and_topics(an, db, me, storage):
    row = page(db, me, times=["20:00"])
    queue_item(db, row, rendered(db, storage, me), me)

    answer = an.get("/api/queue").json()

    shown = next(p for p in answer["pages"] if p["id"] == row.id)
    assert (shown["mine"], shown["healthy"], len(shown["items"]), answer["fill_ahead_hours"]) == (True, True, 1, 48)
    assert 1 <= len(shown["free_slots"]) <= 2
    assert {"id": first_topic(db).id, "name": first_topic(db).name} in answer["topics"]


# --- The zone the times are written in ---


def test_a_page_of_a_us_group_posts_at_its_new_york_time(db, me):
    row = page(db, me)
    topic = first_topic(db)
    topic.plan_post_times, topic.schedule_timezone = ["20:00"], "America/New_York"
    db.commit()
    assert page_queue.timezone_of(db, row) == "America/New_York"
    start = datetime(2027, 3, 13, 12, 0, tzinfo=VIETNAM)
    got = page_queue.free_slots(db, row, start, start + page_queue.FILL_AHEAD)
    # 13/3 20:00 EST is 01:00 UTC on the 14th; 14/3 20:00 EDT is 00:00 UTC on the 15th.
    assert [slot.isoformat() for slot in got] == ["2027-03-14T01:00:00+00:00", "2027-03-15T00:00:00+00:00"]


def test_a_page_with_own_times_and_no_zone_stays_in_vietnam(db, me):
    row = page(db, me, times=["09:00"])
    first_topic(db).schedule_timezone = "America/New_York"
    db.commit()
    assert page_queue.timezone_of(db, row) == "Asia/Ho_Chi_Minh"
    row.schedule_timezone = "America/Chicago"
    assert page_queue.timezone_of(db, row) == "America/Chicago"


def test_the_page_zone_is_set_through_the_api(an, db, me):
    row = page(db, me)
    url = f"/api/queue/pages/{row.id}"
    refused = an.patch(url, json={"schedule_timezone": "America/New_York"})
    assert refused.status_code == 422  # a zone of its own needs times of its own
    ok = an.patch(url, json={"post_times": ["20:00"], "schedule_timezone": "America/New_York"})
    assert ok.status_code == 200
    assert next(p for p in ok.json()["pages"] if p["id"] == row.id)["schedule_timezone"] == "America/New_York"
    assert an.patch(url, json={"schedule_timezone": "Europe/London"}).status_code == 422
    # Back to the group's times: the Page's own zone goes with them.
    back = an.patch(url, json={"post_times": None, "schedule_timezone": None})
    assert back.status_code == 200


def test_changing_the_zone_keeps_the_hours_or_converts_them(an, db, me):
    row = page(db, me, times=["20:00"])
    url = f"/api/queue/pages/{row.id}"
    kept = an.patch(url, json={"schedule_timezone": "America/New_York"})
    assert kept.status_code == 200
    db.refresh(row)
    assert (row.post_times, row.schedule_timezone) == (["20:00"], "America/New_York")
    assert an.patch(url, json={"schedule_timezone": "Asia/Ho_Chi_Minh", "convert_times": True}).status_code == 200
    db.refresh(row)
    # 20:00 New York is 07:00 or 08:00 in Vietnam the next morning, whichever side of the clock change today is on.
    assert row.post_times in (["07:00"], ["08:00"]) and row.schedule_timezone == "Asia/Ho_Chi_Minh"


def test_a_queued_post_remembers_its_slot_and_is_off_slot_after_the_times_change(db, me, storage, an):
    row = page(db, me, times=["20:00"])
    video = rendered(db, storage, me)
    queue_item(db, row, video, me)
    page_queue.fill(db, MORNING)
    post = db.scalars(select(Publication)).one()
    assert (post.slot_local, post.slot_timezone) == ("20:00", "Asia/Ho_Chi_Minh")
    # The dashboard looks ahead from the real now, so put the post on the next real 20:00 slot.
    from reels_api import schedule_tz
    from reels_api.sessions import now

    post.status = "scheduled"
    post.scheduled_at = schedule_tz.slots_between(["20:00"], "Asia/Ho_Chi_Minh", now(), now() + timedelta(days=2))[0]
    db.commit()
    shown = an.get(f"/api/fanpages/{row.id}/dashboard").json()["upcoming"]["posts"]
    assert [p["off_slot"] for p in shown] == [False]
    row.post_times = ["21:00"]
    db.commit()
    shown = an.get(f"/api/fanpages/{row.id}/dashboard").json()["upcoming"]["posts"]
    assert [p["off_slot"] for p in shown] == [True]


# --- The queue and the plan ---


def plan_idea(db, video=None) -> TopicPlanItem:
    """Day 1, place 2 of the group's plan starting on MORNING's day: 11:30."""
    group = db.get(KnowledgeTopic, first_topic(db).id)
    group.plan_start_date = MORNING.date()
    idea = TopicPlanItem(
        knowledge_topic_id=group.id, day=1, position=2, topic="Ý tưởng", video_id=video.id if video else None
    )
    db.add(idea)
    db.commit()
    return idea


def test_a_video_nobody_planned_leaves_a_time_a_plan_idea_holds(db, me, storage):
    row = page(db, me)
    plan_idea(db)
    lone = rendered(db, storage, me)
    queue_item(db, row, lone, me)

    page_queue.fill(db, at=MORNING)

    post = db.scalar(select(Publication).where(Publication.video_id == lone.id))
    assert post.scheduled_at == MORNING.replace(hour=17, minute=0)


def test_a_planned_video_goes_at_its_ideas_time(db, me, storage):
    row = page(db, me)
    planned = rendered(db, storage, me)
    plan_idea(db, planned)
    lone = rendered(db, storage, me)
    queue_item(db, row, lone, me, position=1)
    queue_item(db, row, planned, me, position=2)

    page_queue.fill(db, at=MORNING)
    page_queue.fill(db, at=MORNING)

    times = {post.video_id: post.scheduled_at for post in db.scalars(select(Publication))}
    assert times[planned.id] == MORNING.replace(hour=11, minute=30)
    assert times[lone.id] == MORNING.replace(hour=17, minute=0)


def test_a_plan_idea_lets_go_of_its_time_two_hours_before(db, me, storage):
    row = page(db, me)
    plan_idea(db)
    lone = rendered(db, storage, me)
    queue_item(db, row, lone, me)

    page_queue.fill(db, at=MORNING.replace(hour=9, minute=45))

    post = db.scalar(select(Publication).where(Publication.video_id == lone.id))
    assert post.scheduled_at == MORNING.replace(hour=11, minute=30)


def test_two_posts_at_one_time_need_a_second_yes(an, db, me, storage):
    row = page(db, me)
    first, second = rendered(db, storage, me), rendered(db, storage, me)
    when = (datetime.now(VIETNAM) + timedelta(days=2)).replace(hour=11, minute=30, second=0, microsecond=0)
    body = {"fanpage_id": row.id, "scheduled_at": when.isoformat()}
    assert an.post(f"/api/videos/{first.id}/publish", json=body).status_code == 200

    refused = an.post(
        f"/api/videos/{second.id}/publish", json={**body, "scheduled_at": (when + timedelta(minutes=10)).isoformat()}
    )
    assert (refused.status_code, refused.json()["code"]) == (409, "slot_taken")
    forced = an.post(
        f"/api/videos/{second.id}/publish",
        json={**body, "scheduled_at": (when + timedelta(minutes=10)).isoformat(), "allow_overlap": True},
    )
    assert forced.status_code == 200


def test_the_video_page_shows_where_the_queue_would_put_it(an, db, me, storage):
    row = page(db, me)
    video = rendered(db, storage, me)

    answer = an.get(f"/api/queue/videos/{video.id}").json()

    assert answer["item"] is None
    assert [(entry["fanpage_id"], entry["slot"] is not None) for entry in answer["next"]] == [(row.id, True)]
