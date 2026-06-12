from __future__ import annotations

import csv
import difflib
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .complex_info import normalize_complex_name, normalize_legal_dong_name, normalize_variant_complex_name
from .geocoding import GeocodeResult, Geocoder
from .school_distances import haversine_distance_m


CSV_ENCODINGS = ("utf-8-sig", "cp949", "euc-kr")
ACADEMY_SOURCE_NAME = "academy_nearby_complex_2604"
PRIMARY_COUNT_COLUMNS = (
    "SSIZE_INSTUT_CNT",
    "MSIZE_INSTUT_CNT",
    "LGZ_INSTUT_CNT",
    "GNRLZ_INSTUT_CNT",
    "ETEX_INSTUT_CNT",
    "FGGG_INSTUT_CNT",
    "AAMAPE_INSTUT_CNT",
    "READRM_CNT",
    "INFO_INSTUT_CNT",
    "SPCEDU_INSTUT_CNT",
    "VCSK_INSTUT_CNT",
    "ETC_INSTUT_CNT",
)

SELECT_REGION_CODES_SQL = """
SELECT city_code, district_name, lawd_cd
FROM administrative_regions
WHERE region_level = 'district'
  AND city_code IN ('seoul', 'busan')
"""

SELECT_COMPLEXES_FOR_ACADEMY_COUNT_SQL = """
SELECT
  c.complex_id,
  c.complex_name,
  c.jibun_address,
  c.road_address,
  c.latitude,
  c.longitude,
  r.city_code,
  r.district_name,
  GROUP_CONCAT(DISTINCT t.legal_dong_name ORDER BY t.legal_dong_name SEPARATOR '\n') AS legal_dongs,
  GROUP_CONCAT(DISTINCT t.deal_yyyymm ORDER BY t.deal_yyyymm SEPARATOR '\n') AS deal_months
FROM housing_complexes c
JOIN administrative_regions r ON r.region_id = c.region_id
LEFT JOIN housing_transactions t ON t.complex_id = c.complex_id
WHERE c.property_type = 'apartment'
  AND r.city_code IN ('seoul', 'busan')
GROUP BY
  c.complex_id,
  c.complex_name,
  c.jibun_address,
  c.road_address,
  c.latitude,
  c.longitude,
  r.city_code,
  r.district_name
"""

UPSERT_ACADEMY_COUNT_SQL = """
INSERT INTO living_environment_snapshots (
  complex_id,
  snapshot_yyyymm,
  source_name,
  radius_m,
  academy_count_radius
) VALUES (%s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
  radius_m = VALUES(radius_m),
  academy_count_radius = VALUES(academy_count_radius),
  updated_at = CURRENT_TIMESTAMP
"""


@dataclass(frozen=True)
class AcademyNearbyComplex:
    source_complex_id: str
    city_code: str
    district_name: str
    legal_dong_name: str
    complex_name: str
    jibun_address: str
    academy_count: int


@dataclass(frozen=True)
class AcademyFacility:
    city_code: str
    district_name: str
    facility_name: str
    address: str
    searchable_text: str


@dataclass(frozen=True)
class LocatedAcademyFacility:
    facility: AcademyFacility
    latitude: float
    longitude: float


@dataclass(frozen=True)
class AcademyComplexMatch:
    complex: AcademyNearbyComplex | None
    kind: str
    score: float = 0.0


def read_nearby_academy_complex_csv(
    path: str | Path,
    *,
    region_by_lawd_cd: dict[str, tuple[str, str]],
) -> list[AcademyNearbyComplex]:
    rows: list[AcademyNearbyComplex] = []
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="|", quotechar='"')
        if reader.fieldnames is None:
            raise ValueError(f"nearby academy complex CSV header row was not found: {path}")
        for row in reader:
            lawd_cd = _cell(row, "SIGNGU_CD")
            region = region_by_lawd_cd.get(lawd_cd)
            if region is None:
                continue
            city_code, district_name = region
            if city_code not in {"seoul", "busan"}:
                continue
            if _cell(row, "HSMP_KIND_CD") and _cell(row, "HSMP_KIND_CD") != "1":
                continue

            jibun_address = _cell(row, "LNNO_ADRES")
            rows.append(
                AcademyNearbyComplex(
                    source_complex_id=_cell(row, "HSMP_INNB") or _cell(row, "PNU"),
                    city_code=city_code,
                    district_name=district_name,
                    legal_dong_name=_legal_dong_from_address(jibun_address),
                    complex_name=_cell(row, "POTVALE_IFRA_HSMP_NM"),
                    jibun_address=jibun_address,
                    academy_count=sum(_optional_int(_cell(row, column)) or 0 for column in PRIMARY_COUNT_COLUMNS),
                )
            )
    return rows


