"""Cửa đo 48h of a Page (page_dashboard.gate): median views and share/view at 48 hours, progress towards 14 and 30
videos, the gate's state and the winners (10× the Page's median)."""

import pytest
from conftest import login, make_user
from test_analytics import NOW, frozen, marked, page  # noqa: F401  (frozen is a fixture)

from reels_api import analytics


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def gate(an, fanpage: int) -> dict:
    response = an.get(f"/api/fanpages/{fanpage}/gate")
    assert response.status_code == 200, response.text
    return response.json()


def test_a_page_with_nothing_measured_is_still_measuring(an, db, me, frozen):
    result = gate(an, page(db, me))
    assert (result["measured"], result["first"], result["last"]) == (0, 14, 30)
    assert (result["median_views"], result["median_share_rate"], result["state"]) == (None, None, "measuring")
    assert result["winners"] == []
    assert an.get("/api/fanpages/999999/gate").status_code == 404


def test_the_gate_passes_on_a_median_over_1000_and_a_video_over_10000(an, db, me, storage, frozen):
    fanpage = page(db, me)
    for views in (1200, 1300, 1400, 1500, 12000):
        marked(db, storage, me, fanpage, views, shares=2)
    result = gate(an, fanpage)
    assert (result["measured"], result["median_views"], result["top_views"]) == (5, 1400, 12000)
    assert result["median_share_rate"] == pytest.approx(2 / 1400)
    assert result["state"] == "pass"
    # 12000 is 8.6× the median: not yet a winner.
    assert result["winners"] == []


def test_a_median_over_1000_without_a_video_over_10000_does_not_pass(an, db, me, storage, frozen):
    fanpage = page(db, me)
    for views in (1200, 1300, 1400, 1500, 9000):
        marked(db, storage, me, fanpage, views)
    assert gate(an, fanpage)["state"] == "measuring"


def test_winners_are_ten_times_the_median_and_the_flag_follows_on_every_screen(an, db, me, storage, frozen):
    fanpage = page(db, me)
    for views in (100, 100, 100, 100, 100):
        marked(db, storage, me, fanpage, views)
    star = marked(db, storage, me, fanpage, 1000)
    result = gate(an, fanpage)
    assert [(w["views_48h"], w["times_median"]) for w in result["winners"]] == [(1000, 10.0)]
    assert result["winners"][0]["post_id"] == star.id
    assert analytics.is_winner(10.0) and not analytics.is_winner(9.9) and not analytics.is_winner(None)
    row = next(r for r in an.get("/api/posts").json() if r["id"] == star.id)
    assert row["metrics"]["analysis"]["is_winner"] is True


def test_thirty_weak_videos_say_to_change_hook_and_pillar(an, db, me, storage, frozen):
    fanpage = page(db, me)
    for _ in range(30):
        marked(db, storage, me, fanpage, 300, shares=0)
    result = gate(an, fanpage)
    assert (result["measured"], result["state"]) == (30, "change")
    assert "hook" in result["state_label"]


def test_thirty_middling_videos_neither_pass_nor_change(an, db, me, storage, frozen):
    fanpage = page(db, me)
    for _ in range(30):
        marked(db, storage, me, fanpage, 700, shares=1)
    assert gate(an, fanpage)["state"] == "hold"
