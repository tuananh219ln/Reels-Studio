import io
import time

import pytest
from PIL import Image
from sqlalchemy import select

from conftest import (
    SCENE_TEXT,
    client_for,
    login,
    make_user,
    make_video,
    photo_bytes,
)
from reels_api.models import Job, Scene, Video


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


@pytest.fixture
def binh(app, db):
    make_user(db, email="binh@doi.vn", name="Trần Thị Bình")
    other = client_for(app)
    login(other, email="binh@doi.vn")
    return other


def scene_ids(db, video):
    return db.scalars(select(Scene.id).where(Scene.video_id == video.id, Scene.is_title.is_(False))
                      .order_by(Scene.position)).all()


def title_id(db, video):
    return db.scalar(select(Scene.id).where(Scene.video_id == video.id, Scene.is_title))


def add_job(db, video, user, kind="render", status="queued", **fields):
    job = Job(video_id=video.id, kind=kind, status=status, created_by_id=user.id, **fields)
    db.add(job)
    db.commit()
    return job


# --- Creating and listing ---

def test_new_video_queues_a_script_job_and_is_locked(an, db):
    response = an.post("/api/videos", json={"topic": "  thực phẩm tốt cho  xương khớp "})
    assert response.status_code == 201
    video = response.json()
    assert video["topic"] == "thực phẩm tốt cho xương khớp"
    assert (video["status"], video["status_label"], video["locked"]) == ("queued", "Chờ thứ 1", True)
    assert video["active_job"]["kind"] == "script"
    assert video["created_by"] == "Nguyễn Văn An"
    assert an.post("/api/videos", json={"topic": "   "}).json()["message"] == "Hãy nhập chủ đề"


def test_queue_position_counts_jobs_ahead(an, db, me, storage):
    first, second = make_video(db, storage, me), make_video(db, storage, me)
    add_job(db, first, me)
    add_job(db, second, me)
    assert an.get(f"/api/videos/{second.id}").json()["status_label"] == "Chờ thứ 2"


def test_list_searches_title_and_topic_and_shows_status(an, db, me, storage):
    make_video(db, storage, me, topic="tim mạch", title_text="7 MÓN\n*BỔ TIM*")
    make_video(db, storage, me, topic="xương khớp")
    assert [row["title"] for row in an.get("/api/videos", params={"q": "bổ tim"}).json()] == ["7 MÓN BỔ TIM"]
    assert [row["topic"] for row in an.get("/api/videos", params={"q": "XƯƠNG"}).json()] == ["xương khớp"]
    row = an.get("/api/videos").json()[0]
    assert {"thumbnail_url", "status_label", "created_by", "created_at", "mp4_outdated", "rerender_failed"} <= set(row)


def test_a_teammate_sees_edits_and_renders_a_video_someone_else_made(binh, db, me, storage):
    video = make_video(db, storage, me)
    assert [row["id"] for row in binh.get("/api/videos").json()] == [video.id]
    assert binh.patch(f"/api/scenes/{scene_ids(db, video)[0]}", json={"text": "Món mới"}).status_code == 200
    response = binh.post(f"/api/videos/{video.id}/render")
    assert response.status_code == 200 and response.json()["status"] == "queued"


# --- Autosave ---

def test_field_saves_never_overwrite_other_fields(an, binh, db, me, storage):
    video = make_video(db, storage, me)
    first, second = scene_ids(db, video)[:2]
    an.patch(f"/api/videos/{video.id}", json={"caption": "Caption của An"})
    binh.patch(f"/api/videos/{video.id}", json={"pinned_comment": "Ghim của Bình"})
    an.patch(f"/api/scenes/{first}", json={"text": "Chữ của An"})
    binh.patch(f"/api/scenes/{second}", json={"seconds": 5})
    binh.patch(f"/api/scenes/{first}", json={"keywords": ["cá cơm", " ", "cá"]})

    saved = an.get(f"/api/videos/{video.id}").json()
    assert (saved["caption"], saved["pinned_comment"]) == ("Caption của An", "Ghim của Bình")
    assert saved["scenes"][0]["text"] == "Chữ của An" and saved["scenes"][0]["keywords"] == ["cá cơm", "cá"]
    assert saved["scenes"][1]["seconds"] == 5


