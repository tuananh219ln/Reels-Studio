""" "Phân tích đối thủ" (competitors.py): the member's list, starting and resuming scans, and the calls the open page
makes while it drives the extension (claim a scan, send the grid's videos in batches, finish). Everything is the
member's own: another member's competitors and scans answer 404.
"""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession

from . import competitors
from .db import get_db
from .models import Session
from .sessions import current_member

router = APIRouter(prefix="/api/competitors")


class ScanBody(BaseModel):
    url: str = Field(max_length=500)
    max_videos: int = Field(competitors.MAX_VIDEOS_DEFAULT, ge=1, le=competitors.MAX_VIDEOS_LIMIT)
    fetch_captions_top_n: int = Field(competitors.CAPTIONS_TOP_DEFAULT, ge=0, le=competitors.CAPTIONS_TOP_LIMIT)
    fetch_comments_top_n: int = Field(competitors.COMMENTS_TOP_DEFAULT, ge=0, le=competitors.COMMENTS_TOP_LIMIT)


class GridVideo(BaseModel):
    fb_video_id: str = Field(pattern=r"^\d{5,30}$")
    views_raw: str | None = Field(None, max_length=60)
    position: int | None = Field(None, ge=0, le=100_000)


class VideosBody(BaseModel):
    videos: list[GridVideo] = Field(max_length=competitors.BATCH_LIMIT)


class CommentSample(BaseModel):
    text: str = Field(max_length=5000)
    likes_raw: str | None = Field(None, max_length=60)


class VideoDetail(BaseModel):
    fb_video_id: str = Field(pattern=r"^\d{5,30}$")
    caption: str | None = Field(None, max_length=20_000)
    audio_name: str | None = Field(None, max_length=1000)
    duration_s: int | None = Field(None, ge=0, le=36_000)
    reactions_raw: str | None = Field(None, max_length=60)
    comments_raw: str | None = Field(None, max_length=60)
    shares_raw: str | None = Field(None, max_length=60)
    # Only for the first fetch_comments_top_n reels; their text and likes, never who wrote them.
    comment_samples: list[CommentSample] = Field(default_factory=list, max_length=60)


class DetailsBody(BaseModel):
    videos: list[VideoDetail] = Field(max_length=competitors.BATCH_LIMIT)


class FinishBody(BaseModel):
    status: Literal["done", "partial", "failed"]
    error: str | None = Field(None, max_length=500)
    name: str | None = Field(None, max_length=200)
    followers: str | None = Field(None, max_length=60)


@router.get("")
def list_competitors(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    return {
        "competitors": competitors.list_competitors(db, me.user_id),
        "scanner_online": competitors.scanner_online(me.user),
    }


@router.post("/scans", status_code=201)
def start_scan(body: ScanBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    scan = competitors.start_scan(
        db, me.user_id, body.url, body.max_videos, body.fetch_captions_top_n, body.fetch_comments_top_n
    )
    db.commit()
    return competitors.scan_payload(scan)


@router.get("/scans/{scan_id}")
def get_scan(scan_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """The scan, its numbers, its ten most viewed videos and the latest report its member's Claude saved."""
    scan = competitors.own_scan(db, scan_id, me.user_id)
    top = competitors.videos_of(db, scan.id)[:10]
    report = competitors.latest_report(db, scan.id)
    return {
        **competitors.scan_payload(scan),
        "stats": competitors.stats(db, scan),
        "top_videos": [competitors.video_payload(video, rank) for rank, video in enumerate(top, start=1)],
        "report": competitors.report_payload(report) if report else None,
    }


@router.post("/scans/{scan_id}/resume")
def resume_scan(scan_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    scan = competitors.own_scan(db, scan_id, me.user_id, lock=True)
    competitors.resume(scan)
    db.commit()
    return competitors.scan_payload(scan)


@router.delete("/{competitor_id}", status_code=204)
def delete_competitor(
    competitor_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> None:
    """ "Xóa dữ liệu": the competitor, every scan of it and every video read, for good."""
    db.delete(competitors.own_competitor(db, competitor_id, me.user_id))
    db.commit()


@router.post("/scanner/claim")
def claim(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """The open page, with the extension there, asks for work; asking also marks the extension online for MCP."""
    scan = competitors.claim(db, me.user)
    db.commit()
    return {"scan": competitors.scan_payload(scan) if scan else None}


@router.post("/scans/{scan_id}/videos")
def add_videos(
    scan_id: int, body: VideosBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    scan = competitors.own_scan(db, scan_id, me.user_id, lock=True)
    found = competitors.add_videos(
        db,
        scan,
        [
            {
                "fb_video_id": video.fb_video_id,
                "url": f"https://www.facebook.com/reel/{video.fb_video_id}/",
                "type": "reel",
                "views_raw": video.views_raw,
                "position": video.position,
            }
            for video in body.videos
        ],
    )
    db.commit()
    return {"videos_found": found}


@router.post("/scans/{scan_id}/enrich-targets")
def enrich_targets(scan_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """After the grid: the reels whose own page the extension opens next, most viewed first."""
    scan = competitors.own_scan(db, scan_id, me.user_id, lock=True)
    ids = competitors.enrich_targets(db, scan)
    db.commit()
    # The first of them also have their comments sampled.
    return {"fb_video_ids": ids, "comment_ids": ids[: competitors.comments_top(scan)]}


@router.post("/scans/{scan_id}/details")
def add_details(
    scan_id: int, body: DetailsBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    scan = competitors.own_scan(db, scan_id, me.user_id, lock=True)
    changed = competitors.add_details(db, scan, [video.model_dump() for video in body.videos])
    db.commit()
    return {"changed": changed}


@router.post("/scans/{scan_id}/finish")
def finish_scan(
    scan_id: int, body: FinishBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    scan = competitors.own_scan(db, scan_id, me.user_id, lock=True)
    competitors.finish(db, scan, body.status, body.error, body.name, body.followers)
    db.commit()
    return competitors.scan_payload(scan)
