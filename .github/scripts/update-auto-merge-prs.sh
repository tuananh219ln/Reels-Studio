#!/usr/bin/env bash
# Brings every open PR that has auto-merge on up to date with main. main's ruleset requires a PR to be up
# to date before it merges, so after one PR merges the others stay blocked until someone presses
# "Update branch". Updating them here starts their CI again, and auto-merge merges each once it passes.
#
# Only PRs with auto-merge on are touched: a PR still being worked on keeps its branch as it is. A PR
# whose update conflicts is reported and left for its author.
#
# Needs GH_TOKEN and GH_REPO (owner/name). The token must not be the workflow's GITHUB_TOKEN: a commit it
# makes starts no workflow, so CI would never run on the updated branch. DRY_RUN=1 only prints.
set -euo pipefail

: "${GH_REPO:?set GH_REPO to owner/name}"

prs=$(gh pr list --repo "$GH_REPO" --state open --base main --limit 100 \
  --json number,headRefOid,isCrossRepository,isDraft,autoMergeRequest \
  -q '.[] | select(.autoMergeRequest != null and (.isCrossRepository | not) and (.isDraft | not)) | "\(.number) \(.headRefOid)"')

if [ -z "$prs" ]; then
  echo "No open PR has auto-merge on"
  exit 0
fi

failed=0
while read -r number head; do
  behind=$(gh api "repos/$GH_REPO/compare/main...$head" -q .behind_by)
  if [ "$behind" = 0 ]; then
    echo "#$number: up to date with main"
    continue
  fi
  echo "#$number: $behind commit(s) behind main, updating its branch"
  [ "${DRY_RUN:-}" = 1 ] && continue
  if ! gh api -X PUT "repos/$GH_REPO/pulls/$number/update-branch" -f expected_head_sha="$head" --silent; then
    echo "::warning::#$number could not be updated (a conflict with main?); its author updates it by hand"
    failed=1
  fi
done <<<"$prs"

exit "$failed"
