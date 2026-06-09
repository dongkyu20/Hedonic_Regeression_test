from __future__ import annotations

import csv
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from .geocoding import GeocodeResult, Geocoder
from .school_distances import haversine_distance_m


CSV_ENCODINGS = ("utf-8-sig", "cp949", "euc-kr")

SELECT_COMPLEXES_FOR_SUBWAY_DISTANCE_SQL = """
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

UPSERT_SUBWAY_DISTANCE_SQL = """
INSERT INTO transport_access_snapshots (
  complex_id,
  snapshot_yyyymm,
  source_name,
  radius_m,
  nearest_subway_distance_m,
  subway_count_radius
) VALUES (%s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
  radius_m = VALUES(radius_m),
  nearest_subway_distance_m = VALUES(nearest_subway_distance_m),
  subway_count_radius = VALUES(subway_count_radius),
  updated_at = CURRENT_TIMESTAMP
"""


@dataclass(frozen=True)
class SubwayStation:
    station_name: str
    line_name: str
    service_area: str
    road_address: str
    jibun_address: str

    def address_candidates(self) -> list[str]:
        candidates: list[str] = []
        for value in (self.road_address, self.jibun_address):
            for candidate in _split_address_values(value):
                if candidate and candidate not in candidates:
                    candidates.append(candidate)
        return candidates


@dataclass(frozen=True)
class LocatedSubwayStation:
    station_name: str
    line_name: str
    service_area: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class SubwayMetrics:
    nearest_distance_m: float | None
    count_radius: int


def read_subway_station_csvs(paths: Sequence[str | Path]) -> list[SubwayStation]:
    return _dedupe_subway_stations(_read_subway_station_rows(paths))


def geocode_subway_stations(
    stations: Sequence[SubwayStation],
    geocoder: Geocoder,
    *,
    sleep_seconds: float = 0.1,
) -> tuple[list[LocatedSubwayStation], dict[str, int]]:
    stats = {
        "geocoded_stations": 0,
        "station_not_found": 0,
        "station_no_address": 0,
        "station_address_attempts": 0,
    }
    cache: dict[str, GeocodeResult | None] = {}
    located: list[LocatedSubwayStation] = []

    for station in stations:
        addresses = station.address_candidates()
        if not addresses:
            stats["station_no_address"] += 1
            continue

        result = _geocode_first_match(
            geocoder,
            addresses,
            cache,
            stats,
            sleep_seconds=sleep_seconds,
        )
        if result is None:
            stats["station_not_found"] += 1
            continue

        located.append(
            LocatedSubwayStation(
                station_name=station.station_name,
                line_name=station.line_name,
                service_area=station.service_area,
                latitude=result.latitude,
                longitude=result.longitude,
            )
        )
        stats["geocoded_stations"] += 1

    return located, stats


def nearest_subway_metrics(
    latitude: float,
    longitude: float,
    stations: Sequence[LocatedSubwayStation],
    *,
    radius_m: int = 1000,
) -> SubwayMetrics:
    nearest: float | None = None
    counted_station_keys: set[tuple[str, float, float]] = set()

    for station in stations:
        distance_m = haversine_distance_m(latitude, longitude, station.latitude, station.longitude)
        if nearest is None or distance_m < nearest:
            nearest = distance_m
        if distance_m <= radius_m:
            counted_station_keys.add(_physical_station_key(station))

    return SubwayMetrics(nearest_distance_m=nearest, count_radius=len(counted_station_keys))


def import_subway_distance_snapshots_csvs(
    connection: Any,
    csv_paths: Sequence[str | Path],
    geocoder: Geocoder,
    *,
    source_name: str = "transport_access",
    radius_m: int = 1000,
    sleep_seconds: float = 0.1,
) -> dict[str, int]:
    raw_stations = _read_subway_station_rows(csv_paths)
    stations = _dedupe_subway_stations(raw_stations)
    located_stations, geocoding_stats = geocode_subway_stations(
        stations,
        geocoder,
        sleep_seconds=sleep_seconds,
    )
    import_stats = import_subway_distance_snapshots(
        connection,
        located_stations,
        source_name=source_name,
        radius_m=radius_m,
    )
    return {
        "source_rows": len(raw_stations),
        "deduped_stations": len(stations),
        **geocoding_stats,
        **import_stats,
    }


def import_subway_distance_snapshots(
    connection: Any,
    stations: Sequence[LocatedSubwayStation],
    *,
    source_name: str = "transport_access",
    radius_m: int = 1000,
) -> dict[str, int]:
    stations_by_area = _located_stations_by_area(stations)
    cursor = connection.cursor(dictionary=True)
    stats = {
        "located_stations": len(stations),
        "candidate_complexes": 0,
        "complexes_with_metrics": 0,
        "skipped_no_months": 0,
        "skipped_no_subway_station": 0,
        "snapshot_rows": 0,
        "changed_snapshot_rows": 0,
    }
    try:
        cursor.execute(SELECT_COMPLEXES_FOR_SUBWAY_DISTANCE_SQL)
        for complex_row in cursor.fetchall():
            stats["candidate_complexes"] += 1
            deal_months = _split_multiline_values(complex_row.get("deal_months"))
            if not deal_months:
                stats["skipped_no_months"] += 1
                continue

            metrics = nearest_subway_metrics(
                float(complex_row["latitude"]),
                float(complex_row["longitude"]),
                stations_by_area.get(str(complex_row["city_code"]), []),
                radius_m=radius_m,
            )
            if metrics.nearest_distance_m is None:
                stats["skipped_no_subway_station"] += 1
                continue

            stats["complexes_with_metrics"] += 1
            for deal_month in deal_months:
                cursor.execute(
                    UPSERT_SUBWAY_DISTANCE_SQL,
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


def _read_subway_station_rows(paths: Sequence[str | Path]) -> list[SubwayStation]:
    stations: list[SubwayStation] = []
    for path in paths:
        input_path = Path(path)
        for row in _read_csv_rows(input_path):
            station = _subway_station_from_row(input_path, row)
            if station is not None:
                stations.append(station)
    return stations


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    last_error: UnicodeDecodeError | None = None
    for encoding in CSV_ENCODINGS:
        try:
            with path.open(encoding=encoding, newline="") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames is None:
                    raise ValueError(f"subway station CSV header row was not found: {path}")
                return [dict(row) for row in reader]
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError(f"subway station CSV could not be decoded: {path}") from last_error


def _subway_station_from_row(path: Path, row: dict[str, str]) -> SubwayStation | None:
    station_name = _cell(row, "역명")
    line_name = _normalize_line_name(_cell(row, "선명") or _cell(row, "호선"))
    if not station_name or not line_name:
        return None

    road_address = _cell(row, "도로명주소")
    jibun_address = _cell(row, "지번주소")
    service_area = _infer_service_area(path, row, road_address, jibun_address)
    if service_area is None:
        return None

    return SubwayStation(
        station_name=station_name,
        line_name=line_name,
        service_area=service_area,
        road_address=road_address,
        jibun_address=jibun_address,
    )


def _dedupe_subway_stations(stations: Iterable[SubwayStation]) -> list[SubwayStation]:
    by_key: dict[tuple[str, str, str], SubwayStation] = {}
    order: list[tuple[str, str, str]] = []
    for station in stations:
        key = _source_station_key(station)
        if key not in by_key:
            by_key[key] = station
            order.append(key)
        else:
            by_key[key] = _preferred_station(by_key[key], station)
    return [by_key[key] for key in order]


def _source_station_key(station: SubwayStation) -> tuple[str, str, str]:
    return (
        station.service_area,
        _normalize_line_name(station.line_name),
        _normalize_station_name(station.station_name),
    )


def _preferred_station(existing: SubwayStation, candidate: SubwayStation) -> SubwayStation:
    existing_score = _station_address_score(existing)
    candidate_score = _station_address_score(candidate)
    if candidate_score > existing_score:
        return candidate
    return existing


def _station_address_score(station: SubwayStation) -> int:
    score = 0
    if station.road_address:
        score += 2
    if station.jibun_address:
        score += 1
    return score


def _located_stations_by_area(
    stations: Sequence[LocatedSubwayStation],
) -> dict[str, list[LocatedSubwayStation]]:
    by_area: dict[str, list[LocatedSubwayStation]] = {}
    for station in stations:
        by_area.setdefault(station.service_area, []).append(station)
    return by_area


def _physical_station_key(station: LocatedSubwayStation) -> tuple[str, float, float]:
    return (
        _normalize_station_name(station.station_name),
        round(station.latitude, 5),
        round(station.longitude, 5),
    )


def _geocode_first_match(
    geocoder: Geocoder,
    addresses: list[str],
    cache: dict[str, GeocodeResult | None],
    stats: dict[str, int],
    *,
    sleep_seconds: float,
) -> GeocodeResult | None:
    for address in addresses:
        if address not in cache:
            cache[address] = geocoder.geocode(address)
            stats["station_address_attempts"] += 1
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
        result = cache[address]
        if result is not None:
            return result
    return None


def _infer_service_area(
    path: Path,
    row: dict[str, str],
    road_address: str,
    jibun_address: str,
) -> str | None:
    text = " ".join(
        [
            path.name,
            _cell(row, "철도운영기관명"),
            road_address,
            jibun_address,
        ]
    )
    if "부산" in text:
        return "busan"
    if "서울" in text or "경기" in text or "인천" in text:
        return "seoul"
    return None


def _normalize_line_name(value: str) -> str:
    normalized = re.sub(r"\s+", "", value.strip())
    if re.fullmatch(r"\d+", normalized):
        return f"{int(normalized)}호선"
    return normalized


def _normalize_station_name(value: str) -> str:
    return re.sub(r"\s+", "", value.strip())


def _split_address_values(value: object) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    return [
        re.sub(r"\s+", " ", part.strip())
        for part in re.split(r"\s*,\s*", text)
        if part.strip()
    ]


def _cell(row: dict[str, str], name: str) -> str:
    return (row.get(name) or "").strip()


def _split_multiline_values(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split("\n") if item.strip()]