def read_academy_facility_csvs(
    *,
    seoul_csv_path: str | Path,
    busan_csv_path: str | Path,
) -> list[AcademyFacility]:
    return _dedupe_facilities(
        [
            *_read_seoul_academy_facilities(Path(seoul_csv_path)),
            *_read_busan_academy_facilities(Path(busan_csv_path)),
        ]
    )


def find_academy_complex_match(
    candidates: Sequence[AcademyNearbyComplex],
    complex_row: dict[str, Any],
) -> AcademyComplexMatch:
    return AcademyComplexMatcher(candidates).match(complex_row)


class AcademyComplexMatcher:
    def __init__(self, candidates: Sequence[AcademyNearbyComplex]):
        self.candidates = list(candidates)
        self.by_address: dict[str, list[AcademyNearbyComplex]] = {}
        self.by_dong: dict[tuple[str, str, str, str], list[AcademyNearbyComplex]] = {}
        self.by_district: dict[tuple[str, str, str], list[AcademyNearbyComplex]] = {}
        self.by_city_district: dict[tuple[str, str], list[AcademyNearbyComplex]] = {}
        for candidate in self.candidates:
            for address_key in _address_match_keys(candidate.jibun_address):
                self.by_address.setdefault(address_key, []).append(candidate)
            normalized_name = normalize_complex_name(candidate.complex_name)
            dong_key = normalize_legal_dong_name(candidate.legal_dong_name)
            self.by_dong.setdefault(
                (candidate.city_code, candidate.district_name, dong_key, normalized_name),
                [],
            ).append(candidate)
            self.by_district.setdefault(
                (candidate.city_code, candidate.district_name, normalized_name),
                [],
            ).append(candidate)
            self.by_city_district.setdefault((candidate.city_code, candidate.district_name), []).append(candidate)

    def match(self, complex_row: dict[str, Any]) -> AcademyComplexMatch:
        for address in (complex_row.get("jibun_address"), complex_row.get("road_address")):
            for address_key in _address_match_keys(address):
                candidates = self.by_address.get(address_key, [])
                match = _pick_candidate_by_name(candidates, str(complex_row.get("complex_name") or ""))
                if match.complex is not None:
                    if len(candidates) == 1:
                        return AcademyComplexMatch(match.complex, "address_unique", match.score)
                    return AcademyComplexMatch(match.complex, f"address_{match.kind}", match.score)

        city_code = str(complex_row.get("city_code") or "")
        district_name = str(complex_row.get("district_name") or "")
        normalized_name = normalize_complex_name(str(complex_row.get("complex_name") or ""))
        for legal_dong in _split_multiline_values(complex_row.get("legal_dongs")):
            key = (city_code, district_name, normalize_legal_dong_name(legal_dong), normalized_name)
            candidates = self.by_dong.get(key, [])
            if len(candidates) == 1:
                return AcademyComplexMatch(candidates[0], "dong")

        district_candidates = self.by_district.get((city_code, district_name, normalized_name), [])
        if len(district_candidates) == 1:
            return AcademyComplexMatch(district_candidates[0], "district_unique")

        return self._variant_match(complex_row)

    def _variant_match(self, complex_row: dict[str, Any]) -> AcademyComplexMatch:
        candidates = self.by_city_district.get(
            (str(complex_row.get("city_code") or ""), str(complex_row.get("district_name") or "")),
            [],
        )
        return _pick_candidate_by_name(
            candidates,
            str(complex_row.get("complex_name") or ""),
            min_score=0.9,
            kind_prefix="name_variant",
            allow_single_unique=False,
        )


