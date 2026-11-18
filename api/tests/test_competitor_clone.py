""" "Clone" a competitor's video (decision 2026-11-18-competitor-clone-video): a "Tự viết" video built in code from the
caption, no AI and no job; "Quét bình luận video này" reads one video's comments through the extension."""

import unicodedata

import pytest
from conftest import first_topic, login, make_user
from sqlalchemy import func, select, update

from reels_api import competitors, duplicate
from reels_api.clone import MAX_SCENES, MAX_SCRIPT_LENGTH, clone_script, cut_words
from reels_api.errors import ApiError
from reels_api.models import CompetitorComment, CompetitorScan, CompetitorVideo, Job, Scene, Video
from reels_api.routes_videos import hand_written_scenes

LONG_CAPTION = """3 món ăn sáng giúp xương chắc khỏe sau tuổi 50 🦴 Bác sĩ khuyên nên ăn mỗi ngày.
Nhiều người nghĩ uống sữa là đủ canxi. Thực ra cơ thể cần thêm vitamin D và magie để hấp thụ. Đúng không?

🔹 Vừng đen: giàu canxi, rắc vào cháo hoặc sữa chua.
🔹 Cá mòi đóng hộp ăn cả xương, một hộp nhỏ bằng một cốc sữa.
2. Đậu phụ non
✨✨✨
Nhớ lưu lại và theo dõi để xem thêm mẹo nhé! #suckhoe #xuongkhop ... Xem thêm"""


def paragraphs(script: str) -> list[str]:
    return script.split("\n\n")


def test_a_long_caption_becomes_a_hook_the_ideas_and_a_closing_scene():
    built = clone_script(LONG_CAPTION)

    assert built.topic == "3 món ăn sáng giúp xương chắc khỏe sau tuổi 50"
    assert not built.thin
    scenes = paragraphs(built.script)
    # The hook says the title; the closing call to follow is a scene of its own.
    assert scenes[0] == f"{built.topic}\nĐọc: {built.topic}"
    assert (
        scenes[-1] == "Nhớ lưu lại và theo dõi để xem thêm mẹo nhé\nĐọc: Nhớ lưu lại và theo dõi để xem thêm mẹo nhé!"
    )
    # Each list item is its own scene, its bullet gone, its number kept; its screen text is its first clause.
    assert "Vừng đen\nĐọc: Vừng đen: giàu canxi, rắc vào cháo hoặc sữa chua." in scenes
    assert "2. Đậu phụ non\nĐọc: 2. Đậu phụ non" in scenes
    # Short sentences join the scene before them.
    assert any(scene.endswith("để hấp thụ. Đúng không?") for scene in scenes)
    # Hashtags, emoji, "Xem thêm" and lines of decoration never reach the script.
    for dropped in ("#", "🦴", "🔹", "✨", "Xem thêm"):
        assert dropped not in built.script
    assert built.scenes == len(scenes)
    # It is the "Tự viết" format: the same scenes once parsed.
    assert len(hand_written_scenes(built.script)) == len(scenes)


def test_a_caption_that_is_only_a_title_gives_a_thin_hook_and_closing():
    built = clone_script("Món này ai cũng mê 😍 #anngon #monngon")
    assert built.thin and built.topic == "Món này ai cũng mê"
    assert len(paragraphs(built.script)) == 2


@pytest.mark.parametrize("caption", ["😍🔥 #anngon #xuhuong", "   ", "", None, "✨✨\n#a"])
def test_a_caption_with_no_words_cannot_be_cloned(caption):
    with pytest.raises(ApiError) as refused:
        clone_script(caption)
    assert refused.value.status == 422 and refused.value.code == "competitor_video_no_text"


def test_vietnamese_stays_composed_and_words_are_never_cut():
    decomposed = unicodedata.normalize("NFD", "Xương khớp khỏe mạnh mỗi ngày. Ăn đủ canxi và vận động nhẹ nhàng.")
    built = clone_script(decomposed)
    assert built.script == unicodedata.normalize("NFC", built.script)
    assert built.topic == "Xương khớp khỏe mạnh mỗi ngày."
    assert cut_words("Ăn đủ canxi và vận động", 12) == "Ăn đủ canxi"
    long_title = "Bí quyết " * 60
    topic = clone_script(long_title).topic
    assert len(topic) <= 300 and long_title.startswith(topic + " ")


