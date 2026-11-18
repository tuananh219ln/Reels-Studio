"""How much of each AI service's allowance is used, on Cài đặt › Nguồn tư liệu (service_usage.py)."""

from datetime import UTC, datetime, timedelta

import pytest
from conftest import login, make_user
from sqlalchemy import func, select
from test_image_jobs import build, run_image_job
from worker_helpers import add_user, committed  # noqa: F401  (fixture)

from reels_api import service_usage
from reels_api.models import AiServiceCall

USAGE = "/api/settings/sources/usage"


@pytest.fixture(autouse=True)
def no_kept_answers():
    service_usage.clear_cache()
    yield
    service_usage.clear_cache()


@pytest.fixture
def an(client, db):
    make_user(db)
    login(client)
    return client


# --- ElevenLabs: exact, from its subscription ---


def test_elevenlabs_shows_the_characters_used_of_the_plan_and_when_they_reset(an, fakes):
    usage = an.get(USAGE).json()["elevenlabs"]
    assert usage["configured"] and usage["ok"]
    assert (usage["tier"], usage["characters_used"], usage["characters_limit"]) == ("creator", 12_345, 100_000)
    assert usage["resets_at"] == datetime.fromtimestamp(1795000000, UTC).isoformat().replace("+00:00", "Z")


def test_an_elevenlabs_key_without_user_read_says_which_permission_is_missing(an, fakes):
    fakes.elevenlabs_usage_mode = "no_permission"
    usage = an.get(USAGE).json()["elevenlabs"]
    assert usage["ok"] is False and "User › Read" in usage["error"]
    assert "characters_used" not in usage


def test_without_an_elevenlabs_key_nothing_is_asked(an, fakes, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "")
    assert an.get(USAGE).json()["elevenlabs"]["configured"] is False
    assert "elevenlabs" not in fakes.usage_requests


# --- Cloudflare: today's neurons, or the app's own count ---


def test_cloudflare_shows_todays_neurons_and_the_answer_is_kept_until_asked_again(an, fakes):
    usage = an.get(USAGE).json()["cloudflare"]
    assert usage["ok"] and (usage["neurons_used"], usage["neurons_limit"]) == (1234.5, 10_000)
    today = datetime.now(UTC).date()
    assert fakes.usage_requests.count(f"cloudflare:{today.isoformat()}") == 1
    assert usage["resets_at"] == f"{(today + timedelta(days=1)).isoformat()}T00:00:00Z"

    fakes.cf_neurons_today = 2000
    assert an.get(USAGE).json()["cloudflare"]["neurons_used"] == 1234.5  # kept a few minutes
    assert an.get(USAGE, params={"fresh": "true"}).json()["cloudflare"]["neurons_used"] == 2000
    assert len([r for r in fakes.usage_requests if r.startswith("cloudflare")]) == 2


def test_a_cloudflare_token_without_analytics_falls_back_to_the_apps_own_count(an, db, fakes):
    fakes.cf_analytics_mode = "no_permission"
    for _ in range(3):
        service_usage.record(db, "cloudflare", "image")
    service_usage.record(db, "cloudflare", "edit")
    db.commit()
    usage = an.get(USAGE).json()["cloudflare"]
    assert usage["ok"] is False and "Account Analytics" in usage["error"]
    assert usage["calls_today"] == {"image": 3, "edit": 1, "voice": 0}


# --- Gemini: the app's own count, by Pacific day ---


def test_gemini_counts_todays_requests_by_kind_and_links_to_ai_studio(an, db, fakes):
    service_usage.record(db, "gemini", "image")
    service_usage.record(db, "gemini", "voice")
    service_usage.record(db, "gemini", "voice")
    db.add(AiServiceCall(service="gemini", kind="image", created_at=datetime.now(UTC) - timedelta(days=2)))
    db.commit()
    usage = an.get(USAGE).json()["gemini"]
    assert usage["configured"] and usage["calls_today"] == {"image": 1, "edit": 0, "voice": 2}
    assert usage["usage_url"] == "https://aistudio.google.com/usage"


@pytest.mark.parametrize(
    ("now", "start", "reset"),
    [
        # 17:00 in Vietnam on 18/11 is 02:00 in California: the day began at 08:00 UTC, resets at 15:00 Vietnam time.
        ("2026-11-18T10:00:00", "2026-11-18T08:00:00", "2026-11-19T08:00:00Z"),
        # 1/11/2026 is the day California's clocks go back: it began in summer time and ends in winter time.
        ("2026-11-01T12:00:00", "2026-11-01T07:00:00", "2026-11-02T08:00:00Z"),
    ],
)
def test_the_gemini_day_follows_pacific_midnight(db, now, start, reset):
    moment = datetime.fromisoformat(now).replace(tzinfo=UTC)
    assert service_usage.pacific_day_start(moment) == datetime.fromisoformat(start).replace(tzinfo=UTC)
    assert service_usage.gemini(db, now=moment)["resets_at"] == reset


def test_rows_older_than_five_weeks_go_when_a_new_one_is_recorded(db):
    db.add(AiServiceCall(service="gemini", kind="image", created_at=datetime.now(UTC) - timedelta(days=40)))
    db.flush()
    service_usage.record(db, "gemini", "image")
    db.flush()
    assert db.scalar(select(func.count()).select_from(AiServiceCall)) == 1


# --- The jobs count their requests ---


@pytest.mark.parametrize("provider", ["cloudflare", "gemini"])
def test_the_image_job_counts_one_request_per_photo_for_its_provider(committed, fakes, storage, monkeypatch, provider):  # noqa: F811
    monkeypatch.setenv("IMAGE_GEN_PROVIDER", provider)
    user = add_user(committed)
    video_id = build(committed, storage, user)

    job = run_image_job(committed, storage, video_id, user.id)

    assert job.status == "done"
    with committed() as db:
        counts = service_usage.calls_since(db, provider, datetime.now(UTC) - timedelta(hours=1))
    assert counts == {"image": 4, "edit": 0, "voice": 0}  # title + 3 scenes
