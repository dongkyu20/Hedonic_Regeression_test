from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FeatureSpec:
    category: str
    column: str
    label: str


@dataclass(frozen=True)
class CoverageRow:
    category: str
    column: str
    label: str
    total_rows: int
    non_null_rows: int
    missing_rows: int
    coverage_pct: float
    seoul_rows: int
    seoul_non_null_rows: int
    seoul_coverage_pct: float
    busan_rows: int
    busan_non_null_rows: int
    busan_coverage_pct: float
    status: str


FEATURE_SPECS = [
    FeatureSpec("core_transaction", "exclusive_area_m2", "전용면적"),
    FeatureSpec("core_transaction", "floor", "층수"),
    FeatureSpec("core_transaction", "build_year", "건축연도"),
    FeatureSpec("property_condition", "household_count", "세대수"),
    FeatureSpec("property_condition", "building_count", "동수"),
    FeatureSpec("property_condition", "total_parking_spaces", "주차대수"),
    FeatureSpec("property_condition", "parking_spaces_per_household", "세대당 주차대수"),
    FeatureSpec("property_condition", "has_community_facilities", "입주 편의시설 여부"),
    FeatureSpec("transport_access", "nearest_subway_distance_m", "지하철역까지 거리"),
    FeatureSpec("transport_access", "subway_count_radius", "반경 내 지하철 수"),
    FeatureSpec("transport_access", "nearest_bus_stop_distance_m", "버스 정류장까지 거리"),
    FeatureSpec("transport_access", "bus_stop_count_radius", "반경 내 버스 정류장 수"),
    FeatureSpec("transport_access", "car_intercity_bus_terminal_minutes", "승용차 시외버스터미널 평균접근시간"),
    FeatureSpec("transport_access", "car_airport_minutes", "승용차 공항 평균접근시간"),
    FeatureSpec("transport_access", "car_rail_station_minutes", "승용차 철도역 평균접근시간"),
    FeatureSpec("transport_access", "car_general_hospital_minutes", "승용차 종합병원 평균접근시간"),
    FeatureSpec("transport_access", "transit_intercity_bus_terminal_minutes", "대중교통 시외버스터미널 평균접근시간"),
    FeatureSpec("transport_access", "transit_airport_minutes", "대중교통 공항 평균접근시간"),
    FeatureSpec("transport_access", "transit_rail_station_minutes", "대중교통 철도역 평균접근시간"),
    FeatureSpec("transport_access", "transit_general_hospital_minutes", "대중교통 종합병원 평균접근시간"),
    FeatureSpec("living_environment", "nearest_elementary_school_distance_m", "초등학교 거리"),
    FeatureSpec("living_environment", "nearest_middle_school_distance_m", "중학교 거리"),
    FeatureSpec("living_environment", "school_count_radius", "반경 내 학교 수"),
    FeatureSpec("living_environment", "academy_count_radius", "학원 수"),
    FeatureSpec("living_environment", "nearest_hospital_distance_m", "병원 거리"),
    FeatureSpec("living_environment", "nearest_pharmacy_distance_m", "약국 거리"),
    FeatureSpec("living_environment", "nearest_park_distance_m", "공원 거리"),
    FeatureSpec("living_environment", "park_area_total_m2_radius", "공원 면적 합계"),
    FeatureSpec("urban_competitiveness", "population_count", "인구 수"),
    FeatureSpec("urban_competitiveness", "population_growth_rate", "인구 증가율"),
    FeatureSpec("urban_competitiveness", "employment_rate", "도시 고용률"),
    FeatureSpec("urban_competitiveness", "recent_transaction_count", "최근 거래량"),
    FeatureSpec("urban_competitiveness", "income_level_krw", "소득수준"),
    FeatureSpec("urban_competitiveness", "unsold_housing_count", "미분양 주택 수"),
    FeatureSpec("urban_competitiveness", "completed_housing_supply_count", "준공 물량"),
]

