# 2026-11-11 — Folders of the "Kho tư liệu" show as a tree; choosing a node filters on whole parts of the path

Brief [docs/specs/media-folder-tree](../specs/media-folder-tree/brief.md). Once the Già photos were renamed into
`Gia/Goi khop`, `Gia/Giac ngu`… and the group linked `Gia` (as [2026-11-11-media-folders](2026-11-11-media-folders.md)
suggested), every folder list still showed eight unrelated lines: the parent `Gia` was nowhere to be seen.

- **The tree is only how the folders are shown.** A folder stays the path kept on each item (`media_items.folder`);
  there is no folder table, no migration and no change to the api or MCP. The web builds the tree from the flat list
  `GET /api/media` already returns ([folderTree.ts](../../web/src/lib/folderTree.ts)): each part before a "/" is a
  parent, at any depth. A parent no item sits right in is still a node.
- **Counts**: a folder with nothing below it shows its own items; a parent shows its own and everything below it.
- **Choosing a node filters on whole parts of the path**, as the api's folder filter already did: `Gia` shows `Gia`
  and `Gia/…` (items right in `Gia` too), never `Gian/…`; `Gia/Lung` shows `Gia/Lung` and `Gia/Lung/…`. It meets the
  tags, kind and search as before.
- **Every parent starts open**, and stays as the member leaves it while the list is open; chosen over opening only
  the parents of what matches, as the library has few folders and seeing them all is what was asked for.
- **The same tree everywhere a folder is chosen**: the filter on `/media`, the scene's "Kho tư liệu" dialog, the
  upload form's folder, "Chuyển thư mục" and a group's "Liên kết thư mục", where a parent links as before (the group
  shows everything below it). A node reads its own name (`Lung`), the box once chosen the whole path (`Gia/Lung`).
  "Đổi tên thư mục" keeps a text box, as it names the folder rather than picking one.
- **A parent has the folder actions too**: with `Gia` chosen, "Đổi tên thư mục" and "Xoá thư mục" act on the whole
  branch (they already took subfolders along); before, they showed only for a folder an item sits right in.
