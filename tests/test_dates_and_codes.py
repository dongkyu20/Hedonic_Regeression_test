import unittest

from hedonic_house_price.dates import recent_months
from hedonic_house_price.law_codes import SEOUL_DISTRICT_CODES


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


if __name__ == "__main__":
    unittest.main()
