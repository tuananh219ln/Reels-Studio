"""Sound effects on a scene, a scene's own music level, and where the song starts, set from the studio."""

import pytest
from conftest import login, make_user, make_video, needs_ffmpeg
from test_text_position import scene_json
from test_voice import first_scene, render
from worker_helpers import add_user, committed  # noqa: F401  (fixture)

from reels_api.models import SceneSound
from reels_api.storage import DirectoryStorage
from reels_api.videos import render_signature, split_scenes


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def test_a_sound_is_added_changed_and_removed(an, db, me, storage):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    signature = render_signature(video, *split_scenes(db, video))

    added = an.post("/api/sounds", json={"scene_id": scene.id, "sound": "ding", "start": 1.5})
    assert added.status_code == 201, added.json()
    (sound,) = scene_json(added.json(), scene.id)["sounds"]
    assert {key: sound[key] for key in ("sound", "start", "volume")} == {
        "sound": "ding",
        "start": 1.5,
        "volume": "normal",
    }
    assert sound["url"] == "/api/sounds/library/ding.mp3"
    db.refresh(video)
    assert render_signature(video, *split_scenes(db, video)) != signature

    changed = scene_json(an.patch(f"/api/sounds/{sound['id']}", json={"volume": "loud", "start": 0}).json(), scene.id)
    assert (changed["sounds"][0]["volume"], changed["sounds"][0]["start"]) == ("loud", 0)
    assert an.delete(f"/api/sounds/{sound['id']}").status_code == 200
    db.refresh(video)
    assert render_signature(video, *split_scenes(db, video)) == signature


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"sound": "laugh"}, "Âm thanh"),
        ({"sound": "pop", "volume": "max"}, "Mức âm"),
        ({"sound": "pop", "start": 99}, "Giây"),
    ],
)
def test_a_bad_sound_is_refused(an, db, me, storage, body, message):
    video = make_video(db, storage, me)
    refused = an.post("/api/sounds", json={"scene_id": first_scene(db, video).id} | body)
    assert refused.status_code == 422 and message in refused.json()["message"], refused.json()


def test_a_scene_music_level_and_the_songs_start(an, db, me, storage):
    video = make_video(db, storage, me)
    title, scenes = split_scenes(db, video)
    signature = render_signature(video, title, scenes)
    payload = an.patch(f"/api/scenes/{title.id}", json={"music_level": "off"}).json()
    assert payload["title_scene"]["music_level"] == "off", "the title may be quiet too"
    assert an.patch(f"/api/scenes/{title.id}", json={"music_level": "max"}).status_code == 422
    an.patch(f"/api/scenes/{title.id}", json={"music_level": None})

    saved = an.patch(f"/api/videos/{video.id}", json={"music_start": 12.5}).json()
    assert saved["music_start"] == 12.5
    for bad in (-1, 1000, "x"):
        assert an.patch(f"/api/videos/{video.id}", json={"music_start": bad}).status_code == 422
    an.patch(f"/api/videos/{video.id}", json={"music_start": 0})
    db.refresh(video)
    assert render_signature(video, *split_scenes(db, video)) == signature


@needs_ffmpeg
def test_each_sound_can_be_heard_before_it_is_added(an):
    heard = an.get("/api/sounds/library/coin.mp3")
    assert heard.status_code == 200 and heard.headers["content-type"] == "audio/mpeg" and len(heard.content) > 1000
    assert an.get("/api/sounds/library/laugh.mp3").status_code == 404


def test_a_split_moves_the_sounds_after_the_cut_and_keeps_the_music_level(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    scene = first_scene(db, video)
    an.patch(f"/api/scenes/{scene.id}", json={"music_level": "low"})
    for start in (0.5, 3):
        an.post("/api/sounds", json={"scene_id": scene.id, "sound": "pop", "start": start})
    first, rest = an.post(f"/api/scenes/{scene.id}/split", json={"at": 2}).json()["scenes"]
    assert [sound["start"] for sound in first["sounds"]] == [0.5]
    assert [sound["start"] for sound in rest["sounds"]] == [1]
    assert rest["music_level"] == "low"


def test_the_render_job_hands_on_the_sounds_levels_and_the_songs_start(committed, tmp_path, monkeypatch):  # noqa: F811
    from reels_api import jobs
    from reels_render import RenderError

    user = add_user(committed)
    storage = DirectoryStorage(tmp_path / "storage")
    with committed() as db:
        video = make_video(db, storage, user, scene_count=2, seconds=2)
        video.voice_enabled, video.music_start = False, 3.0
        first = first_scene(db, video)
        first.music_level = "high"
        db.add(SceneSound(scene_id=first.id, sound="boom", start=1, volume="soft"))
        db.commit()
        video_id = video.id
    handed = {}

    def fake_render(script, output, **options):
        handed["scenes"] = [
            ([(s.sound, s.start, s.volume) for s in scene.sounds], scene.music_level) for scene in script.all_scenes
        ]
        handed["music_start"] = options.get("music_start")
        raise RenderError("dừng trước FFmpeg")

    monkeypatch.setattr(jobs, "render_video", fake_render)
    render(committed, storage, video_id, user.id)
    assert handed["scenes"] == [([], None), ([("boom", 1.0, "soft")], "high"), ([], None)]
    assert handed["music_start"] == 3.0
