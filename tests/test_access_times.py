import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from hedonic_house_price.access_times import (
    AccessTimeMetrics,
    import_average_access_time_snapshots,
    read_access_time_metrics_xlsx,
)


HEADER = [
    "Year",
    "HDCD",
    "Region",
    "HDCD_Lev",
    "Faci_CD",
    "Time_Zone",
    "Mode",
    "HDCD_SD_NM",
    "HDCD_SGG_NM",
    "HDCD_EMD_NM",
    "Region_NM",
    "Faci_CA",
    "Faci_NM",
    "Time_Zone_NM",
    "Mode_NM",
    "평균접근시간(분)",
]


class AccessTimeTests(unittest.TestCase):
    def test_read_access_time_metrics_xlsx_pivots_requested_facilities_and_ignores_subway(self):
        rows = _access_time_rows(
            city="서울특별시",
            district="종로구",
            dong="사직동",
            level="4",
            hdcd="11010530",
            values={
                ("버스터미널", "승용차"): 12.1,
                ("공항", "승용차"): 42.2,
                ("철도역", "승용차"): 15.3,
                ("종합병원", "승용차"): 5.4,
                ("버스터미널", "대중교통/도보"): 21.5,
                ("공항", "대중교통/도보"): 61.6,
                ("철도역", "대중교통/도보"): 18.7,
                ("종합병원", "대중교통/도보"): 14.8,
            },
        )
        rows.append(_row("2023", "11010530", "4", "99", "0_AllDay", "1_PC", "서울특별시", "종로구", "사직동", "기타", "지하철역", "승용차", 3.3))
        rows.append(_row("2023", "11010530", "4", "31", "1_T0709", "1_PC", "서울특별시", "종로구", "사직동", "교통시설", "철도역", "승용차", 99.9))

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "access_times.xlsx"
            _write_minimal_access_time_xlsx(path, rows)
            result = read_access_time_metrics_xlsx(path)

        key = ("seoul", "종로구", "사직동")
        self.assertIn(key, result.by_dong)
        self.assertEqual(
            result.by_dong[key],
            AccessTimeMetrics(
                car_intercity_bus_terminal_minutes=12.1,
                car_airport_minutes=42.2,
                car_rail_station_minutes=15.3,
                car_general_hospital_minutes=5.4,
                transit_intercity_bus_terminal_minutes=21.5,
                transit_airport_minutes=61.6,
                transit_rail_station_minutes=18.7,
                transit_general_hospital_minutes=14.8,
            ),
        )
        self.assertEqual(result.source_rows, 8)

    def test_import_average_access_time_snapshots_uses_dong_match_then_district_fallback(self):
        dong_metrics = AccessTimeMetrics(1, 2, 3, 4, 5, 6, 7, 8)
        district_metrics = AccessTimeMetrics(11, 12, 13, 14, 15, 16, 17, 18)
        connection = FakeConnection(
            [
                {
                    "complex_id": 10,
                    "city_code": "seoul",
                    "district_name": "강남구",
                    "legal_dongs": "역삼동\n삼성동",
                    "deal_months": "202505\n202506",
                },
                {
                    "complex_id": 20,
                    "city_code": "busan",
                    "district_name": "해운대구",
                    "legal_dongs": "우동",
                    "deal_months": "202505",
                },
            ]
        )

        result = import_average_access_time_snapshots(
            connection,
            by_dong={("seoul", "강남구", "역삼동"): dong_metrics},
            by_district={("busan", "해운대구"): district_metrics},
        )

        self.assertEqual(result["candidate_complexes"], 2)
        self.assertEqual(result["complex_dong_matches"], 1)
        self.assertEqual(result["complex_district_fallback_matches"], 1)
        self.assertEqual(result["snapshot_rows"], 3)
        self.assertEqual(connection.commits, 1)
        first_params = connection.cursor_obj.insert_params[0]
        self.assertEqual(first_params[:3], (10, "202505", "transport_access"))
        self.assertEqual(first_params[3:], dong_metrics.as_db_tuple())
        third_params = connection.cursor_obj.insert_params[2]
        self.assertEqual(third_params[:3], (20, "202505", "transport_access"))
        self.assertEqual(third_params[3:], district_metrics.as_db_tuple())


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.statements = []
        self.params = []
        self.insert_params = []
        self.rowcount = 1

    def execute(self, statement, params=None):
        self.statements.append(statement)
        self.params.append(params)
        if statement.strip().startswith("INSERT INTO transport_access_snapshots"):
            self.insert_params.append(params)

    def fetchall(self):
        return self.rows

    def close(self):
        self.statements.append("CLOSE")


class FakeConnection:
    def __init__(self, rows):
        self.cursor_obj = FakeCursor(rows)
        self.commits = 0
        self.rollbacks = 0

    def cursor(self, **kwargs):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _access_time_rows(*, city, district, dong, level, hdcd, values):
    rows = []
    for (facility, mode), value in values.items():
        rows.append(
            _row(
                "2023",
                hdcd,
                level,
                "31",
                "0_AllDay",
                "1_PC" if mode == "승용차" else "2_PT",
                city,
                district,
                dong,
                "교통시설" if facility != "종합병원" else "의료시설",
                facility,
                mode,
                value,
            )
        )
    return rows


def _row(year, hdcd, level, facility_code, time_zone, mode_code, city, district, dong, facility_category, facility_name, mode_name, value):
    return [
        year,
        hdcd,
        "-",
        level,
        facility_code,
        time_zone,
        mode_code,
        city,
        district,
        dong,
        "동부",
        facility_category,
        facility_name,
        "일평균(06-20시)",
        mode_name,
        value,
    ]


def _write_minimal_access_time_xlsx(path: Path, rows: list[list[object]]) -> None:
    sheet_rows = [[None] * len(HEADER) for _ in range(4)] + [HEADER] + rows
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", _content_types_xml())
        archive.writestr("_rels/.rels", _root_rels_xml())
        archive.writestr("xl/workbook.xml", _workbook_xml())
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml())
        archive.writestr("xl/worksheets/sheet1.xml", _worksheet_xml(sheet_rows))


def _worksheet_xml(rows: list[list[object]]) -> str:
    row_xml = []
    for row_idx, row in enumerate(rows, start=1):
        cells = []
        for col_idx, value in enumerate(row, start=1):
            if value is None:
                continue
            ref = f"{_column_name(col_idx)}{row_idx}"
            if isinstance(value, (int, float)):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>')
        row_xml.append(f'<row r="{row_idx}">{"".join(cells)}</row>')
    return '<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + "".join(row_xml) + "</sheetData></worksheet>"


def _column_name(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _content_types_xml() -> str:
    return '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>'


def _root_rels_xml() -> str:
    return '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'


def _workbook_xml() -> str:
    return '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="평균접근시간" sheetId="1" r:id="rId1"/></sheets></workbook>'


def _workbook_rels_xml() -> str:
    return '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'


if __name__ == "__main__":
    unittest.main()
