import math
import os
import tempfile
import unittest

from hedonic_house_price.modeling import (
    PredictionInput,
    TARGET_ENCODING_SMOOTHING,
    TrainedModel,
    global_calibration_log_offset,
    load_model,
    predict_price,
    save_model,
    train_hedonic_model,
)
from hedonic_house_price.features import complex_floor_key
from hedonic_house_price.transactions import Transaction


def sample_transactions():
    rows = []
    for idx in range(12):
        month = idx + 1
        floor = [2, 6, 10, 15, 22, 28][idx % 6]
        area = 59.8 if idx % 2 == 0 else 84.9
        district = "강남구" if idx % 3 else "마포구"
        legal_dong = "역삼동" if district == "강남구" else "공덕동"
        building_name = "반복단지" if idx < 8 else f"희귀단지{idx}"
        property_type = ["apartment", "officetel", "rowhouse"][idx % 3]
        house_type = "다세대" if property_type == "rowhouse" else ""
        land_area_m2 = 18.0 + idx if property_type == "rowhouse" else None
        mid_floor_bonus = 80_000_000 if 13 <= floor <= 18 else 0
        price_krw = 450_000_000 + int(area * 5_000_000) + idx * 8_000_000 + mid_floor_bonus
        rows.append(
            Transaction(
                district=district,
                lawd_cd="11680" if district == "강남구" else "11440",
                deal_year=2025,
                deal_month=month,
                deal_day=10,
                legal_dong=legal_dong,
                building_name=building_name,
                property_type=property_type,
                house_type=house_type,
                land_area_m2=land_area_m2,
                exclusive_area_m2=area,
                floor=floor,
                build_year=2008,
                price_manwon=price_krw // 10_000,
            )
        )
    return rows


def apartment_only_transactions():
    rows = []
    for idx in range(12):
        rows.append(
            Transaction(
                district="강남구",
                lawd_cd="11680",
                deal_year=2025,
                deal_month=idx + 1,
                deal_day=10,
                legal_dong="역삼동",
                building_name="반복단지",
                property_type="apartment",
                exclusive_area_m2=84.9,
                floor=[2, 6, 10, 15][idx % 4],
                build_year=2008,
                price_manwon=90_000 + idx * 1_000,
            )
        )
    return rows


def enriched_apartment_transactions():
    rows = apartment_only_transactions()
    for idx, transaction in enumerate(rows):
        object.__setattr__(transaction, "build_year", 1988 + idx * 3)
        object.__setattr__(transaction, "exclusive_area_m2", 59.8 if idx % 2 == 0 else 84.9)
        object.__setattr__(
            transaction,
            "extra_features",
            {
                "city_code": "seoul" if idx < 6 else "busan",
                "household_count": 800 + idx * 50,
                "building_count": 4 + (idx % 3),
                "total_parking_spaces": 900 + idx * 40,
                "parking_spaces_per_household": 1.0 + idx * 0.02,
                "has_community_facilities": 1 if idx % 2 == 0 else 0,
                "nearest_subway_distance_m": 250.0 + idx * 45,
                "subway_count_radius": idx % 4,
                "nearest_bus_stop_distance_m": 80.0 + idx * 6,
                "bus_stop_count_radius": 10 + idx,
                "car_airport_minutes": 45.0 + idx,
                "nearest_elementary_school_distance_m": 180.0 + idx * 12,
                "school_count_radius": 1 + idx % 5,
                "academy_count_radius": 5 + idx * 2,
                "nearest_hospital_distance_m": 300.0 + idx * 15,
                "nearest_pharmacy_distance_m": 120.0 + idx * 8,
                "nearest_park_distance_m": 220.0 + idx * 11,
                "park_area_total_m2_radius": 0.0 if idx % 4 == 0 else 1500.0 + idx * 250,
            },
        )
    return rows


