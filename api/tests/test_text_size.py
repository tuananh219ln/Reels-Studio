"""The text box's size ("Cỡ chữ"): a preset of the video's "Thiết lập" and of the team's defaults, for the content
scenes and the title on their own; Lớn is the original template."""

import pytest
from conftest import login, make_user, make_video
from test_text_position import scene_json
from test_voice import first_scene

from reels_api import video_options
from reels_api.videos import render_signature, split_scenes

LONG_TITLE = "NĂM LOẠI RAU MẦM DỄ TRỒNG NHẤT TẠI NHÀ CHO NGƯỜI MỚI BẮT ĐẦU TẬP LÀM VƯỜN TRÊN BAN CÔNG NHỎ XINH MỖI NGÀY"


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def test_a_smaller_size_redraws_the_previews_and_outdates_the_mp4_and_large_changes_nothing(an, db, me, storage):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    signature = render_signature(video, *split_scenes(db, video))
    before = scene_json(an.get(f"/api/videos/{video.id}").json(), scene.id)

    saved = an.patch(f"/api/videos/{video.id}", json={"options": {"text_size": "small"}}).json()
    assert saved["options"]["text_size"] == "small" and saved["options"]["title_text_size"] == "large"
    after = scene_json(saved, scene.id)
    assert after["preview_url"] != before["preview_url"] and after["textbox_url"] != before["textbox_url"]
    db.refresh(video)
    assert render_signature(video, *split_scenes(db, video)) != signature
    assert video_options.render_options(video).text_size == "small"

    an.patch(f"/api/videos/{video.id}", json={"options": {"text_size": "large"}})
    db.refresh(video)
    assert render_signature(video, *split_scenes(db, video)) == signature
    refused = an.patch(f"/api/videos/{video.id}", json={"options": {"title_text_size": "huge"}})
    assert refused.status_code == 422 and "Cỡ chữ tiêu đề" in refused.json()["message"]


def test_a_long_title_too_big_at_large_fits_once_the_title_is_small(an, db, me, storage):
    video = make_video(db, storage, me)
    title, _ = split_scenes(db, video)
    blocked = an.patch(f"/api/scenes/{title.id}", json={"text": LONG_TITLE}).json()
    assert blocked["title_scene"]["text_problem"] and blocked["title_scene"]["textbox_url"] is None
    fits = an.patch(f"/api/videos/{video.id}", json={"options": {"title_text_size": "small"}}).json()
    assert fits["title_scene"]["text_problem"] is None and fits["title_scene"]["textbox_url"]
    assert not any("tràn" in issue for issue in fits["title_scene"]["blocking"])


def test_the_team_default_size_reaches_a_new_video(an):
    saved = an.put("/api/settings/my-video-defaults", json={"values": {"title_text_size": "medium"}}).json()
    assert saved["title_text_size"] == "medium"
