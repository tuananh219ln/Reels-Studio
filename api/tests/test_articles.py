"""Articles ("Bài viết"): drafts, the AI caption job, the text card, a pasted photo and the checks."""

import io
import json

import pytest
from conftest import first_topic, login, make_user
from PIL import Image
from sqlalchemy import select
from worker_helpers import add_user, committed, job_row  # noqa: F401  (fixtures)

from reels_api import articles, jobs, knowledge, remote_media
from reels_api.claude import OUTPUT_FORMAT, build_script_prompt
from reels_api.models import Article, Job, KnowledgeTopic
from reels_api.storage import DirectoryStorage


@pytest.fixture
def me(db):
    return make_user(db)


@pytest.fixture
def an(client, me):
    login(client)
    return client


@pytest.fixture
def topic_id(db):
    return first_topic(db).id


def create(an, topic_id, kind="kien_thuc", topic="Uống nước ấm buổi sáng", **fields):
    response = an.post("/api/articles", json={"knowledge_topic_id": topic_id, "kind": kind, "topic": topic, **fields})
    assert response.status_code == 201, response.text
    return response.json()


NOTE = "Ai có bệnh nền thì hỏi bác sĩ trước nhé."


def answer(hook="Uống nước lạnh sau khi ăn có hại?", body="Dòng 1\nDòng 2\nDòng 3", question="Bạn uống gì?", **more):
    return json.dumps({"hook": hook, "body": body, "question": question, "hashtags": ["#suckhoe"], **more})


# --- Drafts ---


def test_an_article_starts_as_a_draft_without_caption_or_picture(an, topic_id):
    article = create(an, topic_id)
    assert article["status"] == "draft" and article["status_label"] == "Nháp"
    assert (article["kind"], article["kind_label"], article["group_name"]) == (
        "kien_thuc",
        "Kiến thức ngắn",
        "Sức khỏe",
    )
    assert article["caption"] == "" and article["hashtags"] == [] and article["has_image"] is False
    # No picture is fine (a text post); no caption is what blocks.
    assert [issue["message"] for issue in article["checks"]["blocking"]] == ["Chưa có caption"]
    listed = an.get("/api/articles").json()
    assert [row["id"] for row in listed["articles"]] == [article["id"]]
    assert [kind["value"] for kind in listed["kinds"]] == list(articles.KIND_LABELS)
    # No fixed disclaimer any more: the AI writes its own reminder (decisions 2026-11-07).
    assert "disclaimer" not in listed


def test_a_kind_or_group_that_does_not_exist_is_refused(an, topic_id):
    assert an.post("/api/articles", json={"knowledge_topic_id": topic_id, "kind": "carousel"}).status_code == 422
    assert an.post("/api/articles", json={"knowledge_topic_id": 999999, "kind": "meo"}).status_code == 422
    assert an.get("/api/articles/999999").status_code == 404


def test_the_list_filters_by_group_and_kind(an, db, topic_id):
    other = KnowledgeTopic(name="Làm vườn")
    db.add(other)
    db.commit()
    first = create(an, topic_id, kind="meo")
    create(an, other.id, kind="cau_hoi")
    assert [row["id"] for row in an.get(f"/api/articles?topic_id={topic_id}").json()["articles"]] == [first["id"]]
    assert [row["kind"] for row in an.get("/api/articles?kind=cau_hoi").json()["articles"]] == ["cau_hoi"]


def test_a_member_edits_the_caption_and_hashtags(an, topic_id):
    article = create(an, topic_id)
    saved = an.patch(
        f"/api/articles/{article['id']}",
        json={"caption": f"Mẹo hay\n\nNội dung\n\n{NOTE}", "hashtags": ["suckhoe", "#SucKhoe", "#meo"]},
    ).json()
    assert saved["hook"] == "Mẹo hay"
    # "#" added, repeats (case ignored) dropped.
    assert saved["hashtags"] == ["#suckhoe", "#meo"]
    assert saved["checks"] == {"blocking": [], "warnings": []}
    too_many = an.patch(f"/api/articles/{article['id']}", json={"hashtags": [f"#tag{n}a" for n in range(6)]})
    assert too_many.status_code == 422


