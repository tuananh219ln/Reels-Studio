import pytest

from reels_render.timeline import FPS, build_timeline, fit_seconds, to_frames


@pytest.mark.parametrize(("seconds", "frames"), [(4, 120), (3.5, 105), (4.02, 121), (4.01, 120), (1, 30)])
def test_seconds_round_to_nearest_frame(seconds, frames):
    assert to_frames(seconds) == frames


def test_crossfades_straddle_boundaries_and_total_is_sum_of_seconds():
    timeline = build_timeline([3, 4, 4])
    assert timeline.scene_frames == [90, 120, 120]
    # title +0.2s, middle +0.2s each side, last +0.2s
    assert timeline.clip_frames == [96, 132, 126]
    assert timeline.xfade_offsets == [84, 204]
    assert timeline.total_frames == 330


def test_xfade_chain_length_equals_total():
    timeline = build_timeline([3, 4, 3.5, 4, 1])
    length = timeline.clip_frames[0]
    for offset, clip in zip(timeline.xfade_offsets, timeline.clip_frames[1:]):
        assert offset < length
        length = offset + clip
    assert length == timeline.total_frames


def test_fractional_seconds_do_not_accumulate_drift():
    seconds = [1.01] * 10
    timeline = build_timeline(seconds)
    assert abs(timeline.total_frames - sum(seconds) * FPS) <= 0.5


@pytest.mark.parametrize(("seconds", "voice", "fitted"), [
    (4, None, 4),  # no narration: the scene keeps its seconds
    (4, 2.5, 4),  # narration fits with lead-in and pause
    (1, 2.5, 3.1),  # 0.2 lead + 2.5 + 0.4 pause
    (3, 3.0, 3.6),  # exactly 36 tenths, not rounded up to 3.7 by float noise
    (3, 3.01, 3.7),  # any part of a tenth rounds up, so the narration is never cut
])
def test_scene_is_lengthened_to_fit_its_narration(seconds, voice, fitted):
    assert fit_seconds(seconds, voice) == fitted
