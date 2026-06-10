import unittest

from sklearn.feature_extraction import DictVectorizer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.pipeline import Pipeline

from hedonic_house_price.linear_model import HistGradientBoostingPipeline


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
    def test_hist_gradient_boosting_pipeline_uses_sklearn_pipeline_components(self):
        rows = [
            row(1, district="강남구", target=11.0),
            row(2, district="마포구", target=13.0),
        ]
        pipeline = HistGradientBoostingPipeline(
            max_iter=7,
            learning_rate=0.04,
            max_leaf_nodes=15,
            min_samples_leaf=3,
            l2_regularization=0.2,
            random_state=11,
        )
        pipeline.fit(rows)

        self.assertIsInstance(pipeline.estimator, Pipeline)
        self.assertIsInstance(pipeline.estimator.named_steps["vectorizer"], DictVectorizer)
        self.assertFalse(pipeline.estimator.named_steps["vectorizer"].sparse)
        self.assertNotIn("scaler", pipeline.estimator.named_steps)
        self.assertIsInstance(pipeline.estimator.named_steps["hist_gradient_boosting"], HistGradientBoostingRegressor)
        self.assertEqual(pipeline.estimator.named_steps["hist_gradient_boosting"].max_iter, 7)
        self.assertEqual(pipeline.estimator.named_steps["hist_gradient_boosting"].learning_rate, 0.04)
        self.assertEqual(pipeline.estimator.named_steps["hist_gradient_boosting"].max_leaf_nodes, 15)
        self.assertEqual(pipeline.estimator.named_steps["hist_gradient_boosting"].min_samples_leaf, 3)
        self.assertEqual(pipeline.estimator.named_steps["hist_gradient_boosting"].l2_regularization, 0.2)
        self.assertEqual(pipeline.estimator.named_steps["hist_gradient_boosting"].random_state, 11)
        self.assertIn("__bias__", pipeline.estimator.named_steps["vectorizer"].feature_names_)

    def test_hist_gradient_boosting_pipeline_predicts_from_feature_rows_with_unseen_categories(self):
        rows = [
            row(1, district="강남구", target=11.0),
            row(2, district="강남구", target=13.0),
            row(3, district="마포구", target=15.0),
            row(4, district="마포구", target=17.0),
        ]
        pipeline = HistGradientBoostingPipeline(max_iter=20, min_samples_leaf=1, random_state=42)
        pipeline.fit(rows)

        prediction = pipeline.predict_one(row(5, district="마포구"))
        unseen_prediction = pipeline.predict_one(row(5, district="은평구"))

        self.assertGreaterEqual(prediction, 11.0)
        self.assertLessEqual(prediction, 17.0)
        self.assertIsInstance(unseen_prediction, float)


if __name__ == "__main__":
    unittest.main()
