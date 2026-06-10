from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


SHEET_NAME = "평균접근시간"
HEADER_MARKERS = {"Year", "HDCD", "HDCD_Lev", "Faci_NM", "Time_Zone", "Mode_NM", "평균접근시간(분)"}
SUPPORTED_CITY_NAMES = {
    "서울특별시": "seoul",
    "부산광역시": "busan",
}
TARGET_TIME_ZONE = "0_AllDay"
TARGET_LEVELS = {"2", "4"}
ACCESS_TIME_FIELD_BY_FACILITY_MODE = {
    ("버스터미널", "승용차"): "car_intercity_bus_terminal_minutes",
    ("공항", "승용차"): "car_airport_minutes",
    ("철도역", "승용차"): "car_rail_station_minutes",
    ("종합병원", "승용차"): "car_general_hospital_minutes",
    ("버스터미널", "대중교통/도보"): "transit_intercity_bus_terminal_minutes",
    ("공항", "대중교통/도보"): "transit_airport_minutes",
    ("철도역", "대중교통/도보"): "transit_rail_station_minutes",
    ("종합병원", "대중교통/도보"): "transit_general_hospital_minutes",
}
METRIC_FIELD_NAMES = (
    "car_intercity_bus_terminal_minutes",
    "car_airport_minutes",
    "car_rail_station_minutes",
    "car_general_hospital_minutes",
    "transit_intercity_bus_terminal_minutes",
    "transit_airport_minutes",
    "transit_rail_station_minutes",
    "transit_general_hospital_minutes",
)

SELECT_COMPLEXES_FOR_ACCESS_TIME_SQL = """
SELECT
  c.complex_id,
  r.city_code,
  r.district_name,
  GROUP_CONCAT(DISTINCT t.legal_dong_name ORDER BY t.legal_dong_name SEPARATOR '\n') AS legal_dongs,
  GROUP_CONCAT(DISTINCT t.deal_yyyymm ORDER BY t.deal_yyyymm SEPARATOR '\n') AS deal_months
FROM housing_complexes c
JOIN administrative_regions r ON r.region_id = c.region_id
LEFT JOIN housing_transactions t ON t.complex_id = c.complex_id
WHERE c.property_type = 'apartment'
  AND r.city_code IN ('seoul', 'busan')
GROUP BY c.complex_id, r.city_code, r.district_name
"""

UPSERT_ACCESS_TIME_SQL = """
INSERT INTO transport_access_snapshots (
  complex_id,
  snapshot_yyyymm,
  source_name,
  car_intercity_bus_terminal_minutes,
  car_airport_minutes,
  car_rail_station_minutes,
  car_general_hospital_minutes,
  transit_intercity_bus_terminal_minutes,
  transit_airport_minutes,
  transit_rail_station_minutes,
  transit_general_hospital_minutes
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
  car_intercity_bus_terminal_minutes = VALUES(car_intercity_bus_terminal_minutes),
  car_airport_minutes = VALUES(car_airport_minutes),
  car_rail_station_minutes = VALUES(car_rail_station_minutes),
  car_general_hospital_minutes = VALUES(car_general_hospital_minutes),
  transit_intercity_bus_terminal_minutes = VALUES(transit_intercity_bus_terminal_minutes),
  transit_airport_minutes = VALUES(transit_airport_minutes),
  transit_rail_station_minutes = VALUES(transit_rail_station_minutes),
  transit_general_hospital_minutes = VALUES(transit_general_hospital_minutes),
  updated_at = CURRENT_TIMESTAMP
"""

MAIN_NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
RELS_NS = {"rel": "http://schemas.openxmlformats.org/package/2006/relationships"}
OFFICE_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


@dataclass(frozen=True)
class AccessTimeMetrics:
    car_intercity_bus_terminal_minutes: float | None = None
    car_airport_minutes: float | None = None
    car_rail_station_minutes: float | None = None
    car_general_hospital_minutes: float | None = None
    transit_intercity_bus_terminal_minutes: float | None = None
    transit_airport_minutes: float | None = None
    transit_rail_station_minutes: float | None = None
    transit_general_hospital_minutes: float | None = None

    @classmethod
    def from_fields(cls, fields: dict[str, float]) -> "AccessTimeMetrics":
        return cls(**{name: fields.get(name) for name in METRIC_FIELD_NAMES})

    def as_db_tuple(self) -> tuple[float | None, ...]:
        return tuple(getattr(self, name) for name in METRIC_FIELD_NAMES)

    def has_any_value(self) -> bool:
        return any(value is not None for value in self.as_db_tuple())


