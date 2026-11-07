"""'Từ video mẫu': a video learned from a sample video, in its four ways (reference.py, routes_references.py)."""

import json

import pytest
from conftest import clip_bytes, first_topic, login, make_user, needs_ffmpeg
from fake_services import learned_json
from sqlalchemy import delete, select
from worker_helpers import add_job, add_user, committed, job_row  # noqa: F401  (fixtures)

from reels_api import jobs, reference, remote_media, stt
from reels_api.claude import ClaudeError
from reels_api.models import Job, KnowledgeTopic, Scene, Video, VideoReference
from reels_api.storage import DirectoryStorage

# --- Pure helpers ---


def test_stills_are_spread_evenly_and_capped():
    assert reference.frame_seconds(4) == [1.0, 3.0]
    many = reference.frame_seconds(120)
    assert len(many) == reference.MAX_FRAMES and many[0] == 3.8 and many[-1] < 120


def test_a_clip_stretch_is_kept_inside_the_sample_and_its_limits():
    assert reference.clip_range({"tu": 2, "den": 5}, 20) == (2.0, 5.0)
    assert reference.clip_range([2, 5], 20) == (2.0, 5.0)
    assert reference.clip_range({"tu": 18, "den": 40}, 20) == (18.0, 20.0)  # cut at the sample's end
    assert reference.clip_range({"tu": 0, "den": 30}, 60) == (0.0, 10.0)  # at most 10 s
    assert reference.clip_range({"tu": 3, "den": 3}, 20) == (3.0, 4.5)  # at least 1.5 s
    assert reference.clip_range({"tu": 25, "den": 30}, 20) == (18.5, 20.0)
    for unusable in (None, "1-3", {"tu": "a", "den": 2}, [1], {"tu": float("nan"), "den": 2}):
        assert reference.clip_range(unusable, 20) is None


def test_the_words_become_lines_that_start_with_their_second():
    words = [
        {"text": "Xin", "start": 0.1, "type": "word"},
        {"text": " ", "start": 0.2, "type": "spacing"},
        {"text": "chào.", "start": 0.3, "type": "word"},
        {"text": "(nhạc)", "start": 1, "type": "audio_event"},
        {"text": "Hôm", "start": 62.5, "type": "word"},
        {"text": "nay", "start": 62.8, "type": "word"},
    ]
    assert stt.lines(words) == "[0:00] Xin chào.\n[1:02] Hôm nay"
    assert stt.lines([]) == ""


# --- Jobs ---


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


class SeeingLlm:
    """The LLM as the learn job calls it: records each prompt and how many stills came with it."""

    def __init__(self, replies=None):
        self.calls: list[tuple[str, int]] = []
        self.replies = list(replies or [])

    def __call__(self, prompt, label, images=()):
        self.calls.append((prompt, len(images)))
        if self.replies:
            reply = self.replies.pop(0)
            return reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)
        frames = prompt.count("gửi kèm, giây")
        if '"khung_hinh"' in prompt:
            return json.dumps(
                {"phan_tich": "Hook: hỏi ngay giây đầu.", "khung_hinh": [f"Cảnh {n}" for n in range(frames)]},
                ensure_ascii=False,
            )
        return json.dumps(learned_json("tim mạch", with_analysis='"phan_tich"' in prompt), ensure_ascii=False)


def sample_video(factory, storage, tmp_path, user, mode="quick", seconds=12.0, topic="3 món tốt cho tim") -> int:
    data = clip_bytes(tmp_path, seconds=seconds, size="720x1280", rate=10)
    with factory() as db:
        sample = VideoReference(source_name="mau.mp4", created_by_id=user.id)
        db.add(sample)
        db.flush()
        sample.video_key = reference.source_key(sample.id, "mp4")
        storage.save_bytes(sample.video_key, data)
        video = Video(
            topic=topic,
            knowledge_topic_id=first_topic(db).id,
            has_script=False,
            created_by_id=user.id,
            reference_id=sample.id,
            reference_mode=mode,
        )
        db.add(video)
        db.commit()
        return video.id


def run_learn(factory, storage, video_id, user_id, call) -> Job:
    job_id = add_job(factory, video_id, user_id, kind="learn", status="running")
    jobs.run_job(job_id, factory, storage, call)
    return job_row(factory, job_id)


