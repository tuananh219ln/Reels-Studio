import os
import tempfile
from fractions import Fraction

import pytest
from PIL import ImageChops, ImageStat

from conftest import extract_frame, make_clip, make_image, make_tone, mean_volume, needs_ffmpeg, script_data, urls, write_script
from reels_render import render as render_module
from reels_render.errors import (
    FFmpegError,
    MissingImagesError,
    OutputNotReplacedError,
    RenderError,
    StockSearchError,
    ToolNotFoundError,
)
from reels_render.ffmpeg import probe
from reels_render.render import render_video
from reels_render.script import load_script
from reels_render.textbox import SCENE_BOX_BOTTOM

FRAME = 1 / 30


@pytest.fixture
def isolated_tmp(tmp_path, monkeypatch):
    """Point intermediate files at a known folder so leftovers can be detected."""
    folder = tmp_path / "system-tmp"
    folder.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(folder))
    return folder


def short_script(folder, seconds=(1, 1)):
    """Bright, non-9:16 images: landscape for the title, square for content scenes."""
    make_image(folder / "ngang.jpg", (1600, 900), (190, 215, 240))
    make_image(folder / "vuong.jpg", (1000, 1000), (240, 200, 205))
    data = script_data(scene_count=len(seconds) - 1, image="ngang.jpg", seconds=seconds[0])
    for item, value in zip(data["scenes"], seconds[1:]):
        item.update(image="vuong.jpg", seconds=value)
    return load_script(write_script(folder, data))


def difference(first, second) -> float:
    """Mean absolute difference per channel, 0–255."""
    return sum(ImageStat.Stat(ImageChops.difference(first, second)).mean) / 3


def streams(info, kind):
    return [s for s in info["streams"] if s["codec_type"] == kind]


@pytest.fixture(scope="module")
def video(tmp_path_factory):
    folder = tmp_path_factory.mktemp("render")
    script = short_script(folder, seconds=(1, 1.5, 1.5))
    return render_video(script, folder / "out" / "video.mp4"), folder


@needs_ffmpeg
class TestOutput:
    def test_format(self, video):
        path, _ = video
        info = probe("ffprobe", path)
        (stream,) = streams(info, "video")
        assert (stream["width"], stream["height"]) == (1080, 1920)
        assert Fraction(stream["r_frame_rate"]) == 30
        assert stream["codec_name"] == "h264"
        assert stream["pix_fmt"] == "yuv420p"
        assert float(info["format"]["duration"]) == pytest.approx(4.0, abs=FRAME)
        assert float(stream["duration"]) == pytest.approx(4.0, abs=FRAME)

    def test_silent_audio_track_covers_whole_video(self, video):
        path, _ = video
        (audio,) = streams(probe("ffprobe", path), "audio")
        assert audio["codec_name"] == "aac"
        assert float(audio["duration"]) == pytest.approx(4.0, abs=0.05)
        assert mean_volume(path, 0, 4) < -80

    def test_frame_is_covered_edge_to_edge(self, video):
        path, folder = video
        frame = extract_frame(path, 1.75, folder / "mid-scene-1.png")  # middle of content scene 1
        w, h = frame.size
        border = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]
        for point in border:
            assert min(frame.getpixel(point)) > 60, f"viền tối tại {point}"

    def test_content_box_bottom_is_at_lower_third_line(self, video):
        path, folder = video
        frame = extract_frame(path, 1.75, folder / "box.png")

        def yellow(y):
            r, g, b = frame.getpixel((540, y))
            return r > 200 and g > 170 and b < 100

        assert yellow(SCENE_BOX_BOTTOM - 3)
        assert not any(yellow(y) for y in range(SCENE_BOX_BOTTOM + 4, 1920))

    def test_first_frame_is_title_with_text(self, video):
        path, folder = video
        frame = extract_frame(path, 0, folder / "first.png")
        centre = [frame.getpixel((x, 960)) for x in range(200, 880)]
        assert any(p[0] > 200 and p[1] > 170 and p[2] < 100 for p in centre), "khung đầu không có hộp vàng"
        assert min(frame.getpixel((5, 5))) > 150, "khung đầu bị fade từ đen"

    def test_no_leftover_files(self, video):
        path, _ = video
        assert sorted(p.name for p in path.parent.iterdir()) == ["video.mp4"]


