"""Scene narration: voice text editing, ElevenLabs in the render job, lengthened scenes, reuse of made MP3s."""

import shutil

import pytest
from conftest import login, make_user, make_video
from fake_services import ELEVENLABS_KEY
from sqlalchemy import select
from worker_helpers import add_job, add_user, committed, job_row  # noqa: F401  (fixtures)

from reels_api import config, source_keys
from reels_api.models import Job, Scene, Video
from reels_api.storage import DirectoryStorage
from reels_api.tts import voice_signature
from reels_api.videos import auto_seconds, render_signature, split_scenes, spoken
from reels_render.ffmpeg import probe

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg/ffprobe không có trên PATH")
TEN_WORDS = "một hai ba bốn năm sáu bảy tám chín mười"


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def first_scene(db, video) -> Scene:
    return db.scalar(
        select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)).order_by(Scene.position).limit(1)
    )


# --- Editing ---


def test_voice_text_and_switch_are_saved(an, db, me, storage):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    payload = an.patch(f"/api/scenes/{scene.id}", json={"voice_text": "  Cá nhỏ giàu canxi \r\n"}).json()
    assert payload["scenes"][0]["voice_text"] == "Cá nhỏ giàu canxi"
    # Nothing made yet: no player, and the scene keeps its seconds.
    assert payload["scenes"][0]["voice_url"] is None and payload["scenes"][0]["fitted_seconds"] == 4
    assert payload["voice_enabled"] is True
    assert an.patch(f"/api/videos/{video.id}", json={"voice_enabled": False}).json()["voice_enabled"] is False
    response = an.patch(f"/api/scenes/{scene.id}", json={"voice_text": "a" * 1001})
    assert response.status_code == 422 and "Lời đọc" in response.json()["message"]


@pytest.mark.parametrize(
    ("text", "voice_text", "expected"),
    [
        ("2. Canh rau ngót\nMát gan, dễ tiêu", "Rau ngót nấu tôm dễ ăn", "Rau ngót nấu tôm dễ ăn"),
        ("", "Ăn cả xương", "Ăn cả xương"),
        ("2. Canh rau ngót\nMát gan, dễ tiêu", "  ", "Canh rau ngót. Mát gan, dễ tiêu."),
        ("", "  ", ""),
    ],
)
def test_narration_reads_the_voice_text_else_the_on_screen_text(text, voice_text, expected):
    assert spoken(Video(voice_enabled=True), Scene(text=text, voice_text=voice_text)) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2) Canh rau ngót\nMát gan", "Canh rau ngót. Mát gan."),
        ("2.Canh rau ngót", "Canh rau ngót."),
        ("*2.* Giàu *canxi*\n\nRẻ, dễ tìm", "Giàu canxi. Rẻ, dễ tìm."),
        ("2.\nCanh rau ngót", "Canh rau ngót."),
        ("Ăn gì tốt cho xương?\nXem ngay!", "Ăn gì tốt cho xương? Xem ngay!"),
        ("Rắc vào cháo,\nsữa hạt mỗi sáng", "Rắc vào cháo, sữa hạt mỗi sáng."),
        ("2.5 lít nước mỗi ngày", "2.5 lít nước mỗi ngày."),
        ("5 món tốt cho xương", "5 món tốt cho xương."),
        ("2.", ""),
    ],
)
def test_on_screen_text_is_cleaned_for_reading(text, expected):
    assert spoken(Video(voice_enabled=True), Scene(text=text, voice_text="")) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [("5 MÓN TỐT\nCHO *XƯƠNG*", "5 MÓN TỐT CHO XƯƠNG"), ("1. MÓN ĐẦU TIÊN", "1. MÓN ĐẦU TIÊN")],
)
def test_the_title_scene_keeps_its_whole_sentence(text, expected):
    assert spoken(Video(voice_enabled=True), Scene(is_title=True, text=text, voice_text="")) == expected


def test_nothing_is_read_when_the_narration_is_off():
    assert spoken(Video(voice_enabled=False), Scene(text="Cá nhỏ", voice_text="Ăn cả xương")) == ""


def test_a_banned_word_in_the_on_screen_text_is_not_reported_as_narration(an, db, me, storage):
    video = make_video(db, storage, me, scene_text="Món chữa khỏi đau lưng")
    scene = first_scene(db, video)
    warnings = an.patch(f"/api/scenes/{scene.id}", json={"voice_text": "Ăn cả xương"}).json()["scenes"][0]["warnings"]
    assert "Có từ cấm: “chữa khỏi”" in warnings
    assert "Lời đọc có từ cấm: “chữa khỏi”" not in warnings


