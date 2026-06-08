from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .law_codes import city_code_for_lawd_cd
from .transactions import Transaction, read_transactions_csv


INSERT_TRANSACTION_SQL = """
INSERT INTO housing_transactions (
  source_system,
  source_property_type,
  source_row_hash,
  property_type,
  city_code,
  region_id,
  complex_id,
  lawd_cd,
  district_name,
  legal_dong_name,
  building_name,
  house_type,
  deal_date,
  deal_yyyymm,
  exclusive_area_m2,
  land_area_m2,
  floor,
  build_year,
  price_manwon
) VALUES (
  %(source_system)s,
  %(source_property_type)s,
  %(source_row_hash)s,
  %(property_type)s,
  %(city_code)s,
  %(region_id)s,
  %(complex_id)s,
  %(lawd_cd)s,
  %(district_name)s,
  %(legal_dong_name)s,
  %(building_name)s,
  %(house_type)s,
  %(deal_date)s,
  %(deal_yyyymm)s,
  %(exclusive_area_m2)s,
  %(land_area_m2)s,
  %(floor)s,
  %(build_year)s,
  %(price_manwon)s
)
ON DUPLICATE KEY UPDATE
  updated_at = CURRENT_TIMESTAMP
"""


def validate_transaction_city(transaction: Transaction, city_code: str) -> None:
    expected = city_code_for_lawd_cd(transaction.lawd_cd)
    normalized = city_code.strip().lower()
    if expected != normalized:
        raise ValueError(
            f"lawd_cd {transaction.lawd_cd} does not belong to city_code {city_code}"
        )


def source_row_hash(
    transaction: Transaction,
    *,
    city_code: str,
    source_system: str,
) -> str:
    parts = [
        source_system,
        city_code,
        transaction.property_type,
        transaction.lawd_cd,
        transaction.legal_dong,
        transaction.building_name,
        transaction.deal_ymd,
        f"{transaction.exclusive_area_m2:.3f}",
        str(transaction.floor),
        str(transaction.build_year),
        str(transaction.price_manwon),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def transaction_to_db_params(
    transaction: Transaction,
    *,
    city_code: str,
    region_id: int,
    complex_id: int | None,
    source_system: str = "data_go_kr",
) -> dict[str, object]:
    validate_transaction_city(transaction, city_code)
    return {
        "source_system": source_system,
        "source_property_type": transaction.property_type,
        "source_row_hash": source_row_hash(
            transaction,
            city_code=city_code,
            source_system=source_system,
        ),
        "property_type": transaction.property_type,
        "city_code": city_code.strip().lower(),
        "region_id": region_id,
        "complex_id": complex_id,
        "lawd_cd": transaction.lawd_cd,
        "district_name": transaction.district,
        "legal_dong_name": transaction.legal_dong,
        "building_name": transaction.building_name,
        "house_type": transaction.house_type,
        "deal_date": f"{transaction.deal_year:04d}-{transaction.deal_month:02d}-{transaction.deal_day:02d}",
        "deal_yyyymm": transaction.deal_yyyymm,
        "exclusive_area_m2": transaction.exclusive_area_m2,
        "land_area_m2": transaction.land_area_m2,
        "floor": transaction.floor,
        "build_year": transaction.build_year,
        "price_manwon": transaction.price_manwon,
    }


def resolve_region_id(cursor: Any, *, lawd_cd: str, city_code: str) -> int:
    cursor.execute(
        """
        SELECT region_id
        FROM administrative_regions
        WHERE lawd_cd = %s AND city_code = %s AND region_level = 'district'
        """,
        (lawd_cd, city_code),
    )
    row = cursor.fetchone()
    if not row:
        raise ValueError(f"unknown lawd_cd for city import: {city_code} {lawd_cd}")
    if isinstance(row, dict):
        return int(row["region_id"])
    return int(row[0])


def get_or_create_complex(cursor: Any, transaction: Transaction, *, region_id: int) -> int:
    cursor.execute(
        """
        SELECT complex_id
        FROM housing_complexes
        WHERE region_id = %s AND property_type = %s AND complex_name = %s
        LIMIT 1
        """,
        (region_id, transaction.property_type, transaction.building_name),
    )
    row = cursor.fetchone()
    if row:
        return int(row["complex_id"] if isinstance(row, dict) else row[0])

    cursor.execute(
        """
        INSERT INTO housing_complexes (region_id, property_type, complex_name)
        VALUES (%s, %s, %s)
        """,
        (region_id, transaction.property_type, transaction.building_name),
    )
    return int(cursor.lastrowid)


def import_transactions(
    connection: Any,
    transactions: list[Transaction],
    *,
    city_code: str,
    source_system: str = "data_go_kr",
) -> dict[str, int]:
    cursor = connection.cursor()
    attempted = 0
    try:
        for transaction in transactions:
            validate_transaction_city(transaction, city_code)
            region_id = resolve_region_id(cursor, lawd_cd=transaction.lawd_cd, city_code=city_code)
            complex_id = get_or_create_complex(cursor, transaction, region_id=region_id)
            params = transaction_to_db_params(
                transaction,
                city_code=city_code,
                region_id=region_id,
                complex_id=complex_id,
                source_system=source_system,
            )
            cursor.execute(INSERT_TRANSACTION_SQL, params)
            attempted += 1
        connection.commit()
        return {"attempted_rows": attempted}
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def import_transactions_csv(
    connection: Any,
    csv_path: str | Path,
    *,
    city_code: str,
    source_system: str = "data_go_kr",
) -> dict[str, int]:
    transactions = read_transactions_csv(csv_path)
    return import_transactions(
        connection,
        transactions,
        city_code=city_code,
        source_system=source_system,
    )