def test_post_fields_and_image_prompt_are_editable(an, db, me, storage):
    video = make_video(db, storage, me)
    body = {"caption": "Mới", "hashtags": ["#x", "#y"], "affiliates": ["A", "B"], "pinned_comment": "G",
            "music_suggestions": ["Windy Hill", "Nhạc 2"]}
    saved = an.patch(f"/api/videos/{video.id}", json=body).json()
    assert {name: saved[name] for name in body} == body
    scene = an.patch(f"/api/scenes/{scene_ids(db, video)[0]}", json={"image_prompt": "cá trên bàn gỗ"}).json()
    assert scene["scenes"][0]["image_prompt"] == "cá trên bàn gỗ"


def test_choosing_a_title_changes_only_the_title_scene_text(an, db, me, storage):
    video = make_video(db, storage, me)
    saved = an.patch(f"/api/scenes/{title_id(db, video)}", json={"text": "TIÊU ĐỀ 2 SỬA TIẾP"}).json()
    assert saved["title_scene"]["text"] == "TIÊU ĐỀ 2 SỬA TIẾP" and saved["title"] == "TIÊU ĐỀ 2 SỬA TIẾP"
    assert saved["title_options"] == ["5 MÓN GIÚP\n*XƯƠNG CHẮC KHỎE*", "TIÊU ĐỀ 2"]


def test_saving_into_a_deleted_scene_is_refused(an, binh, db, me, storage):
    video = make_video(db, storage, me)
    target = scene_ids(db, video)[2]
    assert binh.delete(f"/api/scenes/{target}").status_code == 200
    response = an.patch(f"/api/scenes/{target}", json={"text": "muộn"})
    assert (response.status_code, response.json()["message"]) == (404, "Cảnh này đã bị xóa")
    assert len(an.get(f"/api/videos/{video.id}").json()["scenes"]) == 4


def test_add_delete_and_reorder_scenes_with_the_last_order_winning(an, binh, db, me, storage):
    video = make_video(db, storage, me, scene_count=3)
    a, b, c = scene_ids(db, video)
    an.put(f"/api/videos/{video.id}/scene-order", json={"ids": [c, a, b]})
    added = binh.post(f"/api/videos/{video.id}/scenes").json()["scenes"][-1]
    assert (added["text"], added["seconds"], added["has_image"]) == ("", 4, False)
    # Bình's order was built before the new scene existed: the new one keeps its place at the end.
    final = binh.put(f"/api/videos/{video.id}/scene-order", json={"ids": [b, a, c]}).json()
    assert [scene["id"] for scene in final["scenes"]] == [b, a, c, added["id"]]
    assert an.delete(f"/api/scenes/{title_id(db, video)}").status_code == 409


# --- Locking and jobs ---

def test_an_active_job_locks_editing_deleting_and_a_second_render(an, db, me, storage):
    video = make_video(db, storage, me)
    assert an.post(f"/api/videos/{video.id}/render").status_code == 200

    save = an.patch(f"/api/scenes/{scene_ids(db, video)[0]}", json={"text": "B đang gõ"})
    assert (save.status_code, save.json()["message"]) == (409, "Video đang render, chưa lưu")
    assert an.patch(f"/api/videos/{video.id}", json={"caption": "x"}).status_code == 409
    assert an.post(f"/api/videos/{video.id}/scenes").status_code == 409
    assert an.delete(f"/api/videos/{video.id}").status_code == 409
    assert an.post(f"/api/videos/{video.id}/render").status_code == 409
    assert db.scalar(select(Scene.text).where(Scene.id == scene_ids(db, video)[0])) == SCENE_TEXT


