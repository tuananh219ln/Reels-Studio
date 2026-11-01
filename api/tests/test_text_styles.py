"""The team's text box styles (Cài đặt shared by every member) and a video taking one's colours."""

import pytest
from conftest import login, make_user, make_video

from reels_api import video_options

URL = "/api/settings/text-styles"
NAVY = {"name": "Xanh navy", "box_color": "#1d4ed8", "box_opacity": "soft", "text_color": "#FFFFFF"}


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def test_members_add_edit_and_delete_the_teams_box_styles(an, db):
    assert an.get(URL).json() == []
    created = an.post(URL, json=NAVY).json()
    # Colours are stored in capitals; marked words default to the automatic colour.
    assert created | {"id": "x"} == {
        "id": "x",
        "name": "Xanh navy",
        "box_color": "#1D4ED8",
        "box_opacity": "soft",
        "text_color": "#FFFFFF",
        "accent_color": "auto",
    }
    second = an.post(URL, json=NAVY | {"name": "Cam", "box_color": "#FF7A00", "accent_color": "#111111"}).json()
    assert [style["name"] for style in an.get(URL).json()] == ["Xanh navy", "Cam"]

    edited = an.put(f"{URL}/{created['id']}", json=NAVY | {"name": "Navy đậm", "box_opacity": "solid"}).json()
    assert (edited["id"], edited["name"], edited["box_opacity"]) == (created["id"], "Navy đậm", "solid")
    assert an.delete(f"{URL}/{second['id']}").status_code == 200
    assert [style["name"] for style in an.get(URL).json()] == ["Navy đậm"]
    assert an.delete(f"{URL}/{second['id']}").status_code == 404
    assert an.put(f"{URL}/nope", json=NAVY).status_code == 404


def test_a_box_style_needs_a_name_of_its_own_and_real_colours(an):
    an.post(URL, json=NAVY)
    for body, message in (
        (NAVY | {"name": "  "}, "Cần đặt tên"),
        (NAVY | {"name": "xanh NAVY"}, "Đã có kiểu tên"),
        (NAVY | {"name": "x" * 41}, "Tên kiểu tối đa 40"),
        (NAVY | {"name": "A", "box_color": "auto"}, "Màu nền hộp"),
        (NAVY | {"name": "A", "text_color": "#12345"}, "Màu chữ"),
        (NAVY | {"name": "A", "accent_color": "red"}, "Màu chữ đánh dấu"),
        (NAVY | {"name": "A", "box_opacity": "auto"}, "Độ trong"),
    ):
        refused = an.post(URL, json=body)
        assert refused.status_code == 422 and refused.json()["message"].startswith(message), body


def test_a_video_keeps_its_copy_when_the_style_changes_or_goes(an, db, me, storage):
    video = make_video(db, storage, me)
    style = an.post(URL, json=NAVY).json()
    copied = {name: style[name] for name in ("box_color", "box_opacity", "text_color", "accent_color")}
    payload = an.patch(f"/api/videos/{video.id}", json={"options": {"text_style": "box"} | copied}).json()
    assert payload["options"]["box_opacity"] == "soft"
    an.put(f"{URL}/{style['id']}", json=NAVY | {"box_color": "#E10600"})
    an.delete(f"{URL}/{style['id']}")
    db.refresh(video)
    options = video_options.render_options(video)
    assert (options.text_style, options.box_color, options.box_opacity) == ("box", "#1D4ED8", "soft")
    refused = an.patch(f"/api/videos/{video.id}", json={"options": {"box_opacity": "50"}})
    assert refused.status_code == 422 and "Độ trong" in refused.json()["message"]


def test_the_opacity_option_leaves_the_fingerprint_of_earlier_videos_alone(db, me, storage):
    video = make_video(db, storage, me)
    video.options = {"text_style": "dark"}  # saved before the option existed
    assert "box_opacity" not in video_options.look_signature(video)
    video.options = {"text_style": "dark", "box_opacity": "solid"}
    assert video_options.look_signature(video)["box_opacity"] == "solid"


def test_a_box_style_can_have_no_background(an, db, me, storage):
    style = an.post(URL, json=NAVY | {"name": "Chữ vàng viền đen", "box_color": "#000000", "box_opacity": "none"})
    assert style.status_code == 200 and style.json()["box_opacity"] == "none"
    video = make_video(db, storage, me)
    payload = an.patch(f"/api/videos/{video.id}", json={"options": {"text_style": "box", "box_opacity": "none"}})
    assert payload.json()["options"]["box_opacity"] == "none"
