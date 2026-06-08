from __future__ import annotations

from typing import Any

from .transactions import Transaction


TRAINING_VIEW_COLUMNS = [
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


def training_view_row_to_transaction(row: dict[str, Any]) -> Transaction:
    missing = [column for column in TRAINING_VIEW_COLUMNS if column not in row]
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
    )


def read_transactions_from_training_view(
    connection: Any,
    *,
    city_code: str | None = None,
    property_types: list[str] | None = None,
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
