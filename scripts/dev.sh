#!/usr/bin/env bash
# Local development in one command (macOS/Linux): starts Postgres, makes sure api/.venv is a working
# Python venv for this checkout (rebuilt with uv when it is missing, on the wrong Python, moved, or
# behind pyproject.toml), runs the migrations, then runs api + worker + web in this terminal.
# Ctrl+C stops all three. Works with the bash 3.2 that ships with macOS.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API="$ROOT/api"
WEB="$ROOT/web"
VENV="$API/.venv"
PY="$VENV/bin/python"
PYTHON_VERSION="$(tr -d '[:space:]' <"$ROOT/.python-version")"

say() { printf '\033[1m==> %s\033[0m\n' "$*"; }
die() {
  printf '\033[31m%s\033[0m\n' "$*" >&2
  exit 1
}
need() { command -v "$1" >/dev/null 2>&1 || die "Thiếu $1. $2"; }

need uv "Cài bằng: brew install uv (hoặc curl -LsSf https://astral.sh/uv/install.sh | sh)"
need docker "Cài Docker Desktop và mở nó lên."
need npm "Cài Node 22 (brew install node@22)."
command -v ffmpeg >/dev/null 2>&1 || printf '\033[33mChưa có ffmpeg: worker sẽ không render được (brew install ffmpeg).\033[0m\n'

if [ ! -f "$ROOT/.env" ]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  say "Đã tạo .env từ .env.example"
fi

say "Postgres"
docker compose -f "$ROOT/docker-compose.yml" up -d --wait postgres

# The stamp records what the venv was built for: Python version, this checkout's path (editable installs
# point at it, so a moved folder breaks them) and both pyproject files. Any change rebuilds it.
STAMP="$VENV/.dev-stamp"
WANT="$PYTHON_VERSION|$ROOT|$(cat "$API/pyproject.toml" "$ROOT/worker/pyproject.toml" | shasum | cut -d' ' -f1)"
if [ ! -x "$PY" ] || [ "$(cat "$STAMP" 2>/dev/null)" != "$WANT" ] || ! "$PY" -c 'import reels_api, reels_render' 2>/dev/null; then
  say "Tạo lại api/.venv bằng Python $PYTHON_VERSION"
  rm -rf "$VENV"
  # --seed keeps pip in the venv for anyone still following the pip commands.
  uv venv --seed --python "$PYTHON_VERSION" "$VENV"
  uv pip install --python "$PY" -e "$ROOT/worker" -e "$API[dev]"
  printf '%s\n' "$WANT" >"$STAMP"
fi

say "Migration"
(cd "$API" && "$VENV/bin/alembic" upgrade head) ||
  die "Migration lỗi. Nếu báo \"Can't locate revision\": database dev đang ở migration của một nhánh khác; quay lại nhánh đó, hoặc chạy alembic downgrade trên nhánh đó trước khi đổi nhánh."

if [ ! -d "$WEB/node_modules" ] || [ "$WEB/package-lock.json" -nt "$WEB/node_modules/.package-lock.json" ]; then
  say "npm install"
  (cd "$WEB" && npm install)
fi

# Each process prints with its own label. When one stops (or on Ctrl+C), the others are stopped too.
PIDS=()
# Stops a process and everything under it (uvicorn's reloader child, next's workers, the awk labels).
stop_tree() {
  local child
  for child in $(pgrep -P "$1" 2>/dev/null); do stop_tree "$child"; done
  kill "$1" 2>/dev/null || true
}
cleanup() {
  trap - INT TERM EXIT
  for pid in ${PIDS[@]+"${PIDS[@]}"}; do stop_tree "$pid"; done
  wait 2>/dev/null || true
}
trap 'cleanup; exit 130' INT TERM
trap cleanup EXIT
run() {
  local label="$1"
  shift
  ("$@" 2>&1 | awk -v p="[$label] " '{ print p $0; fflush() }') &
  PIDS+=("$!")
}
export PYTHONUNBUFFERED=1
run api bash -c "cd '$API' && exec '$PY' -m uvicorn reels_api.main:create_app --factory --port 8000 --reload --reload-dir src --reload-dir ../worker/src"
run worker bash -c "cd '$API' && exec '$PY' -m reels_api worker"
run web bash -c "cd '$WEB' && exec npm run dev"

say "Mở http://localhost:3000 (chưa có tài khoản: cd api && .venv/bin/python -m reels_api create-user). Ctrl+C để tắt."
while :; do
  for pid in "${PIDS[@]}"; do
    kill -0 "$pid" 2>/dev/null || die "Một tiến trình đã dừng (xem log ở trên); tắt các tiến trình còn lại."
  done
  sleep 2
done
