import csv
import tempfile
import unittest
from pathlib import Path

from hedonic_house_price.complex_info import (
    ComplexBasicInfo,
    find_complex_basic_info_match,
    import_complex_property_conditions_csv,
    is_apartment_like_category,
    normalize_complex_name,
    normalize_legal_dong_name,
    read_complex_basic_info_csv,
)


class ComplexInfoTests(unittest.TestCase):
    def test_normalize_complex_name_removes_common_spacing_and_symbols(self):
        self.assertEqual(normalize_complex_name("경희궁 자이(3단지)"), "경희궁자이3단지")

    def test_normalize_legal_dong_name_collapses_eup_myeon_ri_suffixes(self):
        self.assertEqual(normalize_legal_dong_name("정관읍 모전리"), "모전리")
        self.assertEqual(normalize_legal_dong_name("철마면 고촌리"), "고촌리")
        self.assertEqual(normalize_legal_dong_name("기장읍 청강리"), "청강리")
        self.assertEqual(normalize_legal_dong_name("대저1동"), "대저1동")
        self.assertEqual(normalize_legal_dong_name("회현동1가"), "회현동1가")

    def test_is_apartment_like_category_accepts_apartment_and_mixed_use_only(self):
        self.assertTrue(is_apartment_like_category("아파트"))
        self.assertTrue(is_apartment_like_category("주상복합"))
        self.assertFalse(is_apartment_like_category("연립주택"))
        self.assertFalse(is_apartment_like_category("다세대"))

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

    def test_read_complex_basic_info_csv_reads_property_condition_columns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "complex_info.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["자료 안내", "", "", "", "", "", "", "", ""])
                writer.writerow(
                    [
                        "시도",
                        "시군구",
                        "읍면",
                        "동리",
                        "단지코드",
                        "단지명",
                        "단지분류",
                        "법정동주소",
                        "도로명주소",
                        "사용승인일",
                        "동수",
                        "세대수",
                        "총주차대수",
                        "부대복리시설",
                        "최고층수",
                        "입주편의시설",
                    ]
                )
                writer.writerow(
                    [
                        "서울특별시",
                        "종로구",
                        "",
                        "내수동",
                        "A1",
                        "경희궁의아침3단지",
                        "주상복합",
                        "서울 종로구 내수동 72",
                        "서울 종로구 사직로8길 34",
                        "20040517",
                        "1",
                        "150.0",
                        "315",
                        "관리사무소, 주민공동시설",
                        "16",
                        "없음",
                    ]
                )

            rows = read_complex_basic_info_csv(path)

        self.assertEqual(rows[0].approval_date, "20040517")
        self.assertEqual(rows[0].building_count, 1)
        self.assertEqual(rows[0].household_count, 150)
        self.assertEqual(rows[0].total_parking_spaces, 315)
        self.assertEqual(rows[0].max_floor, 16)
        self.assertEqual(rows[0].community_facilities, "관리사무소, 주민공동시설")
        self.assertEqual(rows[0].resident_convenience_facilities, "없음")

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

    def test_find_complex_basic_info_match_accepts_likely_name_variant(self):
        candidates = [
            ComplexBasicInfo(
                "seoul",
                "서울특별시",
                "송파구",
                "가락동",
                "A1",
                "헬리오시티아파트",
                "아파트",
                "서울 송파구 가락동",
                "서울 송파구 송파대로",
            )
        ]

        match = find_complex_basic_info_match(
            candidates,
            city_code="seoul",
            district_name="송파구",
            legal_dong_names=["가락동"],
            complex_name="헬리오시티",
        )

        self.assertIsNotNone(match.info)
        self.assertEqual(match.kind, "likely_name_variant")
        self.assertGreaterEqual(match.score, 0.9)

    def test_find_complex_basic_info_match_accepts_possible_name_variant(self):
        candidates = [
            ComplexBasicInfo(
                "seoul",
                "서울특별시",
                "중구",
                "신당동",
                "A1",
                "래미안신당하이베르",
                "아파트",
                "서울 중구 신당동",
                "서울 중구 다산로",
            )
        ]

        match = find_complex_basic_info_match(
            candidates,
            city_code="seoul",
            district_name="중구",
            legal_dong_names=["신당동"],
            complex_name="래미안하이베르",
        )

        self.assertIsNotNone(match.info)
        self.assertEqual(match.kind, "possible_name_variant")
        self.assertGreaterEqual(match.score, 0.72)
        self.assertLess(match.score, 0.9)

    def test_find_complex_basic_info_match_rejects_tied_name_variant_candidates(self):
        candidates = [
            ComplexBasicInfo("seoul", "서울특별시", "송파구", "신천동", "A1", "잠실파크리오", "아파트", "지번1", "도로1"),
            ComplexBasicInfo("seoul", "서울특별시", "송파구", "신천동", "A2", "신천파크리오", "아파트", "지번2", "도로2"),
        ]

        match = find_complex_basic_info_match(
            candidates,
            city_code="seoul",
            district_name="송파구",
            legal_dong_names=["신천동"],
            complex_name="파크리오",
        )

        self.assertIsNone(match.info)
        self.assertEqual(match.kind, "ambiguous_name_variant")

    def test_find_complex_basic_info_match_accepts_tied_name_variant_when_enabled(self):
        candidates = [
            ComplexBasicInfo("seoul", "서울특별시", "송파구", "신천동", "A2", "신천파크리오", "아파트", "지번2", "도로2"),
            ComplexBasicInfo("seoul", "서울특별시", "송파구", "신천동", "A1", "잠실파크리오", "아파트", "지번1", "도로1"),
        ]

        match = find_complex_basic_info_match(
            candidates,
            city_code="seoul",
            district_name="송파구",
            legal_dong_names=["신천동"],
            complex_name="파크리오",
            accept_remaining_matches=True,
        )

        self.assertIsNotNone(match.info)
        self.assertEqual(match.kind, "ambiguous_name_variant")
        self.assertEqual(match.info.source_complex_code, "A1")

    def test_find_complex_basic_info_match_accepts_low_confidence_same_dong_when_enabled(self):
        candidates = [
            ComplexBasicInfo("seoul", "서울특별시", "종로구", "창신동", "A1", "창신두산", "아파트", "지번1", "도로1"),
        ]

        match = find_complex_basic_info_match(
            candidates,
            city_code="seoul",
            district_name="종로구",
            legal_dong_names=["창신동"],
            complex_name="브라운스톤창신",
            accept_remaining_matches=True,
        )

        self.assertIsNotNone(match.info)
        self.assertEqual(match.kind, "counterpart_has_dong_but_name_absent")
        self.assertLess(match.score, 0.72)

    def test_find_complex_basic_info_match_accepts_zero_score_same_dong_when_enabled(self):
        candidates = [
            ComplexBasicInfo("seoul", "서울특별시", "종로구", "창신동", "A1", "라마바", "아파트", "지번1", "도로1"),
        ]

        match = find_complex_basic_info_match(
            candidates,
            city_code="seoul",
            district_name="종로구",
            legal_dong_names=["창신동"],
            complex_name="가나다",
            accept_remaining_matches=True,
        )

        self.assertIsNotNone(match.info)
        self.assertEqual(match.kind, "counterpart_has_dong_but_name_absent")
        self.assertEqual(match.score, 0.0)

    def test_find_complex_basic_info_match_does_not_accept_low_confidence_without_same_dong(self):
        candidates = [
            ComplexBasicInfo("seoul", "서울특별시", "종로구", "창신동", "A1", "창신두산", "아파트", "지번1", "도로1"),
        ]

        match = find_complex_basic_info_match(
            candidates,
            city_code="seoul",
            district_name="종로구",
            legal_dong_names=["사직동"],
            complex_name="광화문스페이스본",
            accept_remaining_matches=True,
        )

        self.assertIsNone(match.info)
        self.assertEqual(match.kind, "unmatched")

    def test_find_complex_basic_info_match_uses_normalized_legal_dong_names(self):
        candidates = [
            ComplexBasicInfo("busan", "부산광역시", "기장군", "모전리", "A1", "정관현진에버빌", "아파트", "지번1", "도로1"),
        ]

        match = find_complex_basic_info_match(
            candidates,
            city_code="busan",
            district_name="기장군",
            legal_dong_names=["정관읍 모전리"],
            complex_name="정관현진에버빌",
        )

        self.assertIsNotNone(match.info)
        self.assertEqual(match.kind, "dong")

    def test_import_complex_property_conditions_inserts_monthly_snapshots(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "complex_info.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["자료 안내", "", "", "", "", "", "", "", ""])
                writer.writerow(
                    [
                        "시도",
                        "시군구",
                        "읍면",
                        "동리",
                        "단지코드",
                        "단지명",
                        "단지분류",
                        "법정동주소",
                        "도로명주소",
                        "사용승인일",
                        "동수",
                        "세대수",
                        "총주차대수",
                        "부대복리시설",
                        "최고층수",
                        "입주편의시설",
                    ]
                )
                writer.writerow(
                    [
                        "서울특별시",
                        "종로구",
                        "",
                        "내수동",
                        "A1",
                        "경희궁의아침3단지",
                        "주상복합",
                        "서울 종로구 내수동 72",
                        "서울 종로구 사직로8길 34",
                        "20040517",
                        "1",
                        "150.0",
                        "315",
                        "관리사무소, 주민공동시설",
                        "16",
                        "없음",
                    ]
                )

            connection = FakeConnection(
                [
                    {
                        "complex_id": 10,
                        "complex_name": "경희궁의아침3단지",
                        "city_code": "seoul",
                        "district_name": "종로구",
                        "legal_dongs": "내수동",
                        "deal_months": "202505\n202601",
                    }
                ]
            )

            result = import_complex_property_conditions_csv(connection, path)

        self.assertEqual(result["matched_complexes"], 1)
        self.assertEqual(result["snapshot_rows"], 2)
        self.assertEqual(connection.commits, 1)
        insert_params = connection.cursor_obj.params
        self.assertEqual(insert_params[0][:3], (10, "202505", "kapt_basic_info"))
        self.assertEqual(insert_params[0][3:], (16, 2004, 21, 150, 1, 315, 2.1, 1))
        self.assertEqual(insert_params[1][5], 22)


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.statements = []
        self.params = []
        self.rowcount = 1

    def execute(self, statement, params=None):
        self.statements.append(statement)
        if params is not None:
            self.params.append(params)

    def fetchall(self):
        return self.rows

    def close(self):
        self.statements.append("CLOSE")


class FakeConnection:
    def __init__(self, rows):
        self.cursor_obj = FakeCursor(rows)
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
