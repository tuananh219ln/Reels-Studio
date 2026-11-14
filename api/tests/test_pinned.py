"""The pinned comment as a template filled from the video's title and scenes (pinned.py)."""

from conftest import login, make_user, make_video
from sqlalchemy import select

from reels_api import pinned
from reels_api.models import Scene

TITLE = "Sau 50 tuổi cứ 7 món canh này mà nấu"
DISHES = [
    ("Canh hến nấu cà chua", "Tốt cho tim mạch"),
    ("Canh củ cải trắng nấu sườn", "Nhẹ bụng, mát gan"),
    ("Canh mồng tơi nấu cua đồng", "Giàu canxi, đỡ mỏi gối"),
    ("Canh hẹ nấu đậu hũ non", "Mát gan, dễ tiêu"),
    ("Canh cải bẹ xanh nấu gừng", "Ấm cổ, tốt hô hấp"),
    ("Canh mướp đắng nhồi thịt", "Hỗ trợ mỡ máu"),
    ("Canh rau lang nấu tôm", "Hỗ trợ đường huyết"),
]
TEMPLATE = "{title}, vừa dễ nấu vừa tốt cho sức khỏe:\n{items}\nNhà bạn hay nấu món nào nhất? Bình luận số thứ tự nhé!"


def source(dishes=DISHES, title=TITLE, products=()):
    return pinned.build_source(title, "", [(f"{name}\n{benefit}", "") for name, benefit in dishes], list(products))


def numbered(text: str) -> list[str]:
    return [line for line in text.splitlines() if line[:1].isdigit()]


def codes(issues) -> list[str]:
    return [issue.message for issue in issues]


def test_normalize_drops_emphasis_and_extra_spaces_and_composes_unicode():
    decomposed = "Cua\u0300  *đồng*\n "
    assert pinned.normalize(decomposed) == "Cuà đồng"
    assert pinned.normalize(" *Canh*   hến ") == "Canh hến"


def test_the_source_is_the_title_and_each_scenes_first_line_then_the_rest():
    built = pinned.build_source(
        "*Sau 50 tuổi*\ncứ 7 món",
        "Mở đầu nè",
        [("Canh hến\nTốt cho\ntim mạch", ""), ("  \n", "x"), ("Canh bí", "Đọc")],
        [],
    )
    assert (built.title, built.hook) == ("Sau 50 tuổi cứ 7 món", "Mở đầu nè")
    assert [(item.order, item.name, item.benefit, item.voice) for item in built.items] == [
        (1, "Canh hến", "Tốt cho tim mạch", "Canh hến Tốt cho tim mạch"),
        (2, "Canh bí", "", "Đọc"),
    ], "an empty scene is left out and the next one takes its number"
    assert pinned.build_source("Tiêu đề", "", [], []).hook == "Tiêu đề", "no narration: the hook is the title"


def test_the_template_renders_the_whole_list_from_the_scenes():
    text = pinned.render(TEMPLATE, source())
    assert text.splitlines()[0] == f"{TITLE}, vừa dễ nấu vừa tốt cho sức khỏe:"
    assert numbered(text)[2] == "3. Canh mồng tơi nấu cua đồng – Giàu canxi, đỡ mỏi gối"
    assert len(numbered(text)) == 7
    assert text.endswith("Bình luận số thứ tự nhé!")


def test_every_variable_is_filled_and_an_unknown_one_stays():
    built = source(DISHES[:2], products=["Nồi nấu canh"])
    text = pinned.render("{count} món: {item_names}. {products} {hook} {nope}", built)
    assert text == f"2 món: Canh hến nấu cà chua, Canh củ cải trắng nấu sườn. Nồi nấu canh {TITLE} {{nope}}"


def test_a_plain_comment_reads_as_itself_and_blank_lines_collapse():
    assert pinned.render("  Món nào nhà bạn hay nấu nhất?  ", source()) == "Món nào nhà bạn hay nấu nhất?"
    assert pinned.render("Mở\n{products}\n\n\nKết", source()) == "Mở\n\nKết"


def test_editing_deleting_and_reordering_scenes_change_the_comment():
    renamed = [*DISHES[:2], ("Canh bí đao nấu tôm", "Mát"), *DISHES[3:]]
    assert numbered(pinned.render(TEMPLATE, source(renamed)))[2] == "3. Canh bí đao nấu tôm – Mát"
    deleted = numbered(pinned.render(TEMPLATE, source(DISHES[:4] + DISHES[5:])))
    assert [line.split(".")[0] for line in deleted] == ["1", "2", "3", "4", "5", "6"]
    assert "Canh cải bẹ xanh" not in "".join(deleted)
    moved = numbered(pinned.render(TEMPLATE, source([DISHES[6], *DISHES[:6]])))
    assert moved[0].startswith("1. Canh rau lang nấu tôm")