def test_a_link_in_the_caption_blocks_and_a_banned_word_only_warns(an, db, topic_id):
    first_topic(db).banned_words = ["chữa khỏi"]
    db.commit()
    article = create(an, topic_id)
    for caption in ("Mua tại https://shope.ee/abc", "Xem shope.ee/abc nhé", "vào www.example.vn"):
        saved = an.patch(f"/api/articles/{article['id']}", json={"caption": caption}).json()
        assert "Caption có link: link sản phẩm chỉ để ở bình luận ghim" in [
            issue["message"] for issue in saved["checks"]["blocking"]
        ], caption
    saved = an.patch(f"/api/articles/{article['id']}", json={"caption": f"Gừng chữa khỏi ho 0.5 lít\n\n{NOTE}"}).json()
    assert saved["checks"]["blocking"] == []
    assert [issue["message"] for issue in saved["checks"]["warnings"]] == ["Có từ cấm: “chữa khỏi”"]


def test_a_caption_without_the_old_fixed_sentence_is_fine(an, topic_id):
    article = create(an, topic_id)
    saved = an.patch(f"/api/articles/{article['id']}", json={"caption": "Chỉ một dòng"}).json()
    assert saved["checks"] == {"blocking": [], "warnings": []}


def test_the_pinned_comment_and_product_ideas_are_edited_and_checked(an, db, topic_id):
    first_topic(db).banned_words = ["thần dược"]
    db.commit()
    article = create(an, topic_id)
    saved = an.patch(
        f"/api/articles/{article['id']}",
        json={"pinned_comment": "  Gừng là thần dược đó  ", "affiliates": [" bình  giữ nhiệt ", "", "bình giữ nhiệt"]},
    ).json()
    assert (saved["pinned_comment"], saved["affiliates"]) == ("Gừng là thần dược đó", ["bình giữ nhiệt"])
    assert "Bình luận ghim có từ cấm: “thần dược”" in [issue["message"] for issue in saved["checks"]["warnings"]]
    linked = an.patch(f"/api/articles/{article['id']}", json={"pinned_comment": "Mua ở shope.ee/x"}).json()
    assert "Bình luận ghim có link: link sản phẩm do app tự thêm sau bình luận" in [
        issue["message"] for issue in linked["checks"]["blocking"]
    ]


def test_an_article_is_deleted_with_its_picture(an, db, topic_id, tmp_path):
    article = create(an, topic_id)
    an.patch(f"/api/articles/{article['id']}", json={"caption": "Thẻ chữ thử"})
    an.post(f"/api/articles/{article['id']}/text-card", json={"preset": "cam"})
    key = db.scalar(select(Article.image_key).where(Article.id == article["id"]))
    storage = DirectoryStorage(tmp_path / "storage")
    assert storage.exists(key)
    assert an.delete(f"/api/articles/{article['id']}").json() == {"ok": True}
    assert not storage.exists(key)
    assert an.get(f"/api/articles/{article['id']}").status_code == 404


# --- Pictures ---


def test_a_text_card_draws_the_caption_first_line_in_the_chosen_colour(an, topic_id, tmp_path):
    article = create(an, topic_id)
    refused = an.post(f"/api/articles/{article['id']}/text-card", json={"preset": "cam"})
    assert refused.status_code == 422 and "viết caption trước" in refused.json()["message"]
    an.patch(f"/api/articles/{article['id']}", json={"caption": "Ăn sáng muộn có sao không?\n\nNội dung"})
    saved = an.post(f"/api/articles/{article['id']}/text-card", json={"preset": "xanh_la"}).json()
    assert (saved["has_image"], saved["image_kind"], saved["image_kind_label"]) == (True, "text_card", "Thẻ chữ")
    image = Image.open(io.BytesIO(an.get(f"/api/articles/{article['id']}/image").content))
    assert image.size == articles.CARD_SIZE
    # The corner is the preset's background.
    assert image.getpixel((5, 5)) == pytest.approx((0x2F, 0x7D, 0x4F), abs=6)
    assert an.post(f"/api/articles/{article['id']}/text-card", json={"preset": "tim"}).status_code == 422


