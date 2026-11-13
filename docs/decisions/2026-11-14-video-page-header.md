# 2026-11-14 — The video page: a fixed header in place of the bottom bar, a menu rail, a 440 px side panel

The second of three PRs for "Đặc tả tối ưu giao diện trang Video – Reels Studio" (asked by tuananh219ln; the first is
[the side tabs](2026-11-14-video-inspector-tabs.md)).

- **The render bar at the bottom of the screen is gone** (owner's choice in the same session): it covered the last
  scene and kept "Đăng bài" apart from "Render". Everything it held moves into a header fixed at the top of the page:
  "Xem trước", "Render"/"Render lại", "Tạo ảnh AI cho cảnh thiếu" and the Google one on the first row with the title
  and the actions; the blocking count with its jump, the running job with "Hủy", how the MP4 stands and the summary on
  the second row, after the progress line. The header keeps `data-testid="render-bar"`, so what tests read in the bar
  is found in the same place.
- **A QC chip** beside the progress line ("QC: đạt" / "QC: N mục chưa đạt") opens "Đăng bài", where the tiles are.
- **The topic line, "Loại nội dung" and the kind tags are not in the fixed header**: they are read once, so they sit
  under it and scroll away. The spec's "into the ⋮ menu or a chip" was not taken: the type is a field typed into, and
  a menu would hide it.
- **The side panel is 440 px from 1100 px wide**, stuck under the header (its height measured, since it wraps) and
  scrolling on its own; narrower, a drawer from the right opened by "Thiết lập / Đăng bài", kept mounted while closed.
  It was a 9/24 or 13/24 column from Ant Design's xl (1200 px) before.
- **On a video's page the menu is a 56 px rail of icons**, widened by "Mở rộng menu" (in memory only, not stored). A
  click on a rail icon navigates through the menu's own click, since the link text is hidden. "Ẩn menu" is not
  offered there and a menu hidden elsewhere shows as the rail: its floating "Hiện menu" would sit on the header.

No api, data or render change.
