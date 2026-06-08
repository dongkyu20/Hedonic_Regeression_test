SEOUL_DISTRICT_CODES: dict[str, str] = {
    "종로구": "11110",
    "중구": "11140",
    "용산구": "11170",
    "성동구": "11200",
    "광진구": "11215",
    "동대문구": "11230",
    "중랑구": "11260",
    "성북구": "11290",
    "강북구": "11305",
    "도봉구": "11320",
    "노원구": "11350",
    "은평구": "11380",
    "서대문구": "11410",
    "마포구": "11440",
    "양천구": "11470",
    "강서구": "11500",
    "구로구": "11530",
    "금천구": "11545",
    "영등포구": "11560",
    "동작구": "11590",
    "관악구": "11620",
    "서초구": "11650",
    "강남구": "11680",
    "송파구": "11710",
    "강동구": "11740",
}

BUSAN_DISTRICT_CODES: dict[str, str] = {
    "중구": "26110",
    "서구": "26140",
    "동구": "26170",
    "영도구": "26200",
    "부산진구": "26230",
    "동래구": "26260",
    "남구": "26290",
    "북구": "26320",
    "해운대구": "26350",
    "사하구": "26380",
    "금정구": "26410",
    "강서구": "26440",
    "연제구": "26470",
    "수영구": "26500",
    "사상구": "26530",
    "기장군": "26710",
}

CITY_NAMES: dict[str, str] = {
    "seoul": "서울특별시",
    "busan": "부산광역시",
}

CITY_DISTRICT_CODES: dict[str, dict[str, str]] = {
    "seoul": SEOUL_DISTRICT_CODES,
    "busan": BUSAN_DISTRICT_CODES,
}


def city_name_for_city_code(city_code: str) -> str:
    normalized = city_code.strip().lower()
    try:
        return CITY_NAMES[normalized]
    except KeyError as exc:
        raise ValueError(f"unsupported city_code: {city_code}") from exc


def district_codes_for_city(city_code: str) -> dict[str, str]:
    normalized = city_code.strip().lower()
    try:
        return CITY_DISTRICT_CODES[normalized]
    except KeyError as exc:
        raise ValueError(f"unsupported city_code: {city_code}") from exc


def city_code_for_lawd_cd(lawd_cd: str) -> str:
    normalized = lawd_cd.strip()
    for city_code, district_codes in CITY_DISTRICT_CODES.items():
        if normalized in district_codes.values():
            return city_code
    raise ValueError(f"unsupported lawd_cd: {lawd_cd}")
