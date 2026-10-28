#!/usr/bin/env bash
#
# setup-online-pipeline.sh — Enable online-pipeline on the current repo
#
# Usage: ./setup-online-pipeline.sh
#
# Run from the target project root (not from this skill's own directory). Vendors the
# online-pipeline workflow files plus every skill/agent they depend on, offers to set the required
# secrets via `gh secret set`, creates the needed labels, and prints the manual steps that cannot
# be scripted.
#
# A project scaffolded by project-initialization already has all of this vendored in; run this
# script only on a pre-existing repo that does not.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v gh >/dev/null 2>&1; then
  echo "Error: gh (GitHub CLI) is required and was not found on PATH" >&2
  exit 1
fi

# --- Vendor the workflows plus every skill/agent claude -p needs on a bare CI runner ---
# A GitHub Actions runner has no ~/.claude/skills or ~/.claude/agents, so every skill and agent
# the pipeline's claude -p calls depend on (user-spec-planning, code-writing, documentation-writing,
# test-master, online-pipeline itself, and the 9 agents they spawn) must live in this repo's own
# .claude/. Re-run scripts/vendor-skills.sh anytime later to pick up upstream updates.
"$SCRIPT_DIR/vendor-skills.sh"

# --- Create the labels the workflows apply (gh pr create --label fails on a missing label) ---
for label in userspec-spec userspec-implement; do
  if ! gh label list --json name -q '.[].name' 2>/dev/null | grep -qx "$label"; then
    gh label create "$label" --description "online-pipeline" --color "0E8A16" || true
    echo "Created label: $label"
  fi
done

# --- Offer to set secrets ---
echo ""
echo "online-pipeline needs these repo secrets:"
echo "  1. CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY — Claude auth (pick one)"
echo "  2. GH_PAT — a Personal Access Token with 'repo' scope, used only to merge the spec PR on"
echo "     /approve. The default GITHUB_TOKEN cannot trigger the implement job's workflow run, so"
echo "     this one merge step needs a real user token instead."
echo ""

set_secret_if_confirmed() {
  local name="$1" prompt="$2"
  read -r -p "Set secret $name now? [y/N] " reply
  if [[ "$reply" =~ ^[Yy]$ ]]; then
    read -r -s -p "$prompt: " value
    echo ""
    gh secret set "$name" --body "$value"
    echo "Secret $name set."
  else
    echo "Skipped $name — set it later with: gh secret set $name"
  fi
}

read -r -p "Which Claude auth method? [oauth/api-key/skip] " auth_choice
case "$auth_choice" in
  oauth) set_secret_if_confirmed "CLAUDE_CODE_OAUTH_TOKEN" "Paste the OAuth token (from 'claude setup-token')" ;;
  api-key) set_secret_if_confirmed "ANTHROPIC_API_KEY" "Paste the Anthropic API key" ;;
  *) echo "Skipped Claude auth — set CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY later." ;;
esac

set_secret_if_confirmed "GH_PAT" "Paste the Personal Access Token (repo scope)"

# --- Print the manual, browser-only steps ---
cat <<'EOF'

Remaining manual steps (cannot be scripted — each requires browser authentication):

  1. Install the Claude GitHub App on this repository.
     Easiest path: run `claude` locally once and use `/install-github-app`, or visit
     https://github.com/apps/claude and select this repository.

  2. Create the Claude auth credential if you have not already:
     - OAuth (subscription): run `claude setup-token` and copy the printed token.
     - API key: create one at https://console.anthropic.com and copy it.
     Store whichever one you chose as a repo secret (see above).

  3. Create a Personal Access Token (classic or fine-grained, 'repo' scope) at
     https://github.com/settings/tokens and store it as the GH_PAT secret (see above).
     This is required only so that approving a spec PR can trigger the implement job.

Once all three secrets are set and the GitHub App is installed, open a new issue on this repo to
start the pipeline.

To pick up a newer version of the vendored skills/agents later, re-run:
  .claude/skills/online-pipeline/scripts/vendor-skills.sh
EOF
