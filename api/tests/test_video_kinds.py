"""What kind of video each one is, on every list of videos: how its script was made, how it is built, whether it
carries products, and the content type a member gave it ("Loại nội dung")."""

import pytest
from conftest import login, make_user, make_video
from test_affiliate_accounts import attach, product


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


def rows(an) -> dict[int, dict]:
    return {row["id"]: row for row in an.get("/api/videos").json()}


def test_each_row_says_how_its_script_was_made_how_it_is_built_and_its_products(an, db, me, storage):
    ai = make_video(db, storage, me)
    typed = make_video(db, storage, me)
    typed.hand_written = True
    assistant = make_video(db, storage, me)
    assistant.written_via = "assistant"
    clone = make_video(db, storage, me)
    clone.clone_source = {"title": "Gốc"}
    sample = make_video(db, storage, me)
    sample.reference_mode = "quick"
    sample.mode = "single"
    db.flush()
    attach(db, ai.id, product(db, me))

    listed = rows(an)
    assert {video.id: listed[video.id]["made_via"] for video in (ai, typed, assistant, clone, sample)} == {
        ai.id: "ai",
        typed.id: "manual",
        assistant.id: "assistant",
        clone.id: "clone",
        sample.id: "sample",
    }
    assert (listed[sample.id]["mode"], listed[ai.id]["mode"]) == ("single", "slides")
    assert (listed[ai.id]["product_count"], listed[typed.id]["product_count"]) == (1, 0)
    detail = an.get(f"/api/videos/{sample.id}").json()
    assert (detail["made_via"], detail["content_type"], detail["posted_on"]) == ("sample", "", [])


def test_a_member_gives_a_video_a_content_type_suggested_from_those_used(an, db, me, storage):
    first, second, third = (make_video(db, storage, me) for _ in range(3))
    saved = an.patch(f"/api/videos/{first.id}", json={"content_type": "  Hướng   dẫn tập "}).json()
    assert saved["content_type"] == "Hướng dẫn tập"
    an.patch(f"/api/videos/{second.id}", json={"content_type": "Mẹo nhanh"})
    an.patch(f"/api/videos/{third.id}", json={"content_type": "hướng dẫn tập"})
    listed = rows(an)
    assert (listed[first.id]["content_type"], listed[second.id]["content_type"]) == ("Hướng dẫn tập", "Mẹo nhanh")
    # One suggestion per type, whatever its case, in the alphabet's order.
    assert an.get("/api/video-content-types").json() == ["Hướng dẫn tập", "Mẹo nhanh"]

    assert an.patch(f"/api/videos/{second.id}", json={"content_type": ""}).json()["content_type"] == ""
    refused = an.patch(f"/api/videos/{third.id}", json={"content_type": "x" * 41})
    assert refused.status_code == 422 and "Loại nội dung" in refused.json()["message"]