@dataclass(frozen=True)
class AccessTimeMetricSet:
    by_dong: dict[tuple[str, str, str], AccessTimeMetrics]
    by_district: dict[tuple[str, str], AccessTimeMetrics]
    source_rows: int


def read_access_time_metrics_xlsx(path: str | Path) -> AccessTimeMetricSet:
    rows = _read_named_sheet_rows(Path(path), SHEET_NAME)
    if not rows:
        raise ValueError("average access time worksheet has no rows")

    header_index = _find_header_index(rows)
    if header_index is None:
        raise ValueError("average access time worksheet header row was not found")

    header = [str(value or "").strip() for value in rows[header_index]]
    missing = [name for name in HEADER_MARKERS if name not in header]
    if missing:
        raise ValueError(f"average access time worksheet is missing required column: {missing[0]}")

    by_dong_fields: dict[tuple[str, str, str], dict[str, float]] = {}
    by_district_fields: dict[tuple[str, str], dict[str, float]] = {}
    source_rows = 0
    for row in rows[header_index + 1 :]:
        record = _row_dict(header, row)
        field_name = ACCESS_TIME_FIELD_BY_FACILITY_MODE.get(
            (_cell(record, "Faci_NM"), _cell(record, "Mode_NM"))
        )
        if field_name is None:
            continue
        if _cell(record, "Time_Zone") != TARGET_TIME_ZONE:
            continue
        level = _cell(record, "HDCD_Lev")
        if level not in TARGET_LEVELS:
            continue
        city_code = SUPPORTED_CITY_NAMES.get(_cell(record, "HDCD_SD_NM"))
        if city_code is None:
            continue
        value = _optional_float(record.get("평균접근시간(분)"))
        if value is None:
            continue

        district_name = _cell(record, "HDCD_SGG_NM")
        dong_name = _cell(record, "HDCD_EMD_NM")
        source_rows += 1
        if level == "4" and district_name and dong_name and dong_name != "-":
            key = (city_code, _normalize_name(district_name), _normalize_name(dong_name))
            by_dong_fields.setdefault(key, {})[field_name] = value
        elif level == "2" and district_name and district_name != "-":
            key = (city_code, _normalize_name(district_name))
            by_district_fields.setdefault(key, {})[field_name] = value

    return AccessTimeMetricSet(
        by_dong={key: AccessTimeMetrics.from_fields(fields) for key, fields in by_dong_fields.items()},
        by_district={key: AccessTimeMetrics.from_fields(fields) for key, fields in by_district_fields.items()},
        source_rows=source_rows,
    )


def import_average_access_time_snapshots_xlsx(
    connection: Any,
    xlsx_path: str | Path,
    *,
    source_name: str = "transport_access",
) -> dict[str, int]:
    metric_set = read_access_time_metrics_xlsx(xlsx_path)
    stats = import_average_access_time_snapshots(
        connection,
        by_dong=metric_set.by_dong,
        by_district=metric_set.by_district,
        source_name=source_name,
    )
    return {
        "source_rows": metric_set.source_rows,
        "dong_metric_rows": len(metric_set.by_dong),
        "district_metric_rows": len(metric_set.by_district),
        **stats,
    }


