"""The MCP editing tools: the studio's handlers, presets and locks, and the frames the assistant looks at to check
its work before saying a video is done."""

from conftest import clip_bytes, make_video, needs_ffmpeg
from sqlalchemy import select
from test_mcp import call, grant, mcp_client, payload  # noqa: F401  (mcp_client is a fixture)

from reels_api.models import Scene, SceneLayer, SceneSound, Video


def scenes_of(db, video) -> list[Scene]:
    db.expire_all()
    return db.scalars(
        select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)).order_by(Scene.position)
    ).all()


def test_the_assistant_reads_the_presets_it_may_use(mcp_client, db):  # noqa: F811
    _, _, tokens, _ = grant(mcp_client, db)
    options = payload(call(mcp_client, tokens["access_token"], "list_edit_options"))
    assert options["transitions"]["fade"] == "Mờ dần"
    assert "natural" in options["colors"] and "off" in options["music_levels"]
    assert "sale" in options["stickers"] and "ding" in options["sounds"]
    assert options["frame"] == {"width": 1080, "height": 1920}


def test_scene_effects_order_split_and_delete_use_the_studios_rules(mcp_client, db, storage):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    video = make_video(db, storage, user, scene_count=3)
    first, second, third = scenes_of(db, video)
    done = call(mcp_client, token, "set_scene_effects", scene_id=second.id, transition="zoom", color="vivid")
    assert not done.get("isError"), done
    db.refresh(second)
    assert (second.transition, second.color) == ("zoom", "vivid")
    assert not call(mcp_client, token, "set_scene_effects", scene_id=second.id, transition="default").get("isError")
    db.refresh(second)
    assert (second.transition, second.color) == (None, "vivid")
    assert call(mcp_client, token, "set_scene_effects", scene_id=second.id, color="neon-tím")["isError"]
    moved = call(mcp_client, token, "reorder_scenes", video_id=video.id, scene_ids=[third.id, first.id, second.id])
    assert not moved.get("isError"), moved
    assert [scene.id for scene in scenes_of(db, video)] == [third.id, first.id, second.id]
    split = call(mcp_client, token, "split_scene", scene_id=first.id, at=2)
    assert not split.get("isError"), split
    assert len(scenes_of(db, video)) == 4
    gone = call(mcp_client, token, "delete_scene", scene_id=third.id)
    assert not gone.get("isError"), gone
    assert third.id not in [scene.id for scene in scenes_of(db, video)]
    title = db.scalar(select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(True)))
    assert call(mcp_client, token, "delete_scene", scene_id=title.id)["isError"]


def test_layers_sounds_and_audio_settings(mcp_client, db, storage):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    video = make_video(db, storage, user, scene_count=2)
    scene = scenes_of(db, video)[0]
    text = call(mcp_client, token, "add_layer", scene_id=scene.id, kind="text", text="Chỉ 899K", style="yellow")
    assert not text.get("isError"), text
    sticker = call(mcp_client, token, "add_layer", scene_id=scene.id, kind="sticker", sticker="sale", y=400)
    assert not sticker.get("isError"), sticker
    assert call(mcp_client, token, "add_layer", scene_id=scene.id, kind="sticker", sticker="kim-cương")["isError"]
    layers = db.scalars(select(SceneLayer).where(SceneLayer.scene_id == scene.id).order_by(SceneLayer.position)).all()
    assert [(row.kind, row.text, row.sticker) for row in layers] == [("text", "Chỉ 899K", ""), ("sticker", "", "sale")]
    edited = call(mcp_client, token, "update_layer", layer_id=layers[0].id, text="Chỉ 799K", start=0.5)
    assert not edited.get("isError"), edited
    db.refresh(layers[0])
    assert (layers[0].text, layers[0].start) == ("Chỉ 799K", 0.5)
    assert not call(mcp_client, token, "delete_layer", layer_id=layers[1].id).get("isError")
    assert db.scalar(select(SceneLayer.id).where(SceneLayer.id == layers[1].id)) is None
    sound = call(mcp_client, token, "add_sound", scene_id=scene.id, sound="ding", start=0.5)
    assert not sound.get("isError"), sound
    row = db.scalar(select(SceneSound).where(SceneSound.scene_id == scene.id))
    assert (row.sound, row.start, row.volume) == ("ding", 0.5, "normal")
    assert not call(mcp_client, token, "delete_sound", sound_id=row.id).get("isError")
    audio = call(mcp_client, token, "set_audio", video_id=video.id, music_volume=30, voice_enabled=False)
    assert not audio.get("isError"), audio
    db.expire_all()
    stored = db.get(Video, video.id)
    assert (stored.music_volume, stored.voice_enabled) == (30, False)
    assert call(mcp_client, token, "set_audio", video_id=video.id, music_track_id=999999)["isError"]


def test_the_assistant_looks_at_a_scene_as_it_will_render(mcp_client, db, storage):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    video = make_video(db, storage, user, scene_count=1)
    scene = scenes_of(db, video)[0]
    seen = call(mcp_client, tokens["access_token"], "view_scene", scene_id=scene.id)
    assert not seen.get("isError"), seen
    assert seen["content"][0]["type"] == "image" and seen["content"][0]["mimeType"] == "image/jpeg"
    bare = make_video(db, storage, user, scene_count=1, images=False)
    assert call(mcp_client, tokens["access_token"], "view_scene", scene_id=scenes_of(db, bare)[0].id)["isError"]


@needs_ffmpeg
def test_the_assistant_looks_at_frames_of_the_rendered_mp4(mcp_client, db, storage, tmp_path):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    video = make_video(db, storage, user, scene_count=1)
    assert call(mcp_client, token, "view_render_frames", video_id=video.id, seconds=[0.5])["isError"]
    key = f"videos/{video.id}/video-test.mp4"
    storage.save_bytes(key, clip_bytes(tmp_path, seconds=3.0, size="1080x1920"))
    video.mp4_key = key
    db.commit()
    frames = call(mcp_client, token, "view_render_frames", video_id=video.id, seconds=[0.5, 1.5, 2.5])
    assert not frames.get("isError"), frames
    assert [block["type"] for block in frames["content"]] == ["image", "image", "image"]
