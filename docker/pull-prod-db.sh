#!/usr/bin/env bash
# Copy the production database into the local dev database `reels` (docker compose postgres).
#
# Run by a person with SSH access to the production server, never by an agent (AGENTS.md).
# Production is only read: pg_dump runs inside the Coolify Postgres container over SSH.
#
#   docker/pull-prod-db.sh <ssh-target> <postgres-container> [--yes]
#   docker/pull-prod-db.sh root@203.0.113.10 abc123postgres
#
# The dump is kept in data/prod-dumps/ (git-ignored); it holds real member data, so do not share it.
set -euo pipefail

usage() {
  echo "Usage: $0 <ssh-target> <postgres-container> [--yes]" >&2
  echo "  ssh-target          e.g. root@203.0.113.10 or an alias from ~/.ssh/config" >&2
  echo "  postgres-container  the Postgres container name shown on the Coolify database page" >&2
  echo "  --yes               do not ask before replacing the local database 'reels'" >&2
  exit 2
}

[[ $# -ge 2 && $# -le 3 ]] || usage
SSH_TARGET=$1
CONTAINER=$2
ASSUME_YES=${3:-}
[[ -z $ASSUME_YES || $ASSUME_YES == --yes ]] || usage
[[ $CONTAINER =~ ^[A-Za-z0-9_.-]+$ ]] || { echo "Invalid container name: $CONTAINER" >&2; exit 2; }

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
DUMP_DIR=data/prod-dumps
DUMP="$DUMP_DIR/reels-$(date +%Y%m%d-%H%M%S).dump"
LOCAL_DB=reels

local_psql() { docker compose exec -T postgres psql -U reels -v ON_ERROR_STOP=1 "$@"; }

docker compose up -d --wait postgres >/dev/null

mkdir -p "$DUMP_DIR"
echo "Dumping production database from $CONTAINER on $SSH_TARGET ..."
# The container's own POSTGRES_USER / POSTGRES_DB; the socket inside the container needs no password.
# shellcheck disable=SC2016 # expanded inside the container, not here
if ! ssh "$SSH_TARGET" "docker exec $CONTAINER sh -c 'pg_dump -U \"\$POSTGRES_USER\" -d \"\${POSTGRES_DB:-reels}\" -Fc --no-owner --no-acl'" >"$DUMP.part"; then
  rm -f "$DUMP.part"
  echo "pg_dump failed; the local database was not touched." >&2
  exit 1
fi
# The dump must be Reels Studio's database before the local one is dropped: the Coolify server also
# runs Coolify's own Postgres (coolify-db), whose dump holds the server's keys and every app's secrets.
toc=$(docker compose exec -T postgres pg_restore -l <"$DUMP.part" 2>/dev/null || true)
if ! grep -q ' TABLE public alembic_version ' <<<"$toc" || ! grep -q ' TABLE public jobs ' <<<"$toc"; then
  rm -f "$DUMP.part"
  echo "$CONTAINER is not the Reels Studio database (no alembic_version and jobs tables); the dump was" >&2
  echo "deleted and the local database was not touched. The right container is the end of the URL of" >&2
  echo "Reels Studio's PostgreSQL resource in Coolify (.../database/<container>), not coolify-db." >&2
  exit 1
fi
mv "$DUMP.part" "$DUMP"
echo "Saved $DUMP ($(du -h "$DUMP" | cut -f1))"

if [[ $ASSUME_YES != --yes ]]; then
  read -r -p "Replace the local database '$LOCAL_DB' with this dump? All local dev data in it is lost. Type '$LOCAL_DB' to continue: " answer
  [[ $answer == "$LOCAL_DB" ]] || { echo "Cancelled; the dump is kept in $DUMP."; exit 1; }
fi

echo "Restoring into local '$LOCAL_DB' ..."
local_psql -d postgres -c "DROP DATABASE IF EXISTS $LOCAL_DB WITH (FORCE)" -c "CREATE DATABASE $LOCAL_DB OWNER reels" >/dev/null
docker compose exec -T postgres pg_restore -U reels -d "$LOCAL_DB" --no-owner --no-acl --exit-on-error <"$DUMP"

# A local worker must not pick up production's unfinished jobs (they would call real APIs).
cancelled=$(local_psql -d "$LOCAL_DB" -tA -c "WITH c AS (UPDATE jobs SET status = 'cancelled' WHERE status IN ('queued', 'running') RETURNING 1) SELECT count(*) FROM c")
echo "Done. Cancelled $cancelled unfinished production job(s) in the local copy."
echo "Next: cd api && .venv/bin/alembic upgrade head   (the branch may have newer migrations than production)"
