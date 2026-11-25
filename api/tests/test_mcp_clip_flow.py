"""The MCP clip flow (owner, 2026-11-15): compact answers of the write tools, a scene's own text position, a blur the
scene's text and cover stickers hide, the clip's contact sheet, "Gắn clip cho cảnh", the group's "Không dùng cảnh có
người" and a licensed track added to the music library from a link."""

from conftest import clip_bytes, make_video, needs_ffmpeg
from sqlalchemy import select
from test_mcp import call, grant, mcp_client, payload  # noqa: F401  (mcp_client is a fixture)

from reels_api import mcp_server
from reels_api.models import KnowledgeTopic, MediaItem, MusicTrack, Scene, SceneLayer


def scenes_of(db, video) -> list[Scene]:
    db.expire_all()
    return db.scalars(
        select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)).order_by(Scene.position)
    ).all()


def title_of(db, video) -> Scene:
    db.expire_all()
    return db.scalar(select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(True)))


def give_clip(db, storage, scene, seconds=12.0) -> None:
    """A clip on the scene without running FFmpeg: enough for the blur and the text box, which only read the rows."""
    key = f"videos/{scene.video_id}/clip-{scene.id}.mp4"
    storage.save_bytes(key, b"clip")
    scene.image_key, scene.video_key, scene.video_seconds = None, key, seconds
    db.commit()


# --- Compact answers ---


def test_a_write_tool_answers_with_a_compact_video(mcp_client, db, storage):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    video = make_video(db, storage, user, scene_count=2)
    scene = scenes_of(db, video)[0]
    answer = payload(call(mcp_client, tokens["access_token"], "update_scene", scene_id=scene.id, seconds=4))
    assert answer["id"] == video.id and "note" in answer
    assert [row["id"] for row in answer["scenes"]] == [row.id for row in scenes_of(db, video)]
    assert answer["scenes"][0]["media"] == "photo" and answer["title_scene"]["is_title"] is True
    # The heavy parts stay with "Đọc video".
    for heavy in ("fanpages", "pinned_comment", "options", "caption", "publications"):
        assert heavy not in answer
    full = payload(call(mcp_client, tokens["access_token"], "get_video", video_id=video.id))
    assert "fanpages" in full and "pinned_survey" in full


# --- A scene's own text position ---


def test_the_assistant_moves_and_resets_a_scenes_text(mcp_client, db, storage):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    video = make_video(db, storage, user, scene_count=1)
    scene = scenes_of(db, video)[0]
    moved = call(mcp_client, token, "update_scene", scene_id=scene.id, text_position=[300, 400])
    assert not moved.get("isError"), moved
    db.refresh(scene)
    assert (scene.text_x, scene.text_y) == (300, 400)
    assert payload(moved)["scenes"][0]["text_position"] == [300, 400]
    assert not call(mcp_client, token, "update_scene", scene_id=scene.id, reset_text_position=True).get("isError")
    db.refresh(scene)
    assert (scene.text_x, scene.text_y) == (None, None)


# --- Text and stickers over a blur ---


def test_uncovered_strips_and_cover_stickers():
    patch = (100, 100, 900, 200)
    # The text box covers the middle: the left and right parts show.
    strips = mcp_server.uncovered_strips(patch, (300, 90, 700, 210))
    assert strips == [(100, 100, 300, 200), (700, 100, 900, 200)]
    # A box covering it all leaves nothing; a box elsewhere leaves the whole patch.
    assert mcp_server.uncovered_strips(patch, (50, 50, 950, 250)) == []
    assert mcp_server.uncovered_strips(patch, (0, 1000, 100, 1100)) == [patch]
    # A sliver thinner than COVER_MIN_PIXELS is not worth a sticker.
    assert mcp_server.uncovered_strips(patch, (105, 50, 950, 250)) == []
    placed = mcp_server.cover_stickers(strips)
    assert placed == [(200, 150, "medium"), (800, 150, "medium")]
    # Never more than COVER_MAX, and a strip longer than the largest side takes two.
    assert len(mcp_server.cover_stickers([(0, 0, 1000, 50)])) == 2
    assert len(mcp_server.cover_stickers([(0, 0, 1000, 50), (0, 500, 200, 600)])) == mcp_server.COVER_MAX


