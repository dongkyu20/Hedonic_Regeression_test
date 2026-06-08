import csv
import tempfile
import unittest
from pathlib import Path

from hedonic_house_price.complex_info import (
    ComplexBasicInfo,
    find_complex_basic_info_match,
    normalize_complex_name,
    read_complex_basic_info_csv,
)


class ComplexInfoTests(unittest.TestCase):
    def test_normalize_complex_name_removes_common_spacing_and_symbols(self):
        self.assertEqual(normalize_complex_name("경희궁 자이(3단지)"), "경희궁자이3단지")

    def test_read_complex_basic_info_csv_skips_notice_row_and_filters_supported_cities(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "complex_info.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["자료 안내", "", "", "", "", "", "", "", ""])
                writer.writerow(["시도", "시군구", "읍면", "동리", "단지코드", "단지명", "단지분류", "법정동주소", "도로명주소"])
                writer.writerow(["서울특별시", "종로구", "", "평동", "A1", "경희궁자이3단지", "아파트", "서울 종로구 평동 233", "서울 종로구 경교장길 35"])
                writer.writerow(["대구광역시", "중구", "", "동인동", "A2", "미지원단지", "아파트", "대구 주소", "대구 도로"])

            rows = read_complex_basic_info_csv(path)

        self.assertEqual(
            rows,
            [
                ComplexBasicInfo(
                    city_code="seoul",
                    city_name="서울특별시",
                    district_name="종로구",
                    legal_dong_name="평동",
                    source_complex_code="A1",
                    complex_name="경희궁자이3단지",
                    complex_category="아파트",
                    jibun_address="서울 종로구 평동 233",
                    road_address="서울 종로구 경교장길 35",
                )
            ],
        )

    def test_find_complex_basic_info_match_prefers_legal_dong_match(self):
        candidates = [
            ComplexBasicInfo(
                city_code="seoul",
                city_name="서울특별시",
                district_name="종로구",
                legal_dong_name="평동",
                source_complex_code="A1",
                complex_name="경희궁자이3단지",
                complex_category="아파트",
                jibun_address="서울 종로구 평동 233",
                road_address="서울 종로구 경교장길 35",
            )
        ]

        match = find_complex_basic_info_match(
            candidates,
            city_code="seoul",
            district_name="종로구",
            legal_dong_names=["평동"],
            complex_name="경희궁 자이(3단지)",
        )

        self.assertIsNotNone(match.info)
        self.assertEqual(match.kind, "dong")
        self.assertEqual(match.info.source_complex_code, "A1")

    def test_find_complex_basic_info_match_rejects_ambiguous_district_fallback(self):
        candidates = [
            ComplexBasicInfo("seoul", "서울특별시", "강남구", "대치동", "A1", "현대", "아파트", "지번1", "도로1"),
            ComplexBasicInfo("seoul", "서울특별시", "강남구", "압구정동", "A2", "현대", "아파트", "지번2", "도로2"),
        ]

        match = find_complex_basic_info_match(
            candidates,
            city_code="seoul",
            district_name="강남구",
            legal_dong_names=["역삼동"],
            complex_name="현대",
        )

        self.assertIsNone(match.info)
        self.assertEqual(match.kind, "ambiguous_district")


if __name__ == "__main__":
    unittest.main()
