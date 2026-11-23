"""'Thẻ' (a screenshot card over a scene's picture) and 'Hiện dần' (the card shown part by part as it is read)."""

import io

import pytest
from conftest import login, make_user, make_video
from PIL import Image

from reels_api.jobs import reveal_layers
from reels_api.models import MediaItem
from reels_api.videos import drawn_layers, render_signature, reveal_steps, split_scenes


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def card_png(size=(1000, 1200)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (245, 245, 245)).save(buffer, "PNG")
    return buffer.getvalue()


def library_card(db, storage, me, size=(1000, 1200)) -> MediaItem:
    storage.save_bytes("media/the.png", card_png(size))
    item = MediaItem(kind="photo", storage_key="media/the.png", name="the.png", created_by_id=me.id)
    db.add(item)
    db.commit()
    return item


def scene_json(payload: dict, scene_id: int) -> dict:
    return next(scene for scene in payload["scenes"] if scene["id"] == scene_id)


def test_a_card_goes_on_a_slide_videos_scene_and_is_drawn(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=2)
    first = split_scenes(db, video)[1][0]
    item = library_card(db, storage, me)
    added = an.post("/api/layers/card", json={"scene_id": first.id, "media_id": item.id, "top": 300})
    assert added.status_code == 201, added.json()
    (layer,) = scene_json(added.json(), first.id)["layers"]
    assert (layer["kind"], layer["style"], layer["x"], layer["y"], layer["height"]) == ("photo", "card", 540, 300, 90)
    assert layer["reveal"] == []
    db.expire_all()
    assert [row.style for row in drawn_layers(video, first)] == ["card"]
    assert an.get(layer["image_url"]).status_code == 200

    # A new picture takes the old one's place, keeping its place: still one card.
    again = an.post("/api/layers/card", json={"scene_id": first.id, "media_id": item.id})
    (kept,) = scene_json(again.json(), first.id)["layers"]
    assert kept["id"] == layer["id"] and kept["y"] == 300


