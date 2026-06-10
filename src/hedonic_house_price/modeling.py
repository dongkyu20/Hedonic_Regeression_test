from __future__ import annotations

import math
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .features import estimate_complex_max_floors, make_feature_row, make_feature_rows
from .linear_model import HistGradientBoostingPipeline
from .transactions import Transaction, normalize_property_type


TARGET_ENCODING_COLUMNS = ("district", "legal_dong")
TARGET_ENCODING_SMOOTHING = 20.0


@dataclass(frozen=True)
class PredictionInput:
    district: str
    lawd_cd: str
    deal_year: int
    deal_month: int
    deal_day: int
    legal_dong: str
    apartment_name: str
    exclusive_area_m2: float
    floor: int
    build_year: int
    property_type: str = "apartment"
    house_type: str = ""
    land_area_m2: float | None = None

    def to_transaction(self) -> Transaction:
        return Transaction(
            property_type=normalize_property_type(self.property_type),
            district=self.district,
            lawd_cd=self.lawd_cd,
            deal_year=self.deal_year,
            deal_month=self.deal_month,
            deal_day=self.deal_day,
            legal_dong=self.legal_dong,
            apartment_name=self.apartment_name,
            house_type=self.house_type,
            land_area_m2=self.land_area_m2,
            exclusive_area_m2=self.exclusive_area_m2,
            floor=self.floor,
            build_year=self.build_year,
            price_manwon=1,
        )


@dataclass
class TargetEncodingMap:
    global_mean: float = 0.0
    smoothing: float = TARGET_ENCODING_SMOOTHING
    values: dict[str, dict[str, float]] = field(default_factory=dict)
    counts: dict[str, dict[str, int]] = field(default_factory=dict)


@dataclass
class TrainedModel:
    pipeline: HistGradientBoostingPipeline
    first_month: str
    common_apartments: set[str]
    metrics: dict[str, float]
    residuals_by_floor_band: dict[str, dict[str, float]]
    training_rows: int
    validation_rows: int
    estimated_max_floors: dict[tuple[str, str, str, str], int] = field(default_factory=dict)
    dropped_features: set[str] = field(default_factory=set)
    target_encodings: TargetEncodingMap = field(default_factory=TargetEncodingMap)

def train_hedonic_model(
    transactions: list[Transaction],
    max_iter: int = 300,
    learning_rate: float = 0.06,
    max_leaf_nodes: int = 31,
    min_samples_leaf: int = 30,
    l2_regularization: float = 0.0,
    random_state: int = 42,
    min_apartment_count: int = 5,
    validation_months: int = 6,
    progress: Callable[[dict[str, object]], None] | None = None,
) -> TrainedModel:
    usable = sorted(transactions, key=lambda transaction: transaction.deal_ymd)
    if not usable:
        raise ValueError("no transactions provided")
    _report(progress, "sort", rows=len(usable))

    train_transactions, validation_transactions = _chronological_split(usable, validation_months)
    first_month = min(transaction.deal_yyyymm for transaction in usable)
    _report(
        progress,
        "split",
        training_rows=len(train_transactions),
        validation_rows=len(validation_transactions),
        first_month=first_month,
    )

    common_apartments: set[str] = set()
    _report(progress, "exclude_apartment_name")
    estimated_max_floors = estimate_complex_max_floors(train_transactions)

    raw_train_rows = make_feature_rows(
        train_transactions,
        first_month=first_month,
        estimated_max_floors=estimated_max_floors,
    )
    target_encodings = fit_target_encodings(raw_train_rows)
    raw_train_rows = apply_target_encodings(raw_train_rows, target_encodings)
    dropped_feature_names = _constant_feature_names(raw_train_rows)
    train_rows = _drop_features(
        raw_train_rows,
        dropped_feature_names,
    )
    _report(progress, "features_train", rows=len(train_rows))

    raw_validation_rows = make_feature_rows(
        validation_transactions,
        first_month=first_month,
        estimated_max_floors=estimated_max_floors,
    )
    raw_validation_rows = apply_target_encodings(raw_validation_rows, target_encodings)
    validation_rows = _drop_features(
        raw_validation_rows,
        dropped_feature_names,
    )
    _report(progress, "features_validation", rows=len(validation_rows))

    pipeline = HistGradientBoostingPipeline(
        max_iter=max_iter,
        learning_rate=learning_rate,
        max_leaf_nodes=max_leaf_nodes,
        min_samples_leaf=min_samples_leaf,
        l2_regularization=l2_regularization,
        random_state=random_state,
    ).fit(train_rows)
    _report(
        progress,
        "fit",
        training_rows=len(train_rows),
        max_iter=max_iter,
        learning_rate=learning_rate,
        max_leaf_nodes=max_leaf_nodes,
        min_samples_leaf=min_samples_leaf,
        l2_regularization=l2_regularization,
        random_state=random_state,
    )

    metrics = evaluate_rows(pipeline, validation_rows or train_rows)
    _report(progress, "evaluate", rows=len(validation_rows or train_rows), mape=metrics["mape"], r2_log=metrics["r2_log"])

    all_rows = _drop_features(
        apply_target_encodings(
            make_feature_rows(
                usable,
                first_month=first_month,
                estimated_max_floors=estimated_max_floors,
            ),
            target_encodings,
        ),
        dropped_feature_names,
    )
    residuals_by_floor_band = residuals_by_group(pipeline, all_rows, group_name="floor_band")
    _report(progress, "residuals", rows=len(all_rows), floor_bands=len(residuals_by_floor_band))

    model = TrainedModel(
        pipeline=pipeline,
        first_month=first_month,
        common_apartments=common_apartments,
        metrics=metrics,
        residuals_by_floor_band=residuals_by_floor_band,
        training_rows=len(train_rows),
        validation_rows=len(validation_rows),
        estimated_max_floors=estimated_max_floors,
        dropped_features=dropped_feature_names,
        target_encodings=target_encodings,
    )
    _report(progress, "complete", training_rows=model.training_rows, validation_rows=model.validation_rows)
    return model


