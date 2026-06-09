from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from .school_distances import haversine_distance_m


CSV_ENCODINGS = ("utf-8-sig", "cp949", "euc-kr")
SUPPORTED_BUS_STOP_CITY_PREFIXES = {
    "서울특별시": "seoul",
    "부산광역시": "busan",
}
GRID_DEGREES = 0.01

REQUIRED_BUS_STOP_COLUMNS = (
    "정류장번호",
    "정류장명",
    "위도",
    "경도",
    "도시명",
)

SELECT_COMPLEXES_FOR_BUS_STOP_DISTANCE_SQL = """
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

UPSERT_BUS_STOP_DISTANCE_SQL = """
INSERT INTO transport_access_snapshots (
  complex_id,
  snapshot_yyyymm,
  source_name,
  radius_m,
  nearest_bus_stop_distance_m,
  bus_stop_count_radius
) VALUES (%s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
  radius_m = VALUES(radius_m),
  nearest_bus_stop_distance_m = VALUES(nearest_bus_stop_distance_m),
  bus_stop_count_radius = VALUES(bus_stop_count_radius),
  updated_at = CURRENT_TIMESTAMP
"""


@dataclass(frozen=True)
class BusStopLocation:
    bus_stop_id: str
    bus_stop_name: str
    city_code: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class BusStopMetrics:
    nearest_distance_m: float | None
    count_radius: int


class BusStopSpatialIndex:
    def __init__(self, stops: Sequence[BusStopLocation]):
        self.stops = list(stops)
        self.grid: dict[tuple[int, int], list[BusStopLocation]] = {}
        for stop in self.stops:
            self.grid.setdefault(_grid_key(stop.latitude, stop.longitude), []).append(stop)

    def metrics(self, latitude: float, longitude: float, *, radius_m: int = 1000) -> BusStopMetrics:
        candidates = self._nearby_candidates(latitude, longitude, radius_m=radius_m)
        nearest, count_radius = _metrics_from_candidates(latitude, longitude, candidates, radius_m)
        if count_radius == 0 and self.stops:
            nearest, _ = _metrics_from_candidates(latitude, longitude, self.stops, radius_m)
        return BusStopMetrics(nearest_distance_m=nearest, count_radius=count_radius)

    def _nearby_candidates(
        self,
        latitude: float,
        longitude: float,
        *,
        radius_m: int,
    ) -> list[BusStopLocation]:
        lat_delta, lon_delta = _radius_degree_deltas(latitude, radius_m)
        min_lat_key, min_lon_key = _grid_key(latitude - lat_delta, longitude - lon_delta)
        max_lat_key, max_lon_key = _grid_key(latitude + lat_delta, longitude + lon_delta)
        candidates: list[BusStopLocation] = []
        for lat_key in range(min_lat_key, max_lat_key + 1):
            for lon_key in range(min_lon_key, max_lon_key + 1):
                candidates.extend(self.grid.get((lat_key, lon_key), []))
        return candidates


def read_bus_stop_locations_csv(path: str | Path) -> list[BusStopLocation]:
    rows = _read_csv_rows(Path(path))
    _validate_columns(rows.fieldnames, Path(path))
    return _dedupe_bus_stops(
        _bus_stop_from_row(row)
        for row in rows.records
    )


def nearest_bus_stop_metrics(
    latitude: float,
    longitude: float,
    stops: Sequence[BusStopLocation],
    *,
    radius_m: int = 1000,
) -> BusStopMetrics:
    return BusStopSpatialIndex(stops).metrics(latitude, longitude, radius_m=radius_m)


def import_bus_stop_distance_snapshots_csv(
    connection: Any,
    csv_path: str | Path,
    *,
    source_name: str = "transport_access",
    radius_m: int = 1000,
) -> dict[str, int]:
    rows = _read_csv_rows(Path(csv_path))
    _validate_columns(rows.fieldnames, Path(csv_path))
    stops = _dedupe_bus_stops(_bus_stop_from_row(row) for row in rows.records)
    stats = import_bus_stop_distance_snapshots(
        connection,
        stops,
        source_name=source_name,
        radius_m=radius_m,
    )
    return {
        "source_rows": rows.record_count,
        "bus_stop_rows": len(stops),
        "seoul_bus_stop_rows": sum(1 for stop in stops if stop.city_code == "seoul"),
        "busan_bus_stop_rows": sum(1 for stop in stops if stop.city_code == "busan"),
        **stats,
    }


def import_bus_stop_distance_snapshots(
    connection: Any,
    stops: Sequence[BusStopLocation],
    *,
    source_name: str = "transport_access",
    radius_m: int = 1000,
) -> dict[str, int]:
    indexes_by_city = {
        city_code: BusStopSpatialIndex(city_stops)
        for city_code, city_stops in _bus_stops_by_city(stops).items()
    }
    cursor = connection.cursor(dictionary=True)
    stats = {
        "candidate_complexes": 0,
        "complexes_with_metrics": 0,
        "skipped_no_months": 0,
        "skipped_no_bus_stop": 0,
        "snapshot_rows": 0,
        "changed_snapshot_rows": 0,
    }
    try:
        cursor.execute(SELECT_COMPLEXES_FOR_BUS_STOP_DISTANCE_SQL)
        for complex_row in cursor.fetchall():
            stats["candidate_complexes"] += 1
            deal_months = _split_multiline_values(complex_row.get("deal_months"))
            if not deal_months:
                stats["skipped_no_months"] += 1
                continue

            index = indexes_by_city.get(str(complex_row["city_code"]))
            if index is None:
                stats["skipped_no_bus_stop"] += 1
                continue

            metrics = index.metrics(
                float(complex_row["latitude"]),
                float(complex_row["longitude"]),
                radius_m=radius_m,
            )
            if metrics.nearest_distance_m is None:
                stats["skipped_no_bus_stop"] += 1
                continue

            stats["complexes_with_metrics"] += 1
            for deal_month in deal_months:
                cursor.execute(
                    UPSERT_BUS_STOP_DISTANCE_SQL,
                    (
                        complex_row["complex_id"],
                        deal_month,
                        source_name,
                        radius_m,
                        metrics.nearest_distance_m,
                        metrics.count_radius,
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


@dataclass(frozen=True)
class _CsvRows:
    fieldnames: list[str]
    records: list[dict[str, str]]

    @property
    def record_count(self) -> int:
        return len(self.records)


def _read_csv_rows(path: Path) -> _CsvRows:
    last_error: UnicodeDecodeError | None = None
    for encoding in CSV_ENCODINGS:
        try:
            with path.open(encoding=encoding, newline="") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames is None:
                    raise ValueError(f"bus stop CSV header row was not found: {path}")
                return _CsvRows(fieldnames=list(reader.fieldnames), records=[dict(row) for row in reader])
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError(f"bus stop CSV could not be decoded: {path}") from last_error


def _validate_columns(fieldnames: list[str], path: Path) -> None:
    missing = [column for column in REQUIRED_BUS_STOP_COLUMNS if column not in fieldnames]
    if missing:
        raise ValueError(f"bus stop CSV is missing required column: {missing[0]} ({path})")


def _bus_stop_from_row(row: dict[str, str]) -> BusStopLocation | None:
    city_code = _city_code_for_bus_stop_city_name(_cell(row, "도시명"))
    if city_code is None:
        return None
    latitude = _optional_float(_cell(row, "위도"))
    longitude = _optional_float(_cell(row, "경도"))
    if latitude is None or longitude is None:
        return None
    return BusStopLocation(
        bus_stop_id=_cell(row, "정류장번호"),
        bus_stop_name=_cell(row, "정류장명"),
        city_code=city_code,
        latitude=latitude,
        longitude=longitude,
    )


def _city_code_for_bus_stop_city_name(value: str) -> str | None:
    for prefix, city_code in SUPPORTED_BUS_STOP_CITY_PREFIXES.items():
        if value.startswith(prefix):
            return city_code
    return None


def _dedupe_bus_stops(stops: Iterable[BusStopLocation | None]) -> list[BusStopLocation]:
    by_key: dict[tuple[str, str], BusStopLocation] = {}
    order: list[tuple[str, str]] = []
    for stop in stops:
        if stop is None:
            continue
        key = (stop.city_code, stop.bus_stop_id or _fallback_stop_key(stop))
        if key not in by_key:
            by_key[key] = stop
            order.append(key)
    return [by_key[key] for key in order]


def _fallback_stop_key(stop: BusStopLocation) -> str:
    return f"{stop.bus_stop_name}|{stop.latitude:.7f}|{stop.longitude:.7f}"


def _bus_stops_by_city(stops: Sequence[BusStopLocation]) -> dict[str, list[BusStopLocation]]:
    by_city: dict[str, list[BusStopLocation]] = {}
    for stop in stops:
        by_city.setdefault(stop.city_code, []).append(stop)
    return by_city


def _metrics_from_candidates(
    latitude: float,
    longitude: float,
    candidates: Sequence[BusStopLocation],
    radius_m: int,
) -> tuple[float | None, int]:
    nearest: float | None = None
    count_radius = 0
    for stop in candidates:
        distance_m = haversine_distance_m(latitude, longitude, stop.latitude, stop.longitude)
        if nearest is None or distance_m < nearest:
            nearest = distance_m
        if distance_m <= radius_m:
            count_radius += 1
    return nearest, count_radius


def _radius_degree_deltas(latitude: float, radius_m: int) -> tuple[float, float]:
    latitude_delta = radius_m / 111_000 * 1.2
    cosine = max(abs(math.cos(math.radians(latitude))), 0.1)
    longitude_delta = radius_m / (111_000 * cosine) * 1.2
    return latitude_delta, longitude_delta


def _grid_key(latitude: float, longitude: float) -> tuple[int, int]:
    return (math.floor(latitude / GRID_DEGREES), math.floor(longitude / GRID_DEGREES))


def _cell(row: dict[str, str], name: str) -> str:
    return (row.get(name) or "").strip()


def _optional_float(value: str) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _split_multiline_values(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split("\n") if item.strip()]
