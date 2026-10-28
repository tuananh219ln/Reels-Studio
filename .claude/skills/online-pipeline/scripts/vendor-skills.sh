#!/usr/bin/env bash
#
# vendor-skills.sh — copy everything online-pipeline needs into this project
#
# Why this exists: a GitHub Actions runner has no ~/.claude/skills or ~/.claude/agents (those are
# only populated on a developer's own machine). claude -p running in CI can only use a skill or
# agent that physically exists in the checked-out repo under .claude/skills/ or .claude/agents/.
# online-pipeline's stages drive user-spec-planning, code-writing, documentation-writing, and
# test-master, which in turn spawn nine reviewer/research agents — all of it must be vendored here.
# This also refreshes the three .github/workflows/online-pipeline-*.yml files, so re-running this
# script is the single update path for both the automation logic and the skills/agents it drives.
#
# Usage: ./vendor-skills.sh [source-dir]
#   source-dir  — optional path to a local molyanov-ai-dev checkout. If omitted, clones
#                 https://github.com/thanhpd56/molyanov-ai-dev.git fresh (public repo, no auth).
#
# Run from the target project root. Safe to re-run anytime to pick up upstream updates — this is
# also the proactive-update mechanism: re-run it whenever you want the latest version. Nothing is
# committed automatically; review with `git status`/`git diff` before committing.
#
# Refuses to run if .claude/skills/, .claude/agents/, or .github/workflows/online-pipeline-*.yml
# have uncommitted changes, since this script overwrites those paths wholesale and an uncommitted
# local edit there would be silently lost with no trace once overwritten. Commit or stash first.

set -euo pipefail

SKILLS=(user-spec-planning code-writing documentation-writing test-master online-pipeline)
AGENTS=(code-researcher interview-completeness-checker skeptic userspec-quality-validator userspec-adequacy-validator code-reviewer security-auditor test-reviewer documentation-reviewer)
WORKFLOWS=(online-pipeline-userspec.yml online-pipeline-implement.yml online-pipeline-finalize.yml)

if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  CHECK_PATHS=()
  for s in "${SKILLS[@]}"; do CHECK_PATHS+=(".claude/skills/$s"); done
  for a in "${AGENTS[@]}"; do CHECK_PATHS+=(".claude/agents/$a.md"); done
  for w in "${WORKFLOWS[@]}"; do CHECK_PATHS+=(".github/workflows/$w"); done
  DIRTY="$(git status --porcelain -- "${CHECK_PATHS[@]}" 2>/dev/null || true)"
  if [[ -n "$DIRTY" ]]; then
    echo "Error: uncommitted changes in files this script would overwrite." >&2
    echo "Commit or stash first so nothing is silently lost:" >&2
    echo "$DIRTY" >&2
    exit 1
  fi
fi

SOURCE_DIR="${1:-}"
CLEANUP_DIR=""
cleanup() {
  local exit_code=$?
  if [[ -n "$CLEANUP_DIR" ]]; then
    rm -rf "$CLEANUP_DIR"
  fi
  exit "$exit_code"
}
trap cleanup EXIT

if [[ -z "$SOURCE_DIR" ]]; then
  CLEANUP_DIR="$(mktemp -d)"
  SOURCE_DIR="$CLEANUP_DIR"
  echo "Cloning https://github.com/thanhpd56/molyanov-ai-dev.git (public repo, no auth needed)..."
  git clone --depth 1 --quiet https://github.com/thanhpd56/molyanov-ai-dev.git "$SOURCE_DIR"
fi

if [[ ! -d "$SOURCE_DIR/skills" || ! -d "$SOURCE_DIR/agents" ]]; then
  echo "Error: $SOURCE_DIR does not look like a molyanov-ai-dev checkout (missing skills/ or agents/)" >&2
  exit 1
fi

# --- Validate the full closure exists before changing anything (all-or-nothing, not a partial mix) ---
for s in "${SKILLS[@]}"; do
  if [[ ! -d "$SOURCE_DIR/skills/$s" ]]; then
    echo "Error: source is missing skills/$s — aborting before changing anything" >&2
    exit 1
  fi
done
for a in "${AGENTS[@]}"; do
  if [[ ! -f "$SOURCE_DIR/agents/$a.md" ]]; then
    echo "Error: source is missing agents/$a.md — aborting before changing anything" >&2
    exit 1
  fi
done
for w in "${WORKFLOWS[@]}"; do
  if [[ ! -f "$SOURCE_DIR/skills/online-pipeline/assets/workflows/$w" ]]; then
    echo "Error: source is missing skills/online-pipeline/assets/workflows/$w — aborting before changing anything" >&2
    exit 1
  fi
done

# --- Apply ---
mkdir -p .claude/skills .claude/agents .github/workflows

for s in "${SKILLS[@]}"; do
  rm -rf ".claude/skills/$s"
  cp -r "$SOURCE_DIR/skills/$s" ".claude/skills/$s"
  echo "Vendored skill: $s"
done

for a in "${AGENTS[@]}"; do
  cp "$SOURCE_DIR/agents/$a.md" ".claude/agents/$a.md"
  echo "Vendored agent: $a"
done

for w in "${WORKFLOWS[@]}"; do
  cp "$SOURCE_DIR/skills/online-pipeline/assets/workflows/$w" ".github/workflows/$w"
  echo "Updated workflow: .github/workflows/$w"
done

echo ""
echo "Done. Review with 'git status' / 'git diff', then commit when ready."
