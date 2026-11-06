"""Automatic QC of a rendered MP4 (qc.py) on clips FFmpeg makes, and the render job storing it with the MP4."""

import subprocess

from conftest import needs_ffmpeg
from test_worker import rendered_mp4, short_video  # noqa: F401  (short_video is a fixture)
from worker_helpers import committed  # noqa: F401  (fixture)

from reels_api import qc
from reels_api.models import Video


def clip(path, seconds=25, volume=1.0, video_filter="null", audio_filter="anull", size="1080x1920"):
    """A moving test pattern with a tone; at volume 1.0 the tone is close to the platforms' -14 LUFS."""
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=30:duration={seconds}",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds},volume={volume}",
            "-vf", video_filter, "-af", audio_filter,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path),
        ],
        check=True,
    )  # fmt: skip
    return path


def by_id(result: dict) -> dict:
    return {check["id"]: check for check in result["checks"]}


@needs_ffmpeg
def test_a_clean_vertical_video_at_the_platforms_loudness_passes(tmp_path):
    result = qc.measure(clip(tmp_path / "good.mp4", volume=2.6), expect_sound=True)
    checks = by_id(result)
    assert result["status"] == "pass", result
    assert checks["loudness"]["status"] == "pass" and "LUFS" in checks["loudness"]["detail"]
    assert {"format", "duration", "true_peak", "black", "freeze"} <= checks.keys()


@needs_ffmpeg
def test_black_frames_dead_air_and_quiet_sound_are_named_with_their_times(tmp_path):
    bad = clip(
        tmp_path / "bad.mp4",
        volume=0.2,
        video_filter="drawbox=enable='between(t,10,11.5)':color=black:t=fill",
        audio_filter="volume=enable='between(t,15,17.5)':volume=0",
    )
    result = qc.measure(bad, expect_sound=True)
    checks = by_id(result)
    assert result["status"] == "fail"
    assert checks["black"]["status"] == "fail" and "10.0–11.5s" in checks["black"]["detail"]
    assert checks["dead_air"]["status"] == "warn" and "15.0–17.5s" in checks["dead_air"]["detail"]
    assert checks["loudness"]["status"] == "fail" and "nhỏ quá" in checks["loudness"]["detail"]


@needs_ffmpeg
def test_wrong_size_and_a_short_video_fail(tmp_path):
    result = qc.measure(clip(tmp_path / "wide.mp4", seconds=3, volume=2.6, size="1280x720"), expect_sound=True)
    checks = by_id(result)
    assert checks["format"]["status"] == "fail" and "1080×1920" in checks["format"]["detail"]
    assert checks["duration"]["status"] == "fail"


@needs_ffmpeg
def test_silence_fails_only_when_the_video_should_have_sound(tmp_path):
    quiet = clip(tmp_path / "quiet.mp4", audio_filter="volume=0")
    assert by_id(qc.measure(quiet, expect_sound=True))["loudness"]["status"] == "fail"
    assert by_id(qc.measure(quiet, expect_sound=False))["loudness"]["status"] == "warn"


def test_an_unreadable_file_is_a_warning_not_a_failed_render(tmp_path):
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"not a video")
    result = qc.measure(broken, expect_sound=True)
    assert result["status"] == "warn" and result["checks"][0]["id"] == "read"


@needs_ffmpeg
def test_the_render_job_stores_the_qc_of_the_mp4_it_made(committed, short_video):  # noqa: F811
    user, storage, video_id = short_video
    rendered_mp4(committed, storage, video_id, user.id)
    with committed() as db:
        result = db.get(Video, video_id).qc
    checks = by_id(result)
    # A 2-second silent test video: too short, and silent is only a warning with narration and music off.
    assert checks["format"]["status"] == "pass"
    assert checks["duration"]["status"] == "fail" and result["status"] == "fail"
    assert checks["loudness"]["status"] == "warn" and checks["loudness"]["detail"] == "Video không có tiếng"
