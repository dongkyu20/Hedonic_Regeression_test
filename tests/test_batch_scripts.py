from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BatchScriptTests(unittest.TestCase):
    def test_refresh_apartment_db_script_fetches_only_seoul_and_busan_apartments(self):
        script = (ROOT / "scripts" / "refresh_apartment_db.sh").read_text(encoding="utf-8")

        self.assertIn("db-clear-data", script)
        self.assertIn('--city-codes "$city_code"', script)
        self.assertIn("fetch_apartments seoul", script)
        self.assertIn("fetch_apartments busan", script)
        self.assertIn("--property-types apartment", script)
        self.assertIn('MONTHS="${MONTHS:-36}"', script)
        self.assertNotIn("officetel", script)
        self.assertNotIn("rowhouse", script)
        self.assertNotIn("REFERENCE_MONTH_ARGS[@]", script)
        self.assertIn("db-refresh-derived-snapshots", script)

    def test_fetch_historical_floor_stats_script_targets_seoul_busan_since_201001(self):
        script = (ROOT / "scripts" / "fetch_historical_floor_stats.sh").read_text(encoding="utf-8")

        self.assertIn("fetch-historical-floor-stats", script)
        self.assertIn('START_MONTH="${START_MONTH:-201001}"', script)
        self.assertIn('RETRY_BACKOFF_SECONDS="${RETRY_BACKOFF_SECONDS:-60}"', script)
        self.assertIn('WORKERS="${WORKERS:-1}"', script)
        self.assertIn("--city-codes seoul,busan", script)
        self.assertIn("--start-month \"$START_MONTH\"", script)
        self.assertIn("--workers \"$WORKERS\"", script)
        self.assertIn("--retry-backoff-seconds \"$RETRY_BACKOFF_SECONDS\"", script)
        self.assertIn("--output \"$OUTPUT\"", script)
        self.assertNotIn("db-import-csv", script)
        self.assertNotIn("db-clear-data", script)


if __name__ == "__main__":
    unittest.main()
