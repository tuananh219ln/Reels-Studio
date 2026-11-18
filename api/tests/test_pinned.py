"""The pinned comment: the title, the scenes numbered from 1, then the survey line (pinned.py)."""

import importlib.util
from pathlib import Path

import pytest
from conftest import first_topic, login, make_user, make_video
from sqlalchemy import select

from reels_api import pinned
from reels_api.models import Scene

TITLE = "7 cặp rau củ ăn cùng nhau thành thuốc bổ"
PAIRS = [
    "CÀ TÍM + ĐẬU ĐŨA",
    "BÔNG CẢI XANH + ỚT CHUÔNG",
    "CẢI THÌA + NẤM HƯƠNG",
    "BÍ NGÒI + CÀ RỐT",
    "CẦN TÂY + MỘC NHĨ",
    "GIÁ ĐỖ + LÁ HẸ",
    "CẢI THẢO + ỚT CHUÔNG",
]
SURVEY = "Bạn hay ăn cặp nào nhất? Bình luận số thứ tự nhé"
EXPECTED = "\n".join([TITLE, *(f"{order}. {name}" for order, name in enumerate(PAIRS, start=1)), SURVEY])


def source(texts, title=TITLE, products=()):
    return pinned.build_source(title, list(texts), list(products))


def codes(issues) -> list[str]:
    return [issue.message for issue in issues]


@pytest.mark.parametrize(
    ("name", "stripped"),
    [
        ("1. CÀ TÍM + ĐẬU ĐŨA", "CÀ TÍM + ĐẬU ĐŨA"),
        ("2) BÔNG CẢI XANH", "BÔNG CẢI XANH"),
        ("3 - CẢI THÌA", "CẢI THÌA"),
        ("#4: BÍ NGÒI", "BÍ NGÒI"),
        ("Cặp 5: CẦN TÂY", "CẦN TÂY"),
        ("số 6 – GIÁ ĐỖ", "GIÁ ĐỖ"),
        ("CẢI THẢO + ỚT CHUÔNG", "CẢI THẢO + ỚT CHUÔNG"),
        ("5 LOẠI RAU", "5 LOẠI RAU"),
    ],
)
def test_the_number_before_a_scene_name_is_dropped_only_with_a_mark_after_it(name, stripped):
    assert pinned.strip_index(name) == stripped


def test_a_name_that_already_says_its_number_is_not_numbered_twice():
    numbered = [f"{order}. {name}" for order, name in enumerate(PAIRS, start=1)]
    assert pinned.render(SURVEY, source(numbered)) == EXPECTED
    assert pinned.render(SURVEY, source(PAIRS)) == EXPECTED, "a scene with no number gets one"


def test_the_list_is_numbered_again_after_a_reorder_or_a_delete():
    numbered = [f"{order}. {name}" for order, name in enumerate(PAIRS, start=1)]
    moved = pinned.render("", source([numbered[2], numbered[0], numbered[1]]))
    assert moved.splitlines()[1:] == ["1. CẢI THÌA + NẤM HƯƠNG", "2. CÀ TÍM + ĐẬU ĐŨA", "3. BÔNG CẢI XANH + ỚT CHUÔNG"]
    deleted = pinned.render("", source(numbered[:3] + numbered[4:]))
    assert [line.split(".")[0] for line in deleted.splitlines()[1:]] == ["1", "2", "3", "4", "5", "6"]


def test_a_scenes_name_is_its_first_line_without_emphasis_and_an_empty_scene_is_left_out():
    built = source(["1. *Canh hến*\nTốt cho tim", "  \n", "2.", "Canh  bí\nMát gan"], title="*Sau 50 tuổi*\ncứ ăn")
    assert built.title == "Sau 50 tuổi cứ ăn"
    assert built.names == ["Canh hến", "Canh bí"]
    assert pinned.render("", built) == "Sau 50 tuổi cứ ăn\n1. Canh hến\n2. Canh bí"


def test_an_empty_part_leaves_no_blank_line():
    assert pinned.render("  ", source(PAIRS[:1])) == f"{TITLE}\n1. CÀ TÍM + ĐẬU ĐŨA"
    assert pinned.render(SURVEY, source([])) == f"{TITLE}\n{SURVEY}"
    assert pinned.render(SURVEY, source([], title="")) == SURVEY
    assert pinned.render("", source([], title="")) == ""


