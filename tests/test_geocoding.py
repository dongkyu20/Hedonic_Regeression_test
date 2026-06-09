import unittest

from hedonic_house_price.geocoding import (
    GeocodeResult,
    geocode_missing_complex_coordinates,
    parse_kakao_address_response,
)


class GeocodingTests(unittest.TestCase):
    def test_parse_kakao_address_response_reads_first_document_coordinates(self):
        result = parse_kakao_address_response(
            {
                "documents": [
                    {
                        "address_name": "서울특별시 종로구 사직로8길 34",
                        "x": "126.9724500",
                        "y": "37.5730600",
                    }
                ]
            }
        )

        self.assertEqual(
            result,
            GeocodeResult(
                latitude=37.57306,
                longitude=126.97245,
                matched_address="서울특별시 종로구 사직로8길 34",
            ),
        )

    def test_parse_kakao_address_response_returns_none_for_empty_documents(self):
        self.assertIsNone(parse_kakao_address_response({"documents": []}))

    def test_geocode_missing_complex_coordinates_updates_road_address_matches(self):
        connection = FakeConnection(
            [
                {
                    "complex_id": 10,
                    "road_address": "서울특별시 종로구 사직로8길 34",
                    "jibun_address": "서울특별시 종로구 내수동 72",
                }
            ]
        )
        geocoder = FakeGeocoder(
            {
                "서울특별시 종로구 사직로8길 34": GeocodeResult(
                    latitude=37.57306,
                    longitude=126.97245,
                    matched_address="서울특별시 종로구 사직로8길 34",
                )
            }
        )

        result = geocode_missing_complex_coordinates(connection, geocoder, sleep_seconds=0)

        self.assertEqual(result["candidate_complexes"], 1)
        self.assertEqual(result["updated_complexes"], 1)
        self.assertEqual(result["not_found_complexes"], 0)
        self.assertEqual(connection.commits, 1)
        self.assertEqual(connection.cursor_obj.update_params[0], (37.57306, 126.97245, 10))

    def test_geocode_missing_complex_coordinates_falls_back_to_jibun_address(self):
        connection = FakeConnection(
            [
                {
                    "complex_id": 20,
                    "road_address": "미매칭 도로명",
                    "jibun_address": "부산광역시 해운대구 우동 1407",
                }
            ]
        )
        geocoder = FakeGeocoder(
            {
                "부산광역시 해운대구 우동 1407": GeocodeResult(
                    latitude=35.15821,
                    longitude=129.15984,
                    matched_address="부산광역시 해운대구 우동 1407",
                )
            }
        )

        result = geocode_missing_complex_coordinates(connection, geocoder, sleep_seconds=0)

        self.assertEqual(result["updated_complexes"], 1)
        self.assertEqual(result["address_attempts"], 2)
        self.assertEqual(connection.cursor_obj.update_params[0], (35.15821, 129.15984, 20))


class FakeGeocoder:
    def __init__(self, results):
        self.results = results
        self.queries = []

    def geocode(self, address):
        self.queries.append(address)
        return self.results.get(address)


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.statements = []
        self.params = []
        self.update_params = []
        self.rowcount = 1

    def execute(self, statement, params=None):
        self.statements.append(statement)
        self.params.append(params)
        if statement.strip().startswith("UPDATE housing_complexes"):
            self.update_params.append(params)

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
