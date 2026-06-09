import csv
import tempfile
import unittest
from pathlib import Path

from hedonic_house_price.school_distances import (
    SchoolLocation,
    haversine_distance_m,
    import_school_distance_snapshots_csv,
    nearest_school_distances,
    read_school_locations_csv,
)


class SchoolDistanceTests(unittest.TestCase):
    def test_read_school_locations_csv_filters_supported_active_elementary_middle_and_high_schools(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "schools.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    [
                        "학교ID",
                        "학교명",
                        "학교급구분",
                        "운영상태",
                        "시도교육청명",
                        "위도",
                        "경도",
                    ]
                )
                writer.writerow(["S1", "서울초", "초등학교", "운영", "서울특별시교육청", "37.5", "127.0"])
                writer.writerow(["S2", "부산중", "중학교", "운영", "부산광역시교육청", "35.1", "129.0"])
                writer.writerow(["S3", "서울고", "고등학교", "운영", "서울특별시교육청", "37.6", "127.1"])
                writer.writerow(["S4", "폐교중", "중학교", "폐교", "서울특별시교육청", "37.7", "127.2"])
                writer.writerow(["S5", "대구초", "초등학교", "운영", "대구광역시교육청", "35.8", "128.5"])

            rows = read_school_locations_csv(path)

        self.assertEqual(
            rows,
            [
                SchoolLocation("S1", "서울초", "초등학교", "seoul", 37.5, 127.0),
                SchoolLocation("S2", "부산중", "중학교", "busan", 35.1, 129.0),
                SchoolLocation("S3", "서울고", "고등학교", "seoul", 37.6, 127.1),
            ],
        )

    def test_nearest_school_distances_returns_elementary_middle_distances_and_school_count(self):
        schools = [
            SchoolLocation("E1", "먼초", "초등학교", "seoul", 37.52, 127.0),
            SchoolLocation("E2", "가까운초", "초등학교", "seoul", 37.5005, 127.0),
            SchoolLocation("M1", "가까운중", "중학교", "seoul", 37.501, 127.0),
            SchoolLocation("H1", "가까운고", "고등학교", "seoul", 37.5015, 127.0),
        ]

        distances = nearest_school_distances(37.5, 127.0, schools, radius_m=200)

        self.assertLess(distances.elementary_distance_m, 60)
        self.assertLess(distances.middle_distance_m, 120)
        self.assertEqual(distances.school_count_radius, 3)

    def test_haversine_distance_m_is_zero_for_same_coordinate(self):
        self.assertEqual(haversine_distance_m(37.5, 127.0, 37.5, 127.0), 0.0)

    def test_import_school_distance_snapshots_csv_inserts_monthly_snapshots(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "schools.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    [
                        "학교ID",
                        "학교명",
                        "학교급구분",
                        "운영상태",
                        "시도교육청명",
                        "위도",
                        "경도",
                    ]
                )
                writer.writerow(["S1", "가까운초", "초등학교", "운영", "서울특별시교육청", "37.5005", "127.0"])
                writer.writerow(["S2", "가까운중", "중학교", "운영", "서울특별시교육청", "37.501", "127.0"])
                writer.writerow(["S3", "가까운고", "고등학교", "운영", "서울특별시교육청", "37.5015", "127.0"])

            connection = FakeConnection(
                [
                    {
                        "complex_id": 10,
                        "city_code": "seoul",
                        "latitude": 37.5,
                        "longitude": 127.0,
                        "deal_months": "202505\n202506",
                    }
                ]
            )

            result = import_school_distance_snapshots_csv(connection, path)

        self.assertEqual(result["candidate_complexes"], 1)
        self.assertEqual(result["complexes_with_distances"], 1)
        self.assertEqual(result["snapshot_rows"], 2)
        self.assertEqual(connection.commits, 1)
        first_params = connection.cursor_obj.insert_params[0]
        self.assertEqual(first_params[:4], (10, "202505", "school_location", 1000))
        self.assertLess(first_params[4], 60)
        self.assertLess(first_params[5], 120)
        self.assertEqual(first_params[6], 3)


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
        if statement.strip().startswith("INSERT INTO living_environment_snapshots"):
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


if __name__ == "__main__":
    unittest.main()
