import unittest

from hedonic_house_price.db_training import training_view_row_to_transaction


class DbTrainingTests(unittest.TestCase):
    def test_training_view_row_to_transaction_preserves_model_fields(self):
        tx = training_view_row_to_transaction(
            {
                "property_type": "rowhouse",
                "district": "강남구",
                "lawd_cd": "11680",
                "deal_year": 2025,
                "deal_month": 6,
                "deal_day": 11,
                "legal_dong": "역삼동",
                "building_name": "테스트빌라",
                "house_type": "다세대",
                "land_area_m2": 18.2,
                "exclusive_area_m2": 84.95,
                "floor": 14,
                "build_year": 2005,
                "price_manwon": 84500,
            }
        )

        self.assertEqual(tx.property_type, "rowhouse")
        self.assertEqual(tx.district, "강남구")
        self.assertEqual(tx.lawd_cd, "11680")
        self.assertEqual(tx.deal_yyyymm, "202506")
        self.assertEqual(tx.legal_dong, "역삼동")
        self.assertEqual(tx.building_name, "테스트빌라")
        self.assertEqual(tx.house_type, "다세대")
        self.assertEqual(tx.land_area_m2, 18.2)
        self.assertEqual(tx.exclusive_area_m2, 84.95)
        self.assertEqual(tx.price_krw, 845_000_000)

    def test_training_view_row_to_transaction_raises_for_missing_required_column(self):
        with self.assertRaisesRegex(ValueError, "missing training view column"):
            training_view_row_to_transaction({"district": "강남구"})


if __name__ == "__main__":
    unittest.main()
