"""A group's "Mô tả YouTube" (youtube_meta.py): the YouTube description and tags built from the caption as it is at
upload time, apart from the Facebook caption (docs/decisions/2026-11-25-youtube-description.md)."""

import pytest
from conftest import first_topic, login, make_user
from test_mcp import call, grant, mcp_client, payload  # noqa: F401  (mcp_client is a fixture)

from reels_api import youtube_meta

FB_TAGS = ["#HealthTips", "#HealthyLiving", "#HealthyFood", "#NutritionTips", "#FoodAsMedicine"]
CAPTION = "3 daily choices — good or bad? Which one surprised you? Like and follow for more health tips daily."
FOODDOSE = {
    "hashtags": ["#FoodDose", "#Shorts", "#HealthTips"],
    "keywords": ["food is medicine", "healthy foods"],
    "cta": "🔔 Subscribe to {channel} for daily food tips.",
    "disclaimer": "Disclaimer: not medical advice. No single food can cure disease.",
}


def test_a_group_with_nothing_set_uploads_the_caption_and_the_videos_hashtags():
    assert youtube_meta.description(CAPTION, FB_TAGS, None, "FoodDose") == f"{CAPTION}\n\n{' '.join(FB_TAGS)}"
    assert youtube_meta.description(CAPTION, FB_TAGS, youtube_meta.empty(), "FoodDose").endswith("#FoodAsMedicine")
    assert youtube_meta.tags(FB_TAGS, None) == [tag.lstrip("#") for tag in FB_TAGS]


def test_the_description_swaps_the_facebook_hashtags_for_cta_disclaimer_and_youtube_set():
    caption = f"{CAPTION} {' '.join(FB_TAGS)}"
    assert youtube_meta.description(caption, FB_TAGS, FOODDOSE, "FoodDose") == (
        f"{CAPTION}\n\n"
        "🔔 Subscribe to FoodDose for daily food tips.\n\n"
        "Disclaimer: not medical advice. No single food can cure disease.\n\n"
        "#FoodDose #Shorts #HealthTips"
    )


def test_keywords_go_to_the_tags_only_after_the_youtube_hashtags():
    assert "food is medicine" not in youtube_meta.description(CAPTION, FB_TAGS, FOODDOSE, "FoodDose")
    assert youtube_meta.tags(FB_TAGS, FOODDOSE) == [
        "FoodDose",
        "Shorts",
        "HealthTips",
        "food is medicine",
        "healthy foods",
    ]


def test_a_group_without_a_disclaimer_or_youtube_hashtags_keeps_the_videos_own():
    threads = {"cta": "🔔 Đăng ký {channel} để nghe đọc Threads mỗi ngày."}
    text = youtube_meta.description("Chuyện đám cưới.", ["#threads", "#reels"], threads, "Tiệm Đọc Comment")
    assert text == "Chuyện đám cưới.\n\n🔔 Đăng ký Tiệm Đọc Comment để nghe đọc Threads mỗi ngày.\n\n#threads #reels"


def test_the_cta_naming_a_channel_is_left_out_when_there_is_no_channel():
    text = youtube_meta.description(CAPTION, FB_TAGS, FOODDOSE, None)
    assert "Subscribe" not in text and "Disclaimer" in text


def test_a_long_caption_is_shortened_never_the_blocks_after_it():
    caption = "Một câu rất dài. " * 400
    text = youtube_meta.description(caption, FB_TAGS, FOODDOSE, "FoodDose")
    assert len(text) <= youtube_meta.MAX_DESCRIPTION
    assert text.endswith("#FoodDose #Shorts #HealthTips")
    assert "…\n\n🔔 Subscribe to FoodDose" in text


def test_only_fifteen_hashtags_are_written_in_the_description():
    many = {"hashtags": [f"#tag{chr(97 + i)}" for i in range(20)]}
    text = youtube_meta.description(CAPTION, FB_TAGS, many, None)
    assert text.split("\n\n")[-1].split() == many["hashtags"][:15]


