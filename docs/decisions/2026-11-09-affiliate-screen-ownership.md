# 2026-11-09 — The Affiliate screen by owner: "Của tôi / Cả đội" and whose commission each product earns

From [docs/specs/affiliate-screen-ownership](../specs/affiliate-screen-ownership/brief.md), with the owner's answers
of 2026-11-09. Replaces, in [decisions.md](../decisions.md), the words "and Affiliate (out of the brief's scope) are
not filtered" of "2026-11-08 — Every list of the team's work starts on the member's own, 'Cả đội' one click away";
the rest of that entry, and "2026-11-08 — A member's own Pages and topic groups come first where one is picked",
stand and are what this follows.

- **"Video đã đăng" gets "Của tôi / Cả đội"** with that entry's rule: a video is mine when I posted it or it is
  live on a Page I own; it starts on "Của tôi" once I have one, else on "Cả đội". Every live post counts, so a video
  a teammate posted again on their Page stays mine. **A TikTok post belongs to the owner of its TikTok account**
  (`publications.affiliate_account_id`), as it has no Page.
- **"Nhóm của tôi" in the product filter** is the groups of the Pages I own and use (`routes_videos.my_topic_ids`),
  not `knowledge_topics.created_by_id`, which only decides who deletes a group.
- **The product list stays the team's**, by topic group; a product's saved link (`url`) is the member's who added
  it, so the list names them ("Người thêm").
- **Whose commission is said, never refused.** One function, `affiliate.commission_to`, makes the same choice as
  the comment's `link_for`: the Page's own Shopee account when it can make links (`page_account`: its owner's, with
  App ID and Secret, in use), else the product's saved link (the member who added it), else no link, and the product
  is left out of that Page's comment. Under a video's products the screen shows, per Page, every case that is not
  the member's own commission; attaching a teammate's product to a teammate's video stays allowed.
- **No banner for a team without a Shopee App ID**: the "Thêm sản phẩm" drawer already says so. The row's quick fill
  of stars and sales is offered for every Shopee draft under the rule, not only for one nobody has read. The
  approval rule (4.7 stars, 100 sales) is unchanged.
- **"Đã dán link tay"** (owner's request, 2026-11-09): without a Shopee App ID members paste their links on Facebook
  themselves. A video marked so (one switch per video, for all its posts) is never commented or edited by the app;
  its attached products are only a record, so the list still shows what it carries. Such links carry no sub ids, so
  their orders never reach a video in "Doanh thu".
- **"Video đã đăng" has three views** (owner's choice of all three): a table to scan, cards with the cover, and a list
  beside the open video, remembered per browser; the table is the default.
- **"Sản phẩm" is read by topic group, imported "for a Page" or a group** (owner's approval of the redesign): the
  groups sit on the left with the Pages that post them; a file or links go into one group, chosen directly or as the
  group a Page posts. Products stay one row per Shopee item in one group, shared by the team.
- **An import never replaces a teammate's link** (a bug found in the review: re-importing a teammate's item overwrote
  their affiliate link with the importer's while "Người thêm" still named them). Such rows are kept as they are and
  listed; the file is previewed first. One saved link per product stays the rule; a link per member, with the Page
  owner's used on their Page, is a possible later change, not made here.
- **The assistant (MCP) picks the member's own products** (owner's approval, in this PR): `list_affiliate_products`
  lists only the products the member added unless asked for the whole team, and `set_video_products` answers with
  whose commission each product earns, with a line for every case that is not the member's, so the assistant says
  so. Attaching a teammate's product stays allowed, as on the screen.
