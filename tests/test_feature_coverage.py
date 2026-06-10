import csv
import tempfile
import unittest
from pathlib import Path

from hedonic_house_price.feature_coverage import (
    FEATURE_SPECS,
    FeatureSpec,
    build_coverage_rows,
    summarize_coverage_rows,
    write_feature_coverage_reports,
)


class FeatureCoverageTests(unittest.TestCase):
    def test_feature_specs_cover_expected_groups_and_exclude_removed_high_school_field(self):
        columns = {spec.column for spec in FEATURE_SPECS}
        groups = {spec.category for spec in FEATURE_SPECS}

        self.assertIn("property_condition", groups)
        self.assertIn("transport_access", groups)
        self.assertIn("living_environment", groups)
        self.assertIn("urban_competitiveness", groups)
        self.assertIn("nearest_middle_school_distance_m", columns)
        self.assertIn("nearest_park_distance_m", columns)
        self.assertNotIn("nearest_high_school_distance_m", columns)

    def test_build_coverage_rows_calculates_percentages_and_status(self):
        specs = [
            FeatureSpec("core_transaction", "exclusive_area_m2", "전용면적"),
            FeatureSpec("living_environment", "academy_count_radius", "학원 수"),
            FeatureSpec("urban_competitiveness", "population_count", "인구 수"),
        ]
        rows = build_coverage_rows(
            specs,
            totals={"all": 100, "seoul": 60, "busan": 40},
            counts_by_column={
                "exclusive_area_m2": {"all": 100, "seoul": 60, "busan": 40},
                "academy_count_radius": {"all": 12, "seoul": 10, "busan": 2},
                "population_count": {"all": 0, "seoul": 0, "busan": 0},
            },
        )

        self.assertEqual(rows[0].coverage_pct, 100.0)
        self.assertEqual(rows[0].status, "ready")
        self.assertEqual(rows[1].missing_rows, 88)
        self.assertEqual(rows[1].coverage_pct, 12.0)
        self.assertEqual(rows[1].seoul_coverage_pct, 16.67)
        self.assertEqual(rows[1].busan_coverage_pct, 5.0)
        self.assertEqual(rows[1].status, "partial")
        self.assertEqual(rows[2].coverage_pct, 0.0)
        self.assertEqual(rows[2].status, "missing")

    def test_write_feature_coverage_reports_creates_csv_and_markdown_summary(self):
        specs = [
            FeatureSpec("core_transaction", "exclusive_area_m2", "전용면적"),
            FeatureSpec("urban_competitiveness", "population_count", "인구 수"),
        ]
        rows = build_coverage_rows(
            specs,
            totals={"all": 10, "seoul": 6, "busan": 4},
            counts_by_column={
                "exclusive_area_m2": {"all": 10, "seoul": 6, "busan": 4},
                "population_count": {"all": 0, "seoul": 0, "busan": 0},
            },
        )
        summary = summarize_coverage_rows(rows, total_rows=10)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = write_feature_coverage_reports(rows, summary, Path(tmpdir))

            csv_path = Path(result["csv_output"])
            markdown_path = Path(result["markdown_output"])
            with csv_path.open(encoding="utf-8") as handle:
                csv_rows = list(csv.DictReader(handle))
            markdown = markdown_path.read_text(encoding="utf-8")

        self.assertEqual(len(csv_rows), 2)
        self.assertEqual(csv_rows[0]["column"], "exclusive_area_m2")
        self.assertEqual(csv_rows[1]["status"], "missing")
        self.assertIn("# Feature Coverage Report", markdown)
        self.assertIn("총 거래 행 수: 10", markdown)
        self.assertIn("population_count", markdown)


if __name__ == "__main__":
    unittest.main()
