from datetime import UTC, datetime, timedelta

import pytest
from conftest import make_user

from reels_api import media_cleanup
from reels_api.errors import ApiError
from reels_api.models import Job, PageQueueItem, Publication, Video, VideoPresence
from reels_api.storage import DirectoryStorage

NOW = datetime(2026, 12, 20, 3, 0, tzinfo=UTC)


def video(db, user, name="v", days_ago=40, status="published", approved=True, **fields) -> Video:
    row = Video(
        topic=name,
        created_by_id=user.id,
        review_status="approved" if approved else "pending_review",
        mp4_key=f"videos/9/{name}-video.mp4",
        thumbnail_key=f"videos/9/{name}-thumb.jpg",
        **fields,
    )
    db.add(row)
    db.flush()
    db.add(
        Publication(
            video_id=row.id,
            platform="facebook",
            status=status,
            published_at=NOW - timedelta(days=days_ago),
            created_by_id=user.id,
        )
    )
    db.flush()
    return row


def due_ids(db) -> list[int]:
    return [item.video_id for item in media_cleanup.choose(db, NOW, days=30)]


def test_an_old_posted_video_is_due(db):
    user = make_user(db)
    old = video(db, user, "old", 40)
    video(db, user, "fresh", 10)
    assert due_ids(db) == [old.id]


@pytest.mark.parametrize(
    "fields",
    [{"keep_media": True}, {"media_cleaned_at": NOW}, {"approved": False}],
)
def test_a_video_kept_cleaned_or_unapproved_is_not_due(db, fields):
    user = make_user(db)
    video(db, user, "x", 40, **fields)
    assert due_ids(db) == []


def test_a_video_with_a_post_still_to_go_out_is_not_due(db):
    user = make_user(db)
    row = video(db, user, "x", 40)
    db.add(Publication(video_id=row.id, platform="youtube", status="scheduled", created_by_id=user.id))
    db.flush()
    assert due_ids(db) == []


def test_a_video_left_private_on_youtube_is_still_due(db):
    user = make_user(db)
    row = video(db, user, "x", 40)
    db.add(Publication(video_id=row.id, platform="youtube", status="private", created_by_id=user.id))
    db.flush()
    assert due_ids(db) == [row.id]


def test_a_queued_video_a_running_job_or_an_open_editor_hold_it_back(db):
    from reels_api.models import Fanpage

    user = make_user(db)
    queued, working, editing = (video(db, user, name, 40) for name in ("q", "w", "e"))
    page = Fanpage(name="p", page_id="1", token_encrypted="x", token_tail="x")
    db.add(page)
    db.flush()
    db.add(PageQueueItem(fanpage_id=page.id, video_id=queued.id, position=1, added_by_id=user.id))
    db.add(Job(kind="render", video_id=working.id, status="running", created_by_id=user.id))
    db.add(VideoPresence(video_id=editing.id, tab="t", user_id=user.id, editing=True, seen_at=NOW))
    db.flush()
    assert due_ids(db) == []


def test_a_source_of_a_recent_copy_is_kept(db):
    user = make_user(db)
    source = video(db, user, "src", 40)
    copy = video(db, user, "copy", 5, shuffled_from_id=source.id)
    copy.created_at = NOW - timedelta(days=5)
    db.flush()
    assert source.id not in due_ids(db)


def test_clean_video_deletes_everything_but_the_mp4s_and_the_thumbnail(db, tmp_path):
    user = make_user(db)
    row = video(db, user, "x", 40)
    storage = DirectoryStorage(tmp_path)
    folder = tmp_path / "videos" / str(row.id)
    folder.mkdir(parents=True)
    for name, size in {
        "x-video.mp4": 100,
        "x-thumb.jpg": 10,
        "clip-1.mp4": 1000,
        "voice-1.mp3": 50,
        "scene-1.jpg": 5,
    }.items():
        (folder / name).write_bytes(b"0" * size)
    # A post made from another MP4 keeps it.
    row.mp4_key, row.thumbnail_key = f"videos/{row.id}/x-video.mp4", f"videos/{row.id}/x-thumb.jpg"
    db.add(
        Publication(
            video_id=row.id,
            platform="facebook",
            status="published",
            remote_mp4_key=f"videos/{row.id}/clip-1.mp4",
            created_by_id=user.id,
        )
    )
    db.flush()
    freed = media_cleanup.clean_video(db, storage, row, dry_run=True)
    assert freed == 55 and (folder / "voice-1.mp3").exists() and row.media_cleaned_at is None
    freed = media_cleanup.clean_video(db, storage, row)
    assert freed == 55 and row.media_freed_bytes == 55 and row.media_cleaned_at is not None
    assert sorted(path.name for path in folder.iterdir()) == ["clip-1.mp4", "x-thumb.jpg", "x-video.mp4"]


def test_a_cleaned_video_refuses_what_needs_its_files(db):
    user = make_user(db)
    row = video(db, user, "x", 40, media_cleaned_at=NOW)
    with pytest.raises(ApiError) as error:
        media_cleanup.ensure_media(row, "render")
    assert error.value.status == 409 and "đã được dọn ngày 20/12/2026" in error.value.message
