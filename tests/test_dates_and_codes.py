import unittest

from hedonic_house_price.dates import recent_months
from hedonic_house_price.law_codes import (
    BUSAN_DISTRICT_CODES,
    CITY_DISTRICT_CODES,
    SEOUL_DISTRICT_CODES,
    city_code_for_lawd_cd,
    city_name_for_city_code,
    district_codes_for_city,
)


class DateAndCodeTests(unittest.TestCase):
    def test_recent_months_returns_yyyymm_values_ending_at_reference_month(self):
        self.assertEqual(
            recent_months(count=4, reference_yyyymm="202606"),
            ["202603", "202604", "202605", "202606"],
        )

    def test_recent_months_rolls_across_year_boundary(self):
        self.assertEqual(
            recent_months(count=5, reference_yyyymm="202601"),
            ["202509", "202510", "202511", "202512", "202601"],
        )

    def test_seoul_law_code_map_has_all_25_districts(self):
        self.assertEqual(len(SEOUL_DISTRICT_CODES), 25)
        self.assertEqual(SEOUL_DISTRICT_CODES["강남구"], "11680")
        self.assertEqual(SEOUL_DISTRICT_CODES["종로구"], "11110")
        self.assertEqual(SEOUL_DISTRICT_CODES["중구"], "11140")

    def test_busan_law_code_map_has_all_16_districts(self):
        self.assertEqual(len(BUSAN_DISTRICT_CODES), 16)
        self.assertEqual(BUSAN_DISTRICT_CODES["해운대구"], "26350")
        self.assertEqual(BUSAN_DISTRICT_CODES["기장군"], "26710")
        self.assertEqual(BUSAN_DISTRICT_CODES["중구"], "26110")

    def test_city_district_code_map_groups_seoul_and_busan(self):
        self.assertEqual(set(CITY_DISTRICT_CODES), {"seoul", "busan"})
        self.assertEqual(CITY_DISTRICT_CODES["seoul"]["강남구"], "11680")
        self.assertEqual(CITY_DISTRICT_CODES["busan"]["해운대구"], "26350")

    def test_city_code_for_lawd_cd_identifies_supported_cities(self):
        self.assertEqual(city_code_for_lawd_cd("11680"), "seoul")
        self.assertEqual(city_code_for_lawd_cd("26350"), "busan")

        with self.assertRaisesRegex(ValueError, "unsupported lawd_cd"):
            city_code_for_lawd_cd("99999")

    def test_city_name_for_city_code_returns_korean_display_name(self):
        self.assertEqual(city_name_for_city_code("seoul"), "서울특별시")
        self.assertEqual(city_name_for_city_code("busan"), "부산광역시")

        with self.assertRaisesRegex(ValueError, "unsupported city_code"):
            city_name_for_city_code("daegu")

    def test_district_codes_for_city_rejects_unknown_city(self):
        self.assertEqual(district_codes_for_city("seoul")["강남구"], "11680")
        self.assertEqual(district_codes_for_city("busan")["해운대구"], "26350")

        with self.assertRaisesRegex(ValueError, "unsupported city_code"):
            district_codes_for_city("unknown")


if __name__ == "__main__":
    unittest.main()
