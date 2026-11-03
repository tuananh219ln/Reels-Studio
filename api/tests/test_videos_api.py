import io
import time

import pytest
from conftest import (
    SCENE_TEXT,
    client_for,
    clip_bytes,
    first_topic,
    login,
    make_user,
    make_video,
    needs_ffmpeg,
    photo_bytes,
)
from PIL import Image
from sqlalchemy import select

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
    return db.scalars(
        select(Scene.id).where(Scene.video_id == video.id, Scene.is_title.is_(False)).order_by(Scene.position)
    ).all()


def title_id(db, video):
    return db.scalar(select(Scene.id).where(Scene.video_id == video.id, Scene.is_title))


def add_job(db, video, user, kind="render", status="queued", **fields):
    job = Job(video_id=video.id, kind=kind, status=status, created_by_id=user.id, **fields)
    db.add(job)
    db.commit()
    return job


# --- Creating and listing ---


def test_new_video_queues_a_script_job_and_is_locked(an, db):
    group = first_topic(db).id
    response = an.post("/api/videos", json={"topic": "  thực phẩm tốt cho  xương khớp ", "knowledge_topic_id": group})
    assert response.status_code == 201
    video = response.json()
    assert video["topic"] == "thực phẩm tốt cho xương khớp"
    assert (video["status"], video["status_label"], video["locked"]) == ("queued", "Chờ thứ 1", True)
    assert video["active_job"]["kind"] == "script"
    assert video["created_by"] == "Nguyễn Văn An"
    assert video["knowledge_topic"] == "Sức khỏe"
    assert an.post("/api/videos", json={"topic": "   "}).json()["message"] == "Hãy nhập chủ đề"
    assert an.post("/api/videos", json={"topic": "tim"}).json()["message"] == "Hãy chọn nhóm chủ đề"


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
    body = {
        "caption": "Mới",
        "hashtags": ["#x", "#y"],
        "affiliates": ["A", "B"],
        "pinned_comment": "G",
        "music_suggestions": ["Windy Hill", "Nhạc 2"],
    }
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
    video = an.post("/api/videos", json={"topic": "tim mạch", "knowledge_topic_id": first_topic(db).id}).json()
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
        (
            ("video", {"hashtags": ["#khac"], "affiliates": ["x"], "pinned_comment": "y", "music_suggestions": ["z"]}),
            False,
        ),
        (("scene", {"keywords": ["khác"], "image_prompt": "khác"}), False),
    ],
)
def test_mp4_outdated_label_follows_only_changes_that_alter_the_mp4(an, db, me, storage, change, outdated):
    from reels_api.videos import render_signature, split_scenes

    video = make_video(db, storage, me)
    title, scenes = split_scenes(db, video)
    video.mp4_key, video.rendered_signature = f"videos/{video.id}/video-x.mp4", render_signature(video, title, scenes)
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


@pytest.mark.parametrize("source", ["https://cdn.pixabay.com/a.jpg", "ai:gemini-2.5-flash-image", "upload"])
def test_a_cropped_photo_replaces_the_old_one_and_keeps_where_it_came_from(an, db, me, storage, source):
    video = make_video(db, storage, me)
    target = scene_ids(db, video)[0]
    scene = db.get(Scene, target)
    scene.image_source = source
    db.commit()
    old_key = scene.image_key
    cropped = an.post(f"/api/scenes/{target}/image/crop", files={"file": ("crop.jpg", photo_bytes(size=(1080, 1920)))})
    assert cropped.status_code == 200 and cropped.json()["scenes"][0]["has_image"] is True
    db.expire_all()
    scene = db.get(Scene, target)
    # An AI photo stays labelled as AI after a crop; a stock photo keeps its credit.
    assert scene.image_source == source
    assert scene.image_key != old_key and not storage.path(old_key).exists()