def test_cleaning_adds_the_hash_dedupes_and_saves_nothing_when_empty():
    cleaned = youtube_meta.clean(
        {"hashtags": "FoodDose, #Shorts #fooddose", "keywords": "a, b\nb", "cta": " x ", "disclaimer": ""}
    )
    assert cleaned == {"hashtags": ["#FoodDose", "#Shorts"], "keywords": ["a", "b"], "cta": "x", "disclaimer": ""}
    assert youtube_meta.clean({"hashtags": [], "keywords": [], "cta": " ", "disclaimer": ""}) is None
    assert youtube_meta.clean(None) is None


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ({"hashtags": ["#a b"]}, "Hashtag không hợp lệ"),
        ({"hashtags": [f"#t{i}x" for i in range(21)]}, "tối đa 20"),
        ({"cta": "x" * 501}, "dài quá 500"),
        ({"title": "x"}, "Không có mục title"),
    ],
)
def test_cleaning_refuses_what_youtube_could_not_take(value, message):
    with pytest.raises(youtube_meta.MetaError, match=message):
        youtube_meta.clean(value)


# --- Kho kiến thức and MCP ---


@pytest.fixture
def an(client, db):
    make_user(db)
    login(client)
    return client


def test_a_member_sets_the_groups_youtube_description_and_it_is_in_the_history(an, db):
    group = first_topic(db)
    sent = {"hashtags": ["FoodDose", "#Shorts"], "keywords": ["food is medicine"], "cta": "Hi {channel}"}
    shown = an.patch(f"/api/knowledge/topics/{group.id}", json={"youtube_meta": sent})
    assert shown.status_code == 200, shown.json()
    row = next(row for row in shown.json()["topics"] if row["id"] == group.id)
    assert row["youtube_meta"] == {**sent, "hashtags": ["#FoodDose", "#Shorts"], "disclaimer": ""}
    assert row["youtube_meta_set"] is True
    history = an.get(f"/api/edit-logs?entity_type=knowledge_topic&entity_id={group.id}").json()["entries"]
    assert history[0]["changes"]["youtube_meta"]["old"] is None

    refused = an.patch(f"/api/knowledge/topics/{group.id}", json={"youtube_meta": {"hashtags": ["#a b"]}})
    assert refused.status_code == 422 and "Hashtag không hợp lệ" in refused.text

    cleared = an.patch(f"/api/knowledge/topics/{group.id}", json={"youtube_meta": None})
    row = next(row for row in cleared.json()["topics"] if row["id"] == group.id)
    assert row["youtube_meta_set"] is False and row["youtube_meta"] == youtube_meta.empty()


def test_an_assistant_reads_and_edits_the_groups_youtube_description(mcp_client, db):  # noqa: F811
    _, _, tokens, _ = grant(mcp_client, db)
    token = tokens["access_token"]
    group = first_topic(db)

    read = payload(call(mcp_client, token, "get_youtube_meta", knowledge_topic_id=group.id))
    assert read["is_set"] is False and read["youtube_meta"] == youtube_meta.empty()

    edited = call(
        mcp_client, token, "update_youtube_meta", knowledge_topic_id=group.id, hashtags=["#FoodDose"], cta="Hi"
    )
    assert not edited.get("isError"), edited
    again = payload(
        call(mcp_client, token, "update_youtube_meta", knowledge_topic_id=group.id, disclaimer="Not advice.")
    )
    assert again["youtube_meta"] == {
        "hashtags": ["#FoodDose"],
        "keywords": [],
        "cta": "Hi",
        "disclaimer": "Not advice.",
    }, "fields not sent are kept"
    bad = call(mcp_client, token, "update_youtube_meta", knowledge_topic_id=group.id, hashtags=["#a b"])
    assert bad["isError"] and "Hashtag không hợp lệ" in str(bad)
