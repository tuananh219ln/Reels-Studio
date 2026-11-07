"""A photo or clip pasted as a link or dragged from another tab: downloaded by the api, only from the public internet."""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from conftest import clip_bytes, login, make_user, make_video, needs_ffmpeg, photo_bytes
from sqlalchemy import select

from reels_api import remote_media
from reels_api.models import Scene


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def first_scene(db, video) -> int:
    return db.scalar(
        select(Scene.id).where(Scene.video_id == video.id, Scene.is_title.is_(False)).order_by(Scene.position).limit(1)
    )


@pytest.fixture
def site():
    """A web page host on this machine: /redirect?to=<url> redirects, /page answers HTML."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/redirect?to="):
                self.send_response(302)
                self.send_header("Location", self.path.removeprefix("/redirect?to="))
                self.end_headers()
                return
            body = b"<html><body>not a photo</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture
def public_loopback(monkeypatch):
    """The test servers listen on 127.0.0.1; treat it as public so the download itself can be tested."""
    monkeypatch.setattr(remote_media, "is_public", lambda address: True)


def stored(db, scene_id):
    db.expire_all()
    return db.execute(select(Scene.image_key, Scene.image_source).where(Scene.id == scene_id)).one()


def stored_clip(db, scene_id):
    db.expire_all()
    return db.execute(select(Scene.video_key, Scene.video_seconds, Scene.image_key).where(Scene.id == scene_id)).one()


def test_a_pasted_link_stores_the_photo_and_keeps_the_link(an, db, me, storage, fakes, public_loopback):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    url = fakes.image_url("ca-com")
    saved = an.post(f"/api/scenes/{scene}/media-from-url", json={"url": f"  {url} "})
    assert saved.status_code == 200, saved.text
    key, source = stored(db, scene)
    assert source == url and storage.exists(key) and key.startswith(f"videos/{video.id}/")
    assert saved.json()["scenes"][0]["image_url"].startswith(f"/api/scenes/{scene}/image")


def test_a_link_into_this_machine_or_the_local_network_is_refused(an, db, me, storage, fakes):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    before = stored(db, scene)
    refused = an.post(f"/api/scenes/{scene}/media-from-url", json={"url": fakes.image_url("ca-com")})
    assert refused.status_code == 422 and "địa chỉ nội bộ" in refused.json()["message"]
    assert fakes.image_downloads == [] and stored(db, scene) == before


def test_a_redirect_into_this_machine_is_refused(an, db, me, storage, fakes, site, monkeypatch):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    # The site passes the check before connecting and on its connection; the redirect's connection does not.
    answers = iter([True, True])
    monkeypatch.setattr(remote_media, "is_public", lambda address: next(answers, False))
    refused = an.post(
        f"/api/scenes/{scene}/media-from-url", json={"url": f"{site}/redirect?to={fakes.image_url('ca-com')}"}
    )
    assert refused.status_code == 422 and "địa chỉ nội bộ" in refused.json()["message"]
    assert fakes.image_downloads == []


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("", "Hãy dán link ảnh hoặc video"),
        ("file:///etc/passwd", "http:// hoặc https://"),
        ("ftp://example.com/a.jpg", "http:// hoặc https://"),
        ("data:image/png;base64,AAAA", "http:// hoặc https://"),
        ("https://user:pass@example.com/a.jpg", "tên đăng nhập"),
        ("https://example.com/" + "a" * 2001, "quá dài"),
    ],
)
def test_links_that_are_not_web_addresses_are_refused(an, db, me, storage, url, message):
    video = make_video(db, storage, me)
    refused = an.post(f"/api/scenes/{first_scene(db, video)}/media-from-url", json={"url": url})
    assert refused.status_code == 422 and message in refused.json()["message"]


def test_a_redirect_to_another_kind_of_address_is_refused(an, db, me, storage, site, public_loopback):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    before = stored(db, scene)
    refused = an.post(f"/api/scenes/{scene}/media-from-url", json={"url": f"{site}/redirect?to=file:///etc/passwd"})
    assert refused.status_code == 422 and stored(db, scene) == before


def test_a_web_page_instead_of_a_photo_says_how_to_copy_the_photo_address(an, db, me, storage, site, public_loopback):
    video = make_video(db, storage, me)
    refused = an.post(f"/api/scenes/{first_scene(db, video)}/media-from-url", json={"url": f"{site}/page"})
    assert refused.status_code == 422 and "Sao chép địa chỉ hình ảnh" in refused.json()["message"]


@pytest.mark.parametrize(
    ("address", "public"),
    [
        ("8.8.8.8", True),
        ("2606:4700:4700::1111", True),
        ("127.0.0.1", False),
        ("10.0.0.5", False),
        ("192.168.1.1", False),
        ("172.16.0.1", False),
        ("169.254.169.254", False),
        ("100.64.0.1", False),
        ("0.0.0.0", False),
        ("::1", False),
        ("fe80::1%en0", False),
        ("fd00::1", False),
        ("::ffff:127.0.0.1", False),
        ("224.0.0.1", False),
        ("not-an-address", False),
    ],
)
def test_only_public_internet_addresses_count_as_public(address, public):
    assert remote_media.is_public(address) is public


@pytest.mark.parametrize("url", ["http://127.0.0.1:9/a.jpg", "http://localhost/a.jpg", "http://[::1]/a.jpg"])
def test_a_local_address_is_refused_before_connecting(an, db, me, storage, url):
    video = make_video(db, storage, me)
    refused = an.post(f"/api/scenes/{first_scene(db, video)}/media-from-url", json={"url": url})
    assert refused.status_code == 422 and "địa chỉ nội bộ" in refused.json()["message"]


@needs_ffmpeg
def test_a_pasted_video_link_stores_the_clip_in_place_of_the_photo(an, db, me, storage, fakes, public_loopback):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    saved = an.post(f"/api/scenes/{scene}/media-from-url", json={"url": f"{fakes.url}/clips/bep.mp4"})
    assert saved.status_code == 200, saved.text
    key, seconds, image_key = stored_clip(db, scene)
    assert storage.exists(key) and key.endswith(".mp4") and seconds == pytest.approx(3, abs=0.1)
    assert image_key is None and fakes.clip_downloads == ["bep.mp4"]


@needs_ffmpeg
def test_a_tiktok_link_is_fetched_through_yt_dlp_and_cut_to_its_first_minute(
    an, db, me, storage, monkeypatch, tmp_path
):
    long_clip = clip_bytes(tmp_path, seconds=62, size="720x1280", rate=5)
    asked = []

    def fake_download(url, folder):
        asked.append(url)
        path = folder / "tiktok.mp4"
        path.write_bytes(long_clip)
        return path

    monkeypatch.setattr(remote_media, "download_tiktok", fake_download)
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    url = "https://www.tiktok.com/@bep.nha.minh/video/7300000000000000000"
    saved = an.post(f"/api/scenes/{scene}/media-from-url", json={"url": url})
    assert saved.status_code == 200, saved.text
    key, seconds, _ = stored_clip(db, scene)
    assert asked == [url] and storage.exists(key)
    assert 58 <= seconds <= 60


def test_only_tiktok_hosts_go_to_yt_dlp():
    assert remote_media.is_tiktok("www.tiktok.com") and remote_media.is_tiktok("vt.tiktok.com.")
    assert remote_media.is_tiktok("TIKTOK.COM")
    assert not remote_media.is_tiktok("tiktok.com.evil.example") and not remote_media.is_tiktok("nottiktok.com")


class FakeYoutubeDL:
    """yt-dlp's downloader without the network: `answer` is what reading the link gives."""

    answer: dict = {}
    downloaded: list[dict] = []

    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download, process):
        assert download is False and process is False
        return self.answer

    def process_ie_result(self, info, download):
        FakeYoutubeDL.downloaded.append(info)