def test_a_card_refuses_a_clip_the_title_and_bad_sizes(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    title, (first,) = split_scenes(db, video)
    item = library_card(db, storage, me)
    assert an.post("/api/layers/card", json={"scene_id": title.id, "media_id": item.id}).status_code == 422
    narrow = an.post("/api/layers/card", json={"scene_id": first.id, "media_id": item.id, "width": 20})
    assert narrow.status_code == 422 and "Cỡ thẻ" in narrow.json()["message"]
    storage.save_bytes("media/clip.mp4", b"x")
    clip = MediaItem(kind="clip", storage_key="media/clip.mp4", name="clip.mp4", created_by_id=me.id)
    db.add(clip)
    db.commit()
    refused = an.post("/api/layers/card", json={"scene_id": first.id, "media_id": clip.id})
    assert refused.status_code == 422 and "không phải video" in refused.json()["message"]


def test_a_card_moves_only_up_and_down_and_changes_width(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    first = split_scenes(db, video)[1][0]
    added = an.post("/api/layers/card", json={"scene_id": first.id, "media_id": library_card(db, storage, me).id})
    layer = scene_json(added.json(), first.id)["layers"][0]
    moved = an.patch(f"/api/layers/{layer['id']}", json={"x": 100, "y": 500, "height": 70, "style": "rounded"})
    assert moved.status_code == 200, moved.json()
    after = scene_json(moved.json(), first.id)["layers"][0]
    assert (after["x"], after["y"], after["height"], after["style"]) == (540, 500, 70, "card")


def test_the_card_is_shown_part_by_part_as_its_words_are_read(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1, seconds=10)
    first = split_scenes(db, video)[1][0]
    an.post("/api/layers/card", json={"scene_id": first.id, "media_id": library_card(db, storage, me).id})
    parts = [
        {"cut_y": 300, "text": "một hai ba"},
        {"cut_y": 700, "text": "bốn năm sáu bảy tám chín"},
        {"text": "mười"},
    ]
    saved = an.put("/api/layers/card/reveal", json={"scene_id": first.id, "parts": parts})
    assert saved.status_code == 200, saved.json()
    shown = scene_json(saved.json(), first.id)
    assert shown["voice_text"] == "một hai ba bốn năm sáu bảy tám chín mười"
    db.expire_all()
    assert first.reveal == {
        "parts": [
            {"until": 0.25, "words": 3, "text": "một hai ba"},
            {"until": 0.5833, "words": 6, "text": "bốn năm sáu bảy tám chín"},
            {"until": 1.0, "words": 1, "text": "mười"},
        ]
    }
    # No narration made yet: the parts share the scene's 10 s by their words (3, 6, 1 of 10).
    steps = [step["start"] for step in reveal_steps(video, first)]
    assert steps == [0.0, 3.0, 9.0]
    assert shown["layers"][0]["reveal"] == [
        {"start": 0.0, "until": 0.25, "text": "một hai ba"},
        {"start": 3.0, "until": 0.5833, "text": "bốn năm sáu bảy tám chín"},
        {"start": 9.0, "until": 1.0, "text": "mười"},
    ]

    off = an.put("/api/layers/card/reveal", json={"scene_id": first.id, "parts": []})
    assert scene_json(off.json(), first.id)["layers"][0]["reveal"] == []


def test_the_parts_must_go_down_the_card_and_each_have_words(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    first = split_scenes(db, video)[1][0]
    no_card = an.put("/api/layers/card/reveal", json={"scene_id": first.id, "parts": [{"text": "a"}, {"text": "b"}]})
    assert no_card.status_code == 422 and "chưa có thẻ" in no_card.json()["message"]
    an.post("/api/layers/card", json={"scene_id": first.id, "media_id": library_card(db, storage, me).id})
    for parts, message in (
        ([{"text": "một"}], "từ 2 đến"),
        ([{"cut_y": 600, "text": "một"}, {"cut_y": 400, "text": "hai"}], "lớn hơn phần trước"),
        ([{"cut_y": 1300, "text": "một"}, {"text": "hai"}], "không quá 1200"),
        ([{"text": "một"}, {"text": "hai"}], "thiếu cut_y"),
        ([{"cut_y": 600, "text": ""}, {"text": "hai"}], "lời đọc của phần"),
    ):
        refused = an.put("/api/layers/card/reveal", json={"scene_id": first.id, "parts": parts})
        assert refused.status_code == 422 and message in refused.json()["message"], (parts, refused.json())


def test_a_new_card_picture_or_removing_it_drops_the_parts(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    first = split_scenes(db, video)[1][0]
    item = library_card(db, storage, me)
    added = an.post("/api/layers/card", json={"scene_id": first.id, "media_id": item.id})
    layer_id = scene_json(added.json(), first.id)["layers"][0]["id"]
    parts = [{"cut_y": 600, "text": "một"}, {"text": "hai"}]
    an.put("/api/layers/card/reveal", json={"scene_id": first.id, "parts": parts})
    an.post("/api/layers/card", json={"scene_id": first.id, "media_id": item.id})
    db.expire_all()
    assert first.reveal is None
    an.put("/api/layers/card/reveal", json={"scene_id": first.id, "parts": parts})
    an.delete(f"/api/layers/{layer_id}")
    db.expire_all()
    assert first.reveal is None and first.layers == []


def test_the_render_lays_one_card_per_part_with_the_rows_below_cleared(tmp_path):
    Image.new("RGB", (100, 200), (245, 245, 245)).save(tmp_path / "card-01.png")
    fields = {"kind": "photo", "style": "card", "image": "card-01.png", "start": 0, "seconds": 60, "y": 220}
    steps = [{"start": 0.0, "until": 0.25}, {"start": 2.5, "until": 1.0}]
    first, second = reveal_layers(fields, steps, tmp_path, "card-01")
    assert (first["start"], first["seconds"], second["start"], second["seconds"]) == (0, 60, 2.5, 57.5)
    with Image.open(tmp_path / first["image"]) as part:
        assert part.size == (100, 200)
        assert part.getpixel((50, 10))[3] == 255 and part.getpixel((50, 60))[3] == 0
    with Image.open(tmp_path / second["image"]) as part:
        assert part.getpixel((50, 190))[3] == 255


def test_videos_without_a_card_keep_their_fingerprint(db, me, storage):
    video = make_video(db, storage, me, scene_count=2)
    title, scenes = split_scenes(db, video)
    before = render_signature(video, title, scenes)
    scenes[0].reveal = None
    assert render_signature(video, title, scenes) == before
    scenes[0].reveal = {"parts": [{"until": 0.5, "words": 1}, {"until": 1.0, "words": 1}]}
    assert render_signature(video, title, scenes) != before


def test_the_scene_preview_shows_the_card_under_the_text(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1)
    first = split_scenes(db, video)[1][0]
    before = Image.open(io.BytesIO(an.get(f"/api/scenes/{first.id}/preview.jpg").content)).convert("RGB")
    storage.save_bytes("media/red.png", _png((1000, 600), (220, 30, 30)))
    item = MediaItem(kind="photo", storage_key="media/red.png", name="red.png", created_by_id=me.id)
    db.add(item)
    db.commit()
    an.post("/api/layers/card", json={"scene_id": first.id, "media_id": item.id, "top": 200})
    after = Image.open(io.BytesIO(an.get(f"/api/scenes/{first.id}/preview.jpg").content)).convert("RGB")
    # 972 × 583 from y 200, centred: red there now, the picture as before above it.
    red, green, blue = after.getpixel((540, 450))
    assert red > 180 and green < 80 and blue < 80
    assert after.getpixel((540, 100)) == before.getpixel((540, 100))


def _png(size, colour) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, colour).save(buffer, "PNG")
    return buffer.getvalue()


def test_the_studio_cuts_the_card_by_fractions_and_uploads_it(an, db, me, storage):
    video = make_video(db, storage, me, scene_count=1, seconds=6)
    first = split_scenes(db, video)[1][0]
    uploaded = an.post(
        "/api/layers/card/upload",
        data={"scene_id": str(first.id)},
        files={"file": ("the.png", card_png(), "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.json()
    assert scene_json(uploaded.json(), first.id)["layers"][0]["style"] == "card"
    parts = [{"until": 0.4, "text": "một hai"}, {"text": "ba bốn"}]
    saved = an.put("/api/layers/card/reveal", json={"scene_id": first.id, "parts": parts})
    assert saved.status_code == 200, saved.json()
    assert scene_json(saved.json(), first.id)["layers"][0]["reveal"] == [
        {"start": 0.0, "until": 0.4, "text": "một hai"},
        {"start": 3.0, "until": 1.0, "text": "ba bốn"},
    ]
    for bad, message in (
        ([{"until": 0.6, "text": "a"}, {"until": 0.5, "text": "b"}], "thấp hơn phần trước"),
        ([{"until": 1.5, "text": "a"}, {"text": "b"}], "nằm trong thẻ"),
    ):
        refused = an.put("/api/layers/card/reveal", json={"scene_id": first.id, "parts": bad})
        assert refused.status_code == 422 and message in refused.json()["message"], refused.json()