@pytest.mark.parametrize(("voice_text", "kept"), [("Ăn cả xương", 5.0), ("", None)])
def test_only_a_scene_that_reads_its_on_screen_text_remakes_the_narration(an, db, me, storage, voice_text, kept):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    scene.voice_text, scene.voice_key = voice_text, f"videos/{video.id}/voice-{scene.id}-x.mp3"
    scene.voice_signature, scene.voice_seconds = voice_signature(spoken(video, scene)), 5.0
    storage.save_bytes(scene.voice_key, b"mp3")
    db.commit()
    assert an.get(f"/api/videos/{video.id}").json()["scenes"][0]["voice_seconds"] == 5.0
    payload = an.patch(f"/api/scenes/{scene.id}", json={"text": "Tôm nhỏ"}).json()
    assert payload["scenes"][0]["voice_seconds"] == kept


def test_the_payload_says_what_the_narration_reads(an, db, me, storage):
    video = make_video(db, storage, me, scene_text="2. Cá nhỏ\nGiàu *canxi*")
    scene = first_scene(db, video)
    assert an.get(f"/api/videos/{video.id}").json()["scenes"][0]["spoken_text"] == "Cá nhỏ. Giàu canxi."
    payload = an.patch(f"/api/scenes/{scene.id}", json={"voice_text": "Ăn cả xương"}).json()
    assert payload["scenes"][0]["spoken_text"] == "Ăn cả xương"
    payload = an.patch(f"/api/videos/{video.id}", json={"voice_enabled": False}).json()
    assert payload["scenes"][0]["spoken_text"] == ""


def test_banned_words_in_voice_text_warn(an, db, me, storage):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    payload = an.patch(f"/api/scenes/{scene.id}", json={"voice_text": "Món này chữa khỏi đau lưng"}).json()
    assert "Lời đọc có từ cấm: “chữa khỏi”" in payload["scenes"][0]["warnings"]
    assert payload["can_render"] is True


def test_made_narration_shows_its_length_and_player_until_the_text_changes(an, db, me, storage):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    scene.voice_text, scene.voice_key = "Cá nhỏ giàu canxi", f"videos/{video.id}/voice-{scene.id}-x.mp3"
    scene.voice_signature, scene.voice_seconds = voice_signature(spoken(video, scene)), 5.0
    storage.save_bytes(scene.voice_key, b"mp3")
    db.commit()
    data = an.get(f"/api/videos/{video.id}").json()["scenes"][0]
    assert (data["voice_seconds"], data["fitted_seconds"]) == (5.0, 5.6)
    assert an.get(data["voice_url"]).content == b"mp3"

    data = an.patch(f"/api/scenes/{scene.id}", json={"voice_text": "Cá nhỏ rất giàu canxi"}).json()["scenes"][0]
    assert (data["voice_seconds"], data["voice_url"], data["fitted_seconds"]) == (None, None, 4)


@pytest.mark.parametrize("change", ["voice_text", "voice_off"])
def test_narration_changes_mark_the_mp4_outdated(an, db, me, storage, change):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    scene.voice_text = "Cá nhỏ giàu canxi"
    db.commit()
    title, scenes = split_scenes(db, video)
    video.mp4_key, video.rendered_signature = f"videos/{video.id}/v.mp4", render_signature(video, title, scenes)
    db.commit()
    assert an.get(f"/api/videos/{video.id}").json()["mp4_outdated"] is False
    if change == "voice_text":
        an.patch(f"/api/scenes/{scene.id}", json={"voice_text": "Cá nhỏ ăn cả xương"})
    else:
        an.patch(f"/api/videos/{video.id}", json={"voice_enabled": False})
    assert an.get(f"/api/videos/{video.id}").json()["mp4_outdated"] is True


def test_videos_without_narration_keep_their_fingerprint(db, me, storage):
    video = make_video(db, storage, me, title_text="", scene_text="")
    title, scenes = split_scenes(db, video)
    before = render_signature(video, title, scenes)
    video.voice_enabled = False
    assert render_signature(video, title, scenes) == before