def loaded(factory, video_id):
    with factory() as db:
        video = db.get(Video, video_id)
        sample = db.get(VideoReference, video.reference_id) if video.reference_id else None
        scenes = db.scalars(
            select(Scene).where(Scene.video_id == video_id).order_by(Scene.is_title.desc(), Scene.position)
        ).all()
        return video, sample, scenes


@needs_ffmpeg
def test_quick_way_sees_the_stills_once_and_cuts_the_chosen_stretches(factory, storage, tmp_path, fakes):
    user = add_user(factory)
    video_id = sample_video(factory, storage, tmp_path, user)
    llm = SeeingLlm()
    job = run_learn(factory, storage, video_id, user.id, llm)
    assert job.status == "done", (job.error, job.error_detail)
    video, sample, scenes = loaded(factory, video_id)
    # One call, with every still, that also wrote the analysis.
    assert len(llm.calls) == 1 and llm.calls[0][1] == len(sample.frames) == 6
    prompt = llm.calls[0][0]
    assert "3 món tốt cho tim" in prompt and '"phan_tich"' in prompt and '"clip"' in prompt
    assert "[0:00] Ba món ăn sáng tốt cho tim." in prompt  # the fake ElevenLabs' words, with their second
    assert sample.transcript.startswith("[0:00] Ba món") and sample.analysis.startswith("Hook")
    assert fakes.stt_requests and fakes.stt_requests[0]["model_id"] == "scribe_v2"
    # The title and the first two scenes show stretches of the sample; the others wait for "Tự tìm ảnh".
    title, first, second, third = scenes[0], scenes[1], scenes[2], scenes[3]
    for scene in (title, first, second):
        assert scene.video_key and storage.exists(scene.video_key) and scene.image_key is None
        assert scene.video_seconds >= scene.seconds
    assert third.video_key is None and third.image_key is None
    assert video.has_script and video.thumbnail_key
    with factory() as db:
        assert db.scalar(select(Job).where(Job.video_id == video_id, Job.kind == "photos")) is not None


@needs_ffmpeg
def test_two_step_way_analyses_with_the_stills_then_writes_without_them(factory, storage, tmp_path, fakes):
    user = add_user(factory)
    video_id = sample_video(factory, storage, tmp_path, user, mode="twostep")
    llm = SeeingLlm()
    job = run_learn(factory, storage, video_id, user.id, llm)
    assert job.status == "done", (job.error, job.error_detail)
    (analysis_prompt, seen), (write_prompt, seen_after) = llm.calls
    assert seen == 6 and seen_after == 0
    assert '"khung_hinh"' in analysis_prompt and '"phan_tich"' not in write_prompt.split("THÊM VÀO")[-1]
    # The writing call knows the stills by the notes the analysis wrote, and the analysis itself.
    assert "Cảnh 0" in write_prompt and "Hook: hỏi ngay giây đầu." in write_prompt
    video, sample, _ = loaded(factory, video_id)
    assert video.has_script and sample.frames[0]["note"] == "Cảnh 0"
    assert job_row(factory, job.id).claude_calls == 2


@needs_ffmpeg
def test_review_way_stops_after_the_analysis_and_writes_from_the_edited_one(factory, storage, tmp_path, fakes):
    user = add_user(factory)
    video_id = sample_video(factory, storage, tmp_path, user, mode="review")
    llm = SeeingLlm()
    job = run_learn(factory, storage, video_id, user.id, llm)
    assert job.status == "done", (job.error, job.error_detail)
    video, sample, scenes = loaded(factory, video_id)
    assert not video.has_script and not scenes and sample.analysis.startswith("Hook")
    with factory() as db:
        assert db.scalar(select(Job).where(Job.kind == "photos")) is None
        db.get(VideoReference, sample.id).analysis = "Hook: bắt đầu bằng con số gây sốc."
        db.commit()
    again = run_learn(factory, storage, video_id, user.id, llm)
    assert again.status == "done", (again.error, again.error_detail)
    prompt, seen = llm.calls[-1]
    assert "Hook: bắt đầu bằng con số gây sốc." in prompt and seen == 6 and '"phan_tich"' not in prompt
    assert len(llm.calls) == 2 and loaded(factory, video_id)[0].has_script


