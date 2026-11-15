# 2026-11-15 — A Page has one 30-day plan of article scripts, filled by hand or from a file

Round 3 ("Đợt 3 — Kế hoạch") of the spec "Đặc tả: Kế hoạch 30 ngày cho Bài viết" (by Looper), asked by tuananh219ln.
This part (3a) is the plan, its Backlog and the file import; "Tạo bằng AI", "Viết lại AI" and the 3-step "Tạo bài
viết" dialog follow in 3b. The spec's open questions were answered with these defaults, for the owner to change:

- **One plan per Page** (`article_plans.fanpage_id` unique), so two plans never overlap on a Page; "Tạo 30 ngày tiếp"
  (round 4) will move it on. Unlike the video plan, which belongs to a topic group, the article plan belongs to a
  Page, as the spec asks: its slots are the Page's posting times.
- **Its Backlog is its own**, not shared with the video plans (a video idea and an article script do not hold the
  same fields).
- **Only the Page's owner changes it** (settings, scripts, files, "Tạo bài từ ô này"), as only they post to the Page
  (2026-11-09); everyone reads it.
- **The file preview is not stored**: as for the video plan's file, the preview is read and sent back by "Lưu kế
  hoạch", where every row is checked again; the spec's `plan_imports` table is not built, and "Tải N dòng lỗi" is made
  in the browser from the preview.
- **"format" is the article's kind** ("Dạng bài": its code, its label or a short name such as "Mẹo", "Danh sách",
  "Câu hỏi tương tác"); a name the app has no kind for ("Thử thách") is an error, as the spec's sample shows.
  "topic_group" is a topic group of Kho kiến thức, by name.
- **"Gần giống bài đăng"** is a warning when 80 % of a hook's words (without accents or case) are those of an
  article posted or scheduled on the Page in the last 60 days.
- **A slot is "Đã dùng" while its article exists**: deleting the article frees it ("Chưa dùng"); a script with an
  article cannot be deleted or skipped, and goes to the Backlog instead of being overwritten.
- **Fewer posts a day** moves the dropped slots' scripts to the Backlog, never deletes them.
- The article made from a script gets its caption (hook, body, call to comment), hashtags, kind, group and photo
  brief (as its photo search words and AI prompt); the script's photo links are added to it one by one, and "Đăng"
  starts on the plan's Page at the slot's time while that time is ahead.
