from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SUPPORTED_EDUCATION_OFFICES = {
    "서울특별시교육청": "seoul",
    "부산광역시교육청": "busan",
}

SUPPORTED_SCHOOL_LEVELS = {"초등학교", "중학교", "고등학교"}

REQUIRED_SCHOOL_COLUMNS = (
    "학교ID",
    "학교명",
    "학교급구분",
    "운영상태",
    "시도교육청명",
    "위도",
    "경도",
)

SELECT_COMPLEXES_FOR_SCHOOL_DISTANCE_SQL = """
SELECT
  c.complex_id,
  r.city_code,
  c.latitude,
  c.longitude,
  GROUP_CONCAT(DISTINCT t.deal_yyyymm ORDER BY t.deal_yyyymm SEPARATOR '\n') AS deal_months
FROM housing_complexes c
JOIN administrative_regions r ON r.region_id = c.region_id
LEFT JOIN housing_transactions t ON t.complex_id = c.complex_id
WHERE c.property_type = 'apartment'
  AND r.city_code IN ('seoul', 'busan')
  AND c.latitude IS NOT NULL
  AND c.longitude IS NOT NULL
GROUP BY c.complex_id, r.city_code, c.latitude, c.longitude
"""

UPSERT_SCHOOL_DISTANCE_SQL = """
INSERT INTO living_environment_snapshots (
  complex_id,
  snapshot_yyyymm,
  source_name,
  radius_m,
  nearest_elementary_school_distance_m,
  nearest_middle_school_distance_m,
  school_count_radius
) VALUES (%s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
  radius_m = VALUES(radius_m),
  nearest_elementary_school_distance_m = VALUES(nearest_elementary_school_distance_m),
  nearest_middle_school_distance_m = VALUES(nearest_middle_school_distance_m),
  school_count_radius = VALUES(school_count_radius),
  updated_at = CURRENT_TIMESTAMP
"""


@dataclass(frozen=True)
class SchoolLocation:
    school_id: str
    school_name: str
    school_level: str
    city_code: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class SchoolDistanceResult:
    elementary_distance_m: float | None
    middle_distance_m: float | None
    school_count_radius: int


def read_school_locations_csv(path: str | Path) -> list[SchoolLocation]:
    input_path = Path(path)
    rows: list[SchoolLocation] = []
    with input_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("school location CSV header row was not found")
        missing = [column for column in REQUIRED_SCHOOL_COLUMNS if column not in reader.fieldnames]
        if missing:
            raise ValueError(f"school location CSV is missing required column: {missing[0]}")

        for row in reader:
            city_code = SUPPORTED_EDUCATION_OFFICES.get(_cell(row, "시도교육청명"))
            school_level = _cell(row, "학교급구분")
            if city_code is None or school_level not in SUPPORTED_SCHOOL_LEVELS:
                continue
            if _cell(row, "운영상태") != "운영":
                continue
            latitude = _optional_float(_cell(row, "위도"))
            longitude = _optional_float(_cell(row, "경도"))
            if latitude is None or longitude is None:
                continue

            rows.append(
                SchoolLocation(
                    school_id=_cell(row, "학교ID"),
                    school_name=_cell(row, "학교명"),
                    school_level=school_level,
                    city_code=city_code,
                    latitude=latitude,
                    longitude=longitude,
                )
            )
    return rows


def nearest_school_distances(
    latitude: float,
    longitude: float,
    schools: list[SchoolLocation],
    *,
    radius_m: int = 1000,
) -> SchoolDistanceResult:
    nearest_elementary: float | None = None
    nearest_middle: float | None = None
    school_count_radius = 0
    for school in schools:
        distance_m = haversine_distance_m(latitude, longitude, school.latitude, school.longitude)
        if school.school_level == "초등학교":
            nearest_elementary = _min_optional(nearest_elementary, distance_m)
        elif school.school_level == "중학교":
            nearest_middle = _min_optional(nearest_middle, distance_m)
        if distance_m <= radius_m:
            school_count_radius += 1
    return SchoolDistanceResult(
        elementary_distance_m=nearest_elementary,
        middle_distance_m=nearest_middle,
        school_count_radius=school_count_radius,
    )


def haversine_distance_m(
    latitude1: float,
    longitude1: float,
    latitude2: float,
    longitude2: float,
) -> float:
    if latitude1 == latitude2 and longitude1 == longitude2:
        return 0.0
    earth_radius_m = 6_371_000
    lat1 = math.radians(latitude1)
    lat2 = math.radians(latitude2)
    delta_lat = math.radians(latitude2 - latitude1)
    delta_lon = math.radians(longitude2 - longitude1)
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(earth_radius_m * c, 2)


def import_school_distance_snapshots_csv(
    connection: Any,
    csv_path: str | Path,
    *,
    source_name: str = "school_location",
    radius_m: int = 1000,
) -> dict[str, int]:
    schools = read_school_locations_csv(csv_path)
    schools_by_city = _schools_by_city(schools)
    cursor = connection.cursor(dictionary=True)
    stats = {
        "source_rows": len(schools),
        "elementary_school_rows": sum(1 for school in schools if school.school_level == "초등학교"),
        "middle_school_rows": sum(1 for school in schools if school.school_level == "중학교"),
        "high_school_rows": sum(1 for school in schools if school.school_level == "고등학교"),
        "candidate_complexes": 0,
        "complexes_with_distances": 0,
        "skipped_no_months": 0,
        "skipped_no_school_distance": 0,
        "snapshot_rows": 0,
        "changed_snapshot_rows": 0,
    }
    try:
        cursor.execute(SELECT_COMPLEXES_FOR_SCHOOL_DISTANCE_SQL)
        for complex_row in cursor.fetchall():
            stats["candidate_complexes"] += 1
            deal_months = _split_multiline_values(complex_row.get("deal_months"))
            if not deal_months:
                stats["skipped_no_months"] += 1
                continue

            distances = nearest_school_distances(
                float(complex_row["latitude"]),
                float(complex_row["longitude"]),
                schools_by_city.get(str(complex_row["city_code"]), []),
                radius_m=radius_m,
            )
            if (
                distances.elementary_distance_m is None
                and distances.middle_distance_m is None
                and distances.school_count_radius == 0
            ):
                stats["skipped_no_school_distance"] += 1
                continue

            stats["complexes_with_distances"] += 1
            for deal_month in deal_months:
                cursor.execute(
                    UPSERT_SCHOOL_DISTANCE_SQL,
                    (
                        complex_row["complex_id"],
                        deal_month,
                        source_name,
                        radius_m,
                        distances.elementary_distance_m,
                        distances.middle_distance_m,
                        distances.school_count_radius,
                    ),
                )
                stats["snapshot_rows"] += 1
                if cursor.rowcount > 0:
                    stats["changed_snapshot_rows"] += cursor.rowcount
        connection.commit()
        return stats
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def _schools_by_city(schools: list[SchoolLocation]) -> dict[str, list[SchoolLocation]]:
    by_city: dict[str, list[SchoolLocation]] = {}
    for school in schools:
        by_city.setdefault(school.city_code, []).append(school)
    return by_city


def _cell(row: dict[str, str], name: str) -> str:
    return (row.get(name) or "").strip()


def _optional_float(value: str) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _min_optional(left: float | None, right: float) -> float:
    if left is None:
        return right
    return min(left, right)


def _split_multiline_values(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split("\n") if item.strip()]
