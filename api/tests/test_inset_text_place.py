"""Where a scene's text goes when nobody placed it and the scene has an inset photo: away from the photo."""

import pytest

from reels_api.models import Scene, SceneLayer, Video
from reels_api.videos import text_position


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