class ModelingTests(unittest.TestCase):
    def test_train_hedonic_model_reports_metrics_and_floor_residuals(self):
        model = train_hedonic_model(
            sample_transactions(),
            max_iter=20,
            random_state=42,
            min_apartment_count=2,
            validation_months=2,
        )

        self.assertEqual(model.first_month, "202501")
        self.assertGreater(model.training_rows, 0)
        self.assertGreater(model.validation_rows, 0)
        self.assertIn("mae_krw", model.metrics)
        self.assertIn("mape", model.metrics)
        self.assertIn("floor_13_18", model.residuals_by_floor_band)
        self.assertGreater(len(model.estimated_max_floors), 0)
        self.assertIsInstance(model.dropped_features, set)
        self.assertEqual(model.common_apartments, set())
        feature_names = model.pipeline.estimator.named_steps["vectorizer"].feature_names_
        self.assertIn("hist_gradient_boosting", model.pipeline.estimator.named_steps)
        self.assertFalse(any("apartment_name" in name or "building_name" in name for name in feature_names))
        self.assertTrue(any("property_type=apartment" == name for name in feature_names))
        self.assertTrue(any("property_type=officetel" == name for name in feature_names))
        self.assertTrue(any("property_type=rowhouse" == name for name in feature_names))
        self.assertTrue(any("house_type=다세대" == name for name in feature_names))

    def test_train_hedonic_model_drops_constant_non_apartment_features(self):
        model = train_hedonic_model(
            apartment_only_transactions(),
            max_iter=20,
            random_state=42,
            min_apartment_count=2,
            validation_months=2,
        )

        feature_names = model.pipeline.estimator.named_steps["vectorizer"].feature_names_
        self.assertFalse(any(name == "property_type=apartment" for name in feature_names))
        self.assertFalse(any(name == "house_type=unknown" for name in feature_names))
        self.assertFalse(any(name == "has_land_area" for name in feature_names))
        self.assertFalse(any(name == "log_land_area_m2" for name in feature_names))

    def test_train_hedonic_model_uses_preprocessed_db_feature_set(self):
        model = train_hedonic_model(
            enriched_apartment_transactions(),
            max_iter=20,
            random_state=42,
            min_apartment_count=2,
            validation_months=2,
        )

        feature_names = model.pipeline.estimator.named_steps["vectorizer"].feature_names_
        self.assertTrue(any(name.startswith("age_band=") for name in feature_names))
        self.assertTrue(any(name.startswith("floor_band=") for name in feature_names))
        self.assertTrue(any(name.startswith("subway_count_radius_bin=") for name in feature_names))
        self.assertTrue(any(name.startswith("academy_count_radius_bin=") for name in feature_names))
        self.assertIn("relative_floor", feature_names)
        self.assertIn("is_floor_2_3", feature_names)
        self.assertIn("log_area_m2", feature_names)
        self.assertIn("log_household_count", feature_names)
        self.assertIn("households_per_building", feature_names)
        self.assertIn("log_total_parking_spaces", feature_names)
        self.assertIn("parking_spaces_per_household", feature_names)
        self.assertIn("log_nearest_subway_distance_m", feature_names)
        self.assertIn("log_car_airport_minutes", feature_names)
        self.assertIn("park_exists", feature_names)
        self.assertIn("log_park_area_total_m2_radius", feature_names)
        self.assertNotIn("age", feature_names)
        self.assertNotIn("age_squared", feature_names)
        self.assertNotIn("floor", feature_names)
        self.assertNotIn("floor_squared", feature_names)
        self.assertNotIn("building_count", feature_names)

    def test_train_hedonic_model_stores_observed_complex_floor_estimates(self):
        transactions = [
            Transaction(
                district="강남구",
                lawd_cd="11680",
                deal_year=2025,
                deal_month=idx + 1,
                deal_day=10,
                legal_dong="역삼동",
                building_name="추정단지",
                property_type="apartment",
                exclusive_area_m2=84.9,
                floor=floor,
                build_year=2008,
                price_manwon=90_000 + idx * 1_000,
            )
            for idx, floor in enumerate([1, 2, 4, 7, 7, 6, 5, 3])
        ]

        model = train_hedonic_model(
            transactions,
            max_iter=20,
            random_state=42,
            validation_months=2,
        )

        self.assertEqual(model.estimated_max_floors[complex_floor_key(transactions[0])], 7)

    def test_train_hedonic_model_estimates_max_floor_from_training_split_only(self):
        transactions = [
            Transaction(
                district="강남구",
                lawd_cd="11680",
                deal_year=2025,
                deal_month=idx + 1,
                deal_day=10,
                legal_dong="역삼동",
                building_name="검증누수방지단지",
                property_type="apartment",
                exclusive_area_m2=84.9,
                floor=floor,
                build_year=2008,
                price_manwon=90_000 + idx * 1_000,
            )
            for idx, floor in enumerate([1, 2, 4, 7, 7, 6, 21, 5])
        ]

        model = train_hedonic_model(
            transactions,
            max_iter=20,
            min_samples_leaf=1,
            random_state=42,
            validation_months=2,
        )

        self.assertEqual(model.estimated_max_floors[complex_floor_key(transactions[0])], 7)

    def test_train_hedonic_model_uses_external_complex_floor_estimates(self):
        transactions = [
            Transaction(
                district="강남구",
                lawd_cd="11680",
                deal_year=2025,
                deal_month=idx + 1,
                deal_day=10,
                legal_dong="역삼동",
                building_name="외부최고층단지",
                property_type="apartment",
                exclusive_area_m2=84.9,
                floor=floor,
                build_year=2008,
                price_manwon=90_000 + idx * 1_000,
            )
            for idx, floor in enumerate([1, 2, 4, 7, 7, 6, 5, 3])
        ]
        key = complex_floor_key(transactions[0])

        model = train_hedonic_model(
            transactions,
            max_iter=20,
            random_state=42,
            validation_months=2,
            estimated_max_floors={key: 29},
        )

        self.assertEqual(model.estimated_max_floors[key], 29)

    def test_train_hedonic_model_adds_training_split_smoothed_target_encodings(self):
        transactions = []
        for idx, (district, lawd_cd, legal_dong, price_manwon) in enumerate(
            [
                ("강남구", "11680", "역삼동", 90_000),
                ("강남구", "11680", "역삼동", 91_000),
                ("강남구", "11680", "역삼동", 92_000),
                ("마포구", "11440", "공덕동", 60_000),
                ("마포구", "11440", "공덕동", 61_000),
                ("마포구", "11440", "공덕동", 62_000),
                ("강남구", "11680", "역삼동", 300_000),
                ("강남구", "11680", "역삼동", 320_000),
            ]
        ):
            transactions.append(
                Transaction(
                    district=district,
                    lawd_cd=lawd_cd,
                    deal_year=2025,
                    deal_month=idx + 1,
                    deal_day=10,
                    legal_dong=legal_dong,
                    building_name="인코딩단지",
                    property_type="apartment",
                    exclusive_area_m2=84.9,
                    floor=[2, 6, 10, 15][idx % 4],
                    build_year=2008,
                    price_manwon=price_manwon,
                )
            )

        model = train_hedonic_model(
            transactions,
            max_iter=20,
            min_samples_leaf=1,
            random_state=42,
            validation_months=2,
        )

        train_log_prices = [math.log(transaction.price_krw) for transaction in transactions[:6]]
        global_mean = sum(train_log_prices) / len(train_log_prices)
        gangnam_logs = train_log_prices[:3]
        expected_gangnam = (sum(gangnam_logs) + TARGET_ENCODING_SMOOTHING * global_mean) / (
            len(gangnam_logs) + TARGET_ENCODING_SMOOTHING
        )

        self.assertAlmostEqual(model.target_encodings.global_mean, global_mean)
        self.assertAlmostEqual(
            model.target_encodings.values["legal_dong"]["역삼동"],
            expected_gangnam,
        )
        self.assertEqual(model.target_encodings.counts["legal_dong"]["역삼동"], 3)
        feature_names = model.pipeline.estimator.named_steps["vectorizer"].feature_names_
        self.assertIn("legal_dong_target_log_price_smooth", feature_names)
        self.assertIn("district_target_log_price_smooth", feature_names)

    def test_predict_price_applies_target_encodings_and_dropped_features(self):
        class CapturingPipeline:
            def __init__(self):
                self.row = {}

            def predict_one(self, row):
                self.row = row
                return math.log(100_000_000)

        pipeline = CapturingPipeline()
        model = TrainedModel(
            pipeline=pipeline,
            first_month="202501",
            common_apartments=set(),
            metrics={},
            residuals_by_floor_band={},
            training_rows=1,
            validation_rows=0,
            dropped_features={"district"},
        )
        model.target_encodings.global_mean = 20.0
        model.target_encodings.values = {
            "district": {"강남구": 21.0},
            "legal_dong": {"역삼동": 22.0},
        }
        model.target_encodings.counts = {
            "district": {"강남구": 10},
            "legal_dong": {"역삼동": 5},
        }

        predict_price(
            model,
            PredictionInput(
                district="강남구",
                lawd_cd="11680",
                deal_year=2025,
                deal_month=12,
                deal_day=15,
                legal_dong="역삼동",
                apartment_name="인코딩단지",
                property_type="apartment",
                exclusive_area_m2=84.9,
                floor=10,
                build_year=2008,
            ),
        )

        self.assertNotIn("district", pipeline.row)
        self.assertEqual(pipeline.row["district_target_log_price_smooth"], 21.0)
        self.assertEqual(pipeline.row["district_target_count_log1p"], math.log1p(10))
        self.assertEqual(pipeline.row["legal_dong_target_log_price_smooth"], 22.0)
        self.assertEqual(pipeline.row["legal_dong_target_count_log1p"], math.log1p(5))

    def test_global_calibration_log_offset_is_shrunk_and_capped(self):
        class UnderpredictingPipeline:
            def predict(self, rows):
                return [float(row["target_log_price"]) - 0.08 for row in rows]

        offset = global_calibration_log_offset(
            UnderpredictingPipeline(),
            [{"target_log_price": math.log(100_000_000)}, {"target_log_price": math.log(120_000_000)}],
            shrinkage=0.25,
            max_abs_log_offset=0.01,
        )

        self.assertAlmostEqual(offset, 0.01)

    def test_predict_price_applies_global_calibration_log_offset(self):
        class ConstantPipeline:
            def predict_one(self, row):
                return math.log(100_000_000)

        model = TrainedModel(
            pipeline=ConstantPipeline(),
            first_month="202501",
            common_apartments=set(),
            metrics={},
            residuals_by_floor_band={},
            training_rows=1,
            validation_rows=0,
            global_calibration_log_offset=math.log(1.01),
        )

        prediction = predict_price(
            model,
            PredictionInput(
                district="강남구",
                lawd_cd="11680",
                deal_year=2025,
                deal_month=12,
                deal_day=15,
                legal_dong="역삼동",
                apartment_name="보정단지",
                property_type="apartment",
                exclusive_area_m2=84.9,
                floor=10,
                build_year=2008,
            ),
        )

        self.assertEqual(prediction["price_krw"], 101_000_000)

    def test_train_hedonic_model_reports_progress_events_in_order(self):
        events = []

        train_hedonic_model(
            sample_transactions(),
            max_iter=20,
            random_state=42,
            min_apartment_count=2,
            validation_months=2,
            progress=events.append,
        )

        self.assertEqual(
            [event["stage"] for event in events],
            [
                "sort",
                "split",
                "exclude_apartment_name",
                "features_train",
                "features_validation",
                "fit",
                "evaluate",
                "residuals",
                "complete",
            ],
        )
        self.assertEqual(events[0]["rows"], 12)
        self.assertGreater(events[5]["training_rows"], 0)

    def test_predict_price_returns_krw_and_manwon_values(self):
        model = train_hedonic_model(
            sample_transactions(),
            max_iter=20,
            random_state=42,
            min_apartment_count=2,
        )

        prediction = predict_price(
            model,
            PredictionInput(
                district="강남구",
                lawd_cd="11680",
                deal_year=2025,
                deal_month=12,
                deal_day=15,
                legal_dong="역삼동",
                apartment_name="반복단지",
                property_type="officetel",
                exclusive_area_m2=84.9,
                floor=15,
                build_year=2008,
            ),
        )

        self.assertGreater(prediction["price_krw"], 100_000_000)
        self.assertEqual(prediction["price_manwon"], round(prediction["price_krw"] / 10_000))

    def test_model_artifact_round_trips_as_sklearn_pickle(self):
        model = train_hedonic_model(
            sample_transactions(),
            max_iter=20,
            random_state=42,
            min_apartment_count=2,
        )
        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as handle:
            path = handle.name

        try:
            save_model(model, path)
            with open(path, "rb") as handle:
                self.assertEqual(handle.read(1), b"\x80")
            restored = load_model(path)
            self.assertIn("hist_gradient_boosting", restored.pipeline.estimator.named_steps)

            original = predict_price(
                model,
                PredictionInput(
                    district="강남구",
                    lawd_cd="11680",
                    deal_year=2025,
                    deal_month=12,
                    deal_day=15,
                    legal_dong="역삼동",
                    apartment_name="반복단지",
                    property_type="rowhouse",
                    exclusive_area_m2=84.9,
                    floor=15,
                    build_year=2008,
                ),
            )
            loaded = predict_price(
                restored,
                PredictionInput(
                    district="강남구",
                    lawd_cd="11680",
                    deal_year=2025,
                    deal_month=12,
                    deal_day=15,
                    legal_dong="역삼동",
                    apartment_name="반복단지",
                    property_type="rowhouse",
                    exclusive_area_m2=84.9,
                    floor=15,
                    build_year=2008,
                ),
            )
            self.assertEqual(loaded["price_krw"], original["price_krw"])
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
