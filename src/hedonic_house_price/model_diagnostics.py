from __future__ import annotations

import csv
import math
from pathlib import Path
from statistics import median
from typing import Any

from .features import count_bin, floors_below_top_bin, make_feature_rows, relative_floor_bin
from .modeling import TrainedModel, _chronological_split
from .transactions import Transaction


SEGMENT_CSV_FIELDS = [
    "segment_name",
    "condition",
    "count",
    "actual_mean_krw",
    "predicted_mean_krw",
    "residual_mean_krw",
    "mae_krw",
    "rmse_krw",
    "mape",
    "median_ape",
    "underprediction_rate",
    "bias_direction",
]


def generate_residual_diagnostics(
    model: TrainedModel,
    transactions: list[Transaction],
    *,
    output_dir: str | Path = "artifacts/model_diagnostics",
    validation_months: int = 6,
    min_segment_count: int = 100,
) -> dict[str, object]:
    _, validation_transactions = _chronological_split(
        sorted(transactions, key=lambda transaction: transaction.deal_ymd),
        validation_months,
    )
    if not validation_transactions:
        raise ValueError("no validation rows available for diagnostics")

    feature_rows = make_feature_rows(
        validation_transactions,
        first_month=model.first_month,
        estimated_max_floors=getattr(model, "estimated_max_floors", {}),
    )
    predicted_log_prices = model.pipeline.predict(feature_rows)
    residual_records = [
        _residual_record(transaction, feature_row, predicted_log_price)
        for transaction, feature_row, predicted_log_price in zip(
            validation_transactions,
            feature_rows,
            predicted_log_prices,
        )
    ]
    segment_rows = _summarize_segments(residual_records)
    top_rows = [
        row for row in segment_rows
        if int(row["count"]) >= min_segment_count
    ]
    top_rows.sort(key=lambda row: (float(row["mape"]), float(row["mae_krw"])), reverse=True)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    residual_segments_csv = output_path / "residual_segments.csv"
    top_error_segments_csv = output_path / "top_error_segments.csv"
    summary_markdown = output_path / "diagnostics_summary.md"

    _write_csv(residual_segments_csv, segment_rows)
    _write_csv(top_error_segments_csv, top_rows)
    summary_markdown.write_text(
        _summary_markdown(
            validation_rows=len(validation_transactions),
            segment_rows=segment_rows,
            top_rows=top_rows[:20],
            min_segment_count=min_segment_count,
        ),
        encoding="utf-8",
    )

    return {
        "validation_rows": len(validation_transactions),
        "segment_rows": len(segment_rows),
        "top_segment_rows": len(top_rows),
        "residual_segments_csv": str(residual_segments_csv),
        "top_error_segments_csv": str(top_error_segments_csv),
        "summary_markdown": str(summary_markdown),
    }


def _residual_record(
    transaction: Transaction,
    feature_row: dict[str, object],
    predicted_log_price: float,
) -> dict[str, object]:
    predicted_krw = math.exp(predicted_log_price)
    actual_krw = float(transaction.price_krw)
    residual_krw = actual_krw - predicted_krw
    return {
        "actual_krw": actual_krw,
        "predicted_krw": predicted_krw,
        "residual_krw": residual_krw,
        "ape": abs(residual_krw) / actual_krw if actual_krw else 0.0,
        "segments": _segment_conditions(transaction, feature_row),
    }


