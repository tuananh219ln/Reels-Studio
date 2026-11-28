"""Where text and the logo go (docs/decisions/2026-11-28-safe-layout.md): the video's profile, the logo's own place,
what the page is sent, the warning and the render machine's options."""

import pytest
from test_brands import patch, with_logo
from test_videos_api import make_video

from reels_api import frames, render_nodes, video_options
from reels_api.models import Video
from reels_api.videos import LOGO_ON_TEXT, layout_payload, render_signature, split_scenes
from reels_render.options import RenderOptions

# --- Without a database ---


def test_a_video_is_on_the_balanced_profile_unless_it_says_otherwise():
    plain = Video(mode="slides", options={})
    assert video_options.render_options(plain).layout_profile == "balanced"
    assert video_options.look_signature(plain) is None, "MP4s rendered before profiles existed stay current"
    wide = Video(mode="slides", options={"layout_profile": "universal"})
    assert video_options.look_signature(wide) is not None
    assert video_options.text_look(wide) != video_options.text_look(plain)
    assert video_options.preview_look(wide, False) == ["universal"]
    with pytest.raises(video_options.OptionError, match="Vùng an toàn"):
        video_options.clean({"layout_profile": "shorts"})


def test_the_page_is_sent_the_profiles_edges_and_the_logos_place():
    assert layout_payload(Video(mode="slides", options={})) == {
        "profile": "balanced",
        "text_top_min": 290,
        "text_left": 65,
        "text_right": 1015,
        "subtitle_bottom": 1530,
        "logo": {"x": 750, "y": 660, "size": 130, "own": False},
    }
    moved = Video(mode="slides", options={"layout_profile": "universal", "logo_position": [1000, 100]})
    payload = layout_payload(moved)
    # Kept inside the profile's edges, as the render keeps it.
    assert payload["logo"] == {"x": 758, "y": 290, "size": 130, "own": True}
    assert (payload["text_right"], payload["subtitle_bottom"]) == (888, 1248)


def test_a_render_machine_is_always_told_the_profile_and_the_logos_place_only_when_set():
    sent = render_nodes.options_dict(RenderOptions())
    assert sent["layout_profile"] == "balanced", "a machine on older code refuses it rather than using the old places"
    assert "logo_position" not in sent and "logo_size" not in sent
    own = render_nodes.options_dict(RenderOptions(logo_position=(100, 700), logo_size=160))
    assert (own["logo_position"], own["logo_size"]) == ((100, 700), 160)
    assert RenderOptions(**own).logo_position == (100, 700)


@pytest.mark.parametrize("is_title", [True, False])
def test_the_previews_text_starts_290_down(is_title):
    rect = frames.text_rect("Cá nhỏ\nGiàu *canxi*", is_title, RenderOptions(), None, False, None)
    assert rect[1] == 290 and 65 <= rect[0] and rect[2] <= 1015
    compact = RenderOptions(title_layout="three_tier", scene_text_layout="two_tier")
    assert frames.text_rect("Cá nhỏ\nGiàu *canxi*", is_title, compact, None, False, None)[1] == 290


# --- With the database ---


def test_the_logos_place_is_saved_checked_and_put_back(an, db, me, storage):
    video = make_video(db, storage, me)
    saved = patch(an, video, logo_position=[100, 900], logo_size=180)
    assert saved.status_code == 200, saved.text
    assert saved.json()["layout"]["logo"] == {"x": 100, "y": 900, "size": 180, "own": True}
    for bad in ({"logo_position": [1, 2, 3]}, {"logo_position": [-5, 0]}, {"logo_size": 20}, {"logo_size": "to"}):
        assert patch(an, video, **bad).status_code == 400, bad
    back = patch(an, video, logo_position=None, logo_size=None)
    assert back.json()["layout"]["logo"] == {"x": 750, "y": 660, "size": 130, "own": False}
    db.refresh(video)
    assert "logo_position" not in video.options and "logo_size" not in video.options


def test_moving_the_logo_marks_the_mp4_outdated_only_while_the_logo_is_on(an, db, me, storage):
    brand_id, _ = with_logo(an)
    video = make_video(db, storage, me)
    title, scenes = split_scenes(db, video)
    without = render_signature(video, title, scenes)
    patch(an, video, logo_position=[100, 900])
    db.refresh(video)
    assert render_signature(video, title, scenes) == without
    patch(an, video, brand_id=brand_id, logo_position=None)
    db.refresh(video)
    on = render_signature(video, title, scenes)
    patch(an, video, logo_position=[100, 900])
    db.refresh(video)
    assert render_signature(video, title, scenes) != on


def test_a_logo_laid_over_a_scenes_text_is_warned_about(an, db, me, storage):
    brand_id, _ = with_logo(an)
    video = make_video(db, storage, me)

    def warned(response) -> bool:
        return any(LOGO_ON_TEXT in scene["warnings"] for scene in response.json()["scenes"])

    assert not warned(patch(an, video, brand_id=brand_id)), "the default place is under the text"
    assert warned(patch(an, video, logo_position=[475, 300]))
    assert not warned(patch(an, video, logo_enabled=False))


def test_a_scene_can_be_put_low_or_back_to_its_usual_place(an, db, me, storage):
    video = make_video(db, storage, me)
    scene = split_scenes(db, video)[1][0]
    for zone in ("bottom", "top", None):
        saved = an.patch(f"/api/scenes/{scene.id}", json={"text_zone": zone})
        assert saved.status_code == 200, saved.text
        assert next(one for one in saved.json()["scenes"] if one["id"] == scene.id)["text_zone"] == zone
