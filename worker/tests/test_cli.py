import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from conftest import make_image, needs_ffmpeg, scene, script_data, urls, write_script
from reels_render import cli, stock
from reels_render.stock import NetworkError


def run_cli(*args, cwd):
    return subprocess.run(
        [sys.executable, "-m", "reels_render", *map(str, args)],
        capture_output=True, encoding="utf-8", errors="replace", cwd=cwd,
    )


class Terminal:
    """Interactive stdin: each item is one typed line, or an exception raised while reading."""

    def __init__(self, *lines, on_read=None):
        self.lines = list(lines)
        self.on_read = on_read or (lambda: None)

    def isatty(self):
        return True

    def readline(self):
        self.on_read()
        if not self.lines:
            return ""  # EOF
        line = self.lines.pop(0)
        if isinstance(line, BaseException):
            raise line
        return line + "\n"


@pytest.fixture
def renders(monkeypatch):
    """Replaces FFmpeg rendering; records the script each render received."""
    calls = []

    def fake_render(script, output, **options):
        assert all(item.image is not None and item.image.is_file() for item in script.all_scenes)
        calls.append(script)
        return Path(output)

    monkeypatch.setattr(cli, "render_video", fake_render)
    return calls


@pytest.fixture
def photo(tmp_path):
    """A photo in a folder whose name has spaces and Vietnamese, like a real drag-and-drop source."""
    return make_image(tmp_path / "ảnh của tôi" / "món cá.png", (60, 80))


def run_main(monkeypatch, script: Path, stdin) -> int:
    monkeypatch.setattr(sys, "stdin", stdin)
    return cli.main([str(script), "-o", str(script.parent / "out" / "v.mp4")])


def untitled_script(tmp_path) -> Path:
    """Title without image or keywords, content scene with its own image: only the title is asked."""
    make_image(tmp_path / "a.jpg", (40, 40))
    return write_script(tmp_path, script_data(image=""))


def test_title_without_keywords_is_asked_without_a_key_and_render_continues(tmp_path, monkeypatch, capsys, renders, photo):
    script = untitled_script(tmp_path)

    assert run_main(monkeypatch, script, Terminal(f'"{photo}"')) == 0

    out = capsys.readouterr().out
    assert "Cảnh tiêu đề (5 món) chưa có ảnh. Kéo thả ảnh vào đây rồi nhấn Enter:" in out
    copied = tmp_path / "script" / "00-5-mon.png"
    assert copied.read_bytes() == photo.read_bytes()
    assert json.loads(script.read_text(encoding="utf-8"))["title"]["image"] == "script/00-5-mon.png"
    (rendered,) = renders
    assert rendered.title.image == copied
    assert "Tìm ảnh: 0.0s (0 lượt gọi API) · Render: " in out


def test_time_spent_at_the_prompt_counts_as_neither_search_nor_render(tmp_path, monkeypatch, capsys, renders, photo):
    now = [0.0]
    monkeypatch.setattr(cli.time, "perf_counter", lambda: now[0])
    script = untitled_script(tmp_path)

    def user_thinks():
        now[0] += 100

    assert run_main(monkeypatch, script, Terminal(str(photo), on_read=user_thinks)) == 0
    assert "Tìm ảnh: 0.0s (0 lượt gọi API) · Render: 0.0s" in capsys.readouterr().out


def test_content_scene_image_is_named_by_number_and_unaccented_first_line(tmp_path, monkeypatch, pixabay, renders, photo):
    make_image(tmp_path / "a.jpg", (40, 40))
    data = script_data()
    data["scenes"][0] = scene("Đậu phụ chiên\nCanxi và *đạm*", image="", keywords=["xyzqwv"])
    script = write_script(tmp_path, data)

    assert run_main(monkeypatch, script, Terminal(str(photo))) == 0

    assert (tmp_path / "script" / "01-dau-phu-chien.png").is_file()
    assert json.loads(script.read_text(encoding="utf-8"))["scenes"][0]["image"] == "script/01-dau-phu-chien.png"