@needs_ffmpeg
class TestMusic:
    def render(self, tmp_path, tone_seconds, **volume):
        script = short_script(tmp_path, seconds=(1, 1, 1))
        tone = make_tone(tmp_path / "tone.wav", tone_seconds)
        output = render_video(script, tmp_path / "video.mp4", music=tone, **volume)
        return output, mean_volume(tone, 0, min(tone_seconds, 1))

    def test_short_music_loops_at_default_volume_and_fades_out(self, tmp_path):
        output, tone_level = self.render(tmp_path, tone_seconds=1)
        middle = mean_volume(output, 0.2, 1.0)
        assert middle == pytest.approx(tone_level - 12, abs=1.5)
        assert mean_volume(output, 1.1, 0.3) > -40, "nhạc ngắn không được lặp"
        assert mean_volume(output, 2.8, 0.2) <= middle - 20

    def test_long_music_is_cut_and_volume_is_configurable(self, tmp_path):
        output, tone_level = self.render(tmp_path, tone_seconds=5, music_volume=0.5)
        (audio,) = streams(probe("ffprobe", output), "audio")
        assert float(audio["duration"]) == pytest.approx(3.0, abs=0.05)
        assert mean_volume(output, 0.2, 1.0) == pytest.approx(tone_level - 6, abs=1.5)


@needs_ffmpeg
class TestVoice:
    def test_scene_is_lengthened_and_narration_plays_on_it(self, tmp_path):
        make_tone(tmp_path / "loi-doc.wav", 2.5)
        short_script(tmp_path)  # writes the images
        data = script_data(scene_count=2, image="ngang.jpg", seconds=1)
        for item in data["scenes"]:
            item.update(image="vuong.jpg", seconds=1)
        data["scenes"][0]["voice"] = "loi-doc.wav"
        script = load_script(write_script(tmp_path, data))
        output = render_video(script, tmp_path / "video.mp4")

        info = probe("ffprobe", output)
        # Title 1 s + scene 1 lengthened to 0.2 + 2.5 + 0.4 = 3.1 s + scene 2 1 s.
        assert float(info["format"]["duration"]) == pytest.approx(5.1, abs=0.05)
        assert mean_volume(output, 0.1, 0.8) < -60, "cảnh tiêu đề không có lời đọc"
        assert mean_volume(output, 1.4, 2.0) > -30
        assert mean_volume(output, 4.3, 0.7) < -60, "lời đọc không được tràn sang cảnh sau"

    def test_narration_is_mixed_at_full_level_over_the_music(self, tmp_path):
        make_tone(tmp_path / "loi-doc.wav", 1.0)
        tone = make_tone(tmp_path / "nhac.wav", 5)
        short_script(tmp_path)  # writes the images
        data = script_data(scene_count=1, image="ngang.jpg", seconds=1)
        data["scenes"][0].update(image="vuong.jpg", seconds=2, voice="loi-doc.wav")
        script = load_script(write_script(tmp_path, data))
        output = render_video(script, tmp_path / "video.mp4", music=tone, music_volume=0.25)

        assert float(probe("ffprobe", output)["format"]["duration"]) == pytest.approx(3.0, abs=0.05)
        tone_level = mean_volume(tone, 0, 1)
        music_only = mean_volume(output, 0.2, 0.6)
        assert music_only == pytest.approx(tone_level - 12, abs=1.5)
        # Narration (same tone, full level) plus the music at 25%: louder than the narration alone.
        assert mean_volume(output, 1.4, 0.6) > tone_level - 1

    def test_unreadable_voice_file_is_named_before_ffmpeg(self, tmp_path):
        short_script(tmp_path)
        (tmp_path / "hong.mp3").write_bytes(b"not audio at all")
        data = script_data(scene_count=1, image="ngang.jpg", seconds=1)
        data["scenes"][0].update(image="vuong.jpg", voice="hong.mp3")
        script = load_script(write_script(tmp_path, data))
        with pytest.raises(RenderError, match="Cảnh 1: file lời đọc không đọc được"):
            render_video(script, tmp_path / "video.mp4")
        assert not (tmp_path / "video.mp4").exists()


