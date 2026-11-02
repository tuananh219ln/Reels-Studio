"""A photo pasted as a link or dragged from another tab: downloaded by the api, only from the public internet."""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from conftest import login, make_user, make_video
from sqlalchemy import select

from reels_api import remote_images
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
    monkeypatch.setattr(remote_images, "is_public", lambda address: True)


def stored(db, scene_id):
    db.expire_all()
    return db.execute(select(Scene.image_key, Scene.image_source).where(Scene.id == scene_id)).one()


def test_a_pasted_link_stores_the_photo_and_keeps_the_link(an, db, me, storage, fakes, public_loopback):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    url = fakes.image_url("ca-com")
    saved = an.post(f"/api/scenes/{scene}/image-from-url", json={"url": f"  {url} "})
    assert saved.status_code == 200, saved.text
    key, source = stored(db, scene)
    assert source == url and storage.exists(key) and key.startswith(f"videos/{video.id}/")
    assert saved.json()["scenes"][0]["image_url"].startswith(f"/api/scenes/{scene}/image")


def test_a_link_into_this_machine_or_the_local_network_is_refused(an, db, me, storage, fakes):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    before = stored(db, scene)
    refused = an.post(f"/api/scenes/{scene}/image-from-url", json={"url": fakes.image_url("ca-com")})
    assert refused.status_code == 422 and "địa chỉ nội bộ" in refused.json()["message"]
    assert fakes.image_downloads == [] and stored(db, scene) == before


def test_a_redirect_into_this_machine_is_refused(an, db, me, storage, fakes, site, monkeypatch):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    # The site passes the check before connecting and on its connection; the redirect's connection does not.
    answers = iter([True, True])
    monkeypatch.setattr(remote_images, "is_public", lambda address: next(answers, False))
    refused = an.post(
        f"/api/scenes/{scene}/image-from-url", json={"url": f"{site}/redirect?to={fakes.image_url('ca-com')}"}
    )
    assert refused.status_code == 422 and "địa chỉ nội bộ" in refused.json()["message"]
    assert fakes.image_downloads == []


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("", "Hãy dán link ảnh"),
        ("file:///etc/passwd", "http:// hoặc https://"),
        ("ftp://example.com/a.jpg", "http:// hoặc https://"),
        ("data:image/png;base64,AAAA", "http:// hoặc https://"),
        ("https://user:pass@example.com/a.jpg", "tên đăng nhập"),
        ("https://example.com/" + "a" * 2001, "quá dài"),
    ],
)
def test_links_that_are_not_web_addresses_are_refused(an, db, me, storage, url, message):
    video = make_video(db, storage, me)
    refused = an.post(f"/api/scenes/{first_scene(db, video)}/image-from-url", json={"url": url})
    assert refused.status_code == 422 and message in refused.json()["message"]


def test_a_redirect_to_another_kind_of_address_is_refused(an, db, me, storage, site, public_loopback):
    video = make_video(db, storage, me)
    scene = first_scene(db, video)
    before = stored(db, scene)
    refused = an.post(f"/api/scenes/{scene}/image-from-url", json={"url": f"{site}/redirect?to=file:///etc/passwd"})
    assert refused.status_code == 422 and stored(db, scene) == before


def test_a_web_page_instead_of_a_photo_says_how_to_copy_the_photo_address(an, db, me, storage, site, public_loopback):
    video = make_video(db, storage, me)
    refused = an.post(f"/api/scenes/{first_scene(db, video)}/image-from-url", json={"url": f"{site}/page"})
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
    assert remote_images.is_public(address) is public


@pytest.mark.parametrize("url", ["http://127.0.0.1:9/a.jpg", "http://localhost/a.jpg", "http://[::1]/a.jpg"])
def test_a_local_address_is_refused_before_connecting(an, db, me, storage, url):
    video = make_video(db, storage, me)
    refused = an.post(f"/api/scenes/{first_scene(db, video)}/image-from-url", json={"url": url})
    assert refused.status_code == 422 and "địa chỉ nội bộ" in refused.json()["message"]
