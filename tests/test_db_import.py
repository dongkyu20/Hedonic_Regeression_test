import unittest

from hedonic_house_price.db_import import (
    source_row_hash,
    transaction_to_db_params,
    validate_transaction_city,
)
from hedonic_house_price.transactions import Transaction


def sample_transaction():
    return Transaction(
        district="강남구",
        lawd_cd="11680",
        deal_year=2025,
        deal_month=6,
        deal_day=11,
        legal_dong="역삼동",
        building_name="테스트아파트",
        property_type="apartment",
        exclusive_area_m2=84.95,
        floor=14,
        build_year=2005,
        price_manwon=84500,
    )


class DbImportTests(unittest.TestCase):
    def test_validate_transaction_city_accepts_matching_lawd_prefix(self):
        validate_transaction_city(sample_transaction(), "seoul")

        busan = Transaction(
            district="해운대구",
            lawd_cd="26350",
            deal_year=2025,
            deal_month=6,
            deal_day=11,
            legal_dong="우동",
            building_name="부산테스트",
            property_type="apartment",
            exclusive_area_m2=84.95,
            floor=14,
            build_year=2005,
            price_manwon=84500,
        )
        validate_transaction_city(busan, "busan")

    def test_validate_transaction_city_rejects_mismatched_city(self):
        with self.assertRaisesRegex(ValueError, "does not belong to city_code"):
            validate_transaction_city(sample_transaction(), "busan")

    def test_source_row_hash_is_stable_for_same_transaction(self):
        tx = sample_transaction()

        first = source_row_hash(tx, city_code="seoul", source_system="data_go_kr")
        second = source_row_hash(tx, city_code="seoul", source_system="data_go_kr")

        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_transaction_to_db_params_preserves_csv_values(self):
        params = transaction_to_db_params(
            sample_transaction(),
            city_code="seoul",
            region_id=123,
            complex_id=456,
            source_system="data_go_kr",
        )

        self.assertEqual(params["source_system"], "data_go_kr")
        self.assertEqual(params["source_property_type"], "apartment")
        self.assertEqual(params["property_type"], "apartment")
        self.assertEqual(params["city_code"], "seoul")
        self.assertEqual(params["region_id"], 123)
        self.assertEqual(params["complex_id"], 456)
        self.assertEqual(params["lawd_cd"], "11680")
        self.assertEqual(params["district_name"], "강남구")
        self.assertEqual(params["legal_dong_name"], "역삼동")
        self.assertEqual(params["building_name"], "테스트아파트")
        self.assertEqual(params["deal_date"], "2025-06-11")
        self.assertEqual(params["deal_yyyymm"], "202506")
        self.assertEqual(params["exclusive_area_m2"], 84.95)
        self.assertEqual(params["floor"], 14)
        self.assertEqual(params["build_year"], 2005)
        self.assertEqual(params["price_manwon"], 84500)


if __name__ == "__main__":
    unittest.main()