@needs_ffmpeg
class TestVideoScene:
    def test_clip_is_cropped_to_30_fps_held_on_its_last_frame_and_muted(self, tmp_path):
        make_clip(tmp_path / "vuon.mp4", 2, rate=25)
        short_script(tmp_path)  # writes the images
        data = script_data(scene_count=2, image="", video="vuon.mp4", video_start=0.5, seconds=2)
        data["scenes"][0].update(image="vuong.jpg", seconds=1)
        # The default start: still the moving clip, never a zoomed still.
        data["scenes"][1].update(image="", video="vuon.mp4", seconds=1)
        output = render_video(load_script(write_script(tmp_path, data)), tmp_path / "video.mp4")

        info = probe("ffprobe", output)
        (video,) = streams(info, "video")
        assert (video["width"], video["height"]) == (1080, 1920)
        assert Fraction(video["avg_frame_rate"]) == 30
        # The clip has 1.5 s left after its start; the 2 s title holds its last frame for the rest.
        assert float(info["format"]["duration"]) == pytest.approx(4.0, abs=0.05)
        assert mean_volume(output, 0.1, 1.5) < -60, "tiếng gốc của video không được lọt vào MP4"
        # testsrc2 changes every frame, so only a held frame stays this close to the next one.
        held = [extract_frame(output, seconds, tmp_path / f"held-{seconds}.png") for seconds in (1.6, 1.75)]
        moving = [extract_frame(output, seconds, tmp_path / f"moving-{seconds}.png") for seconds in (0.3, 0.5)]
        assert difference(*held) < 1 < difference(*moving)
        last = [extract_frame(output, seconds, tmp_path / f"last-{seconds}.png") for seconds in (3.4, 3.6)]
        assert difference(*last) > 1, "a clip starting at 0 moves like footage"


@needs_ffmpeg
class TestOutputFile:
    def test_success_leaves_no_temp_or_intermediate_files(self, tmp_path, isolated_tmp):
        script = short_script(tmp_path)
        output = render_video(script, tmp_path / "out" / "video.mp4")
        assert sorted(p.name for p in output.parent.iterdir()) == ["video.mp4"]
        assert list(isolated_tmp.iterdir()) == []

    def test_ffmpeg_failure_keeps_old_output(self, tmp_path, isolated_tmp):
        script = short_script(tmp_path)
        output = tmp_path / "out" / "video.mp4"
        output.parent.mkdir()
        output.write_bytes(b"old video")
        bad_music = tmp_path / "hong.mp3"
        bad_music.write_bytes(b"not audio at all")

        with pytest.raises(FFmpegError) as err:
            render_video(script, output, music=bad_music)
        assert err.value.stderr_tail
        assert output.read_bytes() == b"old video"
        assert sorted(p.name for p in output.parent.iterdir()) == ["video.mp4"]
        assert list(isolated_tmp.iterdir()) == []

    def lock(self, monkeypatch, locked):
        real_replace = os.replace
        calls = []

        def fake_replace(src, dst):
            calls.append(dst)
            if os.path.basename(dst) in locked or "*" in locked:
                raise PermissionError(13, "giả lập file bị khóa", str(dst))
            return real_replace(src, dst)

        monkeypatch.setattr(render_module.os, "replace", fake_replace)
        return calls

    def test_locked_target_keeps_new_copy(self, tmp_path, monkeypatch):
        script = short_script(tmp_path)
        output = tmp_path / "video.mp4"
        output.write_bytes(b"old video")
        self.lock(monkeypatch, {"video.mp4"})

        with pytest.raises(OutputNotReplacedError) as err:
            render_video(script, output)
        kept = tmp_path / "video.new.mp4"
        assert err.value.kept_path == kept
        assert kept.stat().st_size > 1000
        assert output.read_bytes() == b"old video"
        assert "file đích đang bị mở" in str(err.value)
        assert str(kept) in str(err.value)
        assert not list(tmp_path.glob("*.tmp"))

    def test_locked_target_and_new_name_use_next_number(self, tmp_path, monkeypatch):
        script = short_script(tmp_path)
        output = tmp_path / "video.mp4"
        (tmp_path / "video.new.mp4").write_bytes(b"older copy")
        self.lock(monkeypatch, {"video.mp4", "video.new.mp4"})

        with pytest.raises(OutputNotReplacedError) as err:
            render_video(script, output)
        kept = tmp_path / "video.new-2.mp4"
        assert err.value.kept_path == kept
        assert kept.exists()
        assert str(kept) in str(err.value)
        assert not list(tmp_path.glob("*.tmp"))

    def test_every_rename_failing_keeps_temp_file(self, tmp_path, monkeypatch):
        script = short_script(tmp_path)
        output = tmp_path / "video.mp4"
        calls = self.lock(monkeypatch, {"*"})

        with pytest.raises(OutputNotReplacedError) as err:
            render_video(script, output)
        assert len(calls) == 10
        temp = err.value.kept_path
        assert temp.exists() and temp.suffix == ".tmp" and temp.parent == tmp_path
        message = str(err.value)
        assert str(temp) in message
        assert "giả lập file bị khóa" in message
        assert "file đích đang bị mở" not in message


