"""Where a scene's text goes when nobody placed it and the scene has an inset photo: away from the photo."""

import pytest

from reels_api.models import Scene, SceneLayer, Video
from reels_api.videos import signed_position, text_position


def scene_with(inset_y: int | None, height: int = 38, **own) -> tuple[Video, Scene]:
    layers = [SceneLayer(kind="photo", style="half", y=inset_y, height=height)] if inset_y is not None else []
    return Video(mode="single", options={}), Scene(is_title=False, layers=layers, **own)


@pytest.mark.parametrize(
    ("inset_y", "expected"),
    [(365, [540, 1920]), (960, None), (1555, None), (None, None)],
    ids=["inset-top: text goes low", "inset-middle: text stays on top", "inset-bottom: text stays on top", "no inset"],
)
def test_the_text_goes_opposite_the_inset(inset_y, expected):
    video, scene = scene_with(inset_y)
    assert text_position(video, scene) == expected


def test_a_place_the_member_chose_is_never_changed_by_the_inset():
    video, scene = scene_with(1555, text_x=540, text_y=960)
    assert text_position(video, scene) == [540, 960]


def test_the_insets_place_follows_its_height():
    # 45% tall is 864 px: at centre 1000 it still reaches up to the text's place (290 + 300), at 1030 it is clear.
    assert text_position(*scene_with(1000, height=45)) == [540, 1920]
    assert text_position(*scene_with(1030, height=45)) is None


def test_a_slide_video_ignores_an_inset_kept_for_switching_back():
    video, scene = scene_with(1555)
    video.mode = "slides"
    assert text_position(video, scene) is None


@pytest.mark.parametrize("mode", ["slides", "single"])
def test_a_card_hung_at_the_top_sends_the_text_to_the_bottom(mode):
    def with_card(top):
        card = SceneLayer(kind="photo", style="card", y=top, height=1000)
        return Video(mode=mode, options={}), Scene(is_title=False, layers=[card])

    assert text_position(*with_card(220)) == [540, 1920]
    assert text_position(*with_card(700)) is None, "a card hung low leaves the text at the top"


@pytest.mark.parametrize(("inset_y", "signed"), [(365, None), (960, [540, 0]), (1555, [540, 0])])
def test_the_fingerprint_keeps_the_place_it_held_before_the_safe_layout(inset_y, signed):
    """An MP4 rendered before it, with nothing changed since, must not be marked outdated."""
    video, scene = scene_with(inset_y)
    assert signed_position(video, scene) == signed
    scene.text_x, scene.text_y = 540, 800
    assert signed_position(video, scene) == [540, 800]


def test_a_card_adds_no_place_to_the_fingerprint():
    card = SceneLayer(kind="photo", style="card", y=220, height=1000)
    assert signed_position(Video(mode="slides", options={}), Scene(is_title=False, layers=[card])) is None
