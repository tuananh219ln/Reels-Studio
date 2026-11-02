"""Choosing the AI image provider: the team's default on Cài đặt › Nguồn tư liệu, or one picked for a press."""

import pytest
from conftest import login, make_user, make_video
from sqlalchemy import select
from test_image_jobs import build, load_scenes
from worker_helpers import add_job, add_user, committed, job_row  # noqa: F401  (fixture)

from reels_api import image_providers, jobs
from reels_api.models import Job, Scene

CLOUDFLARE_SOURCE = "ai:@cf/black-forest-labs/flux-1-schnell"


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


# --- The default ---


def test_cloudflare_is_the_default_when_it_is_set_up(db, fakes):
    assert image_providers.default(db) == "cloudflare"


def test_gemini_is_the_default_when_only_it_is_set_up(db, fakes, monkeypatch):
    monkeypatch.setenv("IMAGE_GEN_CF_API_KEY", "")
    assert image_providers.default(db) == "gemini"


def test_the_env_provider_still_applies_until_the_team_chooses(db, fakes, me, monkeypatch):
    monkeypatch.setenv("IMAGE_GEN_PROVIDER", "gemini")
    assert image_providers.default(db) == "gemini"
    image_providers.save(db, "cloudflare", me.id)
    db.commit()
    assert image_providers.default(db) == "cloudflare"


def test_the_team_default_is_chosen_on_the_sources_page(an, fakes):
    before = an.get("/api/settings/sources").json()
    assert (before["ai_provider"], before["ai_provider_saved"]) == ("cloudflare", False)
    saved = an.put("/api/settings/image-provider", json={"provider": "gemini"})
    assert saved.status_code == 200
    assert (saved.json()["ai_provider"], saved.json()["ai_provider_saved"]) == ("gemini", True)
    offered = an.get("/api/settings/image-providers").json()
    assert offered["default"] == "gemini"
    assert offered["providers"] == [
        {"id": "cloudflare", "label": "Cloudflare", "configured": True},
        {"id": "gemini", "label": "Gemini", "configured": True},
    ]
    refused = an.put("/api/settings/image-provider", json={"provider": "midjourney"})
    assert refused.status_code == 422 and "không hợp lệ" in refused.json()["message"]


# --- A press ---


@pytest.mark.parametrize("path", ["videos", "scenes"])
def test_a_press_queues_the_chosen_provider_or_the_default(an, db, me, storage, fakes, path):
    video = make_video(db, storage, me, images=False)
    scene_id = db.scalar(select(Scene.id).where(Scene.video_id == video.id, Scene.is_title.is_(False)))
    url = f"/api/videos/{video.id}/image" if path == "videos" else f"/api/scenes/{scene_id}/image-ai"

    refused = an.post(url, params={"provider": "midjourney"})
    assert refused.status_code == 422 and "Nguồn ảnh AI không hợp lệ" in refused.json()["message"]

    chosen = an.post(url, params={"provider": "gemini"})
    assert chosen.status_code == 200 and chosen.json()["active_job"]["image_provider"] == "gemini"
    job = db.scalar(select(Job).where(Job.video_id == video.id))
    assert job.image_provider == "gemini"

    job.status = "done"
    db.commit()
    assert an.post(url).json()["active_job"]["image_provider"] == "cloudflare"  # the default


def test_the_job_uses_its_provider_whatever_the_default_is_now(committed, fakes, storage, monkeypatch):
    user = add_user(committed)
    video_id = build(committed, storage, user)
    monkeypatch.setenv("IMAGE_GEN_PROVIDER", "gemini")

    job_id = add_job(committed, video_id, user.id, kind="image", status="running", image_provider="cloudflare")
    jobs.run_job(job_id, committed, storage)

    assert job_row(committed, job_id).status == "done"
    assert all(scene.image_source == CLOUDFLARE_SOURCE for scene in load_scenes(committed, video_id))
    assert fakes.image_gen_prompts == []


def test_a_retry_keeps_the_provider_and_the_job_log_shows_it(an, db, me, storage, fakes):
    video = make_video(db, storage, me, images=False)
    failed = Job(video_id=video.id, kind="image", status="failed", created_by_id=me.id, image_provider="gemini")
    db.add(failed)
    db.commit()
    assert an.post(f"/api/jobs/{failed.id}/retry").status_code == 200
    assert db.scalar(select(Job).where(Job.retry_of_id == failed.id)).image_provider == "gemini"
    rows = [row for row in an.get("/api/jobs").json() if row["kind"] == "image"]
    assert {row["llm"] for row in rows} == {"Gemini"}
