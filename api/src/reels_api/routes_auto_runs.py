"""Semi-automatic posting's runs ("Bán tự động", auto_runs.py): what the worker prepared, and the owner's approval."""

from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import auto_runs
from .db import get_db
from .errors import ApiError
from .models import AutoRun, Session
from .sessions import current_member

router = APIRouter(prefix="/api/auto-runs")


class ApproveBody(BaseModel):
    skip_tiktok: bool = False


@router.get("")
def list_runs(
    knowledge_topic_id: int | None = None,
    day: date | None = None,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
) -> list[dict]:
    """The runs, newest day first; `knowledge_topic_id` keeps those of the group's Pages, `day` one day's."""
    return [auto_runs.payload(db, run, me.user_id) for run in auto_runs.runs_of(db, knowledge_topic_id, day)]


def _run(db: DbSession, run_id: int) -> AutoRun:
    run = db.scalar(select(AutoRun).where(AutoRun.id == run_id, AutoRun.role == "facebook").with_for_update())
    if run is None:
        raise ApiError(404, "auto_run_not_found", "Không tìm thấy lượt chạy")
    return run


@router.post("/{run_id}/approve")
def approve(
    run_id: int, body: ApproveBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Duyệt": the Facebook post at the idea's posting time and, unless skipped, the TikTok draft after it."""
    run = _run(db, run_id)
    try:
        auto_runs.approve(db, run, me.user_id, body.skip_tiktok)
    except auto_runs.ApprovalError as err:
        raise ApiError(409, "auto_run_refused", str(err)) from None
    db.commit()
    return auto_runs.payload(db, run, me.user_id)


@router.post("/{run_id}/reject")
def reject(run_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Không duyệt": nothing is posted; the video stays to be fixed by hand."""
    run = _run(db, run_id)
    try:
        auto_runs.reject(db, run, me.user_id)
    except auto_runs.ApprovalError as err:
        raise ApiError(409, "auto_run_refused", str(err)) from None
    db.commit()
    return auto_runs.payload(db, run, me.user_id)
