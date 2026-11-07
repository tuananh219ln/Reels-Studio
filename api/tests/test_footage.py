"""'Edit từ footage': footage cut into scenes by what is said, each keeping its own sound (footage.py), and the
"Tiếng gốc" switch on any clip scene."""

import pytest
from conftest import clip_bytes, first_topic, login, make_user, make_video, needs_ffmpeg
from sqlalchemy import delete, select
from test_reference import loaded, run_learn, sample_video
from test_voice import first_scene, render
from worker_helpers import add_job, add_user, committed, job_row  # noqa: F401  (fixtures)

from reels_api import footage, stt
from reels_api.models import Job, KnowledgeTopic, Scene, Video, VideoReference
from reels_api.storage import DirectoryStorage
from reels_api.videos import render_signature, split_scenes


def words(*items) -> list[dict]:
    """(text, start, end) as stt.clean_words gives them."""
    return [{"text": text, "start": start, "end": end} for text, start, end in items]


# --- Cutting by the words ---


def test_pauses_and_fillers_are_cut_out_and_never_padded_back_in():
    said = words(
        ("Xin", 0.2, 0.4),
        ("chào", 0.4, 0.7),
        ("các", 0.7, 0.9),
        ("bạn.", 0.9, 1.3),
        ("Ờ,", 1.5, 1.9),  # a filler right after the sentence
        ("Hôm", 2.0, 2.2),
        ("nay", 2.2, 2.5),
        ("mình", 2.5, 2.8),
        ("review", 2.8, 3.3),
        ("yến", 3.3, 3.6),
        ("mạch.", 3.6, 4.0),
        ("Nó", 5.5, 5.7),  # after a 1.5 s pause
        ("ngon", 5.7, 6.4),
    )
    segments = footage.plan(said, 30.0)
    assert [(s.start, s.end, s.text) for s in segments] == [
        (0.08, 1.5, "Xin chào các bạn."),  # its tail stops where the filler starts
        (1.9, 4.25, "Hôm nay mình review yến mạch."),
        (5.38, 6.65, "Nó ngon"),
    ]


def test_a_stretch_longer_than_a_scene_is_split_at_a_sentence_end():
    said = [{"text": f"từ{n}" + ("." if n == 9 else ""), "start": n * 0.5, "end": n * 0.5 + 0.45} for n in range(30)]
    segments = footage.plan(said, 20.0)
    assert [segment.words[-1]["text"] for segment in segments][:1] == ["từ9."]
    assert all(1 <= segment.seconds <= 10 for segment in segments)
    assert [word["text"] for segment in segments for word in segment.words] == [word["text"] for word in said]


def test_a_very_short_stretch_takes_some_silence_to_last_a_second():
    segments = footage.plan(words(("Vâng.", 2.0, 2.3), ("Đúng", 4.0, 4.4), ("rồi.", 4.4, 5.6)), 8.0)
    assert segments[0].start == 1.88 and segments[0].seconds == pytest.approx(1.0)
    assert segments[1].text == "Đúng rồi."


def test_only_the_first_90_seconds_are_kept():
    said = [{"text": f"câu{n}.", "start": n * 5.0, "end": n * 5.0 + 4.0} for n in range(40)]
    segments = footage.plan(said, 200.0)
    assert sum(segment.seconds for segment in segments) <= 90
    assert segments[-1].words[-1]["text"] == f"câu{len(segments) - 1}."


def test_fillers_are_recognised_whatever_their_case_or_punctuation():
    assert all(footage.is_filler(text) for text in ("ờ", "Ừm,", "À...", "uh", "ừ"))
    assert not any(footage.is_filler(text) for text in ("ăn", "à la", "ơn"))


def test_the_title_is_the_topic_cut_to_fit_its_box():
    title = footage.title_text(
        "Yến Mạch Cán Dẹt Úc Polinuts 100% Nguyên Chất Rolled Oats Làm Overnight Oats Cháo Granola Sữa Hạt"
    )
    assert title.startswith("Yến Mạch") and len(title.split()) <= 12