def _segment_conditions(
    transaction: Transaction,
    feature_row: dict[str, object],
) -> dict[str, str]:
    extra = getattr(transaction, "extra_features", {}) or {}
    return {
        "city_code": str(feature_row.get("city_code", "unknown")),
        "district": transaction.district,
        "legal_dong": transaction.legal_dong,
        "floor_band": str(feature_row["floor_band"]),
        "max_floor_source": str(feature_row.get("max_floor_source", "unknown")),
        "relative_floor_bin": str(feature_row.get("relative_floor_bin") or relative_floor_bin(feature_row.get("relative_floor"))),
        "floors_below_estimated_top_bin": str(
            feature_row.get("floors_below_estimated_top_bin")
            or floors_below_top_bin(feature_row.get("floors_below_estimated_top"))
        ),
        "is_first_floor": str(int(feature_row.get("is_first_floor", 0))),
        "is_floor_2_3": str(int(feature_row.get("is_floor_2_3", 0))),
        "is_estimated_top_floor": str(int(feature_row.get("is_estimated_top_floor", 0))),
        "is_near_estimated_top_floor": str(int(feature_row.get("is_near_estimated_top_floor", 0))),
        "age_band": str(feature_row["age_band"]),
        "area_m2_bin": _area_bin(transaction.exclusive_area_m2),
        "household_count_bin": _household_count_bin(extra.get("household_count")),
        "households_per_building_bin": _households_per_building_bin(feature_row.get("households_per_building")),
        "parking_spaces_per_household_bin": _parking_spaces_per_household_bin(extra.get("parking_spaces_per_household")),
        "nearest_subway_distance_m_bin": _distance_bin(extra.get("nearest_subway_distance_m")),
        "subway_count_radius_bin": count_bin(extra.get("subway_count_radius")),
        "nearest_bus_stop_distance_m_bin": _distance_bin(extra.get("nearest_bus_stop_distance_m")),
        "bus_stop_count_radius_bin": count_bin(extra.get("bus_stop_count_radius")),
        "car_intercity_bus_terminal_minutes_bin": _minutes_bin(extra.get("car_intercity_bus_terminal_minutes")),
        "car_airport_minutes_bin": _minutes_bin(extra.get("car_airport_minutes")),
        "car_rail_station_minutes_bin": _minutes_bin(extra.get("car_rail_station_minutes")),
        "car_general_hospital_minutes_bin": _minutes_bin(extra.get("car_general_hospital_minutes")),
        "transit_intercity_bus_terminal_minutes_bin": _minutes_bin(extra.get("transit_intercity_bus_terminal_minutes")),
        "transit_airport_minutes_bin": _minutes_bin(extra.get("transit_airport_minutes")),
        "transit_rail_station_minutes_bin": _minutes_bin(extra.get("transit_rail_station_minutes")),
        "transit_general_hospital_minutes_bin": _minutes_bin(extra.get("transit_general_hospital_minutes")),
        "nearest_elementary_school_distance_m_bin": _distance_bin(extra.get("nearest_elementary_school_distance_m")),
        "nearest_middle_school_distance_m_bin": _distance_bin(extra.get("nearest_middle_school_distance_m")),
        "school_count_radius_bin": count_bin(extra.get("school_count_radius")),
        "academy_count_radius_bin": count_bin(extra.get("academy_count_radius")),
        "nearest_hospital_distance_m_bin": _distance_bin(extra.get("nearest_hospital_distance_m")),
        "nearest_pharmacy_distance_m_bin": _distance_bin(extra.get("nearest_pharmacy_distance_m")),
        "nearest_park_distance_m_bin": _distance_bin(extra.get("nearest_park_distance_m")),
        "park_exists": str(int(feature_row.get("park_exists", 0))),
        "park_area_total_m2_radius_bin": _park_area_bin(extra.get("park_area_total_m2_radius")),
        "recent_transaction_count_bin": count_bin(extra.get("recent_transaction_count")),
    }


def _summarize_segments(records: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
    for record in records:
        segments = record["segments"]
        if not isinstance(segments, dict):
            continue
        for segment_name, condition in segments.items():
            grouped.setdefault((segment_name, str(condition)), []).append(record)

    rows = [
        _segment_summary(segment_name, condition, values)
        for (segment_name, condition), values in grouped.items()
    ]
    rows.sort(key=lambda row: (str(row["segment_name"]), str(row["condition"])))
    return rows


def _segment_summary(
    segment_name: str,
    condition: str,
    records: list[dict[str, object]],
) -> dict[str, object]:
    actual = [float(record["actual_krw"]) for record in records]
    predicted = [float(record["predicted_krw"]) for record in records]
    residuals = [float(record["residual_krw"]) for record in records]
    absolute_errors = [abs(value) for value in residuals]
    ape_values = [float(record["ape"]) for record in records]
    residual_mean = sum(residuals) / len(residuals)
    if residual_mean > 0:
        bias_direction = "underpredicted"
    elif residual_mean < 0:
        bias_direction = "overpredicted"
    else:
        bias_direction = "neutral"

    return {
        "segment_name": segment_name,
        "condition": condition,
        "count": len(records),
        "actual_mean_krw": sum(actual) / len(actual),
        "predicted_mean_krw": sum(predicted) / len(predicted),
        "residual_mean_krw": residual_mean,
        "mae_krw": sum(absolute_errors) / len(absolute_errors),
        "rmse_krw": math.sqrt(sum(value * value for value in residuals) / len(residuals)),
        "mape": sum(ape_values) / len(ape_values),
        "median_ape": median(ape_values),
        "underprediction_rate": sum(1 for value in residuals if value > 0) / len(residuals),
        "bias_direction": bias_direction,
    }


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SEGMENT_CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in SEGMENT_CSV_FIELDS})


