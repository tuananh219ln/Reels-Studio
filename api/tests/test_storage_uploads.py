import io

import pytest
from PIL import Image

from reels_api.storage import DirectoryStorage, StorageError
from reels_api.uploads import UploadRejected, image_extension


def image_bytes(kind: str, size=(40, 30)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (200, 100, 50)).save(buffer, kind)
    return buffer.getvalue()


def test_save_read_copy_and_delete(tmp_path):
    storage = DirectoryStorage(tmp_path / "store")
    storage.save_bytes("videos/1/a.jpg", b"one")
    source = tmp_path / "src.bin"
    source.write_bytes(b"two")
    storage.save_file("videos/1/b.mp4", source)

    assert storage.path("videos/1/a.jpg").read_bytes() == b"one"
    assert storage.copy_to("videos/1/b.mp4", tmp_path / "out.mp4").read_bytes() == b"two"
    storage.save_bytes("videos/1/a.jpg", b"replaced")
    assert storage.path("videos/1/a.jpg").read_bytes() == b"replaced"
    assert [p.name for p in (tmp_path / "store/videos/1").iterdir() if p.name.startswith(".")] == []

    storage.delete("videos/1/a.jpg")
    storage.delete(None)
    assert not storage.exists("videos/1/a.jpg") and storage.exists("videos/1/b.mp4")
    storage.delete_prefix("videos/1")
    assert not (tmp_path / "store/videos/1").exists()


@pytest.mark.parametrize("key", ["../etc/passwd", "/abs.jpg", "videos/../x", "Videos/A.jpg", "a\\b", ""])
def test_keys_that_could_escape_the_root_are_refused(tmp_path, key):
    with pytest.raises(StorageError):
        DirectoryStorage(tmp_path).path(key)


@pytest.mark.parametrize(("kind", "extension"), [("JPEG", "jpg"), ("PNG", "png"), ("WEBP", "webp")])
def test_photo_types_are_read_from_the_bytes(kind, extension):
    assert image_extension(image_bytes(kind)) == extension


def test_a_24_mp_camera_photo_passes_and_a_small_file_with_more_pixels_is_refused():
    assert image_extension(image_bytes("PNG", size=(6000, 4000))) == "png"
    # A one-colour PNG is a few kB but would decode to hundreds of MB.
    with pytest.raises(UploadRejected, match="Ảnh quá lớn: tối đa 24 megapixel"):
        image_extension(image_bytes("PNG", size=(6000, 4001)))


@pytest.mark.parametrize("data", [image_bytes("GIF"), image_bytes("BMP"), b"not an image", image_bytes("JPEG")[:200]])
def test_other_or_broken_files_are_refused(data):
    with pytest.raises(UploadRejected, match="JPG, PNG hoặc WebP"):
        image_extension(data)
