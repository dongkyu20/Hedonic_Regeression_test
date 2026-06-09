from __future__ import annotations

import csv
import difflib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from hedonic_house_price.complex_info import (
    ComplexBasicInfo,
    find_complex_basic_info_match,
    is_apartment_like_category,
    normalize_variant_complex_name,
    read_complex_basic_info_csv,
)
from hedonic_house_price.db import get_mysql_connection


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_KAPT_CSV = ROOT_DIR / "data" / "complex_export" / "complex_basic_info.csv"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "data" / "complex_matching_reports"


def main() -> None:
    kapt_csv = DEFAULT_KAPT_CSV
    output_dir = DEFAULT_OUTPUT_DIR
    kapt_rows = [
        row
        for row in read_complex_basic_info_csv(kapt_csv)
        if is_apartment_like_category(row.complex_category)
    ]
    raw_rows = _load_kapt_raw_rows(kapt_csv)
    db_rows = _load_db_complexes()
    db_candidates = _db_rows_as_complex_basic_info(db_rows)

    transaction_rows = _transaction_unmatched_rows(db_rows, kapt_rows)
    kapt_unmatched_rows = _kapt_unmatched_rows(kapt_rows, raw_rows, db_rows, db_candidates)

    transaction_rows.sort(
        key=lambda row: (
            str(row["city_code"]),
            str(row["district_name"]),
            -int(row["transaction_count"] or 0),
            str(row["db_complex_name"]),
        )
    )
    kapt_unmatched_rows.sort(
        key=lambda row: (
            str(row["city_code"]),
            str(row["district_name"]),
            str(row["legal_dong_name"]),
            str(row["source_complex_name"]),
        )
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "transaction_complex_unmatched.csv", transaction_rows, TRANSACTION_FIELDS)
    _write_csv(output_dir / "kapt_complex_info_unmatched.csv", kapt_unmatched_rows, KAPT_FIELDS)
    _write_csv(output_dir / "unmatched_complexes_all.csv", transaction_rows + kapt_unmatched_rows, COMBINED_FIELDS)

    summary = {
        "output_dir": str(output_dir),
        "transaction_complex_unmatched_rows": len(transaction_rows),
        "kapt_complex_info_unmatched_rows": len(kapt_unmatched_rows),
        "combined_rows": len(transaction_rows) + len(kapt_unmatched_rows),
        "transaction_reason_counts": dict(Counter(row["reason"] for row in transaction_rows)),
        "kapt_reason_counts": dict(Counter(row["reason"] for row in kapt_unmatched_rows)),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def _transaction_unmatched_rows(
    db_rows: list[dict[str, Any]],
    kapt_rows: list[ComplexBasicInfo],
) -> list[dict[str, Any]]:
    source_districts = {(row.city_code, row.district_name) for row in kapt_rows}
    source_dongs = {(row.city_code, row.district_name, row.legal_dong_name) for row in kapt_rows}
    rows: list[dict[str, Any]] = []
    for db_row in db_rows:
        city_code = str(db_row["city_code"])
        district_name = str(db_row["district_name"])
        legal_dongs = _split_dongs(db_row.get("legal_dongs"))
        match = find_complex_basic_info_match(
            kapt_rows,
            city_code=city_code,
            district_name=district_name,
            legal_dong_names=legal_dongs,
            complex_name=str(db_row["complex_name"]),
        )
        if match.info is not None:
            continue

        scope, score, candidate = _best_kapt_candidate(db_row, kapt_rows)
        reason = _remaining_reason(
            match_kind=match.kind,
            has_district=(city_code, district_name) in source_districts,
            has_dong=any((city_code, district_name, dong) in source_dongs for dong in legal_dongs),
        )
        rows.append(
            {
                "basis": "transaction_history",
                "reason": reason,
                "city_code": city_code,
                "city_name": db_row["city_name"],
                "district_name": district_name,
                "legal_dong_names": "|".join(legal_dongs),
                "db_complex_id": db_row["complex_id"],
                "db_complex_name": db_row["complex_name"],
                "transaction_count": db_row["transaction_count"],
                "first_deal_yyyymm": db_row["first_deal_yyyymm"],
                "last_deal_yyyymm": db_row["last_deal_yyyymm"],
                "min_build_year": db_row["min_build_year"],
                "max_build_year": db_row["max_build_year"],
                "min_exclusive_area_m2": db_row["min_exclusive_area_m2"],
                "max_exclusive_area_m2": db_row["max_exclusive_area_m2"],
                "current_road_address": db_row["road_address"] or "",
                "current_jibun_address": db_row["jibun_address"] or "",
                "best_candidate_scope": scope,
                "best_candidate_score": round(score, 4),
                "candidate_source_complex_code": candidate.source_complex_code if candidate else "",
                "candidate_complex_name": candidate.complex_name if candidate else "",
                "candidate_complex_category": candidate.complex_category if candidate else "",
                "candidate_legal_dong_name": candidate.legal_dong_name if candidate else "",
                "candidate_road_address": candidate.road_address if candidate else "",
                "candidate_jibun_address": candidate.jibun_address if candidate else "",
                "match_kind": match.kind,
                "match_score": round(match.score, 4),
            }
        )
    return rows


def _kapt_unmatched_rows(
    kapt_rows: list[ComplexBasicInfo],
    raw_rows: dict[str, dict[str, str]],
    db_rows: list[dict[str, Any]],
    db_candidates: list[ComplexBasicInfo],
) -> list[dict[str, Any]]:
    db_districts = {(str(row["city_code"]), str(row["district_name"])) for row in db_rows}
    db_dongs = {
        (str(row["city_code"]), str(row["district_name"]), dong)
        for row in db_rows
        for dong in _split_dongs(row.get("legal_dongs"))
    }
    rows: list[dict[str, Any]] = []
    for kapt_row in kapt_rows:
        match = find_complex_basic_info_match(
            db_candidates,
            city_code=kapt_row.city_code,
            district_name=kapt_row.district_name,
            legal_dong_names=[kapt_row.legal_dong_name],
            complex_name=kapt_row.complex_name,
        )
        if match.info is not None:
            continue

        scope, score, candidate = _best_db_candidate(kapt_row, db_rows)
        raw = raw_rows.get(kapt_row.source_complex_code, {})
        reason = _remaining_reason(
            match_kind=match.kind,
            has_district=(kapt_row.city_code, kapt_row.district_name) in db_districts,
            has_dong=(kapt_row.city_code, kapt_row.district_name, kapt_row.legal_dong_name) in db_dongs,
        )
        rows.append(
            {
                "basis": "kapt_complex_info",
                "reason": reason,
                "city_code": kapt_row.city_code,
                "city_name": kapt_row.city_name,
                "district_name": kapt_row.district_name,
                "legal_dong_name": kapt_row.legal_dong_name,
                "source_complex_code": kapt_row.source_complex_code,
                "source_complex_name": kapt_row.complex_name,
                "source_complex_category": kapt_row.complex_category,
                "source_road_address": kapt_row.road_address,
                "source_jibun_address": kapt_row.jibun_address,
                "approval_date": raw.get("사용승인일", ""),
                "building_count": raw.get("동수", ""),
                "household_count": raw.get("세대수", ""),
                "total_parking_spaces": raw.get("총주차대수", ""),
                "max_floor": raw.get("최고층수", ""),
                "amenities": raw.get("입주편의시설", ""),
                "best_candidate_scope": scope,
                "best_candidate_score": round(score, 4),
                "candidate_db_complex_id": candidate["complex_id"] if candidate else "",
                "candidate_db_complex_name": candidate["complex_name"] if candidate else "",
                "candidate_legal_dong_names": "|".join(_split_dongs(candidate.get("legal_dongs"))) if candidate else "",
                "candidate_transaction_count": candidate["transaction_count"] if candidate else "",
                "candidate_first_deal_yyyymm": candidate["first_deal_yyyymm"] if candidate else "",
                "candidate_last_deal_yyyymm": candidate["last_deal_yyyymm"] if candidate else "",
                "match_kind": match.kind,
                "match_score": round(match.score, 4),
            }
        )
    return rows


def _load_db_complexes() -> list[dict[str, Any]]:
    connection = get_mysql_connection()
    cursor = connection.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT
          c.complex_id,
          c.complex_name,
          c.road_address,
          c.jibun_address,
          r.city_code,
          r.city_name,
          r.district_name,
          GROUP_CONCAT(DISTINCT t.legal_dong_name ORDER BY t.legal_dong_name SEPARATOR '\n') AS legal_dongs,
          COUNT(t.transaction_id) AS transaction_count,
          MIN(t.deal_yyyymm) AS first_deal_yyyymm,
          MAX(t.deal_yyyymm) AS last_deal_yyyymm,
          MIN(t.build_year) AS min_build_year,
          MAX(t.build_year) AS max_build_year,
          MIN(t.exclusive_area_m2) AS min_exclusive_area_m2,
          MAX(t.exclusive_area_m2) AS max_exclusive_area_m2
        FROM housing_complexes c
        JOIN administrative_regions r ON r.region_id = c.region_id
        LEFT JOIN housing_transactions t ON t.complex_id = c.complex_id
        WHERE c.property_type = 'apartment'
          AND r.city_code IN ('seoul', 'busan')
        GROUP BY c.complex_id, c.complex_name, c.road_address, c.jibun_address,
                 r.city_code, r.city_name, r.district_name
        """
    )
    rows = list(cursor.fetchall())
    cursor.close()
    connection.close()
    return rows


def _load_kapt_raw_rows(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = None
        for row in reader:
            if {"시도", "시군구", "동리", "단지코드", "단지명"}.issubset(set(row)):
                header = row
                break
        if header is None:
            raise RuntimeError("K-apt CSV header was not found")
        index = {name: idx for idx, name in enumerate(header)}
        rows = {}
        for raw in reader:
            if len(raw) < len(header):
                raw += [""] * (len(header) - len(raw))
            code = raw[index["단지코드"]].strip()
            if code:
                rows[code] = {name: raw[idx].strip() for name, idx in index.items()}
        return rows


def _db_rows_as_complex_basic_info(db_rows: list[dict[str, Any]]) -> list[ComplexBasicInfo]:
    candidates: list[ComplexBasicInfo] = []
    for row in db_rows:
        legal_dongs = _split_dongs(row.get("legal_dongs")) or [""]
        for legal_dong in legal_dongs:
            candidates.append(
                ComplexBasicInfo(
                    city_code=str(row["city_code"]),
                    city_name=str(row["city_name"]),
                    district_name=str(row["district_name"]),
                    legal_dong_name=legal_dong,
                    source_complex_code=str(row["complex_id"]),
                    complex_name=str(row["complex_name"]),
                    complex_category="apartment",
                    jibun_address=str(row["jibun_address"] or ""),
                    road_address=str(row["road_address"] or ""),
                )
            )
    return candidates


def _best_kapt_candidate(
    db_row: dict[str, Any],
    kapt_rows: list[ComplexBasicInfo],
) -> tuple[str, float, ComplexBasicInfo | None]:
    city_code = str(db_row["city_code"])
    district_name = str(db_row["district_name"])
    legal_dongs = set(_split_dongs(db_row.get("legal_dongs")))
    best: tuple[str, float, ComplexBasicInfo | None] = ("", 0.0, None)
    for candidate in kapt_rows:
        if candidate.city_code != city_code or candidate.district_name != district_name:
            continue
        scope = "same_legal_dong" if candidate.legal_dong_name in legal_dongs else "same_district"
        score = _name_score(str(db_row["complex_name"]), candidate.complex_name)
        if score > best[1]:
            best = (scope, score, candidate)
    return best


def _best_db_candidate(
    kapt_row: ComplexBasicInfo,
    db_rows: list[dict[str, Any]],
) -> tuple[str, float, dict[str, Any] | None]:
    best: tuple[str, float, dict[str, Any] | None] = ("", 0.0, None)
    for candidate in db_rows:
        if candidate["city_code"] != kapt_row.city_code or candidate["district_name"] != kapt_row.district_name:
            continue
        legal_dongs = set(_split_dongs(candidate.get("legal_dongs")))
        scope = "same_legal_dong" if kapt_row.legal_dong_name in legal_dongs else "same_district"
        score = _name_score(kapt_row.complex_name, str(candidate["complex_name"]))
        if score > best[1]:
            best = (scope, score, candidate)
    return best


def _name_score(left: str, right: str) -> float:
    lhs = normalize_variant_complex_name(left)
    rhs = normalize_variant_complex_name(right)
    if not lhs or not rhs:
        return 0.0
    score = difflib.SequenceMatcher(None, lhs, rhs).ratio()
    if lhs in rhs or rhs in lhs:
        score = max(score, 0.92)
    return score


def _remaining_reason(*, match_kind: str, has_district: bool, has_dong: bool) -> str:
    if match_kind.startswith("ambiguous"):
        return match_kind
    if not has_district:
        return "no_counterpart_district"
    if not has_dong:
        return "no_counterpart_legal_dong"
    return "counterpart_has_dong_but_name_absent"


def _split_dongs(value: object) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in str(value).split("\n") if item.strip()]


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


TRANSACTION_FIELDS = [
    "basis",
    "reason",
    "city_code",
    "city_name",
    "district_name",
    "legal_dong_names",
    "db_complex_id",
    "db_complex_name",
    "transaction_count",
    "first_deal_yyyymm",
    "last_deal_yyyymm",
    "min_build_year",
    "max_build_year",
    "min_exclusive_area_m2",
    "max_exclusive_area_m2",
    "current_road_address",
    "current_jibun_address",
    "best_candidate_scope",
    "best_candidate_score",
    "candidate_source_complex_code",
    "candidate_complex_name",
    "candidate_complex_category",
    "candidate_legal_dong_name",
    "candidate_road_address",
    "candidate_jibun_address",
    "match_kind",
    "match_score",
]

KAPT_FIELDS = [
    "basis",
    "reason",
    "city_code",
    "city_name",
    "district_name",
    "legal_dong_name",
    "source_complex_code",
    "source_complex_name",
    "source_complex_category",
    "source_road_address",
    "source_jibun_address",
    "approval_date",
    "building_count",
    "household_count",
    "total_parking_spaces",
    "max_floor",
    "amenities",
    "best_candidate_scope",
    "best_candidate_score",
    "candidate_db_complex_id",
    "candidate_db_complex_name",
    "candidate_legal_dong_names",
    "candidate_transaction_count",
    "candidate_first_deal_yyyymm",
    "candidate_last_deal_yyyymm",
    "match_kind",
    "match_score",
]

COMBINED_FIELDS = [
    "basis",
    "reason",
    "city_code",
    "city_name",
    "district_name",
    "legal_dong_names",
    "legal_dong_name",
    "db_complex_id",
    "db_complex_name",
    "source_complex_code",
    "source_complex_name",
    "source_complex_category",
    "transaction_count",
    "first_deal_yyyymm",
    "last_deal_yyyymm",
    "source_road_address",
    "source_jibun_address",
    "current_road_address",
    "current_jibun_address",
    "best_candidate_scope",
    "best_candidate_score",
    "candidate_source_complex_code",
    "candidate_complex_name",
    "candidate_db_complex_id",
    "candidate_db_complex_name",
    "match_kind",
    "match_score",
]


if __name__ == "__main__":
    main()
