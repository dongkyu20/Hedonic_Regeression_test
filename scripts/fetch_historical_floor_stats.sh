#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
START_MONTH="${START_MONTH:-201001}"
END_MONTH="${END_MONTH:-$(date +%Y%m)}"
NUM_ROWS="${NUM_ROWS:-1000}"
SLEEP_SECONDS="${SLEEP_SECONDS:-0.05}"
MAX_RETRIES="${MAX_RETRIES:-3}"
RETRY_BACKOFF_SECONDS="${RETRY_BACKOFF_SECONDS:-60}"
WORKERS="${WORKERS:-1}"
PROGRESS_EVERY="${PROGRESS_EVERY:-100}"
OUTPUT="${OUTPUT:-$ROOT_DIR/data/seoul_busan_historical_complex_floor_stats.csv}"

export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

mkdir -p "$(dirname "$OUTPUT")"

"$PYTHON_BIN" -m hedonic_house_price fetch-historical-floor-stats \
  --city-codes seoul,busan \
  --start-month "$START_MONTH" \
  --end-month "$END_MONTH" \
  --num-rows "$NUM_ROWS" \
  --sleep-seconds "$SLEEP_SECONDS" \
  --max-retries "$MAX_RETRIES" \
  --retry-backoff-seconds "$RETRY_BACKOFF_SECONDS" \
  --workers "$WORKERS" \
  --progress-every "$PROGRESS_EVERY" \
  --output "$OUTPUT"