class FallbackAcademyCounter:
    def __init__(
        self,
        facilities: Sequence[AcademyFacility],
        geocoder: Geocoder,
        *,
        radius_m: int,
        sleep_seconds: float,
        geocode_cache: dict[str, GeocodeResult | None] | None = None,
    ):
        self.facilities_by_city_district: dict[tuple[str, str], list[AcademyFacility]] = {}
        for facility in facilities:
            self.facilities_by_city_district.setdefault((facility.city_code, facility.district_name), []).append(facility)
        self.geocoder = geocoder
        self.radius_m = radius_m
        self.sleep_seconds = sleep_seconds
        self.geocode_cache = geocode_cache if geocode_cache is not None else {}
        self.stats = {
            "fallback_candidate_facilities": 0,
            "fallback_geocoded_facilities": 0,
            "fallback_not_found_facilities": 0,
            "fallback_address_attempts": 0,
        }

    def count_for_complex(self, complex_row: dict[str, Any]) -> int | None:
        latitude = _optional_float(complex_row.get("latitude"))
        longitude = _optional_float(complex_row.get("longitude"))
        if latitude is None or longitude is None:
            return None

        candidates = self._candidate_facilities(complex_row)
        if not candidates:
            return None

        count = 0
        saw_geocoded_candidate = False
        for facility in candidates:
            result = self._geocode_facility(facility)
            if result is None:
                continue
            saw_geocoded_candidate = True
            distance_m = haversine_distance_m(latitude, longitude, result.latitude, result.longitude)
            if distance_m <= self.radius_m:
                count += 1
        return count if saw_geocoded_candidate else None

    def _candidate_facilities(self, complex_row: dict[str, Any]) -> list[AcademyFacility]:
        facilities = self.facilities_by_city_district.get(
            (str(complex_row.get("city_code") or ""), str(complex_row.get("district_name") or "")),
            [],
        )
        legal_dongs = _legal_dong_match_keys(_split_multiline_values(complex_row.get("legal_dongs")))
        if legal_dongs:
            filtered = [
                facility
                for facility in facilities
                if any(dong and dong in facility.searchable_text for dong in legal_dongs)
            ]
            if filtered:
                self.stats["fallback_candidate_facilities"] += len(filtered)
                return filtered
        self.stats["fallback_candidate_facilities"] += len(facilities)
        return list(facilities)

    def _geocode_facility(self, facility: AcademyFacility) -> GeocodeResult | None:
        if facility.address not in self.geocode_cache:
            self.geocode_cache[facility.address] = self.geocoder.geocode(facility.address)
            self.stats["fallback_address_attempts"] += 1
            if self.sleep_seconds > 0:
                time.sleep(self.sleep_seconds)
        result = self.geocode_cache[facility.address]
        if result is None:
            self.stats["fallback_not_found_facilities"] += 1
        else:
            self.stats["fallback_geocoded_facilities"] += 1
        return result


def import_academy_count_snapshots_csv(
    connection: Any,
    primary_csv_path: str | Path,
    *,
    seoul_csv_path: str | Path,
    busan_csv_path: str | Path,
    geocoder: Geocoder,
    source_name: str = ACADEMY_SOURCE_NAME,
    radius_m: int = 500,
    sleep_seconds: float = 0.05,
    geocode_cache_path: str | Path | None = "artifacts/academy_geocode_cache.csv",
) -> dict[str, int]:
    region_by_lawd_cd = _load_region_by_lawd_cd(connection)
    primary_rows = read_nearby_academy_complex_csv(
        primary_csv_path,
        region_by_lawd_cd=region_by_lawd_cd,
    )
    fallback_facilities = read_academy_facility_csvs(
        seoul_csv_path=seoul_csv_path,
        busan_csv_path=busan_csv_path,
    )
    geocode_cache = _read_geocode_cache(geocode_cache_path) if geocode_cache_path else {}
    stats = import_academy_count_snapshots(
        connection,
        primary_rows,
        fallback_facilities,
        geocoder=geocoder,
        source_name=source_name,
        radius_m=radius_m,
        sleep_seconds=sleep_seconds,
        geocode_cache=geocode_cache,
    )
    if geocode_cache_path:
        _write_geocode_cache(geocode_cache_path, geocode_cache)
    return {
        "primary_source_rows": len(primary_rows),
        "primary_seoul_rows": sum(1 for row in primary_rows if row.city_code == "seoul"),
        "primary_busan_rows": sum(1 for row in primary_rows if row.city_code == "busan"),
        "fallback_facility_rows": len(fallback_facilities),
        **stats,
    }


