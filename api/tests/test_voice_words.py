"""Word seconds of the narration for "Cộng dồn": ElevenLabs' `with-timestamps`, kept per scene."""

import pytest
from conftest import make_user, make_video
from test_voice import TEN_WORDS, first_scene, needs_ffmpeg
from worker_helpers import committed  # noqa: F401  (fixture)

from reels_api import tts, video_options
from reels_api.jobs import make_voices
from reels_api.videos import split_scenes


def test_characters_become_words_and_follow_the_reading_speed():
    alignment = {
        "characters": list("hai ba"),
        "character_start_times_seconds": [0, 0.1, 0.2, 0.3, 0.3, 0.4],
        "character_end_times_seconds": [0.1, 0.2, 0.3, 0.3, 0.4, 0.5],
    }
    assert tts.words_from_alignment(alignment) == [
        {"text": "hai", "start": 0.0, "end": 0.3},
        {"text": "ba", "start": 0.3, "end": 0.5},
    ]
    # Sped up 2×, each word comes twice as early.
    assert tts.words_from_alignment(alignment, 2.0)[1] == {"text": "ba", "start": 0.15, "end": 0.25}


@pytest.mark.parametrize(
    "alignment",
    [
        None,
        {},
        {"characters": ["a"]},
        {"characters": ["a"], "character_start_times_seconds": [0], "character_end_times_seconds": []},
    ],
)
def test_an_answer_without_a_usable_alignment_gives_no_words(alignment):
    assert tts.words_from_alignment(alignment) == []


@pytest.fixture
def me(db):
    return make_user(db)


@needs_ffmpeg
def test_cumulative_narration_keeps_each_words_seconds_and_other_captions_do_not(db, me, storage, fakes):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    scene.voice_text = TEN_WORDS
    video.options = video_options.DEFAULTS | {"captions": "cumulative"}
    db.commit()
    make_voices(db, video, split_scenes(db, video)[1], storage)
    assert [word["text"] for word in scene.voice_words] == TEN_WORDS.split()
    assert scene.voice_words[1]["start"] == pytest.approx(0.3, abs=0.01)  # 0.3 s a word in the fake voice

    video.options = video_options.DEFAULTS | {"captions": "word"}
    scene.voice_text = TEN_WORDS + " mười một"  # a new text: the narration is made again, now with no timings
    db.commit()
    make_voices(db, video, split_scenes(db, video)[1], storage)
    assert scene.voice_words is None
