#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
MONTHS="${MONTHS:-36}"
NUM_ROWS="${NUM_ROWS:-1000}"

export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

fetch_apartments() {
  local city_code="$1"
  local output_path="$2"

  if [[ -n "${REFERENCE_MONTH:-}" ]]; then
    "$PYTHON_BIN" -m hedonic_house_price fetch \
      --city-codes "$city_code" \
      --property-types apartment \
      --months "$MONTHS" \
      --num-rows "$NUM_ROWS" \
      --reference-month "$REFERENCE_MONTH" \
      --output "$output_path"
  else
    "$PYTHON_BIN" -m hedonic_house_price fetch \
      --city-codes "$city_code" \
      --property-types apartment \
      --months "$MONTHS" \
      --num-rows "$NUM_ROWS" \
      --output "$output_path"
  fi
}

mkdir -p "$ROOT_DIR/data"

"$PYTHON_BIN" -m hedonic_house_price db-clear-data

fetch_apartments seoul "$ROOT_DIR/data/seoul_apartment_trades.csv"

"$PYTHON_BIN" -m hedonic_house_price db-import-csv \
  --input "$ROOT_DIR/data/seoul_apartment_trades.csv" \
  --city-code seoul

fetch_apartments busan "$ROOT_DIR/data/busan_apartment_trades.csv"

"$PYTHON_BIN" -m hedonic_house_price db-import-csv \
  --input "$ROOT_DIR/data/busan_apartment_trades.csv" \
  --city-code busan

"$PYTHON_BIN" -m hedonic_house_price db-refresh-derived-snapshots
