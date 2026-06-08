from __future__ import annotations

from typing import Callable
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
import xml.etree.ElementTree as ET

from .transactions import Transaction, normalize_property_type, parse_price_manwon


API_ENDPOINTS = {
    "apartment": "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade",
    "officetel": "https://apis.data.go.kr/1613000/RTMSDataSvcOffiTrade/getRTMSDataSvcOffiTrade",
    "rowhouse": "https://apis.data.go.kr/1613000/RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade",
}

API_BASE_URL = API_ENDPOINTS["apartment"]

BUILDING_NAME_FIELDS = {
    "apartment": ("aptNm", "아파트", "aptName", "apartmentName"),
    "officetel": ("offiNm", "officetelNm", "officetelName", "단지명", "오피스텔"),
    "rowhouse": ("mhouseNm", "houseNm", "buildingName", "연립다세대", "단지명"),
}


def build_request_url(
    service_key: str,
    lawd_cd: str,
    deal_ymd: str,
    page_no: int = 1,
    num_rows: int = 1000,
    property_type: str = "apartment",
) -> str:
    normalized_type = normalize_property_type(property_type)
    query = urlencode(
        {
            "serviceKey": service_key,
            "LAWD_CD": lawd_cd,
            "DEAL_YMD": deal_ymd,
            "pageNo": str(page_no),
            "numOfRows": str(num_rows),
        }
    )
    return f"{API_ENDPOINTS[normalized_type]}?{query}"


SkipLogger = Callable[[dict[str, object]], None]


def parse_apartment_trade_xml(xml_text: str, district: str, lawd_cd: str) -> list[Transaction]:
    return parse_trade_xml(xml_text, district=district, lawd_cd=lawd_cd, property_type="apartment")


def parse_trade_xml(
    xml_text: str,
    district: str,
    lawd_cd: str,
    property_type: str,
    deal_ymd: str | None = None,
    skip_logger: SkipLogger | None = None,
) -> list[Transaction]:
    normalized_type = normalize_property_type(property_type)
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise RuntimeError(f"failed to parse API XML response: {exc}") from exc

    result_code = _first_text(root, ["resultCode"])
    if result_code and result_code not in {"00", "000"}:
        message = _first_text(root, ["resultMsg"]) or "unknown API error"
        raise RuntimeError(f"data.go.kr API error {result_code}: {message}")

    transactions: list[Transaction] = []
    for item_index, item in enumerate(root.findall(".//item"), start=1):
        values = {child.tag: (child.text or "").strip() for child in list(item)}
        if not _optional_value(values, "buildYear", "건축년도"):
            _log_skipped_item(
                skip_logger,
                values=values,
                district=district,
                lawd_cd=lawd_cd,
                property_type=normalized_type,
                deal_ymd=deal_ymd,
                item_index=item_index,
                reason="missing_build_year",
            )
            continue
        transactions.append(_transaction_from_item(values, district=district, lawd_cd=lawd_cd, property_type=normalized_type))
    return transactions


def parse_total_count(xml_text: str) -> int:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return 0
    raw = _first_text(root, ["totalCount"])
    if not raw:
        return 0
    return int(raw)


def fetch_transactions_for_month(
    service_key: str,
    district: str,
    lawd_cd: str,
    deal_ymd: str,
    num_rows: int = 1000,
    property_type: str = "apartment",
    read_url: Callable[[str], str] | None = None,
    skip_logger: SkipLogger | None = None,
) -> list[Transaction]:
    normalized_type = normalize_property_type(property_type)
    reader = read_url or _read_url
    page_no = 1
    fetched: list[Transaction] = []
    total_count: int | None = None

    while True:
        url = build_request_url(
            service_key,
            lawd_cd,
            deal_ymd,
            page_no=page_no,
            num_rows=num_rows,
            property_type=normalized_type,
        )
        try:
            xml_text = reader(url)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(
                f"failed to fetch {normalized_type} trades for {district} {lawd_cd} {deal_ymd}: {exc}"
            ) from exc
        fetched.extend(
            parse_trade_xml(
                xml_text,
                district=district,
                lawd_cd=lawd_cd,
                property_type=normalized_type,
                deal_ymd=deal_ymd,
                skip_logger=skip_logger,
            )
        )
        if total_count is None:
            total_count = parse_total_count(xml_text)
        if total_count == 0 or page_no * num_rows >= total_count:
            break
        page_no += 1

    return fetched


