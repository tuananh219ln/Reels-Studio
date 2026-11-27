"""The AI cuts PC Shopee's title into tiers in the script call (jobs.TITLE_TIERS_FORMAT), docs/decisions/2026-11-27-pc-text-motion.md."""

import json

from reels_api import jobs
from reels_api.claude import parse_output
from reels_api.models import KnowledgeTopic, Video

SCENE = {"text": "A", "seconds": 4, "voice": "Một hai ba bốn năm sáu bảy tám.", "keywords": ["a"]}


def answer(**extra) -> str:
    return json.dumps({"titles": ["Black Friday: 5 món PC đáng săn, xem trước khi mua"], "scenes": [SCENE], **extra})


def group(name: str) -> KnowledgeTopic:
    return KnowledgeTopic(
        name=name, script_prompt="Viết kịch bản.", banned_words=[], photo_hint="", text_ai=False, outro_cta=False
    )


def test_the_prompt_asks_for_tiers_only_for_pc_shopee():
    pc = jobs.script_prompt(group("PC Shopee"), "chuột", None, False, False)
    other = jobs.script_prompt(group("Ăn Lành"), "chuột", None, False, False)
    assert "title_tiers" in pc and "title_tiers" not in other


def test_the_tiers_are_read_clean_and_need_a_main_line():
    tiers = parse_output(
        answer(
            title_tiers={
                "small": "Black Friday",
                "main": " 5 món PC ",
                "sub": "đáng săn",
                "label": "[[-50%]]",
                "extra": "xem trước khi mua",
            }
        )
    ).title_tiers
    assert tiers == {
        "small": "Black Friday",
        "main": "5 món PC",
        "sub": "đáng săn",
        "label": "-50%",
        "extra": "xem trước khi mua",
    }
    assert parse_output(answer(title_tiers={"small": "x", "main": ""})).title_tiers is None
    assert parse_output(answer(title_tiers="Black Friday")).title_tiers is None
    assert parse_output(answer()).title_tiers is None


def test_the_title_scene_takes_the_tiers_as_lines_and_the_rest_goes_to_the_caption_head():
    script = parse_output(
        answer(
            caption="Mô tả.",
            title_tiers={
                "small": "Black Friday",
                "main": "5 món PC",
                "sub": "đáng săn",
                "label": "-50%",
                "extra": "xem trước khi mua",
            },
        )
    )
    video = Video(options={"title_layout": "three_tier"})
    assert jobs.title_text(video, group("PC Shopee"), script) == "Black Friday\n5 món PC\nđáng săn\n[[-50%]]"
    # Any other group, or a title in a box, keeps the first title as written.
    assert jobs.title_text(video, group("Ăn Lành"), script) == script.titles[0]
    assert jobs.title_text(Video(options={"title_layout": "box"}), group("PC Shopee"), script) == script.titles[0]


def test_the_tiers_read_back_as_the_renders_three_tiers():
    from reels_render.markup import parse_scene_text
    from reels_render.tiers import parse_title

    script = parse_output(
        answer(title_tiers={"small": "Black Friday", "main": "5 món PC", "sub": "đáng săn", "label": "-50%"})
    )
    text = jobs.title_text(Video(options={"title_layout": "three_tier"}), group("PC Shopee"), script)
    tiers = parse_title(parse_scene_text(text))
    # The title is read in capitals (the video's letter case), so compare without case.
    assert (tiers.small.casefold(), tiers.main.casefold(), tiers.sub.casefold(), tiers.label) == (
        "black friday",
        "5 món pc",
        "đáng săn",
        "-50%",
    )
