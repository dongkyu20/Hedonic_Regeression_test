from __future__ import annotations

from dataclasses import dataclass

from sklearn.ensemble import RandomForestRegressor
from sklearn.feature_extraction import DictVectorizer
from sklearn.pipeline import Pipeline


@dataclass
class RandomForestPipeline:
    n_estimators: int = 40
    max_depth: int | None = 20
    min_samples_leaf: int = 5
    random_state: int = 42
    n_jobs: int = -1
    estimator: Pipeline | None = None
    target_name: str = "target_log_price"

    def fit(self, rows: list[dict[str, object]], target_name: str = "target_log_price") -> "RandomForestPipeline":
        if not rows:
            raise ValueError("cannot fit model on empty rows")

        self.target_name = target_name
        x_rows = [_without_target(row, target_name) for row in rows]
        y = [float(row[target_name]) for row in rows]
        self.estimator = Pipeline(
            [
                ("vectorizer", DictVectorizer(sparse=True)),
                (
                    "random_forest",
                    RandomForestRegressor(
                        n_estimators=self.n_estimators,
                        max_depth=self.max_depth,
                        min_samples_leaf=self.min_samples_leaf,
                        random_state=self.random_state,
                        n_jobs=self.n_jobs,
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


ElasticNetPipeline = RandomForestPipeline
RidgePipeline = RandomForestPipeline