@pytest.mark.parametrize("status", ["queued", "running"])
def test_every_change_is_refused_while_a_job_is_queued_or_running(an, db, me, storage, fakes, status):
    video = make_video(db, storage, me)
    first, second = scene_ids(db, video)[:2]
    add_job(db, video, me, status=status)
    photo = {"file": ("a.jpg", photo_bytes())}
    for response in (
        an.patch(f"/api/scenes/{first}", json={"text": "x"}),
        an.patch(f"/api/videos/{video.id}", json={"caption": "x"}),
        an.post(f"/api/videos/{video.id}/scenes"),
        an.delete(f"/api/scenes/{first}"),
        an.put(f"/api/videos/{video.id}/scene-order", json={"ids": [second, first]}),
        an.post(f"/api/scenes/{first}/image", files=photo),
        an.post(f"/api/scenes/{first}/find-image"),
        an.delete(f"/api/videos/{video.id}"),
    ):
        assert response.status_code == 409 and response.json()["code"] == "video_locked", response.request.url
    assert scene_ids(db, video)[:2] == [first, second]


def test_a_job_starting_during_the_pixabay_search_blocks_the_photo_save(an, db, me, storage, fakes, monkeypatch):
    from reels_api import routes_videos

    video = make_video(db, storage, me)
    target = scene_ids(db, video)[0]
    before = db.scalar(select(Scene.image_key).where(Scene.id == target))
    real_find = routes_videos.Pixabay.find_photo

    def find_then_render(self, *args, **kwargs):
        photo = real_find(self, *args, **kwargs)
        add_job(db, video, me, status="running")
        return photo

    monkeypatch.setattr(routes_videos.Pixabay, "find_photo", find_then_render)
    response = an.post(f"/api/scenes/{target}/find-image")
    assert (response.status_code, response.json()["message"]) == (409, "Video đang render, chưa lưu")
    assert db.scalar(select(Scene.image_key).where(Scene.id == target)) == before


def test_render_is_refused_while_a_blocking_problem_remains(an, db, me, storage):
    video = make_video(db, storage, me)
    first = scene_ids(db, video)[0]
    an.patch(f"/api/scenes/{first}", json={"text": "Cá *nhỏ"})
    payload = an.get(f"/api/videos/{video.id}").json()
    assert payload["can_render"] is False
    assert payload["scenes"][0]["blocking"] == ["Chữ sai cách đánh dấu: dấu * không đóng cặp"]
    response = an.post(f"/api/videos/{video.id}/render")
    assert (response.status_code, response.json()["code"]) == (409, "render_blocked")
    an.patch(f"/api/scenes/{first}", json={"text": "Cá *nhỏ*"})
    assert an.get(f"/api/videos/{video.id}").json()["can_render"] is True


def test_cancelling_a_script_job_leaves_an_empty_draft_that_can_be_written_again(an, db):
    video = an.post("/api/videos", json={"topic": "tim mạch"}).json()
    cancelled = an.post(f"/api/jobs/{video['active_job']['id']}/cancel").json()
    assert (cancelled["status"], cancelled["locked"], cancelled["has_script"]) == ("draft", False, False)
    assert db.get(Job, video["active_job"]["id"]).status == "cancelled"
    again = an.post(f"/api/videos/{video['id']}/script").json()
    assert again["active_job"]["kind"] == "script"


def test_cancelling_a_render_keeps_the_old_mp4(an, db, me, storage):
    video = make_video(db, storage, me)
    video.mp4_key = f"videos/{video.id}/video-old.mp4"
    storage.save_bytes(video.mp4_key, b"old mp4")
    db.commit()
    job = an.post(f"/api/videos/{video.id}/render").json()["active_job"]
    after = an.post(f"/api/jobs/{job['id']}/cancel").json()
    assert after["status"] == "done" and after["mp4"] is not None and after["rerender_failed"] is False
    assert an.get(f"/api/videos/{video.id}/video.mp4").content == b"old mp4"
    assert an.post(f"/api/jobs/{job['id']}/cancel").status_code == 409


def test_a_running_job_cannot_be_cancelled(an, db, me, storage):
    video = make_video(db, storage, me)
    job = add_job(db, video, me, status="running")
    assert an.post(f"/api/jobs/{job.id}/cancel").status_code == 409


def test_retry_creates_a_new_job_and_keeps_the_failed_one(an, db, me, storage):
    video = make_video(db, storage, me)
    failed = add_job(db, video, me, kind="script", status="failed", error="Claude hết hạn mức")
    payload = an.get(f"/api/videos/{video.id}").json()
    assert (payload["status"], payload["failed_job"]["error"]) == ("failed", "Claude hết hạn mức")
    retried = an.post(f"/api/jobs/{failed.id}/retry").json()
    assert retried["active_job"]["kind"] == "script" and retried["active_job"]["id"] != failed.id
    jobs = db.scalars(select(Job).where(Job.video_id == video.id).order_by(Job.id)).all()
    assert [(job.status, job.retry_of_id) for job in jobs] == [("failed", None), ("queued", failed.id)]