def test_a_huge_caption_stays_within_the_scene_and_length_limits():
    lines = [
        f"Ý số {n}: ăn uống điều độ, ngủ đủ giấc và đi bộ ba mươi phút mỗi ngày giúp xương chắc." for n in range(80)
    ]
    built = clone_script("Tiêu đề rất hay cho video\n" + "\n".join(lines))
    scenes = hand_written_scenes(built.script)  # raises past 20 scenes or 5000 characters
    assert len(scenes) <= MAX_SCENES and len(built.script) <= MAX_SCRIPT_LENGTH
    # Whole scenes only: every narration ends where a sentence of the caption ends.
    assert all(voice.endswith(".") for _, voice in scenes[1:])


# --- The endpoints ---


def _scan_with_caption(client, captions: dict[str, str | None], comments=None) -> dict:
    """A finished scan of one competitor whose videos (id -> caption) were opened; returns the scan."""
    scan = client.post(
        "/api/competitors/scans", json={"url": "facebook.com/linhdoan", "fetch_comments_top_n": 0}
    ).json()
    client.post("/api/competitors/scanner/claim")
    grid = [{"fb_video_id": fb_id, "views_raw": "5K", "position": n} for n, fb_id in enumerate(captions)]
    client.post(f"/api/competitors/scans/{scan['id']}/videos", json={"videos": grid})
    details = [
        {"fb_video_id": fb_id, "caption": caption, "comment_samples": (comments or {}).get(fb_id, [])}
        for fb_id, caption in captions.items()
    ]
    client.post(f"/api/competitors/scans/{scan['id']}/details", json={"videos": details})
    client.post(f"/api/competitors/scans/{scan['id']}/finish", json={"status": "done", "name": "Linh Đoàn"})
    return scan


def test_clone_makes_a_hand_written_video_with_its_source_and_no_job(client, db):
    make_user(db)
    login(client)
    scan = _scan_with_caption(
        client,
        {"4000001": LONG_CAPTION, "4000002": None},
        comments={"4000001": [{"text": "Mẹ tôi đau gối, ăn được không?", "likes_raw": "12"}]},
    )
    competitor_id = scan["competitor"]["id"]
    group = first_topic(db)

    preview = client.get(f"/api/competitors/{competitor_id}/videos/4000001/clone-preview").json()
    assert preview["topic"] == "3 món ăn sáng giúp xương chắc khỏe sau tuổi 50"
    assert preview["comment_count"] == 1 and preview["can_scan_comments"] and preview["comments_scan"] is None

    response = client.post(
        f"/api/competitors/{competitor_id}/videos/4000001/clone",
        json={"knowledge_topic_id": group.id, "video_mode": "single"},
    )
    assert response.status_code == 201, response.text
    answer = response.json()
    video = db.get(Video, answer["video_id"])
    assert answer["url"] == f"/videos/{video.id}" and answer["has_comments"] and not answer["thin"]
    assert video.hand_written and video.written_via == "" and video.mode == "single"
    assert video.topic == preview["topic"]
    # The title scene, then one scene per paragraph of the script.
    assert answer["scenes"] == 1 + len(paragraphs(preview["script"]))
    assert db.scalar(select(func.count()).where(Scene.video_id == video.id)) == answer["scenes"]
    assert (video.competitor_source_url, video.competitor_source_name) == (
        "https://www.facebook.com/reel/4000001/",
        "Linh Đoàn",
    )
    assert video.competitor_source_video_id is not None
    # No AI call and no render: nothing is queued.
    assert db.scalar(select(func.count()).select_from(Job)) == 0

    page = client.get(f"/api/videos/{video.id}").json()
    assert page["competitor_source"] == {
        "url": "https://www.facebook.com/reel/4000001/",
        "name": "Linh Đoàn",
        "has_comments": True,
        "comments": [{"text": "Mẹ tôi đau gối, ăn được không?", "like_count": 12}],
    }

    # The member's own edits from the dialog win over what the caption gives.
    edited = client.post(
        f"/api/competitors/{competitor_id}/videos/4000001/clone",
        json={"knowledge_topic_id": group.id, "topic": "Tiêu đề của tôi", "script": "Cảnh một\nĐọc: Lời một"},
    ).json()
    assert db.get(Video, edited["video_id"]).topic == "Tiêu đề của tôi" and edited["scenes"] == 2

    no_caption = client.post(
        f"/api/competitors/{competitor_id}/videos/4000002/clone", json={"knowledge_topic_id": group.id}
    )
    assert no_caption.status_code == 422 and no_caption.json()["code"] == "competitor_video_no_caption"
    missing = client.post(
        f"/api/competitors/{competitor_id}/videos/4999999/clone", json={"knowledge_topic_id": group.id}
    )
    assert missing.status_code == 404 and missing.json()["code"] == "competitor_video_not_found"
    no_group = client.post(
        f"/api/competitors/{competitor_id}/videos/4000001/clone", json={"knowledge_topic_id": 999999}
    )
    assert no_group.status_code == 422


