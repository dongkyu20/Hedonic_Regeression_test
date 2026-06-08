from __future__ import annotations

from typing import Any


CLEAR_DATA_TABLES = [
    "property_condition_snapshots",
    "transport_access_snapshots",
    "living_environment_snapshots",
    "urban_competitiveness_snapshots",
    "housing_transactions",
    "housing_complexes",
]

PROPERTY_CONDITION_DERIVED_SQL = """
INSERT INTO property_condition_snapshots (
  complex_id,
  snapshot_yyyymm,
  source_name,
  exclusive_area_m2,
  representative_floor,
  build_year,
  building_age_years
)
SELECT
  complex_id,
  deal_yyyymm,
  'transactions_derived',
  ROUND(AVG(exclusive_area_m2), 3),
  ROUND(AVG(floor)),
  MIN(build_year),
  GREATEST(0, CAST(LEFT(deal_yyyymm, 4) AS SIGNED) - CAST(MIN(build_year) AS SIGNED))
FROM housing_transactions
WHERE complex_id IS NOT NULL
GROUP BY complex_id, deal_yyyymm
ON DUPLICATE KEY UPDATE
  exclusive_area_m2 = VALUES(exclusive_area_m2),
  representative_floor = VALUES(representative_floor),
  build_year = VALUES(build_year),
  building_age_years = VALUES(building_age_years),
  updated_at = CURRENT_TIMESTAMP
"""

URBAN_COMPETITIVENESS_DERIVED_SQL = """
INSERT INTO urban_competitiveness_snapshots (
  region_id,
  snapshot_yyyymm,
  source_name,
  recent_transaction_count
)
SELECT
  region_id,
  deal_yyyymm,
  'transactions_derived',
  COUNT(*)
FROM housing_transactions
GROUP BY region_id, deal_yyyymm
ON DUPLICATE KEY UPDATE
  recent_transaction_count = VALUES(recent_transaction_count),
  updated_at = CURRENT_TIMESTAMP
"""


def clear_transaction_data(connection: Any) -> dict[str, int]:
    cursor = connection.cursor()
    try:
        for table_name in CLEAR_DATA_TABLES:
            cursor.execute(f"DELETE FROM {table_name}")
            cursor.execute(f"ALTER TABLE {table_name} AUTO_INCREMENT = 1")
        connection.commit()
        return {"cleared_tables": len(CLEAR_DATA_TABLES)}
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def refresh_transaction_derived_snapshots(connection: Any) -> dict[str, int]:
    cursor = connection.cursor()
    try:
        cursor.execute("DELETE FROM property_condition_snapshots WHERE source_name = 'transactions_derived'")
        cursor.execute("DELETE FROM urban_competitiveness_snapshots WHERE source_name = 'transactions_derived'")
        cursor.execute(PROPERTY_CONDITION_DERIVED_SQL)
        property_condition_rows = cursor.rowcount
        cursor.execute(URBAN_COMPETITIVENESS_DERIVED_SQL)
        urban_competitiveness_rows = cursor.rowcount
        connection.commit()
        return {
            "property_condition_rows": property_condition_rows,
            "urban_competitiveness_rows": urban_competitiveness_rows,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
