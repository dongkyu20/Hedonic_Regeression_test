import csv
import tempfile
import unittest
from pathlib import Path

from hedonic_house_price.subway_distances import (
    LocatedSubwayStation,
    SubwayStation,
    import_subway_distance_snapshots,
    nearest_subway_metrics,
    read_subway_station_csvs,
)


class SubwayDistanceTests(unittest.TestCase):
    def test_read_subway_station_csvs_merges_duplicate_seoul_station_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            national_path = Path(tmpdir) / "국가철도공단_서울경기도_지하철_주소데이터.csv"
            with national_path.open("w", encoding="cp949", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["철도운영기관명", "선명", "역명", "지번주소", "도로명주소"])
                writer.writerow(["서울교통공사", "2호선", "강남", "서울특별시 강남구 역삼동 858", "서울특별시 강남구 강남대로 지하396"])
                writer.writerow(["한국철도공사", "수인분당선", "수서", "서울특별시 강남구 수서동 214-1", "서울특별시 강남구 광평로 지하270"])

            seoul_metro_path = Path(tmpdir) / "서울교통공사_역주소.csv"
            with seoul_metro_path.open("w", encoding="cp949", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["연번", "역번호", "호선", "역명", "전화번호", "도로명주소", "지번주소"])
                writer.writerow(["1", "222", "2", "강남", "02-6110-2221", "서울특별시 강남구 강남대로 지하396", "서울특별시 강남구 역삼동 858"])
                writer.writerow(["2", "221", "2", "역삼", "02-6110-2211", "서울특별시 강남구 테헤란로 지하156", "서울특별시 강남구 역삼동 804"])

            stations = read_subway_station_csvs([national_path, seoul_metro_path])

        self.assertEqual(len(stations), 3)
        self.assertEqual(
            [(station.service_area, station.line_name, station.station_name) for station in stations],
            [
                ("seoul", "2호선", "강남"),
                ("seoul", "수인분당선", "수서"),
                ("seoul", "2호선", "역삼"),
            ],
        )

    def test_nearest_subway_metrics_returns_nearest_distance_and_radius_count(self):
        stations = [
            LocatedSubwayStation("가까운역", "2호선", "seoul", 37.5005, 127.0),
            LocatedSubwayStation("가까운역", "신분당선", "seoul", 37.5005, 127.0),
            LocatedSubwayStation("먼역", "2호선", "seoul", 37.52, 127.0),
        ]

        metrics = nearest_subway_metrics(37.5, 127.0, stations, radius_m=100)

        self.assertLess(metrics.nearest_distance_m, 60)
        self.assertEqual(metrics.count_radius, 1)

    def test_import_subway_distance_snapshots_inserts_monthly_snapshots(self):
        stations = [
            LocatedSubwayStation("가까운역", "2호선", "seoul", 37.5005, 127.0),
            LocatedSubwayStation("부산역", "1호선", "busan", 35.115, 129.041),
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

        result = import_subway_distance_snapshots(connection, stations, radius_m=100)

        self.assertEqual(result["candidate_complexes"], 1)
        self.assertEqual(result["complexes_with_metrics"], 1)
        self.assertEqual(result["snapshot_rows"], 2)
        self.assertEqual(connection.commits, 1)
        first_params = connection.cursor_obj.insert_params[0]
        self.assertEqual(first_params[:4], (10, "202505", "transport_access", 100))
        self.assertLess(first_params[4], 60)
        self.assertEqual(first_params[5], 1)

    def test_subway_station_address_candidates_prefers_road_then_jibun(self):
        station = SubwayStation(
            station_name="강남",
            line_name="2호선",
            service_area="seoul",
            road_address="서울특별시 강남구 강남대로 지하396",
            jibun_address="서울특별시 강남구 역삼동 858",
        )

        self.assertEqual(
            station.address_candidates(),
            ["서울특별시 강남구 강남대로 지하396", "서울특별시 강남구 역삼동 858"],
        )


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