def fetch_transactions(
    service_key: str,
    district_codes: dict[str, str],
    deal_months: list[str],
    num_rows: int = 1000,
    property_types: list[str] | None = None,
    read_url: Callable[[str], str] | None = None,
    skip_logger: SkipLogger | None = None,
) -> list[Transaction]:
    normalized_types = [normalize_property_type(value) for value in (property_types or ["apartment"])]
    rows: list[Transaction] = []
    for property_type in normalized_types:
        for district, lawd_cd in district_codes.items():
            for deal_ymd in deal_months:
                rows.extend(
                    fetch_transactions_for_month(
                        service_key=service_key,
                        district=district,
                        lawd_cd=lawd_cd,
                        deal_ymd=deal_ymd,
                        num_rows=num_rows,
                        property_type=property_type,
                        read_url=read_url,
                        skip_logger=skip_logger,
                    )
                )
    return rows


def _read_url(url: str) -> str:
    with urlopen(url, timeout=30) as response:
        return response.read().decode("utf-8")


def _first_text(root: ET.Element, tags: list[str]) -> str | None:
    for tag in tags:
        found = root.find(f".//{tag}")
        if found is not None and found.text is not None:
            text = found.text.strip()
            if text:
                return text
    return None


def _value(values: dict[str, str], *names: str) -> str:
    for name in names:
        value = values.get(name, "").strip()
        if value:
            return value
    raise ValueError(f"missing required API field: {'/'.join(names)}")


def _optional_value(values: dict[str, str], *names: str) -> str:
    for name in names:
        value = values.get(name, "").strip()
        if value:
            return value
    return ""


def _optional_float(values: dict[str, str], *names: str) -> float | None:
    value = _optional_value(values, *names)
    if not value:
        return None
    return float(value.replace(",", "").strip())


def _log_skipped_item(
    skip_logger: SkipLogger | None,
    *,
    values: dict[str, str],
    district: str,
    lawd_cd: str,
    property_type: str,
    deal_ymd: str | None,
    item_index: int,
    reason: str,
) -> None:
    if skip_logger is None:
        return

    skip_logger(
        {
            "reason": reason,
            "property_type": property_type,
            "district": district,
            "lawd_cd": lawd_cd,
            "deal_ymd": deal_ymd or _optional_deal_yyyymm(values),
            "item_index": item_index,
            "deal_year": _optional_value(values, "dealYear", "년"),
            "deal_month": _optional_value(values, "dealMonth", "월"),
            "deal_day": _optional_value(values, "dealDay", "일"),
            "legal_dong": _optional_value(values, "umdNm", "법정동").strip(),
            "building_name": _optional_value(values, *BUILDING_NAME_FIELDS[property_type]).strip(),
            "exclusive_area_m2": _optional_value(values, "excluUseAr", "전용면적"),
            "floor": _optional_value(values, "floor", "층"),
            "price_manwon": _optional_value(values, "dealAmount", "거래금액"),
        }
    )


def _optional_deal_yyyymm(values: dict[str, str]) -> str:
    year = _optional_value(values, "dealYear", "년")
    month = _optional_value(values, "dealMonth", "월")
    if not year or not month:
        return ""
    return f"{int(year):04d}{int(month):02d}"


def _transaction_from_item(values: dict[str, str], district: str, lawd_cd: str, property_type: str) -> Transaction:
    deal_year = int(_value(values, "dealYear", "년"))
    deal_month = int(_value(values, "dealMonth", "월"))
    deal_day = int(_value(values, "dealDay", "일"))
    building_name = _optional_value(values, *BUILDING_NAME_FIELDS[property_type])

    return Transaction(
        property_type=property_type,
        district=district,
        lawd_cd=lawd_cd,
        deal_year=deal_year,
        deal_month=deal_month,
        deal_day=deal_day,
        legal_dong=_value(values, "umdNm", "법정동").strip(),
        building_name=building_name,
        house_type=_optional_value(values, "houseType", "주택유형", "주택타입").strip(),
        land_area_m2=_optional_float(values, "landAr", "대지권면적", "대지면적"),
        exclusive_area_m2=float(_value(values, "excluUseAr", "전용면적")),
        floor=int(float(_value(values, "floor", "층"))),
        build_year=int(_value(values, "buildYear", "건축년도")),
        price_manwon=parse_price_manwon(_value(values, "dealAmount", "거래금액")),
    )
