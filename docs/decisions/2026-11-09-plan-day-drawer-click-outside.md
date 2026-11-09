# 2026-11-09 — A plan day's drawer closes on a press outside it, still without a mask

Part 6 of [docs/specs/per-user-settings-ownership](../specs/per-user-settings-ownership/brief.md): the owner reported
that the day drawer of "Kế hoạch 30 ngày" closed only with its ×. The brief asked for Ant Design's usual mask that
closes on a press. That would reverse a point of "2026-11-08 — A plan day opens in a drawer" in
[decisions.md](../decisions.md) ("the drawer has no mask, so the page keeps its scroll and the Backlog can still be
dragged from"), which the brief did not know of: a mask covers the Backlog and the calendar while the drawer is open.

- **Done without reversing it**: a press anywhere on the page outside the drawer closes it, as a mask would, but no
  mask is drawn ([PlanTab.tsx](../../web/src/components/plan/PlanTab.tsx) `useClickOutsideToClose`). A press on
  another day switches the drawer to it, and one on the Backlog (to drag from it), on the drawer's own pop-ups
  (menus, confirmations) or on the "Sửa ý tưởng" form leaves it open, so an idea being edited is never closed under
  the member. The × works as before.
- Closing either way keeps the page's scroll, the filters and the chosen day, as "Bổ sung 3" asked.
- If the owner wants the dimmed mask after all, it is one prop (`mask`) on the drawer; the Backlog then cannot be
  dragged from while a day is open. That choice is left to them.
