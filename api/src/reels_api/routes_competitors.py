""" "Phân tích đối thủ" (competitors.py): the member's list, starting and resuming scans, and the calls the open page
makes while it drives the extension (claim a scan, send the grid's videos in batches, finish). Everything is the
member's own: another member's competitors and scans answer 404.
"""

from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from . import clone, competitors
from .db import get_db
from .errors import ApiError
from .models import Scene, Session, Video
from .routes_videos import NewVideoBody, start_video
from .sessions import current_member, now
from .storage import get_storage

router = APIRouter(prefix="/api/competitors")


class ScanBody(BaseModel):
    url: str = Field(max_length=500)
    max_videos: int = Field(competitors.MAX_VIDEOS_DEFAULT, ge=1, le=competitors.MAX_VIDEOS_LIMIT)
    fetch_captions_top_n: int = Field(competitors.CAPTIONS_TOP_DEFAULT, ge=0, le=competitors.CAPTIONS_TOP_LIMIT)
    fetch_comments_top_n: int = Field(competitors.COMMENTS_TOP_DEFAULT, ge=0, le=competitors.COMMENTS_TOP_LIMIT)
    # M5: the Videos tab is read too, after Reels.
    include_videos: bool = False


class GridVideo(BaseModel):
    fb_video_id: str = Field(pattern=r"^\d{5,30}$")
    views_raw: str | None = Field(None, max_length=60)
    position: int | None = Field(None, ge=0, le=100_000)
    # Which grid it was on: Reels or Videos (M5); places count on each grid apart.
    type: Literal["reel", "video"] = "reel"


def video_url(fb_video_id: str, kind: str) -> str:
    """The address the extension opens for a video: built here from its id, never taken from the page."""
    if kind == "video":
        return f"https://www.facebook.com/watch/?v={fb_video_id}"
    return f"https://www.facebook.com/reel/{fb_video_id}/"


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
    # The posting time as written ("3 ngày", "17 tháng 10"); read into posted_at by competitors.parse_posted.
    posted_raw: str | None = Field(None, max_length=200)
    # A small picture of the video (`data:image/jpeg;base64,...`), shrunk by the extension; the api re-encodes it.
    thumbnail: str | None = Field(None, max_length=competitors.AVATAR_DATA_LIMIT)
    # Only for the first fetch_comments_top_n reels; their text and likes, never who wrote them.
    comment_samples: list[CommentSample] = Field(default_factory=list, max_length=60)


class DetailsBody(BaseModel):
    videos: list[VideoDetail] = Field(max_length=competitors.BATCH_LIMIT)


class FinishBody(BaseModel):
    status: Literal["done", "partial", "failed"]
    error: str | None = Field(None, max_length=500)
    name: str | None = Field(None, max_length=200)
    followers: str | None = Field(None, max_length=60)
    is_verified: bool | None = None
    # The avatar as the extension read it: a small `data:image/...;base64,` URL, kept by the api as a 128 px copy.
    avatar: str | None = Field(None, max_length=competitors.AVATAR_DATA_LIMIT)


class PatchBody(BaseModel):
    # None or empty restores the name the scan read.
    custom_name: str | None = Field(None, max_length=200)
    # Which videos of a scan are kept; applies from the next scan that ends.
    video_threshold_mode: Literal["auto", "all", "100k", "1m"] | None = None


class ThresholdBody(BaseModel):
    min_hits: int = Field(ge=competitors.MIN_HITS_RANGE[0], le=competitors.MIN_HITS_RANGE[1])
    min_views: int = Field(ge=competitors.MIN_VIEWS_RANGE[0], le=competitors.MIN_VIEWS_RANGE[1])


