# 2026-11-25 — Only the member who made a topic group adds products to it

Asked by the owner ("nhóm của ai thì người đó mới được thêm"). **Narrows**
[2026-11-20-affiliate-product-per-member](2026-11-20-affiliate-product-per-member.md): that entry let every member add
their own row of an item into any group, with their own link. A member now adds rows only to the groups they made.

- **"Owner" is `knowledge_topics.created_by_id`** (the member who made the group), not the owner of the Page that posts
  it. A group whose maker is unknown (the one the first migration made) is open to everyone: nobody to protect.
- **Enforced in the api**, so the screen, the pasted links, the Shopee file and anything else that calls it are refused
  with 403 "Chỉ người tạo nhóm “…” mới thêm được sản phẩm vào nhóm này": `POST /affiliate-products`, `/links`,
  `/import` and `/import/preview` (a row that would be added, `new` or `copy`), pasting links on a video or article
  (only when the link would make a new row), and moving a product to another group (`PUT /{id}`). The worker's Shopee
  search for a video's ideas adds a row only for the group's maker; for anyone else it offers the products the team
  already lists. `GET /options` tells each group's `can_add`.
- **Existing rows stay**, a teammate's rows included. Their owners can still edit, approve and delete them, update
  them by importing a file (a row that is `mine` is updated, never added), and use them on videos.
- **Using a group is unchanged**: anyone may attach any approved product to a video, and Custom Link only writes the
  links of the member's own products.
- **Screen**: "Thêm sản phẩm" and "Nhập file" are disabled (with the reason on hover) when the open group is not the
  member's; the add drawer lists only the groups the member may add to, and the Pages that post them.