def test_speech_to_text_words_are_cleaned_with_their_seconds():
    raw = [
        {"text": "Xin", "start": 0.1, "end": 0.3, "type": "word"},
        {"text": " ", "start": 0.3, "end": 0.35, "type": "spacing"},
        {"text": "(cười)", "start": 0.4, "end": 0.9, "type": "audio_event"},
        {"text": "chào", "start": None, "end": 1.2, "type": "word"},
        {"text": "bạn", "start": 0.9, "end": float("nan"), "type": "word"},
    ]
    assert stt.clean_words(raw) == words(("Xin", 0.1, 0.3), ("chào", 0.3, 1.2), ("bạn", 1.2, 1.2))
    assert stt.lines(stt.clean_words(raw)) == "[0:00] Xin chào bạn"


# --- The job ---


@pytest.fixture
def factory(committed):  # noqa: F811
    yield committed
    with committed() as db:
        db.execute(delete(Job))
        db.execute(delete(Scene))
        db.execute(delete(Video))
        db.execute(delete(VideoReference))
        db.execute(KnowledgeTopic.__table__.update().values(learn_prompt="", analyze_prompt=""))
        db.commit()


@pytest.fixture
def storage(tmp_path) -> DirectoryStorage:
    return DirectoryStorage(tmp_path / "storage")


def no_llm(*_):
    raise AssertionError("Edit từ footage không gọi AI")


@needs_ffmpeg
def test_footage_becomes_scenes_that_keep_their_sound_and_words(factory, storage, tmp_path, fakes):
    user = add_user(factory)
    video_id = sample_video(factory, storage, tmp_path, user, mode="footage", topic="Review *yến mạch* Úc")
    job = run_learn(factory, storage, video_id, user.id, no_llm)
    assert job.status == "done", (job.error, job.error_detail)
    video, sample, scenes = loaded(factory, video_id)
    # The fake ElevenLabs says two sentences, 1.5 s apart: the title scene and one content scene.
    assert len(scenes) == 2 and fakes.stt_requests
    title, scene = scenes
    assert title.is_title and title.text == "Review *yến mạch* Úc" and video.title_options == [title.text]
    assert scene.text == "" and scene.voice_text == "Món đầu tiên."
    for part in (title, scene):
        assert part.video_key and storage.exists(part.video_key) and part.video_sound and part.video_start == 0
        assert part.seconds <= part.video_seconds
    assert [word["text"] for word in title.words] == ["Ba", "món", "ăn", "sáng", "tốt", "cho", "tim."]
    # The clip is cut 0.12 s before the first word, so its words start there.
    assert scene.words[0] == {"text": "Món", "start": 0.12, "end": 0.32}
    assert sample.words and sample.transcript.startswith("[0:00] Ba món")
    assert video.has_script and video.hand_written and not video.voice_enabled and video.thumbnail_key
    assert (video.options["transition"], video.options["captions"], video.options["ducking"]) == ("cut", "word", True)
    from reels_api.clips import has_sound

    assert has_sound(storage.path(scene.video_key))


@needs_ffmpeg
def test_footage_without_words_says_why(factory, storage, tmp_path, fakes):
    user = add_user(factory)
    fakes.stt_mode = "no_permission"
    video_id = sample_video(factory, storage, tmp_path, user, mode="footage")
    job = run_learn(factory, storage, video_id, user.id, no_llm)
    assert job.status == "failed" and "Speech to Text" in job.error
    fakes.stt_mode, fakes.stt_words = "ok", fakes.stt_words[:3]
    again = sample_video(factory, storage, tmp_path, user, mode="footage")
    short = run_learn(factory, storage, again, user.id, no_llm)
    assert short.status == "failed" and "quá ít lời nói" in short.error


