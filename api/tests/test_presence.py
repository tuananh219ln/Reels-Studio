"""Who else has a video open: each open page reports itself every few seconds, and a page silent for longer than
the time-out no longer counts."""

import pytest
from conftest import client_for, login, make_user, make_video
from sqlalchemy import text


@pytest.fixture
def an(db, client):
    make_user(db)
    login(client)
    return client


@pytest.fixture
def binh(db, app):
    make_user(db, email="binh@doi.vn", name="Trần Thị Bình")
    other = client_for(app)
    login(other, "binh@doi.vn")
    return other


@pytest.fixture
def video(db, storage, an):
    from reels_api.models import User

    owner = db.query(User).filter_by(email="an@doi.vn").one()
    return make_video(db, storage, owner, scene_count=1, images=False)


def here(client, video_id, tab, editing=False):
    response = client.post(f"/api/presence/videos/{video_id}", json={"tab": tab, "editing": editing})
    assert response.status_code == 200, response.text
    return response.json()["others"]


def leave(client, video_id, tab):
    response = client.post(f"/api/presence/videos/{video_id}/leave", json={"tab": tab})
    assert response.status_code == 200, response.text


def test_each_member_sees_the_others_on_the_video_but_not_themselves(an, binh, video):
    assert here(an, video.id, "tab-an") == []
    others = here(binh, video.id, "tab-binh", editing=True)
    assert [(o["name"], o["initial"], o["editing"]) for o in others] == [("Nguyễn Văn An", "A", False)]
    others = here(an, video.id, "tab-an")
    assert [(o["name"], o["initial"], o["editing"]) for o in others] == [("Trần Thị Bình", "B", True)]

    # Bình presses "Xong": the next report says viewing.
    here(binh, video.id, "tab-binh", editing=False)
    assert [o["editing"] for o in here(an, video.id, "tab-an")] == [False]


def test_one_member_with_two_tabs_counts_once_and_edits_if_either_tab_does(an, binh, video):
    here(binh, video.id, "binh-1")
    here(binh, video.id, "binh-2", editing=True)
    assert [(o["name"], o["editing"]) for o in here(an, video.id, "tab-an")] == [("Trần Thị Bình", True)]

    leave(binh, video.id, "binh-2")
    assert [(o["name"], o["editing"]) for o in here(an, video.id, "tab-an")] == [("Trần Thị Bình", False)]
    leave(binh, video.id, "binh-1")
    assert here(an, video.id, "tab-an") == []


def test_a_page_that_stops_reporting_drops_out_after_the_time_out(an, binh, video, db):
    here(binh, video.id, "tab-binh", editing=True)
    db.execute(text("UPDATE video_presence SET seen_at = seen_at - interval '29 seconds'"))
    assert len(here(an, video.id, "tab-an")) == 1
    db.execute(text("UPDATE video_presence SET seen_at = seen_at - interval '2 seconds' WHERE tab = 'tab-binh'"))
    assert here(an, video.id, "tab-an") == []
    # Silent pages are deleted, so the table does not grow with every page ever opened.
    assert db.execute(text("SELECT count(*) FROM video_presence WHERE tab = 'tab-binh'")).scalar() == 0


def test_members_on_another_video_are_not_listed(an, binh, video, db, storage):
    from reels_api.models import User

    other = make_video(db, storage, db.query(User).filter_by(email="an@doi.vn").one(), scene_count=1, images=False)
    here(binh, other.id, "tab-binh", editing=True)
    assert here(an, video.id, "tab-an") == []


def test_refusals(an, client, app, video):
    assert client.post("/api/presence/videos/999999", json={"tab": "t", "editing": False}).status_code == 404
    for tab in ("", "x" * 41, "có dấu", "a b"):
        refused = client.post(f"/api/presence/videos/{video.id}", json={"tab": tab, "editing": False})
        assert refused.status_code == 422, tab
    assert client_for(app).post(f"/api/presence/videos/{video.id}", json={"tab": "t"}).status_code == 401
    # Leaving a page that never reported (or already timed out) is fine.
    leave(an, video.id, "never-reported")
