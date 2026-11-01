"""The image job with Cloudflare Workers AI (FLUX.1 schnell) as the provider, against the fake Cloudflare.

Same shape as test_image_jobs.py (Gemini, the default provider): the job runs in process on committed rows.
"""

import pytest
from fake_services import IMAGE_GEN_CF_KEY
from PIL import Image
from test_image_jobs import build, load_scenes, run_image_job
from worker_helpers import add_user, committed  # noqa: F401  (fixture)

from reels_api import source_keys

MODEL_SOURCE = "ai:@cf/black-forest-labs/flux-1-schnell"


@pytest.fixture(autouse=True)
def cloudflare(monkeypatch):
    monkeypatch.setenv("IMAGE_GEN_PROVIDER", "cloudflare")


def test_the_job_fills_every_missing_scene_with_a_9_16_photo(committed, fakes, storage):  # noqa: F811
    user = add_user(committed)
    video_id = build(committed, storage, user)

    job = run_image_job(committed, storage, video_id, user.id)

    assert (job.status, job.error, job.image_calls) == ("done", None, 4)  # title + 3 scenes
    scenes = load_scenes(committed, video_id)
    assert all(scene.image_source == MODEL_SOURCE for scene in scenes)
    assert all(scene.image_error is None for scene in scenes)
    # The title scene has no image prompt: its first line of text is the prompt, as with Gemini.
    assert fakes.cf_image_gen_prompts[0] == "5 MÓN GIÚP"
    assert fakes.cf_image_gen_prompts[1:] == [f"Ảnh món {n} trên bàn gỗ" for n in (1, 2, 3)]
    assert fakes.image_gen_prompts == []
    # The fake answers 1024x1024 squares: what is stored was cut to the vertical frame.
    for scene in scenes:
        with Image.open(storage.path(scene.image_key)) as image:
            width, height = image.size
        assert abs(height * 9 - width * 16) <= 16, (width, height)


def test_scenes_with_a_photo_or_a_clip_are_skipped(committed, fakes, storage):  # noqa: F811
    user = add_user(committed)
    video_id = build(committed, storage, user, images=True)

    job = run_image_job(committed, storage, video_id, user.id)

    assert (job.status, job.image_calls) == ("done", 0)
    assert fakes.cf_image_gen_prompts == []


def test_the_daily_neurons_running_out_fails_the_job_and_keeps_the_finished_scenes(
    committed,  # noqa: F811
    fakes,
    storage,
):
    user = add_user(committed)
    video_id = build(committed, storage, user)
    fakes.cf_image_gen_ok_count = 2

    job = run_image_job(committed, storage, video_id, user.id)

    assert job.status == "failed" and "hạn mức" in (job.error or "")
    assert job.image_calls == 3  # two paid for, the third hit the limit
    scenes = load_scenes(committed, video_id)
    assert [bool(scene.image_key) for scene in scenes] == [True, True, False, False]


def test_a_wrong_token_fails_the_job_at_once(committed, fakes, storage, monkeypatch):  # noqa: F811
    user = add_user(committed)
    video_id = build(committed, storage, user)
    monkeypatch.setenv("IMAGE_GEN_CF_API_KEY", "not-the-fake-token")

    job = run_image_job(committed, storage, video_id, user.id)

    assert job.status == "failed" and "không hợp lệ" in (job.error or "")
    assert not any(scene.image_key for scene in load_scenes(committed, video_id))


def test_no_token_fails_with_a_clear_message(committed, fakes, storage, monkeypatch):  # noqa: F811
    user = add_user(committed)
    video_id = build(committed, storage, user)
    monkeypatch.setenv("IMAGE_GEN_CF_API_KEY", "")

    job = run_image_job(committed, storage, video_id, user.id)

    assert job.status == "failed"
    assert "Chưa có API token Cloudflare nên không tạo được ảnh AI" in (job.error or "")
    assert fakes.cf_image_gen_prompts == []


def test_no_account_id_fails_with_a_clear_message(committed, fakes, storage, monkeypatch):  # noqa: F811
    user = add_user(committed)
    video_id = build(committed, storage, user)
    monkeypatch.setenv("IMAGE_GEN_CF_ACCOUNT_ID", "")

    job = run_image_job(committed, storage, video_id, user.id)

    assert job.status == "failed" and "IMAGE_GEN_CF_ACCOUNT_ID" in (job.error or "")
    assert fakes.cf_image_gen_prompts == []


def test_a_token_saved_on_the_sources_page_makes_the_photos(committed, fakes, storage, monkeypatch):  # noqa: F811
    user = add_user(committed)
    video_id = build(committed, storage, user)
    monkeypatch.setenv("IMAGE_GEN_CF_API_KEY", "")
    with committed() as db:
        source_keys.save(db, "cloudflare", IMAGE_GEN_CF_KEY, user.id)
        db.commit()

    job = run_image_job(committed, storage, video_id, user.id)

    assert job.status == "done", job.error
    assert len(fakes.cf_image_gen_prompts) == 4


def test_a_refused_prompt_fails_only_its_scene(committed, fakes, storage):  # noqa: F811
    user = add_user(committed)
    video_id = build(committed, storage, user)
    fakes.cf_image_gen_refused = ["món 2"]

    job = run_image_job(committed, storage, video_id, user.id)

    assert (job.status, job.image_calls) == ("done", 4)
    scenes = load_scenes(committed, video_id)
    refused = scenes[2]  # title, scene 1, scene 2, scene 3
    assert refused.image_key is None and "từ chối" in (refused.image_error or "")
    assert all(scene.image_key for scene in scenes if scene.id != refused.id)
