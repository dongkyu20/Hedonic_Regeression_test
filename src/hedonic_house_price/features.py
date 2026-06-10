from __future__ import annotations

import math

from .transactions import Transaction


LOG1P_EXTRA_FEATURES = [
    "household_count",
    "total_parking_spaces",
    "nearest_subway_distance_m",
    "nearest_bus_stop_distance_m",
    "car_intercity_bus_terminal_minutes",
    "car_airport_minutes",
    "car_rail_station_minutes",
    "car_general_hospital_minutes",
    "transit_intercity_bus_terminal_minutes",
    "transit_airport_minutes",
    "transit_rail_station_minutes",
    "transit_general_hospital_minutes",
    "nearest_elementary_school_distance_m",
    "nearest_middle_school_distance_m",
    "nearest_hospital_distance_m",
    "nearest_pharmacy_distance_m",
    "nearest_park_distance_m",
    "park_area_total_m2_radius",
]

COUNT_BIN_EXTRA_FEATURES = [
    "subway_count_radius",
    "bus_stop_count_radius",
    "school_count_radius",
    "academy_count_radius",
    "recent_transaction_count",
]

ComplexFloorKey = tuple[str, str, str, str]


def complex_floor_key(transaction: Transaction) -> ComplexFloorKey:
    return (
        transaction.property_type.strip().lower(),
        transaction.lawd_cd.strip(),
        transaction.legal_dong.strip(),
        transaction.building_name.strip(),
    )


def estimate_complex_max_floors(transactions: list[Transaction]) -> dict[ComplexFloorKey, int]:
    observed_max_floors: dict[ComplexFloorKey, int] = {}
    for transaction in transactions:
        key = complex_floor_key(transaction)
        observed_max_floors[key] = max(observed_max_floors.get(key, transaction.floor), transaction.floor)

    return {
        key: _round_up_to_floor_step(max_floor)
        for key, max_floor in observed_max_floors.items()
    }


def floor_band(floor: int) -> str:
    if floor == 1:
        return "floor_1"
    if 2 <= floor <= 3:
        return "floor_2_3"
    if 4 <= floor <= 7:
        return "floor_4_7"
    if 8 <= floor <= 12:
        return "floor_8_12"
    if 13 <= floor <= 18:
        return "floor_13_18"
    if 19 <= floor <= 25:
        return "floor_19_25"
    return "floor_26_plus"


def age_band(age_years: int) -> str:
    if age_years <= 4:
        return "age_0_4"
    if age_years <= 9:
        return "age_5_9"
    if age_years <= 19:
        return "age_10_19"
    if age_years <= 29:
        return "age_20_29"
    if age_years <= 39:
        return "age_30_39"
    return "age_40_plus"


def count_bin(value: object) -> str:
    number = _optional_number(value)
    if number is None:
        return "missing"
    count = int(number)
    if count <= 0:
        return "count_0"
    if count <= 2:
        return "count_1_2"
    if count <= 5:
        return "count_3_5"
    if count <= 10:
        return "count_6_10"
    if count <= 20:
        return "count_11_20"
    return "count_21_plus"


def month_index(first_yyyymm: str, current_yyyymm: str) -> int:
    first_year, first_month = _split_yyyymm(first_yyyymm)
    current_year, current_month = _split_yyyymm(current_yyyymm)
    return (current_year - first_year) * 12 + (current_month - first_month)


def make_feature_row(
    transaction: Transaction,
    first_month: str,
    estimated_max_floors: dict[ComplexFloorKey, int] | None = None,
) -> dict[str, float | int | str]:
    if transaction.exclusive_area_m2 <= 0:
        raise ValueError("exclusive_area_m2 must be positive")
    if transaction.price_krw <= 0:
        raise ValueError("price_krw must be positive")

    age = max(0, transaction.deal_year - transaction.build_year)
    has_land_area = transaction.land_area_m2 is not None and transaction.land_area_m2 > 0
    extra_features = getattr(transaction, "extra_features", {}) or {}
    estimated_max_floor, max_floor_source = _max_floor_context(transaction, estimated_max_floors, extra_features)
    relative_floor = transaction.floor / estimated_max_floor
    floors_below_top = max(0, estimated_max_floor - transaction.floor)

    row: dict[str, float | int | str] = {
        "log_area_m2": math.log1p(transaction.exclusive_area_m2),
        "log_land_area_m2": math.log1p(transaction.land_area_m2) if has_land_area else 0.0,
        "has_land_area": 1 if has_land_area else 0,
        "age_band": age_band(age),
        "low_floor": 1 if transaction.floor <= 3 else 0,
        "floor_band": floor_band(transaction.floor),
        "estimated_max_floor": estimated_max_floor,
        "max_floor_source": max_floor_source,
        "relative_floor": relative_floor,
        "relative_floor_bin": relative_floor_bin(relative_floor),
        "floors_below_estimated_top": floors_below_top,
        "floors_below_estimated_top_bin": floors_below_top_bin(floors_below_top),
        "is_first_floor": 1 if transaction.floor == 1 else 0,
        "is_floor_2_3": 1 if 2 <= transaction.floor <= 3 else 0,
        "is_estimated_top_floor": 1 if transaction.floor == estimated_max_floor else 0,
        "is_near_estimated_top_floor": 1 if transaction.floor >= estimated_max_floor - 2 else 0,
        "deal_month_index": month_index(first_month, transaction.deal_yyyymm),
        "calendar_month": str(transaction.deal_month),
        "district": transaction.district,
        "legal_dong": transaction.legal_dong,
        "property_type": transaction.property_type,
        "house_type": transaction.house_type or "unknown",
        "target_log_price": math.log(transaction.price_krw),
    }

    _add_extra_feature_transforms(row, extra_features)
    return row