@pytest.mark.parametrize(
    "typed",
    ["{path}", '"{path}"', "'{path}'", "& '{path}'", "  & '{path}'  "],
    ids=["plain", "cmd", "powershell", "powershell-call", "spaces"],
)
def test_dragged_path_forms_from_windows_shells(tmp_path, monkeypatch, renders, photo, typed):
    script = untitled_script(tmp_path)
    assert run_main(monkeypatch, script, Terminal(typed.format(path=photo))) == 0
    assert (tmp_path / "script" / "00-5-mon.png").is_file()


def test_powershell_doubled_quote_inside_path(tmp_path, monkeypatch, renders):
    source = make_image(tmp_path / "it's here" / "a.jpg", (20, 20))
    script = untitled_script(tmp_path)
    typed = "& '" + str(source).replace("'", "''") + "'"
    assert run_main(monkeypatch, script, Terminal(typed)) == 0


def test_blank_wrong_and_non_image_inputs_ask_again(tmp_path, monkeypatch, capsys, renders, photo):
    script = untitled_script(tmp_path)
    text_file = tmp_path / "ghi-chu.txt"
    text_file.write_text("không phải ảnh", encoding="utf-8")

    stdin = Terminal("", str(tmp_path / "khong-co.jpg"), str(text_file), str(photo))
    assert run_main(monkeypatch, script, stdin) == 0

    captured = capsys.readouterr()
    assert captured.out.count("Cảnh tiêu đề (5 món) chưa có ảnh") == 4
    assert "Chưa nhập đường dẫn ảnh" in captured.err
    assert "Không thấy file ảnh" in captured.err
    assert "File không phải ảnh" in captured.err
    assert len(renders) == 1


def test_existing_name_gets_a_number_and_is_never_overwritten(tmp_path, monkeypatch, renders, photo):
    script = untitled_script(tmp_path)
    existing = tmp_path / "script" / "00-5-mon.png"
    existing.parent.mkdir()
    existing.write_bytes(b"older image")

    assert run_main(monkeypatch, script, Terminal(str(photo))) == 0

    assert existing.read_bytes() == b"older image"
    assert (tmp_path / "script" / "00-5-mon-2.png").read_bytes() == photo.read_bytes()
    assert json.loads(script.read_text(encoding="utf-8"))["title"]["image"] == "script/00-5-mon-2.png"


@pytest.mark.parametrize("stop", [KeyboardInterrupt(), EOFError()], ids=["ctrl-c", "eof"])
def test_stopping_keeps_earlier_answers_and_does_not_render(tmp_path, monkeypatch, capsys, pixabay, renders, photo, stop):
    make_image(tmp_path / "a.jpg", (40, 40))
    data = script_data(image="")
    data["scenes"][0] = scene("Cá kho tộ\nGiàu *canxi*", image="", keywords=["xyzqwv"])
    script = write_script(tmp_path, data)
    searched_before_prompt = []

    stdin = Terminal(str(photo), stop, on_read=lambda: searched_before_prompt.append(len(pixabay.searches)))
    assert run_main(monkeypatch, script, stdin) != 0

    assert searched_before_prompt[0] == 1, "every search finishes before the first prompt"
    saved = json.loads(script.read_text(encoding="utf-8"))
    assert saved["title"]["image"] == "script/00-5-mon.png"
    assert saved["scenes"][0]["image"] == ""
    assert "Cảnh 1 (Cá kho tộ) chưa có ảnh" in capsys.readouterr().out
    assert renders == []


def test_mixed_script_without_key_stops_before_any_prompt(tmp_path, monkeypatch, capsys, renders):
    make_image(tmp_path / "a.jpg", (40, 40))
    data = script_data(image="")
    data["scenes"][0]["image"] = ""
    script = write_script(tmp_path, data)
    before = script.read_bytes()
    stdin = Terminal("never read")

    assert run_main(monkeypatch, script, stdin) == 1

    err = capsys.readouterr().err
    assert "PIXABAY_API_KEY" in err and ".env" in err
    assert "Traceback" not in err
    assert stdin.lines == ["never read"]
    assert script.read_bytes() == before
    assert renders == []