@pytest.mark.parametrize(
    ("url", "answer", "message"),
    [
        ("https://www.tiktok.com/@bep/photo/7300000000000000000", {}, "bài ảnh TikTok"),
        ("https://www.tiktok.com/@bep", {"_type": "playlist", "entries": []}, "một video TikTok"),
        ("https://www.tiktok.com/@bep/video/1", {"id": "1"}, "quá 50 MB"),
    ],
)
def test_tiktok_links_that_are_not_one_video_or_too_big_are_refused(
    an, db, me, storage, monkeypatch, url, answer, message
):
    monkeypatch.setattr(remote_media.yt_dlp, "YoutubeDL", FakeYoutubeDL)
    monkeypatch.setattr(FakeYoutubeDL, "answer", answer)
    monkeypatch.setattr(FakeYoutubeDL, "downloaded", [])
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    refused = an.post(f"/api/scenes/{scene}/media-from-url", json={"url": url})
    assert refused.status_code == 422 and message in refused.json()["message"]
    assert stored_clip(db, scene)[0] is None
    # Only a single video's page is downloaded (and yt-dlp skips a file over the limit, leaving none).
    assert FakeYoutubeDL.downloaded == ([answer] if "video" in url else [])


@pytest.mark.parametrize(
    ("url", "site"),
    [
        ("https://image.shutterstock.com/image-photo/rau-260nw-1.jpg", "Shutterstock"),
        ("https://www.shutterstock.vn/image-photo/1", "Shutterstock"),
        ("https://media.gettyimages.com/id/1/photo.jpg", "Getty Images"),
        ("https://www.gettyimages.co.uk/detail/1", "Getty Images"),
        ("https://t4.ftcdn.net/jpg/01/02/03/360_F_1.jpg", "Adobe Stock"),
        ("https://product.hstatic.net/200000423303/product/can-tay.jpg", None),
        ("https://notshutterstock.com/x.jpg", None),
        ("https://shutterstock.example.com/x.jpg", None),
        ("https://alamy.com.evil.net/x.jpg", None),
    ],
)
def test_stock_photo_sites_are_recognised_by_their_hosts(url, site):
    from reels_api.stock_sites import stock_site

    assert stock_site(url) == site


