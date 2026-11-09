# 2026-11-09 — Quản lý người dùng keeps "no roles" but guards disabling and temporary passwords

Part 3 of the owner's (namtc) review of who may edit, delete and act on what, approved on 2026-11-09. "There is no
self-signup and there are no roles: every member can manage users" (2026-10-31) stays: no "chủ app" role was added.

- **Already true, kept**: nobody disables themself, and the last active member cannot be disabled.
- **Disabling asks for the member's name**, typed in the dialog, so a slip of the mouse cannot lock a teammate out.
- **A temporary password only for a disabled account** (owner's choice in chat, the recommended wording). This
  reverses "Hãy kích hoạt lại người dùng trước" of the 2026-10-31 user management: before, any member could reset an
  active teammate's password and sign in as them unnoticed. Recovering an account is now disable, set a temporary
  password, enable again, each step kept. The member's own password is changed with "Đổi mật khẩu", as before.
- **Who did it is kept and shown**: disabling, enabling and a temporary password go to the edit history (`user`,
  docs/decisions/2026-11-09-edit-history.md), never the password; the row shows the last one ("Thao tác gần nhất").
- **"Chuyển quyền sở hữu cho…" when disabling**, optional: the member's Pages, topic groups, plan ideas and templates
  go to a chosen active member, as "Nhận Page" (2026-11-03) gives a Page an owner. A moved Page drops the old
  owner's Shopee and TikTok accounts and semi-auto (their affiliate accounts stay theirs, 2026-11-03), for the new
  owner to set. Videos, articles and posts keep their maker. Without a choice nothing moves.