@needs_ffmpeg
def test_reuse_way_writes_another_video_without_preparing_the_sample_again(factory, storage, tmp_path, fakes):
    user = add_user(factory)
    first_id = sample_video(factory, storage, tmp_path, user, mode="quick")
    assert run_learn(factory, storage, first_id, user.id, SeeingLlm()).status == "done"
    words_asked = len(fakes.stt_requests)
    with factory() as db:
        first = db.get(Video, first_id)
        second = Video(
            topic="3 món tốt cho gan",
            knowledge_topic_id=first.knowledge_topic_id,
            created_by_id=user.id,
            reference_id=first.reference_id,
            reference_mode="reuse",
        )
        db.add(second)
        db.commit()
        second_id, frames = second.id, db.get(VideoReference, first.reference_id).frames
    llm = SeeingLlm()
    job = run_learn(factory, storage, second_id, user.id, llm)
    assert job.status == "done", (job.error, job.error_detail)
    assert len(llm.calls) == 1 and llm.calls[0][1] == len(frames) and "3 món tốt cho gan" in llm.calls[0][0]
    assert len(fakes.stt_requests) == words_asked
    assert loaded(factory, second_id)[1].frames == frames


@needs_ffmpeg
def test_a_pasted_link_is_downloaded_by_the_job(factory, storage, tmp_path, fakes, monkeypatch):
    user = add_user(factory)
    data = clip_bytes(tmp_path, seconds=6, size="720x1280", rate=10)

    def fake_download(url, folder):
        assert url == "https://www.tiktok.com/@bep/video/7300000000000000001"
        path = folder / "linked.mp4"
        path.write_bytes(data)
        return path

    monkeypatch.setattr(remote_media, "download_sample", fake_download)
    with factory() as db:
        url = "https://www.tiktok.com/@bep/video/7300000000000000001"
        sample = VideoReference(source_url=url, source_name=url, created_by_id=user.id)
        db.add(sample)
        db.flush()
        video = Video(
            topic="tim mạch",
            knowledge_topic_id=first_topic(db).id,
            created_by_id=user.id,
            reference_id=sample.id,
            reference_mode="quick",
        )
        db.add(video)
        db.commit()
        video_id = video.id
    job = run_learn(factory, storage, video_id, user.id, SeeingLlm())
    assert job.status == "done", (job.error, job.error_detail)
    _, sample, _ = loaded(factory, video_id)
    assert sample.video_key.startswith(f"references/{sample.id}/source-") and storage.exists(sample.video_key)
    assert sample.seconds == pytest.approx(6, abs=0.2)


@needs_ffmpeg
def test_the_real_llm_call_sends_the_stills_as_images(factory, storage, tmp_path, fakes):
    user = add_user(factory)
    video_id = sample_video(factory, storage, tmp_path, user, seconds=4)
    job = run_learn(factory, storage, video_id, user.id, None)
    assert job.status == "done", (job.error, job.error_detail)
    assert fakes.claude_image_counts == [2]
    assert job_row(factory, job.id).llm_provider == "anthropic"


@needs_ffmpeg
def test_a_silent_sample_or_no_elevenlabs_key_still_learns_from_the_stills(
    factory, storage, tmp_path, fakes, monkeypatch
):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "")
    user = add_user(factory)
    video_id = sample_video(factory, storage, tmp_path, user)
    llm = SeeingLlm()
    assert run_learn(factory, storage, video_id, user.id, llm).status == "done"
    assert fakes.stt_requests == [] and "(video mẫu không có lời nói)" in llm.calls[0][0]


@needs_ffmpeg
@pytest.mark.parametrize("mode", ["no_permission", "quota"])
def test_elevenlabs_refusing_the_words_still_learns_from_the_stills(factory, storage, tmp_path, fakes, mode):
    """The words are optional: a key without the speech_to_text permission, or out of quota, is as no key at all."""
    fakes.stt_mode = mode
    user = add_user(factory)
    video_id = sample_video(factory, storage, tmp_path, user)
    llm = SeeingLlm()
    job = run_learn(factory, storage, video_id, user.id, llm)
    assert job.status == "done", (job.error, job.error_detail)
    assert len(fakes.stt_requests) == 1 and "(video mẫu không có lời nói)" in llm.calls[0][0]
    assert loaded(factory, video_id)[1].transcript == ""


