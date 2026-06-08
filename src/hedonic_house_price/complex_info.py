from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SUPPORTED_CITY_NAMES = {
    "서울특별시": "seoul",
    "부산광역시": "busan",
}

REQUIRED_COMPLEX_INFO_COLUMNS = (
    "시도",
    "시군구",
    "동리",
    "단지코드",
    "단지명",
    "단지분류",
    "법정동주소",
    "도로명주소",
)

SELECT_COMPLEXES_SQL = """
SELECT
  c.complex_id,
  c.complex_name,
  r.city_code,
  r.district_name,
  GROUP_CONCAT(DISTINCT t.legal_dong_name ORDER BY t.legal_dong_name SEPARATOR '\n') AS legal_dongs
FROM housing_complexes c
JOIN administrative_regions r ON r.region_id = c.region_id
LEFT JOIN housing_transactions t ON t.complex_id = c.complex_id
WHERE c.property_type = 'apartment'
  AND r.city_code IN ('seoul', 'busan')
GROUP BY c.complex_id, c.complex_name, r.city_code, r.district_name
"""

UPDATE_COMPLEX_ADDRESS_SQL = """
UPDATE housing_complexes
SET
  road_address = COALESCE(NULLIF(%s, ''), road_address),
  jibun_address = COALESCE(NULLIF(%s, ''), jibun_address),
  updated_at = CURRENT_TIMESTAMP
WHERE complex_id = %s
"""


@dataclass(frozen=True)
class ComplexBasicInfo:
    city_code: str
    city_name: str
    district_name: str
    legal_dong_name: str
    source_complex_code: str
    complex_name: str
    complex_category: str
    jibun_address: str
    road_address: str


@dataclass(frozen=True)
class ComplexMatch:
    info: ComplexBasicInfo | None
    kind: str


def normalize_complex_name(value: str) -> str:
    return re.sub(r"[\s·ㆍ\-_()（）\[\]{}]+", "", (value or "").strip().lower())


def read_complex_basic_info_csv(path: str | Path) -> list[ComplexBasicInfo]:
    input_path = Path(path)
    rows: list[ComplexBasicInfo] = []
    with input_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = _find_header(reader)
        index = {name: idx for idx, name in enumerate(header)}

        for raw_row in reader:
            row = _pad_row(raw_row, len(header))
            city_name = _cell(row, index, "시도")
            city_code = SUPPORTED_CITY_NAMES.get(city_name)
            if city_code is None:
                continue
            rows.append(
                ComplexBasicInfo(
                    city_code=city_code,
                    city_name=city_name,
                    district_name=_cell(row, index, "시군구"),
                    legal_dong_name=_cell(row, index, "동리"),
                    source_complex_code=_cell(row, index, "단지코드"),
                    complex_name=_cell(row, index, "단지명"),
                    complex_category=_cell(row, index, "단지분류"),
                    jibun_address=_cell(row, index, "법정동주소"),
                    road_address=_cell(row, index, "도로명주소"),
                )
            )
    return rows


def find_complex_basic_info_match(
    candidates: list[ComplexBasicInfo],
    *,
    city_code: str,
    district_name: str,
    legal_dong_names: list[str],
    complex_name: str,
) -> ComplexMatch:
    by_dong, by_district = _build_match_indexes(candidates)
    return _find_match_in_indexes(
        by_dong,
        by_district,
        city_code=city_code,
        district_name=district_name,
        legal_dong_names=legal_dong_names,
        complex_name=complex_name,
    )


