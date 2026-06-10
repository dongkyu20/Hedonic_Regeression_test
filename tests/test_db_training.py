import unittest

from hedonic_house_price.db_training import read_transactions_from_training_view, training_view_row_to_transaction


class DbTrainingTests(unittest.TestCase):
    def test_training_view_row_to_transaction_preserves_model_fields(self):
        tx = training_view_row_to_transaction(
            {
                "city_code": "seoul",
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
                "household_count": 1500,
                "kapt_max_floor": 29,
                "nearest_subway_distance_m": 425.0,
                "academy_count_radius": 27,
                "park_area_total_m2_radius": 3200.0,
            }
        )

        self.assertEqual(getattr(tx, "extra_features", {})["city_code"], "seoul")
        self.assertEqual(getattr(tx, "extra_features", {})["household_count"], 1500)
        self.assertEqual(getattr(tx, "extra_features", {})["kapt_max_floor"], 29)
        self.assertEqual(getattr(tx, "extra_features", {})["nearest_subway_distance_m"], 425.0)
        self.assertEqual(getattr(tx, "extra_features", {})["academy_count_radius"], 27)
        self.assertEqual(getattr(tx, "extra_features", {})["park_area_total_m2_radius"], 3200.0)
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

    def test_read_transactions_from_training_view_selects_factor_columns(self):
        connection = FakeConnection([])

        read_transactions_from_training_view(connection, city_code="seoul", property_types=["apartment"])

        query = connection.cursor_obj.statements[0]
        self.assertIn("city_code", query)
        self.assertIn("household_count", query)
        self.assertIn("kapt_max_floor", query)
        self.assertIn("nearest_subway_distance_m", query)
        self.assertIn("academy_count_radius", query)
        self.assertIn("park_area_total_m2_radius", query)

    def test_read_transactions_from_training_view_excludes_incomplete_factor_rows_by_default(self):
        connection = FakeConnection([])

        read_transactions_from_training_view(connection, city_code="seoul", property_types=["apartment"])

        query = connection.cursor_obj.statements[0]
        self.assertIn("household_count IS NOT NULL", query)
        self.assertIn("nearest_subway_distance_m IS NOT NULL", query)
        self.assertIn("nearest_middle_school_distance_m IS NOT NULL", query)
        self.assertIn("nearest_hospital_distance_m IS NOT NULL", query)
        self.assertIn("park_area_total_m2_radius IS NOT NULL", query)
        self.assertIn("recent_transaction_count IS NOT NULL", query)
        self.assertNotIn("kapt_max_floor IS NOT NULL", query)

    def test_read_transactions_from_training_view_can_include_incomplete_factor_rows_for_diagnostics(self):
        connection = FakeConnection([])

        read_transactions_from_training_view(
            connection,
            city_code="seoul",
            property_types=["apartment"],
            require_complete_factors=False,
        )

        query = connection.cursor_obj.statements[0]
        self.assertNotIn("household_count IS NOT NULL", query)
        self.assertNotIn("nearest_subway_distance_m IS NOT NULL", query)


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.statements = []
        self.params = []

    def execute(self, statement, params=None):
        self.statements.append(statement)
        self.params.append(params)

    def fetchall(self):
        return self.rows

    def close(self):
        self.statements.append("CLOSE")


class FakeConnection:
    def __init__(self, rows):
        self.cursor_obj = FakeCursor(rows)

    def cursor(self, **kwargs):
        return self.cursor_obj


if __name__ == "__main__":
    unittest.main()