def test_deleting_a_scene_deletes_its_narration(an, db, me, storage):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    scene.voice_key = f"videos/{video.id}/voice-{scene.id}-x.mp3"
    storage.save_bytes(scene.voice_key, b"mp3")
    db.commit()
    key = scene.voice_key
    assert an.delete(f"/api/scenes/{scene.id}").status_code == 200
    assert not storage.exists(key)


def test_clone_snapshot_carries_the_voice_text(an, db, me, storage):
    video = make_video(db, storage, me)
    an.patch(f"/api/scenes/{first_scene(db, video).id}", json={"voice_text": "Cá nhỏ ăn cả xương"})
    draft = an.post(f"/api/videos/{video.id}/clone", json={"request": "đổi sang tim mạch"}).json()
    assert (
        "Cảnh 1 (4 giây): Cá nhỏ / Giàu *canxi* — lời đọc: Cá nhỏ ăn cả xương"
        in db.get(Video, draft["id"]).clone_source["script"]
    )


def test_voice_signature_follows_voice_and_model_and_ignores_spacing(monkeypatch):
    base = voice_signature("Cá nhỏ giàu canxi")
    assert voice_signature("  Cá nhỏ \n giàu  canxi ") == base
    monkeypatch.setenv("ELEVENLABS_MODEL", "eleven_flash_v2_5")
    assert voice_signature("Cá nhỏ giàu canxi") != base
    monkeypatch.setenv("ELEVENLABS_MODEL", "")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "another-voice")
    assert voice_signature("Cá nhỏ giàu canxi") != base


# --- Render jobs, in process ---


@pytest.fixture
def voiced(committed, tmp_path, fakes):
    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    with committed() as db:
        video = make_video(db, storage, user, scene_count=1, seconds=2, title_text="", scene_text="")
        first_scene(db, video).voice_text = TEN_WORDS
        db.commit()
    return user, storage, video.id


def render(factory, storage, video_id, user_id) -> Job:
    from reels_api import jobs

    job_id = add_job(factory, video_id, user_id, kind="render", status="running")
    jobs.run_job(job_id, factory, storage)
    return job_row(factory, job_id)


def mp4_seconds(factory, storage, video_id) -> float:
    with factory() as db:
        return float(probe("ffprobe", storage.path(db.get(Video, video_id).mp4_key))["format"]["duration"])


@needs_ffmpeg
def test_render_reads_adam_lengthens_the_scene_and_reuses_the_narration(committed, voiced, fakes):
    user, storage, video_id = voiced
    job = render(committed, storage, video_id, user.id)
    assert job.status == "done", (job.error, job.error_detail)
    assert fakes.tts_requests == [
        {"voice_id": config.DEFAULT_VOICE_ID, "text": TEN_WORDS, "model_id": "eleven_v3", "language_code": "vi"}
    ]
    # Title 3 s + the 2 s scene lengthened to fit 3 s of narration: 0.2 + 3.0 (+ MP3 padding) + 0.4 → 3.7 s.
    assert mp4_seconds(committed, storage, video_id) == pytest.approx(6.7, abs=0.05)
    with committed() as db:
        scene = first_scene(db, db.get(Video, video_id))
        first_key = scene.voice_key
        assert scene.voice_seconds == pytest.approx(3.0, abs=0.1)

    # A re-render pays nothing: the narration made from the same text is reused.
    assert render(committed, storage, video_id, user.id).status == "done"
    assert len(fakes.tts_requests) == 1

    with committed() as db:
        first_scene(db, db.get(Video, video_id)).voice_text = "một hai ba"
        db.commit()
    assert render(committed, storage, video_id, user.id).status == "done"
    assert [request["text"] for request in fakes.tts_requests] == [TEN_WORDS, "một hai ba"]
    assert not storage.exists(first_key)
    # 0.9 s of narration fits in the scene's own 2 s.
    assert mp4_seconds(committed, storage, video_id) == pytest.approx(5.0, abs=0.05)


@needs_ffmpeg
def test_a_new_model_remakes_the_narration_and_marks_the_mp4_outdated(committed, voiced, fakes, monkeypatch):
    user, storage, video_id = voiced
    assert render(committed, storage, video_id, user.id).status == "done"
    monkeypatch.setenv("ELEVENLABS_MODEL", "eleven_flash_v2_5")
    with committed() as db:
        video = db.get(Video, video_id)
        title, scenes = split_scenes(db, video)
        assert video.rendered_signature != render_signature(video, title, scenes)
    assert render(committed, storage, video_id, user.id).status == "done"
    assert [request["model_id"] for request in fakes.tts_requests] == ["eleven_v3", "eleven_flash_v2_5"]