def _find_match_in_indexes(
    by_dong: dict[tuple[str, str, str, str], list[ComplexBasicInfo]],
    by_district: dict[tuple[str, str, str], list[ComplexBasicInfo]],
    *,
    city_code: str,
    district_name: str,
    legal_dong_names: list[str],
    complex_name: str,
) -> ComplexMatch:
    normalized_name = normalize_complex_name(complex_name)

    saw_ambiguous_dong = False
    for legal_dong_name in legal_dong_names:
        key = (city_code, district_name, legal_dong_name, normalized_name)
        matches = by_dong.get(key, [])
        if len(matches) == 1:
            return ComplexMatch(info=matches[0], kind="dong")
        if len(matches) > 1:
            saw_ambiguous_dong = True

    district_key = (city_code, district_name, normalized_name)
    district_matches = by_district.get(district_key, [])
    if len(district_matches) == 1:
        return ComplexMatch(info=district_matches[0], kind="district_unique")
    if len(district_matches) > 1:
        return ComplexMatch(
            info=None,
            kind="ambiguous_dong" if saw_ambiguous_dong else "ambiguous_district",
        )
    return ComplexMatch(info=None, kind="unmatched")


def import_complex_basic_info_csv(connection: Any, csv_path: str | Path) -> dict[str, int]:
    candidates = read_complex_basic_info_csv(csv_path)
    by_dong, by_district = _build_match_indexes(candidates)
    cursor = connection.cursor(dictionary=True)
    stats = {
        "source_rows": len(candidates),
        "db_complexes": 0,
        "matched_complexes": 0,
        "updated_complexes": 0,
        "unmatched_complexes": 0,
        "ambiguous_complexes": 0,
        "empty_address_matches": 0,
        "dong_matches": 0,
        "district_unique_matches": 0,
    }
    try:
        cursor.execute(SELECT_COMPLEXES_SQL)
        for complex_row in cursor.fetchall():
            stats["db_complexes"] += 1
            match = _find_match_in_indexes(
                by_dong,
                by_district,
                city_code=complex_row["city_code"],
                district_name=complex_row["district_name"],
                legal_dong_names=_split_legal_dongs(complex_row.get("legal_dongs")),
                complex_name=complex_row["complex_name"],
            )
            if match.info is None:
                if match.kind.startswith("ambiguous"):
                    stats["ambiguous_complexes"] += 1
                else:
                    stats["unmatched_complexes"] += 1
                continue

            stats["matched_complexes"] += 1
            if match.kind == "dong":
                stats["dong_matches"] += 1
            elif match.kind == "district_unique":
                stats["district_unique_matches"] += 1

            if not match.info.road_address and not match.info.jibun_address:
                stats["empty_address_matches"] += 1
                continue

            cursor.execute(
                UPDATE_COMPLEX_ADDRESS_SQL,
                (
                    match.info.road_address,
                    match.info.jibun_address,
                    complex_row["complex_id"],
                ),
            )
            if cursor.rowcount > 0:
                stats["updated_complexes"] += 1
        connection.commit()
        return stats
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def _find_header(reader: Any) -> list[str]:
    required = set(REQUIRED_COMPLEX_INFO_COLUMNS)
    for row in reader:
        if required.issubset(set(row)):
            return row
    raise ValueError("complex info CSV header row was not found")


def _pad_row(row: list[str], size: int) -> list[str]:
    if len(row) >= size:
        return row
    return row + [""] * (size - len(row))


def _cell(row: list[str], index: dict[str, int], name: str) -> str:
    return row[index[name]].strip()


def _build_match_indexes(
    rows: list[ComplexBasicInfo],
) -> tuple[
    dict[tuple[str, str, str, str], list[ComplexBasicInfo]],
    dict[tuple[str, str, str], list[ComplexBasicInfo]],
]:
    by_dong: dict[tuple[str, str, str, str], list[ComplexBasicInfo]] = {}
    by_district: dict[tuple[str, str, str], list[ComplexBasicInfo]] = {}
    for row in rows:
        normalized_name = normalize_complex_name(row.complex_name)
        by_dong.setdefault(
            (row.city_code, row.district_name, row.legal_dong_name, normalized_name),
            [],
        ).append(row)
        by_district.setdefault(
            (row.city_code, row.district_name, normalized_name),
            [],
        ).append(row)
    return by_dong, by_district


def _split_legal_dongs(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split("\n") if item.strip()]