def test_a_key_missing_the_speech_permission_is_named_as_such():
    body = '{"detail":{"status":"missing_permissions","message":"missing the permission speech_to_text"}}'
    assert stt._error(401, body).message == (
        "Key ElevenLabs chưa bật quyền Speech to Text: bật quyền này cho key ở trang ElevenLabs"
    )
    assert stt._error(401, '{"detail":{"status":"invalid_api_key"}}').message.startswith("Key ElevenLabs không hợp lệ")


@needs_ffmpeg
def test_failures_say_what_went_wrong(factory, storage, tmp_path, fakes):
    user = add_user(factory)
    long_id = sample_video(factory, storage, tmp_path, user, seconds=181)
    failed = run_learn(factory, storage, long_id, user.id, SeeingLlm())
    assert failed.status == "failed" and "từ 3 giây đến 3 phút" in failed.error

    video_id = sample_video(factory, storage, tmp_path, user, seconds=4)

    def refusing(prompt, label, images=()):
        raise ClaudeError("Claude từ chối yêu cầu: có thể model không đọc được ảnh")

    failed = run_learn(factory, storage, video_id, user.id, refusing)
    assert failed.status == "failed" and "không đọc được ảnh" in failed.error
    broken = run_learn(factory, storage, video_id, user.id, SeeingLlm(["không phải JSON", "vẫn không"]))
    assert broken.status == "failed" and "không đúng định dạng" in broken.error
    assert not loaded(factory, video_id)[0].has_script


def test_a_model_that_refuses_images_is_named(monkeypatch):
    from reels_api import llm

    target = llm.Target(
        provider="deepseek",
        name="DeepSeek",
        kind=llm.OPENAI,
        key="k",
        base_url="https://example.invalid",
        model="deepseek-chat",
    )

    def refuse(target, prompt, label, images=()):
        raise ClaudeError("DeepSeek từ chối yêu cầu (HTTP 400)")

    monkeypatch.setattr(llm, "_openai", refuse)
    with pytest.raises(ClaudeError) as caught:
        llm.complete(target, "x", "t", [b"jpeg"])
    assert "không đọc được ảnh" in caught.value.message
    with pytest.raises(ClaudeError) as caught:
        llm.complete(target, "x", "t")
    assert "không đọc được ảnh" not in caught.value.message


# --- API ---


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


@needs_ffmpeg
def test_an_uploaded_sample_makes_a_draft_with_a_learn_job(an, db, me, tmp_path):
    data = clip_bytes(tmp_path, seconds=5, size="720x1280", rate=10)
    response = an.post(
        "/api/references/videos",
        data={"topic": "  3 món  tốt cho tim ", "knowledge_topic_id": str(first_topic(db).id), "mode": "review"},
        files={"file": ("mau.mp4", data, "video/mp4")},
    )
    assert response.status_code == 201, response.text
    video = response.json()
    assert video["topic"] == "3 món tốt cho tim" and video["status"] == "queued"
    assert video["reference"]["mode"] == "review" and video["reference"]["mode_label"] == "Duyệt phân tích trước"
    assert video["reference"]["source_name"] == "mau.mp4" and not video["reference"]["awaiting_review"]
    job = db.scalar(select(Job).where(Job.video_id == video["id"]))
    assert job.kind == "learn"
    sample = db.get(VideoReference, db.get(Video, video["id"]).reference_id)
    assert sample.video_key and sample.seconds == pytest.approx(5, abs=0.2)


def test_a_pasted_link_is_only_checked_by_the_request(an, db, me):
    response = an.post(
        "/api/references/videos",
        data={
            "topic": "tim mạch",
            "knowledge_topic_id": str(first_topic(db).id),
            "url": " https://www.tiktok.com/@a/video/1 ",
        },
    )
    assert response.status_code == 201, response.text
    sample = db.get(VideoReference, response.json()["reference"]["id"])
    assert sample.source_url == "https://www.tiktok.com/@a/video/1" and sample.video_key is None