def test_a_failed_rerender_keeps_done_with_a_label(an, db, me, storage):
    video = make_video(db, storage, me)
    video.mp4_key = f"videos/{video.id}/video-old.mp4"
    storage.save_bytes(video.mp4_key, b"old")
    db.commit()
    add_job(db, video, me, status="failed", error="FFmpeg lỗi khi render video", error_detail="stderr tail")
    payload = an.get(f"/api/videos/{video.id}").json()
    assert (payload["status"], payload["rerender_failed"]) == ("done", True)
    assert payload["failed_job"]["error_detail"] == "stderr tail"
    assert an.get(f"/api/videos/{video.id}/video.mp4").status_code == 200


@pytest.mark.parametrize(
    ("change", "outdated"),
    [
        (("scene", {"text": "Chữ khác"}), True),
        (("scene", {"seconds": 5}), True),
        (("title", {"text": "TIÊU ĐỀ KHÁC"}), True),
        (("order", None), True),
        (("add", None), True),
        (("delete", None), True),
        (("image", None), True),
        (("video", {"caption": "khác"}), False),
        (("video", {"hashtags": ["#khac"], "affiliates": ["x"], "pinned_comment": "y", "music_suggestions": ["z"]}),
         False),
        (("scene", {"keywords": ["khác"], "image_prompt": "khác"}), False),
    ],
)
def test_mp4_outdated_label_follows_only_changes_that_alter_the_mp4(an, db, me, storage, change, outdated):
    from reels_api.videos import render_signature, split_scenes

    video = make_video(db, storage, me)
    title, scenes = split_scenes(db, video)
    video.mp4_key, video.rendered_signature = f"videos/{video.id}/video-x.mp4", render_signature(title, scenes)
    db.commit()
    assert an.get(f"/api/videos/{video.id}").json()["mp4_outdated"] is False
    ids = scene_ids(db, video)
    kind, body = change
    if kind == "scene":
        an.patch(f"/api/scenes/{ids[0]}", json=body)
    elif kind == "title":
        an.patch(f"/api/scenes/{title_id(db, video)}", json=body)
    elif kind == "video":
        an.patch(f"/api/videos/{video.id}", json=body)
    elif kind == "order":
        an.put(f"/api/videos/{video.id}/scene-order", json={"ids": list(reversed(ids))})
    elif kind == "add":
        an.post(f"/api/videos/{video.id}/scenes")
    elif kind == "delete":
        an.delete(f"/api/scenes/{ids[0]}")
    elif kind == "image":
        an.post(f"/api/scenes/{ids[0]}/image", files={"file": ("a.png", photo_bytes(kind="PNG"), "image/png")})
    assert an.get(f"/api/videos/{video.id}").json()["mp4_outdated"] is outdated
    assert an.get("/api/videos").json()[0]["mp4_outdated"] is outdated


def test_deleting_a_video_removes_rows_and_every_file(an, db, me, storage):
    video = make_video(db, storage, me)
    video.mp4_key = f"videos/{video.id}/video-1.mp4"
    storage.save_bytes(video.mp4_key, b"mp4")
    db.commit()
    add_job(db, video, me, status="done")
    folder = storage.path(f"videos/{video.id}")
    assert any(folder.iterdir())
    assert an.delete(f"/api/videos/{video.id}").status_code == 200
    assert db.get(Video, video.id) is None
    assert db.scalars(select(Scene).where(Scene.video_id == video.id)).all() == []
    assert db.scalars(select(Job).where(Job.video_id == video.id)).all() == []
    assert not folder.exists()


# --- Photos, previews, thumbnail ---

