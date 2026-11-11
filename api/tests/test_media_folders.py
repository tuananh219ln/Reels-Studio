"""Folders of the "Kho tư liệu" (routes_media.py) and the topic group's linked folder ("Tư liệu" on /knowledge):
moving items keeps their id and file, renaming and clearing a folder touch only labels, and a folder is linked by at
most one group (docs/decisions/2026-11-11-media-folders.md)."""

import pytest
from conftest import first_topic, login, make_user, photo_bytes
from sqlalchemy import func, select

from reels_api.models import KnowledgeTopic, MediaItem


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def send_photo(client, name: str, folder: str = "") -> dict:
    made = client.post(
        "/api/media", files={"file": (name, photo_bytes(), "image/jpeg")}, data={"folder": folder}
    )  # fmt: skip
    assert made.status_code == 201, made.text
    return made.json()


def counts(client) -> dict[str, int]:
    return {row["folder"]: row["count"] for row in client.get("/api/media").json()["folders"]}


def second_topic(client, name: str = "Già Mà Khỏe") -> dict:
    made = client.post("/api/knowledge/topics", json={"name": name})
    assert made.status_code == 201, made.text
    return next(topic for topic in made.json()["topics"] if topic["name"] == name)


def test_moving_one_item_keeps_its_id_and_file(an, db, storage):
    item = send_photo(an, "goi.jpg", "Gia - Goi khop")
    key = db.get(MediaItem, item["id"]).storage_key
    moved = an.post("/api/media/move", json={"ids": [item["id"]], "folder": "Gia - Giac ngu"})
    assert moved.status_code == 200, moved.text
    assert moved.json()["moved"] == 1
    db.expire_all()
    row = db.get(MediaItem, item["id"])
    assert row.folder == "Gia - Giac ngu" and row.storage_key == key and storage.exists(key)
    assert counts(an) == {"Gia - Giac ngu": 1}
    listed = an.get("/api/media", params={"folder": "Gia - Giac ngu"}).json()["items"]
    assert [entry["id"] for entry in listed] == [item["id"]]


def test_moving_a_batch_and_back_to_no_folder(an, db):
    items = [send_photo(an, f"{index}.jpg", "Cũ") for index in range(3)]
    ids = [item["id"] for item in items]
    moved = an.post("/api/media/move", json={"ids": ids[:2], "folder": "  Mới / con  "})
    assert moved.status_code == 200 and moved.json()["moved"] == 2
    assert counts(an) == {"Cũ": 1, "Mới/con": 2}
    assert {row["folder"]: row["count"] for row in moved.json()["folders"]} == {"Cũ": 1, "Mới/con": 2}
    assert an.post("/api/media/move", json={"ids": [ids[2]], "folder": ""}).json()["moved"] == 1
    assert counts(an) == {"Mới/con": 2}
    assert db.scalar(select(func.count()).select_from(MediaItem)) == 3
    assert sorted(db.scalars(select(MediaItem.id))) == sorted(ids)


def test_a_batch_with_a_missing_item_moves_nothing(an, db):
    item = send_photo(an, "a.jpg", "Cũ")
    refused = an.post("/api/media/move", json={"ids": [item["id"], item["id"] + 999], "folder": "Mới"})
    assert refused.status_code == 404
    assert counts(an) == {"Cũ": 1}
    assert an.post("/api/media/move", json={"ids": [], "folder": "Mới"}).status_code == 422


def test_renaming_a_folder_relabels_its_items_and_subfolders_and_the_linked_group(an, db):
    keep = send_photo(an, "khac.jpg", "Khác")
    inside = [send_photo(an, "a.jpg", "Gia"), send_photo(an, "b.jpg", "Gia/Goi khop")]
    topic = first_topic(db)
    group = second_topic(an)
    assert an.patch(f"/api/knowledge/topics/{topic.id}", json={"media_folder": "Gia"}).status_code == 200
    assert an.patch(f"/api/knowledge/topics/{group['id']}", json={"media_folder": "Gia/Goi khop"}).status_code == 200
    renamed = an.post("/api/media/folders/rename", json={"folder": "Gia", "to": "Già Mà Khỏe"})
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["moved"] == 2
    assert counts(an) == {"Khác": 1, "Già Mà Khỏe": 1, "Già Mà Khỏe/Goi khop": 1}
    db.expire_all()
    assert [db.get(MediaItem, item["id"]).folder for item in inside] == ["Già Mà Khỏe", "Già Mà Khỏe/Goi khop"]
    assert db.get(MediaItem, keep["id"]).folder == "Khác"
    assert db.get(KnowledgeTopic, topic.id).media_folder == "Già Mà Khỏe"
    assert db.get(KnowledgeTopic, group["id"]).media_folder == "Già Mà Khỏe/Goi khop"


