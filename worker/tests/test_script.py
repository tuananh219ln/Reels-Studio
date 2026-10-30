import json

import pytest

from conftest import make_image, scene, write_script
from reels_render.errors import InputError
from reels_render.script import load_script, write_scene_image


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
        ({"keywords": "cá kho"}, "\"keywords\" phải là danh sách"),
        ({"keywords": ["cá kho", 3]}, "từ khóa thứ 2 .* phải là chuỗi"),
        ({"keywords": ["  "]}, "từ khóa thứ 1 .* đang trống"),
        ({"keywords": ["a" * 101]}, "dài quá 100 ký tự"),
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
    with pytest.raises(InputError, match="^Cảnh tiêu đề: thiếu trường \"seconds\""):
        load(folder, {"title": {"text": "a"}, "scenes": [scene()]})


def test_keywords_are_kept_in_order_and_trimmed(folder):
    longest = "a" * 100
    data = {"title": scene(keywords=[" sữa chua ", "món ăn giàu canxi"]), "scenes": [scene(keywords=["cá kho tộ", longest])]}
    script = load(folder, data)
    assert script.title.keywords == ("sữa chua", "món ăn giàu canxi")
    assert script.scenes[0].keywords == ("cá kho tộ", longest)


@pytest.mark.parametrize("keywords", [None, []])
def test_content_scene_without_keywords_searches_its_first_line(folder, keywords):
    extra = {} if keywords is None else {"keywords": keywords}
    data = {"title": scene(**extra), "scenes": [scene("*Vừng* đen\nRắc vào *cháo*", **extra)]}
    script = load(folder, data)
    assert script.scenes[0].keywords == ("Vừng đen",)
    assert script.title.keywords == ()


def test_default_keyword_is_cut_to_100_characters(folder):
    script = load(folder, {"title": scene(), "scenes": [scene("ă" * 120 + "\nb")]})
    assert script.scenes[0].keywords == ("ă" * 100,)


@pytest.mark.parametrize("image", [None, "", "   "])
def test_empty_or_absent_image_is_not_an_error(folder, image):
    item = scene() if image is None else scene(image=image)
    if image is None:
        del item["image"]
    script = load(folder, {"title": scene(), "scenes": [item]})
    assert script.scenes[0].image is None
    assert script.scenes[0].missing_image is None


def test_image_that_does_not_exist_is_remembered_for_the_warning(folder):
    script = load(folder, {"title": scene(image="anh-ca.jpg"), "scenes": [scene()]})
    assert script.title.image is None
    assert script.title.missing_image == "anh-ca.jpg"
    assert script.scenes[0].image == folder / "a.jpg"


def test_write_scene_image_changes_only_that_scene(folder):
    data = {
        "title": scene("Tiêu đề", image="", keywords=["sữa chua"]),
        "scenes": [scene("Cá kho tộ\nGiàu *canxi*", image=""), scene(seconds=3.5)],
        "extra": {"ghi chú": "giữ nguyên"},
    }
    path = write_script(folder, data)

    write_scene_image(path, 1, "script/01-ca-kho-to.jpg")
    write_scene_image(path, 0, "script/00-tieu-de.png")

    raw = path.read_text(encoding="utf-8")
    assert "Cá kho tộ" in raw and "\\u" not in raw
    assert raw.startswith('{\n  "title"')
    data["title"]["image"] = "script/00-tieu-de.png"
    data["scenes"][0]["image"] = "script/01-ca-kho-to.jpg"
    assert json.loads(raw) == data
    assert sorted(p.name for p in folder.iterdir()) == ["a.jpg", "script.json"]


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "1" + "0" * 400, "1e308"])
def test_non_finite_seconds(folder, value):
    title = json.dumps(scene())
    raw = f'{{"title": {title}, "scenes": [{{"text": "a", "seconds": {value}, "image": "a.jpg"}}]}}'
    path = folder / "script.json"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(InputError, match="^Cảnh 1: \"seconds\" phải là số hữu hạn"):
        load_script(path)


def test_voice_resolves_relative_to_json_and_is_optional(folder):
    (folder / "doc.mp3").write_bytes(b"audio")
    script = load(folder, {"title": scene(voice=""), "scenes": [scene(voice="doc.mp3"), scene()]})
    assert script.title.voice is None
    assert script.scenes[0].voice == folder / "doc.mp3"
    assert script.scenes[1].voice is None


@pytest.mark.parametrize(("voice", "message"), [
    ("khong-co.mp3", "Cảnh 1: không tìm thấy file lời đọc khong-co.mp3"),
    (3, "Cảnh 1: \"voice\" phải là chuỗi"),
])
def test_bad_voice_is_named(folder, voice, message):
    with pytest.raises(InputError, match=message):
        load(folder, {"title": scene(), "scenes": [scene(voice=voice)]})


def test_video_resolves_relative_to_json_with_its_start(folder):
    (folder / "vuon.mp4").write_bytes(b"clip")
    script = load(folder, {"title": scene(image="", video="vuon.mp4", video_start=1.5), "scenes": [scene()]})
    assert script.title.video == folder / "vuon.mp4"
    assert script.title.video_start == 1.5
    assert script.title.image is None
    assert script.scenes[0].video is None


@pytest.mark.parametrize(("override", "message"), [
    ({"image": "a.jpg", "video": "vuon.mp4"}, "Cảnh 1: chỉ dùng một trong \"image\" hoặc \"video\""),
    ({"image": "", "video": "khong-co.mp4"}, "Cảnh 1: không tìm thấy file video khong-co.mp4"),
    ({"image": "", "video": 3}, "Cảnh 1: \"video\" phải là chuỗi"),
    ({"image": "", "video": "vuon.mp4", "video_start": -1}, "Cảnh 1: \"video_start\" phải là số giây từ 0"),
    ({"image": "", "video": "vuon.mp4", "video_start": True}, "Cảnh 1: \"video_start\" phải là số giây từ 0"),
])
def test_bad_video_is_named(folder, override, message):
    (folder / "vuon.mp4").write_bytes(b"clip")
    with pytest.raises(InputError, match=message):
        load(folder, {"title": scene(), "scenes": [scene(**override)]})
