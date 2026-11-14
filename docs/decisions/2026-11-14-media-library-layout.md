# 2026-11-14 — "Kho tư liệu" page: folder tree beside the grid, upload in a drawer, small tiles with their numbers

The page showed the whole upload form (drop zone, link search, a paste box) above the library, so the pictures started
below the first screen, and each card was a large tile with its name, folder and tags but no numbers. Nothing here
changes what the library keeps (folders and tags stay labels, see [folders](2026-11-11-media-folders.md),
[tags](2026-11-11-media-tags.md), [tree](2026-11-11-media-folder-tree.md)); only how it is shown and handled.

- **The library comes first.** "Thêm tư liệu" (top right) opens the upload form unchanged in a drawer; the folder
  filter becomes a tree beside the grid on wide screens (a select on narrow ones, in a scene's picker and in a group's
  tab). A group's tab and the picker keep their form and one grid.
- **Tiles are small and carry their numbers**: the picture, its name, "1080×1920 · 820 KB" (photo) or "0:12 · 8,1 MB"
  (clip), and its tags on one line; S/M/L sizes, kept per browser. Small photos (shorter side under 720 px) and photos
  that are not vertical are marked, since they are cropped or look soft in a 1080×1920 video. The box and the actions
  show on hover, always when something is chosen or on touch screens.
- **Groups**: "Theo thư mục" (the default on the page) lays the tiles out as one collapsible section per folder, with
  a box choosing a whole section; "Lưới" shows them as one. The choice is in the address (`view=grid`).
- **A tile opens its details** (picture or playable clip, pixels, size, length, folder, tags, who and when in Vietnam
  time, the source link, whether the shape fits 9:16) with move, tags, download and delete.
- **Drag to move**: a tile (or the chosen ones when it is among them) dropped on a folder of the tree moves it, the
  same `POST /api/media/move` as "Chuyển thư mục": the id and the file stay.
- **Numbers are read from the file when listing**, not stored: no migration, no backfill, and the library's existing
  items have them at once. A clip's pixels are not read (ffprobe per item would slow the list); its length was already
  kept.
- Not done: listing past 500 items (the api's cap stays; the page says so), and filtering on items with no folder.