def predict_price(model: TrainedModel, prediction_input: PredictionInput) -> dict[str, int | float]:
    feature_row = _drop_features(
        [
            apply_target_encoding(
                make_feature_row(
                    prediction_input.to_transaction(),
                    first_month=model.first_month,
                    estimated_max_floors=getattr(model, "estimated_max_floors", {}),
                ),
                getattr(model, "target_encodings", TargetEncodingMap()),
            )
        ],
        getattr(model, "dropped_features", set()),
    )
    predicted_log_price = model.pipeline.predict_one(feature_row[0])
    price_krw = int(round(math.exp(predicted_log_price)))
    return {
        "log_price": predicted_log_price,
        "price_krw": price_krw,
        "price_manwon": round(price_krw / 10_000),
    }


def fit_target_encodings(
    rows: list[dict[str, object]],
    *,
    columns: tuple[str, ...] = TARGET_ENCODING_COLUMNS,
    smoothing: float = TARGET_ENCODING_SMOOTHING,
) -> TargetEncodingMap:
    target_values = [float(row["target_log_price"]) for row in rows if "target_log_price" in row]
    global_mean = sum(target_values) / len(target_values) if target_values else 0.0
    values: dict[str, dict[str, float]] = {}
    counts: dict[str, dict[str, int]] = {}

    for column in columns:
        grouped: dict[str, list[float]] = {}
        for row in rows:
            if column not in row or "target_log_price" not in row:
                continue
            grouped.setdefault(str(row[column]), []).append(float(row["target_log_price"]))

        values[column] = {
            category: (sum(category_values) + smoothing * global_mean) / (len(category_values) + smoothing)
            for category, category_values in grouped.items()
        }
        counts[column] = {
            category: len(category_values)
            for category, category_values in grouped.items()
        }

    return TargetEncodingMap(
        global_mean=global_mean,
        smoothing=smoothing,
        values=values,
        counts=counts,
    )


def apply_target_encodings(
    rows: list[dict[str, object]],
    target_encodings: TargetEncodingMap,
) -> list[dict[str, object]]:
    return [apply_target_encoding(row, target_encodings) for row in rows]


