from __future__ import annotations

import csv
import difflib
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

APARTMENT_LIKE_COMPLEX_CATEGORIES = {
    "아파트",
    "주상복합",
    "도시형 생활주택(아파트)",
    "도시형 생활주택(주상복합)",
}

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

RESET_COMPLEX_ADDRESS_SQL = """
UPDATE housing_complexes c
JOIN administrative_regions r ON r.region_id = c.region_id
SET
  c.road_address = NULL,
  c.jibun_address = NULL,
  c.updated_at = CURRENT_TIMESTAMP
WHERE c.property_type = 'apartment'
  AND r.city_code IN ('seoul', 'busan')
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
    score: float = 0.0


def normalize_complex_name(value: str) -> str:
    return re.sub(r"[\s·ㆍ\-_()（）\[\]{}]+", "", (value or "").strip().lower())


def normalize_legal_dong_name(value: str) -> str:
    normalized = re.sub(r"\s+", " ", (value or "").strip())
    parts = normalized.split(" ")
    if len(parts) >= 2 and parts[-2].endswith(("읍", "면")) and parts[-1].endswith("리"):
        return parts[-1]
    return normalized


def normalize_variant_complex_name(value: str) -> str:
    normalized = normalize_complex_name(value)
    replacements = (
        ("에스케이", "sk"),
        ("지에스", "gs"),
        ("엘에이치", "lh"),
        ("이편한세상", "e편한세상"),
    )
    for old, new in replacements:
        normalized = normalized.replace(old, new)
    for suffix in ("아파트", "apt", "분양", "임대", "공공임대", "영구임대", "민간임대"):
        normalized = normalized.replace(suffix, "")
    return normalized


def is_apartment_like_category(value: str) -> bool:
    return (value or "").strip() in APARTMENT_LIKE_COMPLEX_CATEGORIES


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
    accept_remaining_matches: bool = False,
) -> ComplexMatch:
    by_dong, by_district = _build_match_indexes(candidates)
    return _find_match_in_indexes(
        by_dong,
        by_district,
        city_code=city_code,
        district_name=district_name,
        legal_dong_names=legal_dong_names,
        complex_name=complex_name,
        accept_remaining_matches=accept_remaining_matches,
    )


def _find_match_in_indexes(
    by_dong: dict[tuple[str, str, str, str], list[ComplexBasicInfo]],
    by_district: dict[tuple[str, str, str], list[ComplexBasicInfo]],
    *,
    city_code: str,
    district_name: str,
    legal_dong_names: list[str],
    complex_name: str,
    accept_remaining_matches: bool = False,
) -> ComplexMatch:
    normalized_name = normalize_complex_name(complex_name)

    saw_ambiguous_dong = False
    for legal_dong_name in _legal_dong_match_keys(legal_dong_names):
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

    return _find_name_variant_match(
        by_dong,
        by_district,
        city_code=city_code,
        district_name=district_name,
        legal_dong_names=legal_dong_names,
        complex_name=complex_name,
        accept_remaining_matches=accept_remaining_matches,
    )


def import_complex_basic_info_csv(
    connection: Any,
    csv_path: str | Path,
    *,
    reset_addresses: bool = False,
    accept_remaining_matches: bool = False,
) -> dict[str, int]:
    candidates = [
        candidate
        for candidate in read_complex_basic_info_csv(csv_path)
        if is_apartment_like_category(candidate.complex_category)
    ]
    by_dong, by_district = _build_match_indexes(candidates)
    cursor = connection.cursor(dictionary=True)
    stats = {
        "source_rows": len(candidates),
        "reset_complex_addresses": 0,
        "db_complexes": 0,
        "matched_complexes": 0,
        "updated_complexes": 0,
        "unmatched_complexes": 0,
        "ambiguous_complexes": 0,
        "empty_address_matches": 0,
        "dong_matches": 0,
        "district_unique_matches": 0,
        "likely_name_variant_matches": 0,
        "possible_name_variant_matches": 0,
        "ambiguous_name_variant_matches": 0,
        "counterpart_has_dong_but_name_absent_matches": 0,
    }
    try:
        if reset_addresses:
            cursor.execute(RESET_COMPLEX_ADDRESS_SQL)
            stats["reset_complex_addresses"] = cursor.rowcount

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
                accept_remaining_matches=accept_remaining_matches,
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
            elif match.kind == "likely_name_variant":
                stats["likely_name_variant_matches"] += 1
            elif match.kind == "possible_name_variant":
                stats["possible_name_variant_matches"] += 1
            elif match.kind == "ambiguous_name_variant":
                stats["ambiguous_name_variant_matches"] += 1
            elif match.kind == "counterpart_has_dong_but_name_absent":
                stats["counterpart_has_dong_but_name_absent_matches"] += 1

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
        for legal_dong_name in _legal_dong_match_keys([row.legal_dong_name]):
            by_dong.setdefault(
                (row.city_code, row.district_name, legal_dong_name, normalized_name),
                [],
            ).append(row)
        by_district.setdefault(
            (row.city_code, row.district_name, normalized_name),
            [],
        ).append(row)
    return by_dong, by_district


def _find_name_variant_match(
    by_dong: dict[tuple[str, str, str, str], list[ComplexBasicInfo]],
    by_district: dict[tuple[str, str, str], list[ComplexBasicInfo]],
    *,
    city_code: str,
    district_name: str,
    legal_dong_names: list[str],
    complex_name: str,
    accept_remaining_matches: bool,
) -> ComplexMatch:
    candidates_by_code: dict[str, tuple[ComplexBasicInfo, str]] = {}
    legal_dong_match_keys = _legal_dong_match_keys(legal_dong_names)
    for (candidate_city, candidate_district, candidate_dong, _), candidates in by_dong.items():
        if candidate_city != city_code or candidate_district != district_name:
            continue
        if candidate_dong not in legal_dong_match_keys:
            continue
        for candidate in candidates:
            candidates_by_code[candidate.source_complex_code] = (candidate, "same_legal_dong")

    for (candidate_city, candidate_district, _), candidates in by_district.items():
        if candidate_city != city_code or candidate_district != district_name:
            continue
        for candidate in candidates:
            candidates_by_code.setdefault(candidate.source_complex_code, (candidate, "same_district"))

    best_score = 0.0
    best_candidates: list[tuple[ComplexBasicInfo, str]] = []
    for candidate, scope in candidates_by_code.values():
        score = _name_variant_score(complex_name, candidate.complex_name)
        if score > best_score:
            best_score = score
            best_candidates = [(candidate, scope)]
        elif abs(score - best_score) < 0.0001:
            best_candidates.append((candidate, scope))

    if best_score < 0.72:
        if accept_remaining_matches:
            same_dong_match = _best_same_dong_candidate(complex_name, candidates_by_code)
            if same_dong_match is not None:
                candidate, score = same_dong_match
                return ComplexMatch(
                    info=candidate,
                    kind="counterpart_has_dong_but_name_absent",
                    score=score,
                )
        return ComplexMatch(info=None, kind="unmatched", score=best_score)
    if len(best_candidates) != 1:
        if accept_remaining_matches:
            candidate = sorted(
                (candidate for candidate, _ in best_candidates),
                key=lambda item: item.source_complex_code,
            )[0]
            return ComplexMatch(info=candidate, kind="ambiguous_name_variant", score=best_score)
        return ComplexMatch(info=None, kind="ambiguous_name_variant", score=best_score)

    kind = "likely_name_variant" if best_score >= 0.9 else "possible_name_variant"
    return ComplexMatch(info=best_candidates[0][0], kind=kind, score=best_score)


def _best_same_dong_candidate(
    complex_name: str,
    candidates_by_code: dict[str, tuple[ComplexBasicInfo, str]],
) -> tuple[ComplexBasicInfo, float] | None:
    same_dong_candidates = [
        candidate
        for candidate, scope in candidates_by_code.values()
        if scope == "same_legal_dong"
    ]
    if not same_dong_candidates:
        return None

    ranked = sorted(
        (
            (_name_variant_score(complex_name, candidate.complex_name), candidate)
            for candidate in same_dong_candidates
        ),
        key=lambda item: (-item[0], item[1].source_complex_code),
    )
    best_score, best_candidate = ranked[0]
    return best_candidate, best_score


def _name_variant_score(left: str, right: str) -> float:
    lhs = normalize_variant_complex_name(left)
    rhs = normalize_variant_complex_name(right)
    if not lhs or not rhs:
        return 0.0
    score = difflib.SequenceMatcher(None, lhs, rhs).ratio()
    if lhs in rhs or rhs in lhs:
        score = max(score, 0.92)
    return score


def _split_legal_dongs(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split("\n") if item.strip()]


def _legal_dong_match_keys(values: list[str]) -> set[str]:
    keys: set[str] = set()
    for value in values:
        stripped = (value or "").strip()
        if not stripped:
            continue
        keys.add(stripped)
        keys.add(normalize_legal_dong_name(stripped))
    return keys
