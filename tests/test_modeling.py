import os
import tempfile
import unittest

from hedonic_house_price.modeling import (
    PredictionInput,
    load_model,
    predict_price,
    save_model,
    train_hedonic_model,
)
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


class ModelingTests(unittest.TestCase):
    def test_train_hedonic_model_reports_metrics_and_floor_residuals(self):
        model = train_hedonic_model(
            sample_transactions(),
            alpha=0.1,
            min_apartment_count=2,
            validation_months=2,
        )

        self.assertEqual(model.first_month, "202501")
        self.assertGreater(model.training_rows, 0)
        self.assertGreater(model.validation_rows, 0)
        self.assertIn("mae_krw", model.metrics)
        self.assertIn("mape", model.metrics)
        self.assertIn("floor_13_18", model.residuals_by_floor_band)
        self.assertEqual(model.common_apartments, set())
        feature_names = model.pipeline.estimator.named_steps["vectorizer"].feature_names_
        self.assertFalse(any("apartment_name" in name or "building_name" in name for name in feature_names))
        self.assertTrue(any("property_type=apartment" == name for name in feature_names))
        self.assertTrue(any("property_type=officetel" == name for name in feature_names))
        self.assertTrue(any("property_type=rowhouse" == name for name in feature_names))
        self.assertTrue(any("house_type=다세대" == name for name in feature_names))

    def test_train_hedonic_model_drops_constant_non_apartment_features(self):
        model = train_hedonic_model(
            apartment_only_transactions(),
            alpha=0.1,
            min_apartment_count=2,
            validation_months=2,
        )

        feature_names = model.pipeline.estimator.named_steps["vectorizer"].feature_names_
        self.assertFalse(any(name == "property_type=apartment" for name in feature_names))
        self.assertFalse(any(name == "house_type=unknown" for name in feature_names))
        self.assertFalse(any(name == "has_land_area" for name in feature_names))
        self.assertFalse(any(name == "log_land_area_m2" for name in feature_names))

    def test_train_hedonic_model_reports_progress_events_in_order(self):
        events = []

        train_hedonic_model(
            sample_transactions(),
            alpha=0.1,
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
        model = train_hedonic_model(sample_transactions(), alpha=0.1, min_apartment_count=2)

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
        model = train_hedonic_model(sample_transactions(), alpha=0.1, min_apartment_count=2)
        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as handle:
            path = handle.name

        try:
            save_model(model, path)
            with open(path, "rb") as handle:
                self.assertEqual(handle.read(1), b"\x80")
            restored = load_model(path)
            self.assertIn("ridge", restored.pipeline.estimator.named_steps)

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