def test_a_blur_moves_the_scenes_text_onto_it_and_stickers_cover_the_rest(mcp_client, db, storage):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    video = make_video(db, storage, user, scene_count=1)
    scene = scenes_of(db, video)[0]
    give_clip(db, storage, scene)
    # A wide patch near the top: the text box sits on its centre, too narrow to hide all of it.
    box = [0.02, 0.1, 0.96, 0.08]
    done = call(mcp_client, token, "set_scene_clip_blur", scene_id=scene.id, boxes=[box])
    assert not done.get("isError"), done
    db.refresh(scene)
    assert [scene.text_x, scene.text_y] == mcp_server._box_centre([box])
    stickers = db.scalars(select(SceneLayer).where(SceneLayer.scene_id == scene.id)).all()
    assert stickers and all(mcp_server.is_cover_sticker(layer) for layer in stickers)
    assert all(layer.sticker in mcp_server.COVER_STICKERS for layer in stickers)
    assert payload(done)["cover"]
    # Drawing the blur again replaces the cover stickers instead of adding more.
    again = call(mcp_client, token, "set_scene_clip_blur", scene_id=scene.id, boxes=[box])
    assert not again.get("isError"), again
    assert len(db.scalars(select(SceneLayer).where(SceneLayer.scene_id == scene.id)).all()) == len(stickers)
    # Without the rule, the text stays where it is and no sticker is added.
    other = make_video(db, storage, user, scene_count=1)
    plain = scenes_of(db, other)[0]
    give_clip(db, storage, plain)
    kept = call(mcp_client, token, "set_scene_clip_blur", scene_id=plain.id, boxes=[box], move_text=False)
    assert not kept.get("isError"), kept
    db.refresh(plain)
    assert (plain.text_x, plain.text_y) == (None, None)
    assert db.scalars(select(SceneLayer).where(SceneLayer.scene_id == plain.id)).all() == []


def test_a_scene_without_text_gets_no_move_and_no_sticker(mcp_client, db, storage):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    video = make_video(db, storage, user, scene_count=1, scene_text="")
    scene = scenes_of(db, video)[0]
    give_clip(db, storage, scene)
    done = call(
        mcp_client, tokens["access_token"], "set_scene_clip_blur", scene_id=scene.id, boxes=[[0.1, 0.1, 0.5, 0.1]]
    )
    assert not done.get("isError"), done
    db.refresh(scene)
    assert (scene.text_x, scene.text_y) == (None, None)
    assert db.scalars(select(SceneLayer).where(SceneLayer.scene_id == scene.id)).all() == []


def test_the_title_takes_no_sticker_and_says_what_still_shows(mcp_client, db, storage):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    video = make_video(db, storage, user, scene_count=1)
    title = title_of(db, video)
    give_clip(db, storage, title)
    done = call(
        mcp_client, tokens["access_token"], "set_scene_clip_blur", scene_id=title.id, boxes=[[0.0, 0.1, 1.0, 0.1]]
    )
    assert not done.get("isError"), done
    assert any("Cảnh tiêu đề" in note for note in payload(done)["cover"])
    assert db.scalars(select(SceneLayer).where(SceneLayer.scene_id == title.id)).all() == []


# --- Contact sheet and "Gắn clip cho cảnh" ---


def test_sheet_seconds_are_spread_over_the_stretch():
    assert mcp_server.sheet_seconds(2.0, 4.0, 3) == [2.0, 4.0, 6.0]
    assert mcp_server.sheet_seconds(0.0, 6.0, 2) == [0.0, 6.0]


def library_clip(db, storage, user, tmp_path, seconds=8.0) -> MediaItem:
    key = "media/clip-test.mp4"
    storage.save_bytes(key, clip_bytes(tmp_path, seconds=seconds, size="720x1280"))
    item = MediaItem(kind="clip", storage_key=key, name="clip-test.mp4", seconds=seconds, created_by_id=user.id)
    db.add(item)
    db.commit()
    return item


