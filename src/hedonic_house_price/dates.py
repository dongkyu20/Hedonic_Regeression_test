from __future__ import annotations

from datetime import date


def current_yyyymm() -> str:
    today = date.today()
    return f"{today.year:04d}{today.month:02d}"


def recent_months(count: int = 24, reference_yyyymm: str | None = None) -> list[str]:
    if count <= 0:
        raise ValueError("count must be positive")

    reference = reference_yyyymm or current_yyyymm()
    if len(reference) != 6 or not reference.isdigit():
        raise ValueError("reference_yyyymm must be in YYYYMM format")

    year = int(reference[:4])
    month = int(reference[4:])
    if not 1 <= month <= 12:
        raise ValueError("reference_yyyymm month must be between 01 and 12")

    months: list[str] = []
    for offset in range(count - 1, -1, -1):
        total = year * 12 + month - 1 - offset
        item_year = total // 12
        item_month = total % 12 + 1
        months.append(f"{item_year:04d}{item_month:02d}")
    return months
