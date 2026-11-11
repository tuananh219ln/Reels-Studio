"""Tags of the "Kho tư liệu" (media_tags.py, routes_media.py): kept lowercase without accents, joined with "-";
edited on one item or a chosen batch; filtered on (an item must carry every tag asked) with the folder, by the web and
by MCP; and the one-off seed of the Già Mà Khỏe photos by file name (docs/decisions/2026-11-11-media-tags.md)."""

import pytest
from conftest import login, make_user, photo_bytes
from sqlalchemy import select
from test_mcp import call, grant, mcp_client, payload  # noqa: F401  (mcp_client is a fixture)

from reels_api import media_tag_seed
from reels_api.media_tags import TagError, clean_tag, clean_tags
from reels_api.models import MediaItem


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def send_photo(client, name: str, folder: str = "", tags: str | None = None) -> dict:
    data = {"folder": folder} | ({"tags": tags} if tags is not None else {})
    made = client.post("/api/media", files={"file": (name, photo_bytes(), "image/jpeg")}, data=data)
    assert made.status_code == 201, made.text
    return made.json()


def names(client, **params) -> list[str]:
    return sorted(item["name"] for item in client.get("/api/media", params=params).json()["items"])


def test_a_tag_is_kept_lowercase_without_accents_joined_with_dashes():
    assert {clean_tag(raw) for raw in ("Xoay Cổ", " xoay-co ", "XOAY-CO", "xoay  _ cổ")} == {"xoay-co"}
    assert clean_tag("Đi bộ buổi tối") == "di-bo-buoi-toi"
    assert clean_tag("--Cổ vai gáy!--") == "co-vai-gay"
    assert clean_tags(["Xoay Cổ", "sofa", "xoay-co", "SOFA"]) == ["xoay-co", "sofa"]
    for empty in ("", "   ", "!!!"):
        with pytest.raises(TagError):
            clean_tag(empty)


def test_tags_are_set_on_one_item_and_shown_with_it(an, db):
    item = send_photo(an, "a.jpg", tags="Xoay Cổ, sofa")
    assert item["tags"] == ["xoay-co", "sofa"]
    edited = an.patch(f"/api/media/{item['id']}", json={"tags": ["Buổi tối", "xoay-co", "XOAY-CO"]})
    assert edited.status_code == 200, edited.text
    assert edited.json()["tags"] == ["buoi-toi", "xoay-co"]
    listed = an.get("/api/media").json()
    assert listed["items"][0]["tags"] == ["buoi-toi", "xoay-co"]
    assert listed["tags"] == [{"tag": "buoi-toi", "count": 1}, {"tag": "xoay-co", "count": 1}]
    assert an.patch(f"/api/media/{item['id']}", json={"tags": ["ok", "  "]}).status_code == 422
    assert an.patch(f"/api/media/{item['id']}", json={"tags": []}).json()["tags"] == []


def test_tags_are_added_to_and_taken_from_a_batch(an, db):
    items = [send_photo(an, f"{index}.jpg", tags="goi") for index in range(3)]
    ids = [item["id"] for item in items]
    added = an.post("/api/media/tags", json={"ids": ids[:2], "add": ["Phòng khách", "goi"]})
    assert added.status_code == 200, added.text
    assert added.json()["changed"] == 2
    assert names(an, tags="phong-khach") == ["0.jpg", "1.jpg"]
    removed = an.post("/api/media/tags", json={"ids": ids, "remove": ["GOI"]})
    assert removed.status_code == 200 and removed.json()["changed"] == 3
    db.expire_all()
    assert [db.get(MediaItem, item_id).tags for item_id in ids] == [["phong-khach"], ["phong-khach"], []]
    assert an.post("/api/media/tags", json={"ids": ids, "add": [], "remove": []}).status_code == 422
    assert an.post("/api/media/tags", json={"ids": [ids[0] + 999], "add": ["x"]}).status_code == 404