_FEATURE_COLUMNS = {spec.column for spec in FEATURE_SPECS}


def build_coverage_rows(
    specs: list[FeatureSpec],
    *,
    totals: dict[str, int],
    counts_by_column: dict[str, dict[str, int]],
) -> list[CoverageRow]:
    rows: list[CoverageRow] = []
    total_rows = int(totals.get("all", 0))
    seoul_rows = int(totals.get("seoul", 0))
    busan_rows = int(totals.get("busan", 0))

    for spec in specs:
        counts = counts_by_column.get(spec.column, {})
        non_null_rows = int(counts.get("all", 0))
        seoul_non_null_rows = int(counts.get("seoul", 0))
        busan_non_null_rows = int(counts.get("busan", 0))
        coverage_pct = _percentage(non_null_rows, total_rows)
        rows.append(
            CoverageRow(
                category=spec.category,
                column=spec.column,
                label=spec.label,
                total_rows=total_rows,
                non_null_rows=non_null_rows,
                missing_rows=max(total_rows - non_null_rows, 0),
                coverage_pct=coverage_pct,
                seoul_rows=seoul_rows,
                seoul_non_null_rows=seoul_non_null_rows,
                seoul_coverage_pct=_percentage(seoul_non_null_rows, seoul_rows),
                busan_rows=busan_rows,
                busan_non_null_rows=busan_non_null_rows,
                busan_coverage_pct=_percentage(busan_non_null_rows, busan_rows),
                status=_coverage_status(coverage_pct),
            )
        )
    return rows


def summarize_coverage_rows(rows: list[CoverageRow], *, total_rows: int) -> dict[str, int]:
    return {
        "total_rows": int(total_rows),
        "feature_count": len(rows),
        "ready_features": sum(1 for row in rows if row.status == "ready"),
        "partial_features": sum(1 for row in rows if row.status == "partial"),
        "missing_features": sum(1 for row in rows if row.status == "missing"),
    }


def write_feature_coverage_reports(
    rows: list[CoverageRow],
    summary: dict[str, int],
    output_dir: str | Path,
) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    csv_path = output_path / "feature_coverage.csv"
    markdown_path = output_path / "feature_coverage.md"

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(_row_to_dict(rows[0]).keys()) if rows else _csv_fieldnames())
        writer.writeheader()
        for row in rows:
            writer.writerow(_row_to_dict(row))

    markdown_path.write_text(_render_markdown(rows, summary), encoding="utf-8")
    return {
        "csv_output": str(csv_path),
        "markdown_output": str(markdown_path),
    }


def generate_feature_coverage_report(
    connection: Any,
    *,
    output_dir: str | Path = "artifacts/feature_coverage",
    specs: list[FeatureSpec] | None = None,
) -> dict[str, object]:
    selected_specs = specs or FEATURE_SPECS
    totals = _fetch_training_view_totals(connection)
    counts_by_column = _fetch_all_feature_non_null_counts(connection, [spec.column for spec in selected_specs])
    rows = build_coverage_rows(
        selected_specs,
        totals=totals,
        counts_by_column=counts_by_column,
    )
    summary = summarize_coverage_rows(rows, total_rows=totals["all"])
    outputs = write_feature_coverage_reports(rows, summary, output_dir)
    return {**summary, **outputs}


