import json

import pytest

from conftest import make_image, scene, write_script
from reels_render.errors import InputError
from reels_render.script import load_script


@pytest.fixture
def folder(tmp_path):
    make_image(tmp_path / "a.jpg", (40, 40))
    return tmp_path


def load(folder, data):
    return load_script(write_script(folder, data))


def test_valid_script_resolves_images_relative_to_json(folder):
    nested = folder / "kb"
    nested.mkdir()
    make_image(nested / "img" / "x.jpg", (40, 40))
    data = {"title": scene(image="img/x.jpg"), "scenes": [scene(image="img/x.jpg", seconds=3.5)]}
    script = load(nested, data)
    assert script.title.image == nested / "img" / "x.jpg"
    assert script.title.label == "Cảnh tiêu đề"
    assert script.scenes[0].label == "Cảnh 1"
    assert script.scenes[0].seconds == 3.5


def test_missing_script_file(tmp_path):
    with pytest.raises(InputError, match="Không tìm thấy file kịch bản"):
        load_script(tmp_path / "khong-co.json")


def test_broken_json_names_file(folder):
    path = folder / "script.json"
    path.write_text('{"title": ', encoding="utf-8")
    with pytest.raises(InputError, match="JSON lỗi cú pháp") as err:
        load_script(path)
    assert str(path) in str(err.value)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ([], "object JSON"),
        ({"scenes": [scene()]}, "thiếu trường \"title\""),
        ({"title": scene()}, "thiếu trường \"scenes\""),
        ({"title": scene(), "scenes": []}, "không có cảnh nội dung"),
        ({"title": scene(), "scenes": {"a": scene()}}, "\"scenes\" phải là một danh sách"),
    ],
)
def test_structure_errors(folder, data, message):
    with pytest.raises(InputError, match=message):
        load(folder, data)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"seconds": "4"}, "\"seconds\" phải là số"),
        ({"seconds": True}, "\"seconds\" phải là số"),
        ({"seconds": None}, "\"seconds\" phải là số"),
        ({"seconds": 0.5}, "từ 1 trở lên"),
        ({"text": 5}, "\"text\" phải là chuỗi"),
        ({"image": 3}, "\"image\" phải là chuỗi"),
        ({"image": ""}, "thiếu ảnh"),
        ({"image": "khong-co.jpg"}, "không tìm thấy file ảnh"),
        ({"text": "   "}, "chữ trống"),
        ({"text": "a\n\nb"}, "dòng trống"),
        ({"text": "a *b"}, "không đóng cặp"),
        ({"text": "a ** b"}, "\\*\\* rỗng"),
    ],
)
def test_scene_errors_name_the_scene(folder, override, message):
    data = {"title": scene(), "scenes": [scene(), scene(), scene() | override]}
    with pytest.raises(InputError, match=message) as err:
        load(folder, data)
    assert str(err.value).startswith("Cảnh 3: ")


def test_title_errors_name_title(folder):
    with pytest.raises(InputError, match="^Cảnh tiêu đề: thiếu trường \"image\""):
        load(folder, {"title": {"text": "a", "seconds": 3}, "scenes": [scene()]})


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "1" + "0" * 400, "1e308"])
def test_non_finite_seconds(folder, value):
    title = json.dumps(scene())
    raw = f'{{"title": {title}, "scenes": [{{"text": "a", "seconds": {value}, "image": "a.jpg"}}]}}'
    path = folder / "script.json"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(InputError, match="^Cảnh 1: \"seconds\" phải là số hữu hạn"):
        load_script(path)
