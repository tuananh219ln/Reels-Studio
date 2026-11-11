# 2026-11-11 — One "Kho tư liệu" with folders; a topic group links one folder; ids never change when items move

Brief [docs/specs/media-library-upgrade](../specs/media-library-upgrade/brief.md), from loading the Già Mà Khỏe
picture bank on 2026-11-11: splitting it into three folders meant uploading everything again and deleting the old
copies, which changed every `media id` (5–24 became 25–44) and broke the ids written in the MCP render notes.

- **One library for the team, folders are labels.** The library stays `media_items` with its `folder` text, as on
  2026-11-07; there is no folder table and no library per topic group. A photo two groups use sits once, and is fixed
  once. A folder exists while an item carries it, or while a group links it (listed with a count of 0).
- **Moving keeps the id and the file.** "Chuyển thư mục" (one item, or the items chosen with their boxes,
  `POST /api/media/move`) changes only `folder`; renaming a folder (`POST /api/media/folders/rename`) and deleting it
  (`POST /api/media/folders/clear`) change only labels too. A scene's copy and what the assistant knows by id still
  hold. A batch with an item that no longer exists moves nothing.
- **A folder includes its subfolders**, as the filter already did: renaming "Gia" renames "Gia/Goi khop" with it,
  deleting "Gia" puts the subfolders' items in "Không thư mục" too. Renaming into a folder that exists merges them.
- **Deleting a folder deletes no item**: its items go to "Không thư mục", after a dialog that says how many and which
  group is unlinked. Deleting an item is unchanged (its maker only; scenes keep their copy).
- **Anyone renames, moves or deletes a folder**, as anyone could already change an item's folder: the library is the
  team's, and no item is lost by it.
- **A group's "Tư liệu"** (`knowledge_topics.media_folder`, migration 0076; null: none linked) shows the library on
  the group's folder (with its subfolders), uploads into it, and opens `/media?folder=…`. Linking is an edit of the
  group, so "Cho cả đội sửa" off keeps it to the group's maker. A folder belongs to at most one group (a unique
  column; the app names the group that has it).
- **Renaming a folder takes the group's link along** (chosen over refusing the rename): the link names the folder,
  so after a rename the group still shows the same photos. A subfolder linked by a group follows the same way. The
  rename is refused, naming both groups, only when two groups would end up on one folder (renaming a linked folder
  onto another group's). Deleting a folder unlinks the group, which then offers "Liên kết thư mục" again. Both are
  written in the group's "Lịch sử" as "Thư mục tư liệu".
- **Not done here:** a group linking a prefix (all of "Già - …"). Today the same comes free from subfolders: name the
  folders "Già/Gối khớp", "Già/Giấc ngủ"… and link "Già". Renaming the three existing folders that way is the
  member's choice, not a migration.
- MCP is unchanged: `list_media` already returns the folders with their counts; each now also carries the group that
  links it (`topic_id`, `topic`).
