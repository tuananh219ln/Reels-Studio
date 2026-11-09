# 2026-11-09 — Cấu hình is split into "Của tôi" and "Chung cả nhóm"; the shared settings show who changed them

Asked and approved by the owner (namtc) on 2026-11-09, on a drawing reviewed in chat, together with Part 6 of the
review of who may edit what: "phần mô hình AI, nguồn tư liệu là dùng chung hết … thêm đã sửa hoặc cập nhật, hoặc thêm
log vào". The settings stay shared and editable by every member, as before ("there are no roles", 2026-10-31); no
member has keys or a model of their own.

- **Two groups of tabs** on Cấu hình: **Của tôi** (Thiết lập mặc định, Tài khoản affiliate, Kết nối MCP)
  and **Chung cả nhóm** (Mô hình AI, Nguồn tư liệu, Mẫu dựng, Máy render). One tab per job, placed where most of it
  belongs: Mẫu dựng is the team's library, with the member's own "Video mới của tôi tự áp mẫu" as its one card tagged
  "Của tôi"; Máy render is shared, since a free machine takes the oldest waiting job whoever's it is
  (`render_nodes.claim`), and only its adder removes a machine (2026-11-09, delete by maker).
- **Kết nối ChatGPT / Claude moves into Cấu hình, renamed "Kết nối MCP"** (`/settings/mcp`), as it also connects
  Claude Code and Muse; the menu's own item goes, and `/chatgpt` and `/api/mcp/manage` lead there.
- **No tag beside a tab's title and no banner saying whose it is**: the group in the list says it. This drops the
  "Của tôi (theo người dùng)" tag and line of Thiết lập mặc định (2026-11-09, member defaults).
- **Who changed a shared setting is shown and kept**: each card of a shared tab ends with "Sửa lần cuối bởi <tên>,
  <giờ VN>", and the tab's "Lịch sử" lists every change from the edit history (2026-11-09, edit history): the model in
  use, each provider's base URL, model and key, the AI image provider and style, "Tự tìm ảnh", the sources on and off,
  their keys, render machines on or off and added or removed, and templates made, renamed or deleted.
- **A key is never logged or shown**: only "…" and its last four characters (none for a key under 12 characters), so
  the history says "đã thêm / đã đổi khoá …k3P1" or "đã xoá khoá". The .env keys of the server are not logged.
- Nothing here is put back from the log: a setting is changed again on its card, as keys could not be restored anyway.