@needs_ffmpeg
def test_a_failure_partway_keeps_the_narration_already_paid_for(committed, tmp_path, fakes):
    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    with committed() as db:
        video = make_video(db, storage, user, scene_count=2, seconds=2, title_text="", scene_text="")
        _, scenes = split_scenes(db, video)
        scenes[0].voice_text, scenes[1].voice_text = "một hai ba", "bốn năm sáu"
        db.commit()
        video_id = video.id
    fakes.tts_ok_count = 1
    job = render(committed, storage, video_id, user.id)
    assert (job.status, job.error) == ("failed", "Cảnh 2: Tài khoản ElevenLabs đã hết ký tự (credit), cần nạp thêm")
    with committed() as db:
        _, scenes = split_scenes(db, db.get(Video, video_id))
        assert scenes[0].voice_key and storage.exists(scenes[0].voice_key) and scenes[1].voice_key is None

    fakes.tts_ok_count = None
    assert render(committed, storage, video_id, user.id).status == "done"
    assert [request["text"] for request in fakes.tts_requests] == ["một hai ba", "bốn năm sáu", "bốn năm sáu"]


@needs_ffmpeg
def test_render_sends_only_the_voice_text_when_the_scene_has_both(committed, voiced, fakes):
    user, storage, video_id = voiced
    with committed() as db:
        first_scene(db, db.get(Video, video_id)).text = "Cá nhỏ\nGiàu *canxi*"
        db.commit()
    assert render(committed, storage, video_id, user.id).status == "done"
    assert [request["text"] for request in fakes.tts_requests] == [TEN_WORDS]


@needs_ffmpeg
def test_render_reads_the_on_screen_text_of_a_scene_without_voice_text(committed, voiced, fakes):
    user, storage, video_id = voiced
    with committed() as db:
        scene = first_scene(db, db.get(Video, video_id))
        scene.text, scene.voice_text = "2. Cá nhỏ\nGiàu *canxi*", ""
        db.commit()
    job = render(committed, storage, video_id, user.id)
    assert job.status == "done", (job.error, job.error_detail)
    assert [request["text"] for request in fakes.tts_requests] == ["Cá nhỏ. Giàu canxi."]


@needs_ffmpeg
def test_a_scene_with_empty_text_renders(committed, voiced, fakes):
    user, storage, video_id = voiced
    with committed() as db:
        first_scene(db, db.get(Video, video_id)).text = ""
        db.commit()
    job = render(committed, storage, video_id, user.id)
    assert job.status == "done", (job.error, job.error_detail)


@needs_ffmpeg
def test_narration_switched_off_renders_without_calling_elevenlabs(committed, voiced, fakes):
    user, storage, video_id = voiced
    with committed() as db:
        db.get(Video, video_id).voice_enabled = False
        db.commit()
    assert render(committed, storage, video_id, user.id).status == "done"
    assert fakes.tts_requests == []
    assert mp4_seconds(committed, storage, video_id) == pytest.approx(5.0, abs=0.05)


@needs_ffmpeg
def test_elevenlabs_out_of_credit_fails_the_render_with_a_clear_reason(committed, voiced, fakes):
    user, storage, video_id = voiced
    fakes.tts_mode = "quota"
    job = render(committed, storage, video_id, user.id)
    assert (job.status, job.error) == ("failed", "Cảnh 1: Tài khoản ElevenLabs đã hết ký tự (credit), cần nạp thêm")
    assert "quota_exceeded" in job.error_detail
    with committed() as db:
        assert db.get(Video, video_id).mp4_key is None


@needs_ffmpeg
def test_render_reads_with_the_elevenlabs_key_pasted_on_the_sources_page(committed, voiced, fakes, monkeypatch):
    user, storage, video_id = voiced
    monkeypatch.setenv("ELEVENLABS_API_KEY", "")
    with committed() as db:
        source_keys.save(db, "elevenlabs", ELEVENLABS_KEY, user.id)
        db.commit()
    job = render(committed, storage, video_id, user.id)
    assert job.status == "done", (job.error, job.error_detail)
    assert len(fakes.tts_requests) == 1


@needs_ffmpeg
def test_render_without_an_elevenlabs_key_says_where_to_paste_one(committed, voiced, fakes, monkeypatch):
    user, storage, video_id = voiced
    monkeypatch.setenv("ELEVENLABS_API_KEY", "")
    job = render(committed, storage, video_id, user.id)
    assert job.status == "failed" and "Chưa có key ElevenLabs" in job.error and "Nguồn tư liệu" in job.error
    assert fakes.tts_requests == []


