# 2026-11-25 — A health group's medical reminder moves from the caption to the last pinned comment

Asked by the owner (spec "Chuyển câu lưu ý y khoa từ thân bài xuống bình luận"). **This reverses part of
[2026-11-07](../decisions.md)**, where the fixed line "Tham khảo, không thay thế tư vấn bác sĩ." was dropped because it read as
machine-made, the AI wrote its own reminder in the caption and the app added nothing. The owner chose to reverse it: the
reminder is now a fixed sentence again, but it is written under the post, so the caption stays short and ends on its
question. Everything else of 2026-11-07 (the pinned comment, product ideas) stands.

- **Per group** (`knowledge_topics`, migration 0126): `medical_disclaimer_enabled` (on for groups whose name has "khỏe",
  off for the rest), `medical_disclaimer_text` (empty: the default sentence, `disclaimer.DEFAULT_TEXT`; changed in
  "Câu lưu ý y khoa" on the group's page, with history) and `medical_disclaimer_position` (`last_comment`, the default, or
  `caption`, which brings back the 2026-11-07 behaviour: the AI's own line in the caption, nothing added).
- **The caption has none.** With `last_comment` the AI prompt drops the `note` field and says the app posts the reminder
  under the post. `disclaimer.strip` (twin in the web, `stripMedicalDisclaimer`) takes it out of a caption when the post text
  and the preview are built: a paragraph that opens with `(*)`, or one under 300 characters with "tham khảo" and ("bác sĩ",
  "y khoa" or "chuyên gia"). The first paragraph, the hook, only goes when it opens with `(*)`. The stored caption is never
  changed, so old drafts need no migration. `checks.warnings` warns (never blocks) when "bác sĩ" or "y khoa" is left in the
  last two paragraphs.
- **The worker writes it, the database never holds it.** At the end of the last comment in posting order (the pinned
  comment first, the others in script order), after a blank line, when the comment is written (`slot_comments.text_to_write`);
  a comment already holding a reminder gets no second one. No sixth comment is made, except when the two texts together are
  over Facebook's 8,000 characters: then the reminder follows as a comment of its own. An article with no comments, or with
  "Đăng kèm bình luận" off, gets one comment holding only the reminder (a `post_comments` row of type `disclaimer`, text empty,
  the sentence read from the group when written). The switch off does not stop the reminder; turn the group's switch off for that.
- **Scripts.** An imported script's body loses the reminder at the preview (badge "Đã bỏ câu lưu ý y khoa") and an article
  made from a script gets a clean caption. Migration 0126 cleaned the body of the scripts of those groups that no article was
  made from; posted articles and drafts are left alone.
- **Screens and API.** "Bình luận ghim" shows a grey "+ Tự thêm khi đăng" line under the comment that is last (it follows a
  drag); the Facebook preview shows the cleaned caption and the last comment with the reminder. `get_article` (web and MCP)
  returns `post_text`, `post_comments` and `disclaimer`.
- **Not done:** Reels/video captions (the spec leaves them for later); the optional one-off script that cleans the captions of
  draft and scheduled articles (the caption is cleaned when posted, so nothing depends on it).
