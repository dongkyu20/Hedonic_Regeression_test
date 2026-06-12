from __future__ import annotations

import os
from dataclasses import dataclass

os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(os.cpu_count() or 1))

from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.feature_extraction import DictVectorizer
from sklearn.pipeline import Pipeline


@dataclass
class HistGradientBoostingPipeline:
    max_iter: int = 300
    learning_rate: float = 0.06
    max_leaf_nodes: int = 31
    min_samples_leaf: int = 30
    l2_regularization: float = 0.0
    random_state: int = 42
    estimator: Pipeline | None = None
    target_name: str = "target_log_price"

    def fit(self, rows: list[dict[str, object]], target_name: str = "target_log_price") -> "HistGradientBoostingPipeline":
        if not rows:
            raise ValueError("cannot fit model on empty rows")

        self.target_name = target_name
        x_rows = [_without_target(row, target_name) for row in rows]
        y = [float(row[target_name]) for row in rows]
        self.estimator = Pipeline(
            [
                ("vectorizer", DictVectorizer(sparse=False)),
                (
                    "hist_gradient_boosting",
                    HistGradientBoostingRegressor(
                        max_iter=self.max_iter,
                        learning_rate=self.learning_rate,
                        max_leaf_nodes=self.max_leaf_nodes,
                        min_samples_leaf=self.min_samples_leaf,
                        l2_regularization=self.l2_regularization,
                        random_state=self.random_state,
                    ),
                ),
            ]
        )
        self.estimator.fit(x_rows, y)
        return self

    def predict(self, rows: list[dict[str, object]]) -> list[float]:
        if self.estimator is None:
            raise ValueError("pipeline is not fitted")
        x_rows = [_without_target(row, self.target_name) for row in rows]
        return [float(value) for value in self.estimator.predict(x_rows)]

    def predict_one(self, row: dict[str, object]) -> float:
        return self.predict([row])[0]


def _without_target(row: dict[str, object], target_name: str) -> dict[str, object]:
    features = {key: value for key, value in row.items() if key != target_name}
    features["__bias__"] = 1.0
    return features


RandomForestPipeline = HistGradientBoostingPipeline
ElasticNetPipeline = HistGradientBoostingPipeline
RidgePipeline = HistGradientBoostingPipeline
