from __future__ import annotations

import math

from .transactions import Transaction


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


def month_index(first_yyyymm: str, current_yyyymm: str) -> int:
    first_year, first_month = _split_yyyymm(first_yyyymm)
    current_year, current_month = _split_yyyymm(current_yyyymm)
    return (current_year - first_year) * 12 + (current_month - first_month)


def make_feature_row(
    transaction: Transaction,
    first_month: str,
) -> dict[str, float | int | str]:
    if transaction.exclusive_area_m2 <= 0:
        raise ValueError("exclusive_area_m2 must be positive")
    if transaction.price_krw <= 0:
        raise ValueError("price_krw must be positive")

    age = max(0, transaction.deal_year - transaction.build_year)
    has_land_area = transaction.land_area_m2 is not None and transaction.land_area_m2 > 0

    return {
        "log_area_m2": math.log(transaction.exclusive_area_m2),
        "log_land_area_m2": math.log(transaction.land_area_m2) if has_land_area else 0.0,
        "has_land_area": 1 if has_land_area else 0,
        "age": age,
        "age_squared": age * age,
        "floor": transaction.floor,
        "floor_squared": transaction.floor * transaction.floor,
        "low_floor": 1 if transaction.floor <= 3 else 0,
        "floor_band": floor_band(transaction.floor),
        "deal_month_index": month_index(first_month, transaction.deal_yyyymm),
        "calendar_month": str(transaction.deal_month),
        "district": transaction.district,
        "legal_dong": transaction.legal_dong,
        "property_type": transaction.property_type,
        "house_type": transaction.house_type or "unknown",
        "target_log_price": math.log(transaction.price_krw),
    }


def make_feature_rows(
    transactions: list[Transaction],
    first_month: str,
) -> list[dict[str, float | int | str]]:
    return [
        make_feature_row(transaction, first_month=first_month)
        for transaction in transactions
    ]


def _split_yyyymm(value: str) -> tuple[int, int]:
    if len(value) != 6 or not value.isdigit():
        raise ValueError("month must be in YYYYMM format")
    year = int(value[:4])
    month = int(value[4:])
    if not 1 <= month <= 12:
        raise ValueError("month must be between 01 and 12")
    return year, month
