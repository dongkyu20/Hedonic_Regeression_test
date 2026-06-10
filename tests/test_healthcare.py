import csv
import tempfile
import unittest
from pathlib import Path

from hedonic_house_price.healthcare import (
    HealthcareFacility,
    import_healthcare_distance_snapshots,
    nearest_healthcare_metrics,
    read_healthcare_facilities_csvs,
)


class HealthcareDistanceTests(unittest.TestCase):
    def test_read_healthcare_facilities_csvs_filters_open_rows_and_converts_coordinates(self):
        with tempfile.NamedTemporaryFile("w", encoding="cp949", newline="", delete=False) as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "관리번호",
                    "사업장명",
                    "영업상태명",
                    "상세영업상태명",
                    "도로명주소",
                    "좌표정보(X)",
                    "좌표정보(Y)",
                    "지번주소",
                ]
            )
            writer.writerow(
                [
                    "H1",
                    "열린병원",
                    "영업/정상",
                    "영업중",
                    "서울특별시 종로구 율곡로 1",
                    "200000",
                    "450000",
                    "",
                ]
            )
            writer.writerow(
                [
                    "H2",
                    "닫힌병원",
                    "폐업",
                    "폐업",
                    "서울특별시 종로구 율곡로 2",
                    "200100",
                    "450100",
                    "",
                ]
            )
            path = handle.name

        try:
            facilities = read_healthcare_facilities_csvs(
                [path],
                city_code="seoul",
                facility_kind="hospital",
                coordinate_converter=lambda x, y: (37.5, 127.0),
            )
        finally:
            Path(path).unlink()

        self.assertEqual(len(facilities), 1)
        self.assertEqual(facilities[0].facility_id, "H1")
        self.assertEqual(facilities[0].facility_kind, "hospital")
        self.assertEqual(facilities[0].latitude, 37.5)
        self.assertEqual(facilities[0].longitude, 127.0)

    def test_nearest_healthcare_metrics_returns_hospital_and_pharmacy_distances(self):
        facilities = [
            HealthcareFacility("H1", "hospital", "병원", "seoul", 37.5005, 127.0000),
            HealthcareFacility("P1", "pharmacy", "약국", "seoul", 37.5010, 127.0000),
            HealthcareFacility("B1", "hospital", "부산병원", "busan", 35.1, 129.0),
        ]

        metrics = nearest_healthcare_metrics(37.5, 127.0, facilities)

        self.assertIsNotNone(metrics.nearest_hospital_distance_m)
        self.assertIsNotNone(metrics.nearest_pharmacy_distance_m)
        self.assertLess(metrics.nearest_hospital_distance_m, metrics.nearest_pharmacy_distance_m)

    def test_import_healthcare_distance_snapshots_inserts_monthly_snapshots(self):
        facilities = [
            HealthcareFacility("H1", "hospital", "병원", "seoul", 37.5005, 127.0000),
            HealthcareFacility("P1", "pharmacy", "약국", "seoul", 37.5010, 127.0000),
        ]
        connection = FakeConnection(
            [
                {
                    "complex_id": 10,
                    "city_code": "seoul",
                    "latitude": 37.5,
                    "longitude": 127.0,
                    "deal_months": "202501\n202502",
                }
            ]
        )

        result = import_healthcare_distance_snapshots(
            connection,
            facilities,
            source_name="healthcare_facility",
        )

        self.assertEqual(result["candidate_complexes"], 1)
        self.assertEqual(result["complexes_with_metrics"], 1)
        self.assertEqual(result["snapshot_rows"], 2)
        self.assertEqual(connection.cursor_obj.upsert_params[0][0], 10)
        self.assertEqual(connection.cursor_obj.upsert_params[0][2], "healthcare_facility")
        self.assertIsNotNone(connection.cursor_obj.upsert_params[0][4])
        self.assertIsNotNone(connection.cursor_obj.upsert_params[0][5])


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.statements = []
        self.upsert_params = []
        self.rowcount = 1

    def execute(self, statement, params=None):
        self.statements.append(statement)
        if statement.strip().startswith("INSERT INTO living_environment_snapshots"):
            self.upsert_params.append(params)

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


if __name__ == "__main__":
    unittest.main()
