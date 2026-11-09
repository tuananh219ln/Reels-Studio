"""Edit templates ("Mẫu dựng"): the app's own ("Gợi ý của app", the studio's "Tự dựng"), the team's, saved from a
video, and the one put on every new video."""

import pytest
from conftest import SCENE_TEXT, client_for, first_topic, login, make_user, make_video
from sqlalchemy import select

from reels_api import autoedit
from reels_api.models import SceneLayer, SceneSound, Video
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
    # A last scene with nothing on it is no call to action of its own, so the template's end line goes there.
    _, scenes = split_scenes(db, video)
    scenes[-1].text = ""
    db.commit()
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


def test_a_video_ending_on_its_call_to_action_keeps_it_without_the_templates_end_line(an, db, me, storage):
    """The script's last scene is its call to action: the template's end line never goes on it; the rest does."""
    video = make_video(db, storage, me, scene_count=3)
    title, *scenes = scenes_of(
        an.post("/api/edit-templates/apply", json={"video_id": video.id, "template": "app"}).json()
    )
    assert [scene["transition"] for scene in scenes] == ["zoom", "slide", "fade"]
    assert [sound["sound"] for sound in scenes[-1]["sounds"]] == ["whoosh"]
    assert scenes[-1]["layers"] == [] and scenes[-1]["text"] == SCENE_TEXT


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
    split_scenes(db, target)[1][-1].text = ""  # no call to action of its own: the end layer goes on it
    db.commit()
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


def make_hand_written(client, db, script="Một\n\nHai") -> dict:
    made = client.post(
        "/api/videos",
        json={"topic": "rau mầm", "knowledge_topic_id": first_topic(db).id, "mode": "manual", "script": script},
    )
    assert made.status_code == 201, made.json()
    return made.json()


def test_each_member_has_their_own_template_for_new_videos(an, app, db, me):
    """Part 1: the template new videos take is the signed-in member's own, nobody else's; none by default."""
    make_user(db, email="binh@doi.vn", name="Trần Bình")
    binh = client_for(app)
    login(binh, email="binh@doi.vn")
    assert an.get("/api/edit-templates").json()["default"] is None

    listing = an.put("/api/edit-templates/default", json={"template": "app"}).json()
    assert listing["default"] == "app"
    assert binh.get("/api/edit-templates").json()["default"] is None

    assert [scene["transition"] for scene in make_hand_written(an, db)["scenes"]] == ["zoom", "slide"]
    assert [scene["transition"] for scene in make_hand_written(binh, db)["scenes"]] == [None, None]

    binh.put("/api/edit-templates/default", json={"template": None})
    assert an.get("/api/edit-templates").json()["default"] == "app"
    assert an.put("/api/edit-templates/default", json={"template": None}).json()["default"] is None
    assert an.put("/api/edit-templates/default", json={"template": 9999}).status_code == 422


def test_the_default_template_dresses_a_script_the_ai_wrote_by_its_makers_choice(db, me, storage):
    """The script job's save calls the same apply, after the scenes are written, with the video's maker's template."""
    me.edit_template_default = "app"
    other = make_user(db, email="binh@doi.vn", name="Trần Bình")
    video = make_video(db, storage, me, scene_count=2)
    theirs = make_video(db, storage, other, scene_count=2)
    title, scenes = split_scenes(db, video)
    autoedit.apply_default(db, video)
    autoedit.apply_default(db, theirs)
    db.commit()
    assert [scene.transition for scene in scenes] == ["zoom", "slide"]
    assert db.scalars(select(SceneSound.sound).where(SceneSound.scene_id == title.id)).all() == ["rise"]
    assert [scene.transition for scene in split_scenes(db, theirs)[1]] == [None, None]


def test_a_video_whose_maker_is_unknown_takes_no_template(db, me):
    me.edit_template_default = "app"
    db.commit()
    unknown = Video(topic="nền", knowledge_topic_id=first_topic(db).id, created_by_id=None)
    assert autoedit.chosen_template(db, unknown) is None
    assert autoedit.chosen_template(db, Video(topic="của An", created_by_id=me.id))[0]["source"] == "member"


def test_removing_a_template_takes_it_off_every_members_new_videos(an, db, me, storage):
    source = make_video(db, storage, me, scene_count=2)
    _, scenes = split_scenes(db, source)
    scenes[0].transition = "circle"
    db.commit()
    made = an.post("/api/edit-templates", json={"name": "Tròn", "video_id": source.id}).json()
    template_id = next(item["id"] for item in made["templates"] if item["name"] == "Tròn")
    an.put("/api/edit-templates/default", json={"template": template_id})
    assert an.delete(f"/api/edit-templates/{template_id}").json()["default"] is None
    db.refresh(me)
    assert me.edit_template_default is None


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
