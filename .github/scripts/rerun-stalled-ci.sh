#!/usr/bin/env bash
# Reruns a CI/CD run that GitHub itself broke, once. During a GitHub Actions incident a run can end as
# "failure" having created no jobs, or only some of them, with none of its jobs failing: the checks
# it never created stay "Waiting for status" on the PR and block the merge until someone reruns it.
#
# For the newest CI/CD run of main and of each open PR's branch, on the branch's current commit:
# when it ended as failure or startup_failure on its first attempt and none of its jobs failed, was
# cancelled or timed out, it reruns the whole run (not only failed jobs, as the missing ones never
# ran). A run with a real failing job, or one already rerun, is left alone.
#
# Needs GH_TOKEN (actions: write) and GH_REPO (owner/name). DRY_RUN=1 only prints what it would do.
set -euo pipefail

: "${GH_REPO:?set GH_REPO to owner/name}"
workflow="${WORKFLOW:-ci-cd.yml}"

# Branches whose checks matter: main and the head of every open PR from this repository.
branches=$(
  {
    echo main
    gh pr list --repo "$GH_REPO" --state open --limit 100 \
      --json headRefName,isCrossRepository -q '.[] | select(.isCrossRepository | not) | .headRefName'
  } | sort -u
)

for branch in $branches; do
  head=$(gh api "repos/$GH_REPO/branches/$branch" -q .commit.sha 2>/dev/null) || continue
  run=$(gh api "repos/$GH_REPO/actions/workflows/$workflow/runs?branch=$branch&per_page=1" \
    -q '.workflow_runs[0] // empty | [.id, .head_sha, .status, (.conclusion // "none"), .run_attempt] | @tsv')
  [ -n "$run" ] || continue
  read -r id sha status conclusion attempt <<<"$run"

  [ "$sha" = "$head" ] || continue
  [ "$status" = completed ] || continue
  case "$conclusion" in failure | startup_failure) ;; *) continue ;; esac
  if [ "$attempt" != 1 ]; then
    echo "$branch: run $id already rerun (attempt $attempt), leaving it"
    continue
  fi

  broken=$(gh api "repos/$GH_REPO/actions/runs/$id/jobs?filter=latest&per_page=100" \
    -q '[.jobs[] | select(.conclusion == "failure" or .conclusion == "cancelled" or .conclusion == "timed_out")] | length')
  if [ "$broken" != 0 ]; then
    echo "$branch: run $id has $broken failing job(s), a real failure, leaving it"
    continue
  fi

  echo "$branch: run $id ended $conclusion with no failing job, rerunning it"
  if [ "${DRY_RUN:-}" != 1 ]; then
    gh run rerun "$id" --repo "$GH_REPO"
  fi
done
