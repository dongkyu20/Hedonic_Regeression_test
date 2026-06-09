from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .config import load_env_file


KAKAO_REST_API_KEY_ENV = "KAKAO_REST_API_KEY"
KAKAO_ADDRESS_SEARCH_URL = "https://dapi.kakao.com/v2/local/search/address.json"

SELECT_GEOCODING_CANDIDATES_SQL = """
SELECT
  c.complex_id,
  c.road_address,
  c.jibun_address
FROM housing_complexes c
JOIN administrative_regions r ON r.region_id = c.region_id
WHERE c.property_type = 'apartment'
  AND r.city_code IN ('seoul', 'busan')
  AND (c.road_address IS NOT NULL OR c.jibun_address IS NOT NULL)
"""

UPDATE_COMPLEX_COORDINATES_SQL = """
UPDATE housing_complexes
SET
  latitude = %s,
  longitude = %s,
  updated_at = CURRENT_TIMESTAMP
WHERE complex_id = %s
"""


@dataclass(frozen=True)
class GeocodeResult:
    latitude: float
    longitude: float
    matched_address: str = ""


class Geocoder(Protocol):
    def geocode(self, address: str) -> GeocodeResult | None:
        ...


class KakaoGeocoder:
    def __init__(self, rest_api_key: str):
        self.rest_api_key = rest_api_key.strip()
        if not self.rest_api_key:
            raise ValueError("Kakao REST API key is required")

    def geocode(self, address: str) -> GeocodeResult | None:
        query = urllib.parse.urlencode({"query": address})
        request = urllib.request.Request(
            f"{KAKAO_ADDRESS_SEARCH_URL}?{query}",
            headers={"Authorization": f"KakaoAK {self.rest_api_key}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Kakao geocoding failed with HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Kakao geocoding request failed: {exc.reason}") from exc

        return parse_kakao_address_response(payload)


def get_kakao_rest_api_key(
    env: dict[str, str] | None = None,
    env_path: str | Path = ".env",
) -> str:
    merged: dict[str, str] = {}
    merged.update(load_env_file(env_path))
    merged.update(os.environ)
    if env is not None:
        merged.update(env)

    api_key = merged.get(KAKAO_REST_API_KEY_ENV, "").strip()
    if not api_key:
        raise RuntimeError(f"{KAKAO_REST_API_KEY_ENV} is required. Put it in .env or export it.")
    return api_key


def parse_kakao_address_response(payload: dict[str, Any]) -> GeocodeResult | None:
    documents = payload.get("documents") or []
    if not documents:
        return None
    first = documents[0]
    try:
        longitude = float(first["x"])
        latitude = float(first["y"])
    except (KeyError, TypeError, ValueError):
        return None
    return GeocodeResult(
        latitude=latitude,
        longitude=longitude,
        matched_address=str(first.get("address_name") or first.get("road_address_name") or ""),
    )


def geocode_missing_complex_coordinates(
    connection: Any,
    geocoder: Geocoder,
    *,
    city_code: str | None = None,
    limit: int | None = None,
    overwrite: bool = False,
    sleep_seconds: float = 0.1,
) -> dict[str, int]:
    cursor = connection.cursor(dictionary=True)
    stats = {
        "candidate_complexes": 0,
        "updated_complexes": 0,
        "not_found_complexes": 0,
        "failed_complexes": 0,
        "skipped_no_address": 0,
        "address_attempts": 0,
    }
    cache: dict[str, GeocodeResult | None] = {}
    try:
        cursor.execute(
            _candidate_query(city_code=city_code, limit=limit, overwrite=overwrite),
            tuple(_candidate_params(city_code=city_code, limit=limit)),
        )
        for row in cursor.fetchall():
            stats["candidate_complexes"] += 1
            addresses = _address_candidates(row)
            if not addresses:
                stats["skipped_no_address"] += 1
                continue

            try:
                result = _geocode_first_match(
                    geocoder,
                    addresses,
                    cache,
                    stats,
                    sleep_seconds=sleep_seconds,
                )
            except Exception:
                stats["failed_complexes"] += 1
                raise

            if result is None:
                stats["not_found_complexes"] += 1
                continue

            cursor.execute(
                UPDATE_COMPLEX_COORDINATES_SQL,
                (result.latitude, result.longitude, row["complex_id"]),
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


def _candidate_query(*, city_code: str | None, limit: int | None, overwrite: bool) -> str:
    clauses = []
    if not overwrite:
        clauses.append("(c.latitude IS NULL OR c.longitude IS NULL)")
    if city_code:
        clauses.append("r.city_code = %s")
    where = ""
    if clauses:
        where = "\n  AND " + "\n  AND ".join(clauses)
    limit_sql = "\nLIMIT %s" if limit is not None else ""
    return f"{SELECT_GEOCODING_CANDIDATES_SQL}{where}\nORDER BY c.complex_id{limit_sql}"


def _candidate_params(*, city_code: str | None, limit: int | None) -> list[object]:
    params: list[object] = []
    if city_code:
        params.append(city_code.strip().lower())
    if limit is not None:
        params.append(limit)
    return params


def _address_candidates(row: dict[str, Any]) -> list[str]:
    candidates = []
    for value in (row.get("road_address"), row.get("jibun_address")):
        for address in _split_address_values(value):
            for candidate in _address_variants(address):
                if candidate and candidate not in candidates:
                    candidates.append(candidate)
    return candidates


def _split_address_values(value: object) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    return [
        re.sub(r"\s+", " ", part.strip())
        for part in re.split(r"\s*,\s*", text)
        if part.strip()
    ]


def _address_variants(address: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", address.strip())
    variants = [normalized]
    trimmed = _trim_jibun_detail(normalized)
    if trimmed and trimmed not in variants:
        variants.append(trimmed)
    return variants


def _trim_jibun_detail(address: str) -> str | None:
    match = re.match(r"^(.+?(?:동|가|리)\s+)(\d+(?:-\d+)?)-?(?:\s+.+)?$", address)
    if match is None:
        return None
    lot_number = match.group(2)
    if lot_number == "0":
        return None
    return f"{match.group(1)}{lot_number}".strip()


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
            stats["address_attempts"] += 1
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
        result = cache[address]
        if result is not None:
            return result
    return None
