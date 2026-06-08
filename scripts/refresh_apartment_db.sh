#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
MONTHS="${MONTHS:-24}"
NUM_ROWS="${NUM_ROWS:-1000}"

export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

REFERENCE_MONTH_ARGS=()
if [[ -n "${REFERENCE_MONTH:-}" ]]; then
  REFERENCE_MONTH_ARGS=(--reference-month "$REFERENCE_MONTH")
fi

mkdir -p "$ROOT_DIR/data"

"$PYTHON_BIN" -m hedonic_house_price db-clear-data

"$PYTHON_BIN" -m hedonic_house_price fetch \
  --city-codes seoul \
  --property-types apartment \
  --months "$MONTHS" \
  --num-rows "$NUM_ROWS" \
  "${REFERENCE_MONTH_ARGS[@]}" \
  --output "$ROOT_DIR/data/seoul_apartment_trades.csv"

"$PYTHON_BIN" -m hedonic_house_price db-import-csv \
  --input "$ROOT_DIR/data/seoul_apartment_trades.csv" \
  --city-code seoul

"$PYTHON_BIN" -m hedonic_house_price fetch \
  --city-codes busan \
  --property-types apartment \
  --months "$MONTHS" \
  --num-rows "$NUM_ROWS" \
  "${REFERENCE_MONTH_ARGS[@]}" \
  --output "$ROOT_DIR/data/busan_apartment_trades.csv"

"$PYTHON_BIN" -m hedonic_house_price db-import-csv \
  --input "$ROOT_DIR/data/busan_apartment_trades.csv" \
  --city-code busan

"$PYTHON_BIN" -m hedonic_house_price db-refresh-derived-snapshots
