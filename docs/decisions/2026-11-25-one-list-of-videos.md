# 2026-11-25 — One list of videos: the same table, cells, card and toolbar on every screen

Asked by the owner after a screen review (the Video list, a group's "Video" tab, a Page's "Nội dung", Bài đăng and
Affiliate each drew their lists their own way). Done in the same pull request as [the stats page](2026-11-25-stats-page.md).

- **Parts, not a rewrite** ([web/src/components/videoList](../../web/src/components/videoList/)): `VideoTable`, the columns
  after the title (`useVideoColumns`: Trạng thái, Số liệu, Tạo, and ID), `VideoCard`, `videoDetails` (the grey line under a
  title), `VideoSearch` and `ViewToggle`. A screen keeps what is its own (Bài đăng's platform cells, Affiliate's products and
  comments, a Page's Facebook number columns) and gives only those columns.
- **The row's "⋮" menu is the last column, pinned to the right, with no heading**, on every table. It was first on the Video
  list ("Thao tác"), last elsewhere, and inside the title cell on Affiliate.
- **"Số liệu" is the Video list's short form everywhere**: "N view", then "48h: x×, y% share"; a dash before the first
  reading. The group tab's "View Facebook N, tool 48h N, Share 48h N, share/view 48h N" (four dashes for an unposted video) is gone.
- **"Thẻ | Bảng"** is one switch with one remembered choice (`reels-studio.video-view`) for the Video list and a group's tab.
  What each kept before (`reels-studio.videos-view`: grid/list, `topic-videos-view`: table/list) is read once as the starting
  point, so no one loses it. A page of its own opens on cards, a group's tab on the table, until chosen.
- **The group tab's cards are the Video list's cards** (no second card), without the group line.
- **Winner** shows the same everywhere a video has its 48-hour number: the gold flag and "Tạo 3 biến thể" in the Trạng thái
  cell and on the card; the multiple is orange and bold from 10× in Số liệu.
- **"Cột" is on both video tables**, with "ID" off by default (the group tab used to show it always).
- **Dropped**: the extra "Đã đăng / Đã hẹn giờ" word beside the status on the Video list (the status and the platform icons
  already say it) and the "Chủ đề: …" line, which the one grey line now carries when the title does not say the topic.
- **Sizes**: "middle" for a page's own list, "small" inside a card; 50 rows a page everywhere (a group's tab had 20).
