"""A video made from a finished MP4 ("MP4 tải lên"): the file is the video's MP4 as it is, it is never rendered, and it
goes through the same review gate (docs/decisions/2026-11-26-upload-mp4.md)."""

import base64
import hashlib
import subprocess

import pytest
from conftest import first_topic, login, make_user
from sqlalchemy import select
from test_mcp import call, grant, mcp_client, payload  # noqa: F401  (mcp_client is a fixture)

from reels_api.models import Job, Publication, TopicPlanItem, Video


def make_mp4(folder, name="clip.mp4", size="1080x1920", seconds=16, audio=True, codec="libx264") -> bytes:
    """A tiny real MP4 made by FFmpeg, as a member's finished video would be."""
    path = folder / name
    command = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size={size}:rate=10:duration={seconds}"]
    if audio:
        command += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    command += ["-c:v", codec, "-pix_fmt", "yuv420p", "-preset", "ultrafast", "-crf", "40"]
    if audio:
        command += ["-c:a", "aac", "-shortest"]
    subprocess.run([*command, str(path)], check=True)
    return path.read_bytes()


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


@pytest.fixture
def idea(db, me) -> TopicPlanItem:
    group = first_topic(db)
    item = TopicPlanItem(
        knowledge_topic_id=group.id, day=1, position=1, topic="7 thói quen buổi sáng", created_by_id=me.id
    )
    db.add(item)
    db.commit()
    return item


def send(an, db, data, **fields):
    form = {"knowledge_topic_id": str(first_topic(db).id), **{key: str(value) for key, value in fields.items()}}
    return an.post("/api/videos/upload", data=form, files={"file": ("day01.mp4", data, "video/mp4")})


def test_an_upload_becomes_the_videos_mp4_untouched_and_waits_for_review(an, db, tmp_path, storage, idea):
    data = make_mp4(tmp_path)
    answer = send(an, db, data, plan_item_id=idea.id, caption="Hello", hashtags="#a #b", upload_note="Muse v2")
    assert answer.status_code == 201, answer.text
    video = answer.json()
    assert video["mode"] == "upload" and video["status"] == "done" and video["scenes"] == []
    assert video["media_info"]["width"] == 1080 and video["media_info"]["has_audio"] is True
    assert video["hashtags"] == ["#a", "#b"] and video["upload"]["note"] == "Muse v2"
    assert video["mp4_outdated"] is False and video["active_job"] is None
    assert video["review"]["status"] == "pending_review" and video["warnings"] == []
    row = db.get(Video, video["id"])
    assert hashlib.sha256(storage.path(row.mp4_key).read_bytes()).hexdigest() == hashlib.sha256(data).hexdigest()
    assert row.source_mp4["sha256"] == hashlib.sha256(data).hexdigest()
    assert storage.exists(row.thumbnail_key)
    db.refresh(idea)
    assert idea.video_id == row.id
    served = an.get(f"/api/videos/{row.id}/video.mp4")
    assert served.content == data


def test_a_taken_idea_is_refused_unless_replaced(an, db, tmp_path, idea):
    data = make_mp4(tmp_path)
    first = send(an, db, data, plan_item_id=idea.id).json()
    again = send(an, db, data, plan_item_id=idea.id)
    assert (again.status_code, again.json()["code"]) == (409, "plan_item_taken")
    assert send(an, db, data, plan_item_id=999999).json()["code"] == "plan_item_not_found"
    swapped = send(an, db, data, plan_item_id=idea.id, replace_existing="true")
    assert swapped.status_code == 201
    db.refresh(idea)
    assert idea.video_id == swapped.json()["id"] != first["id"]


def test_the_same_idempotency_key_returns_the_video_made_before(an, db, tmp_path):
    data = make_mp4(tmp_path)
    first = send(an, db, data, idempotency_key="ehg-day01-s1-v1").json()
    second = send(an, db, data, idempotency_key="ehg-day01-s1-v1").json()
    assert second["id"] == first["id"]
    assert len(list(db.scalars(select(Video).where(Video.mode == "upload")))) == 1


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"seconds": 2}, "từ 3 đến 90"),
        ({"size": "320x568"}, "quá nhỏ"),
    ],
)
def test_a_file_that_breaks_a_hard_rule_is_refused_with_its_reason(an, db, tmp_path, kwargs, reason):
    answer = send(an, db, make_mp4(tmp_path, **kwargs))
    assert (answer.status_code, answer.json()["code"]) == (400, "invalid_media")
    assert reason in answer.json()["message"]
    assert db.scalar(select(Video.id).where(Video.mode == "upload")) is None


def test_a_file_that_is_not_an_mp4_is_refused(an, db):
    answer = send(an, db, b"this is not a video at all, just text" * 10)
    assert (answer.status_code, answer.json()["code"]) == (400, "invalid_media")