def _summary_markdown(
    *,
    validation_rows: int,
    segment_rows: list[dict[str, object]],
    top_rows: list[dict[str, object]],
    min_segment_count: int,
) -> str:
    lines = [
        "# Model Residual Diagnostics",
        "",
        "## 잔차 해석",
        "",
        "`residual_mean_krw`는 `실거래가 - 예측가`입니다. 양수면 모델이 그 조건의 가격을 낮게 예측한 것이고, 음수면 높게 예측한 것입니다.",
        "`mape`와 `mae_krw`가 높은 조건은 모델이 약한 구간일 가능성이 큽니다. 다만 `count`가 작은 조건은 표본 우연성이 크므로 우선순위를 낮춰 해석해야 합니다.",
        "",
        f"- validation rows: {validation_rows}",
        f"- segment rows: {len(segment_rows)}",
        f"- top segment min count: {min_segment_count}",
        "",
        "## Top Error Segments",
        "",
        "| segment | condition | count | mape | mae_krw | residual_mean_krw | direction |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in top_rows:
        lines.append(
            "| {segment_name} | {condition} | {count} | {mape:.4f} | {mae_krw:,.0f} | {residual_mean_krw:,.0f} | {bias_direction} |".format(
                segment_name=row["segment_name"],
                condition=row["condition"],
                count=int(row["count"]),
                mape=float(row["mape"]),
                mae_krw=float(row["mae_krw"]),
                residual_mean_krw=float(row["residual_mean_krw"]),
                bias_direction=row["bias_direction"],
            )
        )
    lines.append("")
    return "\n".join(lines)


def _area_bin(value: float) -> str:
    if value <= 40:
        return "area_0_40"
    if value <= 60:
        return "area_40_60"
    if value <= 85:
        return "area_60_85"
    if value <= 102:
        return "area_85_102"
    if value <= 135:
        return "area_102_135"
    return "area_135_plus"


def _household_count_bin(value: Any) -> str:
    number = _optional_number(value)
    if number is None:
        return "missing"
    if number < 300:
        return "households_0_299"
    if number < 500:
        return "households_300_499"
    if number < 1000:
        return "households_500_999"
    if number < 2000:
        return "households_1000_1999"
    return "households_2000_plus"


def _households_per_building_bin(value: Any) -> str:
    number = _optional_number(value)
    if number is None:
        return "missing"
    if number < 100:
        return "households_per_building_0_99"
    if number < 200:
        return "households_per_building_100_199"
    if number < 300:
        return "households_per_building_200_299"
    return "households_per_building_300_plus"


def _parking_spaces_per_household_bin(value: Any) -> str:
    number = _optional_number(value)
    if number is None:
        return "missing"
    if number < 0.8:
        return "parking_0_0.8"
    if number < 1.0:
        return "parking_0.8_1.0"
    if number < 1.3:
        return "parking_1.0_1.3"
    if number < 1.8:
        return "parking_1.3_1.8"
    return "parking_1.8_plus"


def _distance_bin(value: Any) -> str:
    number = _optional_number(value)
    if number is None:
        return "missing"
    if number <= 250:
        return "distance_0_250"
    if number <= 500:
        return "distance_250_500"
    if number <= 1000:
        return "distance_500_1000"
    if number <= 2000:
        return "distance_1000_2000"
    return "distance_2000_plus"


def _minutes_bin(value: Any) -> str:
    number = _optional_number(value)
    if number is None:
        return "missing"
    if number <= 15:
        return "minutes_0_15"
    if number <= 30:
        return "minutes_15_30"
    if number <= 45:
        return "minutes_30_45"
    if number <= 60:
        return "minutes_45_60"
    return "minutes_60_plus"


def _park_area_bin(value: Any) -> str:
    number = _optional_number(value)
    if number is None:
        return "missing"
    if number <= 0:
        return "park_area_0"
    if number <= 10_000:
        return "park_area_1_10000"
    if number <= 50_000:
        return "park_area_10000_50000"
    return "park_area_50000_plus"


def _optional_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return float(text)
