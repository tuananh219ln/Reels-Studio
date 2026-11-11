# 2026-11-11 — Tags on the "Kho tư liệu": lowercase without accents, independent of folders; the Già photos tagged once by name

Brief [docs/specs/media-tags](../specs/media-tags/brief.md), made on the same branch as the folders
([2026-11-11-media-folders](2026-11-11-media-folders.md)), as the owner chose on 2026-11-11. Matching a scene to one
of the 42 Già Mà Khỏe photos needed a map kept outside the app (`MANIFEST.md`), as file names do not say the room, the
joint or whether a photo opens or closes a video. The tags bring that into the library, for the web and for MCP.

- **A tag is kept one way** (`media_items.tags`, JSONB, migration 0077, `[]` by default): lowercase, Vietnamese
  without accents, words joined with "-". What is typed is cleaned rather than refused ("Xoay Cổ", " xoay-co " and
  "XOAY-CO" are all `xoay-co`), each tag once per item; only a tag that is empty once cleaned is refused, as are tags
  over 50 characters or more than 30 on one item ([media_tags.py](../../api/src/reels_api/media_tags.py)). Without
  accents so the assistant and a member typing on a phone find the same tag.
- **Tags and folders are independent.** A folder says where an item is kept (one per item, a topic group's view), its
  tags what it shows (any number). Moving, renaming or deleting a folder never touches tags; tags never change a
  folder.
- **Filtering asks for every tag chosen** (`tags @> [...]`, a GIN index), and meets the folder, kind and search. The
  search (`q` on the web, `query` over MCP) matches tags as well as names and folders, cleaned the same way
  ("phòng ngủ" finds `phong-ngu`).
- **Editing**: an item's whole set (`PATCH /api/media/{id}` with `tags`), "Thêm thẻ" and "Gỡ thẻ" on a chosen batch
  (`POST /api/media/tags`), and tags given to everything added at once (the upload form and pasted links). Anyone may
  tag, as anyone may move an item. The web suggests the tags already in the library first, with their counts. No new
  MCP write tool: `list_media` gains `tags` and returns each item's tags and the library's tags with their counts.
- **The Già photos are tagged once, by file name**, from the brief's table: `python -m reels_api seed-media-tags`
  (`--dry-run` to read only), run by hand by the owner, as production is changed only by a person. It adds the table's
  tags to the items of that name (the extension aside) and keeps any tag a member gave them, so running it again adds
  nothing; it logs every change, every item not in the table and every name of the table not found. It is not a
  migration: the photos are operating data of one Page, not of every install, and a fresh database has none of them.
- Not done: suggesting photos for a scene from its content, and tags written by AI (the brief leaves both for later,
  once the tags have settled).
