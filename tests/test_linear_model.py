import unittest

from sklearn.feature_extraction import DictVectorizer
from sklearn.ensemble import RandomForestRegressor
from sklearn.pipeline import Pipeline

from hedonic_house_price.linear_model import RandomForestPipeline


def row(x, district="강남구", floor_band="floor_13_18", target=None):
    values = {
        "log_area_m2": float(x),
        "age": 10.0,
        "age_squared": 100.0,
        "floor": 14.0,
        "floor_squared": 196.0,
        "low_floor": 0.0,
        "deal_month_index": 1.0,
        "floor_band": floor_band,
        "calendar_month": "6",
        "district": district,
        "legal_dong": "역삼동",
    }
    if target is not None:
        values["target_log_price"] = target
    return values


class LinearModelTests(unittest.TestCase):
    def test_random_forest_pipeline_uses_sklearn_pipeline_components(self):
        rows = [
            row(1, district="강남구", target=11.0),
            row(2, district="마포구", target=13.0),
        ]
        pipeline = RandomForestPipeline(
            n_estimators=7,
            max_depth=5,
            min_samples_leaf=3,
            random_state=11,
            n_jobs=1,
        )
        pipeline.fit(rows)

        self.assertIsInstance(pipeline.estimator, Pipeline)
        self.assertIsInstance(pipeline.estimator.named_steps["vectorizer"], DictVectorizer)
        self.assertNotIn("scaler", pipeline.estimator.named_steps)
        self.assertIsInstance(pipeline.estimator.named_steps["random_forest"], RandomForestRegressor)
        self.assertEqual(pipeline.estimator.named_steps["random_forest"].n_estimators, 7)
        self.assertEqual(pipeline.estimator.named_steps["random_forest"].max_depth, 5)
        self.assertEqual(pipeline.estimator.named_steps["random_forest"].min_samples_leaf, 3)
        self.assertEqual(pipeline.estimator.named_steps["random_forest"].random_state, 11)
        self.assertEqual(pipeline.estimator.named_steps["random_forest"].n_jobs, 1)
        self.assertIn("__bias__", pipeline.estimator.named_steps["vectorizer"].feature_names_)

    def test_random_forest_pipeline_predicts_from_feature_rows_with_unseen_categories(self):
        rows = [
            row(1, district="강남구", target=11.0),
            row(2, district="강남구", target=13.0),
            row(3, district="마포구", target=15.0),
            row(4, district="마포구", target=17.0),
        ]
        pipeline = RandomForestPipeline(n_estimators=20, random_state=42, n_jobs=1)
        pipeline.fit(rows)

        prediction = pipeline.predict_one(row(5, district="마포구"))
        unseen_prediction = pipeline.predict_one(row(5, district="은평구"))

        self.assertGreaterEqual(prediction, 11.0)
        self.assertLessEqual(prediction, 17.0)
        self.assertIsInstance(unseen_prediction, float)


if __name__ == "__main__":
    unittest.main()
