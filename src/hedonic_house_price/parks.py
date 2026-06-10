from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from .school_distances import haversine_distance_m


SUPPORTED_PARK_CITY_MARKERS = {
    "서울특별시": "seoul",
    "부산광역시": "busan",
}
GRID_DEGREES = 0.01
PARK_SOURCE_NAME = "park_standard_data"
PARK_SHEET_HEADER_MARKERS = {
    "관리번호",
    "공원명",
    "소재지도로명주소",
    "소재지지번주소",
    "위도",
    "경도",
    "공원면적",
    "관리기관명",
    "제공기관명",
}

SELECT_COMPLEXES_FOR_PARK_DISTANCE_SQL = """
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

UPSERT_PARK_ENVIRONMENT_SQL = """
INSERT INTO living_environment_snapshots (
  complex_id,
  snapshot_yyyymm,
  source_name,
  radius_m,
  nearest_park_distance_m,
  park_area_total_m2_radius
) VALUES (%s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
  radius_m = VALUES(radius_m),
  nearest_park_distance_m = VALUES(nearest_park_distance_m),
  park_area_total_m2_radius = VALUES(park_area_total_m2_radius),
  updated_at = CURRENT_TIMESTAMP
"""


@dataclass(frozen=True)
class ParkLocation:
    park_id: str
    park_name: str
    city_code: str
    latitude: float
    longitude: float
    area_m2: float


@dataclass(frozen=True)
class ParkMetrics:
    nearest_distance_m: float | None
    park_area_total_m2_radius: float


class ParkSpatialIndex:
    def __init__(self, parks: Sequence[ParkLocation]):
        self.parks = list(parks)
        self.grid: dict[tuple[int, int], list[ParkLocation]] = {}
        for park in self.parks:
            self.grid.setdefault(_grid_key(park.latitude, park.longitude), []).append(park)

    def metrics(self, latitude: float, longitude: float, *, radius_m: int = 1000) -> ParkMetrics:
        candidates = self._nearby_candidates(latitude, longitude, radius_m=radius_m)
        nearest, area_total = _metrics_from_candidates(latitude, longitude, candidates, radius_m)
        if area_total == 0 and self.parks:
            nearest, _ = _metrics_from_candidates(latitude, longitude, self.parks, radius_m)
        return ParkMetrics(
            nearest_distance_m=nearest,
            park_area_total_m2_radius=round(area_total, 2),
        )

    def _nearby_candidates(self, latitude: float, longitude: float, *, radius_m: int) -> list[ParkLocation]:
        lat_delta, lon_delta = _radius_degree_deltas(latitude, radius_m)
        min_lat_key, min_lon_key = _grid_key(latitude - lat_delta, longitude - lon_delta)
        max_lat_key, max_lon_key = _grid_key(latitude + lat_delta, longitude + lon_delta)
        candidates: list[ParkLocation] = []
        for lat_key in range(min_lat_key, max_lat_key + 1):
            for lon_key in range(min_lon_key, max_lon_key + 1):
                candidates.extend(self.grid.get((lat_key, lon_key), []))
        return candidates


def park_locations_from_rows(rows: Iterable[dict[str, object]]) -> list[ParkLocation]:
    return _dedupe_parks(_park_from_row(row) for row in rows)


def read_park_locations_xls(path: str | Path) -> list[ParkLocation]:
    rows = _read_xls_rows(Path(path))
    return park_locations_from_rows(rows)


def nearest_park_metrics(
    latitude: float,
    longitude: float,
    parks: Sequence[ParkLocation],
    *,
    radius_m: int = 1000,
) -> ParkMetrics:
    return ParkSpatialIndex(parks).metrics(latitude, longitude, radius_m=radius_m)


def import_park_environment_snapshots_xls(
    connection: Any,
    xls_path: str | Path,
    *,
    source_name: str = PARK_SOURCE_NAME,
    radius_m: int = 1000,
) -> dict[str, int]:
    rows = _read_xls_rows(Path(xls_path))
    parks = park_locations_from_rows(rows)
    stats = import_park_environment_snapshots(
        connection,
        parks,
        source_name=source_name,
        radius_m=radius_m,
    )
    return {
        "source_rows": len(rows),
        "park_rows": len(parks),
        "seoul_park_rows": sum(1 for park in parks if park.city_code == "seoul"),
        "busan_park_rows": sum(1 for park in parks if park.city_code == "busan"),
        **stats,
    }


def import_park_environment_snapshots(
    connection: Any,
    parks: Sequence[ParkLocation],
    *,
    source_name: str = PARK_SOURCE_NAME,
    radius_m: int = 1000,
) -> dict[str, int]:
    indexes_by_city = {
        city_code: ParkSpatialIndex(city_parks)
        for city_code, city_parks in _parks_by_city(parks).items()
    }
    cursor = connection.cursor(dictionary=True)
    stats = {
        "candidate_complexes": 0,
        "complexes_with_metrics": 0,
        "skipped_no_months": 0,
        "skipped_no_park": 0,
        "snapshot_rows": 0,
        "changed_snapshot_rows": 0,
    }
    try:
        cursor.execute(SELECT_COMPLEXES_FOR_PARK_DISTANCE_SQL)
        for complex_row in cursor.fetchall():
            stats["candidate_complexes"] += 1
            deal_months = _split_multiline_values(complex_row.get("deal_months"))
            if not deal_months:
                stats["skipped_no_months"] += 1
                continue

            index = indexes_by_city.get(str(complex_row["city_code"]))
            if index is None:
                stats["skipped_no_park"] += 1
                continue

            metrics = index.metrics(
                float(complex_row["latitude"]),
                float(complex_row["longitude"]),
                radius_m=radius_m,
            )
            if metrics.nearest_distance_m is None:
                stats["skipped_no_park"] += 1
                continue

            stats["complexes_with_metrics"] += 1
            for deal_month in deal_months:
                cursor.execute(
                    UPSERT_PARK_ENVIRONMENT_SQL,
                    (
                        complex_row["complex_id"],
                        deal_month,
                        source_name,
                        radius_m,
                        metrics.nearest_distance_m,
                        metrics.park_area_total_m2_radius,
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


def _read_xls_rows(path: Path) -> list[dict[str, object]]:
    try:
        import xlrd
    except ImportError as exc:
        raise RuntimeError("xlrd>=2 is required to read park .xls files") from exc

    workbook = xlrd.open_workbook(path)
    sheet = workbook.sheet_by_index(0)
    header_index = _find_header_index(sheet)
    if header_index is None:
        raise ValueError(f"park .xls header row was not found: {path}")
    header = [_cell_text(value) for value in sheet.row_values(header_index)]
    rows = []
    for row_index in range(header_index + 1, sheet.nrows):
        values = sheet.row_values(row_index)
        rows.append({name: values[index] if index < len(values) else "" for index, name in enumerate(header)})
    return rows


def _find_header_index(sheet: Any) -> int | None:
    for row_index in range(min(sheet.nrows, 20)):
        values = {_cell_text(value) for value in sheet.row_values(row_index)}
        if PARK_SHEET_HEADER_MARKERS.issubset(values):
            return row_index
    return None


def _park_from_row(row: dict[str, object]) -> ParkLocation | None:
    city_code = _city_code_for_park_row(row)
    if city_code is None:
        return None
    latitude = _optional_float(row.get("위도"))
    longitude = _optional_float(row.get("경도"))
    area_m2 = _optional_float(row.get("공원면적"))
    if latitude is None or longitude is None or area_m2 is None:
        return None
    return ParkLocation(
        park_id=_cell_text(row.get("관리번호")),
        park_name=_cell_text(row.get("공원명")),
        city_code=city_code,
        latitude=latitude,
        longitude=longitude,
        area_m2=area_m2,
    )


def _city_code_for_park_row(row: dict[str, object]) -> str | None:
    text = " ".join(
        [
            _cell_text(row.get("소재지도로명주소")),
            _cell_text(row.get("소재지지번주소")),
            _cell_text(row.get("관리기관명")),
            _cell_text(row.get("제공기관명")),
        ]
    )
    for marker, city_code in SUPPORTED_PARK_CITY_MARKERS.items():
        if marker in text:
            return city_code
    return None


def _dedupe_parks(parks: Iterable[ParkLocation | None]) -> list[ParkLocation]:
    by_key: dict[tuple[str, str], ParkLocation] = {}
    order: list[tuple[str, str]] = []
    for park in parks:
        if park is None:
            continue
        key = (park.city_code, park.park_id or _fallback_park_key(park))
        if key not in by_key:
            by_key[key] = park
            order.append(key)
    return [by_key[key] for key in order]


def _fallback_park_key(park: ParkLocation) -> str:
    return f"{park.park_name}|{park.latitude:.7f}|{park.longitude:.7f}"


def _parks_by_city(parks: Sequence[ParkLocation]) -> dict[str, list[ParkLocation]]:
    by_city: dict[str, list[ParkLocation]] = {}
    for park in parks:
        by_city.setdefault(park.city_code, []).append(park)
    return by_city


def _metrics_from_candidates(
    latitude: float,
    longitude: float,
    candidates: Sequence[ParkLocation],
    radius_m: int,
) -> tuple[float | None, float]:
    nearest: float | None = None
    area_total = 0.0
    for park in candidates:
        distance_m = haversine_distance_m(latitude, longitude, park.latitude, park.longitude)
        if nearest is None or distance_m < nearest:
            nearest = distance_m
        if distance_m <= radius_m:
            area_total += park.area_m2
    return nearest, area_total


def _radius_degree_deltas(latitude: float, radius_m: int) -> tuple[float, float]:
    latitude_delta = radius_m / 111_000 * 1.2
    cosine = max(abs(math.cos(math.radians(latitude))), 0.1)
    longitude_delta = radius_m / (111_000 * cosine) * 1.2
    return latitude_delta, longitude_delta


def _grid_key(latitude: float, longitude: float) -> tuple[int, int]:
    return (math.floor(latitude / GRID_DEGREES), math.floor(longitude / GRID_DEGREES))


def _optional_float(value: object) -> float | None:
    text = _cell_text(value).replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _split_multiline_values(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split("\n") if item.strip()]