def test_a_photo_picked_from_google_is_marked_to_check_and_never_from_a_stock_site(an, db, me, storage, monkeypatch):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    fetched = []

    def download(url, folder):
        fetched.append(url)
        return remote_media.Media(photo=(photo_bytes(), "jpg"))

    monkeypatch.setattr(remote_media, "download", download)

    stock = an.post(
        f"/api/scenes/{scene}/media-from-url", json={"url": "https://image.shutterstock.com/rau.jpg", "auto": True}
    )
    assert stock.status_code == 422 and stock.json()["code"] == "stock_photo" and fetched == []

    picked = an.post(
        f"/api/scenes/{scene}/media-from-url", json={"url": "https://product.hstatic.net/can-tay.jpg", "auto": True}
    )
    assert picked.status_code == 200, picked.text
    shown = next(item for item in picked.json()["scenes"] if item["id"] == scene)
    assert shown["image_auto"] is True
    assert stored(db, scene)[1] == "https://product.hstatic.net/can-tay.jpg"

    # The same link pasted by a member is the member's choice.
    pasted = an.post(f"/api/scenes/{scene}/media-from-url", json={"url": "https://product.hstatic.net/can-tay.jpg"})
    assert next(item for item in pasted.json()["scenes"] if item["id"] == scene)["image_auto"] is False


def test_a_clip_is_not_an_automatic_photo_pick(an, db, me, storage, monkeypatch, tmp_path):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")
    monkeypatch.setattr(remote_media, "download", lambda url, folder: remote_media.Media(clip=clip))
    refused = an.post(f"/api/scenes/{scene}/media-from-url", json={"url": "https://example.com/a.mp4", "auto": True})
    assert refused.status_code == 422 and refused.json()["code"] == "not_a_photo"
