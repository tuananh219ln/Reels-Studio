# 2026-11-10 — PRs with auto-merge on are brought up to date with main by a workflow

Asked by the owner (namtc) on 2026-11-10: with two PRs on auto-merge, the second one stopped at "This branch is
out-of-date with the base branch" after the first merged, and someone had to press "Update branch" every time.

- **Keep "require branches to be up to date"** in the `Protect main` ruleset: two PRs green on their own can break
  together, and the push to `main` skips testing again only because the merged code is exactly what the PR tested
  (docs/deployment.md, Delivery).
- **No merge queue**: GitHub offers it only to repositories owned by an organization; this one belongs to a user.
- **A workflow on every push to `main`** ([pr-auto-update.yml](../../.github/workflows/pr-auto-update.yml)) updates
  each open PR that has auto-merge on and is behind. Auto-merge is the author's "merge this when green", so a PR
  still being worked on is not touched and does not run CI for nothing. Every such PR is updated at once, not one at
  a time: CI is free on this public repository, and a queue would stall behind a PR whose checks fail.
- **A person's token, `AUTO_UPDATE_TOKEN`**: an update made with the workflow's `GITHUB_TOKEN` starts no workflow,
  so the PR would wait for checks forever. The token is fine-grained, for this repository only, and its owner
  renews it when it expires; without it the workflow only warns.
- **A conflict is left to the author**: the workflow warns and the PR stays blocked until it is resolved by hand.
