"""Render machines (render_nodes.py): the worker packs a render, a member's machine takes it over HTTPS with its token,
renders it and the api finishes the job; the worker's restart and exit checks leave such a job alone."""

from contextlib import contextmanager

import pytest
from conftest import login, make_user, make_video, needs_ffmpeg
from fastapi.testclient import TestClient

from reels_api import jobs, render_nodes, worker
from reels_api.models import Job, Video
from reels_api.sessions import now


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


@pytest.fixture
def factory(db):
    """The worker's session factory, on the test's own transaction."""

    @contextmanager
    def same():
        yield db

    return same


def machine(an, name="Máy nhà An") -> dict:
    made = an.post("/api/render-nodes", json={"name": name})
    assert made.status_code == 201, made.text
    return made.json()


def as_node(app, token: str) -> TestClient:
    # No Origin header, like the real program: the node endpoints authenticate by token alone.
    return TestClient(app, headers={"Authorization": f"Bearer {token}"})


def handed_off(db, factory, storage, user, kind="render") -> Job:
    video = make_video(db, storage, user, scene_count=1, seconds=3)
    video.voice_enabled = False
    job = Job(video_id=video.id, kind=kind, status="running", created_by_id=user.id)
    db.add(job)
    db.commit()
    jobs.run_job(job.id, factory, storage)
    db.refresh(job)
    return job


def test_members_add_a_machine_and_turn_render_machines_on(an, db):
    assert an.get("/api/render-nodes").json() == {"enabled": False, "waiting": 0, "nodes": []}
    made = machine(an)
    assert len(made["token"]) > 30 and made["node"]["online"] is False
    assert an.put("/api/render-nodes/setting", json={"enabled": True}).json()["enabled"] is True
    listed = an.get("/api/render-nodes").json()
    assert [node["name"] for node in listed["nodes"]] == ["Máy nhà An"] and "token" not in listed["nodes"][0]
    assert an.post("/api/render-nodes", json={"name": "  "}).status_code == 422


@needs_ffmpeg
def test_without_render_machines_the_worker_renders_as_before(an, db, me, factory, storage):
    job = handed_off(db, factory, storage, me)
    assert (job.status, job.node_stage) == ("done", None)
    assert db.get(Video, job.video_id).mp4_key


@needs_ffmpeg
def test_a_machine_takes_the_packed_render_and_the_api_finishes_it(app, an, db, me, factory, storage, tmp_path):
    token = machine(an)["token"]
    an.put("/api/render-nodes/setting", json={"enabled": True})
    job = handed_off(db, factory, storage, me)
    assert (job.status, job.node_stage) == ("running", "ready")
    assert storage.exists(render_nodes.bundle_key(job.id))
    assert an.get(f"/api/videos/{job.video_id}").json()["active_job"]["node_stage"] == "ready"
    # The worker restarting, or its child process exiting, never fails a job waiting for a machine.
    worker.recover_interrupted(factory)
    worker._fail_if_running(factory, job.id, "x", "y")
    db.refresh(job)
    assert job.status == "running"

    node = as_node(app, token)
    assert as_node(app, "sai").post("/api/node/claim").status_code == 401
    claimed = node.post("/api/node/claim").json()
    assert claimed == {"job_id": job.id, "kind": "render"}
    assert node.post("/api/node/claim").json() == {"job_id": None}
    bundle = node.get(f"/api/node/jobs/{job.id}/bundle")
    assert bundle.status_code == 200
    from reels_api.node import _unpack

    (tmp_path / "bundle.zip").write_bytes(bundle.content)
    manifest = _unpack(tmp_path / "bundle.zip", tmp_path / "again")
    result = render_nodes.render_bundle(tmp_path / "again", manifest)
    assert node.post(f"/api/node/jobs/{job.id}/heartbeat").status_code == 200
    sent = node.put(f"/api/node/jobs/{job.id}/output", content=(tmp_path / "again" / "output.mp4").read_bytes())
    assert sent.status_code == 200, sent.text
    finished = node.post(f"/api/node/jobs/{job.id}/done", json=result)
    assert finished.json() == {"ok": True}, finished.text
    db.refresh(job)
    video = db.get(Video, job.video_id)
    db.refresh(video)
    assert (job.status, job.node_stage) == ("done", None)
    assert video.mp4_key and storage.exists(video.mp4_key) and video.qc["checks"]
    assert video.rendered_signature == manifest["signature"]
    assert not storage.exists(render_nodes.bundle_key(job.id))


def test_a_waiting_job_can_be_cancelled_and_a_failed_render_says_why(app, an, db, me, factory, storage):
    token = machine(an)["token"]
    an.put("/api/render-nodes/setting", json={"enabled": True})
    waiting = handed_off(db, factory, storage, me)
    cancelled = an.post(f"/api/jobs/{waiting.id}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    db.refresh(waiting)
    assert (waiting.status, waiting.node_stage) == ("cancelled", None)
    assert not storage.exists(render_nodes.bundle_key(waiting.id))

    job = handed_off(db, factory, storage, me)
    node = as_node(app, token)
    node.post("/api/node/claim")
    assert an.post(f"/api/jobs/{job.id}/cancel").status_code == 409  # a machine is rendering it
    failed = node.post(f"/api/node/jobs/{job.id}/fail", json={"error": "FFmpeg lỗi", "detail": "codec"})
    assert failed.status_code == 200
    db.refresh(job)
    assert (job.status, job.error, job.error_detail, job.node_stage) == ("failed", "FFmpeg lỗi", "codec", None)
    assert node.post(f"/api/node/jobs/{job.id}/heartbeat").status_code == 409


def test_a_silent_machine_gives_its_job_back_and_a_deleted_one_loses_its_token(app, an, db, me, factory, storage):
    first, second = machine(an, "Máy 1"), machine(an, "Máy 2")
    an.put("/api/render-nodes/setting", json={"enabled": True})
    job = handed_off(db, factory, storage, me)
    assert as_node(app, first["token"]).post("/api/node/claim").json()["job_id"] == job.id
    # Another machine cannot touch it while the first one is alive.
    assert as_node(app, second["token"]).get(f"/api/node/jobs/{job.id}/bundle").status_code == 409
    job.node_seen_at = now() - render_nodes.STALE - render_nodes.ONLINE
    db.commit()
    assert as_node(app, second["token"]).post("/api/node/claim").json()["job_id"] == job.id
    assert an.delete(f"/api/render-nodes/{second['node']['id']}").status_code == 200
    db.refresh(job)
    assert (job.node_stage, job.node_id) == ("ready", None)
    assert as_node(app, second["token"]).post("/api/node/claim").status_code == 401
