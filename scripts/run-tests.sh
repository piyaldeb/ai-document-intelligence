#!/usr/bin/env sh
# Run the backend test-suite inside the backend image against the compose Postgres/Redis.
# Usage: ./scripts/run-tests.sh [extra pytest args]
set -e
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1  # Git Bash on Windows: don't rewrite container paths
docker compose up -d db redis >/dev/null
docker compose run --rm --no-deps -T api \
  sh -c "python -m pytest -p no:cacheprovider --cov=app --cov-report=term-missing:skip-covered -q $*"
