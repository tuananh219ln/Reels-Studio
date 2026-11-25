"""Kho kiến thức "Tài liệu": a group's Markdown documents, edited by the group's editors, read by anyone and by
assistants through MCP (`list_docs`, `get_doc`). The copy in the app is the master."""

import pytest
from conftest import client_for, login, make_user
from test_mcp import call, grant, mcp_client, payload, rpc  # noqa: F401  (mcp_client is a fixture)

from reels_api.models import KnowledgeTopic, TopicDoc


@pytest.fixture
def an_user(db):
    return make_user(db)


@pytest.fixture
def an(client, an_user):
    login(client)
    return client


@pytest.fixture
def binh(app, db):
    make_user(db, email="binh@doi.vn", name="Trần Bình")
    client = client_for(app)
    login(client, email="binh@doi.vn")
    return client


@pytest.fixture
def group(db, an_user):
    topic = KnowledgeTopic(name="FoodDose TEST", created_by_id=an_user.id)
    db.add(topic)
    db.commit()
    return topic


def add(client, group, name="mau-chung.md", section="template", body="# Mẫu chung\n\nKhung 0: lưới collage", **more):
    return client.post(
        f"/api/topic-docs?topic_id={group.id}", json={"section": section, "name": name, "body": body, **more}
    )


def test_a_document_is_added_read_edited_and_deleted(an, db, group):
    made = add(an, group)
    assert made.status_code == 201, made.text
    doc = made.json()
    assert (doc["name"], doc["section_label"], doc["title"], doc["updated_by"]) == (
        "mau-chung.md",
        "Mẫu",
        "Mẫu chung",
        "Nguyễn Văn An",
    )
    assert an.get(f"/api/topic-docs/{doc['id']}").json()["body"].startswith("# Mẫu chung")
    # The list holds no text, only what the tab shows.
    [row] = an.get(f"/api/topic-docs?topic_id={group.id}").json()["docs"]
    assert "body" not in row and row["size"] == len(doc["body"])

    changed = an.patch(f"/api/topic-docs/{doc['id']}", json={"body": "# Mẫu chung v2", "pinned": True}).json()
    assert (changed["title"], changed["pinned"]) == ("Mẫu chung v2", True)
    assert an.delete(f"/api/topic-docs/{doc['id']}").status_code == 200
    assert an.get(f"/api/topic-docs/{doc['id']}").status_code == 404


def test_names_are_files_and_unique_in_the_group(an, group):
    assert add(an, group, name="van-hanh").json()["name"] == "van-hanh.md"
    assert add(an, group, name="van-hanh.md").status_code == 409
    assert add(an, group, name="a/b.md").status_code == 422
    assert add(an, group, section="khac").status_code == 422
    assert add(an, group, body="x" * 200_001).status_code == 422


def test_the_list_puts_pinned_first_then_sections_and_searches_without_accents(an, group):
    add(an, group, name="bao-cao.md", section="report", body="# Báo cáo tuần")
    add(an, group, name="mau-chung.md", section="template", body="# Mẫu\nThứ tự dấu")
    add(an, group, name="job-14h.md", section="job", body="# Job dựng", pinned=True)
    add(an, group, name="lich.md", section="plan", body="# Lịch 7 ngày")
    names = [d["name"] for d in an.get(f"/api/topic-docs?topic_id={group.id}").json()["docs"]]
    assert names == ["job-14h.md", "mau-chung.md", "lich.md", "bao-cao.md"]
    found = an.get(f"/api/topic-docs?topic_id={group.id}&q=thu tu dau").json()["docs"]
    assert [d["name"] for d in found] == ["mau-chung.md"]
    only = an.get(f"/api/topic-docs?topic_id={group.id}&section=report").json()["docs"]
    assert [d["name"] for d in only] == ["bao-cao.md"]


def test_editing_follows_the_groups_team_edit_but_reading_stays_open(an, binh, db, group):
    doc = add(an, group).json()
    assert binh.patch(f"/api/topic-docs/{doc['id']}", json={"body": "Bình sửa"}).status_code == 200
    group.team_edit = False
    db.commit()
    for response in (
        binh.patch(f"/api/topic-docs/{doc['id']}", json={"body": "Lại sửa"}),
        binh.delete(f"/api/topic-docs/{doc['id']}"),
        add(binh, group, name="khac.md"),
    ):
        assert response.status_code == 403 and response.json()["code"] == "group_locked"
    assert binh.get(f"/api/topic-docs/{doc['id']}").json()["body"] == "Bình sửa"
    assert add(an, group, name="cua-an.md").status_code == 201


def test_a_deleted_group_takes_its_documents(an, db, group):
    add(an, group)
    db.delete(group)
    db.commit()
    assert db.query(TopicDoc).count() == 0


def test_mcp_lists_and_reads_the_groups_documents(mcp_client, db):  # noqa: F811
    me, _, tokens, _ = grant(mcp_client, db)
    topic = KnowledgeTopic(name="FoodDose TEST", created_by_id=me.id)
    db.add(topic)
    db.flush()
    db.add_all(
        [
            TopicDoc(knowledge_topic_id=topic.id, section="template", name="mau-chung.md", body="# Mẫu chung\nKhung 0"),
            TopicDoc(knowledge_topic_id=topic.id, section="job", name="job.md", body="# Job", pinned=True),
        ]
    )
    db.commit()
    token = tokens["access_token"]

    listed = payload(call(mcp_client, token, "list_docs", knowledge_topic_id=topic.id))["docs"]
    assert [(d["name"], d["section"], d["pinned"]) for d in listed] == [
        ("job.md", "job", True),
        ("mau-chung.md", "template", False),
    ]
    assert "body" not in listed[0] and listed[0]["updated_at"]
    only = payload(call(mcp_client, token, "list_docs", knowledge_topic_id=topic.id, section="template"))["docs"]
    assert [d["name"] for d in only] == ["mau-chung.md"]
    by_name = payload(call(mcp_client, token, "get_doc", knowledge_topic_id=topic.id, file_name="mau-chung"))
    by_id = payload(call(mcp_client, token, "get_doc", knowledge_topic_id=topic.id, doc_id=listed[0]["id"]))
    assert by_name["body"] == "# Mẫu chung\nKhung 0" and by_id["name"] == "job.md"
    assert call(mcp_client, token, "get_doc", knowledge_topic_id=topic.id, file_name="khong-co")["isError"]
    assert call(mcp_client, token, "list_docs", knowledge_topic_id=999999)["isError"]

    tools = {t["name"]: t for t in rpc(mcp_client, token, "tools/list").json()["result"]["tools"]}
    assert all(tools[name]["annotations"]["readOnlyHint"] is True for name in ("list_docs", "get_doc"))
