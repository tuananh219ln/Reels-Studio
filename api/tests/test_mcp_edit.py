"""The MCP editing tools: the studio's handlers, presets and locks, and the frames the assistant looks at to check
its work before saying a video is done."""

import json

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


def test_the_assistant_finds_a_mark_erases_it_and_can_restore_the_photo(mcp_client, db, storage):  # noqa: F811
    from reels_api.models import Job

    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    video = make_video(db, storage, user, scene_count=1)
    scene = scenes_of(db, video)[0]
    seen = call(mcp_client, token, "view_scene_photo", scene_id=scene.id)
    assert not seen.get("isError"), seen
    assert seen["content"][0]["type"] == "text" and "720×1280" in seen["content"][0]["text"]
    assert seen["content"][1]["type"] == "image"

    queued = call(mcp_client, token, "edit_scene_image", scene_id=scene.id, boxes=[[0.4, 0.4, 0.2, 0.05]])
    assert not queued.get("isError"), queued
    job = db.scalar(select(Job).where(Job.video_id == video.id))
    assert (job.kind, job.image_provider, job.edit_boxes) == ("image_edit", "lama", [[0.4, 0.4, 0.2, 0.05]])
    # Gemini without words is refused like on the page.
    assert call(mcp_client, token, "edit_scene_image", scene_id=scene.id, engine="gemini")["isError"]

    db.delete(job)
    original = scene.image_key
    storage.save_bytes(f"videos/{video.id}/edited.jpg", storage.path(original).read_bytes())
    scene.image_original_key, scene.image_key = original, f"videos/{video.id}/edited.jpg"
    db.commit()
    restored = call(mcp_client, token, "restore_scene_image", scene_id=scene.id)
    assert not restored.get("isError"), restored
    db.refresh(scene)
    assert (scene.image_key, scene.image_original_key) == (original, None)


def test_the_assistant_blurs_a_logo_on_a_clip(mcp_client, db, storage):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    video = make_video(db, storage, user, scene_count=1)
    scene = scenes_of(db, video)[0]
    storage.save_bytes(f"videos/{video.id}/clip.mp4", b"clip")
    scene.image_key, scene.video_key, scene.video_seconds = None, f"videos/{video.id}/clip.mp4", 3.0
    db.commit()
    done = call(
        mcp_client, tokens["access_token"], "set_scene_clip_blur", scene_id=scene.id, boxes=[[0.7, 0.02, 0.28, 0.06]]
    )
    assert not done.get("isError"), done
    db.refresh(scene)
    assert scene.video_blur["boxes"] == [[0.7, 0.02, 0.28, 0.06]]


def test_the_assistant_finds_a_free_stock_photo_looks_at_it_and_uses_it(mcp_client, db, storage, fakes, monkeypatch):  # noqa: F811
    from reels_api import remote_media

    # The fake sources listen on this machine; let their previews be fetched as from the internet.
    monkeypatch.setattr(remote_media, "is_public", lambda address: True)
    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    video = make_video(db, storage, user, scene_count=1, images=False)
    scene = scenes_of(db, video)[0]
    fakes.pexels_results["fresh celery"] = ["px1", "px2"]

    found = call(mcp_client, token, "search_stock_photos", scene_id=scene.id, keyword="fresh celery")
    assert not found.get("isError"), found
    listing = json.loads(found["content"][0]["text"])
    assert listing["source"] == "pexels" and [hit["url"] for hit in listing["hits"]] == [
        fakes.image_url("px1"),
        fakes.image_url("px2"),
    ]
    assert [item["type"] for item in found["content"][1:]] == ["text", "image", "text", "image"]

    used = call(
        mcp_client,
        token,
        "use_stock_photo",
        scene_id=scene.id,
        source="pexels",
        keyword="fresh celery",
        url=listing["hits"][1]["url"],
    )
    assert not used.get("isError"), used
    db.refresh(scene)
    assert scene.image_source == fakes.image_url("px2")
    # Only a photo the source itself returned may be fetched.
    assert call(
        mcp_client,
        token,
        "use_stock_photo",
        scene_id=scene.id,
        source="pexels",
        keyword="fresh celery",
        url="https://example.com/x.jpg",
    )["isError"]


def test_no_stock_result_says_to_try_other_words(mcp_client, db, storage, monkeypatch):  # noqa: F811
    from reels_api import routes_videos

    monkeypatch.setattr(routes_videos, "search_stock", lambda *args: {"keyword": "zzz", "source": "pexels", "hits": []})
    user, _, tokens, _ = grant(mcp_client, db)
    video = make_video(db, storage, user, scene_count=1, images=False)
    found = call(
        mcp_client, tokens["access_token"], "search_stock_photos", scene_id=scenes_of(db, video)[0].id, keyword="zzz"
    )
    assert not found.get("isError") and "thử từ khóa khác" in found["content"][0]["text"]