@needs_ffmpeg
def test_the_assistant_sees_a_clips_stretch_as_one_sheet(mcp_client, db, storage, tmp_path):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    item = library_clip(db, storage, user, tmp_path)
    sheet = call(mcp_client, token, "view_clip_frames", media_id=item.id, start=1, seconds=4, count=6)
    assert not sheet.get("isError"), sheet
    assert sheet["content"][0]["type"] == "text" and "6 khung từ giây 1 tới 5" in sheet["content"][0]["text"]
    assert sheet["content"][1]["type"] == "image"
    assert call(mcp_client, token, "view_clip_frames")["isError"]
    assert call(mcp_client, token, "view_clip_frames", media_id=item.id, scene_id=1)["isError"]


@needs_ffmpeg
def test_attaching_a_clip_keeps_the_titles_seconds_and_blurs_in_one_call(mcp_client, db, storage, tmp_path):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    video = make_video(db, storage, user, scene_count=1)
    title = title_of(db, video)
    assert title.seconds == 3 and not title.seconds_auto
    item = library_clip(db, storage, user, tmp_path, seconds=12.0)
    done = call(
        mcp_client,
        token,
        "attach_scene_clip",
        scene_id=title.id,
        media_id=item.id,
        video_start=2,
        blur=[[0.7, 0.02, 0.28, 0.05]],
    )
    assert not done.get("isError"), done
    assert [block["type"] for block in done["content"]] == ["text", "image"]
    title = title_of(db, video)
    assert title.video_key and title.video_start == 2
    # The web sets a clip's scene to the clip's length (10 s at most); the tool puts the title's 3 s back.
    assert title.seconds == 3
    assert title.video_blur["boxes"] == [[0.7, 0.02, 0.28, 0.05]]


# --- "Không dùng cảnh có người" ---


def test_the_groups_no_people_switch_reaches_the_video_and_the_rules(mcp_client, db, storage):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    video = make_video(db, storage, user, scene_count=1)
    group = db.get(KnowledgeTopic, video.knowledge_topic_id)
    assert group.no_people is False
    assert payload(call(mcp_client, tokens["access_token"], "get_video", video_id=video.id))["no_people"] is False
    group.no_people = True
    db.commit()
    assert payload(call(mcp_client, tokens["access_token"], "get_video", video_id=video.id))["no_people"] is True
    assert "no_people=true" in mcp_server.CLIP_RULES and "bàn tay" in mcp_server.CLIP_RULES


# --- Music from a link ---


def test_music_comes_only_from_a_licensed_mp3_link(mcp_client, db, monkeypatch):  # noqa: F811
    from reels_api import remote_media

    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    mp3 = b"ID3" + b"\x00" * 64
    monkeypatch.setattr(remote_media, "download_music", lambda url, folder: mp3)
    added = call(
        mcp_client,
        token,
        "add_music_from_link",
        url="https://cdn.example.org/song.mp3",
        mood="piano",
        license_note="Pixabay Content License, https://pixabay.com/music/x",
    )
    assert not added.get("isError"), added
    answer = payload(added)
    track = db.get(MusicTrack, answer["music_track_id"])
    assert (track.name, track.mood, track.topics) == ("song", "piano", ["chung"])
    # A licence note is required, and the mood must be one of the list.
    assert call(mcp_client, token, "add_music_from_link", url="https://cdn.example.org/a.mp3", mood="piano")["isError"]
    assert call(
        mcp_client, token, "add_music_from_link", url="https://cdn.example.org/a.mp3", mood="rock", license_note="CC0"
    )["isError"]


def test_tiktok_and_youtube_links_are_refused_for_music(tmp_path):
    import pytest

    from reels_api import remote_media

    for url in ("https://www.tiktok.com/@a/video/1", "https://www.youtube.com/watch?v=x", "https://youtu.be/x"):
        with pytest.raises(remote_media.RemoteMediaError, match="TikTok hay YouTube"):
            remote_media.download_music(url, tmp_path)


def test_a_member_turns_the_groups_no_people_switch_and_it_is_in_the_history(client, db):
    from conftest import first_topic, login, make_user

    make_user(db)
    login(client)
    group = first_topic(db)
    shown = client.patch(f"/api/knowledge/topics/{group.id}", json={"no_people": True})
    assert shown.status_code == 200, shown.json()
    assert next(row for row in shown.json()["topics"] if row["id"] == group.id)["no_people"] is True
    history = client.get(f"/api/edit-logs?entity_type=knowledge_topic&entity_id={group.id}").json()["entries"]
    assert history[0]["changes"]["no_people"] == {"old": False, "new": True}