def test_upload_accepts_jpg_png_webp_and_refuses_other_types_and_large_files(an, db, me, storage, monkeypatch):
    video = make_video(db, storage, me, images=False)
    target = scene_ids(db, video)[0]
    for kind, name in (("JPEG", "a.jpg"), ("PNG", "a.png"), ("WEBP", "a.webp")):
        saved = an.post(f"/api/scenes/{target}/image", files={"file": (name, photo_bytes(kind=kind))})
        assert saved.status_code == 200 and saved.json()["scenes"][0]["has_image"] is True
    assert len(list(storage.path(f"videos/{video.id}").iterdir())) == 1, "the replaced photos are deleted"

    gif = io.BytesIO()
    Image.new("RGB", (10, 10)).save(gif, "GIF")
    refused = an.post(f"/api/scenes/{target}/image", files={"file": ("a.jpg", gif.getvalue())})
    assert (refused.status_code, refused.json()["message"]) == (415, "Ảnh phải là JPG, PNG hoặc WebP và không bị hỏng")

    from reels_api import routes_videos
    monkeypatch.setattr(routes_videos, "MAX_IMAGE_BYTES", 1000)
    big = an.post(f"/api/scenes/{target}/image", files={"file": ("a.jpg", photo_bytes())})
    assert (big.status_code, big.json()["message"]) == (413, "Ảnh quá 15 MB, hãy chọn ảnh nhỏ hơn")


def test_thumbnail_appears_with_the_title_photo_and_follows_its_text_and_photo(an, db, me, storage):
    video = make_video(db, storage, me, images=False)
    title = title_id(db, video)
    assert an.get(f"/api/videos/{video.id}").json()["thumbnail_url"] is None

    from reels_api.frames import thumbnail_bytes

    def served_matches(payload, text):
        """The served thumbnail is drawn from the title scene's current photo and text."""
        photo = storage.path(db.scalar(select(Scene.image_key).where(Scene.id == title)))
        assert an.get(payload["thumbnail_url"]).content == thumbnail_bytes(photo, text)

    first = an.post(f"/api/scenes/{title}/image", files={"file": ("t.jpg", photo_bytes((10, 200, 10)))}).json()
    assert first["status"] == "draft" and first["thumbnail_url"]
    image = Image.open(io.BytesIO(an.get(first["thumbnail_url"]).content)).convert("RGB")
    assert image.size == (540, 960)
    assert image.getpixel((10, 10))[1] > 150, "the green title photo"
    served_matches(first, "5 MÓN GIÚP\n*XƯƠNG CHẮC KHỎE*")
    before = an.get(first["thumbnail_url"]).content

    retitled = an.patch(f"/api/scenes/{title}", json={"text": "TIÊU ĐỀ MỚI"}).json()
    assert an.get(retitled["thumbnail_url"]).content != before
    served_matches(retitled, "TIÊU ĐỀ MỚI")
    rephoto = an.post(f"/api/scenes/{title}/image", files={"file": ("t.jpg", photo_bytes((200, 10, 10)))}).json()
    red = Image.open(io.BytesIO(an.get(rephoto["thumbnail_url"]).content)).convert("RGB")
    assert red.getpixel((10, 10))[0] > 150, "the new red title photo"
    served_matches(rephoto, "TIÊU ĐỀ MỚI")
    assert len([p for p in storage.path(f"videos/{video.id}").iterdir() if p.name.startswith("thumb-")]) == 1


def test_preview_uses_the_photo_and_the_renderers_text_box(an, db, me, storage):
    from PIL import ImageChops, ImageOps, ImageStat

    from reels_api.frames import _yuv420
    from reels_render.markup import parse_scene_text
    from reels_render.textbox import SCENE_STYLE, layout_text, render_box, scene_box_position

    video = make_video(db, storage, me)
    scene = an.get(f"/api/videos/{video.id}").json()["scenes"][0]
    preview = Image.open(io.BytesIO(an.get(scene["preview_url"]).content)).convert("RGB")
    assert preview.size == (1080, 1920)

    # The same calls render_video makes for a content scene, on the photo stored for this scene.
    layout = layout_text(parse_scene_text(SCENE_TEXT), SCENE_STYLE)
    box = render_box(layout)
    photo_key = db.scalar(select(Scene.image_key).where(Scene.id == scene["id"]))
    expected = ImageOps.fit(Image.open(storage.path(photo_key)).convert("RGB"), (1080, 1920),
                            Image.Resampling.BICUBIC)
    expected.paste(box, scene_box_position(layout.width, layout.height), box)
    difference = sum(ImageStat.Stat(ImageChops.difference(preview, _yuv420(expected))).mean) / 3
    assert difference < 1, "only JPEG noise may differ"


