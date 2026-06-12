import csv
import tempfile
import unittest
from pathlib import Path

from hedonic_house_price.academies import (
    AcademyFacility,
    AcademyNearbyComplex,
    find_academy_complex_match,
    import_academy_count_snapshots,
    read_nearby_academy_complex_csv,
)
from hedonic_house_price.geocoding import GeocodeResult


class AcademyImportTests(unittest.TestCase):
    def test_read_nearby_academy_complex_csv_filters_supported_cities_and_sums_counts(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", newline="", delete=False) as handle:
            writer = csv.writer(handle, delimiter="|", quotechar='"')
            writer.writerow(
                [
                    "HSMP_INNB",
                    "PNU",
                    "RN_MNNMB",
                    "SIGNGU_CD",
                    "LNNO_ADRES",
                    "POTVALE_IFRA_HSMP_NM",
                    "HSMP_KIND_CD",
                    "DONG_CNT",
                    "NMHSH",
                    "USE_APRV_YMD",
                    "SSIZE_INSTUT_CNT",
                    "MSIZE_INSTUT_CNT",
                    "READRM_CNT",
                    "ETC_INSTUT_CNT",
                ]
            )
            writer.writerow(
                [
                    "1",
                    "1111010100100560045",
                    "",
                    "11110",
                    "서울특별시 종로구 청운동 56-45",
                    "청운현대",
                    "1",
                    "4",
                    "60",
                    "20001002",
                    "5",
                    "1",
                    "2",
                    "3",
                ]
            )
            writer.writerow(
                [
                    "2",
                    "",
                    "",
                    "41111",
                    "경기도 수원시 장안구 정자동 1",
                    "경기단지",
                    "1",
                    "1",
                    "10",
                    "20000101",
                    "9",
                    "9",
                    "9",
                    "9",
                ]
            )
            path = handle.name

        try:
            rows = read_nearby_academy_complex_csv(
                path,
                region_by_lawd_cd={"11110": ("seoul", "종로구")},
            )
        finally:
            Path(path).unlink()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].city_code, "seoul")
        self.assertEqual(rows[0].district_name, "종로구")
        self.assertEqual(rows[0].legal_dong_name, "청운동")
        self.assertEqual(rows[0].academy_count, 11)

    def test_find_academy_complex_match_uses_trimmed_jibun_address(self):
        candidates = [
            AcademyNearbyComplex(
                source_complex_id="100",
                city_code="seoul",
                district_name="성동구",
                legal_dong_name="성수동1가",
                complex_name="서울숲아이파크리버포레2차",
                jibun_address="서울특별시 성동구 성수동1가 723",
                academy_count=14,
            )
        ]
        complex_row = {
            "city_code": "seoul",
            "district_name": "성동구",
            "legal_dongs": "성수동1가",
            "complex_name": "서울숲아이파크리버포레2차",
            "jibun_address": "서울특별시 성동구 성수동1가 723- 서울숲 아이파크 리버포레2차",
            "road_address": "",
        }

        match = find_academy_complex_match(candidates, complex_row)

        self.assertIsNotNone(match.complex)
        self.assertEqual(match.kind, "address_unique")
        self.assertEqual(match.complex.academy_count, 14)

    def test_import_academy_count_snapshots_uses_primary_then_geocoded_fallback(self):
        primary = [
            AcademyNearbyComplex(
                source_complex_id="100",
                city_code="seoul",
                district_name="종로구",
                legal_dong_name="청운동",
                complex_name="청운현대",
                jibun_address="서울특별시 종로구 청운동 56-45",
                academy_count=11,
            )
        ]
        fallback_facilities = [
            AcademyFacility(
                city_code="seoul",
                district_name="종로구",
                facility_name="가까운학원",
                address="서울특별시 종로구 사직동 10",
                searchable_text="서울특별시 종로구 사직동 10",
            ),
            AcademyFacility(
                city_code="seoul",
                district_name="종로구",
                facility_name="먼학원",
                address="서울특별시 종로구 사직동 99",
                searchable_text="서울특별시 종로구 사직동 99",
            ),
        ]
        connection = FakeConnection(
            [
                {
                    "complex_id": 1,
                    "city_code": "seoul",
                    "district_name": "종로구",
                    "legal_dongs": "청운동",
                    "deal_months": "202501\n202502",
                    "complex_name": "청운현대",
                    "jibun_address": "서울특별시 종로구 청운동 56-45",
                    "road_address": "",
                    "latitude": 37.5900,
                    "longitude": 126.9700,
                },
                {
                    "complex_id": 2,
                    "city_code": "seoul",
                    "district_name": "종로구",
                    "legal_dongs": "사직동",
                    "deal_months": "202501",
                    "complex_name": "새단지",
                    "jibun_address": "서울특별시 종로구 사직동 20",
                    "road_address": "",
                    "latitude": 37.5900,
                    "longitude": 126.9700,
                },
            ]
        )
        geocoder = FakeGeocoder(
            {
                "서울특별시 종로구 사직동 10": GeocodeResult(latitude=37.5905, longitude=126.9705),
                "서울특별시 종로구 사직동 99": GeocodeResult(latitude=37.6200, longitude=127.0200),
            }
        )

        result = import_academy_count_snapshots(
            connection,
            primary,
            fallback_facilities,
            geocoder=geocoder,
            source_name="academy_nearby_complex_2604",
            radius_m=500,
            sleep_seconds=0,
        )

        self.assertEqual(result["primary_matched_complexes"], 1)
        self.assertEqual(result["fallback_matched_complexes"], 1)
        self.assertEqual(result["unmatched_complexes"], 0)
        self.assertEqual(connection.cursor_obj.upsert_params[0][4], 11)
        self.assertEqual(connection.cursor_obj.upsert_params[1][4], 11)
        self.assertEqual(connection.cursor_obj.upsert_params[2][4], 1)


class FakeGeocoder:
    def __init__(self, results):
        self.results = results
        self.queries = []

    def geocode(self, address):
        self.queries.append(address)
        return self.results.get(address)


class FakeCursor:
    def __init__(self, complex_rows):
        self.complex_rows = complex_rows
        self.statements = []
        self.upsert_params = []
        self.rowcount = 1

    def execute(self, statement, params=None):
        self.statements.append(statement)
        if statement.strip().startswith("INSERT INTO living_environment_snapshots"):
            self.upsert_params.append(params)

    def fetchall(self):
        return self.complex_rows

    def close(self):
        self.statements.append("CLOSE")


class FakeConnection:
    def __init__(self, complex_rows):
        self.cursor_obj = FakeCursor(complex_rows)
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