def test_filtering_asks_for_every_tag_and_meets_the_folder(an, db):
    send_photo(an, "co-sofa.jpg", "Già/Sofa", "xoay-co, sofa")
    send_photo(an, "co-giuong.jpg", "Già/Ngủ", "xoay-co, phong-ngu")
    send_photo(an, "vai-sofa.jpg", "Già/Sofa", "nhun-vai, sofa")
    assert names(an, tags="xoay-co,sofa") == ["co-sofa.jpg"]
    assert names(an, tags="xoay-co") == ["co-giuong.jpg", "co-sofa.jpg"]
    assert names(an, tags="Sofa", folder="Già/Sofa") == ["co-sofa.jpg", "vai-sofa.jpg"]
    assert names(an, tags="xoay-co", folder="Già/Ngủ") == ["co-giuong.jpg"]
    assert names(an, tags="xoay-co", folder="Già/Sofa", kind="clip") == []
    # The search matches tags as well as names, typed with accents and spaces or not.
    assert names(an, q="nhun") == ["vai-sofa.jpg"]
    assert names(an, q="phòng ngủ") == ["co-giuong.jpg"]


def test_the_assistant_filters_by_tags_and_reads_them(mcp_client, db, storage):  # noqa: F811
    user, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    for name, tags in (("a.jpg", ["xoay-co", "sofa"]), ("b.jpg", ["xoay-co"]), ("c.jpg", ["sofa", "ong"])):
        db.add(MediaItem(kind="photo", storage_key=f"media/{name}", name=name, tags=tags, created_by_id=user.id))
    db.commit()
    both = payload(call(mcp_client, token, "list_media", tags="xoay-co, Sofa"))
    assert [(row["name"], row["tags"]) for row in both["items"]] == [("a.jpg", ["xoay-co", "sofa"])]
    found = payload(call(mcp_client, token, "list_media", query="ong"))
    assert [row["name"] for row in found["items"]] == ["c.jpg"]


def test_the_seed_tags_the_gia_photos_by_name_once(db, me):
    for name in media_tag_seed.TAGS:
        db.add(MediaItem(kind="photo", storage_key=f"media/{name}", name=name, folder="Già", created_by_id=me.id))
    db.add(MediaItem(kind="photo", storage_key="media/x.webp", name="khac.webp", tags=["rieng"], created_by_id=me.id))
    first = db.scalar(select(MediaItem).where(MediaItem.name == "gia-goi-01-mo-dau.webp"))
    first.tags = ["da-co"]  # a tag a member gave it stays
    db.commit()
    log = media_tag_seed.apply(db)
    assert any("42" in line for line in log) and any("khac.webp" in line for line in log)
    again = media_tag_seed.apply(db)
    assert any("0 ảnh thêm thẻ" in line for line in again)
    db.expire_all()
    first = db.scalar(select(MediaItem).where(MediaItem.name == "gia-goi-01-mo-dau.webp"))
    assert first.tags == ["da-co", "ca-hai", "phong-khach", "ngoi-ghe", "mo-dau", "nam-tay"]
    assert db.scalar(select(MediaItem).where(MediaItem.name == "khac.webp")).tags == ["rieng"]
    for item in db.scalars(select(MediaItem).where(MediaItem.name.like("gia-%"))):
        assert len(item.tags) == len(set(item.tags))

    def tagged(tag: str) -> list[str]:
        return sorted(item.name for item in db.scalars(select(MediaItem)) if tag in item.tags)

    assert len(tagged("thang-bang")) == 4
    assert tagged("cta") == ["gia-goi-08-cta-nam-tay.webp", "gia-ngu-08-cta.webp"]
    assert len(tagged("xoa-bop")) == 2
    assert tagged("tu-the-sai") == ["gia-dibo-02-gu-lung.webp"]


def test_the_seed_reports_a_photo_it_cannot_find(db, me):
    db.add(MediaItem(kind="photo", storage_key="media/a.webp", name="gia-ngu-03-om-goi.webp", created_by_id=me.id))
    db.commit()
    log = media_tag_seed.apply(db, dry_run=True)
    assert any("gia-goi-01-mo-dau.webp" in line and "Không thấy" in line for line in log)
    db.expire_all()
    assert db.scalar(select(MediaItem)).tags == []  # a dry run changes nothing
