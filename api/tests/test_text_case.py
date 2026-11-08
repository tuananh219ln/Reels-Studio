""" "Dạng chữ": a video's scenes and its title each drawn as typed or in capitals; capitals are the original template
and what every video made before the option has."""

import pytest
from conftest import first_topic, login, make_user, make_video
from test_text_position import scene_json
from test_voice import first_scene

from reels_api import render_nodes, video_options
from reels_api.videos import render_signature, split_scenes

DEFAULTS_URL = "/api/settings/video-defaults"


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def test_capitals_stay_the_default_and_leave_earlier_videos_alone(db, me, storage):
    video = make_video(db, storage, me)
    options = video_options.render_options(video)
    assert (options.text_case, options.title_text_case) == ("upper", "upper")
    video.options = {"text_style": "red"}  # saved before the option existed
    signature = video_options.look_signature(video)
    assert "text_case" not in signature and "title_text_case" not in signature
    video.options = {"text_style": "red", "text_case": "keep"}
    assert video_options.look_signature(video)["text_case"] == "keep"


def test_keeping_the_scenes_text_redraws_their_previews_only_and_outdates_the_mp4(an, db, me, storage):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    title, _ = split_scenes(db, video)
    signature = render_signature(video, *split_scenes(db, video))
    before = an.get(f"/api/videos/{video.id}").json()
    box = an.get(scene_json(before, scene.id)["textbox_url"]).content

    saved = an.patch(f"/api/videos/{video.id}", json={"options": {"text_case": "keep"}}).json()
    assert saved["options"]["text_case"] == "keep" and saved["options"]["title_text_case"] == "upper"
    after = scene_json(saved, scene.id)
    assert after["preview_url"] != scene_json(before, scene.id)["preview_url"]
    assert an.get(after["textbox_url"]).content != box, "the box is drawn as typed"
    assert saved["title_scene"]["preview_url"] == before["title_scene"]["preview_url"], "the title keeps capitals"
    db.refresh(video)
    assert render_signature(video, *split_scenes(db, video)) != signature
    assert video_options.render_options(video).text_case == "keep"

    an.patch(f"/api/videos/{video.id}", json={"options": {"text_case": "upper"}})
    db.refresh(video)
    assert render_signature(video, *split_scenes(db, video)) == signature
    assert title.id == before["title_scene"]["id"]


def test_the_title_has_a_case_of_its_own(an, db, me, storage):
    video = make_video(db, storage, me)
    before = an.get(f"/api/videos/{video.id}").json()
    saved = an.patch(f"/api/videos/{video.id}", json={"options": {"title_text_case": "keep"}}).json()
    assert saved["title_scene"]["preview_url"] != before["title_scene"]["preview_url"]
    assert saved["scenes"][0]["preview_url"] == before["scenes"][0]["preview_url"]
    db.refresh(video)
    assert video_options.render_options(video).title_text_case == "keep"


@pytest.mark.parametrize(("field", "label"), [("text_case", "Dạng chữ"), ("title_text_case", "Dạng chữ tiêu đề")])
def test_an_unknown_case_is_refused(an, db, me, storage, field, label):
    video = make_video(db, storage, me)
    refused = an.patch(f"/api/videos/{video.id}", json={"options": {field: "lower"}})
    assert refused.status_code == 422 and label in refused.json()["message"]
    assert an.put(DEFAULTS_URL, json={"values": {field: "lower"}}).status_code == 422


def test_the_team_default_case_reaches_a_new_video(an, db):
    saved = an.put(DEFAULTS_URL, json={"values": {"text_case": "keep", "title_text_case": "keep"}}).json()
    assert (saved["text_case"], saved["title_text_case"]) == ("keep", "keep")
    created = an.post("/api/videos", json={"topic": "tim mạch", "knowledge_topic_id": first_topic(db).id}).json()
    assert (created["options"]["text_case"], created["options"]["title_text_case"]) == ("keep", "keep")


def test_a_text_layer_follows_the_scenes_case(an, db, me, storage):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    added = an.post("/api/layers", json={"scene_id": scene.id, "kind": "text", "text": "Giàu *canxi*"}).json()
    (layer,) = scene_json(added, scene.id)["layers"]
    picture = an.get(layer["image_url"]).content

    saved = an.patch(f"/api/videos/{video.id}", json={"options": {"text_case": "keep"}}).json()
    (kept,) = scene_json(saved, scene.id)["layers"]
    assert kept["image_url"] != layer["image_url"] and an.get(kept["image_url"]).content != picture


def test_a_render_machine_is_sent_the_case_only_when_text_is_kept(db, me, storage):
    video = make_video(db, storage, me)
    # A machine on older code then refuses a video it would draw in capitals, instead of rendering it wrong.
    assert "text_case" not in render_nodes.options_dict(video_options.render_options(video))
    video.options = {"text_case": "keep"}
    sent = render_nodes.options_dict(video_options.render_options(video))
    assert sent["text_case"] == "keep" and "title_text_case" not in sent
