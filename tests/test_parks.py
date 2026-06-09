import unittest

from hedonic_house_price.parks import (
    ParkLocation,
    import_park_environment_snapshots,
    nearest_park_metrics,
    park_locations_from_rows,
)


class ParkEnvironmentTests(unittest.TestCase):
    def test_park_locations_from_rows_filters_seoul_and_busan_parks(self):
        rows = [
            {
                "관리번호": "S1",
                "공원명": "서울공원",
                "소재지도로명주소": "서울특별시 강남구 테헤란로 1",
                "소재지지번주소": "",
                "위도": "37.5005",
                "경도": "127.0",
                "공원면적": "1000.5",
                "관리기관명": "서울특별시 강남구",
                "제공기관명": "서울특별시 강남구",
            },
            {
                "관리번호": "B1",
                "공원명": "부산공원",
                "소재지도로명주소": "",
                "소재지지번주소": "부산광역시 해운대구 우동 1",
                "위도": "35.1005",
                "경도": "129.0",
                "공원면적": "2000",
                "관리기관명": "부산광역시 해운대구",
                "제공기관명": "부산광역시 해운대구",
            },
            {
                "관리번호": "D1",
                "공원명": "대구공원",
                "소재지도로명주소": "대구광역시 중구",
                "소재지지번주소": "",
                "위도": "35.8",
                "경도": "128.5",
                "공원면적": "3000",
                "관리기관명": "대구광역시 중구",
                "제공기관명": "대구광역시 중구",
            },
            {
                "관리번호": "S1",
                "공원명": "서울공원중복",
                "소재지도로명주소": "서울특별시 강남구 테헤란로 1",
                "소재지지번주소": "",
                "위도": "37.5005",
                "경도": "127.0",
                "공원면적": "1000.5",
                "관리기관명": "서울특별시 강남구",
                "제공기관명": "서울특별시 강남구",
            },
        ]

        parks = park_locations_from_rows(rows)

        self.assertEqual(
            parks,
            [
                ParkLocation("S1", "서울공원", "seoul", 37.5005, 127.0, 1000.5),
                ParkLocation("B1", "부산공원", "busan", 35.1005, 129.0, 2000.0),
            ],
        )

    def test_nearest_park_metrics_returns_distance_and_area_sum(self):
        parks = [
            ParkLocation("P1", "가까운공원", "seoul", 37.5005, 127.0, 1000.0),
            ParkLocation("P2", "반경내공원", "seoul", 37.501, 127.0, 2500.0),
            ParkLocation("P3", "반경밖공원", "seoul", 37.52, 127.0, 10000.0),
        ]

        metrics = nearest_park_metrics(37.5, 127.0, parks, radius_m=150)

        self.assertLess(metrics.nearest_distance_m, 60)
        self.assertEqual(metrics.park_area_total_m2_radius, 3500.0)

    def test_import_park_environment_snapshots_inserts_monthly_snapshots(self):
        parks = [
            ParkLocation("P1", "가까운공원", "seoul", 37.5005, 127.0, 1000.0),
            ParkLocation("P2", "부산공원", "busan", 35.115, 129.041, 2000.0),
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

        result = import_park_environment_snapshots(connection, parks, radius_m=100)

        self.assertEqual(result["candidate_complexes"], 1)
        self.assertEqual(result["complexes_with_metrics"], 1)
        self.assertEqual(result["snapshot_rows"], 2)
        self.assertEqual(connection.commits, 1)
        first_params = connection.cursor_obj.insert_params[0]
        self.assertEqual(first_params[:4], (10, "202505", "park_standard_data", 100))
        self.assertLess(first_params[4], 60)
        self.assertEqual(first_params[5], 1000.0)


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
