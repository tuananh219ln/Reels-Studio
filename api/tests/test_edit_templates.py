"""Edit templates ("Mẫu dựng"): the app's own ("Gợi ý của app", the studio's "Tự dựng"), the team's, saved from a
video, and the one put on every new video."""

import pytest
from conftest import first_topic, login, make_user, make_video
from sqlalchemy import select

from reels_api import autoedit
from reels_api.models import SceneLayer, SceneSound
from reels_api.videos import split_scenes


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def scenes_of(payload: dict) -> list[dict]:
    return [payload["title_scene"], *payload["scenes"]]


def test_the_apps_template_dresses_every_content_scene_and_the_last_one_ends_with_a_line(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=5)
    saved = an.post("/api/edit-templates/apply", json={"video_id": video.id, "template": "app"})
    assert saved.status_code == 200, saved.json()
    title, *scenes = scenes_of(saved.json())
    assert [scene["transition"] for scene in scenes] == ["zoom", "slide", "fade", "wipe", "zoom"]
    assert all([sound["sound"] for sound in scene["sounds"]] == ["whoosh"] for scene in scenes)
    assert [sound["sound"] for sound in title["sounds"]] == ["rise"]
    assert [layer["text"] for layer in scenes[-1]["layers"]] == ["Lưu video lại\n*để xem sau nhé!*"]
    assert all(scene["layers"] == [] for scene in scenes[:-1]) and title["transition"] is None

    # Applying it again adds nothing twice.
    again = scenes_of(an.post("/api/edit-templates/apply", json={"video_id": video.id, "template": "app"}).json())
    assert len(again[-1]["layers"]) == 1 and len(again[1]["sounds"]) == 1


def test_a_template_saved_from_a_video_carries_its_look_to_another(an, db, me, storage):
    source = make_video(db, storage, me, scene_count=3)
    title, scenes = split_scenes(db, source)
    for scene, transition in zip(scenes, ["circle", "flash", "circle"]):
        scene.transition, scene.color = transition, "warm"
    title.music_level = "low"
    db.add(SceneSound(scene_id=scenes[0].id, sound="pop", start=0.4, volume="loud"))
    db.add(SceneSound(scene_id=title.id, sound="ding", start=0, volume="normal"))
    db.add(
        SceneLayer(
            scene_id=scenes[-1].id, position=1, kind="sticker", sticker="heart", start=1, seconds=2, x=300, y=500
        )
    )
    db.commit()

    made = an.post("/api/edit-templates", json={"name": "Vườn nhà ấm", "video_id": source.id})
    assert made.status_code == 201, made.json()
    template = next(item for item in made.json()["templates"] if item["name"] == "Vườn nhà ấm")
    assert template["data"]["transitions"] == ["circle", "flash", "circle"]
    assert template["data"]["color"] == "warm" and template["data"]["title_music"] == "low"
    assert "Chuyển cảnh: Mở vòng tròn, Chớp trắng, Mở vòng tròn" in template["summary"]

    target = make_video(db, storage, me, scene_count=4)
    title2, *scenes2 = scenes_of(
        an.post("/api/edit-templates/apply", json={"video_id": target.id, "template": template["id"]}).json()
    )
    assert [scene["transition"] for scene in scenes2] == ["circle", "flash", "circle", "circle"]
    assert {scene["color"] for scene in scenes2} == {"warm"}
    assert [(s["sound"], s["start"], s["volume"]) for s in scenes2[0]["sounds"]] == [("pop", 0.4, "loud")]
    assert title2["music_level"] == "low" and [s["sound"] for s in title2["sounds"]] == ["ding"]
    assert [(layer["sticker"], layer["x"]) for layer in scenes2[-1]["layers"]] == [("heart", 300)]

    renamed = an.patch(f"/api/edit-templates/{template['id']}", json={"name": "Vườn ấm"}).json()
    assert any(item["name"] == "Vườn ấm" for item in renamed["templates"])
    assert an.post("/api/edit-templates", json={"name": "Vườn ấm", "video_id": source.id}).status_code == 422
    assert an.delete(f"/api/edit-templates/{template['id']}").status_code == 200


def test_a_template_with_nothing_to_carry_is_refused(an, db, me, storage):
    plain = make_video(db, storage, me)
    refused = an.post("/api/edit-templates", json={"name": "Trống", "video_id": plain.id})
    assert refused.status_code == 422 and "chưa có hiệu ứng" in refused.json()["message"]


def test_the_teams_default_template_dresses_a_hand_written_video_when_it_is_made(an, db, me):
    listing = an.put("/api/edit-templates/default", json={"template": "app"}).json()
    assert listing["default"] == "app"
    made = an.post(
        "/api/videos",
        json={"topic": "rau mầm", "knowledge_topic_id": first_topic(db).id, "mode": "manual", "script": "Một\n\nHai"},
    ).json()
    assert [scene["transition"] for scene in made["scenes"]] == ["zoom", "slide"]
    assert an.put("/api/edit-templates/default", json={"template": None}).json()["default"] is None
    assert an.put("/api/edit-templates/default", json={"template": 9999}).status_code == 422


def test_the_default_template_dresses_a_script_the_ai_wrote(db, me, storage):
    """The script job's save calls the same apply, after the scenes are written."""
    from reels_api.models import AppSetting

    db.add(AppSetting(key=autoedit.DEFAULT_KEY, value="app"))
    video = make_video(db, storage, me, scene_count=2)
    title, scenes = split_scenes(db, video)
    autoedit.apply_default(db, video)
    db.commit()
    assert [scene.transition for scene in scenes] == ["zoom", "slide"]
    assert db.scalars(select(SceneSound.sound).where(SceneSound.scene_id == title.id)).all() == ["rise"]


@pytest.mark.parametrize(
    "data",
    [
        {"transitions": ["spin"]},
        {"color": "neon"},
        {"scene_sounds": [{"sound": "laugh", "start": 0}]},
        {"end_layers": [{"kind": "text", "text": ""}]},
        {"title_music": "max"},
    ],
)
def test_a_bad_template_is_refused(data):
    with pytest.raises(ValueError):
        autoedit.parse(data)
