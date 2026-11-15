# 2026-11-15 — The video page's header folds, and the line between the scenes and the panel is dragged

Asked by namtc, 2026-11-15: "header này cho đóng mở được … phần nội dung cho kéo qua kéo lại để tùy chọn hiển thị",
approved from a sketch in the same session.

- **The fixed header folds to one row** (title and actions) with a ⌃/⌄ button at the end of that row. Folded, the
  progress line, the QC chip and the render's state are hidden (kept mounted), and a pill beside the title still says
  what needs a look: the job running or waiting, the last job that failed, or the count of reasons that block a
  render. Nothing when all is well; a click on it unfolds the header. The worker strip planned for every page is not
  part of the fold.
- **The scenes and the side panel are split by a line the member drags** (`ResizableColumns`). The default stays
  60/40 ([video editor spec](2026-11-14-video-editor-spec.md)); a double click, or Enter, goes back to it; ← → move it
  by 2%. The scenes keep at least 420 px and the panel at least 440 px (the drawer's width). Below 1100 px nothing
  changes: the panel is still a drawer. This relaxes "60% and 40%" of that decision to "60/40 until the member drags
  it"; it does not bring back the half-and-half split.
- **Kept in this browser, per member** (`video-header:<id>`, `video-split:<id>`), like the open groups of "Thiết
  lập": a layout preference, not data, so it is not stored in the database and does not follow the member to
  another computer.
- **The panel lays its tabs out by its own width** (a CSS container): from 720 px the groups of "Thiết lập" and the
  two blocks of "Bình luận & Sản phẩm" sit in two columns, and the "Đăng bài" card's MP4 stops at 260 px wide with a
  post's buttons back beside its name. Narrower, everything is as before. The scene cards already change by their own
  width (photo beside the fields from 700 px).

No api, data or render change.
