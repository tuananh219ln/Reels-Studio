"""Render machines (render_nodes.py): members manage them on Cài đặt › Máy render, and a machine works the queue.

Member endpoints use the login cookie like every page. A machine's endpoints (/api/node/...) take its token as a
bearer instead, never a cookie, and only touch the job that machine took; main.py lets them through the Origin check
because no browser sends them.
"""

import math
import tempfile
import unicodedata
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from . import motion, render_nodes
from .db import get_db
from .errors import ApiError
from .models import AppSetting, Job, RenderNode, Session, Video
from .security import hash_session_token, new_session_token
from .sessions import current_member, now
from .storage import DirectoryStorage, get_storage

router = APIRouter()

MAX_OUTPUT_BYTES = 95 * 1024 * 1024  # under Cloudflare's 100 MB request limit in front of the api
MAX_DETAIL = 4000


class NodeBody(BaseModel):
    name: str


class SettingBody(BaseModel):
    enabled: bool


class DoneBody(BaseModel):
    seconds: float
    elapsed: float
    qc: dict | None = None


class FailBody(BaseModel):
    error: str
    detail: str = ""


def node_payload(node: RenderNode) -> dict:
    seen = node.last_seen_at
    return {
        "id": node.id,
        "name": node.name,
        "created_by": node.created_by.name,
        "created_at": node.created_at.isoformat(),
        "last_seen_at": seen.isoformat() if seen else None,
        "online": bool(seen and now() - seen < render_nodes.ONLINE),
    }


def overview(db: DbSession) -> dict:
    waiting = db.scalar(select(func.count()).where(Job.status == "running", Job.node_stage.is_not(None)))
    nodes = db.scalars(select(RenderNode).order_by(RenderNode.id)).all()
    return {"enabled": render_nodes.enabled(db), "waiting": waiting, "nodes": [node_payload(n) for n in nodes]}


