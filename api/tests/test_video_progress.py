"""The video page's progress line: when the script was written (`script_at`), beside the times the payload already
carries (created, rendered, posted)."""

from datetime import UTC, datetime, timedelta

import pytest
from conftest import first_topic, login, make_user, make_video

from reels_api.models import Job, Video


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def test_a_written_script_is_dated_by_its_last_finished_script_job(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    first = datetime(2026, 11, 9, 2, 0, tzinfo=UTC)
    db.add_all(
        [
            Job(video_id=video.id, kind="script", status="done", created_by_id=me.id, finished_at=first),
            # Written again later ("Viết lại"): the newest one dates the script.
            Job(
                video_id=video.id,
                kind="script",
                status="done",
                created_by_id=me.id,
                finished_at=first + timedelta(hours=3),
            ),
            # A failed rewrite and other jobs do not move it.
            Job(
                video_id=video.id,
                kind="script",
                status="failed",
                created_by_id=me.id,
                finished_at=first + timedelta(hours=5),
            ),
            Job(
                video_id=video.id,
                kind="render",
                status="done",
                created_by_id=me.id,
                finished_at=first + timedelta(hours=6),
            ),
        ]
    )
    db.commit()
    assert an.get(f"/api/videos/{video.id}").json()["script_at"] == (first + timedelta(hours=3)).isoformat()


def test_a_script_with_no_job_is_dated_by_the_video(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)  # hand-written or sent by an assistant over MCP
    payload = an.get(f"/api/videos/{video.id}").json()
    assert payload["script_at"] == payload["created_at"]


def test_a_video_still_without_a_script_has_no_script_time(an, db, me):
    video = Video(topic="rau dền", knowledge_topic_id=first_topic(db).id, has_script=False, created_by_id=me.id)
    db.add(video)
    db.commit()
    assert an.get(f"/api/videos/{video.id}").json()["script_at"] is None