def test_a_teammate_clones_and_the_video_is_theirs(client, db):
    make_user(db)
    login(client)
    scan = _scan_with_caption(client, {"4000001": LONG_CAPTION})
    teammate = make_user(db, email="binh@doi.vn", name="Bình")
    login(client, email="binh@doi.vn")
    competitor_id = scan["competitor"]["id"]

    preview = client.get(f"/api/competitors/{competitor_id}/videos/4000001/clone-preview").json()
    assert preview["can_scan_comments"] is False
    response = client.post(
        f"/api/competitors/{competitor_id}/videos/4000001/clone", json={"knowledge_topic_id": first_topic(db).id}
    )
    assert response.status_code == 201
    assert db.get(Video, response.json()["video_id"]).created_by_id == teammate.id
    # Only the member who scans the competitor has its comments read again.
    refused = client.post(f"/api/competitors/{competitor_id}/videos/4000001/scan-comments")
    assert refused.status_code == 403


def test_only_a_facebook_link_is_kept_and_deleting_the_competitor_keeps_link_and_name(client, db, storage):
    me = make_user(db)
    login(client)
    scan = _scan_with_caption(client, {"4000001": LONG_CAPTION, "4000003": "Một video khác về sức khỏe xương"})
    competitor_id = scan["competitor"]["id"]
    group = first_topic(db).id
    db.execute(
        update(CompetitorVideo).where(CompetitorVideo.fb_video_id == "4000003").values(url="https://evil.example/x")
    )
    db.commit()
    odd = client.post(f"/api/competitors/{competitor_id}/videos/4000003/clone", json={"knowledge_topic_id": group})
    assert db.get(Video, odd.json()["video_id"]).competitor_source_url is None

    made = client.post(f"/api/competitors/{competitor_id}/videos/4000001/clone", json={"knowledge_topic_id": group})
    video = db.get(Video, made.json()["video_id"])
    # "Nhân bản y hệt" and the shuffled copies keep where it came from.
    copy, _ = duplicate.copy_video(db, storage, video, me.id, "Bản sao")
    db.commit()
    assert (copy.competitor_source_url, copy.competitor_source_name, copy.competitor_source_video_id) == (
        video.competitor_source_url,
        video.competitor_source_name,
        video.competitor_source_video_id,
    )

    assert client.delete(f"/api/competitors/{competitor_id}").status_code == 204
    db.expire_all()
    video = db.get(Video, video.id)
    assert video.competitor_source_video_id is None
    assert (video.competitor_source_url, video.competitor_source_name) == (
        "https://www.facebook.com/reel/4000001/",
        "Linh Đoàn",
    )
    assert client.get(f"/api/videos/{video.id}").json()["competitor_source"]["comments"] == []


def test_clones_are_limited_per_minute(client, db):
    make_user(db)
    login(client)
    scan = _scan_with_caption(client, {"4000001": "Một video ngắn về sức khỏe"})
    url = f"/api/competitors/{scan['competitor']['id']}/videos/4000001/clone"
    body = {"knowledge_topic_id": first_topic(db).id}
    for _ in range(20):
        assert client.post(url, json=body).status_code == 201
    refused = client.post(url, json=body)
    assert refused.status_code == 429 and refused.json()["code"] == "too_many_clones"


