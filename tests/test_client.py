import os
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse

from hedonic_house_price.client import (
    API_ENDPOINTS,
    API_BASE_URL,
    build_request_url,
    parse_apartment_trade_xml,
    parse_trade_xml,
)
from hedonic_house_price.config import get_service_key, load_env_file
from hedonic_house_price.transactions import transaction_from_row


SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<response>
  <header>
    <resultCode>00</resultCode>
    <resultMsg>NORMAL SERVICE.</resultMsg>
  </header>
  <body>
    <items>
      <item>
        <dealAmount>84,500</dealAmount>
        <buildYear>2005</buildYear>
        <dealYear>2025</dealYear>
        <dealMonth>6</dealMonth>
        <dealDay>11</dealDay>
        <umdNm>역삼동</umdNm>
        <aptNm>테스트아파트</aptNm>
        <excluUseAr>84.95</excluUseAr>
        <floor>14</floor>
      </item>
      <item>
        <거래금액>102,000</거래금액>
        <건축년도>2010</건축년도>
        <년>2025</년>
        <월>6</월>
        <일>20</일>
        <법정동> 삼성동 </법정동>
        <아파트>한글필드아파트</아파트>
        <전용면적>59.8</전용면적>
        <층>3</층>
      </item>
    </items>
    <totalCount>2</totalCount>
  </body>
</response>
"""

SAMPLE_OFFICETEL_XML = """<?xml version="1.0" encoding="UTF-8"?>
<response>
  <header>
    <resultCode>000</resultCode>
    <resultMsg>OK</resultMsg>
  </header>
  <body>
    <items>
      <item>
        <dealAmount>55,000</dealAmount>
        <buildYear>2018</buildYear>
        <dealYear>2025</dealYear>
        <dealMonth>5</dealMonth>
        <dealDay>20</dealDay>
        <umdNm>문정동</umdNm>
        <offiNm>테스트오피스텔</offiNm>
        <excluUseAr>42.4</excluUseAr>
        <floor>12</floor>
      </item>
    </items>
    <totalCount>1</totalCount>
  </body>
</response>
"""

SAMPLE_OFFICETEL_MISSING_BUILD_YEAR_XML = """<?xml version="1.0" encoding="UTF-8"?>
<response>
  <header>
    <resultCode>000</resultCode>
    <resultMsg>OK</resultMsg>
  </header>
  <body>
    <items>
      <item>
        <dealAmount>55,000</dealAmount>
        <dealYear>2025</dealYear>
        <dealMonth>5</dealMonth>
        <dealDay>20</dealDay>
        <umdNm>문정동</umdNm>
        <offiNm>건축년도없는오피스텔</offiNm>
        <excluUseAr>42.4</excluUseAr>
        <floor>12</floor>
      </item>
      <item>
        <dealAmount>60,000</dealAmount>
        <buildYear>2019</buildYear>
        <dealYear>2025</dealYear>
        <dealMonth>5</dealMonth>
        <dealDay>21</dealDay>
        <umdNm>문정동</umdNm>
        <offiNm>정상오피스텔</offiNm>
        <excluUseAr>44.1</excluUseAr>
        <floor>10</floor>
      </item>
    </items>
    <totalCount>2</totalCount>
  </body>
</response>
"""

SAMPLE_ROWHOUSE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<response>
  <header>
    <resultCode>000</resultCode>
    <resultMsg>OK</resultMsg>
  </header>
  <body>
    <items>
      <item>
        <dealAmount>80,000</dealAmount>
        <buildYear>2011</buildYear>
        <dealYear>2025</dealYear>
        <dealMonth>5</dealMonth>
        <dealDay>20</dealDay>
        <umdNm>역삼동</umdNm>
        <mhouseNm>테스트빌라</mhouseNm>
        <houseType>다세대</houseType>
        <excluUseAr>29.43</excluUseAr>
        <landAr>18.2</landAr>
        <floor>3</floor>
      </item>
    </items>
    <totalCount>1</totalCount>
  </body>
</response>
"""


