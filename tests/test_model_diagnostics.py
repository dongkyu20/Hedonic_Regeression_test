import csv
import math
import tempfile
import unittest
from pathlib import Path

from hedonic_house_price.model_diagnostics import generate_residual_diagnostics
from hedonic_house_price.modeling import TrainedModel
from hedonic_house_price.transactions import Transaction


class FakePipeline:
    def predict(self, rows):
        return [math.log(900_000_000), math.log(1_200_000_000)]


def tx(month, city_code, price_manwon, floor=10, area=84.9):
    return Transaction(
        district="강남구" if city_code == "seoul" else "해운대구",
        lawd_cd="11680" if city_code == "seoul" else "26350",
        deal_year=2025,
        deal_month=month,
        deal_day=10,
        legal_dong="역삼동" if city_code == "seoul" else "우동",
        building_name="테스트단지",
        exclusive_area_m2=area,
        floor=floor,
        build_year=2005,
        price_manwon=price_manwon,
        extra_features={
            "city_code": city_code,
            "household_count": 1200,
            "building_count": 8,
            "parking_spaces_per_household": 1.2,
            "nearest_subway_distance_m": 420.0,
            "subway_count_radius": 2,
            "nearest_bus_stop_distance_m": 80.0,
            "bus_stop_count_radius": 12,
            "nearest_elementary_school_distance_m": 240.0,
            "school_count_radius": 3,
            "academy_count_radius": 18,
            "nearest_hospital_distance_m": 620.0,
            "nearest_pharmacy_distance_m": 140.0,
            "nearest_park_distance_m": 350.0,
            "park_area_total_m2_radius": 3000.0,
        },
    )


class ModelDiagnosticsTests(unittest.TestCase):
    def test_generate_residual_diagnostics_writes_condition_reports(self):
        model = TrainedModel(
            pipeline=FakePipeline(),
            first_month="202501",
            common_apartments=set(),
            metrics={},
            residuals_by_floor_band={},
            training_rows=4,
            validation_rows=2,
        )
        transactions = [
            tx(1, "seoul", 80_000),
            tx(2, "seoul", 82_000),
            tx(3, "busan", 70_000),
            tx(4, "busan", 72_000),
            tx(5, "seoul", 100_000, floor=15, area=84.9),
            tx(6, "busan", 100_000, floor=2, area=59.8),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            result = generate_residual_diagnostics(
                model,
                transactions,
                output_dir=tmpdir,
                validation_months=2,
                min_segment_count=1,
            )

            residual_path = Path(result["residual_segments_csv"])
            top_path = Path(result["top_error_segments_csv"])
            summary_path = Path(result["summary_markdown"])

            self.assertEqual(result["validation_rows"], 2)
            self.assertTrue(residual_path.exists())
            self.assertTrue(top_path.exists())
            self.assertTrue(summary_path.exists())

            with residual_path.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertTrue(any(row["segment_name"] == "city_code" and row["condition"] == "seoul" for row in rows))
            self.assertTrue(any(row["segment_name"] == "city_code" and row["condition"] == "busan" for row in rows))
            self.assertTrue(any(row["segment_name"] == "floor_band" and row["condition"] == "floor_13_18" for row in rows))
            self.assertTrue(any(row["segment_name"] == "area_m2_bin" and row["condition"] == "area_40_60" for row in rows))
            self.assertTrue(any(float(row["mape"]) > 0 for row in rows))

            with top_path.open(encoding="utf-8") as handle:
                top_rows = list(csv.DictReader(handle))
            self.assertGreater(len(top_rows), 0)
            self.assertIn("잔차 해석", summary_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