def test_missing_ffmpeg_is_typed_error_with_install_hint(tmp_path, monkeypatch):
    make_image(tmp_path / "a.jpg", (40, 40))
    script = load_script(write_script(tmp_path, script_data()))
    monkeypatch.setattr("reels_render.ffmpeg.shutil.which", lambda name: None if name == "ffprobe" else "ffmpeg")
    with pytest.raises(ToolNotFoundError, match="Không tìm thấy ffprobe.*winget install Gyan.FFmpeg"):
        render_video(script, tmp_path / "out" / "v.mp4")
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("volume", [-0.1, 1.5, float("nan")])
def test_music_volume_out_of_range(tmp_path, monkeypatch, volume):
    make_image(tmp_path / "a.jpg", (40, 40))
    script = load_script(write_script(tmp_path, script_data()))
    monkeypatch.setattr("reels_render.ffmpeg.shutil.which", lambda name: name)
    with pytest.raises(render_module.InputError, match="từ 0 đến 1"):
        render_video(script, tmp_path / "v.mp4", music=tmp_path / "a.jpg", music_volume=volume)


def test_missing_music_file(tmp_path, monkeypatch):
    make_image(tmp_path / "a.jpg", (40, 40))
    script = load_script(write_script(tmp_path, script_data()))
    monkeypatch.setattr("reels_render.ffmpeg.shutil.which", lambda name: name)
    missing = tmp_path / "khong-co.mp3"
    with pytest.raises(render_module.InputError, match="Không tìm thấy file nhạc") as err:
        render_video(script, tmp_path / "v.mp4", music=missing)
    assert str(missing) in str(err.value)


def test_output_path_that_is_a_folder_is_rejected_before_ffmpeg(tmp_path, monkeypatch):
    make_image(tmp_path / "a.jpg", (40, 40))
    script = load_script(write_script(tmp_path, script_data()))
    monkeypatch.setattr("reels_render.ffmpeg.shutil.which", lambda name: name)
    monkeypatch.setattr("reels_render.ffmpeg.run", lambda *a: pytest.fail("FFmpeg must not run"))
    with pytest.raises(render_module.InputError, match="là một thư mục"):
        render_video(script, tmp_path)


def test_output_folder_that_cannot_be_created_is_typed_error(tmp_path, monkeypatch):
    make_image(tmp_path / "a.jpg", (40, 40))
    script = load_script(write_script(tmp_path, script_data()))
    monkeypatch.setattr("reels_render.ffmpeg.shutil.which", lambda name: name)
    monkeypatch.setattr("reels_render.ffmpeg.run", lambda *a: pytest.fail("FFmpeg must not run"))
    blocker = tmp_path / "a-file"
    blocker.write_bytes(b"x")
    with pytest.raises(render_module.InputError, match="Không tạo được file đầu ra"):
        render_video(script, blocker / "v.mp4")


def test_title_scene_uses_title_box_style(tmp_path, monkeypatch):
    make_image(tmp_path / "a.jpg", (40, 40))
    data = script_data(text="a\nb\nc\nd\ne")  # 5 lines: allowed for the title, not for content scenes
    script = load_script(write_script(tmp_path, data))
    monkeypatch.setattr("reels_render.ffmpeg.shutil.which", lambda name: name)
    monkeypatch.setattr("reels_render.ffmpeg.run", lambda *a: None)
    render_video(script, tmp_path / "v.mp4")

    data["scenes"][0]["text"] = "a\nb\nc\nd"
    script = load_script(write_script(tmp_path, data))
    with pytest.raises(render_module.InputError, match="^Cảnh 1: chữ quá dài"):
        render_video(script, tmp_path / "v.mp4")