def test_renaming_into_an_existing_folder_merges_them(an, db):
    send_photo(an, "a.jpg", "Gia - Goi khop")
    send_photo(an, "b.jpg", "Gia goi khop")
    renamed = an.post("/api/media/folders/rename", json={"folder": "Gia goi khop", "to": "Gia - Goi khop"})
    assert renamed.status_code == 200 and renamed.json()["moved"] == 1
    assert counts(an) == {"Gia - Goi khop": 2}


def test_renaming_is_refused_when_two_groups_would_share_a_folder(an, db):
    send_photo(an, "a.jpg", "Một")
    send_photo(an, "b.jpg", "Hai")
    topic = first_topic(db)
    group = second_topic(an)
    an.patch(f"/api/knowledge/topics/{topic.id}", json={"media_folder": "Một"})
    an.patch(f"/api/knowledge/topics/{group['id']}", json={"media_folder": "Hai"})
    refused = an.post("/api/media/folders/rename", json={"folder": "Một", "to": "Hai"})
    assert refused.status_code == 409 and "Già Mà Khỏe" in refused.json()["message"]
    assert counts(an) == {"Một": 1, "Hai": 1}
    assert an.post("/api/media/folders/rename", json={"folder": "Một", "to": " / "}).status_code == 422
    assert an.post("/api/media/folders/rename", json={"folder": "Không có", "to": "X"}).status_code == 404


def test_clearing_a_folder_keeps_every_item_and_unlinks_the_group(an, db, storage):
    items = [send_photo(an, "a.jpg", "Gia"), send_photo(an, "b.jpg", "Gia/con"), send_photo(an, "c.jpg", "Khác")]
    topic = first_topic(db)
    an.patch(f"/api/knowledge/topics/{topic.id}", json={"media_folder": "Gia"})
    cleared = an.post("/api/media/folders/clear", json={"folder": "Gia"})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["cleared"] == 2
    assert counts(an) == {"Khác": 1}
    db.expire_all()
    assert [db.get(MediaItem, item["id"]).folder for item in items] == ["", "", "Khác"]
    assert all(storage.exists(db.get(MediaItem, item["id"]).storage_key) for item in items)
    assert db.get(KnowledgeTopic, topic.id).media_folder is None


def test_a_group_links_one_folder_and_a_folder_belongs_to_one_group(an, db):
    topic = first_topic(db)
    group = second_topic(an)
    linked = an.patch(f"/api/knowledge/topics/{topic.id}", json={"media_folder": " Gia - Goi khop "})
    assert linked.status_code == 200, linked.text
    shown = next(row for row in linked.json()["topics"] if row["id"] == topic.id)
    assert shown["media_folder"] == "Gia - Goi khop"
    # A folder with nothing in it yet is listed for the dropdowns, with its group.
    folders = an.get("/api/media").json()["folders"]
    assert folders == [{"folder": "Gia - Goi khop", "count": 0, "topic_id": topic.id, "topic": topic.name}]
    taken = an.patch(f"/api/knowledge/topics/{group['id']}", json={"media_folder": "Gia - Goi khop"})
    assert taken.status_code == 409 and topic.name in taken.json()["message"]
    # Uploading from the group's "Tư liệu" goes into its folder, and its view shows only that folder.
    mine = send_photo(an, "goi.jpg", "Gia - Goi khop")
    send_photo(an, "khac.jpg", "Khác")
    listed = an.get("/api/media", params={"folder": shown["media_folder"]}).json()["items"]
    assert [item["id"] for item in listed] == [mine["id"]]
    unlinked = an.patch(f"/api/knowledge/topics/{topic.id}", json={"media_folder": None})
    assert next(row for row in unlinked.json()["topics"] if row["id"] == topic.id)["media_folder"] is None
    assert an.patch(f"/api/knowledge/topics/{group['id']}", json={"media_folder": "Gia - Goi khop"}).status_code == 200
    assert an.patch(f"/api/knowledge/topics/{group['id']}", json={"media_folder": ""}).status_code == 200
    db.expire_all()
    assert db.get(KnowledgeTopic, group["id"]).media_folder is None


def test_linking_a_folder_is_an_edit_of_the_group(an, db):
    topic = first_topic(db)
    topic.team_edit, topic.created_by_id = False, make_user(db, "binh@doi.vn", "Bình").id
    db.commit()
    refused = an.patch(f"/api/knowledge/topics/{topic.id}", json={"media_folder": "Gia"})
    assert refused.status_code == 403
