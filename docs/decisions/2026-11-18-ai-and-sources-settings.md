# 2026-11-18 — "Mô hình AI" and "Nguồn tư liệu" become one settings tab in groups that open and close

Asked by the owner (namtc): one menu for the two, each kind of setting in its own group, collapsible to keep the page
short. Revises the tab list of 2026-11-09 "settings-mine-and-shared" (the mine/shared split itself stays).

- **One tab, "AI và nguồn tư liệu"** (`/settings/ai`), in "Chung cả nhóm". The old `/settings/sources` redirects
  there, so links and bookmarks keep working. Every message that named either page now says "Cài đặt › AI và nguồn tư
  liệu".
- **Four groups** (antd Collapse): "AI viết kịch bản", "Giọng đọc" (ElevenLabs, Gemini, VieNeu and their backup
  keys, side by side: the narration keys used to be split over both pages), "Ảnh AI", "Kho ảnh và video miễn phí".
  All open the first time; the ones a member closes stay closed in that browser (localStorage, only a convenience).
- **History stays per card** (`settings_ai` 1/2, `settings_sources` 1/2, unchanged): each group's header has the
  "Lịch sử" of its own card instead of one per page, so nothing in the edit log moves.
- **The settings tab list wraps its hints** inside its 240 px column: a long hint on one line pushed the list over the
  page beside it (reported on production, 2026-11-18).
