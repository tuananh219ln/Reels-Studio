# 2026-11-09 — One file per decision, so parallel branches never conflict on the log

Asked by the owner (namtc) after #165, #166 and #167 all stopped on a conflict in `docs/decisions.md`: every branch
added its entry at the top of the same file, so any two open at once collided, and auto-merge ("Green CI is the
approval", 2026-11-07) waited for someone to merge by hand, always keeping both sides.

- **A new decision is a new file** in `docs/decisions/`, `YYYY-MM-DD-short-name.md` (the date it was made, a few
  English words), opening with `# YYYY-MM-DD — Title` and written as the entries were: what was decided and why,
  and which earlier decision it replaces, if any. Two branches add two files and git never sees a conflict.
- **No index**: a list of the files would be one shared file again. The folder sorts by date on its own.
- **`docs/decisions.md` stays** as the log of everything decided before, unchanged but for its header, which points
  here; links to its entries keep working. Old decisions are never edited, in either place.
- Agents read both before a new round of work ([AGENTS.md](../../AGENTS.md)). The `@claude` workflow's prompt still
  says to start with `docs/decisions.md`, whose header leads to the folder; `.github/` is left as it is.