def test_the_form_takes_the_footage_way(client, db):
    make_user(db)
    login(client)
    response = client.post(
        "/api/references/videos",
        data={
            "topic": "Review yến mạch",
            "knowledge_topic_id": str(first_topic(db).id),
            "mode": "footage",
            "url": "https://www.tiktok.com/@a/video/1",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["reference"]["mode_label"] == "Edit từ footage"
    assert db.scalar(select(Job).where(Job.video_id == response.json()["id"])).kind == "learn"


# --- "Tiếng gốc" on a clip scene ---


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def with_clip(db, storage, scene, tmp_path, sound=True) -> None:
    data = clip_bytes(tmp_path, seconds=3, size="720x1280", rate=10)
    if not sound:
        import subprocess

        path = tmp_path / "silent.mp4"
        (tmp_path / "loud.mp4").write_bytes(data)
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(tmp_path / "loud.mp4"), "-an", "-c", "copy", str(path)],
            check=True,
        )
        data = path.read_bytes()
    scene.video_key, scene.video_seconds, scene.image_key = f"videos/{scene.video_id}/clip-{scene.id}.mp4", 3.0, None
    storage.save_bytes(scene.video_key, data)
    db.commit()


def video_of(response) -> dict:
    return next(item for item in response.json()["scenes"])["video"]


@needs_ffmpeg
def test_tieng_goc_is_turned_on_and_off_and_changes_the_mp4(an, db, me, storage, tmp_path):
    video = make_video(db, storage, me, scene_count=2)
    scene = first_scene(db, video)
    with_clip(db, storage, scene, tmp_path)
    before = render_signature(video, *split_scenes(db, video))
    response = an.patch(f"/api/scenes/{scene.id}", json={"video_sound": True})
    assert response.status_code == 200, response.text
    assert video_of(response)["sound"] is True and video_of(response)["words"] == 0
    db.refresh(video)
    assert render_signature(video, *split_scenes(db, video)) != before
    an.patch(f"/api/scenes/{scene.id}", json={"video_sound": False})
    db.refresh(video)
    assert render_signature(video, *split_scenes(db, video)) == before


@needs_ffmpeg
def test_tieng_goc_needs_a_clip_with_sound(an, db, me, storage, tmp_path):
    video = make_video(db, storage, me, scene_count=2)
    scene = first_scene(db, video)
    refused = an.patch(f"/api/scenes/{scene.id}", json={"video_sound": True})
    assert refused.status_code == 422 and "chưa có video" in refused.json()["message"]
    with_clip(db, storage, scene, tmp_path, sound=False)
    silent = an.patch(f"/api/scenes/{scene.id}", json={"video_sound": True})
    assert silent.status_code == 422 and "không có tiếng" in silent.json()["message"]


@needs_ffmpeg
def test_a_split_keeps_the_sound_and_words_and_removing_the_clip_drops_them(an, db, me, storage, tmp_path):
    video = make_video(db, storage, me, scene_count=1)
    scene = first_scene(db, video)
    with_clip(db, storage, scene, tmp_path)
    scene.video_sound, scene.words = True, words(("Xin", 0.2, 0.5), ("chào", 2.4, 2.8))
    db.commit()
    an.post(f"/api/scenes/{scene.id}/split", json={"at": 2})
    first, rest = split_scenes(db, video)[1]
    db.refresh(first)
    db.refresh(rest)
    assert rest.video_sound and rest.words == first.words and rest.video_start == 2
    an.delete(f"/api/scenes/{rest.id}/video")
    db.refresh(rest)
    assert not rest.video_sound and rest.words is None


def test_the_render_job_hands_the_clip_its_sound_and_words(committed, tmp_path, monkeypatch):  # noqa: F811
    from reels_api import jobs
    from reels_render import RenderError

    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    with committed() as db:
        video = make_video(db, storage, user, scene_count=2, seconds=2)
        video.voice_enabled = False
        scene = first_scene(db, video)
        scene.video_key, scene.video_seconds, scene.image_key = f"videos/{video.id}/clip.mp4", 3.0, None
        storage.save_bytes(scene.video_key, b"clip")
        scene.video_sound, scene.words = True, words(("Xin", 0.2, 0.5))
        db.commit()
        video_id = video.id
    handed = []

    def fake_render(script, output, **_):
        handed.extend((scene.video_sound, [word.text for word in scene.words]) for scene in script.all_scenes)
        raise RenderError("dừng trước FFmpeg")

    monkeypatch.setattr(jobs, "render_video", fake_render)
    render(committed, storage, video_id, user.id)
    assert handed == [(False, []), (True, ["Xin"]), (False, [])]
