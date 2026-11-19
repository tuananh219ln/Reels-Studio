# 2026-11-19: E2E runs on eight machines

## Context

Every CI round took 13-14 minutes, almost all of it E2E: each of the four machines spends about two minutes setting
up (npm ci, the api's venv, Chromium from cache), then ran 6-11 minutes of tests. Because a PR must be up to date with
`main` before it merges, a busy day reran whole rounds several times, and a flaky test one more.

## Decision

tuananh219ln's choice (2026-11-19): E2E runs on eight machines, each taking every 8th test of
`playwright test --list` (still round-robin, not `--shard`, so the render-heavy tests spread out). The "passed" job's
list and the "Protect main" ruleset's required checks name all eight shards, `e2e (1)` to `e2e (8)`; the ruleset is
updated right after this merges, since a check it requires but no workflow runs would block every PR.

More machines cost more Actions minutes (the setup is paid eight times), for a round expected around 7-8 minutes.

## Verification

The workflow parses; the first PR run shows the eight shards and their times.
