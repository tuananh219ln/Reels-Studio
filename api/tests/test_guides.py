"""In-app guides ("Hướng dẫn"): Markdown files shipped with the api, one or more per screen."""

from conftest import login, make_user


def test_guides_need_a_login(client):
    assert client.get("/api/guides").status_code == 401


def test_a_screens_guides_are_listed_with_their_titles(client, db):
    make_user(db)
    login(client)
    listed = client.get("/api/guides", params={"screen": "affiliate"}).json()
    assert [guide["slug"] for guide in listed] == ["affiliate", "custom-link"]
    found = next(guide for guide in listed if guide["slug"] == "custom-link")
    assert found["screen"] == "affiliate"
    assert found["title"].startswith("Hướng dẫn: gắn link affiliate hàng loạt")
    assert client.get("/api/guides", params={"screen": "knowledge"}).json() == []


def test_a_guide_is_read_by_its_slug_and_an_unknown_one_is_a_404(client, db):
    make_user(db)
    login(client)
    guide = client.get("/api/guides/custom-link").json()
    assert guide["slug"] == "custom-link"
    assert "Custom Link" in guide["body"]
    assert client.get("/api/guides/khong-co").status_code == 404
    assert client.get("/api/guides/..%2Fpyproject").status_code == 404
