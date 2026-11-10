# 2026-11-10 — CI reruns itself once when a GitHub incident broke the run

Asked by the owner (namtc) on 2026-11-10, after PRs 184 and 185 sat at "Waiting for status": their CI/CD runs started
during GitHub's "Incident with Actions and Checks API" (2026-11-09 18:12-18:59 UTC) and ended as failure, one with no
jobs at all and one with 5 of its 11 required checks, none of them failing. GitHub had six Actions incidents that week.

- **A scheduled workflow, not `workflow_run`** ([ci-rerun.yml](../../.github/workflows/ci-rerun.yml), every 20 minutes):
  a run that failed at startup may never fire `workflow_run`, and a schedule also catches a run nobody is watching.
- **Rerun only what GitHub broke**: the newest CI/CD run of `main` or an open PR's branch, on its current commit,
  ended as failure or startup_failure with no job failed, cancelled or timed out. A run with a real failing test is
  never rerun, so flaky tests stay visible and get fixed.
- **Once per run** (`run_attempt == 1`), so a long incident does not loop; after that a person reruns it by hand.
- **The whole run** is rerun, not only failed jobs: the missing jobs never ran, so "rerun failed jobs" would not make
  them.
- **Not covered**: a run whose every job failed in seconds because no runner started (seen 2026-11-08) has failing
  jobs, so it looks like a real failure and is left to a person.