def test_a_new_scripts_survey_is_the_ais_question_or_the_default():
    assert pinned.survey_of_script(" Nhà bạn hay nấu món nào? ") == "Nhà bạn hay nấu món nào?"
    assert pinned.survey_of_script("") == pinned.DEFAULT_SURVEY == SURVEY


def test_a_comment_that_lists_the_scenes_raises_no_warning():
    assert pinned.validate(SURVEY, source(PAIRS), []) == []


def test_a_title_counting_other_than_the_scenes_warns_on_the_scenes():
    (issue,) = pinned.validate(SURVEY, source(PAIRS[:6]), [])
    assert issue.field == "scenes"
    assert issue.message.startswith("Tiêu đề ghi “7 cặp” nhưng video có 6 cảnh nội dung")
    assert pinned.validate(SURVEY, source(PAIRS[:6], title="Rau củ ăn cùng nhau"), []) == [], "no count, no warning"


def test_a_link_mentioned_with_no_product_attached_warns():
    message = "Bình luận nhắc tới “link” nhưng video chưa gắn sản phẩm nào"
    assert codes(pinned.validate(SURVEY, source(PAIRS), ["Link nồi trong bình luận ghim"])) == [message]
    assert codes(pinned.validate("Link ở dưới nhé", source(PAIRS), [])) == [message]
    assert pinned.validate("Link ở dưới nhé", source(PAIRS, products=["Nồi"]), []) == []
    assert pinned.validate("Đường linkage", source(PAIRS), []) == [], "only the word link"


def test_a_comment_over_1500_characters_warns():
    (issue,) = pinned.validate("a" * 1500, source(PAIRS), [])
    assert issue.message.startswith("Bình luận ghim dài") and issue.message.endswith("nên tối đa 1500 ký tự")


def test_the_video_shows_the_survey_and_the_comment_as_it_reads_now(client, db, storage):
    me = make_user(db)
    login(client)
    video = make_video(db, storage, me, scene_count=2, title_text="2 món canh", scene_text="1. Canh hến\nTốt cho tim")
    video.pinned_survey = "Nhà bạn nấu món nào?"
    db.commit()
    body = client.get(f"/api/videos/{video.id}").json()
    assert body["pinned_survey"] == "Nhà bạn nấu món nào?"
    assert body["pinned_comment_text"] == "2 món canh\n1. Canh hến\n2. Canh hến\nNhà bạn nấu món nào?"
    assert "pinned_comment" not in body and "pinned_products" not in body
    # Editing a scene changes the comment with nothing else to do.
    last = db.scalars(select(Scene).where(Scene.video_id == video.id).order_by(Scene.position.desc())).first()
    assert client.patch(f"/api/scenes/{last.id}", json={"text": "Canh bí\nMát gan"}).status_code == 200
    assert client.get(f"/api/videos/{video.id}").json()["pinned_comment_text"].splitlines()[2] == "2. Canh bí"
    # "Dòng khảo sát" is saved per video, as one line; cleared, the comment ends with the list.
    saved = client.patch(f"/api/videos/{video.id}", json={"pinned_survey": "  Bạn chọn\n món nào? "}).json()
    assert saved["pinned_survey"] == "Bạn chọn món nào?"
    cleared = client.patch(f"/api/videos/{video.id}", json={"pinned_survey": ""}).json()
    assert cleared["pinned_survey"] == "" and cleared["pinned_comment_text"] == "2 món canh\n1. Canh hến\n2. Canh bí"


def test_a_new_video_gets_the_default_survey(client, db):
    make_user(db)
    login(client)
    made = client.post("/api/videos", json={"knowledge_topic_id": first_topic(db).id, "mode": "manual", "topic": "Rau"})
    assert made.status_code == 201, made.text
    assert made.json()["pinned_survey"] == pinned.DEFAULT_SURVEY


def _migration():
    path = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0110_pinned_survey.py"
    spec = importlib.util.spec_from_file_location("migration_0110", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("template", "survey"),
    [
        ("{title}\n{items}\nBạn thích rau nào nhất?", "Bạn thích rau nào nhất?"),
        ("{title}:\n{items}\n\n  Nhà bạn nấu món nào?  \n{products}", "Nhà bạn nấu món nào?"),
        ("{title}\n{items}\n{products}", SURVEY),
        ("{title}\n{items}", SURVEY),
        ("Món nào nhà bạn hay nấu nhất?", SURVEY),
        ("", SURVEY),
    ],
)
def test_an_old_template_gives_its_survey_line(template, survey):
    assert _migration().survey_of(template) == survey
