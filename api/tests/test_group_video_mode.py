""" "Kiểu video" of a topic group (brief docs/specs/mcp-video-mode): slides, "Video xuyên suốt" or by turns ("Xen kẽ
theo ngày": odd days of the Vietnam calendar a backdrop video, even days slides). A mode asked for the one video wins
over the group's; every way of making a video goes through start_video, where it is resolved."""

from datetime import date

import pytest
from conftest import client_for, first_topic, login, make_user
from sqlalchemy import select
from test_mcp import call, grant, mcp_client, payload  # noqa: F401  (fixture)

from reels_api import plans
from reels_api.claude import BACKDROP_FORMAT, OUTPUT_FORMAT
from reels_api.models import KnowledgeTopic, Video
from reels_api.videos import group_video_mode, resolve_video_mode

EVEN = date(2026, 11, 10)
ODD = date(2026, 11, 11)


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def set_group_mode(db, mode: str) -> KnowledgeTopic:
    group = first_topic(db)
    group.video_mode = mode
    db.commit()
    return group


def new_video(an, group_id: int, **extra) -> dict:
    made = an.post("/api/videos", json={"topic": "chuối xanh", "knowledge_topic_id": group_id, **extra})
    assert made.status_code == 201, made.json()
    return made.json()


# --- The one place it is resolved ---


@pytest.mark.parametrize(
    ("group_mode", "day", "expected"),
    [
        ("slides", ODD, "slides"),
        ("single", EVEN, "single"),
        ("alternate", ODD, "single"),
        ("alternate", EVEN, "slides"),
        ("alternate", date(2026, 12, 31), "single"),
        ("alternate", date(2027, 1, 1), "single"),  # the calendar's day, not a count of days
        ("alternate", date(2027, 1, 2), "slides"),
    ],
)
def test_the_groups_switch_resolves_by_the_vietnam_calendar_day(group_mode, day, expected):
    group = KnowledgeTopic(name="Nhóm", video_mode=group_mode)
    assert group_video_mode(group, day) == expected
    assert resolve_video_mode(None, group, day) == expected


@pytest.mark.parametrize("chosen", ["slides", "single"])
@pytest.mark.parametrize("group_mode", ["slides", "single", "alternate"])
def test_a_mode_asked_for_the_video_wins_over_the_group(chosen, group_mode):
    group = KnowledgeTopic(name="Nhóm", video_mode=group_mode)
    assert resolve_video_mode(chosen, group, ODD) == chosen
    assert resolve_video_mode(chosen, group, EVEN) == chosen


def test_today_is_the_vietnam_day(monkeypatch):
    group = KnowledgeTopic(name="Nhóm", video_mode="alternate")
    monkeypatch.setattr(plans, "today", lambda: ODD)
    assert group_video_mode(group) == "single"
    monkeypatch.setattr(plans, "today", lambda: EVEN)
    assert group_video_mode(group) == "slides"


# --- Making a video on the web (and the team's AI, which posts the same body) ---


def test_a_group_never_set_makes_slide_videos(an, db):
    group = first_topic(db)
    assert group.video_mode == "slides"
    assert new_video(an, group.id)["mode"] == "slides"


def test_a_new_video_follows_its_groups_switch_unless_one_is_asked(an, db, monkeypatch):
    group = set_group_mode(db, "single")
    assert new_video(an, group.id)["mode"] == "single"
    assert new_video(an, group.id, video_mode="slides")["mode"] == "slides"
    assert new_video(an, group.id, video_mode=None)["mode"] == "single"

    set_group_mode(db, "alternate")
    monkeypatch.setattr(plans, "today", lambda: ODD)
    assert new_video(an, group.id)["mode"] == "single"
    monkeypatch.setattr(plans, "today", lambda: EVEN)
    assert new_video(an, group.id)["mode"] == "slides"
    assert new_video(an, group.id, video_mode="single")["mode"] == "single"


def test_a_hand_written_video_follows_the_group_too(an, db):
    group = set_group_mode(db, "single")
    assert new_video(an, group.id, mode="manual", script="Cảnh một\nĐọc: một")["mode"] == "single"


# --- The group's setting ---


