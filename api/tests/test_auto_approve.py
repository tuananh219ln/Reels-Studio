"""Tự duyệt: a member who turned it on has the video they made scheduled the moment its render is done, when it could
be approved by hand without a doubt; any other video waits, with the reason kept for Muse to pass on."""

from datetime import timedelta

import pytest
from conftest import first_topic, login, make_user, make_video
from fake_services import FACEBOOK_PAGE, FACEBOOK_TOKEN
from sqlalchemy import select
from test_publish import add_mp4

from reels_api import auto_approve, fanpages
from reels_api.models import AutoApproval, Job, Publication, TopicPlanItem, User
from reels_api.plans import VIETNAM
from reels_api.sessions import now
from reels_api.videos import split_scenes


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def plan(db, video, days_ahead=2, hour=9):
    """The video's idea sits on a plan day ahead, so the plan names a time for it."""
    topic = first_topic(db)
    topic.plan_start_date = (now().astimezone(VIETNAM) + timedelta(days=days_ahead)).date()
    topic.plan_post_times = [f"{hour:02d}:00"]
    db.add(
        TopicPlanItem(
            knowledge_topic_id=topic.id,
            day=1,
            position=1,
            topic="Ngâm chân",
            video_id=video.id,
            created_by_id=video.created_by_id,
        )
    )
    db.commit()


def own_page(db, user, same_group=True):
    page = fanpages.save(db, FACEBOOK_PAGE, "Trang Dưỡng Sinh", FACEBOOK_TOKEN, user.id)
    page.owner_id = user.id
    page.knowledge_topic_id = first_topic(db).id if same_group else None
    db.commit()
    return page


def ready(db, storage, user, **kwargs):
    """A rendered video with a plan time and a Page of its maker, the maker having turned the switch on."""
    video = make_video(db, storage, user)
    add_mp4(db, storage, video)
    plan(db, video, **kwargs)
    user.auto_approve = True
    db.commit()
    return video


def outcome(db, video):
    return db.scalars(select(AutoApproval).where(AutoApproval.video_id == video.id)).all()


def test_a_finished_render_is_approved_at_the_planned_time(db, me, storage):
    page = own_page(db, me)
    video = ready(db, storage, me)
    auto_approve.settle(db, video.id)
    post = db.scalar(select(Publication).where(Publication.video_id == video.id))
    assert (post.status, post.fanpage_id, post.auto_comment, post.created_by_id) == ("pending", page.id, True, me.id)
    assert post.scheduled_at is not None and post.scheduled_at > now() + timedelta(days=1)
    assert db.scalar(select(Job).where(Job.video_id == video.id, Job.kind == "publish")) is not None
    (record,) = outcome(db, video)
    assert (record.outcome, record.user_id, record.fanpage_name) == ("approved", me.id, "Trang Dưỡng Sinh")


def test_nothing_happens_while_the_switch_is_off(db, me, storage):
    own_page(db, me)
    video = ready(db, storage, me)
    me.auto_approve = False
    db.commit()
    auto_approve.settle(db, video.id)
    assert db.scalar(select(Publication)) is None
    assert outcome(db, video) == []


@pytest.mark.parametrize(
    ("setup", "reason"),
    [
        ("no_time", "giờ đăng dự kiến"),
        ("past_time", "giờ đăng dự kiến"),
        ("no_page", "Page"),
        ("warning", "cảnh báo"),
        ("qc", "Kiểm tra MP4"),
    ],
)
def test_a_video_that_could_not_be_approved_by_hand_waits_with_its_reason(db, me, storage, setup, reason):
    own_page(db, me, same_group=setup != "no_page")
    if setup == "no_page":
        for page in fanpages_of(db):
            page.owner_id = None
        db.commit()
    video = make_video(db, storage, me)
    add_mp4(db, storage, video)
    if setup != "no_time":
        plan(db, video, days_ahead=-3 if setup == "past_time" else 2)
    if setup == "warning":
        for scene in split_scenes(db, video)[1][1:]:
            db.delete(scene)  # a video of one content scene is outside the channel's formula: a warning
    if setup == "qc":
        video.qc = {"status": "warn", "checks": []}
    me.auto_approve = True
    db.commit()
    auto_approve.settle(db, video.id)
    assert db.scalar(select(Publication)) is None
    (record,) = outcome(db, video)
    assert record.outcome == "held" and reason in record.reason


def fanpages_of(db):
    from reels_api.models import Fanpage

    return db.scalars(select(Fanpage)).all()


def test_a_video_already_on_that_page_is_left_alone(db, me, storage):
    own_page(db, me)
    video = ready(db, storage, me)
    auto_approve.settle(db, video.id)
    auto_approve.settle(db, video.id)
    assert len(db.scalars(select(Publication).where(Publication.video_id == video.id)).all()) == 1
    assert len(outcome(db, video)) == 1


def test_only_the_makers_switch_counts(db, me, storage):
    other = make_user(db, email="binh@doi.vn", name="Trần Bình")
    own_page(db, other)
    video = ready(db, storage, me)
    other.auto_approve = True
    me.auto_approve = False
    db.commit()
    auto_approve.settle(db, video.id)
    assert db.scalar(select(Publication)) is None


def test_the_switch_is_read_and_set_by_its_member(an, db, me):
    assert an.get("/api/me/auto-approve").json() == {"enabled": False}
    assert an.put("/api/me/auto-approve", json={"enabled": True}).json() == {"enabled": True}
    assert db.get(User, me.id).auto_approve is True
    assert an.get("/api/me/auto-approve").json() == {"enabled": True}


def test_the_results_are_listed_for_muse_after_a_cursor(db, me, storage):
    own_page(db, me)
    video = ready(db, storage, me)
    auto_approve.settle(db, video.id)
    first = auto_approve.recent(db, me.id, after_id=0, limit=10)
    assert [row["outcome"] for row in first] == ["approved"]
    assert first[0]["video_id"] == video.id and first[0]["topic"] == video.topic
    assert auto_approve.recent(db, me.id, after_id=first[-1]["id"], limit=10) == []
    stranger = make_user(db, email="binh@doi.vn", name="Trần Bình")
    assert auto_approve.recent(db, stranger.id, after_id=0, limit=10) == []