def apply_target_encoding(
    row: dict[str, object],
    target_encodings: TargetEncodingMap,
) -> dict[str, object]:
    encoded_row = dict(row)
    for column in TARGET_ENCODING_COLUMNS:
        category = str(row.get(column, ""))
        value = target_encodings.values.get(column, {}).get(category, target_encodings.global_mean)
        count = target_encodings.counts.get(column, {}).get(category, 0)
        encoded_row[f"{column}_target_log_price_smooth"] = value
        encoded_row[f"{column}_target_log_price_delta"] = value - target_encodings.global_mean
        encoded_row[f"{column}_target_count_log1p"] = math.log1p(count)
    return encoded_row


def evaluate_rows(pipeline: HistGradientBoostingPipeline, rows: list[dict[str, object]]) -> dict[str, float]:
    if not rows:
        raise ValueError("cannot evaluate empty rows")

    actual_log = [float(row["target_log_price"]) for row in rows]
    predicted_log = pipeline.predict(rows)
    actual_krw = [math.exp(value) for value in actual_log]
    predicted_krw = [math.exp(value) for value in predicted_log]
    errors = [actual - predicted for actual, predicted in zip(actual_krw, predicted_krw)]

    mae = sum(abs(error) for error in errors) / len(errors)
    rmse = math.sqrt(sum(error * error for error in errors) / len(errors))
    mape = sum(abs(error) / actual for error, actual in zip(errors, actual_krw) if actual != 0) / len(errors)

    mean_log = sum(actual_log) / len(actual_log)
    sse = sum((actual - predicted) ** 2 for actual, predicted in zip(actual_log, predicted_log))
    sst = sum((actual - mean_log) ** 2 for actual in actual_log)
    r2 = 1.0 - sse / sst if sst else 0.0

    return {
        "mae_krw": mae,
        "rmse_krw": rmse,
        "mape": mape,
        "r2_log": r2,
    }


def residuals_by_group(
    pipeline: HistGradientBoostingPipeline,
    rows: list[dict[str, object]],
    group_name: str,
) -> dict[str, dict[str, float]]:
    predictions = pipeline.predict(rows)
    grouped: dict[str, list[float]] = {}
    for row, predicted_log in zip(rows, predictions):
        actual_krw = math.exp(float(row["target_log_price"]))
        predicted_krw = math.exp(predicted_log)
        group = str(row[group_name])
        grouped.setdefault(group, []).append(actual_krw - predicted_krw)

    return {
        group: {
            "count": float(len(errors)),
            "mean_error_krw": sum(errors) / len(errors),
        }
        for group, errors in sorted(grouped.items())
    }


def save_model(model: TrainedModel, path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as handle:
        pickle.dump(model, handle, protocol=pickle.HIGHEST_PROTOCOL)


def load_model(path: str | Path) -> TrainedModel:
    with Path(path).open("rb") as handle:
        model = pickle.load(handle)
    if not isinstance(model, TrainedModel):
        raise ValueError("model artifact does not contain a TrainedModel")
    return model


def _report(progress: Callable[[dict[str, object]], None] | None, stage: str, **payload: object) -> None:
    if progress is not None:
        event = {"stage": stage}
        event.update(payload)
        progress(event)


def _chronological_split(
    transactions: list[Transaction],
    validation_months: int,
) -> tuple[list[Transaction], list[Transaction]]:
    if len(transactions) < 4:
        return transactions, []

    months = sorted({transaction.deal_yyyymm for transaction in transactions})
    if validation_months > 0 and len(months) > validation_months:
        validation_set = set(months[-validation_months:])
        train = [transaction for transaction in transactions if transaction.deal_yyyymm not in validation_set]
        validation = [transaction for transaction in transactions if transaction.deal_yyyymm in validation_set]
        if train and validation:
            return train, validation

    cutoff = max(1, int(len(transactions) * 0.8))
    return transactions[:cutoff], transactions[cutoff:]


def _constant_feature_names(rows: list[dict[str, object]]) -> set[str]:
    if not rows:
        return set()

    dropped: set[str] = set()
    feature_names = set().union(*(row.keys() for row in rows))
    feature_names.discard("target_log_price")
    for feature_name in feature_names:
        values = {row.get(feature_name) for row in rows}
        if len(values) <= 1:
            dropped.add(feature_name)

    return dropped


def _drop_features(rows: list[dict[str, object]], feature_names: set[str]) -> list[dict[str, object]]:
    if not feature_names:
        return rows
    return [
        {key: value for key, value in row.items() if key not in feature_names}
        for row in rows
    ]
