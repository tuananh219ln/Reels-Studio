"""Running real worker processes against the committed test database."""

import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import sessionmaker

from reels_api.models import (
    AppSetting,
    Fanpage,
    Job,
    KnowledgeTopic,
    LlmProvider,
    Scene,
    Session,
    Setting,
    User,
    Video,
)
from reels_api.security import hash_password


@pytest.fixture
def committed(engine):
    """Real commits on real connections: the worker processes must see the rows."""
    factory = sessionmaker(engine, expire_on_commit=False)
    yield factory
    with factory() as db:
        for model in (Job, Scene, Video, Fanpage, Setting, AppSetting, LlmProvider, Session, User):
            db.execute(delete(model))
        db.execute(delete(KnowledgeTopic).where(KnowledgeTopic.name != "Sức khỏe"))
        db.commit()


def add_user(factory, email="an@doi.vn", name="Nguyễn Văn An") -> User:
    with factory() as db:
        user = User(
            email=email,
            name=name,
            password_hash=hash_password("mat-khau-dung-1"),
            is_active=True,
            must_change_password=False,
        )
        db.add(user)
        db.commit()
        return user


def add_job(factory, video_id: int, user_id: int, kind="script", status="queued", **fields) -> int:
    with factory() as db:
        job = Job(video_id=video_id, kind=kind, status=status, created_by_id=user_id, **fields)
        db.add(job)
        db.commit()
        return job.id


def job_row(factory, job_id: int) -> Job:
    with factory() as db:
        return db.get(Job, job_id)


def wait_until(check, timeout=60.0, interval=0.2, message="condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(interval)
    raise AssertionError(f"timed out waiting for {message}")


def wait_for_status(factory, job_id: int, statuses=("done", "failed", "cancelled"), timeout=60.0) -> Job:
    return wait_until(
        lambda: (job := job_row(factory, job_id)).status in statuses and job,
        timeout,
        message=f"job {job_id} to reach {statuses}",
    )


class WorkerProcess:
    def __init__(self, env: dict[str, str], log: Path):
        self.log = log
        self.handle = open(log, "wb")  # noqa: SIM115 - stays open for the process's lifetime
        self.process = subprocess.Popen(
            [sys.executable, "-m", "reels_api", "worker"], env=env, stdout=self.handle, stderr=subprocess.STDOUT
        )

    def output(self) -> str:
        return self.log.read_text(encoding="utf-8", errors="replace")

    def stop(self) -> None:
        if self.process.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.process.pid)], capture_output=True)
            else:
                self.process.terminate()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.handle.close()


@pytest.fixture
def worker_env(engine, tmp_path):
    temp = tmp_path / "worker-temp"
    temp.mkdir()
    env = dict(os.environ)
    env.update(
        {
            "DATABASE_URL": engine.url.render_as_string(hide_password=False),
            "STORAGE_DIR": str(tmp_path / "storage"),
            # Own temp folder: job work dirs and the Pixabay search cache never leak between tests.
            "TMP": str(temp),
            "TEMP": str(temp),
            "TMPDIR": str(temp),
            "PYTHONIOENCODING": "utf-8",
        }
    )
    return env


@pytest.fixture
def start_worker(worker_env, tmp_path):
    workers: list[WorkerProcess] = []

    def start(**extra: str) -> WorkerProcess:
        worker = WorkerProcess({**worker_env, **extra}, tmp_path / f"worker-{len(workers)}.log")
        workers.append(worker)
        return worker

    yield start
    for worker in workers:
        worker.stop()


def fake_tools(folder: Path, behaviour: str) -> Path:
    """`ffmpeg`/`ffprobe` stand-ins: `hang` records its PID and sleeps, `fail` prints to stderr and exits 1."""
    folder.mkdir(parents=True, exist_ok=True)
    script = folder / "fake_tool.py"
    script.write_text(
        textwrap.dedent(f"""
        import os, sys, time
        if "{behaviour}" == "hang":
            with open(os.environ["FAKE_FFMPEG_PID"], "w") as f:
                f.write(str(os.getpid()))
            time.sleep(600)
        print("Error while filtering: boom from fake ffmpeg", file=sys.stderr)
        sys.exit(1)
    """),
        encoding="utf-8",
    )
    for name in ("ffmpeg", "ffprobe"):
        if os.name == "nt":
            (folder / f"{name}.cmd").write_text(f'@"{sys.executable}" "{script}" %*\n', encoding="utf-8")
        else:
            path = folder / name
            path.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
            path.chmod(0o755)
    return folder
