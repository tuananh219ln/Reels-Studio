"""Render machines: a member's own computer renders for the team, so the VPS stays light.

With "Render trên máy render" on (Cài đặt › Máy render), the worker still does every light step of a render or
motion job (narration from ElevenLabs, checks, gathering the files), packs what the render needs into a bundle in
storage, marks the job `node_stage = "ready"` and leaves it running. A machine running `python -m reels_api node`
(node.py) claims it over HTTPS with its token, renders it (FFmpeg, HyperFrames, QC), uploads the result, and the
api finishes the job exactly as the worker would have. A job waits for a machine as long as it takes (the owner's
choice); a machine that stops answering for STALE gives its job back for another to take.
"""

import io
import json
import logging
import time
import zipfile
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session as DbSession

from .models import AppSetting, Job
from .sessions import now
from .storage import DirectoryStorage

log = logging.getLogger(__name__)

SETTING = "render_on_node"
KINDS = ("render", "motion")
STALE = timedelta(minutes=10)
ONLINE = timedelta(minutes=1)


class HandedOff(Exception):
    """Raised by a job handler once its bundle is packed: the job stays running until a machine finishes it."""


def enabled(db: DbSession) -> bool:
    row = db.get(AppSetting, SETTING)
    return bool(row and row.value)


def bundle_key(job_id: int) -> str:
    return f"jobs/{job_id}/bundle.zip"


def manifest_key(job_id: int) -> str:
    return f"jobs/{job_id}/manifest.json"


def output_key(job_id: int) -> str:
    return f"jobs/{job_id}/output.mp4"


def pack(db: DbSession, storage: DirectoryStorage, job: Job, manifest: dict, folder: Path) -> None:
    """Zip `folder` (the files the manifest names) with the manifest, and hand the job to the render machines."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as bundle:
        bundle.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        for path in sorted(folder.iterdir()):
            if path.is_file():
                bundle.write(path, path.name)
    storage.save_bytes(bundle_key(job.id), buffer.getvalue())
    storage.save_bytes(manifest_key(job.id), json.dumps(manifest, ensure_ascii=False).encode())
    db.execute(update(Job).where(Job.id == job.id).values(node_stage="ready", node_id=None, node_seen_at=None))
    db.commit()
    log.info("Job %s (%s) packed for a render machine", job.id, job.kind)


def manifest_of(storage: DirectoryStorage, job_id: int) -> dict:
    return json.loads(storage.path(manifest_key(job_id)).read_bytes())


def claim(db: DbSession, node_id: int) -> Job | None:
    """The oldest job waiting for a machine, after giving back those whose machine went silent."""
    db.execute(
        update(Job)
        .where(Job.status == "running", Job.node_stage == "taken", Job.node_seen_at < now() - STALE)
        .values(node_stage="ready", node_id=None, node_seen_at=None)
    )
    job = db.scalar(
        select(Job)
        .where(Job.status == "running", Job.node_stage == "ready")
        .order_by(Job.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is not None:
        job.node_stage, job.node_id, job.node_seen_at = "taken", node_id, now()
    db.commit()
    return job


def clean(storage: DirectoryStorage, job_id: int) -> None:
    storage.delete_prefix(f"jobs/{job_id}/")


# --- What a machine does with a bundle (also what the worker does when no machine is used) ---


def render_bundle(folder: Path, manifest: dict) -> dict:
    """Render the bundle unpacked in `folder` to folder/output.mp4; returns its seconds, the render time and its QC."""
    from reels_render import render_video
    from reels_render.ffmpeg import find_tools, probe
    from reels_render.options import RenderOptions
    from reels_render.script import parse_script

    from . import motion, qc

    output = folder / "output.mp4"
    started = time.monotonic()
    if manifest["kind"] == "motion":
        photo = folder / manifest["photo"] if manifest.get("photo") else None
        made = motion.render_clip(folder / "work", manifest["html"], manifest["seconds"], photo)
        made.replace(output)
        return {"seconds": manifest["seconds"], "elapsed": round(time.monotonic() - started, 1), "qc": None}
    music = folder / manifest["music"] if manifest.get("music") else None
    render_video(
        parse_script(manifest["data"], base_dir=folder),
        output,
        music=music,
        music_volume=manifest["music_volume"],
        music_start=manifest["music_start"],
        options=RenderOptions(**manifest["options"]),
    )
    seconds = float(probe(find_tools().ffprobe, output)["format"]["duration"])
    elapsed = round(time.monotonic() - started, 1)
    return {"seconds": seconds, "elapsed": elapsed, "qc": qc.measure(output, expect_sound=manifest["expect_sound"])}


def options_dict(options) -> dict:
    """The render options for a machine. `backdrop` is sent only when on: a machine on older code renders slide
    videos as before, and refuses a backdrop video (an option it does not know) instead of rendering it wrong."""
    values = asdict(options)
    # Each sent only when on, for the same reason: `clip_blur` (blurred boxes on a clip) too.
    for name in ("backdrop", "clip_blur"):
        if not values[name]:
            del values[name]
    # Likewise "Dạng chữ" only when the text is drawn as typed: an older machine would draw it in capitals.
    for name in ("text_case", "title_text_case"):
        if values[name] == "upper":
            del values[name]
    return values
