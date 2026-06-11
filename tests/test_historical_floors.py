import csv
import tempfile
import unittest
from pathlib import Path

from hedonic_house_price.historical_floors import (
    HistoricalFloorStat,
    build_historical_floor_stats,
    fetch_historical_floor_stats,
    historical_months,
    write_historical_floor_stats_csv,
)
from hedonic_house_price.transactions import Transaction


def tx(
    *,
    city_code="seoul",
    district="강남구",
    lawd_cd="11680",
    legal_dong="역삼동",
    building_name="테스트아파트",
    floor=1,
    year=2020,
    month=1,
    build_year=2005,
):
    return Transaction(
        district=district,
        lawd_cd=lawd_cd,
        deal_year=year,
        deal_month=month,
        deal_day=10,
        legal_dong=legal_dong,
        building_name=building_name,
        exclusive_area_m2=84.9,
        floor=floor,
        build_year=build_year,
        price_manwon=90_000,
        extra_features={"city_code": city_code},
    )


class HistoricalFloorTests(unittest.TestCase):
    def test_historical_months_returns_inclusive_range(self):
        self.assertEqual(historical_months("201001", "201004"), ["201001", "201002", "201003", "201004"])

    def test_historical_months_rejects_reversed_range(self):
        with self.assertRaisesRegex(ValueError, "start_month"):
            historical_months("201004", "201001")

    def test_build_historical_floor_stats_uses_observed_max_floor_as_estimate(self):
        rows = [
            tx(floor=3, year=2011, month=1),
            tx(floor=21, year=2019, month=5),
            tx(floor=7, year=2020, month=3, building_name="낮은단지"),
        ]

        stats = build_historical_floor_stats(rows)

        high = stats[("apartment", "11680", "역삼동", "테스트아파트")]
        self.assertEqual(high.observed_max_floor, 21)
        self.assertEqual(high.estimated_max_floor, 21)
        self.assertEqual(high.observation_count, 2)
        self.assertEqual(high.first_observed_yyyymm, "201101")
        self.assertEqual(high.last_observed_yyyymm, "201905")

        low = stats[("apartment", "11680", "역삼동", "낮은단지")]
        self.assertEqual(low.observed_max_floor, 7)
        self.assertEqual(low.estimated_max_floor, 7)

    def test_build_historical_floor_stats_tracks_city_and_confidence(self):
        rows = [
            tx(city_code="busan", district="해운대구", lawd_cd="26350", legal_dong="우동", floor=10, month=1),
            tx(city_code="busan", district="해운대구", lawd_cd="26350", legal_dong="우동", floor=12, month=2),
            tx(city_code="busan", district="해운대구", lawd_cd="26350", legal_dong="우동", floor=15, month=3),
            tx(city_code="busan", district="해운대구", lawd_cd="26350", legal_dong="우동", floor=16, month=4),
            tx(city_code="busan", district="해운대구", lawd_cd="26350", legal_dong="우동", floor=18, month=5),
        ]

        stat = build_historical_floor_stats(rows)[("apartment", "26350", "우동", "테스트아파트")]

        self.assertEqual(stat.city_code, "busan")
        self.assertEqual(stat.district, "해운대구")
        self.assertEqual(stat.confidence, "medium")

    def test_write_historical_floor_stats_csv(self):
        stat = HistoricalFloorStat(
            city_code="seoul",
            property_type="apartment",
            district="강남구",
            lawd_cd="11680",
            legal_dong="역삼동",
            building_name="테스트아파트",
            observed_max_floor=21,
            estimated_max_floor=21,
            observation_count=12,
            first_observed_yyyymm="201001",
            last_observed_yyyymm="202606",
            min_build_year=2001,
            max_build_year=2005,
            confidence="medium",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "stats.csv"
            write_historical_floor_stats_csv([stat], output)

            with output.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(rows[0]["city_code"], "seoul")
        self.assertEqual(rows[0]["building_name"], "테스트아파트")
        self.assertEqual(rows[0]["observed_max_floor"], "21")
        self.assertEqual(rows[0]["estimated_max_floor"], "21")

    def test_fetch_historical_floor_stats_accumulates_monthly_city_district_fetches(self):
        calls = []

        def fake_fetcher(**kwargs):
            calls.append(kwargs)
            if kwargs["lawd_cd"] != "11680":
                return []
            return [
                tx(floor=21, year=2010, month=1),
            ]

        stats = fetch_historical_floor_stats(
            service_key="service-key",
            city_codes=["seoul"],
            start_month="201001",
            end_month="201001",
            sleep_seconds=0,
            workers=2,
            fetcher=fake_fetcher,
        )

        self.assertEqual(len(calls), 25)
        self.assertEqual(calls[0]["property_type"], "apartment")
        self.assertEqual(len(stats), 1)
        self.assertEqual(stats[0].city_code, "seoul")
        self.assertEqual(stats[0].estimated_max_floor, 21)


if __name__ == "__main__":
    unittest.main()