def import_academy_count_snapshots(
    connection: Any,
    primary_complexes: Sequence[AcademyNearbyComplex],
    fallback_facilities: Sequence[AcademyFacility],
    *,
    geocoder: Geocoder,
    source_name: str = ACADEMY_SOURCE_NAME,
    radius_m: int = 500,
    sleep_seconds: float = 0.05,
    geocode_cache: dict[str, GeocodeResult | None] | None = None,
) -> dict[str, int]:
    matcher = AcademyComplexMatcher(primary_complexes)
    fallback_counter = FallbackAcademyCounter(
        fallback_facilities,
        geocoder,
        radius_m=radius_m,
        sleep_seconds=sleep_seconds,
        geocode_cache=geocode_cache,
    )
    cursor = connection.cursor(dictionary=True)
    stats = {
        "db_complexes": 0,
        "primary_matched_complexes": 0,
        "fallback_matched_complexes": 0,
        "unmatched_complexes": 0,
        "skipped_no_months": 0,
        "skipped_no_coordinates_for_fallback": 0,
        "snapshot_rows": 0,
        "changed_snapshot_rows": 0,
        "address_unique_matches": 0,
        "address_exact_name_matches": 0,
        "address_name_variant_matches": 0,
        "dong_matches": 0,
        "district_unique_matches": 0,
        "name_variant_matches": 0,
    }
    try:
        cursor.execute(SELECT_COMPLEXES_FOR_ACADEMY_COUNT_SQL)
        for complex_row in cursor.fetchall():
            stats["db_complexes"] += 1
            deal_months = _split_multiline_values(complex_row.get("deal_months"))
            if not deal_months:
                stats["skipped_no_months"] += 1
                continue

            match = matcher.match(complex_row)
            academy_count: int | None
            if match.complex is not None:
                academy_count = match.complex.academy_count
                stats["primary_matched_complexes"] += 1
                _count_match_kind(stats, match.kind)
            else:
                academy_count = fallback_counter.count_for_complex(complex_row)
                if academy_count is None:
                    if _optional_float(complex_row.get("latitude")) is None or _optional_float(complex_row.get("longitude")) is None:
                        stats["skipped_no_coordinates_for_fallback"] += 1
                    stats["unmatched_complexes"] += 1
                    continue
                stats["fallback_matched_complexes"] += 1

            for deal_month in deal_months:
                cursor.execute(
                    UPSERT_ACADEMY_COUNT_SQL,
                    (
                        complex_row["complex_id"],
                        deal_month,
                        source_name,
                        radius_m,
                        academy_count,
                    ),
                )
                stats["snapshot_rows"] += 1
                if cursor.rowcount > 0:
                    stats["changed_snapshot_rows"] += cursor.rowcount
        connection.commit()
        return {**stats, **fallback_counter.stats}
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def _load_region_by_lawd_cd(connection: Any) -> dict[str, tuple[str, str]]:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(SELECT_REGION_CODES_SQL)
        return {
            str(row["lawd_cd"]): (str(row["city_code"]), str(row["district_name"]))
            for row in cursor.fetchall()
        }
    finally:
        cursor.close()


def _read_seoul_academy_facilities(path: Path) -> list[AcademyFacility]:
    facilities: list[AcademyFacility] = []
    for row in _read_csv_rows(path):
        if _cell(row, "등록상태명") and _cell(row, "등록상태명") != "개원":
            continue
        district_name = _cell(row, "행정구역명")
        address = _cell(row, "도로명주소")
        facility_name = _cell(row, "학원명")
        if not district_name or not address or not facility_name:
            continue
        facilities.append(
            AcademyFacility(
                city_code="seoul",
                district_name=district_name,
                facility_name=facility_name,
                address=address,
                searchable_text=f"{address} {_cell(row, '도로명상세주소')}",
            )
        )
    return facilities


def _read_busan_academy_facilities(path: Path) -> list[AcademyFacility]:
    facilities: list[AcademyFacility] = []
    for row in _read_csv_rows(path):
        address = _cell(row, "주소")
        facility_name = _cell(row, "학원명")
        district_name = _busan_district_from_address(address)
        if not district_name or not address or not facility_name:
            continue
        facilities.append(
            AcademyFacility(
                city_code="busan",
                district_name=district_name,
                facility_name=facility_name,
                address=address,
                searchable_text=address,
            )
        )
    return facilities


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    last_error: UnicodeDecodeError | None = None
    for encoding in CSV_ENCODINGS:
        try:
            with path.open(encoding=encoding, newline="") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames is None:
                    raise ValueError(f"academy CSV header row was not found: {path}")
                return [dict(row) for row in reader]
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError(f"academy CSV could not be decoded: {path}") from last_error


def _dedupe_facilities(facilities: Sequence[AcademyFacility]) -> list[AcademyFacility]:
    seen: set[tuple[str, str, str, str]] = set()
    deduped: list[AcademyFacility] = []
    for facility in facilities:
        key = (facility.city_code, facility.district_name, facility.facility_name, facility.address)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(facility)
    return deduped


