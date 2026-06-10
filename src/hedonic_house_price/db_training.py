from __future__ import annotations

from typing import Any

from .transactions import Transaction


CORE_TRAINING_VIEW_COLUMNS = [
    "property_type",
    "district",
    "lawd_cd",
    "deal_year",
    "deal_month",
    "deal_day",
    "legal_dong",
    "building_name",
    "house_type",
    "land_area_m2",
    "exclusive_area_m2",
    "floor",
    "build_year",
    "price_manwon",
]

FACTOR_TRAINING_VIEW_COLUMNS = [
    "city_code",
    "household_count",
    "building_count",
    "total_parking_spaces",
    "parking_spaces_per_household",
    "has_community_facilities",
    "nearest_subway_distance_m",
    "subway_count_radius",
    "nearest_bus_stop_distance_m",
    "bus_stop_count_radius",
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
    "school_count_radius",
    "academy_count_radius",
    "nearest_hospital_distance_m",
    "nearest_pharmacy_distance_m",
    "nearest_park_distance_m",
    "park_area_total_m2_radius",
    "recent_transaction_count",
]

TRAINING_VIEW_COLUMNS = CORE_TRAINING_VIEW_COLUMNS + FACTOR_TRAINING_VIEW_COLUMNS


def training_view_row_to_transaction(row: dict[str, Any]) -> Transaction:
    missing = [column for column in CORE_TRAINING_VIEW_COLUMNS if column not in row]
    if missing:
        raise ValueError(f"missing training view column: {missing[0]}")

    return Transaction(
        property_type=str(row["property_type"]),
        district=str(row["district"]),
        lawd_cd=str(row["lawd_cd"]),
        deal_year=int(row["deal_year"]),
        deal_month=int(row["deal_month"]),
        deal_day=int(row["deal_day"]),
        legal_dong=str(row["legal_dong"]),
        building_name=str(row["building_name"] or ""),
        house_type=str(row["house_type"] or ""),
        land_area_m2=_optional_float(row["land_area_m2"]),
        exclusive_area_m2=float(row["exclusive_area_m2"]),
        floor=int(row["floor"]),
        build_year=int(row["build_year"]),
        price_manwon=int(row["price_manwon"]),
        extra_features={
            column: row.get(column)
            for column in FACTOR_TRAINING_VIEW_COLUMNS
            if column in row
        },
    )


def read_transactions_from_training_view(
    connection: Any,
    *,
    city_code: str | None = None,
    property_types: list[str] | None = None,
    require_complete_factors: bool = True,
) -> list[Transaction]:
    where_parts: list[str] = []
    params: list[object] = []
    if city_code:
        where_parts.append("city_code = %s")
        params.append(city_code.strip().lower())
    if property_types:
        placeholders = ", ".join(["%s"] * len(property_types))
        where_parts.append(f"property_type IN ({placeholders})")
        params.extend(property_types)
    if require_complete_factors:
        where_parts.extend(f"{column} IS NOT NULL" for column in FACTOR_TRAINING_VIEW_COLUMNS)

    where_sql = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""
    query = f"""
        SELECT {', '.join(TRAINING_VIEW_COLUMNS)}
        FROM model_training_features
        {where_sql}
        ORDER BY deal_date, transaction_id
    """

    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
    finally:
        cursor.close()

    return [training_view_row_to_transaction(row) for row in rows]


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return float(text)
