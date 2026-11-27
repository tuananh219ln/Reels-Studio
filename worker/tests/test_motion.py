"""Entrance and exit motion for PC Shopee's drawn text: pictures that follow each other with no gap (motion.py)."""

import pytest
from PIL import Image

from reels_render import motion
from reels_render.cumulative import TimedWord, plan_cumulative


def block(size: tuple[int, int] = (400, 120)) -> Image.Image:
    return Image.new("RGBA", size, (255, 255, 255, 255))


def alpha(image: Image.Image) -> int:
    return image.getchannel("A").getextrema()[1]


def assert_covers(frames: list[motion.Frame], start: float, end: float) -> None:
    """The pictures start at `start`, end at `end` and each begins where the one before ended."""
    assert frames[0].start == pytest.approx(start) and frames[-1].end == pytest.approx(end)
    for before, after in zip(frames, frames[1:]):
        assert after.start == pytest.approx(before.end)
    assert all(frame.end > frame.start for frame in frames)


def test_an_entrance_starts_larger_and_faint_but_never_empty_and_ends_as_the_picture():
    picture = block()
    frames = motion.entrance(picture, 340, 1200, 2.0, 4.0)
    assert_covers(frames, 2.0, 4.0)
    assert frames[0].image.width > picture.width and 0 < alpha(frames[0].image) < 255, "visible at its first frame"
    assert frames[-1].image is picture and (frames[-1].left, frames[-1].top) == (340, 1200)
    # The centre stays where it was while it settles.
    first = frames[0]
    assert first.left + first.image.width / 2 == pytest.approx(340 + picture.width / 2, abs=1)
    assert frames[0].end - frames[0].start == pytest.approx(motion.POP_SECONDS / motion.POP_FRAMES)
    assert frames[-2].end == pytest.approx(2.0 + motion.POP_SECONDS)


def test_a_step_shorter_than_the_motion_is_still_covered_to_its_end():
    frames = motion.entrance(block(), 0, 0, 1.0, 1.1)
    assert_covers(frames, 1.0, 1.1)
    assert motion.entrance(block(), 0, 0, 1.0, 1.0) == []


def test_a_departure_keeps_the_picture_then_fades_to_almost_nothing_at_the_end():
    picture = block()
    frames = motion.departure(picture, 0, 0, 5.0, 8.0)
    assert_covers(frames, 5.0, 8.0)
    assert frames[0].image is picture and frames[0].end == pytest.approx(8.0 - motion.CLEAR_SECONDS)
    assert [alpha(frame.image) for frame in frames[1:]] == sorted((alpha(f.image) for f in frames[1:]), reverse=True)
    assert alpha(frames[-1].image) < 100
    short = motion.departure(picture, 0, 0, 5.0, 5.02)
    assert len(short) == 1 and short[0].image is picture, "too short to fade: shown as it is"


def test_a_phrase_pops_in_adds_its_words_plainly_and_fades_out_at_its_last_step():
    picture = block()
    opening = motion.animate(picture, 0, 0, 1.0, 2.0, opens=True, clears=False)
    later = motion.animate(picture, 0, 0, 2.0, 3.0, opens=False, clears=False)
    closing = motion.animate(picture, 0, 0, 3.0, 4.0, opens=False, clears=True)
    for frames, start, end in ((opening, 1.0, 2.0), (later, 2.0, 3.0), (closing, 3.0, 4.0)):
        assert_covers(frames, start, end)
    assert alpha(opening[0].image) < 255 and opening[0].image.width > picture.width
    assert len(later) == 1 and later[0].image is picture, "a later word appears at once: one picture"
    assert alpha(closing[-1].image) < 100


def test_the_plan_marks_where_a_phrase_opens_and_where_it_clears():
    words = [
        TimedWord("Chuột", 0.0, 0.4),
        TimedWord("không", 0.4, 0.8),
        TimedWord("dây.", 0.8, 1.2),
        TimedWord("Pin", 2.5, 2.9),
        TimedWord("trâu", 2.9, 3.3),
    ]
    steps = plan_cumulative(words, 4.0)
    assert [(step.opens, step.clears) for step in steps] == [
        (True, False),
        (False, False),
        (False, True),
        (True, False),
        (False, True),
    ]
