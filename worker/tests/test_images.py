import pytest
from PIL import Image

from reels_render.errors import InputError
from reels_render.images import normalize_image

ORIENTATION = 0x0112


def test_exif_rotation_is_baked_into_pixels(tmp_path):
    source = tmp_path / "phone.jpg"
    exif = Image.Exif()
    exif[ORIENTATION] = 6  # rotate 90° clockwise to display
    stored = Image.new("RGB", (200, 100), (20, 20, 220))
    stored.paste((220, 20, 20), (0, 0, 100, 100))  # left half red
    stored.save(source, exif=exif)

    target = tmp_path / "upright.jpg"
    normalize_image(source, target, "Cảnh 1")

    with Image.open(target) as result:
        assert result.size == (100, 200)
        # Rotating clockwise moves the stored left half to the top.
        assert result.getpixel((50, 40))[0] > 150
        assert result.getpixel((50, 160))[2] > 150
        assert result.getexif().get(ORIENTATION) in (None, 1)


@pytest.mark.parametrize("content", [b"not an image", b"\xff\xd8\xff\xe0" + b"\x00" * 20])
def test_broken_image_names_scene_and_file(tmp_path, content):
    source = tmp_path / "hong.jpg"
    source.write_bytes(content)
    with pytest.raises(InputError, match="^Cảnh 2: ảnh hỏng") as err:
        normalize_image(source, tmp_path / "x.jpg", "Cảnh 2")
    assert str(source) in str(err.value)
