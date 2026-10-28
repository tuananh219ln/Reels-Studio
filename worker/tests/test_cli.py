import subprocess
import sys

from conftest import make_image, needs_ffmpeg, script_data, write_script


def run_cli(*args, cwd):
    return subprocess.run(
        [sys.executable, "-m", "reels_render", *map(str, args)],
        capture_output=True, encoding="utf-8", errors="replace", cwd=cwd,
    )


def test_missing_image_exits_non_zero_and_names_scene(tmp_path):
    make_image(tmp_path / "a.jpg", (40, 40))
    data = script_data(scene_count=2)
    data["scenes"][1]["image"] = "khong-co.jpg"
    script = write_script(tmp_path, data)
    output = tmp_path / "out" / "video.mp4"

    result = run_cli(script, "-o", output, cwd=tmp_path)

    assert result.returncode != 0
    assert "Cảnh 2: không tìm thấy file ảnh" in result.stderr
    assert "Traceback" not in result.stderr
    assert not output.exists()
    assert not output.parent.exists()


@needs_ffmpeg
def test_invalid_music_volume_is_rejected(tmp_path):
    make_image(tmp_path / "a.jpg", (40, 40))
    script = write_script(tmp_path, script_data())
    result = run_cli(script, "-o", tmp_path / "v.mp4", "--music", tmp_path / "a.jpg", "--music-volume", "2", cwd=tmp_path)
    assert result.returncode != 0
    assert "từ 0 đến 1" in result.stderr
    assert not (tmp_path / "v.mp4").exists()


@needs_ffmpeg
def test_success_creates_output_folder_and_reports_path_and_time(tmp_path):
    make_image(tmp_path / "a.jpg", (1080, 1920))
    script = write_script(tmp_path, script_data())
    output = tmp_path / "chua co" / "thu muc" / "video.mp4"

    result = run_cli(script, "-o", output, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert output.is_file()
    assert str(output) in result.stdout
    assert "Thời gian render:" in result.stdout