@needs_ffmpeg
def test_narration_pushing_the_total_over_90_seconds_fails_but_keeps_what_was_made(committed, tmp_path, fakes):
    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    long_text = " ".join(["chữ"] * 40)  # 12 s of fake narration: each of the two scenes becomes 12.7 s
    with committed() as db:
        video = make_video(db, storage, user, scene_count=9, seconds=9, title_text="", scene_text="")
        _, scenes = split_scenes(db, video)
        for scene in scenes[:2]:
            scene.voice_text = long_text
        db.commit()
        video_id = video.id
    job = render(committed, storage, video_id, user.id)
    assert job.status == "failed"
    assert job.error.startswith("Chưa render được: Tổng độ dài") and "tối đa 90 giây" in job.error
    assert len(fakes.tts_requests) == 2
    with committed() as db:
        _, scenes = split_scenes(db, db.get(Video, video_id))
        assert all(scene.voice_key for scene in scenes[:2]), "a retry must not pay for these again"


# --- ElevenLabs narration for the preview ("Tạo giọng thật") ---


def test_making_the_narration_queues_a_voice_job_that_locks_the_video(an, db, me, storage):
    video = make_video(db, storage, me)
    first_scene(db, video).voice_text = TEN_WORDS
    db.commit()
    payload = an.post(f"/api/videos/{video.id}/voices").json()
    assert (payload["active_job"]["kind"], payload["status_label"]) == ("voice", "Chờ thứ 1")
    save = an.patch(f"/api/scenes/{first_scene(db, video).id}", json={"text": "B đang gõ"})
    assert (save.status_code, save.json()["message"]) == (409, "Video đang tạo giọng đọc, chưa lưu")
    assert an.post(f"/api/videos/{video.id}/voices").status_code == 409


def test_making_the_narration_is_refused_when_there_is_nothing_to_make(an, db, me, storage):
    video = make_video(db, storage, me, title_text="", scene_text="")
    response = an.post(f"/api/videos/{video.id}/voices")
    assert (response.status_code, response.json()["message"]) == (409, "Mọi cảnh đã có giọng ElevenLabs")
    first_scene(db, video).voice_text = TEN_WORDS
    video.voice_enabled = False
    db.commit()
    response = an.post(f"/api/videos/{video.id}/voices")
    assert (response.status_code, response.json()["message"]) == (409, "Video đang tắt giọng đọc")


@needs_ffmpeg
def test_a_voice_job_makes_only_the_narration_and_the_render_reuses_it(committed, voiced, fakes):
    from reels_api import jobs

    user, storage, video_id = voiced
    job_id = add_job(committed, video_id, user.id, kind="voice", status="running")
    jobs.run_job(job_id, committed, storage)
    job = job_row(committed, job_id)
    assert job.status == "done", (job.error, job.error_detail)
    assert [request["text"] for request in fakes.tts_requests] == [TEN_WORDS]
    with committed() as db:
        video = db.get(Video, video_id)
        assert video.mp4_key is None and storage.exists(first_scene(db, video).voice_key)
    assert render(committed, storage, video_id, user.id).status == "done"
    assert len(fakes.tts_requests) == 1


@needs_ffmpeg
def test_a_voice_job_fails_with_elevenlabs_reason(committed, voiced, fakes):
    from reels_api import jobs

    user, storage, video_id = voiced
    fakes.tts_mode = "quota"
    job_id = add_job(committed, video_id, user.id, kind="voice", status="running")
    jobs.run_job(job_id, committed, storage)
    job = job_row(committed, job_id)
    assert (job.status, job.error) == ("failed", "Cảnh 1: Tài khoản ElevenLabs đã hết ký tự (credit), cần nạp thêm")


# --- The scene's name before its narration ---


