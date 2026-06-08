import math
import unittest

from hedonic_house_price.features import (
    floor_band,
    make_feature_row,
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
):
    return Transaction(
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

        self.assertAlmostEqual(row["log_area_m2"], math.log(84.95))
        self.assertEqual(row["age"], 20)
        self.assertEqual(row["age_squared"], 400)
        self.assertEqual(row["floor"], 3)
        self.assertEqual(row["floor_squared"], 9)
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
        self.assertAlmostEqual(row["log_land_area_m2"], math.log(18.2))


if __name__ == "__main__":
    unittest.main()
