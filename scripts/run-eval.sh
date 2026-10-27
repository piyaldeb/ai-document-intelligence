#!/usr/bin/env sh
# Regenerate the labeled dataset and run the end-to-end evaluation against the running stack.
# Usage: ./scripts/run-eval.sh [--stress]
#   The stack must be up:  docker compose up -d --build
#   Writes eval/results/metrics.json and docs/evaluation-report.md.
#   WARNING: --reset (always passed) deletes all documents in the target deployment.
set -e
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1
ROOT="$(pwd -W 2>/dev/null || pwd)"
STRESS="$1"
docker compose run --rm --no-deps -T -e PYTHONPATH=/app -v "$ROOT/eval:/eval" api sh -c "
  python /eval/generate_dataset.py --out /eval/dataset $STRESS &&
  python /eval/run_eval.py --api http://api:8000 --dataset /eval/dataset --out /eval/results --reset $STRESS &&
  python /eval/make_report.py --metrics /eval/results/metrics.json --out /eval/results/evaluation-report.md"
cp eval/results/evaluation-report.md docs/evaluation-report.md
echo "Report: docs/evaluation-report.md"
