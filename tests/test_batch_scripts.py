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


if __name__ == "__main__":
    unittest.main()
