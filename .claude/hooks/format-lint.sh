#!/usr/bin/env bash
# Claude Code PostToolUse hook: format and lint the file an agent just wrote.
# Lint problems that cannot be fixed automatically go back to the agent (exit 2 + stderr).
# A missing tool (no api/.venv, no web/node_modules) is skipped silently.
set -uo pipefail

root="$(cd "$(dirname "$0")/../.." && pwd)"
file="$(jq -r '.tool_response.filePath // .tool_input.file_path // empty')"
[ -n "$file" ] && [ -f "$file" ] || exit 0
case "$file" in /*) ;; *) file="$root/$file" ;; esac
rel="${file#"$root"/}"

problems=""
case "$rel" in
  api/*.py | worker/*.py)
    ruff="$root/api/.venv/bin/ruff"
    [ -x "$ruff" ] || ruff="$(command -v ruff || true)"
    [ -n "$ruff" ] || exit 0
    # F401 (unused import) is left to CI: mid-edit, an import is often written before its first use.
    problems="$("$ruff" check --fix --quiet --extend-ignore F401 --output-format concise "$file" 2>&1)"
    "$ruff" format --quiet "$file" >/dev/null 2>&1
    ;;
  web/*)
    web="$root/web"
    [ -x "$web/node_modules/.bin/prettier" ] || exit 0
    case "$rel" in
      *.ts | *.tsx | *.js | *.mjs | *.json | *.jsonc | *.css | *.md)
        (cd "$web" && node_modules/.bin/prettier --write --log-level silent --ignore-unknown "$file") ;;
    esac
    case "$rel" in
      *.ts | *.tsx | *.js | *.mjs)
        # Errors only: warnings such as an unused variable are normal halfway through an edit; CI fails on them.
        problems="$(cd "$web" && node_modules/.bin/eslint --quiet --format stylish "$file" 2>&1)" ;;
    esac
    ;;
  *) exit 0 ;;
esac

if [ -n "$problems" ]; then
  printf 'Lint problems in %s (fix them before moving on):\n%s\n' "$rel" "$problems" >&2
  exit 2
fi
exit 0
