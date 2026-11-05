"""A scene's own transition into it and its colour preset, set from the studio."""

import pytest
from conftest import login, make_user, make_video
from test_text_position import scene_json
from test_voice import first_scene, render
from worker_helpers import add_user, committed  # noqa: F401  (fixture)

from reels_api.storage import DirectoryStorage
from reels_api.videos import render_signature, split_scenes


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def test_a_scene_takes_a_transition_and_a_colour_and_gives_them_back(an, db, me, storage):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    signature = render_signature(video, *split_scenes(db, video))
    before = scene_json(an.get(f"/api/videos/{video.id}").json(), scene.id)
    assert (before["transition"], before["color"]) == (None, None)

    saved = scene_json(
        an.patch(f"/api/scenes/{scene.id}", json={"transition": "circle", "color": "warm"}).json(), scene.id
    )
    assert (saved["transition"], saved["color"]) == ("circle", "warm")
    db.refresh(video)
    assert render_signature(video, *split_scenes(db, video)) != signature

    back = scene_json(an.patch(f"/api/scenes/{scene.id}", json={"transition": None, "color": None}).json(), scene.id)
    assert (back["transition"], back["color"]) == (None, None)
    db.refresh(video)
    # Back to the video's transition and the picture as shot, the MP4 made before still counts as current.
    assert render_signature(video, *split_scenes(db, video)) == signature


@pytest.mark.parametrize(("field", "value"), [("transition", "spin"), ("color", "neon"), ("color", 3)])
def test_an_unknown_preset_is_refused(an, db, me, storage, field, value):
    video = make_video(db, storage, me)
    refused = an.patch(f"/api/scenes/{first_scene(db, video).id}", json={field: value})
    assert refused.status_code == 422 and "không hợp lệ" in refused.json()["message"]


@pytest.mark.parametrize("field", ["transition", "color"])
def test_the_title_scene_has_neither(an, db, me, storage, field):
    """No scene comes before the title; and its first frame stays the thumbnail, drawn without a colour preset."""
    video = make_video(db, storage, me)
    title, _ = split_scenes(db, video)
    refused = an.patch(f"/api/scenes/{title.id}", json={field: "fade" if field == "transition" else "warm"})
    assert refused.status_code == 422 and "Cảnh tiêu đề" in refused.json()["message"]


def test_the_part_after_a_split_cuts_in_and_keeps_the_colour(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    scene = first_scene(db, video)
    an.patch(f"/api/scenes/{scene.id}", json={"color": "mono", "transition": "zoom"})
    first, rest = an.post(f"/api/scenes/{scene.id}/split", json={"at": 2}).json()["scenes"]
    assert (first["transition"], first["color"]) == ("zoom", "mono")
    # The same picture goes on: a transition there would show a jump, so the rest follows with a cut.
    assert (rest["transition"], rest["color"]) == ("cut", "mono")


def test_the_render_job_hands_each_scene_its_effects(committed, tmp_path, monkeypatch):  # noqa: F811
    from reels_api import jobs
    from reels_render import RenderError

    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    with committed() as db:
        video = make_video(db, storage, user, scene_count=2, seconds=2)
        video.voice_enabled = False
        first = first_scene(db, video)
        first.transition, first.color = "flash", "cinematic"
        db.commit()
        video_id = video.id
    handed = []

    def fake_render(script, output, **_):
        handed.extend((scene.transition, scene.color) for scene in script.all_scenes)
        raise RenderError("dừng trước FFmpeg")

    monkeypatch.setattr(jobs, "render_video", fake_render)
    render(committed, storage, video_id, user.id)
    assert handed == [(None, None), ("flash", "cinematic"), (None, None)]
