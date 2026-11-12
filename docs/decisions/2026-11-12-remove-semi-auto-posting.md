# 2026-11-12 — "Bán tự động" is removed

The owner (namtc), 2026-11-12, after the switch was explained to him: remove the feature. It reverses
[2026-11-08 — Semi-automatic posting](2026-11-08-semi-auto-posting.md), which stays as history.

- **What goes:** the worker's round (`auto_runs.py`), `/api/auto-runs`, the Page card's switch, preparing time,
  TikTok account and "Bản TikTok riêng", the plan's "Bán tự động hôm nay" strip and the MCP tool "Đọc video chờ
  duyệt". Migration 0079 drops `auto_runs` and the four `fanpages` columns; its downgrade brings back the empty
  table and the columns, not the runs. Videos the round made, and posts approved from it, stay as ordinary videos
  and posts.
- **What stays:** a Page's queue ("Thêm vào hàng chờ" and its posting times) and its schedule, which never depended
  on it; making a video from a plan idea by hand ("Tạo video" in "Hôm nay") or through MCP.
