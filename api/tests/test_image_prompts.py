"""AI photo prompts: English prompts from the script (the title scene included) plus the team's shared style."""

import json

import pytest
from conftest import first_topic, login, make_user
from sqlalchemy import select
from test_image_jobs import build, load_scenes, run_image_job
from worker_helpers import add_user, committed  # noqa: F401  (fixture)

from reels_api import image_style
from reels_api.claude import OUTPUT_FORMAT, parse_output
from reels_api.jobs import save_script
from reels_api.models import Scene, Video


@pytest.fixture(autouse=True)
def gemini(monkeypatch):
    monkeypatch.setenv("IMAGE_GEN_PROVIDER", "gemini")


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def answer(**changes) -> str:
    data = {
        "titles": ["5 MÓN GIÚP XƯƠNG CHẮC"],
        "title_image_prompt": "Five calcium-rich Vietnamese dishes on one table, top-down view",
        "scenes": [{"text": "Cá nhỏ", "seconds": 4, "image_prompt": "A plate of crispy fried anchovies"}],
    }
    data.update(changes)
    return json.dumps(data, ensure_ascii=False)


# --- The script ---


def test_the_title_scene_gets_its_own_image_prompt(db, me):
    video = Video(topic="canxi", knowledge_topic_id=first_topic(db).id, has_script=False, created_by_id=me.id)
    db.add(video)
    db.flush()
    save_script(db, video, parse_output(answer()))
    db.commit()
    title = db.scalar(select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(True)))
    assert title.image_prompt == "Five calcium-rich Vietnamese dishes on one table, top-down view"


def test_a_script_without_a_title_image_prompt_still_parses():
    data = json.loads(answer())
    del data["title_image_prompt"]
    assert parse_output(json.dumps(data)).title_image_prompt == ""


def test_the_format_asks_for_english_image_prompts_that_describe_only_the_content():
    example = json.loads(OUTPUT_FORMAT[OUTPUT_FORMAT.index("{") :])
    prompts = [example["title_image_prompt"], *(scene["image_prompt"] for scene in example["scenes"])]
    assert all(prompt.isascii() and prompt for prompt in prompts), prompts
    # Light, frame and "no text" come from the shared style, not from each prompt.
    assert not any(word in prompt.lower() for prompt in prompts for word in ("9:16", "natural light", "no text"))
    assert '"title_image_prompt"' in OUTPUT_FORMAT and "tiếng Anh" in OUTPUT_FORMAT


# --- The shared style, added by the image job ---


def test_the_job_adds_the_default_style_to_every_prompt(committed, fakes, storage):
    user = add_user(committed)
    video_id = build(committed, storage, user)
    job = run_image_job(committed, storage, video_id, user.id)
    assert job.status == "done", job.error
    assert fakes.image_gen_prompts[1] == f"Ảnh món 1 trên bàn gỗ. {image_style.DEFAULT}"
    # The title scene without a prompt of its own still falls back to its first line, styled too.
    assert fakes.image_gen_prompts[0] == f"5 MÓN GIÚP. {image_style.DEFAULT}"


def test_the_team_style_replaces_the_default_and_an_empty_one_adds_nothing(committed, fakes, storage):
    user = add_user(committed)
    video_id = build(committed, storage, user)
    with committed() as db:
        image_style.save(db, "  watercolor illustration, pastel colours  ", user.id)
        db.commit()
    run_image_job(committed, storage, video_id, user.id)
    assert fakes.image_gen_prompts[1] == "Ảnh món 1 trên bàn gỗ. watercolor illustration, pastel colours"

    with committed() as db:
        image_style.save(db, "", user.id)
        for scene in db.scalars(select(Scene).where(Scene.video_id == video_id)):
            scene.image_key = None
        db.commit()
    fakes.image_gen_prompts.clear()
    run_image_job(committed, storage, video_id, user.id)
    assert fakes.image_gen_prompts[1] == "Ảnh món 1 trên bàn gỗ"
    assert all(scene.image_key for scene in load_scenes(committed, video_id))


def test_the_style_is_edited_on_the_sources_page(an):
    before = an.get("/api/settings/sources").json()["ai_style"]
    assert before == {"value": image_style.DEFAULT, "default": image_style.DEFAULT, "custom": False}

    saved = an.put("/api/settings/image-style", json={"style": "  soft studio light, no text  "})
    assert saved.status_code == 200
    assert saved.json()["ai_style"] == {
        "value": "soft studio light, no text",
        "default": image_style.DEFAULT,
        "custom": True,
    }

    assert an.put("/api/settings/image-style", json={"style": ""}).json()["ai_style"]["value"] == ""
    reset = an.put("/api/settings/image-style", json={"style": None}).json()["ai_style"]
    assert (reset["value"], reset["custom"]) == (image_style.DEFAULT, False)

    refused = an.put("/api/settings/image-style", json={"style": "a" * (image_style.MAX_LENGTH + 1)})
    assert refused.status_code == 422 and "quá dài" in refused.json()["message"]
