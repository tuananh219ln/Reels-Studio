# 2026-11-09 — A plan day's drawer has a mask and closes on a press outside it

Part 6 of [docs/specs/per-user-settings-ownership](../specs/per-user-settings-ownership/brief.md): the owner reported
that the day drawer of "Kế hoạch 30 ngày" closed only with its ×. Replaces, in "2026-11-08 — A plan day opens in a
drawer" of [decisions.md](../decisions.md), "the drawer has no mask, so the page keeps its scroll and the Backlog can
still be dragged from".

- The conflict was put to the owner (namtc) on 2026-11-09, with a first version that closed on an outside press
  without a mask; the owner chose the mask ("Thêm lớp mờ").
- **Ant Design's usual behaviour**: the drawer opens over a mask, and a press on the mask closes it, like its ×
  (`mask`, `maskClosable` in [PlanTab.tsx](../../web/src/components/plan/PlanTab.tsx)).
- Closing either way keeps the page's scroll, the filters and the chosen day, as "Bổ sung 3" asked. Presses on the
  drawer's own pop-ups and on the "Sửa ý tưởng" form do not close it; that form keeps its own Lưu/Huỷ.
- **The cost, accepted**: while a day is open the calendar and the Backlog are under the mask, so an idea is no longer
  dragged from the Backlog or onto another day with the drawer open; close it first. Dragging between the calendar
  and the Backlog with no day open works as before.