class ConfigAndClientTests(unittest.TestCase):
    def test_load_env_file_reads_key_value_pairs_without_overwriting_process_env(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as handle:
            handle.write("# comment\nPUBLIC_DATA_SERVICE_KEY=abc123\nOTHER=value\n")
            path = handle.name
        try:
            self.assertEqual(load_env_file(path)["PUBLIC_DATA_SERVICE_KEY"], "abc123")
            self.assertNotEqual(os.environ.get("PUBLIC_DATA_SERVICE_KEY"), "abc123")
        finally:
            os.unlink(path)

    def test_get_service_key_raises_clear_error_when_missing(self):
        with self.assertRaisesRegex(RuntimeError, "PUBLIC_DATA_SERVICE_KEY"):
            get_service_key(env={}, env_path="/private/tmp/hedonic_missing_env_file")

    def test_build_request_url_uses_official_endpoint_and_query_parameters(self):
        url = build_request_url("service-key", lawd_cd="11680", deal_ymd="202506", page_no=2, num_rows=500)
        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        self.assertEqual(url.split("?")[0], API_BASE_URL)
        self.assertEqual(query["serviceKey"], ["service-key"])
        self.assertEqual(query["LAWD_CD"], ["11680"])
        self.assertEqual(query["DEAL_YMD"], ["202506"])
        self.assertEqual(query["pageNo"], ["2"])
        self.assertEqual(query["numOfRows"], ["500"])

    def test_build_request_url_selects_non_apartment_endpoints(self):
        offi_url = build_request_url("service-key", lawd_cd="11680", deal_ymd="202506", property_type="officetel")
        rowhouse_url = build_request_url("service-key", lawd_cd="11680", deal_ymd="202506", property_type="rowhouse")

        self.assertEqual(offi_url.split("?")[0], API_ENDPOINTS["officetel"])
        self.assertEqual(rowhouse_url.split("?")[0], API_ENDPOINTS["rowhouse"])

    def test_parse_apartment_trade_xml_normalizes_english_and_korean_fields(self):
        rows = parse_apartment_trade_xml(SAMPLE_XML, district="강남구", lawd_cd="11680")

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].district, "강남구")
        self.assertEqual(rows[0].legal_dong, "역삼동")
        self.assertEqual(rows[0].apartment_name, "테스트아파트")
        self.assertEqual(rows[0].exclusive_area_m2, 84.95)
        self.assertEqual(rows[0].floor, 14)
        self.assertEqual(rows[0].build_year, 2005)
        self.assertEqual(rows[0].price_manwon, 84500)
        self.assertEqual(rows[0].price_krw, 845_000_000)
        self.assertEqual(rows[0].deal_ymd, "20250611")
        self.assertEqual(rows[0].property_type, "apartment")
        self.assertEqual(rows[0].building_name, "테스트아파트")
        self.assertEqual(rows[1].legal_dong, "삼성동")

    def test_parse_apartment_trade_xml_accepts_gateway_success_code(self):
        xml = SAMPLE_XML.replace("<resultCode>00</resultCode>", "<resultCode>000</resultCode>")

        rows = parse_apartment_trade_xml(xml, district="강남구", lawd_cd="11680")

        self.assertEqual(len(rows), 2)

    def test_parse_trade_xml_normalizes_officetel_fields(self):
        rows = parse_trade_xml(SAMPLE_OFFICETEL_XML, district="송파구", lawd_cd="11710", property_type="officetel")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].property_type, "officetel")
        self.assertEqual(rows[0].building_name, "테스트오피스텔")
        self.assertEqual(rows[0].exclusive_area_m2, 42.4)
        self.assertEqual(rows[0].floor, 12)
        self.assertEqual(rows[0].price_manwon, 55000)

    def test_parse_trade_xml_skips_missing_build_year_and_reports_log_record(self):
        skipped = []

        rows = parse_trade_xml(
            SAMPLE_OFFICETEL_MISSING_BUILD_YEAR_XML,
            district="송파구",
            lawd_cd="11710",
            property_type="officetel",
            deal_ymd="202505",
            skip_logger=skipped.append,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].building_name, "정상오피스텔")
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["reason"], "missing_build_year")
        self.assertEqual(skipped[0]["property_type"], "officetel")
        self.assertEqual(skipped[0]["district"], "송파구")
        self.assertEqual(skipped[0]["deal_ymd"], "202505")
        self.assertEqual(skipped[0]["legal_dong"], "문정동")
        self.assertEqual(skipped[0]["building_name"], "건축년도없는오피스텔")
        self.assertEqual(skipped[0]["exclusive_area_m2"], "42.4")
        self.assertEqual(skipped[0]["floor"], "12")
        self.assertEqual(skipped[0]["price_manwon"], "55,000")

    def test_parse_trade_xml_normalizes_rowhouse_fields(self):
        rows = parse_trade_xml(SAMPLE_ROWHOUSE_XML, district="강남구", lawd_cd="11680", property_type="rowhouse")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].property_type, "rowhouse")
        self.assertEqual(rows[0].building_name, "테스트빌라")
        self.assertEqual(rows[0].house_type, "다세대")
        self.assertEqual(rows[0].land_area_m2, 18.2)
        self.assertEqual(rows[0].exclusive_area_m2, 29.43)

    def test_transaction_from_row_round_trips_csv_strings(self):
        tx = transaction_from_row(
            {
                "district": "강남구",
                "lawd_cd": "11680",
                "property_type": "rowhouse",
                "deal_year": "2025",
                "deal_month": "6",
                "deal_day": "11",
                "legal_dong": "역삼동",
                "building_name": "테스트빌라",
                "house_type": "다세대",
                "land_area_m2": "18.2",
                "exclusive_area_m2": "84.95",
                "floor": "14",
                "build_year": "2005",
                "price_manwon": "84500",
            }
        )

        self.assertEqual(tx.price_krw, 845_000_000)
        self.assertEqual(tx.deal_ymd, "20250611")
        self.assertEqual(tx.property_type, "rowhouse")
        self.assertEqual(tx.building_name, "테스트빌라")
        self.assertEqual(tx.apartment_name, "테스트빌라")
        self.assertEqual(tx.house_type, "다세대")
        self.assertEqual(tx.land_area_m2, 18.2)


if __name__ == "__main__":
    unittest.main()
