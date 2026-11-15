# 2026-11-15 — An article's post is tried again by itself after a passing failure; Facebook still does the scheduling

Round 2 ("Đợt 2 — Lên lịch") of the spec "Đặc tả: Kế hoạch 30 ngày cho Bài viết" (by Looper), asked by tuananh219ln,
who chose on 2026-11-15 between the options below.

- **Facebook's own scheduling stays** ("Scheduling uses Facebook's own scheduling; the app has no posting timer",
  2026-10-31). The spec's `publish_scheduled` job, posting each article from the app once its time comes, is not
  built: a scheduled article is sent to Facebook when "Đăng" is pressed, as before, and Facebook publishes it. So a
  logo or caption changed after that does not reach the scheduled post, and changing its time is done in Meta Business
  Suite, as for reels. "Đã hẹn giờ" and "Đăng lỗi" already existed; the list gains "Lịch đăng".
- **A passing failure is tried again by itself**, 1, 5 then 15 minutes after each failure, then the article shows
  "Đăng lỗi". This narrows "a failed job is never re-run automatically; members press Thử lại" for the article
  `publish` job only: it costs no AI money, and "never posted twice" (2026-11-06) still guards every try. Passing
  means no answer or an unreadable one, Facebook's 5xx or its rate limit, and "Facebook may still be posting the
  last try"; a refusal (the post, the token, a missing permission) or a time already too close shows "Đăng lỗi" at
  once. A job killed by a dying worker still waits for "Thử lại".
- **Within 30 minutes a try only looks for the post.** After an answer that proves nothing (a 5xx, a lost answer)
  the app posts again only after 30 minutes without finding it (2026-11-06), and the three tries end 21 minutes after
  the first failure. They find a post that did go out; one that did not ends "Đăng lỗi" with the advice to wait
  30 minutes and press "Thử lại". The spec's timings are kept rather than the 30-minute rule loosened.
- **"Báo cho người tạo" is in the app**: a red count of the member's own "Đăng lỗi" articles on "Bài viết" in the
  menu (read about once a minute, `GET /api/articles/attention`) and a list of them above the articles. There is no
  email or push.
- "Đăng" again or "Thử lại" starts the three tries over.