def test_text_too_long_names_scene_before_ffmpeg(tmp_path, monkeypatch):
    make_image(tmp_path / "a.jpg", (40, 40))
    data = script_data(scene_count=2)
    data["scenes"][1]["text"] = "Rau cải xanh nấu canh ngon\nCó canxi và vitamin K tốt cho xương"
    script = load_script(write_script(tmp_path, data))
    monkeypatch.setattr("reels_render.ffmpeg.shutil.which", lambda name: name)
    monkeypatch.setattr("reels_render.ffmpeg.run", lambda *a: pytest.fail("FFmpeg must not run"))
    with pytest.raises(render_module.InputError, match="^Cảnh 2: chữ quá dài"):
        render_video(script, tmp_path / "out" / "v.mp4")
    assert not (tmp_path / "out").exists()


def test_broken_image_reported_before_ffmpeg_and_output_untouched(tmp_path, monkeypatch):
    make_image(tmp_path / "a.jpg", (40, 40))
    (tmp_path / "hong.jpg").write_bytes(b"broken")
    data = script_data(scene_count=1)
    data["scenes"][0]["image"] = "hong.jpg"
    script = load_script(write_script(tmp_path, data))
    monkeypatch.setattr("reels_render.ffmpeg.shutil.which", lambda name: name)
    monkeypatch.setattr("reels_render.ffmpeg.run", lambda *a: pytest.fail("FFmpeg must not run"))
    with pytest.raises(render_module.InputError, match="^Cảnh 1: ảnh hỏng"):
        render_video(script, tmp_path / "out" / "v.mp4")
    assert not (tmp_path / "out").exists()


def test_scene_left_without_image_is_typed_error_before_ffmpeg(tmp_path, monkeypatch):
    make_image(tmp_path / "a.jpg", (40, 40))
    script = load_script(write_script(tmp_path, script_data(image="")))
    monkeypatch.setattr("reels_render.ffmpeg.shutil.which", lambda name: name)
    monkeypatch.setattr("reels_render.ffmpeg.run", lambda *a: pytest.fail("FFmpeg must not run"))
    with pytest.raises(MissingImagesError) as err:
        render_video(script, tmp_path / "out" / "v.mp4")
    assert isinstance(err.value, RenderError)
    assert err.value.labels == ["Cảnh tiêu đề"]
    assert not (tmp_path / "out").exists()


def test_failed_image_search_stops_before_ffmpeg(tmp_path, monkeypatch):
    make_image(tmp_path / "a.jpg", (40, 40))
    data = script_data()
    data["scenes"][0]["image"] = ""
    script = load_script(write_script(tmp_path, data))
    monkeypatch.setattr("reels_render.ffmpeg.shutil.which", lambda name: name)
    monkeypatch.setattr("reels_render.ffmpeg.run", lambda *a: pytest.fail("FFmpeg must not run"))
    with pytest.raises(StockSearchError, match="PIXABAY_API_KEY"):
        render_video(script, tmp_path / "out" / "v.mp4")
    assert not (tmp_path / "out").exists()


@needs_ffmpeg
def test_script_without_images_renders_with_stock_photos(tmp_path, pixabay, isolated_tmp):
    data = script_data(scene_count=2, image="", keywords=["món ăn giàu canxi"])
    for item in data["scenes"]:
        item["image"] = ""
    pixabay.results["món ăn giàu canxi"] = urls("canxi", 2)
    pixabay.results["Cá nhỏ"] = urls("ca", 3)
    script = load_script(write_script(tmp_path, data))

    output = render_video(script, tmp_path / "out" / "video.mp4")

    (stream,) = streams(probe("ffprobe", output), "video")
    assert (stream["width"], stream["height"]) == (1080, 1920)
    assert len(pixabay.downloads) == 3
    assert list(isolated_tmp.iterdir()) == []
