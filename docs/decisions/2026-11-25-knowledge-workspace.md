# 2026-11-25 — Kho kiến thức: a group is a workspace (groups in a column, a readiness checklist, tabs by the work)

Asked by the owner ("cần update UI màn này, đột phá hơn").

- **Groups in a column on the left**, not a band of pills over the page, so the group below has the whole height and a
  group's state is seen without opening it (a dot: green with all five steps, amber with one missing).
- **The orange warning is a checklist that folds.** "Sẵn sàng tạo video" lists **required** steps (a Page that posts the
  group, a script prompt) and **nice to have** ones (a document, a 30-day plan, an approved product); only the required
  ones decide the dot and whether the card starts open (the owner's rule, same day). Each missing step has the button
  that does it. `GET /api/knowledge` sends `readiness` (`pages`, `docs`, `products`, `plan_started`) per group; the
  script prompt is already in the payload.
- **The eight tabs keep their names and the "Video" start** (so links and tests keep working) but follow the work:
  Video, plans, Lịch đăng | Tư liệu, Tài liệu, Prompt | Cài đặt nhóm, with a thin line between the three parts. Grouping
  them under four section headers was not done: it would hide tabs a member opens often behind a second click.
- **"Tài liệu" reads like a notebook**: pinned documents first, a 760 px text column, "Sao chép", and an outline for a long
  document. No change to what documents are or who may edit them.