# --- "Tìm lại ảnh" ---

def test_find_other_photo_assigns_a_different_pixabay_photo(an, db, me, storage, fakes):
    video = make_video(db, storage, me, images=False)
    target = scene_ids(db, video)[0]
    an.patch(f"/api/scenes/{target}", json={"keywords": ["cá cơm"]})
    fakes.pixabay_results["cá cơm"] = ["p1", "p2", "p3"]
    sources = []
    for _ in range(4):
        assert an.post(f"/api/scenes/{target}/find-image").status_code == 200
        sources.append(db.scalar(select(Scene.image_source).where(Scene.id == target)))
    # Each press moves on through the results instead of bouncing between two photos.
    assert sources == [fakes.image_url(name) for name in ("p1", "p2", "p3", "p1")]
    assert len(list(storage.path(f"videos/{video.id}").iterdir())) == 1


def test_find_other_photo_tries_the_next_keyword_then_reports_none(an, db, me, storage, fakes):
    video = make_video(db, storage, me, images=False)
    target = scene_ids(db, video)[0]
    an.patch(f"/api/scenes/{target}", json={"keywords": ["một", "hai"]})
    fakes.pixabay_results.update({"một": ["only"], "hai": ["other"]})
    an.post(f"/api/scenes/{target}/find-image")
    assert db.scalar(select(Scene.image_source).where(Scene.id == target)) == fakes.image_url("only")
    an.post(f"/api/scenes/{target}/find-image")
    assert db.scalar(select(Scene.image_source).where(Scene.id == target)) == fakes.image_url("other")

    fakes.pixabay_results.update({"một": ["other"], "hai": ["other"]})
    an.patch(f"/api/scenes/{target}", json={"keywords": ["ba"]})
    fakes.pixabay_results["ba"] = ["other"]
    none = an.post(f"/api/scenes/{target}/find-image")
    assert (none.status_code, none.json()["message"]) == (404, "Không tìm thấy ảnh khác, hãy đổi từ khóa")
    assert db.scalar(select(Scene.image_source).where(Scene.id == target)) == fakes.image_url("other")


def test_find_other_photo_needs_keywords(an, db, me, storage, fakes):
    video = make_video(db, storage, me)
    target = scene_ids(db, video)[0]
    an.patch(f"/api/scenes/{target}", json={"keywords": []})
    assert an.post(f"/api/scenes/{target}/find-image").json()["message"] == "Hãy nhập từ khóa tìm ảnh trước"


@pytest.mark.parametrize(("setup", "message"), [
    ("bad_key", "Key Pixabay không hợp lệ"),
    ("error500", "Pixabay đang lỗi (HTTP 500)"),
])
def test_pixabay_failures_keep_the_old_photo(an, db, me, storage, fakes, monkeypatch, setup, message):
    video = make_video(db, storage, me)
    target = scene_ids(db, video)[0]
    before = db.scalar(select(Scene.image_key).where(Scene.id == target))
    if setup == "bad_key":
        monkeypatch.setenv("PIXABAY_API_KEY", "wrong")
    else:
        fakes.pixabay_mode = setup
    response = an.post(f"/api/scenes/{target}/find-image")
    assert response.status_code == 502 and message in response.json()["message"]
    assert db.scalar(select(Scene.image_key).where(Scene.id == target)) == before


def test_a_slow_pixabay_is_given_up_after_about_ten_seconds(an, db, me, storage, fakes, monkeypatch):
    from reels_api import routes_videos
    monkeypatch.setattr(routes_videos, "FIND_IMAGE_SECONDS", 1.5)
    video = make_video(db, storage, me)
    target = scene_ids(db, video)[0]
    fakes.pixabay_mode = "hang"
    started = time.monotonic()
    response = an.post(f"/api/scenes/{target}/find-image")
    assert response.status_code == 502 and "không phản hồi kịp" in response.json()["message"]
    assert time.monotonic() - started < 5