def test_a_text_card_fits_vietnamese_text_of_the_longest_allowed_length():
    data = articles.text_card("Ăn " * 66 + "ổi", "kem")
    assert Image.open(io.BytesIO(data)).size == articles.CARD_SIZE
    with pytest.raises(articles.CardError):
        articles.text_card("a" * (articles.MAX_CARD_CHARS + 1), "kem")


def test_a_pasted_photo_keeps_its_link_and_a_video_link_is_refused(an, topic_id, monkeypatch):
    article = create(an, topic_id)
    photo = io.BytesIO()
    Image.new("RGB", (40, 30), "red").save(photo, "PNG")
    monkeypatch.setattr(
        remote_media, "download", lambda url, folder: remote_media.Media(photo=(photo.getvalue(), "png"))
    )
    saved = an.post(f"/api/articles/{article['id']}/image-from-url", json={"url": " https://anh.vn/a.png "}).json()
    assert (saved["image_kind"], saved["image_source"]) == ("link", "https://anh.vn/a.png")
    removed = an.delete(f"/api/articles/{article['id']}/image").json()
    assert (removed["has_image"], removed["image_kind"], removed["image_source"]) == (False, None, None)
    monkeypatch.setattr(remote_media, "download", lambda url, folder: remote_media.Media(clip=folder / "x.mp4"))
    refused = an.post(f"/api/articles/{article['id']}/image-from-url", json={"url": "https://tiktok.com/x"})
    assert refused.status_code == 422 and refused.json()["message"] == "Link này là video: bài viết chỉ nhận ảnh"


# --- The AI caption ---


def test_ai_caption_queues_one_job_and_locks_the_article_meanwhile(an, db, topic_id):
    article = create(an, topic_id)
    queued = an.post(f"/api/articles/{article['id']}/caption").json()
    assert queued["busy"] is True and queued["job"]["status"] == "queued"
    assert an.post(f"/api/articles/{article['id']}/caption").status_code == 409
    assert an.patch(f"/api/articles/{article['id']}", json={"caption": "x"}).status_code == 409
    job = db.scalar(select(Job).where(Job.article_id == article["id"]))
    assert (job.kind, job.video_id, job.knowledge_topic_id) == ("article_caption", None, None)
    # The job log names the article; cancelling gives the article back.
    row = next(row for row in an.get("/api/jobs").json() if row["id"] == job.id)
    assert (row["video_title"], row["article_id"], row["kind_label"]) == (
        "Bài viết · Uống nước ấm buổi sáng",
        article["id"],
        "Viết bài viết",
    )
    cancelled = an.post(f"/api/jobs/{job.id}/cancel").json()
    assert cancelled["id"] == article["id"] and cancelled["busy"] is False


def test_ai_caption_needs_a_topic(an, topic_id):
    article = create(an, topic_id, topic="")
    refused = an.post(f"/api/articles/{article['id']}/caption")
    assert refused.status_code == 422 and refused.json()["message"] == "Nhập chủ đề của bài trước khi nhờ AI viết"


def test_the_article_prompt_uses_the_shared_assembly_and_the_group_banned_words(db):
    group = first_topic(db)
    group.banned_words = ["thần dược"]
    article = Article(kind="tra_loi_binh_luan", topic="Ngủ trưa bao lâu là đủ")
    prompt = articles.build_prompt(group, article, "Lan: ngủ trưa 2 tiếng có sao không?")
    assert "Trả lời bình luận" in prompt and "Ngủ trưa bao lâu là đủ" in prompt and "Sức khỏe" in prompt
    assert "Lan: ngủ trưa 2 tiếng có sao không?" in prompt
    assert (
        'Từ cấm, không được dùng trong dòng mở đầu, nội dung, câu nhắc, câu hỏi, hashtag và bình luận ghim của bài viết: "thần dược".'
        in prompt
    )
    assert "nhắc lại ngắn gọn câu hỏi hoặc bình luận" in prompt
    assert prompt.endswith(articles.output_format("tra_loi_binh_luan")) and OUTPUT_FORMAT not in prompt
    # The video script's prompt is assembled exactly as before.
    video = build_script_prompt("Viết về [Chủ đề]", "gừng", ["thần dược"])
    assert video.endswith(OUTPUT_FORMAT) and "tiêu đề, chữ trên màn hình, lời đọc, caption và bình luận ghim" in video