@needs_ffmpeg
def test_what_the_form_refuses(an, db, me, tmp_path):
    group = str(first_topic(db).id)
    form = {"topic": "tim mạch", "knowledge_topic_id": group}
    data = clip_bytes(tmp_path, seconds=2, size="720x1280", rate=10)
    cases = [
        ({**form, "url": "https://a.vn/v.mp4"}, {"file": ("v.mp4", data, "video/mp4")}, 422, "chỉ một trong hai"),
        (form, None, 422, "chỉ một trong hai"),
        ({**form, "topic": " "}, None, 422, "chủ đề"),
        ({**form, "mode": "other", "url": "https://a.vn/v.mp4"}, None, 422, "Cách làm"),
        ({**form, "url": "ftp://a.vn/v.mp4"}, None, 422, "http"),
        ({**form, "mode": "reuse"}, None, 422, "video mẫu đã học"),
        (form, {"file": ("v.mp4", data, "video/mp4")}, 415, "từ 3 giây"),
        (form, {"file": ("v.mp4", b"not a video at all", "video/mp4")}, 415, "MP4"),
    ]
    for fields, files, status, message in cases:
        response = an.post("/api/references/videos", data=fields, files=files)
        assert response.status_code == status, (fields, response.text)
        assert message in response.json()["message"], response.text


def test_samples_are_listed_edited_and_deleted(an, db, me, storage):
    sample = VideoReference(source_name="mau.mp4", created_by_id=me.id, analysis="Hook: cũ", frames=[])
    db.add(sample)
    db.commit()
    storage.save_bytes(f"references/{sample.id}/frame-a.jpg", b"jpeg")
    listed = an.get("/api/references").json()
    assert [item["id"] for item in listed] == [sample.id] and listed[0]["analyzed"]
    edited = an.patch(f"/api/references/{sample.id}", json={"analysis": " Hook: mới \r\n"})
    assert edited.status_code == 200 and edited.json()["analysis"] == "Hook: mới"
    assert an.patch(f"/api/references/{sample.id}", json={"analysis": " "}).status_code == 422
    made = an.post(
        "/api/references/videos",
        data={
            "topic": "gan",
            "knowledge_topic_id": str(first_topic(db).id),
            "mode": "reuse",
            "reference_id": str(sample.id),
        },
    )
    assert made.status_code == 201, made.text
    # While its learn job waits, the sample can be neither edited nor deleted.
    assert an.patch(f"/api/references/{sample.id}", json={"analysis": "x"}).status_code == 409
    assert an.delete(f"/api/references/{sample.id}").status_code == 409
    db.execute(delete(Job))
    db.commit()
    assert an.delete(f"/api/references/{sample.id}").status_code == 200
    assert not storage.exists(f"references/{sample.id}/frame-a.jpg")
    db.expire_all()
    video = db.get(Video, made.json()["id"])
    assert video.reference_id is None and an.get(f"/api/videos/{video.id}").json()["reference"]["id"] is None


def test_write_script_on_a_sample_video_queues_a_learn_job(an, db, me):
    sample = VideoReference(source_name="mau.mp4", created_by_id=me.id, analysis="Hook")
    db.add(sample)
    db.flush()
    video = Video(
        topic="tim",
        knowledge_topic_id=first_topic(db).id,
        created_by_id=me.id,
        reference_id=sample.id,
        reference_mode="review",
    )
    db.add(video)
    db.commit()
    assert an.get(f"/api/videos/{video.id}").json()["reference"]["awaiting_review"]
    response = an.post(f"/api/videos/{video.id}/script")
    assert response.status_code == 200, response.text
    assert db.scalar(select(Job.kind).where(Job.video_id == video.id)) == "learn"


def test_the_learn_prompts_are_edited_on_knowledge_and_empty_means_default(an, db, me):
    topic = first_topic(db)
    payload = an.get("/api/knowledge").json()
    assert "[chủ đề]" in payload["default_learn_prompt"] and payload["default_analyze_prompt"]
    saved = an.patch(f"/api/knowledge/topics/{topic.id}", json={"learn_prompt": " Học theo [chủ đề] "})
    assert saved.status_code == 200
    assert next(t for t in saved.json()["topics"] if t["id"] == topic.id)["learn_prompt"] == "Học theo [chủ đề]"
    cleared = an.patch(f"/api/knowledge/topics/{topic.id}", json={"learn_prompt": ""})
    assert next(t for t in cleared.json()["topics"] if t["id"] == topic.id)["learn_prompt"] == ""
