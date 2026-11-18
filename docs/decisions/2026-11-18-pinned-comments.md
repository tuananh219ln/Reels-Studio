# 2026-11-18 — Each plan script carries 5 pinned comments, written under the post by the worker

From the spec "SPEC — Bình luận ghim cho kịch bản bài viết" (v1.1), asked by tuananh219ln. The spec's "scripts" are the
article plan's `article_plan_slots`; its "Tạo bài" screen is the article page opened by "Tạo bài từ ô này". Built as
the spec orders: data and import, the editor, writing under the post, pinning, bulk AI.

- **Comments live on the script** (`pinned_comments`, `pin_index`, `comments_source`, `comments_edited`,
  `comments_updated_at`, migration 0103), so they follow the script when it is dragged to another slot or the Backlog
  and go when it is deleted. `comments_edited` is set by any manual save and stops the bulk AI from overwriting.
- **A script's text is 20–1000 characters** (spec 3.2); an empty or too long one is a row error, a label outside the two
  sets, fewer than 5 comments and a promise such as "chữa khỏi" are warnings. `pin_index` out of range goes to 0.
  The two label sets are chosen by the article kind: "Cảnh báo / nhắc nhở" uses the warning set, every other kind the
  food set (the spec's "bài có nội dung nên hạn chế" cannot be told from the kind, so it is not handled).
- **A CSV file's `pin_index` counts the columns** `cmt_1..cmt_5`, so an empty cell before it does not shift the pin.
- **Import never replaces a slot an article was made from.** A row for such a slot is *Bỏ qua (đã tạo bài / đã đăng)*
  in the preview and is not saved. This narrows 2026-11-15's rule, where the used script moved to the Backlog and the
  new one took its place; a slot without an article behaves as before (`conflict` modes unchanged).
- **The AI is a job per script** (`slot_comments`, `jobs.plan_slot_id` and `jobs.params`): "Tạo bình luận ghim" queues one
  for each script in its scope, a member's "Tạo lại bằng AI" or ↻ (one comment, `params.index`) queues one that
  overwrites. Answers are asked again up to 3 times when the format is wrong or a comment promises a cure. The prompt
  is the spec's template and reads the Page name and a new plan field `audience` ("Nhóm đối tượng" in Thiết lập; the
  plan had no such field). Opening a script's article with no comments asks the AI once.
- **Writing under the post is not a job and never sleeps** (as `post_comments.py`): once the post is live the worker
  copies the script's comments into `post_comments` (so later edits never change what was posted) and writes the
  pinned one 30–60 s later, the others 20–40 s apart, each when its `due_at` comes. The copy is made when the post is
  live, so a script edited after "Đăng" but before a scheduled time uses its newest comments; a post already live for
  more than 24 h gets none made. The switch "Đăng kèm bình luận" is `articles.post_comments_enabled`, on by default.
  This is separate from the article's own affiliate comment (`articles.pinned_comment`, `post_comments.py`), which is
  unchanged.
- **Failures:** a passing one (no answer, 5xx, rate limit) is tried again after 1, 3 and 10 minutes, then the comment
  is `failed` and the next goes on; a permission or token error fails the comment and the rest at once, without retry;
  a post that no longer exists marks the rest `skipped`. A comment with a `fb_comment_id` is never written again; an
  attempt is counted before Facebook is asked and a later one looks for the Page's comment with the same text first, so
  a lost answer does not write it twice. "Đăng lại bình luận lỗi" on the post resets the failed ones.
- **Pinning is by hand.** Spike result: not run, because the Graph API cannot be reached from development (real
  Facebook costs and risk, AGENTS.md) and this repo's `post_comments.py` already records that the API cannot pin a
  comment. So the pinned comment is left `need_manual_pin` ("Chờ ghim tay", with a link to the post) until a member
  presses "Đã ghim" (`pinned`). If a call turns up, only `slot_comments.attempt` changes.
- **Not done from the spec:** the "Nhật ký job" lines (the writing is not a job; each comment's state and error are
  on the post instead), and the "bài có nội dung nên hạn chế" label set.