@router.get("/settings")
def get_threshold(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """The team's rule for a big channel (Cài đặt › Phân tích đối thủ)."""
    return competitors.threshold_settings(db)


@router.put("/settings")
def put_threshold(body: ThresholdBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """Applies to scans that end from now on; videos already dropped are not read again."""
    value = competitors.save_threshold_settings(db, body.min_hits, body.min_views, me.user_id)
    db.commit()
    return value


@router.get("")
def list_competitors(me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    return {
        "competitors": competitors.list_competitors(db, me.user_id),
        "scanner_online": competitors.scanner_online(me.user),
    }


@router.post("/scans", status_code=201)
def start_scan(body: ScanBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    scan = competitors.start_scan(
        db,
        me.user_id,
        body.url,
        body.max_videos,
        body.fetch_captions_top_n,
        body.fetch_comments_top_n,
        body.include_videos,
    )
    db.commit()
    return competitors.scan_payload(scan)


@router.get("/compare")
def compare(ids: str, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "So sánh": 2–10 of the team's competitors side by side (`ids=1,2,3`), each by its latest scan."""
    try:
        wanted = list(dict.fromkeys(int(part) for part in ids.split(",") if part.strip()))
    except ValueError:
        raise ApiError(422, "bad_compare_ids", "Danh sách đối thủ không hợp lệ") from None
    if not 2 <= len(wanted) <= 10:
        raise ApiError(422, "bad_compare_ids", "Chọn từ 2 đến 10 đối thủ để so sánh")
    return {"competitors": competitors.compare(db, wanted)}


@router.get("/scans/{scan_id}")
def get_scan(scan_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """Any member's scan, its numbers, its ten most viewed videos and the latest report saved on it."""
    scan = competitors.team_scan(db, scan_id)
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


@router.patch("/{competitor_id}")
def patch_competitor(
    competitor_id: int, body: PatchBody, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """`custom_name` (the member's own name, shown everywhere) and `video_threshold_mode`."""
    competitor = competitors.own_competitor(db, competitor_id, me.user_id)
    fields = body.model_fields_set
    if "custom_name" in fields:
        competitors.rename(competitor, body.custom_name)
    if body.video_threshold_mode is not None:
        competitors.set_threshold_mode(competitor, body.video_threshold_mode)
    db.commit()
    return competitors.competitor_payload(competitor)


@router.post("/{competitor_id}/refresh-meta", status_code=201)
def refresh_meta(competitor_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> dict:
    """ "Cập nhật thông tin kênh": a light scan that reads only the Page's header (name, avatar, followers)."""
    competitor = competitors.own_competitor(db, competitor_id, me.user_id)
    scan = competitors.start_scan(db, me.user_id, competitor.fb_url, meta_only=True)
    db.commit()
    return competitors.scan_payload(scan)


@router.get("/{competitor_id}/avatar")
def avatar(competitor_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> FileResponse:
    competitor = competitors.team_competitor(db, competitor_id)
    if not competitor.avatar_key or not get_storage().exists(competitor.avatar_key):
        raise ApiError(404, "avatar_not_found", "Kênh này chưa có ảnh đại diện")
    return FileResponse(
        get_storage().path(competitor.avatar_key),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.get("/{competitor_id}/thumbs/{fb_video_id}")
def thumbnail(
    competitor_id: int, fb_video_id: str, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> FileResponse:
    competitors.team_competitor(db, competitor_id)
    key = f"competitors/{competitor_id}/thumbs/{fb_video_id}.jpg"
    if not fb_video_id.isdigit() or not get_storage().exists(key):
        raise ApiError(404, "thumb_not_found", "Video này chưa có ảnh")
    return FileResponse(
        get_storage().path(key), media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"}
    )


@router.get("/{competitor_id}/videos")
def videos(
    competitor_id: int,
    page: int = Query(1, ge=1, le=10_000),
    limit: int = Query(20, ge=1, le=100),
    sort: Literal["views", "posted"] = "views",
    q: str | None = Query(None, max_length=200),
    min_views: int = Query(0, ge=0, le=1_000_000_000),
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
) -> dict:
    """A page of the videos of the competitor's latest scan, for the expanded row."""
    return competitors.videos_page(db, competitors.team_competitor(db, competitor_id), page, limit, sort, q, min_views)


@router.get("/{competitor_id}/videos.csv")
def videos_csv(competitor_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)) -> Response:
    competitor = competitors.team_competitor(db, competitor_id)
    return Response(
        competitors.videos_csv(db, competitor),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="doi-thu-{competitor.id}.csv"'},
    )


@router.delete("/{competitor_id}", status_code=204)
def delete_competitor(
    competitor_id: int, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> None:
    """ "Xóa dữ liệu": the competitor, every scan of it and every video read, for good."""
    competitor = competitors.own_competitor(db, competitor_id, me.user_id)
    get_storage().delete_prefix(f"competitors/{competitor.id}")
    db.delete(competitor)
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
                "url": video_url(video.fb_video_id, video.type),
                "type": video.type,
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
    """After the grids: the videos whose own page the extension opens next, the most viewed first, then the grids'
    timeline samples (for their posting date). `fb_video_ids` and `comment_ids` stay for extension 1.3.0, which
    opens each as a reel."""
    scan = competitors.own_scan(db, scan_id, me.user_id, lock=True)
    targets = competitors.enrich_targets(db, scan)
    db.commit()
    return {
        "targets": targets,
        "fb_video_ids": [target["fb_video_id"] for target in targets],
        "comment_ids": [target["fb_video_id"] for target in targets if target["comments"]],
    }


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
    competitors.finish(db, scan, body.status, body.error, body.name, body.followers, body.is_verified, body.avatar)
    db.commit()
    return competitors.scan_payload(scan)


# "Clone" (decision 2026-11-18-competitor-clone-video): a "Tự viết" video built in code from a competitor's caption,
# with no AI call and no job; its photos and clips are added by hand on its page.
CLONES_PER_MINUTE = 20
FACEBOOK_PREFIX = "https://www.facebook.com/"
NO_CAPTION = "Video chưa có caption để clone"


class CloneBody(BaseModel):
    knowledge_topic_id: int
    video_mode: Literal["slides", "single"] | None = None
    # What the member edited in the dialog; left out, both are built from the caption.
    topic: str | None = Field(None, max_length=1000)
    script: str | None = Field(None, max_length=20_000)


def _captioned(db: DbSession, competitor_id: int, fb_video_id: str):
    competitor = competitors.team_competitor(db, competitor_id)
    video = competitors.listed_video(db, competitor, fb_video_id)
    if not (video.caption or "").strip():
        raise ApiError(422, "competitor_video_no_caption", NO_CAPTION)
    return competitor, video


def _comments_scan(db: DbSession, video) -> dict | None:
    scan = competitors.active_comments_scan(db, video)
    return {"id": scan.id, "status": scan.status} if scan else None


@router.get("/{competitor_id}/videos/{fb_video_id}/clone-preview")
def clone_preview(
    competitor_id: int, fb_video_id: str, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """What "Tạo video" would make, for the dialog to show and edit; nothing is saved."""
    competitor, video = _captioned(db, competitor_id, fb_video_id)
    built = clone.clone_script(video.caption)
    return {
        "topic": built.topic,
        "script": built.script,
        "scenes": built.scenes,
        "thin": built.thin,
        "comment_count": competitors.comment_count(db, video),
        # Only the member who scans the competitor reads its comments again ("Quét bình luận video này").
        "can_scan_comments": competitor.owner_id == me.user_id,
        "comments_scan": _comments_scan(db, video),
    }


@router.post("/{competitor_id}/videos/{fb_video_id}/clone", status_code=201)
def clone_video(
    competitor_id: int,
    fb_video_id: str,
    body: CloneBody,
    me: Session = Depends(current_member),
    db: DbSession = Depends(get_db),
) -> dict:
    """Any member clones any of the team's competitors' videos; the new video is theirs. No job is queued."""
    competitor, source = _captioned(db, competitor_id, fb_video_id)
    recent = db.scalar(
        select(func.count()).where(
            Video.created_by_id == me.user_id,
            Video.competitor_source_name.is_not(None),
            Video.created_at > now() - timedelta(minutes=1),
        )
    )
    if recent >= CLONES_PER_MINUTE:
        raise ApiError(429, "too_many_clones", "Bạn vừa clone nhiều video liền nhau, đợi một phút rồi thử lại")
    built = None
    if not (body.topic or "").strip() or body.script is None:
        built = clone.clone_script(source.caption)
    topic = (body.topic or "").strip() or built.topic
    script = body.script if body.script is not None else built.script
    video = start_video(
        NewVideoBody(
            topic=clone.cut_words(" ".join(topic.split()), clone.MAX_TOPIC_LENGTH),
            knowledge_topic_id=body.knowledge_topic_id,
            mode="manual",
            script=script,
            video_mode=body.video_mode,
        ),
        me,
        db,
    )
    video.competitor_source_url = source.url if source.url.startswith(FACEBOOK_PREFIX) else None
    video.competitor_source_name = competitors.display_name(competitor)[:200]
    video.competitor_source_video_id = source.id
    db.flush()
    scenes = db.scalar(select(func.count()).where(Scene.video_id == video.id))
    db.commit()
    comment_count = competitors.comment_count(db, source)
    return {
        "video_id": video.id,
        "url": f"/videos/{video.id}",
        "scenes": scenes,
        "thin": built.thin if built else False,
        "has_comments": comment_count > 0,
    }


@router.post("/{competitor_id}/videos/{fb_video_id}/scan-comments", status_code=201)
def scan_comments(
    competitor_id: int, fb_video_id: str, me: Session = Depends(current_member), db: DbSession = Depends(get_db)
) -> dict:
    """ "Quét bình luận video này": the member's open page has the extension read this one video's comments."""
    competitor = competitors.own_competitor(db, competitor_id, me.user_id)
    video = competitors.listed_video(db, competitor, fb_video_id)
    scan = competitors.start_comments_scan(db, me.user_id, video)
    db.commit()
    return competitors.scan_payload(scan)
