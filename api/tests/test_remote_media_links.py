"""Links to Google Drive files and why a link failed (remote_media.py): no network, no database."""

import pytest

from reels_api import remote_media
from reels_api.remote_media import RemoteMediaError, normalize_link

ID = "1AbCdEfGhIjKlMnOpQrStUvWxYz_-0123"
DIRECT = f"https://drive.usercontent.google.com/download?id={ID}&export=download"


@pytest.mark.parametrize(
    "link",
    [
        f"https://drive.google.com/file/d/{ID}/view",
        f"https://drive.google.com/file/d/{ID}/view?usp=sharing",
        f"https://drive.google.com/file/u/0/d/{ID}/view?usp=drive_link",
        f"https://drive.google.com/open?id={ID}",
        f"https://drive.google.com/uc?id={ID}",
        f"https://drive.google.com/uc?export=download&id={ID}",
    ],
)
def test_a_drive_link_becomes_the_direct_download(link):
    assert normalize_link(link) == DIRECT


def test_a_drive_links_resource_key_is_kept():
    link = f"https://drive.google.com/file/d/{ID}/view?usp=sharing&resourcekey=0-abc_DEF"
    assert normalize_link(link) == DIRECT + "&resourcekey=0-abc_DEF"


@pytest.mark.parametrize(
    "link",
    [
        "https://example.com/anh.jpg",
        "https://cdn.example.com/file/d/abc/view",
        "https://drive.google.com/file/d/ngan/view",  # not an id
        "https://drive.google.com/file/d/<script>/view",
        "https://drive.google.com/",
        "https://tiktok.com/@a/video/1",
    ],
)
def test_other_links_are_left_alone(link):
    assert normalize_link(link) == link


@pytest.mark.parametrize(
    "link",
    [
        f"https://drive.google.com/drive/folders/{ID}",
        f"https://drive.google.com/drive/u/0/folders/{ID}?usp=sharing",
        f"https://docs.google.com/document/d/{ID}/edit",
        f"https://docs.google.com/spreadsheets/d/{ID}/edit",
        f"https://docs.google.com/presentation/d/{ID}/edit",
    ],
)
def test_a_folder_or_a_google_document_is_refused_with_its_own_message(link):
    with pytest.raises(RemoteMediaError) as refused:
        normalize_link(link)
    assert "từng file" in str(refused.value) and refused.value.reason == "not_media"


def fetching(monkeypatch, body: bytes):
    """download() with no network: `_fetch` writes `body` and remembers the address it was asked for."""
    asked = []

    def fake_fetch(url, target, *args, **kwargs):
        asked.append(url)
        target.write_bytes(body)

    monkeypatch.setattr(remote_media, "_fetch", fake_fetch)
    monkeypatch.setattr(remote_media, "_check_host", lambda parts: None)
    return asked


def test_download_asks_for_the_direct_address_of_a_drive_link(monkeypatch, tmp_path):
    from conftest import photo_bytes

    asked = fetching(monkeypatch, photo_bytes())
    media = remote_media.download(f"https://drive.google.com/file/d/{ID}/view?usp=sharing", tmp_path)
    assert asked == [DIRECT] and media.photo is not None


def test_a_drive_page_instead_of_a_file_says_the_link_is_not_public(monkeypatch, tmp_path):
    fetching(monkeypatch, b"<!DOCTYPE html><html>Sign in</html>")
    with pytest.raises(RemoteMediaError) as failed:
        remote_media.download(f"https://drive.google.com/file/d/{ID}/view", tmp_path)
    assert failed.value.reason == "not_public" and "Drive" in str(failed.value)


def test_any_other_page_instead_of_a_file_is_not_media(monkeypatch, tmp_path):
    fetching(monkeypatch, b"<!DOCTYPE html><html>hello</html>")
    with pytest.raises(RemoteMediaError) as failed:
        remote_media.download("https://example.com/trang", tmp_path)
    assert failed.value.reason == "not_media"


@pytest.mark.parametrize(
    ("status", "reason"),
    [(401, "not_public"), (403, "not_public"), (404, "expired_or_unreachable"), (410, "expired_or_unreachable")],
)
def test_a_refusing_host_is_told_apart_from_a_missing_file(monkeypatch, tmp_path, status, reason):
    import urllib.error

    monkeypatch.setattr(remote_media, "_check_host", lambda parts: None)
    # The real _fetch turns the HTTPError into RemoteMediaError, so only the opener is stubbed.

    class Opener:
        def open(self, request, timeout=None):
            raise urllib.error.HTTPError(request.full_url, status, "no", {}, None)

    monkeypatch.setattr(remote_media, "_opener", lambda: Opener())
    with pytest.raises(RemoteMediaError) as failed:
        remote_media.download("https://example.com/a.jpg", tmp_path)
    assert failed.value.reason == reason


def test_an_oversized_photo_is_too_large(monkeypatch, tmp_path):
    fetching(monkeypatch, b"\xff\xd8\xff" + b"0" * (remote_media.MAX_IMAGE_BYTES + 1))
    with pytest.raises(RemoteMediaError) as failed:
        remote_media.download("https://example.com/a.jpg", tmp_path)
    assert failed.value.reason == "too_large"


def test_a_private_address_is_blocked_host(tmp_path):
    with pytest.raises(RemoteMediaError) as failed:
        remote_media.download("http://127.0.0.1/a.jpg", tmp_path)
    assert failed.value.reason == "blocked_host"


def test_an_error_without_a_reason_is_unreachable():
    assert RemoteMediaError("x").reason == "expired_or_unreachable"
