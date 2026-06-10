import math
import unittest

from hedonic_house_price.features import (
    complex_floor_key,
    estimate_complex_max_floors,
    floor_band,
    make_feature_row,
    make_feature_rows,
    month_index,
)
from hedonic_house_price.transactions import Transaction


def tx(
    building_name="테스트아파트",
    property_type="apartment",
    house_type="",
    land_area_m2=None,
    deal_year=2025,
    deal_month=6,
    deal_day=11,
    floor=14,
    build_year=2005,
    area=84.95,
    price_manwon=84500,
    extra_features=None,
):
    transaction = Transaction(
        district="강남구",
        lawd_cd="11680",
        deal_year=deal_year,
        deal_month=deal_month,
        deal_day=deal_day,
        legal_dong="역삼동",
        building_name=building_name,
        property_type=property_type,
        house_type=house_type,
        land_area_m2=land_area_m2,
        exclusive_area_m2=area,
        floor=floor,
        build_year=build_year,
        price_manwon=price_manwon,
    )
    if extra_features is not None:
        object.__setattr__(transaction, "extra_features", extra_features)
    return transaction


class FeatureTests(unittest.TestCase):
    def test_floor_band_uses_non_monotonic_categories(self):
        self.assertEqual(floor_band(1), "floor_1")
        self.assertEqual(floor_band(2), "floor_2_3")
        self.assertEqual(floor_band(7), "floor_4_7")
        self.assertEqual(floor_band(12), "floor_8_12")
        self.assertEqual(floor_band(15), "floor_13_18")
        self.assertEqual(floor_band(22), "floor_19_25")
        self.assertEqual(floor_band(26), "floor_26_plus")

    def test_month_index_counts_elapsed_months(self):
        self.assertEqual(month_index("202406", "202406"), 0)
        self.assertEqual(month_index("202406", "202506"), 12)
        self.assertEqual(month_index("202512", "202601"), 1)

    def test_make_feature_row_contains_hedonic_features(self):
        row = make_feature_row(tx(floor=3), first_month="202406")

        self.assertAlmostEqual(row["log_area_m2"], math.log1p(84.95))
        self.assertEqual(row["age_band"], "age_20_29")
        self.assertNotIn("age", row)
        self.assertNotIn("age_squared", row)
        self.assertNotIn("floor", row)
        self.assertNotIn("floor_squared", row)
        self.assertEqual(row["low_floor"], 1)
        self.assertEqual(row["floor_band"], "floor_2_3")
        self.assertEqual(row["deal_month_index"], 12)
        self.assertEqual(row["calendar_month"], "6")
        self.assertEqual(row["district"], "강남구")
        self.assertEqual(row["legal_dong"], "역삼동")
        self.assertEqual(row["property_type"], "apartment")
        self.assertEqual(row["house_type"], "unknown")
        self.assertEqual(row["has_land_area"], 0)
        self.assertEqual(row["log_land_area_m2"], 0.0)
        self.assertAlmostEqual(row["target_log_price"], math.log(845_000_000))

    def test_make_feature_rows_adds_estimated_relative_floor_features(self):
        rows = [
            tx(building_name="21층관측단지", floor=1),
            tx(building_name="21층관측단지", floor=21),
            tx(building_name="7층관측단지", floor=2),
            tx(building_name="7층관측단지", floor=7),
        ]

        estimates = estimate_complex_max_floors(rows)
        feature_rows = make_feature_rows(rows, first_month="202406", estimated_max_floors=estimates)

        self.assertEqual(estimates[complex_floor_key(rows[1])], 24)
        self.assertEqual(estimates[complex_floor_key(rows[3])], 8)

        first_floor = feature_rows[0]
        self.assertEqual(first_floor["estimated_max_floor"], 24)
        self.assertAlmostEqual(first_floor["relative_floor"], 1 / 24)
        self.assertEqual(first_floor["is_first_floor"], 1)
        self.assertEqual(first_floor["is_floor_2_3"], 0)
        self.assertEqual(first_floor["is_estimated_top_floor"], 0)

        second_floor = feature_rows[2]
        self.assertEqual(second_floor["estimated_max_floor"], 8)
        self.assertAlmostEqual(second_floor["relative_floor"], 2 / 8)
        self.assertEqual(second_floor["is_first_floor"], 0)
        self.assertEqual(second_floor["is_floor_2_3"], 1)
        self.assertEqual(second_floor["is_estimated_top_floor"], 0)

        inferred_top_floor = make_feature_row(
            tx(building_name="7층관측단지", floor=8),
            first_month="202406",
            estimated_max_floors=estimates,
        )
        self.assertEqual(inferred_top_floor["estimated_max_floor"], 8)
        self.assertAlmostEqual(inferred_top_floor["relative_floor"], 1.0)
        self.assertEqual(inferred_top_floor["is_estimated_top_floor"], 1)
        self.assertEqual(inferred_top_floor["is_near_estimated_top_floor"], 1)

    def test_make_feature_row_excludes_apartment_name_from_model_features(self):
        row = make_feature_row(tx(building_name="희귀단지"), first_month="202406")

        self.assertNotIn("apartment_name", row)
        self.assertNotIn("building_name", row)
        self.assertNotIn("apartment_name_grouped", row)

    def test_make_feature_row_contains_non_apartment_features(self):
        row = make_feature_row(
            tx(property_type="rowhouse", house_type="다세대", land_area_m2=18.2),
            first_month="202406",
        )

        self.assertEqual(row["property_type"], "rowhouse")
        self.assertEqual(row["house_type"], "다세대")
        self.assertEqual(row["has_land_area"], 1)
        self.assertAlmostEqual(row["log_land_area_m2"], math.log1p(18.2))

    def test_make_feature_row_transforms_db_factor_features(self):
        row = make_feature_row(
            tx(
                extra_features={
                    "city_code": "seoul",
                    "household_count": 1500,
                    "building_count": 10,
                    "total_parking_spaces": 1800,
                    "parking_spaces_per_household": 1.2,
                    "has_community_facilities": 1,
                    "nearest_subway_distance_m": 425.0,
                    "subway_count_radius": 2,
                    "nearest_bus_stop_distance_m": 90.0,
                    "bus_stop_count_radius": 14,
                    "car_airport_minutes": 65.5,
                    "nearest_elementary_school_distance_m": 310.0,
                    "nearest_middle_school_distance_m": None,
                    "school_count_radius": 3,
                    "academy_count_radius": 27,
                    "nearest_hospital_distance_m": 540.0,
                    "nearest_pharmacy_distance_m": 120.0,
                    "nearest_park_distance_m": 250.0,
                    "park_area_total_m2_radius": 3200.0,
                }
            ),
            first_month="202406",
        )

        self.assertEqual(row["city_code"], "seoul")
        self.assertAlmostEqual(row["log_household_count"], math.log1p(1500))
        self.assertEqual(row["households_per_building"], 150.0)
        self.assertNotIn("building_count", row)
        self.assertAlmostEqual(row["log_total_parking_spaces"], math.log1p(1800))
        self.assertEqual(row["parking_spaces_per_household"], 1.2)
        self.assertEqual(row["has_community_facilities"], 1)
        self.assertAlmostEqual(row["log_nearest_subway_distance_m"], math.log1p(425.0))
        self.assertEqual(row["subway_count_radius_bin"], "count_1_2")
        self.assertAlmostEqual(row["log_car_airport_minutes"], math.log1p(65.5))
        self.assertAlmostEqual(row["log_nearest_elementary_school_distance_m"], math.log1p(310.0))
        self.assertEqual(row["nearest_middle_school_distance_m_missing"], 1)
        self.assertEqual(row["school_count_radius_bin"], "count_3_5")
        self.assertEqual(row["academy_count_radius_bin"], "count_21_plus")
        self.assertAlmostEqual(row["log_nearest_hospital_distance_m"], math.log1p(540.0))
        self.assertAlmostEqual(row["log_nearest_pharmacy_distance_m"], math.log1p(120.0))
        self.assertEqual(row["park_exists"], 1)
        self.assertAlmostEqual(row["log_nearest_park_distance_m"], math.log1p(250.0))
        self.assertAlmostEqual(row["log_park_area_total_m2_radius"], math.log1p(3200.0))


if __name__ == "__main__":
    unittest.main()