@pytest.mark.parametrize(
    ("text", "voice_text", "expected"),
    [
        ("Rau muống\nKhoảng *3 tuần* cắt ngọn", "Rau muống Ngâm hạt qua đêm", "Rau muống, Ngâm hạt qua đêm"),
        ("2. Cá nhỏ\nĂn cả xương", "cá nhỏ có canxi", "cá nhỏ, có canxi"),
        ("Rau muống\nKhoảng 3 tuần", "Rau muống, ngâm hạt", "Rau muống, ngâm hạt"),
        ("Rau muống\nKhoảng 3 tuần", "Rau muống. Ngâm hạt", "Rau muống. Ngâm hạt"),
        ("Rau muống\nKhoảng 3 tuần", "Rau muống – ngâm hạt", "Rau muống – ngâm hạt"),
        ("Rau muống\nKhoảng 3 tuần", "Rau muốngxanh", "Rau muốngxanh"),
        ("Rau muống\nKhoảng 3 tuần", "Ngâm hạt qua đêm", "Ngâm hạt qua đêm"),
        ("Rau muống", "Rau muống", "Rau muống"),
    ],
)
def test_a_voice_text_opening_with_the_scene_name_pauses_after_it(db, me, storage, text, voice_text, expected):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    scene.text, scene.voice_text = text, voice_text
    assert spoken(video, scene) == expected


def test_the_title_voice_is_read_as_written(db, me, storage):
    video = make_video(db, storage, me)
    title, _ = split_scenes(db, video)
    title.text, title.voice_text = "RAU MUỐNG\nDỄ TRỒNG", "RAU MUỐNG dễ trồng nhất"
    assert spoken(video, title) == "RAU MUỐNG dễ trồng nhất"


# --- Seconds that follow the narration ---


def test_auto_seconds_cover_the_narration_within_a_scene_s_limits():
    assert auto_seconds(3.0) == pytest.approx(3.6)  # 0.2 before, 0.4 after
    assert auto_seconds(0.2) == 1  # a scene lasts at least a second
    assert auto_seconds(12.0) == 10  # longer narration lengthens the scene at render instead (fit_seconds)


@needs_ffmpeg
def test_a_voice_job_sets_the_seconds_of_a_scene_that_follows_its_narration(committed, voiced, fakes):
    from reels_api import jobs

    user, storage, video_id = voiced
    with committed() as db:
        scene = first_scene(db, db.get(Video, video_id))
        scene.seconds, scene.seconds_auto = 8, True
        db.commit()
    job_id = add_job(committed, video_id, user.id, kind="voice", status="running")
    jobs.run_job(job_id, committed, storage)
    assert job_row(committed, job_id).status == "done"
    with committed() as db:
        scene = first_scene(db, db.get(Video, video_id))
        # Shorter than the 8 s it was set to: the scene now ends with its narration.
        assert scene.seconds == auto_seconds(scene.voice_seconds) < 8


@needs_ffmpeg
def test_a_scene_set_by_hand_keeps_its_seconds_after_the_voice_job(committed, voiced, fakes):
    from reels_api import jobs

    user, storage, video_id = voiced
    with committed() as db:
        scene = first_scene(db, db.get(Video, video_id))
        scene.seconds, scene.seconds_auto = 8, False
        db.commit()
    job_id = add_job(committed, video_id, user.id, kind="voice", status="running")
    jobs.run_job(job_id, committed, storage)
    with committed() as db:
        assert first_scene(db, db.get(Video, video_id)).seconds == 8


def test_typing_seconds_stops_following_and_khop_loi_doc_follows_at_once(an, db, me, storage):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    text = spoken(video, scene)
    # A narration already made for the current text, as the voice job leaves it.
    scene.voice_key, scene.voice_seconds = "videos/x/voice.mp3", 2.5
    scene.voice_signature = voice_signature(text, config.DEFAULT_VOICE_ID, video_options_speed(video))
    scene.seconds_auto = True
    db.flush()
    payload = an.patch(f"/api/scenes/{scene.id}", json={"seconds": 6}).json()
    assert (payload["scenes"][0]["seconds"], payload["scenes"][0]["seconds_auto"]) == (6, False)
    payload = an.patch(f"/api/scenes/{scene.id}", json={"seconds_auto": True}).json()
    assert payload["scenes"][0]["seconds_auto"] is True
    assert payload["scenes"][0]["seconds"] == pytest.approx(auto_seconds(2.5))


def test_new_scenes_follow_their_narration(an, db, me, storage):
    video = make_video(db, storage, me)
    payload = an.post(f"/api/videos/{video.id}/scenes").json()
    assert payload["scenes"][-1]["seconds_auto"] is True
    # Scenes from before keep the seconds they were given.
    assert payload["scenes"][0]["seconds_auto"] is False


def video_options_speed(video):
    from reels_api.video_options import voice_speed

    return voice_speed(video)
