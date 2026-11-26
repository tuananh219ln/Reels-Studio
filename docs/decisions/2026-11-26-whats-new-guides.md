# 2026-11-26 — Guides follow features, and "Có gì mới" says who

Follows [2026-11-26-whats-new](2026-11-26-whats-new.md), asked by the owner after it went live.

## Decision

- **A feature ships with its guide.** A `feat` PR that changes what members see or do on a screen adds or updates that
  screen's in-app guide (`api/src/reels_api/guides/`) in the same PR; the rule is in `AGENTS.md`, so the agents who
  write the PRs do it and no member has to. No AI writes guides after the fact (the owner turned AI rewriting down).
- **"Tất cả hướng dẫn" marks what changed, from "Có gì mới".** A guide whose newest change (from the PR's files, already
  in `changelog.json`) is under 7 days old shows "Mới" in the list, and every guide a change wrote names it above the
  text ("Cập nhật cùng <change>, <time>", linking to "Có gì mới"). Nothing is stored for it.
- **Each change says who it was for:** the PR's "Requested by" line (PRs opened through Claude name the member who asked),
  else the author's GitHub name, else their GitHub login. Shown as "bởi <name>" in the app, in the Telegram post and
  as `by` in the MCP tool.