def test_the_assistant_is_told_how_to_find_a_photo_for_each_scene(mcp_client, db):  # noqa: F811
    from test_mcp import rpc

    _, _, tokens, _ = grant(mcp_client, db)
    started = rpc(
        mcp_client,
        tokens["access_token"],
        "initialize",
        {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}},
    )
    instructions = started.json()["result"]["instructions"]
    assert "Tìm ảnh kho miễn phí" in instructions and "CAPTCHA" in instructions and "Sửa ảnh của cảnh" in instructions


CHI = "5yEPTrA0uAhZsBEhHjfi"  # an ElevenLabs voice id, bare


def video_options_of(client, token, video) -> dict:
    return payload(call(client, token, "get_video", video_id=video.id))["options"]


def test_the_assistant_sets_a_videos_voice_and_title_size_and_nothing_else(mcp_client, db, storage):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    video = make_video(db, storage, user, scene_count=1)
    other = make_video(db, storage, user, scene_count=1)
    before = video_options_of(mcp_client, token, video)
    done = call(mcp_client, token, "set_video_options", video_id=video.id, voice_id=CHI, title_text_size="small")
    assert not done.get("isError"), done
    after = video_options_of(mcp_client, token, video)
    assert payload(done)["options"] == after
    assert after == before | {"voice_id": CHI, "title_text_size": "small"}
    assert video_options_of(mcp_client, token, other) == before

    one = call(mcp_client, token, "set_video_options", video_id=video.id, voice_id="vieneu:Ngọc Lan")
    assert not one.get("isError"), one
    assert video_options_of(mcp_client, token, video) == after | {"voice_id": "vieneu:Ngọc Lan"}


def test_every_setting_of_the_tab_can_be_set_and_cleared(mcp_client, db, storage):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    video = make_video(db, storage, user, scene_count=1)
    values = {
        "voice_speed": 1.2,
        "voice_volume": 80,
        "voice_pause": 0.7,
        "ducking": True,
        "transition": "cut",
        "motion": "pan",
        "zoom": "light",
        "text_style": "white",
        "text_color": "#ff0000",
        "title_style": "yellow",
        "box_color": "#000000",
        "accent_color": "#00FF00",
        "box_opacity": "soft",
        "title_text_style": "dark",
        "title_text_color": "white",
        "title_box_color": "#111111",
        "title_accent_color": "#222222",
        "title_box_opacity": "clear",
        "captions": "word",
        "text_size": "medium",
        "text_case": "keep",
        "title_text_case": "keep",
        "text_position": [540, 1200],
    }
    done = call(mcp_client, token, "set_video_options", video_id=video.id, **values)
    assert not done.get("isError"), done
    stored = video_options_of(mcp_client, token, video)
    assert {name: stored[name] for name in values} == values | {"text_color": "#FF0000"}
    cleared = call(mcp_client, token, "set_video_options", video_id=video.id, reset_text_position=True, voice_id="")
    assert not cleared.get("isError"), cleared
    assert video_options_of(mcp_client, token, video) == stored | {"text_position": None, "voice_id": ""}


def test_a_wrong_value_is_refused_and_nothing_is_saved(mcp_client, db, storage):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    video = make_video(db, storage, user, scene_count=1)
    before = video_options_of(mcp_client, token, video)
    wrong = call(mcp_client, token, "set_video_options", video_id=video.id, voice_id=CHI, title_text_size="tiny")
    assert wrong["isError"]
    assert "Cỡ chữ tiêu đề" in wrong["content"][0]["text"]
    assert call(mcp_client, token, "set_video_options", video_id=video.id, voice_id="hai từ")["isError"]
    assert call(mcp_client, token, "set_video_options", video_id=video.id, text_color="tím")["isError"]
    assert video_options_of(mcp_client, token, video) == before


def test_a_read_only_connection_cannot_set_video_options(mcp_client, db, storage):  # noqa: F811
    from reels_api.models import McpConnection

    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    video = make_video(db, storage, user, scene_count=1)
    before = video_options_of(mcp_client, token, video)
    row = db.scalar(select(McpConnection))
    row.scopes = "reels:read"
    db.commit()
    refused = call(mcp_client, token, "set_video_options", video_id=video.id, title_text_size="small")
    assert refused["isError"] and "quyền" in refused["content"][0]["text"]
    assert video_options_of(mcp_client, token, video) == before


def test_the_settings_tool_and_its_choices_come_from_the_tabs_rules(mcp_client, db):  # noqa: F811
    from test_mcp import rpc

    from reels_api import video_options

    _, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    tools = {tool["name"]: tool for tool in rpc(mcp_client, token, "tools/list").json()["result"]["tools"]}
    schema = tools["set_video_options"]["inputSchema"]
    assert schema["required"] == ["video_id"]
    assert set(video_options.DEFAULTS) <= set(schema["properties"])
    assert tools["set_video_options"]["annotations"]["readOnlyHint"] is False
    listed = payload(call(mcp_client, token, "list_edit_options"))["video_options"]
    assert listed["title_text_size"] == list(video_options.CHOICES["title_text_size"])
    assert listed["voice_pause"] == list(video_options.VOICE_PAUSES)
