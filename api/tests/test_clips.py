import json
import re
import subprocess

import pytest
from conftest import clip_bytes, needs_ffmpeg

from reels_api import clips
from reels_api.uploads import UploadRejected

REFUSED = "Video phải là MP4, MOV hoặc WebM (H.264, HEVC hoặc VP9) và không bị hỏng"


@pytest.mark.parametrize("data", [
    b"#EXTM3U\n#EXTINF:1,\nfile:///etc/passwd\n",  # a playlist that would make FFmpeg open other files
    b"ffconcat version 1.0\nfile /etc/passwd\n",
    b"\x89PNG\r\n\x1a\n" + bytes(64),
])
def test_anything_but_an_mp4_mov_or_webm_container_is_refused_before_ffprobe_runs(tmp_path, monkeypatch, data):
    monkeypatch.setattr(clips, "_run", lambda argv: pytest.fail("ffprobe must not open this file"))
    path = tmp_path / "clip.mp4"
    path.write_bytes(data)
    with pytest.raises(UploadRejected, match=re.escape(REFUSED)):
        clips.check_clip(path)


@needs_ffmpeg
def test_a_phone_clip_is_accepted_with_its_length(tmp_path):
    path = tmp_path / "upload"
    path.write_bytes(clip_bytes(tmp_path, seconds=2))
    clip = clips.check_clip(path)
    assert clip.extension == "mp4"
    assert clip.seconds == pytest.approx(2, abs=0.1)


@needs_ffmpeg
def test_a_vp9_webm_is_accepted_through_the_matroska_demuxer(tmp_path):
    path = tmp_path / "upload"
    path.write_bytes(clip_bytes(tmp_path, seconds=2, codec="libvpx-vp9", extension="webm", rate=5))
    clip = clips.check_clip(path)
    assert clip.extension == "webm"
    assert clip.seconds == pytest.approx(2, abs=0.1)
    assert clips.frame_at(path, 0.5).size == (1280, 720)


@needs_ffmpeg
def test_an_mp4_with_another_codec_is_refused(tmp_path):
    path = tmp_path / "upload"
    path.write_bytes(clip_bytes(tmp_path, seconds=2, codec="mpeg4"))
    with pytest.raises(UploadRejected, match=re.escape(REFUSED)):
        clips.check_clip(path)


@needs_ffmpeg
@pytest.mark.parametrize(("seconds", "size", "message"), [
    (0.5, "1280x720", "Video phải dài từ 1 đến 60 giây"),
    (61, "1280x720", "Video phải dài từ 1 đến 60 giây"),
    (2, "640x360", "Video phải có cạnh ngắn từ 720 px"),
    (1, "4112x720", "cạnh dài tối đa 4096 px"),
])
def test_clips_outside_the_length_or_size_limits_are_refused(tmp_path, seconds, size, message):
    path = tmp_path / "upload"
    path.write_bytes(clip_bytes(tmp_path, seconds=seconds, size=size, rate=2))
    with pytest.raises(UploadRejected, match=message):
        clips.check_clip(path)


@needs_ffmpeg
def test_frame_at_returns_the_frame_at_the_start_time(tmp_path):
    path = tmp_path / "upload"
    path.write_bytes(clip_bytes(tmp_path, seconds=2))
    first, later = clips.frame_at(path, 0), clips.frame_at(path, 1.5)
    assert first.size == (1280, 720)
    assert first.tobytes() != later.tobytes(), "testsrc2 moves, so a later start shows another frame"


def test_every_video_stream_is_checked_not_only_the_first(tmp_path, monkeypatch):
    streams = [
        {"codec_type": "video", "codec_name": "h264", "width": 720, "height": 1280},
        {"codec_type": "video", "codec_name": "png", "width": 16000, "height": 16000},
    ]
    monkeypatch.setattr(clips, "_tool", lambda name: name)
    monkeypatch.setattr(clips, "_run", lambda argv: json.dumps({"streams": streams, "format": {"duration": "2"}}))
    path = tmp_path / "clip.mov"
    path.write_bytes(b"\x00\x00\x00\x18ftypqt  " + bytes(16))
    with pytest.raises(UploadRejected, match=re.escape(REFUSED)):
        clips.check_clip(path)


@needs_ffmpeg
def test_the_length_is_the_video_streams_not_a_longer_audio_tracks(tmp_path):
    path = tmp_path / "upload.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=25:duration=2",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=4", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )
    assert clips.check_clip(path).seconds == pytest.approx(2, abs=0.1)


@needs_ffmpeg
def test_a_frame_that_grows_past_the_limit_mid_stream_is_never_decoded(tmp_path, monkeypatch):
    """ffprobe sees the 720×1280 headers; from 1 s on the H.264 stream itself switches to 4800×4800."""
    parts = []
    for size, name in (("720x1280", "a"), ("4800x4800", "b")):
        part = tmp_path / f"{name}.h264"
        seconds = 2 if name == "a" else 1
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=size={size}:rate=2:duration={seconds}",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-f", "h264", str(part)], check=True)
        parts.append(part.read_bytes())
    joined = tmp_path / "ab.h264"
    joined.write_bytes(b"".join(parts))
    path = tmp_path / "upload.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-r", "2", "-f", "h264", "-i", str(joined), "-c", "copy", str(path)],
                   check=True)

    clips.check_clip(path)  # the headers pass
    assert clips.frame_at(path, 0).size == (720, 1280)
    with pytest.raises(clips.ClipError):
        clips.frame_at(path, 1.0)
    # Only the limit stops it: raised, the same frame decodes at its real size.
    monkeypatch.setattr(clips, "MAX_FRAME_PIXELS", 4800 * 4800)
    assert clips.frame_at(path, 1.0).size == (4800, 4800)