def import_average_access_time_snapshots(
    connection: Any,
    *,
    by_dong: dict[tuple[str, str, str], AccessTimeMetrics],
    by_district: dict[tuple[str, str], AccessTimeMetrics],
    source_name: str = "transport_access",
) -> dict[str, int]:
    cursor = connection.cursor(dictionary=True)
    stats = {
        "candidate_complexes": 0,
        "complex_dong_matches": 0,
        "complex_district_fallback_matches": 0,
        "skipped_no_months": 0,
        "skipped_no_access_time": 0,
        "snapshot_rows": 0,
        "changed_snapshot_rows": 0,
    }
    try:
        cursor.execute(SELECT_COMPLEXES_FOR_ACCESS_TIME_SQL)
        for complex_row in cursor.fetchall():
            stats["candidate_complexes"] += 1
            deal_months = _split_multiline_values(complex_row.get("deal_months"))
            if not deal_months:
                stats["skipped_no_months"] += 1
                continue

            metrics, match_kind = _metrics_for_complex(complex_row, by_dong, by_district)
            if metrics is None or not metrics.has_any_value():
                stats["skipped_no_access_time"] += 1
                continue

            if match_kind == "dong":
                stats["complex_dong_matches"] += 1
            elif match_kind == "district":
                stats["complex_district_fallback_matches"] += 1

            for deal_month in deal_months:
                cursor.execute(
                    UPSERT_ACCESS_TIME_SQL,
                    (
                        complex_row["complex_id"],
                        deal_month,
                        source_name,
                        *metrics.as_db_tuple(),
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


def _metrics_for_complex(
    complex_row: dict[str, Any],
    by_dong: dict[tuple[str, str, str], AccessTimeMetrics],
    by_district: dict[tuple[str, str], AccessTimeMetrics],
) -> tuple[AccessTimeMetrics | None, str | None]:
    city_code = _normalize_name(complex_row.get("city_code"))
    district_name = _normalize_name(complex_row.get("district_name"))
    for dong_name in _split_multiline_values(complex_row.get("legal_dongs")):
        metrics = by_dong.get((city_code, district_name, _normalize_name(dong_name)))
        if metrics is not None:
            return metrics, "dong"
    metrics = by_district.get((city_code, district_name))
    if metrics is not None:
        return metrics, "district"
    return None, None


def _read_named_sheet_rows(path: Path, sheet_name: str) -> list[list[object | None]]:
    with zipfile.ZipFile(path) as archive:
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        workbook_rels = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_targets = {
            rel.attrib["Id"]: rel.attrib["Target"]
            for rel in workbook_rels.findall("rel:Relationship", RELS_NS)
        }
        worksheet_target = None
        for sheet in workbook.findall("main:sheets/main:sheet", MAIN_NS):
            if sheet.attrib.get("name") == sheet_name:
                worksheet_target = rel_targets[sheet.attrib[f"{OFFICE_REL_NS}id"]]
                break
        if worksheet_target is None:
            raise ValueError(f"worksheet not found: {sheet_name}")

        worksheet_path = _resolve_workbook_target(worksheet_target)
        shared_strings = _read_shared_strings(archive)
        worksheet = ElementTree.fromstring(archive.read(worksheet_path))
        return _worksheet_rows(worksheet, shared_strings)


def _resolve_workbook_target(target: str) -> str:
    normalized = target.lstrip("/")
    if normalized.startswith("xl/"):
        return normalized
    return f"xl/{normalized}"


def _read_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        payload = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ElementTree.fromstring(payload)
    strings: list[str] = []
    for item in root.findall("main:si", MAIN_NS):
        strings.append("".join(text.text or "" for text in item.findall(".//main:t", MAIN_NS)))
    return strings


def _worksheet_rows(root: ElementTree.Element, shared_strings: list[str]) -> list[list[object | None]]:
    rows: list[list[object | None]] = []
    for row in root.findall(".//main:sheetData/main:row", MAIN_NS):
        cells: dict[int, object | None] = {}
        for cell in row.findall("main:c", MAIN_NS):
            column_index = _column_index_from_reference(cell.attrib.get("r", ""))
            if column_index is None:
                continue
            cells[column_index] = _xlsx_cell_value(cell, shared_strings)
        if cells:
            max_column = max(cells)
            rows.append([cells.get(index) for index in range(1, max_column + 1)])
        else:
            rows.append([])
    return rows


def _xlsx_cell_value(cell: ElementTree.Element, shared_strings: list[str]) -> object | None:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        text = "".join(part.text or "" for part in cell.findall(".//main:t", MAIN_NS))
        return text

    value = cell.find("main:v", MAIN_NS)
    if value is None or value.text is None:
        return None

    raw = value.text
    if cell_type == "s":
        try:
            return shared_strings[int(raw)]
        except (IndexError, ValueError):
            return ""
    return _parse_number(raw)


def _parse_number(value: str) -> object:
    try:
        number = float(value)
    except ValueError:
        return value
    if number.is_integer():
        return int(number)
    return number


def _column_index_from_reference(reference: str) -> int | None:
    match = re.match(r"([A-Z]+)", reference)
    if match is None:
        return None
    index = 0
    for letter in match.group(1):
        index = index * 26 + (ord(letter) - 64)
    return index


def _find_header_index(rows: list[list[object | None]]) -> int | None:
    for index, row in enumerate(rows):
        values = {str(value or "").strip() for value in row}
        if HEADER_MARKERS.issubset(values):
            return index
    return None


def _row_dict(header: list[str], row: list[object | None]) -> dict[str, object | None]:
    return {name: row[index] if index < len(row) else None for index, name in enumerate(header)}


def _cell(row: dict[str, object | None], name: str) -> str:
    return str(row.get(name) or "").strip()


def _optional_float(value: object | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.upper() == "N/A":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _normalize_name(value: object | None) -> str:
    return re.sub(r"\s+", "", str(value or "").strip())


def _split_multiline_values(value: object | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in str(value).split("\n") if item.strip()]
