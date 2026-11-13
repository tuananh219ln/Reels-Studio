"""Batch rework is owner-scoped, unpublished-only and resumes without rewriting a saved script."""

import json

import pytest
from conftest import login, make_user, make_video
from sqlalchemy import select
from worker_helpers import add_user, committed, job_row  # noqa: F401  (fixture)

from reels_api import jobs
from reels_api.models import Job, Publication, Scene, Video


@pytest.mark.parametrize("status", ["pending", "scheduled", "published", "deleted"])
def test_batch_refuses_published_or_scheduled_videos_atomically(client, db, storage, status):
    user = make_user(db)
    login(client)
    first = make_video(db, storage, user)
    second = make_video(db, storage, user)
    db.add(Publication(video_id=second.id, platform="facebook", status=status, created_by_id=user.id))
    db.commit()
    response = client.post("/api/rework/videos", json={"ids": [first.id, second.id]})
    assert response.status_code == 409
    assert not db.scalars(select(Job).where(Job.kind == "rework")).all()


def test_only_the_maker_can_queue_rework(client, db, storage):
    user = make_user(db)
    teammate = make_user(db, email="other@doi.vn")
    login(client)
    video = make_video(db, storage, teammate)
    response = client.post("/api/rework/videos", json={"ids": [video.id]})
    assert response.status_code == 403
    assert not db.scalars(select(Job).where(Job.kind == "rework")).all()
    assert user.id != teammate.id


def test_batch_queues_work_without_modifying_the_script_in_the_handler(client, db, storage):
    user = make_user(db)
    login(client)
    video = make_video(db, storage, user)
    before = [
        (scene.id, scene.text, scene.image_key) for scene in db.scalars(select(Scene).where(Scene.video_id == video.id))
    ]
    response = client.post(
        "/api/rework/videos", json={"ids": [video.id], "replace_manual": False, "render_after": True}
    )
    assert response.status_code == 202, response.text
    assert response.json()["queued"] == 1
    job = db.scalar(select(Job).where(Job.kind == "rework"))
    assert job.status == "queued" and job.created_by_id == user.id
    assert [
        (scene.id, scene.text, scene.image_key) for scene in db.scalars(select(Scene).where(Scene.video_id == video.id))
    ] == before
    duplicate = client.post("/api/rework/videos", json={"ids": [video.id]})
    assert duplicate.status_code == 409


def plan_for(scenes):
    return {
        "scenes": [
            {
                "id": scene.id,
                "text": scene.text,
                "voice": "Món quen, đổi vị cho bữa cơm.",
                "keywords": ["bày món ăn", "món ăn"],
                "keywords_en": ["serving food", "food"],
            }
            for scene in scenes
        ]
    }


def setup_job(factory, storage, user):
    with factory() as db:
        video = make_video(db, storage, user, scene_count=1)
        scenes = db.scalars(select(Scene).where(Scene.video_id == video.id).order_by(Scene.position)).all()
        keys = [scene.image_key for scene in scenes]
        plan = plan_for(scenes)
        job = Job(
            video_id=video.id,
            kind="rework",
            status="running",
            created_by_id=user.id,
            edit_prompt=json.dumps({"replace_manual": False, "render_after": True}),
        )
        db.add(job)
        db.commit()
        return video.id, job.id, plan, keys


def test_worker_preserves_manual_media_and_queues_render(committed, storage, fakes):
    user = add_user(committed)
    video_id, job_id, plan, keys = setup_job(committed, storage, user)
    fakes.claude_replies = [plan]
    jobs.run_job(job_id, committed, storage)
    finished = job_row(committed, job_id)
    assert (finished.status, finished.error) == ("done", None)
    assert finished.claude_calls == 1
    with committed() as db:
        scenes = db.scalars(select(Scene).where(Scene.video_id == video_id).order_by(Scene.position)).all()
        assert [scene.image_key for scene in scenes] == keys
        assert all(scene.voice_key and scene.keywords[0] == "bày món ăn" for scene in scenes)
        render = db.scalar(select(Job).where(Job.video_id == video_id, Job.kind == "render"))
        assert render.status == "queued"
        assert not db.scalars(select(Publication).where(Publication.video_id == video_id)).all()


def test_retry_resumes_after_tts_failure_without_repeating_script_call(committed, storage, fakes):
    user = add_user(committed)
    video_id, job_id, plan, _ = setup_job(committed, storage, user)
    fakes.claude_replies = [plan]
    fakes.tts_mode = "quota"
    jobs.run_job(job_id, committed, storage)
    failed = job_row(committed, job_id)
    assert failed.status == "failed"
    assert json.loads(failed.edit_prompt)["stage"] == "voice"
    fakes.tts_mode = "ok"
    with committed() as db:
        retry = Job(
            video_id=video_id,
            kind="rework",
            status="running",
            created_by_id=user.id,
            retry_of_id=job_id,
            edit_prompt=failed.edit_prompt,
        )
        db.add(retry)
        db.commit()
        retry_id = retry.id
    jobs.run_job(retry_id, committed, storage)
    assert job_row(committed, retry_id).status == "done"
    assert job_row(committed, retry_id).claude_calls == 0
    assert len(fakes.claude_prompts) == 1


def test_retry_refuses_when_the_video_was_edited_after_a_failed_run(committed, storage, fakes):
    user = add_user(committed)
    video_id, job_id, plan, _ = setup_job(committed, storage, user)
    fakes.claude_replies = [plan]
    fakes.tts_mode = "quota"
    jobs.run_job(job_id, committed, storage)
    failed = job_row(committed, job_id)
    assert failed.status == "failed"
    fakes.tts_mode = "ok"
    edited = "Thành viên tự sửa lời đọc sau lần lỗi."
    with committed() as db:
        scene = db.scalars(select(Scene).where(Scene.video_id == video_id).order_by(Scene.position)).first()
        scene.voice_text = edited
        retry = Job(
            video_id=video_id,
            kind="rework",
            status="running",
            created_by_id=user.id,
            retry_of_id=job_id,
            edit_prompt=failed.edit_prompt,
        )
        db.add(retry)
        db.commit()
        retry_id = retry.id
    jobs.run_job(retry_id, committed, storage)
    retried = job_row(committed, retry_id)
    assert retried.status == "failed"
    assert "đã được sửa" in retried.error
    assert len(fakes.claude_prompts) == 1
    with committed() as db:
        scene = db.scalars(select(Scene).where(Scene.video_id == video_id).order_by(Scene.position)).first()
        assert scene.voice_text == edited
        assert not db.scalars(select(Job).where(Job.video_id == video_id, Job.kind == "render")).all()


def test_invalid_scene_plan_never_partially_changes_video(committed, storage, fakes):
    user = add_user(committed)
    video_id, job_id, plan, _ = setup_job(committed, storage, user)
    plan["scenes"][0]["voice"] = "Changed before the invalid second scene"
    plan["scenes"][1]["id"] = 999999
    fakes.claude_replies = [plan]
    jobs.run_job(job_id, committed, storage)
    assert job_row(committed, job_id).status == "failed"
    with committed() as db:
        assert all(scene.voice_text == "" for scene in db.scalars(select(Scene).where(Scene.video_id == video_id)))
        assert db.get(Video, video_id).caption == "caption"
