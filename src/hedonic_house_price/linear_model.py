from __future__ import annotations

from dataclasses import dataclass

from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import ElasticNet
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


@dataclass
class ElasticNetPipeline:
    alpha: float = 1.0
    l1_ratio: float = 0.5
    max_iter: int = 5000
    estimator: Pipeline | None = None
    target_name: str = "target_log_price"

    def fit(self, rows: list[dict[str, object]], target_name: str = "target_log_price") -> "ElasticNetPipeline":
        if not rows:
            raise ValueError("cannot fit model on empty rows")

        self.target_name = target_name
        x_rows = [_without_target(row, target_name) for row in rows]
        y = [float(row[target_name]) for row in rows]
        self.estimator = Pipeline(
            [
                ("vectorizer", DictVectorizer(sparse=True)),
                ("scaler", StandardScaler(with_mean=False)),
                (
                    "elastic_net",
                    ElasticNet(
                        alpha=self.alpha,
                        l1_ratio=self.l1_ratio,
                        max_iter=self.max_iter,
                        fit_intercept=False,
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


RidgePipeline = ElasticNetPipeline