def _fetch_training_view_totals(connection: Any) -> dict[str, int]:
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT
              COUNT(*) AS all_rows,
              SUM(CASE WHEN city_code = 'seoul' THEN 1 ELSE 0 END) AS seoul_rows,
              SUM(CASE WHEN city_code = 'busan' THEN 1 ELSE 0 END) AS busan_rows
            FROM model_training_features
            """
        )
        row = cursor.fetchone() or {}
    finally:
        cursor.close()
    return {
        "all": _as_int(row.get("all_rows")),
        "seoul": _as_int(row.get("seoul_rows")),
        "busan": _as_int(row.get("busan_rows")),
    }


def _fetch_all_feature_non_null_counts(connection: Any, columns: list[str]) -> dict[str, dict[str, int]]:
    unsupported = [column for column in columns if column not in _FEATURE_COLUMNS]
    if unsupported:
        raise ValueError(f"unsupported feature coverage column: {unsupported[0]}")
    select_parts: list[str] = []
    for column in columns:
        select_parts.extend(
            [
                f"COUNT({column}) AS {column}__all",
                f"SUM(CASE WHEN city_code = 'seoul' AND {column} IS NOT NULL THEN 1 ELSE 0 END) AS {column}__seoul",
                f"SUM(CASE WHEN city_code = 'busan' AND {column} IS NOT NULL THEN 1 ELSE 0 END) AS {column}__busan",
            ]
        )

    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(f"SELECT {', '.join(select_parts)} FROM model_training_features")
        row = cursor.fetchone() or {}
    finally:
        cursor.close()

    return {
        column: {
            "all": _as_int(row.get(f"{column}__all")),
            "seoul": _as_int(row.get(f"{column}__seoul")),
            "busan": _as_int(row.get(f"{column}__busan")),
        }
        for column in columns
    }


def _render_markdown(rows: list[CoverageRow], summary: dict[str, int]) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# Feature Coverage Report",
        "",
        f"- 생성 시각: {generated_at}",
        f"- 총 거래 행 수: {summary['total_rows']}",
        f"- 대상 특성 수: {summary['feature_count']}",
        f"- ready: {summary['ready_features']}",
        f"- partial: {summary['partial_features']}",
        f"- missing: {summary['missing_features']}",
        "",
        "## Missing Features",
        "",
    ]
    missing_rows = [row for row in rows if row.status == "missing"]
    if missing_rows:
        for row in missing_rows:
            lines.append(f"- {row.category} / {row.column} ({row.label})")
    else:
        lines.append("- 없음")

    lines.extend(
        [
            "",
            "## Feature Detail",
            "",
            "| category | column | label | coverage_pct | non_null_rows | missing_rows | seoul_coverage_pct | busan_coverage_pct | status |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in rows:
        lines.append(
            "| "
            f"{row.category} | {row.column} | {row.label} | {row.coverage_pct:.2f} | "
            f"{row.non_null_rows} | {row.missing_rows} | {row.seoul_coverage_pct:.2f} | "
            f"{row.busan_coverage_pct:.2f} | {row.status} |"
        )
    lines.append("")
    return "\n".join(lines)


def _row_to_dict(row: CoverageRow) -> dict[str, object]:
    return {
        "category": row.category,
        "column": row.column,
        "label": row.label,
        "total_rows": row.total_rows,
        "non_null_rows": row.non_null_rows,
        "missing_rows": row.missing_rows,
        "coverage_pct": f"{row.coverage_pct:.2f}",
        "seoul_rows": row.seoul_rows,
        "seoul_non_null_rows": row.seoul_non_null_rows,
        "seoul_coverage_pct": f"{row.seoul_coverage_pct:.2f}",
        "busan_rows": row.busan_rows,
        "busan_non_null_rows": row.busan_non_null_rows,
        "busan_coverage_pct": f"{row.busan_coverage_pct:.2f}",
        "status": row.status,
    }


def _csv_fieldnames() -> list[str]:
    return [
        "category",
        "column",
        "label",
        "total_rows",
        "non_null_rows",
        "missing_rows",
        "coverage_pct",
        "seoul_rows",
        "seoul_non_null_rows",
        "seoul_coverage_pct",
        "busan_rows",
        "busan_non_null_rows",
        "busan_coverage_pct",
        "status",
    ]


def _percentage(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100, 2)


def _coverage_status(coverage_pct: float) -> str:
    if coverage_pct >= 95:
        return "ready"
    if coverage_pct > 0:
        return "partial"
    return "missing"


def _as_int(value: object) -> int:
    if value is None:
        return 0
    return int(value)