def test_scanning_one_videos_comments_replaces_its_sample_on_the_listed_scan(client, db):
    make_user(db)
    login(client)
    scan = _scan_with_caption(
        client,
        {"4000001": LONG_CAPTION, "4000002": "Video thứ hai"},
        comments={"4000001": [{"text": "Bình luận cũ", "likes_raw": "1"}]},
    )
    competitor_id = scan["competitor"]["id"]

    queued = client.post(f"/api/competitors/{competitor_id}/videos/4000002/scan-comments")
    assert queued.status_code == 201, queued.text
    comments_scan = queued.json()
    assert comments_scan["meta_only"] and comments_scan["comments_for"] == ["4000002"]
    # Asked again, it is the same; another video of the same scan joins the one still waiting.
    assert (
        client.post(f"/api/competitors/{competitor_id}/videos/4000002/scan-comments").json()["id"]
        == comments_scan["id"]
    )
    joined = client.post(f"/api/competitors/{competitor_id}/videos/4000001/scan-comments").json()
    assert joined["id"] == comments_scan["id"] and joined["comments_for"] == ["4000002", "4000001"]
    preview = client.get(f"/api/competitors/{competitor_id}/videos/4000001/clone-preview").json()
    assert preview["comments_scan"] == {"id": comments_scan["id"], "status": "queued"}
    # It is not "Cập nhật thông tin kênh": that one is queued on its own, and the list shows no header refresh.
    row = client.get("/api/competitors").json()["competitors"][0]
    assert row["meta_busy"] is False and row["latest_scan"]["id"] == scan["id"]
    header = client.post(f"/api/competitors/{competitor_id}/refresh-meta").json()
    assert header["id"] != comments_scan["id"] and header["comments_for"] == []

    # Both are light scans, run before any long scan of videos, the older first.
    assert client.post("/api/competitors/scanner/claim").json()["scan"]["id"] == comments_scan["id"]
    # The screen of grid the extension reads first is not kept.
    grid = client.post(
        f"/api/competitors/scans/{comments_scan['id']}/videos",
        json={"videos": [{"fb_video_id": "4000009", "views_raw": "1K", "position": 0}]},
    )
    assert grid.json() == {"videos_found": 0}
    assert db.scalar(select(func.count()).where(CompetitorVideo.scan_id == comments_scan["id"])) == 0

    targets = client.post(f"/api/competitors/scans/{comments_scan['id']}/enrich-targets").json()["targets"]
    assert targets == [
        {"fb_video_id": "4000001", "url": "https://www.facebook.com/reel/4000001/", "comments": True},
        {"fb_video_id": "4000002", "url": "https://www.facebook.com/reel/4000002/", "comments": True},
    ]
    details = {
        "videos": [
            {
                "fb_video_id": "4000001",
                # Anything else sent about a comment, such as who wrote it, is never kept.
                "comment_samples": [{"text": "Bình luận mới", "likes_raw": "2,5K", "author": "Nguyễn Văn B"}],
            }
        ]
    }
    assert client.post(f"/api/competitors/scans/{comments_scan['id']}/details", json=details).json() == {"changed": 1}
    client.post(f"/api/competitors/scans/{comments_scan['id']}/finish", json={"status": "done"})

    listed = db.scalar(
        select(CompetitorVideo).where(CompetitorVideo.scan_id == scan["id"], CompetitorVideo.fb_video_id == "4000001")
    )
    assert competitors.comment_samples(db, listed) == [{"text": "Bình luận mới", "like_count": 2_500}]
    assert set(CompetitorComment.__table__.columns.keys()) == {"id", "video_id", "position", "text", "like_count"}
    # The numbers and the list still come from the scan of videos.
    assert client.get(f"/api/competitors/{competitor_id}/videos").json()["scan_id"] == scan["id"]
    assert db.get(CompetitorScan, comments_scan["id"]).status == "done"
