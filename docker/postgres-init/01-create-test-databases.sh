#!/bin/sh
# Runs once, when the data volume is empty: the dev database comes from POSTGRES_DB,
# pytest uses reels_test and Playwright uses reels_e2e so tests never touch dev data.
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
	CREATE DATABASE reels_test;
	CREATE DATABASE reels_e2e;
EOSQL