def test_a_crop_needs_a_photo_a_valid_image_and_an_unlocked_video(an, db, me, storage):
    video = make_video(db, storage, me, images=False)
    target = scene_ids(db, video)[0]
    refused = an.post(f"/api/scenes/{target}/image/crop", files={"file": ("crop.jpg", photo_bytes())})
    assert (refused.status_code, refused.json()["message"]) == (409, "Cảnh này chưa có ảnh để chỉnh khung")

    an.post(f"/api/scenes/{target}/image", files={"file": ("a.jpg", photo_bytes())})
    gif = io.BytesIO()
    Image.new("RGB", (10, 10)).save(gif, "GIF")
    bad = an.post(f"/api/scenes/{target}/image/crop", files={"file": ("crop.jpg", gif.getvalue())})
    assert bad.status_code == 415

    add_job(db, video, me)
    locked = an.post(f"/api/scenes/{target}/image/crop", files={"file": ("crop.jpg", photo_bytes())})
    assert locked.status_code == 409


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


@pytest.mark.parametrize("text", ["", "   "])
def test_empty_text_leaves_the_preview_and_thumbnail_without_a_box_and_can_render(an, db, me, storage, text):
    def has_yellow_box(url):
        image = Image.open(io.BytesIO(an.get(url).content)).convert("RGB")
        column = [image.getpixel((image.width // 2, y)) for y in range(0, image.height, 8)]
        return any(r > 200 and g > 170 and b < 100 for r, g, b in column)

    video = make_video(db, storage, me)
    title = title_id(db, video)
    shown = an.get(f"/api/videos/{video.id}").json()
    assert has_yellow_box(shown["title_scene"]["preview_url"])

    empty = an.patch(f"/api/scenes/{title}", json={"text": text}).json()
    assert empty["can_render"] is True
    assert empty["title_scene"]["text_problem"] is None and empty["title_scene"]["blocking"] == []
    assert empty["title"] == "", "the page falls back to the topic"
    assert not has_yellow_box(empty["title_scene"]["preview_url"])
    assert not has_yellow_box(empty["thumbnail_url"])


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
    expected = ImageOps.fit(Image.open(storage.path(photo_key)).convert("RGB"), (1080, 1920), Image.Resampling.BICUBIC)
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


def test_find_other_photo_searches_the_english_keywords_when_the_script_wrote_them(an, db, me, storage, fakes):
    video = make_video(db, storage, me, images=False)
    target = scene_ids(db, video)[0]
    an.patch(f"/api/scenes/{target}", json={"keywords": ["cá cơm"], "keywords_en": ["fried fish"]})
    fakes.pixabay_results["fried fish"] = ["en1"]
    assert an.post(f"/api/scenes/{target}/find-image").status_code == 200
    # Pixabay indexes in English: only the English list was searched, never the Vietnamese one.
    assert fakes.pixabay_queries == ["fried fish"]
    assert db.scalar(select(Scene.image_source).where(Scene.id == target)) == fakes.image_url("en1")


def test_find_other_photo_from_pexels_walks_the_english_keywords(an, db, me, storage, fakes):
    video = make_video(db, storage, me, images=False)
    target = scene_ids(db, video)[0]
    an.patch(f"/api/scenes/{target}", json={"keywords": ["cá cơm"], "keywords_en": ["fried fish"]})
    fakes.pexels_results["fried fish"] = ["px1", "px2"]
    sources = []
    for _ in range(3):
        assert an.post(f"/api/scenes/{target}/find-image", params={"source": "pexels"}).status_code == 200
        sources.append(db.scalar(select(Scene.image_source).where(Scene.id == target)))
    assert sources == [fakes.image_url(name) for name in ("px1", "px2", "px1")]
    assert set(fakes.pexels_queries) == {"fried fish"} and fakes.pixabay_queries == []


def test_find_other_photo_from_openverse_searches_the_vietnamese_keywords(an, db, me, storage, fakes):
    video = make_video(db, storage, me, images=False)
    target = scene_ids(db, video)[0]
    an.patch(f"/api/scenes/{target}", json={"keywords": ["cá kho"], "keywords_en": ["braised fish"]})
    fakes.openverse_results["cá kho"] = [{"name": "ov1", "license": "cc0"}, {"name": "ov2", "license": "pdm"}]
    an.post(f"/api/scenes/{target}/find-image", params={"source": "openverse"})
    assert db.scalar(select(Scene.image_source).where(Scene.id == target)) == fakes.image_url("ov1")
    an.post(f"/api/scenes/{target}/find-image", params={"source": "openverse"})
    assert db.scalar(select(Scene.image_source).where(Scene.id == target)) == fakes.image_url("ov2")
    assert set(fakes.openverse_queries) == {"cá kho"}


def test_find_other_photo_with_an_unknown_source_is_a_clean_error(an, db, me, storage, fakes):
    video = make_video(db, storage, me)
    target = scene_ids(db, video)[0]
    response = an.post(f"/api/scenes/{target}/find-image", params={"source": "flickr"})
    assert (response.status_code, response.json()["message"]) == (422, "Nguồn ảnh không hợp lệ")


@pytest.mark.parametrize(
    ("setup", "message"),
    [
        ("bad_key", "Key Pixabay không hợp lệ"),
        ("error500", "Pixabay đang lỗi (HTTP 500)"),
    ],
)
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


# --- Stock picker sources ---


def test_stock_sources_list_what_is_configured(an, fakes):
    sources = an.get("/api/stock/sources").json()
    assert [(item["id"], item["available"]) for item in sources] == [
        ("pixabay", True),
        ("pexels", True),
        ("openverse", True),
    ]


def test_stock_sources_hide_pexels_without_a_key(an, fakes, monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "")
    sources = {item["id"]: item["available"] for item in an.get("/api/stock/sources").json()}
    assert sources == {"pixabay": True, "pexels": False, "openverse": True}


def test_pixabay_through_the_stock_endpoints(an, db, me, storage, fakes):
    video = make_video(db, storage, me, images=False)
    target = scene_ids(db, video)[0]
    fakes.pixabay_results["cá cơm"] = ["p1"]
    found = an.get(f"/api/scenes/{target}/stock", params={"q": "cá cơm", "source": "pixabay"})
    assert [hit["url"] for hit in found.json()["hits"]] == [fakes.image_url("p1")]
    saved = an.post(
        f"/api/scenes/{target}/stock",
        json={"source": "pixabay", "keyword": "cá cơm", "url": fakes.image_url("p1")},
    )
    assert saved.status_code == 200
    assert db.scalar(select(Scene.image_source).where(Scene.id == target)) == fakes.image_url("p1")


def test_choosing_a_pexels_photo_stores_it(an, db, me, storage, fakes):
    video = make_video(db, storage, me, images=False)
    target = scene_ids(db, video)[0]
    fakes.pexels_results["cá cơm"] = ["px1", "px2"]
    found = an.get(f"/api/scenes/{target}/stock", params={"q": "cá cơm", "source": "pexels"})
    assert found.status_code == 200
    hits = found.json()["hits"]
    assert [hit["url"] for hit in hits] == [fakes.image_url("px1"), fakes.image_url("px2")]
    saved = an.post(
        f"/api/scenes/{target}/stock",
        json={"source": "pexels", "keyword": "cá cơm", "url": hits[1]["url"]},
    )
    assert saved.status_code == 200
    assert db.scalar(select(Scene.image_source).where(Scene.id == target)) == fakes.image_url("px2")


def test_choosing_a_photo_that_is_not_a_result_is_refused(an, db, me, storage, fakes):
    video = make_video(db, storage, me, images=False)
    target = scene_ids(db, video)[0]
    refused = an.post(
        f"/api/scenes/{target}/stock",
        json={"source": "pexels", "keyword": "cá cơm", "url": "https://images.pexels.com/photos/1/x.jpg"},
    )
    assert refused.status_code == 422 and "không có trong kết quả tìm" in refused.json()["message"]


def test_openverse_only_offers_public_domain_works(an, db, me, storage, fakes):
    video = make_video(db, storage, me, images=False)
    target = scene_ids(db, video)[0]
    fakes.openverse_results["cá kho"] = [
        {"name": "free", "license": "cc0"},
        {"name": "marked", "license": "pdm"},
        {"name": "credited", "license": "by"},
        {"name": "noncommercial", "license": "by-nc"},
    ]
    found = an.get(f"/api/scenes/{target}/stock", params={"q": "cá kho", "source": "openverse"})
    assert [hit["url"] for hit in found.json()["hits"]] == [fakes.image_url("free"), fakes.image_url("marked")]
    saved = an.post(
        f"/api/scenes/{target}/stock",
        json={"source": "openverse", "keyword": "cá kho", "url": fakes.image_url("free")},
    )
    assert saved.status_code == 200
    assert db.scalar(select(Scene.image_source).where(Scene.id == target)) == fakes.image_url("free")


def test_stock_search_with_an_unknown_source_is_a_clean_error(an, db, me, storage, fakes):
    video = make_video(db, storage, me, images=False)
    target = scene_ids(db, video)[0]
    response = an.get(f"/api/scenes/{target}/stock", params={"q": "cá", "source": "flickr"})
    assert response.status_code == 422 and response.json()["message"] == "Nguồn ảnh không hợp lệ"


def test_openverse_searches_carry_the_registered_token_and_it_is_cached(an, db, me, storage, fakes):
    video = make_video(db, storage, me, images=False)
    target = scene_ids(db, video)[0]
    found = an.get(f"/api/scenes/{target}/stock", params={"q": "cá kho", "source": "openverse"})
    assert found.status_code == 200
    assert fakes.openverse_authorized == [True]
    saved = an.post(
        f"/api/scenes/{target}/stock",
        json={"source": "openverse", "keyword": "cá kho", "url": found.json()["hits"][0]["url"]},
    )
    assert saved.status_code == 200
    # Choosing searches again under the same token; no second token was asked for.
    assert fakes.openverse_authorized == [True, True]
    assert fakes.openverse_token_requests == 1


def test_openverse_falls_back_to_anonymous_when_the_credentials_are_wrong(an, db, me, storage, fakes, monkeypatch):
    monkeypatch.setenv("OPENVERSE_CLIENT_SECRET", "wrong")
    video = make_video(db, storage, me, images=False)
    target = scene_ids(db, video)[0]
    found = an.get(f"/api/scenes/{target}/stock", params={"q": "cá kho", "source": "openverse"})
    assert found.status_code == 200 and found.json()["hits"]
    assert fakes.openverse_authorized == [False]


# --- Scene video clips ---


def test_a_file_that_is_not_a_video_container_is_refused(an, db, me, storage):
    video = make_video(db, storage, me)
    target = scene_ids(db, video)[0]
    refused = an.post(f"/api/scenes/{target}/video", files={"file": ("a.mp4", b"#EXTM3U\nfile:///etc/passwd\n")})
    assert (refused.status_code, refused.json()["code"]) == (415, "invalid_video")
    assert an.get(f"/api/videos/{video.id}").json()["scenes"][0]["has_image"] is True, "the photo is kept"


def test_a_clip_larger_than_the_limit_is_refused(an, db, me, storage, monkeypatch):
    from reels_api import clips

    monkeypatch.setattr(clips, "MAX_CLIP_BYTES", 1000)
    video = make_video(db, storage, me)
    big = an.post(f"/api/scenes/{scene_ids(db, video)[0]}/video", files={"file": ("a.mp4", bytes(5000))})
    assert (big.status_code, big.json()["message"]) == (
        413,
        "Video quá 50 MB, hãy chọn video ngắn hơn hoặc nén nhỏ lại",
    )


def test_video_start_needs_a_clip(an, db, me, storage):
    video = make_video(db, storage, me)
    response = an.patch(f"/api/scenes/{scene_ids(db, video)[0]}", json={"video_start": 1})
    assert (response.status_code, response.json()["message"]) == (422, "Cảnh này chưa có video")


@needs_ffmpeg
def test_a_clip_replaces_the_photo_sets_the_length_and_a_photo_replaces_it_back(an, db, me, storage, tmp_path):
    video = make_video(db, storage, me)
    target = scene_ids(db, video)[0]
    photo_key = db.scalar(select(Scene.image_key).where(Scene.id == target))

    saved = an.post(f"/api/scenes/{target}/video", files={"file": ("vuon.mov", clip_bytes(tmp_path, seconds=2.5))})
    assert saved.status_code == 200, saved.json()
    scene = saved.json()["scenes"][0]
    assert (scene["has_image"], scene["video"]["start"]) == (False, 0)
    assert scene["video"]["seconds"] == pytest.approx(2.5, abs=0.1)
    # The clip's length minus 0.2 s for each crossfade around a content scene, rounded down to tenths.
    assert scene["video"]["seconds"] - 0.5 < scene["seconds"] <= scene["video"]["seconds"] - 0.4
    assert scene["warnings"] == []
    assert not storage.exists(photo_key), "the replaced photo is deleted"
    assert an.get(scene["video"]["url"]).headers["content-type"] == "video/mp4"
    preview = Image.open(io.BytesIO(an.get(scene["preview_url"]).content))
    assert preview.size == (1080, 1920)

    clip_key = db.scalar(select(Scene.video_key).where(Scene.id == target))
    back = an.post(f"/api/scenes/{target}/image", files={"file": ("a.jpg", photo_bytes())}).json()["scenes"][0]
    assert back["has_image"] is True and back["video"] is None
    assert not storage.exists(clip_key), "the replaced clip is deleted"


@needs_ffmpeg
def test_start_time_is_checked_and_a_short_clip_only_warns(an, db, me, storage, tmp_path):
    video = make_video(db, storage, me)
    target = scene_ids(db, video)[0]
    an.post(f"/api/scenes/{target}/video", files={"file": ("vuon.mp4", clip_bytes(tmp_path, seconds=3))})

    too_late = an.patch(f"/api/scenes/{target}", json={"video_start": 2.5})
    assert too_late.status_code == 422 and too_late.json()["message"].startswith("Giây bắt đầu phải từ 0 đến 2")
    saved = an.patch(f"/api/scenes/{target}", json={"video_start": 1.5}).json()
    scene = saved["scenes"][0]
    assert scene["video"]["start"] == 1.5
    # 3 s of scene, 1.5 s of clip left: the last frame holds, which is allowed.
    assert "Video ngắn hơn cảnh, khung cuối sẽ đứng yên" in scene["warnings"]
    assert scene["blocking"] == [] and saved["can_render"] is True


def test_video_speed_needs_a_clip(an, db, me, storage):
    video = make_video(db, storage, me)
    response = an.patch(f"/api/scenes/{scene_ids(db, video)[0]}", json={"video_speed": 2})
    assert (response.status_code, response.json()["message"]) == (422, "Cảnh này chưa có video")


@needs_ffmpeg
def test_a_clip_speed_is_checked_warns_on_a_short_clip_and_goes_with_the_clip(an, db, me, storage, tmp_path):
    video = make_video(db, storage, me)
    target = scene_ids(db, video)[0]
    clip = clip_bytes(tmp_path, seconds=3)
    first = an.post(f"/api/scenes/{target}/video", files={"file": ("vuon.mp4", clip)}).json()["scenes"][0]
    assert first["video"]["speed"] == 1

    for speed in (0.4, 2.1):
        refused = an.patch(f"/api/scenes/{target}", json={"video_speed": speed})
        assert (refused.status_code, refused.json()["message"]) == (422, "Tốc độ clip phải từ 0,5 đến 2")

    saved = an.patch(f"/api/scenes/{target}", json={"video_speed": 2}).json()
    scene = saved["scenes"][0]
    assert (scene["video"]["speed"], scene["seconds"]) == (2, first["seconds"]), "the scene keeps its seconds"
    assert "Ở tốc độ 2× video ngắn hơn cảnh, khung cuối sẽ đứng yên" in scene["warnings"]
    assert scene["blocking"] == [] and saved["can_render"] is True

    again = an.post(f"/api/scenes/{target}/video", files={"file": ("vuon.mp4", clip)}).json()["scenes"][0]
    assert again["video"]["speed"] == 1, "a new clip starts at 1×"


@needs_ffmpeg
def test_title_clip_draws_the_thumbnail_from_its_start_frame(an, db, me, storage, tmp_path):
    video = make_video(db, storage, me)
    title = title_id(db, video)
    first = an.post(f"/api/scenes/{title}/video", files={"file": ("t.mp4", clip_bytes(tmp_path, seconds=3))}).json()
    moved = an.patch(f"/api/scenes/{title}", json={"video_start": 1.5}).json()
    assert first["thumbnail_url"] and moved["thumbnail_url"] != first["thumbnail_url"]
    assert moved["title_scene"]["preview_url"] != first["title_scene"]["preview_url"]

    clip_key = db.scalar(select(Scene.video_key).where(Scene.id == title))
    removed = an.delete(f"/api/scenes/{title}/video").json()
    assert removed["thumbnail_url"] is None and removed["title_scene"]["video"] is None
    assert not storage.exists(clip_key), "the removed clip is deleted"
    assert "Cảnh chưa có ảnh" in removed["title_scene"]["blocking"]


@needs_ffmpeg
def test_changing_the_clip_its_start_or_its_speed_marks_the_mp4_outdated(an, db, me, storage, tmp_path):
    video = make_video(db, storage, me)
    target = scene_ids(db, video)[0]
    an.post(f"/api/scenes/{target}/video", files={"file": ("vuon.mp4", clip_bytes(tmp_path, seconds=3))})
    from reels_api.videos import render_signature, split_scenes

    row = db.get(Video, video.id)
    row.mp4_key, row.rendered_signature = "videos/x/video.mp4", render_signature(row, *split_scenes(db, row))
    db.commit()
    assert an.get(f"/api/videos/{video.id}").json()["mp4_outdated"] is False
    assert an.patch(f"/api/scenes/{target}", json={"video_speed": 1}).json()["mp4_outdated"] is False
    assert an.patch(f"/api/scenes/{target}", json={"video_speed": 1.5}).json()["mp4_outdated"] is True
    assert an.patch(f"/api/scenes/{target}", json={"video_speed": 1}).json()["mp4_outdated"] is False
    assert an.patch(f"/api/scenes/{target}", json={"video_start": 1}).json()["mp4_outdated"] is True


def test_replacing_a_clip_with_another_of_the_same_length_changes_the_fingerprint():
    from reels_api.videos import render_signature

    video = Video(music_key=None, music_volume=25, voice_enabled=False)
    scene = Scene(
        is_title=False,
        text="Rau dền",
        seconds=10,
        image_key=None,
        video_key="videos/1/clip-a.mp4",
        video_start=0.0,
        voice_text="",
    )
    before = render_signature(video, None, [scene])
    scene.video_key = "videos/1/clip-b.mp4"
    assert render_signature(video, None, [scene]) != before


@needs_ffmpeg
def test_a_long_clip_sets_at_most_10_seconds_and_deleting_the_scene_deletes_it(an, db, me, storage, tmp_path):
    video = make_video(db, storage, me)
    target = scene_ids(db, video)[0]
    long_clip = clip_bytes(tmp_path, seconds=15, rate=2)
    scene = an.post(f"/api/scenes/{target}/video", files={"file": ("dai.mp4", long_clip)}).json()["scenes"][0]
    assert scene["seconds"] == 10 and scene["blocking"] == []

    clip_key = db.scalar(select(Scene.video_key).where(Scene.id == target))
    assert an.delete(f"/api/scenes/{target}").status_code == 200
    assert not storage.exists(clip_key)