@router.get("/api/render-nodes")
def list_nodes(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    return overview(db)


@router.post("/api/render-nodes", status_code=201)
def add_node(body: NodeBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """A new machine and its token, shown only in this answer (stored hashed, like session tokens)."""
    name = " ".join(unicodedata.normalize("NFC", body.name).split())
    if not 1 <= len(name) <= 60:
        raise ApiError(422, "invalid_value", "Tên máy từ 1 đến 60 ký tự")
    token = new_session_token()
    node = RenderNode(name=name, token_hash=hash_session_token(token), created_by_id=me.user_id)
    db.add(node)
    db.commit()
    return {"node": node_payload(node), "token": token}


@router.delete("/api/render-nodes/{node_id}")
def delete_node(node_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    node = db.get(RenderNode, node_id)
    if node is None:
        raise ApiError(404, "node_not_found", "Không tìm thấy máy render")
    # Its job, if any, goes back to the queue for another machine.
    for job in db.scalars(select(Job).where(Job.node_id == node.id, Job.node_stage == "taken")):
        job.node_stage, job.node_id, job.node_seen_at = "ready", None, None
    db.delete(node)
    db.commit()
    return overview(db)


@router.put("/api/render-nodes/setting")
def set_enabled(body: SettingBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """On: renders and motion scenes wait for a render machine. Off: the VPS worker renders them again; jobs already
    waiting stay for a machine (cancel and render again to have the VPS do one)."""
    row = db.get(AppSetting, render_nodes.SETTING)
    if row is None:
        row = AppSetting(key=render_nodes.SETTING)
        db.add(row)
    row.value, row.updated_by_id = body.enabled, me.user_id
    db.commit()
    return overview(db)


# --- What a render machine calls, with its token ---


def current_node(request: Request, db: DbSession = Depends(get_db)) -> RenderNode:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    node = None
    if scheme.lower() == "bearer" and token:
        node = db.scalar(select(RenderNode).where(RenderNode.token_hash == hash_session_token(token.strip())))
    if node is None:
        raise ApiError(401, "node_unauthorized", "Token máy render không đúng hoặc máy đã bị xoá")
    node.last_seen_at = now()
    return node


def _taken(db: DbSession, node: RenderNode, job_id: int) -> Job:
    job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
    if job is None or job.status != "running" or job.node_stage != "taken" or job.node_id != node.id:
        raise ApiError(409, "job_not_yours", "Job này không còn giao cho máy này (đã huỷ, xong hoặc giao lại)")
    job.node_seen_at = now()
    return job


@router.post("/api/node/claim")
def claim(node: RenderNode = Depends(current_node), db: DbSession = Depends(get_db)) -> dict:
    job = render_nodes.claim(db, node.id)
    return {"job_id": job.id, "kind": job.kind} if job else {"job_id": None}


@router.get("/api/node/jobs/{job_id}/bundle")
def bundle(
    job_id: int,
    node: RenderNode = Depends(current_node),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> FileResponse:
    _taken(db, node, job_id)
    db.commit()
    return FileResponse(storage.path(render_nodes.bundle_key(job_id)), media_type="application/zip")


@router.post("/api/node/jobs/{job_id}/heartbeat")
def heartbeat(job_id: int, node: RenderNode = Depends(current_node), db: DbSession = Depends(get_db)) -> dict:
    _taken(db, node, job_id)
    db.commit()
    return {"ok": True}


@router.put("/api/node/jobs/{job_id}/output")
async def output(
    job_id: int,
    request: Request,
    node: RenderNode = Depends(current_node),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """The rendered MP4 as the raw request body, kept until `done` saves it."""
    _taken(db, node, job_id)
    db.commit()
    with tempfile.TemporaryDirectory(prefix="reels_node_") as raw:
        target = Path(raw) / "output.mp4"
        size = 0
        with open(target, "wb") as file:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_OUTPUT_BYTES:
                    raise ApiError(413, "file_too_large", "MP4 quá 95 MB")
                file.write(chunk)
        storage.save_file(render_nodes.output_key(job_id), target)
    return {"ok": True, "bytes": size}


def _finish(db: DbSession, job: Job, status: str, error: str | None = None, detail: str | None = None) -> None:
    job.status, job.finished_at, job.error, job.error_detail = status, now(), error, detail or None
    job.node_stage = None
    db.commit()


@router.post("/api/node/jobs/{job_id}/done")
def done(
    job_id: int,
    body: DoneBody,
    node: RenderNode = Depends(current_node),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    from .jobs import save_render

    job = _taken(db, node, job_id)
    key = render_nodes.output_key(job_id)
    if not storage.exists(key):
        raise ApiError(409, "no_output", "Chưa nhận được MP4 của job này")
    if not (math.isfinite(body.seconds) and body.seconds > 0 and math.isfinite(body.elapsed)):
        raise ApiError(422, "invalid_value", "Số giây không hợp lệ")
    with tempfile.TemporaryDirectory(prefix="reels_node_") as raw:
        made = storage.copy_to(key, Path(raw) / "output.mp4")
        try:
            if job.kind == "render":
                manifest = render_nodes.manifest_of(storage, job_id)
                video = db.get(Video, job.video_id)
                save_render(db, storage, video, made, body.seconds, body.elapsed, body.qc, manifest["signature"])
            else:
                motion.attach(db, storage, job, made)
        except motion.MotionError as err:
            db.rollback()
            job = _taken(db, node, job_id)
            _finish(db, job, "failed", err.message, err.detail)
            motion.fail_pending(db, job)
            render_nodes.clean(storage, job_id)
            return {"ok": False, "error": err.message}
    job = db.get(Job, job_id)
    _finish(db, job, "done")
    render_nodes.clean(storage, job_id)
    return {"ok": True}


@router.post("/api/node/jobs/{job_id}/fail")
def fail(
    job_id: int,
    body: FailBody,
    node: RenderNode = Depends(current_node),
    db: DbSession = Depends(get_db),
    storage: DirectoryStorage = Depends(get_storage),
) -> dict:
    """The machine could not render it (FFmpeg or HyperFrames refused): the job fails with the machine's reason."""
    job = _taken(db, node, job_id)
    _finish(db, job, "failed", body.error[:300] or "Máy render không render được", body.detail[-MAX_DETAIL:])
    if job.kind == "motion":
        motion.fail_pending(db, job)
    render_nodes.clean(storage, job_id)
    return {"ok": True}
