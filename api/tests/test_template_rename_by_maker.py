"""Part 5 (2026-11-09): a saved template is renamed by its maker only, and its maker sees how many members and groups
use it before deleting it. Text box styles stay as they are."""

import pytest
from conftest import client_for, first_topic, login, make_user

from reels_api.models import EditTemplate, User


@pytest.fixture
def an_user(db):
    return make_user(db)


@pytest.fixture
def binh_user(db):
    return make_user(db, email="binh@doi.vn", name="Trần Bình")


@pytest.fixture
def an(client, an_user):
    login(client)
    return client


@pytest.fixture
def binh(app, binh_user):
    client = client_for(app)
    login(client, email="binh@doi.vn")
    return client


@pytest.fixture
def template(db, an_user):
    row = EditTemplate(name="Vườn nhà", data={"transitions": ["flash"]}, created_by_id=an_user.id)
    db.add(row)
    db.commit()
    return row


def item(client, template_id):
    return next(row for row in client.get("/api/edit-templates").json()["templates"] if row["id"] == template_id)


def test_only_the_maker_renames_a_template(an, binh, template):
    refused = binh.patch(f"/api/edit-templates/{template.id}", json={"name": "Của Bình"})
    assert refused.status_code == 403
    assert (refused.json()["code"], refused.json()["message"]) == (
        "not_owner",
        "Chỉ người tạo mẫu này mới đổi tên được",
    )
    assert item(an, template.id)["name"] == "Vườn nhà"
    assert an.patch(f"/api/edit-templates/{template.id}", json={"name": "Vườn ấm"}).status_code == 200
    assert item(binh, template.id)["name"] == "Vườn ấm"


def test_the_list_says_how_many_members_and_groups_use_a_template(an, binh, db, template, an_user, binh_user):
    assert item(an, template.id)["members_using"] == 0
    for user in (an_user, binh_user):
        db.get(User, user.id).edit_template_default = template.id
    group = first_topic(db)
    group.edit_templates.append(template)
    db.commit()
    shown = item(an, template.id)
    assert shown["members_using"] == 2
    assert [topic["name"] for topic in shown["topics"]] == ["Sức khỏe"]
    assert item(an, "app")["members_using"] == 0
