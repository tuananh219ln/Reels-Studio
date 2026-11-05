"""The worker service: `python -m reels_api worker`.

- Only one worker is active: it holds a Postgres advisory lock for its whole life, so the new
  container of a deploy waits until the old one has exited.
- The queue is the `jobs` table: jobs are claimed with SELECT ... FOR UPDATE SKIP LOCKED, one at a time.
- Each job runs in its own child process (`python -m reels_api run-job <id>`) in its own process
  group, so a job over the time limit is killed together with the FFmpeg it started.
"""

import logging
import os
import shutil
import signal
import subprocess
import sys
import time

from sqlalchemy import Connection, Engine, create_engine, inspect, select, text, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from . import affiliate_rounds, comments_inbox, config, fanpages, metrics, page_queue, post_comments
from .jobs import queue_post_checks, work_dir
from .models import Job
from .sessions import now

log = logging.getLogger("reels_api.worker")

ADVISORY_LOCK_KEY = 2026_10_29_01
POLL_SECONDS = 1.0
WAIT_SECONDS = 5.0
# How often scheduled reels whose time has passed are looked for, to be checked on Facebook.
POST_CHECK_SECONDS = 60.0
# How often posts whose numbers are due (metrics.py), Pages due a check (fanpages.py) and comments due
# (post_comments.py), and visitors' comments to read or answer (comments_inbox.py) are looked for: often, so
# "Cập nhật view", "Kiểm tra ngay", "Bình luận ngay" and a reply answer in seconds.
METRICS_SECONDS = 5.0
DEFAULT_JOB_TIMEOUT = 15 * 60
RESTARTED = "Worker khởi động lại giữa chừng"


class Stop(Exception):
    """SIGTERM/SIGINT: stop after killing the running job's process group."""


def job_timeout() -> float:
    raw = config.read_env("JOB_TIMEOUT_SECONDS")
    return float(raw) if raw else DEFAULT_JOB_TIMEOUT


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s", stream=sys.stdout
    )

    def stop(signum, frame):
        raise Stop

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    engine = create_engine(config.database_url(), pool_pre_ping=True, connect_args={"connect_timeout": 5})
    try:
        wait_for_jobs_table(engine)
        with acquire_worker_lock(engine) as lock:
            factory = sessionmaker(engine)
            recover_interrupted(factory)
            serve(factory, lock)
    except Stop:
        log.info("Worker stopping")
    return 0


def wait_for_jobs_table(engine: Engine) -> None:
    """The api runs the migrations; a worker deployed first waits instead of crashing."""
    while True:
        try:
            if inspect(engine).has_table("jobs"):
                return
            log.info("Table jobs does not exist yet (migrations not applied), waiting")
        except OperationalError as err:
            log.warning("Database unavailable (%s), waiting", type(err.orig).__name__ if err.orig else err)
        time.sleep(WAIT_SECONDS)


def acquire_worker_lock(engine: Engine) -> Connection:
    connection = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    if not connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": ADVISORY_LOCK_KEY}):
        log.info("Another worker is active, waiting for it to exit")
        connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": ADVISORY_LOCK_KEY})
    log.info("Worker lock acquired")
    return connection


def recover_interrupted(factory: sessionmaker) -> None:
    """A job still `running` belonged to a worker that died; it is never re-run automatically (cost)."""
    with factory() as db:
        ids = db.scalars(
            update(Job)
            .where(Job.status == "running")
            .values(status="failed", error=RESTARTED, finished_at=now())
            .returning(Job.id)
        ).all()
        db.commit()
    for job_id in ids:
        log.warning("Job %s was running when the previous worker stopped: marked failed", job_id)


def claim_next(factory: sessionmaker) -> int | None:
    with factory() as db:
        job = db.scalar(
            select(Job).where(Job.status == "queued").order_by(Job.id).limit(1).with_for_update(skip_locked=True)
        )
        if job is None:
            return None
        job.status, job.started_at = "running", now()
        db.commit()
        return job.id


def queue_checks(factory: sessionmaker) -> None:
    """A database hiccup here must not stop the queue: the next round tries again."""
    try:
        with factory() as db:
            queue_post_checks(db)
            db.commit()
    except Exception:
        log.exception("Could not queue the post checks")


def serve(factory: sessionmaker, lock: Connection) -> None:
    next_checks = next_metrics = 0.0
    while True:
        # Losing the lock connection would let a second worker start: exit and let Coolify restart us.
        lock.execute(text("SELECT 1"))
        if time.monotonic() >= next_checks:
            queue_checks(factory)
            page_queue.fill_due(factory)
            next_checks = time.monotonic() + POST_CHECK_SECONDS
        if time.monotonic() >= next_metrics:
            metrics.measure_due(factory)
            fanpages.check_due(factory)
            post_comments.write_due(factory)
            comments_inbox.run_round(factory)
            affiliate_rounds.run_round(factory)
            next_metrics = time.monotonic() + METRICS_SECONDS
        job_id = claim_next(factory)
        if job_id is None:
            time.sleep(POLL_SECONDS)
            continue
        run_in_child(factory, job_id)


def _child_options() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def kill_tree(process: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True, check=False)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait()


def run_in_child(factory: sessionmaker, job_id: int) -> None:
    timeout = job_timeout()
    process = subprocess.Popen([sys.executable, "-m", "reels_api", "run-job", str(job_id)], **_child_options())
    try:
        code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_tree(process)
        # The child and its FFmpeg are dead now, so nothing can write after this.
        _fail_if_running(
            factory,
            job_id,
            f"Job chạy quá {timeout / 60:g} phút nên đã bị dừng",
            f"Tiến trình job bị dừng sau {timeout:g} giây",
        )
        log.warning("Job %s exceeded %gs: killed", job_id, timeout)
        return
    except BaseException:
        kill_tree(process)
        raise
    finally:
        shutil.rmtree(work_dir(job_id), ignore_errors=True)
    _fail_if_running(factory, job_id, "Tiến trình job dừng bất ngờ", f"Mã thoát {code}")


def _fail_if_running(factory: sessionmaker, job_id: int, error: str, detail: str) -> None:
    with factory() as db:
        db.execute(
            update(Job)
            .where(Job.id == job_id, Job.status == "running")
            .values(status="failed", error=error, error_detail=detail, finished_at=now())
        )
        db.commit()


def run_job_command(job_id: int) -> int:
    """Body of the child process."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s", stream=sys.stdout
    )
    from .jobs import run_job
    from .storage import get_storage

    engine = create_engine(config.database_url(), pool_pre_ping=True, connect_args={"connect_timeout": 5})
    run_job(job_id, sessionmaker(engine), get_storage())
    engine.dispose()
    return 0