def test_a_wide_video_without_sound_is_accepted_with_warnings(an, db, tmp_path):
    answer = send(an, db, make_mp4(tmp_path, size="1280x720", audio=False))
    assert answer.status_code == 201
    text = " ".join(answer.json()["warnings"])
    assert "9:16" in text and "không có âm thanh" in text


def test_an_upload_is_never_rendered_or_copied(an, db, tmp_path):
    video = send(an, db, make_mp4(tmp_path)).json()
    render = an.post(f"/api/videos/{video['id']}/render")
    assert (render.status_code, render.json()["code"]) == (409, "upload_video")
    copy = an.post(f"/api/videos/{video['id']}/duplicate")
    assert copy.status_code == 409 and copy.json()["code"] == "upload_video"


def test_approving_lets_it_be_posted(an, db, me, tmp_path):
    from test_publish import fanpage_id, in_minutes

    video = send(an, db, make_mp4(tmp_path), title="7 thói quen").json()
    page = fanpage_id(db, me)
    refused = an.post(f"/api/videos/{video['id']}/publish", json={"fanpage_id": page})
    assert refused.json()["code"] == "not_approved"
    assert an.post(f"/api/review/{video['id']}/approve", json={"acknowledge_qc": True}).status_code == 200
    scheduled = an.post(f"/api/videos/{video['id']}/publish", json={"fanpage_id": page, "scheduled_at": in_minutes(60)})
    assert scheduled.status_code == 200, scheduled.text
    # Posting is queued for the worker; no render is ever queued for an upload.
    assert [job.kind for job in db.scalars(select(Job).where(Job.video_id == video["id"]))] == ["publish"]


def test_a_new_file_sends_the_video_back_to_review_and_withdraws_its_plan(an, db, me, tmp_path):
    video = send(an, db, make_mp4(tmp_path), caption="giữ lại").json()
    assert an.post(f"/api/review/{video['id']}/approve", json={"acknowledge_qc": True}).status_code == 200
    waiting = Publication(video_id=video["id"], platform="instagram", status="scheduled", created_by_id=me.id)
    db.add(waiting)
    db.commit()
    replaced = an.put(
        f"/api/videos/{video['id']}/source-mp4",
        files={"file": ("v2.mp4", make_mp4(tmp_path, "v2.mp4", seconds=17), "video/mp4")},
        data={"upload_note": "v2"},
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["review"]["status"] == "pending_review"
    assert replaced.json()["upload"]["note"] == "v2" and replaced.json()["caption"] == "giữ lại"
    assert replaced.json()["upload"]["sha256"] != video["upload"]["sha256"]
    db.expire_all()
    assert waiting.status == "cancelled"


def test_the_idea_follows_the_video_and_is_freed_when_it_is_deleted(an, db, tmp_path, idea):
    video = send(an, db, make_mp4(tmp_path), plan_item_id=idea.id).json()
    assert an.delete(f"/api/videos/{video['id']}").status_code == 200
    db.refresh(idea)
    assert idea.video_id is None


def test_muse_uploads_through_mcp_and_errors_come_back_with_a_code(mcp_client, db, tmp_path):
    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    group = first_topic(db)
    idea = TopicPlanItem(knowledge_topic_id=group.id, day=1, position=1, topic="Ngày 1", created_by_id=user.id)
    db.add(idea)
    db.commit()
    data = base64.b64encode(make_mp4(tmp_path, size="540x960", seconds=4)).decode()
    made = payload(
        call(
            mcp_client,
            token,
            "upload_finished_video",
            topic_id=group.id,
            plan_item_id=idea.id,
            mp4_base64=data,
            title="7 Morning Habits",
            caption="Which surprised you?",
            schedule="suggested",
            idempotency_key="ehg-day01",
        )
    )
    assert made["mode"] == "upload" and made["status"] == "pending_review" and made["plan_day"] == 1
    assert made["media_info"]["duration_s"] > 3 and any("duyệt" in w for w in made["warnings"])
    video = db.get(Video, made["video_id"])
    assert video.written_via == "assistant" and video.assistant_app
    same = payload(
        call(
            mcp_client, token, "upload_finished_video", topic_id=group.id, mp4_base64=data, idempotency_key="ehg-day01"
        )
    )
    assert same["video_id"] == made["video_id"]
    taken = payload(
        call(mcp_client, token, "upload_finished_video", topic_id=group.id, plan_item_id=idea.id, mp4_base64=data)
    )
    assert taken["error"] == "plan_item_taken"
    bad = payload(
        call(
            mcp_client,
            token,
            "upload_finished_video",
            topic_id=group.id,
            mp4_base64=base64.b64encode(b"x" * 64).decode(),
        )
    )
    assert bad["error"] == "invalid_media" and bad["message"]
    replaced = payload(
        call(
            mcp_client,
            token,
            "replace_finished_video",
            video_id=made["video_id"],
            mp4_base64=base64.b64encode(make_mp4(tmp_path, "b.mp4", size="540x960", seconds=5)).decode(),
        )
    )
    assert replaced["video_id"] == made["video_id"] and replaced["media_info"]["duration_s"] > 4
