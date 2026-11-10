# 2026-11-10 — A screen-by-screen review: quieter, shorter, one way for empty lists

Asked by the owner (namtc) on 2026-11-10 ("Làm cả A và B") after a review of every screen from
screenshots at desktop and phone width.

- **Names:** the menu's "Job logs" is "Nhật ký job", like its page (the 2026-11-10 menu decision
  listed the old name); "Quản lý người dùng" stays.
- **Empty lists** all use `EmptyState` (antd's small drawing and one line), and the main lists offer
  their action there, named apart from the page's own button ("Làm video đầu tiên"…, never containing the page button's name), so tests and
  screen readers never meet two buttons of one name.
- **Toolbars:** search, then "Của tôi / Cả đội", then filters, then sort. On a phone the Video list's
  five filters move behind "Bộ lọc (N)".
- **Quiet colour:** the members' status is a dot and a word; a KPI note that only says "not yet" is grey,
  not brand orange; settings group headings are grey text, not coloured tags; the content-type field
  is outlined, not filled grey.
- **Shorter screens:** the video page keeps "Chỉnh sửa"/"Xong" as a button and puts "Nhân bản", "Tạo bản
  TikTok" and "Xóa video" under "⋯"; a scene's three libraries are one "Chọn từ kho ▾"; the setup
  tab's section buttons are "Đi tới:" links; the render bar drops its summary line on a phone; the
  token permissions moved from Quản lý Page into "Thêm Fanpage"; a Page's dashboard says once why
  it has no numbers; an empty 30-day plan starts from one block with "Lập kế hoạch bằng AI".
- **Affiliate:** "Video đã đăng" keeps all three views (the owner's choice, 2026-11-09), now named
  ("Bảng", "Thẻ", "Chi tiết"); the second row of filters on both tabs is a segmented control, so it
  no longer looks like the page's tabs.
- **Plan wording and colours:** "verdict" is "đánh giá nhóm"; "Xong" (cyan) and "Đã đăng" (green) are
  no longer two greens.
