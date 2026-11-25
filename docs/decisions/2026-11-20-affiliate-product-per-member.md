# 2026-11-20: A Shopee product is one row per member and group, each with that member's own link

Replaces the line "One saved link per product stays the rule; a link per member ... is a possible later change" of
[2026-11-09-affiliate-screen-ownership](2026-11-09-affiliate-screen-ownership.md) and its "an import never replaces a
teammate's link ... such rows are kept as they are and listed" (the owner's request, 2026-11-20).

## Context

Nam imported Shopee Affiliate's file of 50 products into his group; 7 were already Looper's, and the preview showed
"Của người khác 7" and imported only 43. Cause: migration 0031 made a unique index on `shopee_item_id` for the whole
team, and the import, the pasted links and the worker's lookup all matched an item across members. A link in Nam's
file is made by Nam's Shopee account, so it earns Nam's commission; skipping it lost that.

## Decision

- The unique key is `(shopee_item_id, created_by_id, knowledge_topic_id)` (migration 0116; no data changes, the
  old key is stricter). A member has at most one row per item in a group, and may have the same item in several groups.
- Import and pasted links match only the member's own row in the chosen group: it is updated (mine), otherwise a
  new row is made, even when a teammate has the item (copy). A teammate's row is never read, changed or reused.
- The preview says new, mine (updated) and copy (added as my own, named with who has it); the answer counts `shared`.
- Comments keep using the product's own saved link (`affiliate.link_for`), so each row gives its owner's link.
- A Shopee search for a video's ideas reuses the searcher's own row, else the team's oldest one (it carries no link; each
  Page makes its own), so it adds no copies. The worker's "already listed" check is per member and group.
- The list shows both rows, told apart by "Người thêm".