def test_the_answer_becomes_hook_body_with_the_ai_reminder_then_question():
    written = articles.parse_output(
        answer(
            body=["Ý 1", "Ý 2"],
            note=NOTE,
            hashtags=["#a1", "b2", "#a1"],
            pinned_comment="Kể mình nghe nhé!",
            affiliates=["bình giữ nhiệt", " ", "ấm siêu tốc", "cốc sứ", "thừa"],
        ),
        "kien_thuc",
    )
    assert written.caption == f"Uống nước lạnh sau khi ăn có hại?\n\nÝ 1\nÝ 2\n{NOTE}\n\nBạn uống gì?"
    assert written.hashtags == ["#a1", "#b2"]
    assert written.pinned_comment == "Kể mình nghe nhé!"
    assert written.affiliates == ["bình giữ nhiệt", "ấm siêu tốc", "cốc sứ"]
    # No reminder and no fixed sentence either: the app adds nothing of its own.
    question = articles.parse_output(answer(body="bị bỏ qua"), "cau_hoi")
    assert question.caption == "Uống nước lạnh sau khi ăn có hại?\n\nBạn uống gì?"
    assert "tham khảo" not in articles.output_format("meo").split('"note"')[0].lower()
    with pytest.raises(articles.ScriptOutputError, match="thiếu nội dung"):
        articles.parse_output(answer(body=""), "meo")


def run_caption(factory, tmp_path, user, call, kind="meo", prompt="") -> tuple[Job, Article]:
    with factory() as db:
        group = db.scalar(select(KnowledgeTopic).order_by(KnowledgeTopic.id))
        group.article_prompt = prompt
        article = Article(knowledge_topic_id=group.id, kind=kind, topic="Ngâm chân nước gừng", created_by_id=user.id)
        db.add(article)
        db.flush()
        job = Job(article_id=article.id, kind="article_caption", status="running", created_by_id=user.id)
        db.add(job)
        db.commit()
    jobs.run_job(job.id, factory, DirectoryStorage(tmp_path / "storage"), call)
    with factory() as db:
        return job_row(factory, job.id), db.get(Article, article.id)


def test_the_caption_job_writes_the_caption_and_hashtags(committed, tmp_path):
    user = add_user(committed)
    prompts = []

    def call(prompt, label):
        prompts.append(prompt)
        return answer(pinned_comment="Kể mình nghe nhé!", affiliates=["chậu ngâm chân"])

    job, article = run_caption(committed, tmp_path, user, call, prompt="Bài [Dạng bài] về [Chủ đề]")
    assert (job.status, job.claude_calls) == ("done", 1)
    assert prompts[0].startswith("Bài Mẹo vặt về Ngâm chân nước gừng")
    assert article.caption.startswith("Uống nước lạnh sau khi ăn có hại?") and article.hashtags == ["#suckhoe"]
    assert (article.pinned_comment, article.affiliates) == ("Kể mình nghe nhé!", ["chậu ngâm chân"])
    # Its writer has no Shopee account, so nothing is searched.
    assert article.suggest_requested_at is None


def test_an_unusable_caption_answer_is_asked_once_more_then_fails(committed, tmp_path):
    user = add_user(committed)
    answers = iter(["không phải JSON", json.dumps({"hook": "x"})])
    job, article = run_caption(committed, tmp_path, user, lambda prompt, label: next(answers))
    assert (job.status, job.claude_calls) == ("failed", 2)
    assert job.error == "AI trả bài viết không đúng định dạng (thiếu câu hỏi kết bài), đã thử lại 1 lần"
    assert article.caption == ""


def test_the_default_article_prompt_is_editable_per_group(an, topic_id):
    path = f"/api/knowledge/topics/{topic_id}"
    saved = an.patch(path, json={"article_prompt": "Viết bài [Dạng bài]"}).json()
    topic = next(row for row in saved["topics"] if row["id"] == topic_id)
    assert topic["article_prompt"] == "Viết bài [Dạng bài]"
    assert saved["default_article_prompt"] == knowledge.default_article_prompt()
    # Saving the default text keeps the group on the default, so later default changes reach it.
    saved = an.patch(path, json={"article_prompt": knowledge.default_article_prompt()}).json()
    assert next(row for row in saved["topics"] if row["id"] == topic_id)["article_prompt"] == ""
