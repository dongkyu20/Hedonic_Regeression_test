from __future__ import annotations

import csv
import math
from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from .school_distances import haversine_distance_m


CSV_ENCODINGS = ("utf-8-sig", "cp949", "euc-kr")
HEALTHCARE_SOURCE_NAME = "healthcare_facility"
GRID_DEGREES = 0.01

SELECT_COMPLEXES_FOR_HEALTHCARE_DISTANCE_SQL = """
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

UPSERT_HEALTHCARE_DISTANCE_SQL = """
INSERT INTO living_environment_snapshots (
  complex_id,
  snapshot_yyyymm,
  source_name,
  radius_m,
  nearest_hospital_distance_m,
  nearest_pharmacy_distance_m
) VALUES (%s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
  radius_m = VALUES(radius_m),
  nearest_hospital_distance_m = VALUES(nearest_hospital_distance_m),
  nearest_pharmacy_distance_m = VALUES(nearest_pharmacy_distance_m),
  updated_at = CURRENT_TIMESTAMP
"""


@dataclass(frozen=True)
class HealthcareFacility:
    facility_id: str
    facility_kind: str
    facility_name: str
    city_code: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class HealthcareMetrics:
    nearest_hospital_distance_m: float | None
    nearest_pharmacy_distance_m: float | None


class HealthcareSpatialIndex:
    def __init__(self, facilities: Sequence[HealthcareFacility]):
        self.facilities = list(facilities)
        self.grid: dict[tuple[int, int], list[HealthcareFacility]] = {}
        for facility in self.facilities:
            self.grid.setdefault(_grid_key(facility.latitude, facility.longitude), []).append(facility)

    def metrics(self, latitude: float, longitude: float) -> HealthcareMetrics:
        nearest_hospital: float | None = None
        nearest_pharmacy: float | None = None
        for facility in self._nearby_candidates(latitude, longitude):
            distance_m = haversine_distance_m(latitude, longitude, facility.latitude, facility.longitude)
            if facility.facility_kind == "hospital":
                nearest_hospital = _min_optional(nearest_hospital, distance_m)
            elif facility.facility_kind == "pharmacy":
                nearest_pharmacy = _min_optional(nearest_pharmacy, distance_m)

        if (nearest_hospital is None or nearest_pharmacy is None) and self.facilities:
            for facility in self.facilities:
                distance_m = haversine_distance_m(latitude, longitude, facility.latitude, facility.longitude)
                if facility.facility_kind == "hospital":
                    nearest_hospital = _min_optional(nearest_hospital, distance_m)
                elif facility.facility_kind == "pharmacy":
                    nearest_pharmacy = _min_optional(nearest_pharmacy, distance_m)

        return HealthcareMetrics(
            nearest_hospital_distance_m=nearest_hospital,
            nearest_pharmacy_distance_m=nearest_pharmacy,
        )

    def _nearby_candidates(self, latitude: float, longitude: float) -> list[HealthcareFacility]:
        radius_m = 5000
        lat_delta, lon_delta = _radius_degree_deltas(latitude, radius_m)
        min_lat_key, min_lon_key = _grid_key(latitude - lat_delta, longitude - lon_delta)
        max_lat_key, max_lon_key = _grid_key(latitude + lat_delta, longitude + lon_delta)
        candidates: list[HealthcareFacility] = []
        for lat_key in range(min_lat_key, max_lat_key + 1):
            for lon_key in range(min_lon_key, max_lon_key + 1):
                candidates.extend(self.grid.get((lat_key, lon_key), []))
        return candidates


def read_healthcare_facilities_csvs(
    paths: Sequence[str | Path],
    *,
    city_code: str,
    facility_kind: str,
    coordinate_converter: Callable[[float, float], tuple[float, float]] | None = None,
) -> list[HealthcareFacility]:
    converter = coordinate_converter or projected_xy_to_wgs84
    facilities: list[HealthcareFacility] = []
    for path in paths:
        for row in _read_csv_rows(Path(path)):
            facility = _facility_from_row(
                row,
                city_code=city_code,
                facility_kind=facility_kind,
                coordinate_converter=converter,
            )
            if facility is not None:
                facilities.append(facility)
    return _dedupe_facilities(facilities)


def read_healthcare_facilities_from_city_csvs(
    *,
    seoul_hospital_paths: Sequence[str | Path],
    busan_hospital_paths: Sequence[str | Path],
    seoul_pharmacy_paths: Sequence[str | Path],
    busan_pharmacy_paths: Sequence[str | Path],
) -> list[HealthcareFacility]:
    return [
        *read_healthcare_facilities_csvs(seoul_hospital_paths, city_code="seoul", facility_kind="hospital"),
        *read_healthcare_facilities_csvs(busan_hospital_paths, city_code="busan", facility_kind="hospital"),
        *read_healthcare_facilities_csvs(seoul_pharmacy_paths, city_code="seoul", facility_kind="pharmacy"),
        *read_healthcare_facilities_csvs(busan_pharmacy_paths, city_code="busan", facility_kind="pharmacy"),
    ]


def nearest_healthcare_metrics(
    latitude: float,
    longitude: float,
    facilities: Sequence[HealthcareFacility],
) -> HealthcareMetrics:
    return HealthcareSpatialIndex(facilities).metrics(latitude, longitude)


def import_healthcare_distance_snapshots_csvs(
    connection: Any,
    *,
    seoul_hospital_paths: Sequence[str | Path],
    busan_hospital_paths: Sequence[str | Path],
    seoul_pharmacy_paths: Sequence[str | Path],
    busan_pharmacy_paths: Sequence[str | Path],
    source_name: str = HEALTHCARE_SOURCE_NAME,
) -> dict[str, int]:
    facilities = read_healthcare_facilities_from_city_csvs(
        seoul_hospital_paths=seoul_hospital_paths,
        busan_hospital_paths=busan_hospital_paths,
        seoul_pharmacy_paths=seoul_pharmacy_paths,
        busan_pharmacy_paths=busan_pharmacy_paths,
    )
    stats = import_healthcare_distance_snapshots(
        connection,
        facilities,
        source_name=source_name,
    )
    return {
        "facility_rows": len(facilities),
        "hospital_rows": sum(1 for facility in facilities if facility.facility_kind == "hospital"),
        "pharmacy_rows": sum(1 for facility in facilities if facility.facility_kind == "pharmacy"),
        "seoul_facility_rows": sum(1 for facility in facilities if facility.city_code == "seoul"),
        "busan_facility_rows": sum(1 for facility in facilities if facility.city_code == "busan"),
        **stats,
    }


def import_healthcare_distance_snapshots(
    connection: Any,
    facilities: Sequence[HealthcareFacility],
    *,
    source_name: str = HEALTHCARE_SOURCE_NAME,
    radius_m: int = 0,
) -> dict[str, int]:
    indexes_by_city = {
        city_code: HealthcareSpatialIndex(city_facilities)
        for city_code, city_facilities in _facilities_by_city(facilities).items()
    }
    cursor = connection.cursor(dictionary=True)
    stats = {
        "candidate_complexes": 0,
        "complexes_with_metrics": 0,
        "skipped_no_months": 0,
        "skipped_no_healthcare": 0,
        "snapshot_rows": 0,
        "changed_snapshot_rows": 0,
    }
    try:
        cursor.execute(SELECT_COMPLEXES_FOR_HEALTHCARE_DISTANCE_SQL)
        for complex_row in cursor.fetchall():
            stats["candidate_complexes"] += 1
            deal_months = _split_multiline_values(complex_row.get("deal_months"))
            if not deal_months:
                stats["skipped_no_months"] += 1
                continue

            index = indexes_by_city.get(str(complex_row["city_code"]))
            if index is None:
                stats["skipped_no_healthcare"] += 1
                continue

            metrics = index.metrics(
                float(complex_row["latitude"]),
                float(complex_row["longitude"]),
            )
            if metrics.nearest_hospital_distance_m is None and metrics.nearest_pharmacy_distance_m is None:
                stats["skipped_no_healthcare"] += 1
                continue

            stats["complexes_with_metrics"] += 1
            for deal_month in deal_months:
                cursor.execute(
                    UPSERT_HEALTHCARE_DISTANCE_SQL,
                    (
                        complex_row["complex_id"],
                        deal_month,
                        source_name,
                        radius_m,
                        metrics.nearest_hospital_distance_m,
                        metrics.nearest_pharmacy_distance_m,
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


def projected_xy_to_wgs84(x: float, y: float) -> tuple[float, float]:
    if 124 <= x <= 132 and 33 <= y <= 39:
        return y, x
    try:
        from pyproj import Transformer
    except ImportError as exc:
        raise RuntimeError("pyproj is required to convert healthcare projected coordinates") from exc

    transformer = _projected_xy_to_wgs84_transformer()
    longitude, latitude = transformer.transform(x, y)
    return float(latitude), float(longitude)


@lru_cache(maxsize=1)
def _projected_xy_to_wgs84_transformer() -> Any:
    from pyproj import Transformer

    return Transformer.from_crs("EPSG:5174", "EPSG:4326", always_xy=True)


def _facility_from_row(
    row: dict[str, str],
    *,
    city_code: str,
    facility_kind: str,
    coordinate_converter: Callable[[float, float], tuple[float, float]],
) -> HealthcareFacility | None:
    if not _is_open(row):
        return None
    x = _optional_float(_cell(row, "좌표정보(X)"))
    y = _optional_float(_cell(row, "좌표정보(Y)"))
    if x is None or y is None:
        return None
    latitude, longitude = coordinate_converter(x, y)
    if not _valid_wgs84(latitude, longitude):
        return None
    return HealthcareFacility(
        facility_id=_cell(row, "관리번호") or f"{facility_kind}:{_cell(row, '사업장명')}:{_cell(row, '도로명주소')}",
        facility_kind=facility_kind,
        facility_name=_cell(row, "사업장명"),
        city_code=city_code,
        latitude=latitude,
        longitude=longitude,
    )


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    last_error: UnicodeDecodeError | None = None
    for encoding in CSV_ENCODINGS:
        try:
            with path.open(encoding=encoding, newline="") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames is None:
                    raise ValueError(f"healthcare CSV header row was not found: {path}")
                return [dict(row) for row in reader]
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError(f"healthcare CSV could not be decoded: {path}") from last_error


def _is_open(row: dict[str, str]) -> bool:
    return _cell(row, "영업상태명") == "영업/정상" or _cell(row, "상세영업상태명") == "영업중"


def _dedupe_facilities(facilities: Sequence[HealthcareFacility]) -> list[HealthcareFacility]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[HealthcareFacility] = []
    for facility in facilities:
        key = (facility.city_code, facility.facility_kind, facility.facility_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(facility)
    return deduped


def _facilities_by_city(facilities: Sequence[HealthcareFacility]) -> dict[str, list[HealthcareFacility]]:
    by_city: dict[str, list[HealthcareFacility]] = {}
    for facility in facilities:
        by_city.setdefault(facility.city_code, []).append(facility)
    return by_city


def _split_multiline_values(value: object) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in str(value).split("\n") if item.strip()]


def _cell(row: dict[str, str], name: str) -> str:
    return (row.get(name) or "").strip()


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _valid_wgs84(latitude: float, longitude: float) -> bool:
    return 33 <= latitude <= 39 and 124 <= longitude <= 132


def _min_optional(left: float | None, right: float) -> float:
    if left is None:
        return right
    return min(left, right)


def _grid_key(latitude: float, longitude: float) -> tuple[int, int]:
    return (math.floor(latitude / GRID_DEGREES), math.floor(longitude / GRID_DEGREES))


def _radius_degree_deltas(latitude: float, radius_m: int) -> tuple[float, float]:
    lat_delta = radius_m / 111_320
    lon_scale = max(math.cos(math.radians(latitude)), 0.1)
    lon_delta = radius_m / (111_320 * lon_scale)
    return lat_delta, lon_delta
