from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


CSV_FIELDS = [
    "property_type",
    "district",
    "lawd_cd",
    "deal_year",
    "deal_month",
    "deal_day",
    "legal_dong",
    "building_name",
    "house_type",
    "land_area_m2",
    "exclusive_area_m2",
    "floor",
    "build_year",
    "price_manwon",
]


@dataclass(frozen=True, init=False)
class Transaction:
    property_type: str
    district: str
    lawd_cd: str
    deal_year: int
    deal_month: int
    deal_day: int
    legal_dong: str
    building_name: str
    house_type: str
    land_area_m2: float | None
    exclusive_area_m2: float
    floor: int
    build_year: int
    price_manwon: int

    def __init__(
        self,
        *,
        district: str,
        lawd_cd: str,
        deal_year: int,
        deal_month: int,
        deal_day: int,
        legal_dong: str,
        exclusive_area_m2: float,
        floor: int,
        build_year: int,
        price_manwon: int,
        property_type: str = "apartment",
        building_name: str = "",
        apartment_name: str = "",
        house_type: str = "",
        land_area_m2: float | None = None,
    ) -> None:
        normalized_type = normalize_property_type(property_type)
        normalized_name = (building_name or apartment_name or "").strip()
        object.__setattr__(self, "property_type", normalized_type)
        object.__setattr__(self, "district", district.strip())
        object.__setattr__(self, "lawd_cd", lawd_cd.strip())
        object.__setattr__(self, "deal_year", int(deal_year))
        object.__setattr__(self, "deal_month", int(deal_month))
        object.__setattr__(self, "deal_day", int(deal_day))
        object.__setattr__(self, "legal_dong", legal_dong.strip())
        object.__setattr__(self, "building_name", normalized_name)
        object.__setattr__(self, "house_type", house_type.strip())
        object.__setattr__(self, "land_area_m2", land_area_m2)
        object.__setattr__(self, "exclusive_area_m2", float(exclusive_area_m2))
        object.__setattr__(self, "floor", int(floor))
        object.__setattr__(self, "build_year", int(build_year))
        object.__setattr__(self, "price_manwon", int(price_manwon))

    @property
    def apartment_name(self) -> str:
        return self.building_name

    @property
    def price_krw(self) -> int:
        return self.price_manwon * 10_000

    @property
    def deal_ymd(self) -> str:
        return f"{self.deal_year:04d}{self.deal_month:02d}{self.deal_day:02d}"

    @property
    def deal_yyyymm(self) -> str:
        return f"{self.deal_year:04d}{self.deal_month:02d}"

    def to_row(self) -> dict[str, str]:
        return {
            "property_type": self.property_type,
            "district": self.district,
            "lawd_cd": self.lawd_cd,
            "deal_year": str(self.deal_year),
            "deal_month": str(self.deal_month),
            "deal_day": str(self.deal_day),
            "legal_dong": self.legal_dong,
            "building_name": self.building_name,
            "house_type": self.house_type,
            "land_area_m2": "" if self.land_area_m2 is None else str(self.land_area_m2),
            "exclusive_area_m2": str(self.exclusive_area_m2),
            "floor": str(self.floor),
            "build_year": str(self.build_year),
            "price_manwon": str(self.price_manwon),
        }


def parse_price_manwon(value: str) -> int:
    normalized = value.replace(",", "").replace(" ", "").strip()
    if not normalized:
        raise ValueError("transaction price is empty")
    return int(normalized)


def normalize_property_type(value: str) -> str:
    normalized = value.strip().lower()
    aliases = {
        "apt": "apartment",
        "apartment": "apartment",
        "아파트": "apartment",
        "offi": "officetel",
        "officetel": "officetel",
        "오피스텔": "officetel",
        "rh": "rowhouse",
        "rowhouse": "rowhouse",
        "villa": "rowhouse",
        "연립": "rowhouse",
        "다세대": "rowhouse",
        "연립다세대": "rowhouse",
        "연립·다세대": "rowhouse",
    }
    if normalized in aliases:
        return aliases[normalized]
    raise ValueError(f"unsupported property_type: {value}")


def transaction_from_row(row: dict[str, str]) -> Transaction:
    return Transaction(
        property_type=normalize_property_type(row.get("property_type", "apartment") or "apartment"),
        district=row["district"].strip(),
        lawd_cd=row["lawd_cd"].strip(),
        deal_year=int(row["deal_year"]),
        deal_month=int(row["deal_month"]),
        deal_day=int(row["deal_day"]),
        legal_dong=row["legal_dong"].strip(),
        building_name=(row.get("building_name") or row.get("apartment_name") or "").strip(),
        house_type=(row.get("house_type") or "").strip(),
        land_area_m2=_optional_float(row.get("land_area_m2")),
        exclusive_area_m2=float(row["exclusive_area_m2"]),
        floor=int(float(row["floor"])),
        build_year=int(row["build_year"]),
        price_manwon=parse_price_manwon(row["price_manwon"]),
    )


def _optional_float(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return float(text)


def write_transactions_csv(transactions: list[Transaction], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for transaction in transactions:
            writer.writerow(transaction.to_row())


def read_transactions_csv(path: str | Path) -> list[Transaction]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [transaction_from_row(row) for row in reader]
