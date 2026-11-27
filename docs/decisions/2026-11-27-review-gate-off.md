# 2026-11-27 — The review gate is switched off for now

Asked by the owner: the "Chờ duyệt" card on the video page, with its long list of warnings, is too complex for now.

- **`REVIEW_GATE` decides** ([review.py](../../api/src/reels_api/review.py) `gate_enabled`). Unset or anything but `on`/`1`/`true` means off, which is production today. Tests and the E2E run set it to `on`, so the gate and its screens stay covered.
- **Off means:** a rendered video can be scheduled or posted at once (no `409 not_approved`, the posting jobs are not skipped), a new render no longer resets the review or withdraws the planned posts, the video page shows no review card, rows carry no "Chờ duyệt" label (so the status filter, the post block and the menu badge go quiet), and the pending count is 0.
- **Kept:** the data (`review_status` and its events), the approve/reject endpoints, Muse and Telegram tools, and the plan tab's "Duyệt" (it approves, then posts as before).
- **Relaxes** [2026-11-26-review-gate](2026-11-26-review-gate.md) without removing it: set `REVIEW_GATE=on` to bring it back as it was. Videos approved or left pending meanwhile keep their stored status.