def test_mixed_script_without_network_stops_before_any_prompt(tmp_path, monkeypatch, capsys, pixabay, renders):
    monkeypatch.setattr(stock, "RETRY_DELAY", 0)
    pixabay.results["Cá nhỏ"] = NetworkError("getaddrinfo failed")
    make_image(tmp_path / "a.jpg", (40, 40))
    data = script_data(image="")
    data["scenes"][0]["image"] = ""
    script = write_script(tmp_path, data)
    before = script.read_bytes()
    stdin = Terminal("never read")

    assert run_main(monkeypatch, script, stdin) == 1

    assert "Không kết nối được Pixabay" in capsys.readouterr().err
    assert stdin.lines == ["never read"]
    assert script.read_bytes() == before
    assert renders == []


def test_without_any_stdin_missing_images_are_a_typed_error(tmp_path, monkeypatch, capsys, renders):
    script = untitled_script(tmp_path)
    assert run_main(monkeypatch, script, None) == 1
    assert capsys.readouterr().err.startswith("Lỗi: Chưa có ảnh cho: Cảnh tiêu đề")
    assert renders == []


def test_without_a_terminal_missing_images_are_a_typed_error(tmp_path, monkeypatch, capsys, renders):
    script = untitled_script(tmp_path)
    before = script.read_bytes()

    assert run_main(monkeypatch, script, io.StringIO(f"{tmp_path / 'a.jpg'}\n")) == 1

    err = capsys.readouterr().err
    assert err.startswith("Lỗi: Chưa có ảnh cho: Cảnh tiêu đề")
    assert "Traceback" not in err
    assert script.read_bytes() == before
    assert renders == []


def test_stock_images_stay_out_of_the_script_and_temp_folder(tmp_path, monkeypatch, capsys, pixabay, renders):
    system_tmp = tmp_path / "system-tmp"
    system_tmp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(system_tmp))
    pixabay.results["Cá nhỏ"] = urls("ca", 3)
    make_image(tmp_path / "a.jpg", (40, 40))
    data = script_data()
    data["scenes"][0]["image"] = "khong-co.jpg"
    script = write_script(tmp_path, data)
    before = script.read_bytes()

    assert run_main(monkeypatch, script, Terminal()) == 0

    captured = capsys.readouterr()
    assert "Cảnh báo: Cảnh 1: không thấy file khong-co.jpg, sẽ tìm ảnh thay thế" in captured.err
    assert "(1 lượt gọi API) · Render: " in captured.out
    assert renders[0].scenes[0].image.is_relative_to(system_tmp)
    assert script.read_bytes() == before
    assert list(system_tmp.iterdir()) == []


@needs_ffmpeg
def test_invalid_music_volume_is_rejected(tmp_path):
    make_image(tmp_path / "a.jpg", (40, 40))
    script = write_script(tmp_path, script_data())
    result = run_cli(script, "-o", tmp_path / "v.mp4", "--music", tmp_path / "a.jpg", "--music-volume", "2", cwd=tmp_path)
    assert result.returncode != 0
    assert "từ 0 đến 1" in result.stderr
    assert not (tmp_path / "v.mp4").exists()


@needs_ffmpeg
def test_success_creates_output_folder_and_reports_path_and_times(tmp_path):
    make_image(tmp_path / "a.jpg", (1080, 1920))
    script = write_script(tmp_path, script_data())
    output = tmp_path / "chua co" / "thu muc" / "video.mp4"

    result = run_cli(script, "-o", output, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert output.is_file()
    assert str(output) in result.stdout
    assert "Tìm ảnh: 0.0s (0 lượt gọi API) · Render: " in result.stdout