def test_emphasis_marks_do_not_change_the_comment():
    marked = [(f"*{name}*", benefit) for name, benefit in DISHES]
    assert pinned.render(TEMPLATE, source(marked)) == pinned.render(TEMPLATE, source())


def test_a_new_scripts_template_lists_the_scenes_before_the_ais_question():
    assert pinned.default_template(" Nhà bạn hay nấu món nào? ") == "{title}\n{items}\nNhà bạn hay nấu món nào?"
    assert pinned.default_template("") == "{title}\n{items}"
    assert pinned.follows_scenes("{items}") and pinned.follows_scenes("a {item_names}")
    assert not pinned.follows_scenes("{title} hỏi gì đó")


def test_a_template_that_lists_the_scenes_raises_no_warning():
    assert pinned.validate(TEMPLATE, source(), []) == []


def test_a_title_counting_other_than_the_scenes_warns_on_the_scenes():
    (issue,) = pinned.validate(TEMPLATE, source(DISHES[:6]), [])
    assert issue.field == "scenes"
    assert issue.message.startswith("Tiêu đề ghi “7 món” nhưng video có 6 cảnh nội dung")
    assert pinned.validate("", source(DISHES[:7], title="Sau 50 tuổi nên ăn canh"), []) == [], "no count, no warning"


def test_a_hand_typed_list_warns_of_a_missing_extra_or_misordered_scene():
    typed = "\n".join(f"{order}. {name}" for order, (name, _) in enumerate(DISHES, start=1))
    assert pinned.validate(typed, source(), []) == []
    renamed = [*DISHES[:2], ("Canh bí đao nấu tôm", "Mát"), *DISHES[3:]]
    assert codes(pinned.validate(typed, source(renamed), [])) == [
        "Bình luận ghim có dòng “Canh mồng tơi nấu cua đồng” không khớp cảnh nào",
        "Bình luận ghim thiếu cảnh 3: “Canh bí đao nấu tôm”",
    ]
    reordered = "\n".join(f"{order}. {name}" for order, (name, _) in enumerate([DISHES[1], DISHES[0], *DISHES[2:]], 1))
    assert codes(pinned.validate(reordered, source(), [])) == ["Thứ tự các món trong bình luận ghim khác thứ tự cảnh"]


def test_a_link_mentioned_with_no_product_attached_warns():
    message = "Bình luận nhắc tới “link” nhưng video chưa gắn sản phẩm nào"
    assert codes(pinned.validate(TEMPLATE, source(), ["Link nồi nấu canh trong bình luận ghim"])) == [message]
    assert codes(pinned.validate("Link ở dưới nhé", source(), [])) == [message]
    assert pinned.validate("Link ở dưới nhé", source(products=["Nồi"]), []) == []
    assert pinned.validate("Đường linkage", source(), []) == [], "only the word link"


def test_a_comment_over_1500_characters_warns():
    (issue,) = pinned.validate("a" * 1501, source(), [])
    assert issue.message == "Bình luận ghim dài 1501 ký tự, nên tối đa 1500 ký tự"


def test_the_video_shows_the_template_and_what_it_reads_as_now(client, db, storage):
    me = make_user(db)
    login(client)
    video = make_video(db, storage, me, scene_count=2, title_text="2 món canh", scene_text="Canh hến\nTốt cho tim")
    video.pinned_comment = "{title}:\n{items}\nNhà bạn nấu món nào?"
    db.commit()
    body = client.get(f"/api/videos/{video.id}").json()
    assert body["pinned_comment"] == "{title}:\n{items}\nNhà bạn nấu món nào?"
    assert (
        body["pinned_comment_text"]
        == "2 món canh:\n1. Canh hến – Tốt cho tim\n2. Canh hến – Tốt cho tim\nNhà bạn nấu món nào?"
    )
    assert body["pinned_products"] == []
    # Editing a scene changes the comment with nothing else to do.
    last = db.scalars(select(Scene).where(Scene.video_id == video.id).order_by(Scene.position.desc())).first()
    assert client.patch(f"/api/scenes/{last.id}", json={"text": "Canh bí\nMát gan"}).status_code == 200
    assert client.get(f"/api/videos/{video.id}").json()["pinned_comment_text"].splitlines()[2] == "2. Canh bí – Mát gan"
