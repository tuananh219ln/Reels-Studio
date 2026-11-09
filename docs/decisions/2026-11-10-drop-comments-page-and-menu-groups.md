# 2026-11-10 — "Bình luận" is gone; the menu is four headed groups

Asked by the owner (namtc) on 2026-11-10 ("thôi bỏ mẹ đi. sắp xếp lại menu"). It reverses "\"Bình luận\" answers
visitors as the Page" (2026-11-03) for the page and its actions.

- **The "Bình luận" page goes**, with "Trả lời", "Ẩn", "Bỏ qua", "Tải bình luận mới" and the reading asked on opening
  it (`POST /api/comments/{id}/reply|hide|dismiss`, `/refresh`, `/freshen`). The worker sends nothing to Facebook for
  a visitor's comment any more; a reply or hide asked for before it went is never sent.
- **The worker still reads the comments** every 30 minutes for posts of the last 14 days, and `GET /api/comments` stays:
  Bài viết's "Trả lời bình luận" picks the comment it answers from them. Asked whether to drop that too, the owner
  chose "Chỉ bỏ trang". No migration: `page_comments` keeps its reply and hide columns, unused.
- **The menu** is four groups under headings that do not fold, in the order of the work: Tạo nội dung (Video, Bài
  viết), Đăng và kiếm tiền (Bài đăng, Quản lý Page, Affiliate), Tài nguyên (Kho kiến thức, Kho tư liệu, Thư viện
  nhạc), Quản trị (Quản lý người dùng, Job logs, Cài đặt). "Đăng bài" and "Cài đặt" are no longer groups of one;
  the settings page and its menu item are both named "Cài đặt" (it was "Cấu hình"). Chosen by the owner from three
  drawn options (headed groups, a flat list, folding groups).