def test_the_group_shows_and_saves_its_switch_with_the_mode_of_today(an, db, monkeypatch):
    group = first_topic(db)
    monkeypatch.setattr(plans, "today", lambda: ODD)
    [shown] = [topic for topic in an.get("/api/knowledge").json()["topics"] if topic["id"] == group.id]
    assert (shown["video_mode"], shown["video_mode_today"]) == ("slides", "slides")

    saved = an.patch(f"/api/knowledge/topics/{group.id}", json={"video_mode": "alternate"})
    assert saved.status_code == 200, saved.json()
    [shown] = [topic for topic in saved.json()["topics"] if topic["id"] == group.id]
    assert (shown["video_mode"], shown["video_mode_today"]) == ("alternate", "single")

    wrong = an.patch(f"/api/knowledge/topics/{group.id}", json={"video_mode": "film"})
    assert wrong.status_code == 422
    db.expire_all()
    assert db.get(KnowledgeTopic, group.id).video_mode == "alternate"


def test_the_switch_is_in_the_groups_history_and_follows_its_edit_lock(an, app, db, me):
    group = first_topic(db)
    group.created_by_id, group.team_edit = me.id, False
    db.commit()
    assert an.patch(f"/api/knowledge/topics/{group.id}", json={"video_mode": "single"}).status_code == 200
    history = an.get(f"/api/edit-logs?entity_type=knowledge_topic&entity_id={group.id}").json()
    assert any(entry["changes"].get("video_mode") == {"old": "slides", "new": "single"} for entry in history["entries"])

    make_user(db, email="binh@doi.vn", name="Bình")
    binh = client_for(app)
    login(binh, email="binh@doi.vn")
    locked = binh.patch(f"/api/knowledge/topics/{group.id}", json={"video_mode": "slides"})
    assert locked.status_code == 403


# --- MCP ---


def test_a_script_typed_through_mcp_takes_the_mode_asked_or_the_groups(mcp_client, db):
    _, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    group = first_topic(db)

    asked = call(
        mcp_client,
        token,
        "create_video_from_script",
        topic="Một",
        knowledge_topic_id=group.id,
        script="Cảnh",
        video_mode="single",
    )
    assert not asked.get("isError"), asked
    assert db.scalar(select(Video).where(Video.topic == "Một")).mode == "single"

    set_group_mode(db, "single")
    unasked = call(mcp_client, token, "create_video_from_script", topic="Hai", knowledge_topic_id=group.id, script="C")
    assert not unasked.get("isError"), unasked
    assert db.scalar(select(Video).where(Video.topic == "Hai")).mode == "single"


def test_the_group_prompt_through_mcp_is_for_the_groups_resolved_mode(mcp_client, db, monkeypatch):
    _, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    group = set_group_mode(db, "alternate")

    monkeypatch.setattr(plans, "today", lambda: ODD)
    odd = payload(call(mcp_client, token, "get_script_prompt", topic="Rau", knowledge_topic_id=group.id))
    assert odd["video_mode"] == "single" and odd["prompt"].endswith(BACKDROP_FORMAT)

    monkeypatch.setattr(plans, "today", lambda: EVEN)
    even = payload(call(mcp_client, token, "get_script_prompt", topic="Rau", knowledge_topic_id=group.id))
    assert even["video_mode"] == "slides" and even["prompt"].endswith(OUTPUT_FORMAT)

    asked = payload(
        call(mcp_client, token, "get_script_prompt", topic="Rau", knowledge_topic_id=group.id, video_mode="single")
    )
    assert asked["video_mode"] == "single" and asked["prompt"].endswith(BACKDROP_FORMAT)


def test_a_script_from_the_group_prompt_through_mcp_follows_the_group(mcp_client, db):
    import json

    from test_mcp import GROUP_SCRIPT

    _, _, tokens, _ = grant(mcp_client, db)
    group = set_group_mode(db, "single")
    made = call(
        mcp_client,
        tokens["access_token"],
        "create_video_from_group_prompt",
        topic="Rau xanh cho tim",
        knowledge_topic_id=group.id,
        script_json=json.dumps(GROUP_SCRIPT, ensure_ascii=False),
    )
    assert not made.get("isError"), made
    assert db.scalar(select(Video).where(Video.topic == "Rau xanh cho tim")).mode == "single"