def make_feature_rows(
    transactions: list[Transaction],
    first_month: str,
    estimated_max_floors: dict[ComplexFloorKey, int] | None = None,
) -> list[dict[str, float | int | str]]:
    return [
        make_feature_row(
            transaction,
            first_month=first_month,
            estimated_max_floors=estimated_max_floors,
        )
        for transaction in transactions
    ]


def _estimated_max_floor(
    transaction: Transaction,
    estimated_max_floors: dict[ComplexFloorKey, int] | None,
) -> int:
    return _max_floor_context(transaction, estimated_max_floors, {})[0]


def _max_floor_context(
    transaction: Transaction,
    estimated_max_floors: dict[ComplexFloorKey, int] | None,
    extra_features: dict[str, object],
) -> tuple[int, str]:
    kapt_max_floor = _positive_int(extra_features.get("kapt_max_floor"))
    if kapt_max_floor is not None:
        if kapt_max_floor >= transaction.floor:
            return kapt_max_floor, "kapt"
        return transaction.floor, "current_floor"

    current_floor_estimate = _round_up_to_floor_step(transaction.floor)
    if not estimated_max_floors:
        return current_floor_estimate, "current_floor_estimate"
    mapped_floor = estimated_max_floors.get(complex_floor_key(transaction))
    if mapped_floor is None:
        return current_floor_estimate, "current_floor_estimate"
    if mapped_floor >= current_floor_estimate:
        return mapped_floor, "transaction_estimate"
    return current_floor_estimate, "current_floor_estimate"


def relative_floor_bin(value: object) -> str:
    number = _optional_number(value)
    if number is None:
        return "missing"
    if number <= 0.25:
        return "relative_floor_0_25"
    if number <= 0.5:
        return "relative_floor_25_50"
    if number <= 0.75:
        return "relative_floor_50_75"
    if number < 1.0:
        return "relative_floor_75_100"
    return "relative_floor_100"


def floors_below_top_bin(value: object) -> str:
    number = _optional_number(value)
    if number is None:
        return "missing"
    floors = int(number)
    if floors <= 0:
        return "below_top_0"
    if floors <= 2:
        return "below_top_1_2"
    if floors <= 5:
        return "below_top_3_5"
    if floors <= 10:
        return "below_top_6_10"
    return "below_top_11_plus"


def _round_up_to_floor_step(floor: int, step: int = 4) -> int:
    normalized_floor = max(1, int(floor))
    return ((normalized_floor + step - 1) // step) * step


def _split_yyyymm(value: str) -> tuple[int, int]:
    if len(value) != 6 or not value.isdigit():
        raise ValueError("month must be in YYYYMM format")
    year = int(value[:4])
    month = int(value[4:])
    if not 1 <= month <= 12:
        raise ValueError("month must be between 01 and 12")
    return year, month


def _add_extra_feature_transforms(
    row: dict[str, float | int | str],
    extra_features: dict[str, object],
) -> None:
    city_code = str(extra_features.get("city_code") or "").strip().lower()
    row["city_code"] = city_code or "unknown"

    household_count = _optional_number(extra_features.get("household_count"))
    building_count = _optional_number(extra_features.get("building_count"))
    if household_count is not None and building_count is not None and building_count > 0:
        row["households_per_building"] = household_count / building_count
        row["households_per_building_missing"] = 0
    else:
        row["households_per_building"] = 0.0
        row["households_per_building_missing"] = 1

    _add_optional_numeric(row, "parking_spaces_per_household", extra_features.get("parking_spaces_per_household"))
    _add_optional_numeric(row, "has_community_facilities", extra_features.get("has_community_facilities"))

    for feature_name in LOG1P_EXTRA_FEATURES:
        _add_log1p_feature(row, feature_name, extra_features.get(feature_name))

    for feature_name in COUNT_BIN_EXTRA_FEATURES:
        row[f"{feature_name}_bin"] = count_bin(extra_features.get(feature_name))

    park_area = _optional_number(extra_features.get("park_area_total_m2_radius"))
    row["park_exists"] = 1 if park_area is not None and park_area > 0 else 0


def _add_log1p_feature(
    row: dict[str, float | int | str],
    feature_name: str,
    value: object,
) -> None:
    number = _optional_number(value)
    if number is None or number < 0:
        row[f"log_{feature_name}"] = 0.0
        row[f"{feature_name}_missing"] = 1
        return

    row[f"log_{feature_name}"] = math.log1p(number)
    row[f"{feature_name}_missing"] = 0


def _add_optional_numeric(
    row: dict[str, float | int | str],
    feature_name: str,
    value: object,
) -> None:
    number = _optional_number(value)
    if number is None:
        row[feature_name] = 0.0
        row[f"{feature_name}_missing"] = 1
        return

    row[feature_name] = number
    row[f"{feature_name}_missing"] = 0


def _optional_number(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return float(text)


def _positive_int(value: object) -> int | None:
    number = _optional_number(value)
    if number is None or number <= 0:
        return None
    return max(1, int(number))
