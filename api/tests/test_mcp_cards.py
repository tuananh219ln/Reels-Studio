"""The assistant's comment-reading tools: a card over a scene, shown part by part, and a scene's own voice."""

import io

from conftest import make_video
from PIL import Image
from sqlalchemy import select
from test_mcp import call, grant, mcp_client, payload  # noqa: F401  (mcp_client is a fixture)

from reels_api.models import MediaItem, Scene


def first_scene(db, video) -> Scene:
    db.expire_all()
    return db.scalar(
        select(Scene).where(Scene.video_id == video.id, Scene.is_title.is_(False)).order_by(Scene.position).limit(1)
    )


def test_the_assistant_lays_a_card_shows_it_part_by_part_and_gives_a_scene_its_voice(mcp_client, db, storage):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    video = make_video(db, storage, user, scene_count=1)
    scene = first_scene(db, video)
    buffer = io.BytesIO()
    Image.new("RGB", (1000, 800), "white").save(buffer, "PNG")
    storage.save_bytes("media/the.png", buffer.getvalue())
    item = MediaItem(kind="photo", storage_key="media/the.png", name="the.png", created_by_id=user.id)
    db.add(item)
    db.commit()

    laid = call(mcp_client, token, "set_scene_card", scene_id=scene.id, media_id=item.id, top=250)
    assert not laid.get("isError"), laid
    answer = payload(laid)
    assert answer["card"]["width_px"] == 1000 and answer["card"]["height_px"] == 800
    (layer,) = answer["scenes"][0]["layers"]
    assert layer["style"] == "card"

    parts = [{"cut_y": 300, "text": "phần một"}, {"text": "phần hai là cuối"}]
    shown = call(mcp_client, token, "set_card_reveal", scene_id=scene.id, parts=parts)
    assert not shown.get("isError"), shown
    row = payload(shown)["scenes"][0]
    assert row["voice_text"] == "phần một phần hai là cuối" and len(row["layers"][0]["reveal"]) == 2

    voiced = call(mcp_client, token, "update_scene", scene_id=scene.id, voice_id="fake-voice-nam")
    assert payload(voiced)["scenes"][0]["voice_id"] == "fake-voice-nam"
    back = call(mcp_client, token, "update_scene", scene_id=scene.id, voice_id="")
    assert "voice_id" not in payload(back)["scenes"][0]
