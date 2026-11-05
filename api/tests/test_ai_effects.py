""" "AI gợi ý hiệu ứng": an option when making a video with AI; the same script call then picks each scene's
transition, colour, sounds and a line of text, from the render's named presets only."""

import json

import pytest
from conftest import first_topic, login, make_user, make_video
from fake_services import script_json
from sqlalchemy import select
from worker_helpers import add_job, add_user, committed, job_row  # noqa: F401  (fixture)

from reels_api import autoedit, jobs
from reels_api.models import SceneLayer, SceneSound, Video
from reels_api.storage import DirectoryStorage
from reels_api.videos import split_scenes


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def test_the_option_is_kept_on_the_video_only_for_an_ai_script(an, db):
    group = first_topic(db).id
    with_ai = an.post("/api/videos", json={"topic": "rau mầm", "knowledge_topic_id": group, "ai_effects": True}).json()
    assert with_ai["ai_effects"] is True and with_ai["active_job"]["kind"] == "script"
    by_hand = an.post(
        "/api/videos", json={"topic": "rau mầm", "knowledge_topic_id": group, "mode": "manual", "ai_effects": True}
    ).json()
    assert by_hand["ai_effects"] is False
    plain = an.post("/api/videos", json={"topic": "rau mầm", "knowledge_topic_id": group}).json()
    assert plain["ai_effects"] is False


def write_script(factory, storage, user, ai_effects: bool, reply: dict) -> tuple[int, list[str]]:
    with factory() as db:
        video = Video(
            topic="rau mầm",
            knowledge_topic_id=first_topic(db).id,
            has_script=False,
            created_by_id=user.id,
            ai_effects=ai_effects,
        )
        db.add(video)
        db.commit()
        video_id = video.id
    prompts = []

    def call(prompt: str, label: str) -> str:
        prompts.append(prompt)
        return json.dumps(reply, ensure_ascii=False)

    job_id = add_job(factory, video_id, user.id, kind="script", status="running")
    jobs.run_job(job_id, factory, storage, call)
    assert job_row(factory, job_id).status == "done"
    return video_id, prompts


def test_the_ai_picks_each_scenes_effects_and_what_is_not_a_preset_is_left_out(committed, tmp_path):
    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    reply = script_json("rau mầm", scene_count=3)
    reply["scenes"][0]["effects"] = {
        "transition": "circle",
        "color": "warm",
        "sounds": [{"sound": "ding", "start": 0.5}, {"sound": "laugh", "start": 1}],
        "layer": {"text": "Dễ *trồng*", "start": 0.5, "seconds": 2},
    }
    reply["scenes"][1]["effects"] = {"transition": "spin", "color": "neon", "sounds": "ding", "layer": None}
    reply["scenes"][2]["effects"] = "nhanh lên"
    video_id, prompts = write_script(committed, storage, user, True, reply)

    assert autoedit.EFFECTS_MARKER in prompts[0] and "circle (Mở vòng tròn)" in prompts[0]
    with committed() as db:
        _, scenes = split_scenes(db, db.get(Video, video_id))
        assert [(scene.transition, scene.color) for scene in scenes] == [("circle", "warm"), (None, None), (None, None)]
        sounds = db.scalars(select(SceneSound).where(SceneSound.scene_id == scenes[0].id)).all()
        assert [(sound.sound, sound.start) for sound in sounds] == [("ding", 0.5)]
        (layer,) = db.scalars(select(SceneLayer).where(SceneLayer.scene_id == scenes[0].id)).all()
        assert (layer.text, layer.style, layer.start) == ("Dễ *trồng*", "yellow", 0.5)


def test_without_the_option_the_prompt_asks_for_no_effects_and_none_are_put(committed, tmp_path):
    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    reply = script_json("rau mầm", scene_count=2)
    reply["scenes"][0]["effects"] = {"transition": "circle"}
    video_id, prompts = write_script(committed, storage, user, False, reply)
    assert autoedit.EFFECTS_MARKER not in prompts[0]
    with committed() as db:
        _, scenes = split_scenes(db, db.get(Video, video_id))
        assert scenes[0].transition is None


def test_at_most_two_lines_of_text_are_added_for_the_whole_video(db, me, storage):
    video = make_video(db, storage, me, scene_count=4)
    _, scenes = split_scenes(db, video)
    autoedit.apply_suggested(db, scenes, [{"layer": {"text": f"Dòng {n}"}} for n in range(4)])
    db.flush()
    assert db.query(SceneLayer).count() == 2
