"""Where a scene's text goes when nobody placed it and the scene has an inset photo: away from the photo."""

import pytest

from reels_api.models import Scene, SceneLayer, Video
from reels_api.videos import text_position


def scene_with(inset_y: int | None, height: int = 38, **own) -> tuple[Video, Scene]:
    layers = [SceneLayer(kind="photo", style="half", y=inset_y, height=height)] if inset_y is not None else []
    return Video(mode="single", options={}), Scene(is_title=False, layers=layers, **own)


@pytest.mark.parametrize(
    ("inset_y", "expected"),
    [(365, None), (960, [540, 0]), (1555, [540, 0]), (None, None)],
    ids=["inset-top: text stays at the bottom", "inset-middle: text on top", "inset-bottom: text on top", "no inset"],
)
def test_the_text_goes_opposite_the_inset(inset_y, expected):
    video, scene = scene_with(inset_y)
    assert text_position(video, scene) == expected


def test_a_place_the_member_chose_is_never_changed_by_the_inset():
    video, scene = scene_with(1555, text_x=540, text_y=960)
    assert text_position(video, scene) == [540, 960]


def test_the_insets_place_follows_its_height():
    # 45% tall is 864 px: centre 432 is still flush with the top edge, 500 is not.
    assert text_position(*scene_with(432, height=45)) is None
    assert text_position(*scene_with(500, height=45)) == [540, 0]


def test_a_slide_video_ignores_an_inset_kept_for_switching_back():
    video, scene = scene_with(1555)
    video.mode = "slides"
    assert text_position(video, scene) is None
