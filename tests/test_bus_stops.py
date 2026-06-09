import csv
import tempfile
import unittest
from pathlib import Path

from hedonic_house_price.bus_stops import (
    BusStopLocation,
    import_bus_stop_distance_snapshots,
    nearest_bus_stop_metrics,
    read_bus_stop_locations_csv,
)


class BusStopDistanceTests(unittest.TestCase):
    def test_read_bus_stop_locations_csv_filters_seoul_and_busan_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bus_stops.csv"
            with path.open("w", encoding="cp949", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["정류장번호", "정류장명", "위도", "경도", "정보수집일", "모바일단축번호", "도시코드", "도시명", "관리도시명"])
                writer.writerow(["S1", "서울정류장", "37.5005", "127.0", "2025-10-31", "1", "11000", "서울특별시", "서울"])
                writer.writerow(["B1", "부산정류장", "35.1005", "129.0", "2025-10-31", "2", "21000", "부산광역시", "부산"])
                writer.writerow(["D1", "대구정류장", "35.8", "128.5", "2025-10-31", "3", "22000", "대구광역시", "대구"])
                writer.writerow(["S1", "서울정류장중복", "37.5005", "127.0", "2025-10-31", "1", "11000", "서울특별시", "서울"])

            rows = read_bus_stop_locations_csv(path)

        self.assertEqual(
            rows,
            [
                BusStopLocation("S1", "서울정류장", "seoul", 37.5005, 127.0),
                BusStopLocation("B1", "부산정류장", "busan", 35.1005, 129.0),
            ],
        )

    def test_nearest_bus_stop_metrics_returns_nearest_distance_and_radius_count(self):
        stops = [
            BusStopLocation("S1", "가까운정류장", "seoul", 37.5005, 127.0),
            BusStopLocation("S2", "반경밖정류장", "seoul", 37.52, 127.0),
        ]

        metrics = nearest_bus_stop_metrics(37.5, 127.0, stops, radius_m=100)

        self.assertLess(metrics.nearest_distance_m, 60)
        self.assertEqual(metrics.count_radius, 1)

    def test_import_bus_stop_distance_snapshots_inserts_monthly_snapshots(self):
        stops = [
            BusStopLocation("S1", "가까운정류장", "seoul", 37.5005, 127.0),
            BusStopLocation("B1", "부산정류장", "busan", 35.115, 129.041),
        ]
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

        result = import_bus_stop_distance_snapshots(connection, stops, radius_m=100)

        self.assertEqual(result["candidate_complexes"], 1)
        self.assertEqual(result["complexes_with_metrics"], 1)
        self.assertEqual(result["snapshot_rows"], 2)
        self.assertEqual(connection.commits, 1)
        first_params = connection.cursor_obj.insert_params[0]
        self.assertEqual(first_params[:4], (10, "202505", "transport_access", 100))
        self.assertLess(first_params[4], 60)
        self.assertEqual(first_params[5], 1)


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


if __name__ == "__main__":
    unittest.main()