def _pick_candidate_by_name(
    candidates: Sequence[AcademyNearbyComplex],
    complex_name: str,
    *,
    min_score: float = 0.72,
    kind_prefix: str = "",
    allow_single_unique: bool = True,
) -> AcademyComplexMatch:
    if not candidates:
        return AcademyComplexMatch(None, "unmatched")
    if len(candidates) == 1 and allow_single_unique:
        return AcademyComplexMatch(candidates[0], "unique")

    normalized_name = normalize_complex_name(complex_name)
    exact_matches = [
        candidate
        for candidate in candidates
        if normalize_complex_name(candidate.complex_name) == normalized_name
    ]
    if len(exact_matches) == 1:
        return AcademyComplexMatch(exact_matches[0], "exact_name", 1.0)

    scored = sorted(
        (
            (_name_variant_score(complex_name, candidate.complex_name), candidate)
            for candidate in candidates
        ),
        key=lambda item: (-item[0], item[1].source_complex_id),
    )
    if not scored or scored[0][0] < min_score:
        return AcademyComplexMatch(None, "unmatched", scored[0][0] if scored else 0.0)
    if len(scored) > 1 and abs(scored[0][0] - scored[1][0]) < 0.0001:
        return AcademyComplexMatch(None, "ambiguous", scored[0][0])

    kind = "name_variant"
    if kind_prefix:
        kind = kind_prefix
    return AcademyComplexMatch(scored[0][1], kind, scored[0][0])


def _name_variant_score(left: str, right: str) -> float:
    lhs = normalize_variant_complex_name(left)
    rhs = normalize_variant_complex_name(right)
    if not lhs or not rhs:
        return 0.0
    score = difflib.SequenceMatcher(None, lhs, rhs).ratio()
    if lhs in rhs or rhs in lhs:
        score = max(score, 0.92)
    return score


def _address_match_keys(value: object) -> list[str]:
    keys: list[str] = []
    for address in _split_address_values(value):
        variants = [address, _trim_jibun_detail(address)]
        for variant in variants:
            key = _normalize_address(variant)
            if key and key not in keys:
                keys.append(key)
    return keys


def _split_address_values(value: object) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    return [
        re.sub(r"\s+", " ", part.strip())
        for part in re.split(r"\s*,\s*", text)
        if part.strip()
    ]


def _trim_jibun_detail(address: object) -> str:
    text = re.sub(r"\s+", " ", str(address or "").strip())
    match = re.match(r"^(.+?(?:동|가|리)\s+)(\d+(?:-\d+)?)-?(?:\s+.+)?$", text)
    if match is None:
        return text
    lot_number = match.group(2)
    if lot_number == "0":
        return text
    return f"{match.group(1)}{lot_number}".strip()


def _normalize_address(value: object) -> str:
    return re.sub(r"[\s,()（）]+", "", str(value or "").strip().lower())


def _legal_dong_from_address(address: str) -> str:
    for part in re.split(r"\s+", address or ""):
        if part.endswith(("동", "가", "리")):
            return part
    return ""


def _legal_dong_match_keys(values: Sequence[str]) -> set[str]:
    keys: set[str] = set()
    for value in values:
        stripped = (value or "").strip()
        if not stripped:
            continue
        keys.add(stripped)
        keys.add(normalize_legal_dong_name(stripped))
    return keys


def _split_multiline_values(value: object) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in str(value).split("\n") if item.strip()]


def _busan_district_from_address(address: str) -> str:
    match = re.search(r"부산광역시\s+([^\s]+)", address or "")
    return match.group(1) if match else ""


def _cell(row: dict[str, str], name: str) -> str:
    return (row.get(name) or "").strip()


def _optional_int(value: str) -> int | None:
    text = (value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _count_match_kind(stats: dict[str, int], kind: str) -> None:
    key = f"{kind}_matches"
    if key in stats:
        stats[key] += 1


def _read_geocode_cache(path: str | Path) -> dict[str, GeocodeResult | None]:
    cache_path = Path(path)
    if not cache_path.exists():
        return {}
    cache: dict[str, GeocodeResult | None] = {}
    with cache_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            address = _cell(row, "address")
            if not address:
                continue
            if _cell(row, "found") != "1":
                cache[address] = None
                continue
            latitude = _optional_float(row.get("latitude"))
            longitude = _optional_float(row.get("longitude"))
            if latitude is None or longitude is None:
                cache[address] = None
            else:
                cache[address] = GeocodeResult(latitude=latitude, longitude=longitude, matched_address=_cell(row, "matched_address"))
    return cache


def _write_geocode_cache(path: str | Path, cache: dict[str, GeocodeResult | None]) -> None:
    cache_path = Path(path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["address", "found", "latitude", "longitude", "matched_address"])
        writer.writeheader()
        for address in sorted(cache):
            result = cache[address]
            writer.writerow(
                {
                    "address": address,
                    "found": "1" if result is not None else "0",
                    "latitude": result.latitude if result is not None else "",
                    "longitude": result.longitude if result is not None else "",
                    "matched_address": result.matched_address if result is not None else "",
                }
            )
