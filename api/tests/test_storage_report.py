from datetime import UTC, datetime, timedelta

from reels_api.storage_report import Item, VideoState, build, kind_of, scan

NOW = datetime(2026, 12, 10, tzinfo=UTC)
MB = 1024 * 1024


def test_kind_of_reads_the_file_name():
    assert kind_of("video-ab12.mp4") == "MP4 cuối"
    assert kind_of("motion-photo-3-ab.jpg") == "Cảnh động"
    assert kind_of("voice-7-ab.mp3") == "Lời đọc"
    assert kind_of("something.bin") == "Khác"


def test_scan_lists_video_files_only(tmp_path):
    folder = tmp_path / "videos" / "5"
    folder.mkdir(parents=True)
    (folder / "clip-1-ab.mp4").write_bytes(b"x" * 10)
    (folder / ".half.tmp").write_bytes(b"y")
    (tmp_path / "brands").mkdir()
    (tmp_path / "brands" / "logo.png").write_bytes(b"z")
    assert [(i.video_id, i.kind, i.size) for i in scan(tmp_path)] == [(5, "Clip cảnh", 10)]


def test_build_counts_what_each_level_would_free():
    items = [
        Item(1, "Clip cảnh", 40 * MB),
        Item(1, "MP4 cuối", 20 * MB),
        Item(1, "Ảnh thu nhỏ", MB),
        Item(2, "Clip cảnh", 10 * MB),
        Item(2, "MP4 cuối", 5 * MB),
        Item(3, "Lời đọc", 2 * MB),
        Item(4, "Clip cảnh", 7 * MB),
        Item(9, "Clip cảnh", 3 * MB),
    ]
    states = {
        1: VideoState(NOW - timedelta(days=70)),
        2: VideoState(NOW - timedelta(days=40)),
        3: VideoState(None),
        4: VideoState(NOW - timedelta(days=90), open_post=True),
    }
    text = "\n".join(build(items, states, NOW))
    # Level 1: the clips of videos 1 and 2 (50 MB); the thumbnail, the MP4s, the unposted video 3, the video with an open
    # post (4) and the orphan folder (9) are left alone. Level 2: video 1's MP4 only.
    assert "Mức 1, file dựng của 2 video đăng quá 30 ngày: 50.0 MB" in text
    assert "Mức 2, thêm MP4 của 1 video đăng quá 60 ngày: 20.0 MB" in text
    assert "Thư mục không còn video trong cơ sở dữ liệu: 3.0 MB (1 file)" in text
    assert "Còn bài đang mở: 7.0 MB" in text


def test_video_states_reads_posts(db):
    from conftest import make_user

    from reels_api.models import Publication, Video
    from reels_api.storage_report import video_states

    user = make_user(db)
    posted, waiting, draft = (Video(topic=name, created_by_id=user.id) for name in ("a", "b", "c"))
    db.add_all([posted, waiting, draft])
    db.flush()
    when = NOW - timedelta(days=5)
    db.add_all(
        [
            Publication(
                video_id=posted.id, platform="facebook", status="published", published_at=when, created_by_id=user.id
            ),
            Publication(video_id=waiting.id, platform="youtube", status="private", created_by_id=user.id),
            Publication(
                video_id=waiting.id, platform="facebook", status="published", published_at=when, created_by_id=user.id
            ),
        ]
    )
    db.flush()
    states = video_states(db)
    assert states[posted.id].last_post == when and not states[posted.id].open_post
    assert states[waiting.id].open_post
    assert states[draft.id].last_post is None
