# MySQL Housing Price Factor DB Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a MySQL backend that stores Seoul and Busan housing transactions, administrative-region codes, and four groups of price-factor snapshots, then let the existing training flow read transactions from MySQL.

**Architecture:** Keep the current CSV workflow intact and add a focused MySQL path beside it. SQL files define the schema and Seoul/Busan seed data; small Python modules handle database settings, bootstrapping, CSV import, and training-view reads. CLI commands expose database setup and import, while `train --from-db` reuses the existing `Transaction` and model pipeline.

**Tech Stack:** Python 3.9+, `unittest`, MySQL 8.0+, optional `mysql-connector-python`, existing `hedonic_house_price` package.

---

## Current Git Note

This workspace currently reports `fatal: not a git repository`. Do not add commit steps during execution unless a Git repository is initialized before implementation starts. At the end of each task, run the listed verification command and report that commits were skipped because Git is unavailable.

## File Structure

- Create `sql/mysql_schema.sql`: MySQL 8.0 DDL for administrative regions, complexes, transactions, four factor snapshot tables, and `model_training_features`.
- Create `sql/mysql_seed_regions.sql`: Seoul and Busan district seed rows with `city_code` and `city_name`.
- Modify `src/hedonic_house_price/law_codes.py`: add Busan district codes and city helpers.
- Create `src/hedonic_house_price/db.py`: database settings, lazy MySQL connector import, SQL file execution.
- Create `src/hedonic_house_price/db_import.py`: CSV-to-MySQL row mapping and import helpers.
- Create `src/hedonic_house_price/db_training.py`: read `model_training_features` rows and convert them to existing `Transaction` objects.
- Modify `src/hedonic_house_price/cli.py`: add `db-init`, `db-import-csv`, and `train --from-db` options.
- Modify `pyproject.toml`: add optional MySQL dependency metadata without forcing unit tests to import it.
- Modify `README.md`: document MySQL setup and train-from-DB usage.
- Modify `tests/test_dates_and_codes.py`: cover Seoul/Busan city code helpers.
- Create `tests/test_mysql_schema.py`: validate SQL files contain required tables, columns, indexes, and city seed rows.
- Create `tests/test_db.py`: validate DB settings and SQL splitting without a live MySQL server.
- Create `tests/test_db_import.py`: validate transaction-to-DB mapping and source row hashes.
- Create `tests/test_db_training.py`: validate model-training-view row conversion.
- Modify `tests/test_cli.py`: cover new parser options and DB training dispatch.

---

### Task 1: Add Seoul/Busan City Code Helpers

**Files:**
- Modify: `src/hedonic_house_price/law_codes.py`
- Modify: `tests/test_dates_and_codes.py`

- [ ] **Step 1: Write failing tests for Busan and city lookup**

Replace the existing `hedonic_house_price.law_codes` import in `tests/test_dates_and_codes.py` with:

```python
from hedonic_house_price.law_codes import (
    BUSAN_DISTRICT_CODES,
    CITY_DISTRICT_CODES,
    SEOUL_DISTRICT_CODES,
    city_code_for_lawd_cd,
    city_name_for_city_code,
    district_codes_for_city,
)
```

Append these methods inside the existing `DateAndCodeTests` class:

```python
    def test_busan_law_code_map_has_all_16_districts(self):
        self.assertEqual(len(BUSAN_DISTRICT_CODES), 16)
        self.assertEqual(BUSAN_DISTRICT_CODES["해운대구"], "26350")
        self.assertEqual(BUSAN_DISTRICT_CODES["기장군"], "26710")
        self.assertEqual(BUSAN_DISTRICT_CODES["중구"], "26110")

    def test_city_district_code_map_groups_seoul_and_busan(self):
        self.assertEqual(set(CITY_DISTRICT_CODES), {"seoul", "busan"})
        self.assertEqual(CITY_DISTRICT_CODES["seoul"]["강남구"], "11680")
        self.assertEqual(CITY_DISTRICT_CODES["busan"]["해운대구"], "26350")

    def test_city_code_for_lawd_cd_identifies_supported_cities(self):
        self.assertEqual(city_code_for_lawd_cd("11680"), "seoul")
        self.assertEqual(city_code_for_lawd_cd("26350"), "busan")

        with self.assertRaisesRegex(ValueError, "unsupported lawd_cd"):
            city_code_for_lawd_cd("99999")

    def test_city_name_for_city_code_returns_korean_display_name(self):
        self.assertEqual(city_name_for_city_code("seoul"), "서울특별시")
        self.assertEqual(city_name_for_city_code("busan"), "부산광역시")

        with self.assertRaisesRegex(ValueError, "unsupported city_code"):
            city_name_for_city_code("daegu")

    def test_district_codes_for_city_rejects_unknown_city(self):
        self.assertEqual(district_codes_for_city("seoul")["강남구"], "11680")
        self.assertEqual(district_codes_for_city("busan")["해운대구"], "26350")

        with self.assertRaisesRegex(ValueError, "unsupported city_code"):
            district_codes_for_city("unknown")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_dates_and_codes -v
```

Expected: FAIL because `BUSAN_DISTRICT_CODES`, `CITY_DISTRICT_CODES`, and helper functions are not defined.

- [ ] **Step 3: Implement city helpers**

Replace `src/hedonic_house_price/law_codes.py` with:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_dates_and_codes -v
```

Expected: PASS.

---

### Task 2: Add MySQL Schema And Seoul/Busan Seed SQL

**Files:**
- Create: `sql/mysql_schema.sql`
- Create: `sql/mysql_seed_regions.sql`
- Create: `tests/test_mysql_schema.py`

- [ ] **Step 1: Write failing SQL structure tests**

Create `tests/test_mysql_schema.py`:

```python
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_SQL = ROOT / "sql" / "mysql_schema.sql"
SEED_SQL = ROOT / "sql" / "mysql_seed_regions.sql"


class MysqlSchemaTests(unittest.TestCase):
    def test_schema_defines_core_tables_factor_tables_and_view(self):
        sql = SCHEMA_SQL.read_text(encoding="utf-8")

        for table_name in [
            "administrative_regions",
            "housing_complexes",
            "housing_transactions",
            "property_condition_snapshots",
            "transport_access_snapshots",
            "living_environment_snapshots",
            "urban_competitiveness_snapshots",
        ]:
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table_name}", sql)

        self.assertIn("CREATE OR REPLACE VIEW model_training_features", sql)
        self.assertIn("city_code VARCHAR(16) NOT NULL", sql)
        self.assertIn("price_krw BIGINT UNSIGNED GENERATED ALWAYS AS", sql)
        self.assertIn("CONSTRAINT fk_transactions_region", sql)
        self.assertIn("KEY idx_transactions_city_month", sql)

    def test_schema_keeps_factor_snapshots_monthly_and_source_aware(self):
        sql = SCHEMA_SQL.read_text(encoding="utf-8")

        self.assertGreaterEqual(sql.count("snapshot_yyyymm CHAR(6) NOT NULL"), 4)
        self.assertGreaterEqual(sql.count("source_name VARCHAR(100) NOT NULL"), 4)
        self.assertIn("nearest_subway_distance_m", sql)
        self.assertIn("park_area_total_m2_radius", sql)
        self.assertIn("unsold_housing_count", sql)

    def test_seed_contains_seoul_and_busan_district_rows(self):
        seed = SEED_SQL.read_text(encoding="utf-8")

        self.assertIn("'seoul', '서울특별시', '강남구', '11680'", seed)
        self.assertIn("'busan', '부산광역시', '해운대구', '26350'", seed)
        self.assertEqual(seed.count("'seoul', '서울특별시'"), 25)
        self.assertEqual(seed.count("'busan', '부산광역시'"), 16)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_mysql_schema -v
```

Expected: ERROR because `sql/mysql_schema.sql` and `sql/mysql_seed_regions.sql` do not exist.

- [ ] **Step 3: Create the schema SQL**

Create `sql/mysql_schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS administrative_regions (
  region_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  city_code VARCHAR(16) NOT NULL,
  city_name VARCHAR(32) NOT NULL,
  district_name VARCHAR(64) NULL,
  legal_dong_name VARCHAR(64) NULL,
  lawd_cd CHAR(5) NULL,
  legal_dong_cd CHAR(10) NULL,
  region_level ENUM('city', 'district', 'legal_dong') NOT NULL,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (region_id),
  UNIQUE KEY uq_administrative_regions_lawd_cd (lawd_cd),
  UNIQUE KEY uq_administrative_regions_legal_dong_cd (legal_dong_cd),
  KEY idx_administrative_regions_city (city_code),
  KEY idx_administrative_regions_district (district_name),
  KEY idx_administrative_regions_city_lawd (city_code, lawd_cd),
  CONSTRAINT chk_administrative_regions_city CHECK (city_code IN ('seoul', 'busan'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS housing_complexes (
  complex_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  region_id BIGINT UNSIGNED NOT NULL,
  property_type ENUM('apartment', 'officetel', 'rowhouse') NOT NULL,
  complex_name VARCHAR(255) NOT NULL,
  road_address VARCHAR(255) NULL,
  jibun_address VARCHAR(255) NULL,
  latitude DECIMAL(10, 7) NULL,
  longitude DECIMAL(10, 7) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (complex_id),
  KEY idx_complexes_region_type_name (region_id, property_type, complex_name),
  KEY idx_complexes_lat_lng (latitude, longitude),
  CONSTRAINT fk_complexes_region FOREIGN KEY (region_id) REFERENCES administrative_regions(region_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS housing_transactions (
  transaction_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  source_system VARCHAR(64) NOT NULL DEFAULT 'data_go_kr',
  source_property_type VARCHAR(64) NOT NULL,
  source_row_hash CHAR(64) NOT NULL,
  property_type ENUM('apartment', 'officetel', 'rowhouse') NOT NULL,
  city_code VARCHAR(16) NOT NULL,
  region_id BIGINT UNSIGNED NOT NULL,
  complex_id BIGINT UNSIGNED NULL,
  lawd_cd CHAR(5) NOT NULL,
  district_name VARCHAR(64) NOT NULL,
  legal_dong_name VARCHAR(64) NOT NULL,
  building_name VARCHAR(255) NOT NULL,
  house_type VARCHAR(64) NOT NULL DEFAULT '',
  deal_date DATE NOT NULL,
  deal_yyyymm CHAR(6) NOT NULL,
  exclusive_area_m2 DECIMAL(10, 3) NOT NULL,
  land_area_m2 DECIMAL(10, 3) NULL,
  floor INT NOT NULL,
  build_year SMALLINT UNSIGNED NOT NULL,
  price_manwon INT UNSIGNED NOT NULL,
  price_krw BIGINT UNSIGNED GENERATED ALWAYS AS (price_manwon * 10000) STORED,
  raw_payload_json JSON NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (transaction_id),
  UNIQUE KEY uq_transactions_source_hash (source_system, source_row_hash),
  KEY idx_transactions_month_type (deal_yyyymm, property_type),
  KEY idx_transactions_city_month (city_code, deal_yyyymm),
  KEY idx_transactions_region_month (region_id, deal_yyyymm),
  KEY idx_transactions_lawd_month (lawd_cd, deal_yyyymm),
  KEY idx_transactions_complex_month (complex_id, deal_yyyymm),
  CONSTRAINT chk_transactions_city CHECK (city_code IN ('seoul', 'busan')),
  CONSTRAINT fk_transactions_region FOREIGN KEY (region_id) REFERENCES administrative_regions(region_id),
  CONSTRAINT fk_transactions_complex FOREIGN KEY (complex_id) REFERENCES housing_complexes(complex_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS property_condition_snapshots (
  snapshot_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  complex_id BIGINT UNSIGNED NOT NULL,
  snapshot_yyyymm CHAR(6) NOT NULL,
  source_name VARCHAR(100) NOT NULL,
  exclusive_area_m2 DECIMAL(10, 3) NULL,
  representative_floor INT NULL,
  build_year SMALLINT UNSIGNED NULL,
  building_age_years SMALLINT UNSIGNED NULL,
  household_count INT UNSIGNED NULL,
  building_count INT UNSIGNED NULL,
  total_parking_spaces INT UNSIGNED NULL,
  parking_spaces_per_household DECIMAL(8, 3) NULL,
  has_community_facilities TINYINT(1) NULL,
  monthly_maintenance_fee_krw INT UNSIGNED NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (snapshot_id),
  UNIQUE KEY uq_property_condition_snapshot (complex_id, snapshot_yyyymm, source_name),
  KEY idx_property_condition_month (snapshot_yyyymm),
  CONSTRAINT fk_property_condition_complex FOREIGN KEY (complex_id) REFERENCES housing_complexes(complex_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS transport_access_snapshots (
  snapshot_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  region_id BIGINT UNSIGNED NULL,
  complex_id BIGINT UNSIGNED NULL,
  snapshot_yyyymm CHAR(6) NOT NULL,
  source_name VARCHAR(100) NOT NULL,
  radius_m INT UNSIGNED NOT NULL DEFAULT 1000,
  nearest_subway_distance_m DECIMAL(10, 2) NULL,
  subway_count_radius INT UNSIGNED NULL,
  nearest_bus_stop_distance_m DECIMAL(10, 2) NULL,
  bus_stop_count_radius INT UNSIGNED NULL,
  car_intercity_bus_terminal_minutes DECIMAL(8, 2) NULL,
  car_airport_minutes DECIMAL(8, 2) NULL,
  car_rail_station_minutes DECIMAL(8, 2) NULL,
  car_general_hospital_minutes DECIMAL(8, 2) NULL,
  transit_intercity_bus_terminal_minutes DECIMAL(8, 2) NULL,
  transit_airport_minutes DECIMAL(8, 2) NULL,
  transit_rail_station_minutes DECIMAL(8, 2) NULL,
  transit_general_hospital_minutes DECIMAL(8, 2) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (snapshot_id),
  UNIQUE KEY uq_transport_complex_snapshot (complex_id, snapshot_yyyymm, source_name),
  UNIQUE KEY uq_transport_region_snapshot (region_id, snapshot_yyyymm, source_name),
  KEY idx_transport_month (snapshot_yyyymm),
  CONSTRAINT chk_transport_scope CHECK (region_id IS NOT NULL OR complex_id IS NOT NULL),
  CONSTRAINT fk_transport_region FOREIGN KEY (region_id) REFERENCES administrative_regions(region_id),
  CONSTRAINT fk_transport_complex FOREIGN KEY (complex_id) REFERENCES housing_complexes(complex_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS living_environment_snapshots (
  snapshot_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  region_id BIGINT UNSIGNED NULL,
  complex_id BIGINT UNSIGNED NULL,
  snapshot_yyyymm CHAR(6) NOT NULL,
  source_name VARCHAR(100) NOT NULL,
  radius_m INT UNSIGNED NOT NULL DEFAULT 1000,
  nearest_elementary_school_distance_m DECIMAL(10, 2) NULL,
  nearest_middle_school_distance_m DECIMAL(10, 2) NULL,
  nearest_high_school_distance_m DECIMAL(10, 2) NULL,
  school_count_radius INT UNSIGNED NULL,
  academy_count_radius INT UNSIGNED NULL,
  nearest_hospital_distance_m DECIMAL(10, 2) NULL,
  nearest_pharmacy_distance_m DECIMAL(10, 2) NULL,
  nearest_park_distance_m DECIMAL(10, 2) NULL,
  park_area_total_m2_radius DECIMAL(14, 2) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (snapshot_id),
  UNIQUE KEY uq_living_complex_snapshot (complex_id, snapshot_yyyymm, source_name),
  UNIQUE KEY uq_living_region_snapshot (region_id, snapshot_yyyymm, source_name),
  KEY idx_living_month (snapshot_yyyymm),
  CONSTRAINT chk_living_scope CHECK (region_id IS NOT NULL OR complex_id IS NOT NULL),
  CONSTRAINT fk_living_region FOREIGN KEY (region_id) REFERENCES administrative_regions(region_id),
  CONSTRAINT fk_living_complex FOREIGN KEY (complex_id) REFERENCES housing_complexes(complex_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS urban_competitiveness_snapshots (
  snapshot_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  region_id BIGINT UNSIGNED NOT NULL,
  snapshot_yyyymm CHAR(6) NOT NULL,
  source_name VARCHAR(100) NOT NULL,
  population_count INT UNSIGNED NULL,
  population_growth_rate DECIMAL(8, 5) NULL,
  employment_rate DECIMAL(7, 4) NULL,
  recent_transaction_count INT UNSIGNED NULL,
  income_level_krw INT UNSIGNED NULL,
  unsold_housing_count INT UNSIGNED NULL,
  completed_housing_supply_count INT UNSIGNED NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (snapshot_id),
  UNIQUE KEY uq_urban_region_snapshot (region_id, snapshot_yyyymm, source_name),
  KEY idx_urban_month (snapshot_yyyymm),
  CONSTRAINT fk_urban_region FOREIGN KEY (region_id) REFERENCES administrative_regions(region_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE OR REPLACE VIEW model_training_features AS
SELECT
  t.transaction_id,
  t.city_code,
  r.city_name,
  t.region_id,
  t.complex_id,
  t.property_type,
  t.lawd_cd,
  t.district_name AS district,
  t.legal_dong_name AS legal_dong,
  t.building_name,
  t.house_type,
  YEAR(t.deal_date) AS deal_year,
  MONTH(t.deal_date) AS deal_month,
  DAYOFMONTH(t.deal_date) AS deal_day,
  t.deal_date,
  t.deal_yyyymm,
  t.exclusive_area_m2,
  t.land_area_m2,
  t.floor,
  t.build_year,
  t.price_manwon,
  t.price_krw,
  pcs.household_count,
  pcs.building_count,
  pcs.total_parking_spaces,
  pcs.parking_spaces_per_household,
  pcs.has_community_facilities,
  pcs.monthly_maintenance_fee_krw,
  COALESCE(tas_complex.nearest_subway_distance_m, tas_region.nearest_subway_distance_m) AS nearest_subway_distance_m,
  COALESCE(tas_complex.subway_count_radius, tas_region.subway_count_radius) AS subway_count_radius,
  COALESCE(tas_complex.nearest_bus_stop_distance_m, tas_region.nearest_bus_stop_distance_m) AS nearest_bus_stop_distance_m,
  COALESCE(tas_complex.bus_stop_count_radius, tas_region.bus_stop_count_radius) AS bus_stop_count_radius,
  COALESCE(tas_complex.car_intercity_bus_terminal_minutes, tas_region.car_intercity_bus_terminal_minutes) AS car_intercity_bus_terminal_minutes,
  COALESCE(tas_complex.car_airport_minutes, tas_region.car_airport_minutes) AS car_airport_minutes,
  COALESCE(tas_complex.car_rail_station_minutes, tas_region.car_rail_station_minutes) AS car_rail_station_minutes,
  COALESCE(tas_complex.car_general_hospital_minutes, tas_region.car_general_hospital_minutes) AS car_general_hospital_minutes,
  COALESCE(tas_complex.transit_intercity_bus_terminal_minutes, tas_region.transit_intercity_bus_terminal_minutes) AS transit_intercity_bus_terminal_minutes,
  COALESCE(tas_complex.transit_airport_minutes, tas_region.transit_airport_minutes) AS transit_airport_minutes,
  COALESCE(tas_complex.transit_rail_station_minutes, tas_region.transit_rail_station_minutes) AS transit_rail_station_minutes,
  COALESCE(tas_complex.transit_general_hospital_minutes, tas_region.transit_general_hospital_minutes) AS transit_general_hospital_minutes,
  COALESCE(les_complex.nearest_elementary_school_distance_m, les_region.nearest_elementary_school_distance_m) AS nearest_elementary_school_distance_m,
  COALESCE(les_complex.nearest_middle_school_distance_m, les_region.nearest_middle_school_distance_m) AS nearest_middle_school_distance_m,
  COALESCE(les_complex.nearest_high_school_distance_m, les_region.nearest_high_school_distance_m) AS nearest_high_school_distance_m,
  COALESCE(les_complex.school_count_radius, les_region.school_count_radius) AS school_count_radius,
  COALESCE(les_complex.academy_count_radius, les_region.academy_count_radius) AS academy_count_radius,
  COALESCE(les_complex.nearest_hospital_distance_m, les_region.nearest_hospital_distance_m) AS nearest_hospital_distance_m,
  COALESCE(les_complex.nearest_pharmacy_distance_m, les_region.nearest_pharmacy_distance_m) AS nearest_pharmacy_distance_m,
  COALESCE(les_complex.nearest_park_distance_m, les_region.nearest_park_distance_m) AS nearest_park_distance_m,
  COALESCE(les_complex.park_area_total_m2_radius, les_region.park_area_total_m2_radius) AS park_area_total_m2_radius,
  ucs.population_count,
  ucs.population_growth_rate,
  ucs.employment_rate,
  ucs.recent_transaction_count,
  ucs.income_level_krw,
  ucs.unsold_housing_count,
  ucs.completed_housing_supply_count
FROM housing_transactions t
JOIN administrative_regions r ON r.region_id = t.region_id
LEFT JOIN property_condition_snapshots pcs
  ON pcs.complex_id = t.complex_id
 AND pcs.snapshot_yyyymm = t.deal_yyyymm
LEFT JOIN transport_access_snapshots tas_complex
  ON tas_complex.complex_id = t.complex_id
 AND tas_complex.snapshot_yyyymm = t.deal_yyyymm
LEFT JOIN transport_access_snapshots tas_region
  ON tas_region.region_id = t.region_id
 AND tas_region.complex_id IS NULL
 AND tas_region.snapshot_yyyymm = t.deal_yyyymm
LEFT JOIN living_environment_snapshots les_complex
  ON les_complex.complex_id = t.complex_id
 AND les_complex.snapshot_yyyymm = t.deal_yyyymm
LEFT JOIN living_environment_snapshots les_region
  ON les_region.region_id = t.region_id
 AND les_region.complex_id IS NULL
 AND les_region.snapshot_yyyymm = t.deal_yyyymm
LEFT JOIN urban_competitiveness_snapshots ucs
  ON ucs.region_id = t.region_id
 AND ucs.snapshot_yyyymm = t.deal_yyyymm;
```

- [ ] **Step 4: Create Seoul/Busan seed SQL**

Create `sql/mysql_seed_regions.sql`:

```sql
INSERT INTO administrative_regions (
  city_code,
  city_name,
  district_name,
  lawd_cd,
  region_level,
  is_active
) VALUES
  ('seoul', '서울특별시', '종로구', '11110', 'district', 1),
  ('seoul', '서울특별시', '중구', '11140', 'district', 1),
  ('seoul', '서울특별시', '용산구', '11170', 'district', 1),
  ('seoul', '서울특별시', '성동구', '11200', 'district', 1),
  ('seoul', '서울특별시', '광진구', '11215', 'district', 1),
  ('seoul', '서울특별시', '동대문구', '11230', 'district', 1),
  ('seoul', '서울특별시', '중랑구', '11260', 'district', 1),
  ('seoul', '서울특별시', '성북구', '11290', 'district', 1),
  ('seoul', '서울특별시', '강북구', '11305', 'district', 1),
  ('seoul', '서울특별시', '도봉구', '11320', 'district', 1),
  ('seoul', '서울특별시', '노원구', '11350', 'district', 1),
  ('seoul', '서울특별시', '은평구', '11380', 'district', 1),
  ('seoul', '서울특별시', '서대문구', '11410', 'district', 1),
  ('seoul', '서울특별시', '마포구', '11440', 'district', 1),
  ('seoul', '서울특별시', '양천구', '11470', 'district', 1),
  ('seoul', '서울특별시', '강서구', '11500', 'district', 1),
  ('seoul', '서울특별시', '구로구', '11530', 'district', 1),
  ('seoul', '서울특별시', '금천구', '11545', 'district', 1),
  ('seoul', '서울특별시', '영등포구', '11560', 'district', 1),
  ('seoul', '서울특별시', '동작구', '11590', 'district', 1),
  ('seoul', '서울특별시', '관악구', '11620', 'district', 1),
  ('seoul', '서울특별시', '서초구', '11650', 'district', 1),
  ('seoul', '서울특별시', '강남구', '11680', 'district', 1),
  ('seoul', '서울특별시', '송파구', '11710', 'district', 1),
  ('seoul', '서울특별시', '강동구', '11740', 'district', 1),
  ('busan', '부산광역시', '중구', '26110', 'district', 1),
  ('busan', '부산광역시', '서구', '26140', 'district', 1),
  ('busan', '부산광역시', '동구', '26170', 'district', 1),
  ('busan', '부산광역시', '영도구', '26200', 'district', 1),
  ('busan', '부산광역시', '부산진구', '26230', 'district', 1),
  ('busan', '부산광역시', '동래구', '26260', 'district', 1),
  ('busan', '부산광역시', '남구', '26290', 'district', 1),
  ('busan', '부산광역시', '북구', '26320', 'district', 1),
  ('busan', '부산광역시', '해운대구', '26350', 'district', 1),
  ('busan', '부산광역시', '사하구', '26380', 'district', 1),
  ('busan', '부산광역시', '금정구', '26410', 'district', 1),
  ('busan', '부산광역시', '강서구', '26440', 'district', 1),
  ('busan', '부산광역시', '연제구', '26470', 'district', 1),
  ('busan', '부산광역시', '수영구', '26500', 'district', 1),
  ('busan', '부산광역시', '사상구', '26530', 'district', 1),
  ('busan', '부산광역시', '기장군', '26710', 'district', 1)
ON DUPLICATE KEY UPDATE
  city_code = VALUES(city_code),
  city_name = VALUES(city_name),
  district_name = VALUES(district_name),
  region_level = VALUES(region_level),
  is_active = VALUES(is_active);
```

- [ ] **Step 5: Run schema tests**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_mysql_schema -v
```

Expected: PASS.

---

### Task 3: Add Database Settings And SQL Bootstrap Helpers

**Files:**
- Create: `src/hedonic_house_price/db.py`
- Create: `tests/test_db.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write failing DB helper tests**

Create `tests/test_db.py`:

```python
from pathlib import Path
import tempfile
import unittest

from hedonic_house_price.db import (
    DatabaseSettings,
    load_database_settings,
    split_sql_statements,
)


class DbTests(unittest.TestCase):
    def test_load_database_settings_reads_env_values(self):
        settings = load_database_settings(
            env={
                "MYSQL_HOST": "db.local",
                "MYSQL_PORT": "3307",
                "MYSQL_USER": "tester",
                "MYSQL_PASSWORD": "secret",
                "MYSQL_DATABASE": "housing",
            },
            env_path="/private/tmp/missing_mysql_env",
        )

        self.assertEqual(
            settings,
            DatabaseSettings(
                host="db.local",
                port=3307,
                user="tester",
                password="secret",
                database="housing",
            ),
        )

    def test_load_database_settings_raises_clear_error_for_missing_values(self):
        with self.assertRaisesRegex(RuntimeError, "MYSQL_HOST, MYSQL_USER, MYSQL_DATABASE"):
            load_database_settings(env={}, env_path="/private/tmp/missing_mysql_env")

    def test_split_sql_statements_ignores_comments_and_empty_statements(self):
        statements = split_sql_statements(
            """
            -- first table
            CREATE TABLE one (id INT);

            -- second table
            CREATE TABLE two (id INT);
            """
        )

        self.assertEqual(statements, ["CREATE TABLE one (id INT)", "CREATE TABLE two (id INT)"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_db -v
```

Expected: FAIL because `hedonic_house_price.db` does not exist.

- [ ] **Step 3: Implement DB helper module**

Create `src/hedonic_house_price/db.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import load_env_file


MYSQL_ENV_KEYS = ("MYSQL_HOST", "MYSQL_USER", "MYSQL_DATABASE")


@dataclass(frozen=True)
class DatabaseSettings:
    host: str
    port: int
    user: str
    password: str
    database: str


def load_database_settings(
    env: dict[str, str] | None = None,
    env_path: str | Path = ".env",
) -> DatabaseSettings:
    merged: dict[str, str] = {}
    merged.update(load_env_file(env_path))
    if env is not None:
        merged.update(env)

    missing = [key for key in MYSQL_ENV_KEYS if not merged.get(key, "").strip()]
    if missing:
        raise RuntimeError(f"{', '.join(missing)} are required for MySQL access")

    return DatabaseSettings(
        host=merged["MYSQL_HOST"].strip(),
        port=int(merged.get("MYSQL_PORT", "3306")),
        user=merged["MYSQL_USER"].strip(),
        password=merged.get("MYSQL_PASSWORD", ""),
        database=merged["MYSQL_DATABASE"].strip(),
    )


def get_mysql_connection(settings: DatabaseSettings | None = None) -> Any:
    if settings is None:
        settings = load_database_settings()
    try:
        import mysql.connector
    except ImportError as exc:
        raise RuntimeError("mysql-connector-python is required for MySQL commands") from exc

    return mysql.connector.connect(
        host=settings.host,
        port=settings.port,
        user=settings.user,
        password=settings.password,
        database=settings.database,
        autocommit=False,
    )


def split_sql_statements(sql: str) -> list[str]:
    cleaned_lines: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines)
    return [statement.strip() for statement in cleaned.split(";") if statement.strip()]


def execute_sql_file(connection: Any, path: str | Path) -> int:
    sql = Path(path).read_text(encoding="utf-8")
    statements = split_sql_statements(sql)
    cursor = connection.cursor()
    try:
        for statement in statements:
            cursor.execute(statement)
        connection.commit()
        return len(statements)
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def bootstrap_database(
    connection: Any,
    schema_path: str | Path = "sql/mysql_schema.sql",
    seed_path: str | Path = "sql/mysql_seed_regions.sql",
    include_seed: bool = True,
) -> dict[str, int]:
    schema_count = execute_sql_file(connection, schema_path)
    seed_count = execute_sql_file(connection, seed_path) if include_seed else 0
    return {
        "schema_statements": schema_count,
        "seed_statements": seed_count,
    }
```

- [ ] **Step 4: Add optional MySQL dependency metadata**

Modify `pyproject.toml` by adding this section after `[project]` dependencies:

```toml
[project.optional-dependencies]
mysql = [
    "mysql-connector-python>=9.0,<10",
]
```

- [ ] **Step 5: Run DB helper tests**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_db -v
```

Expected: PASS.

---

### Task 4: Add CSV-To-MySQL Import Mapping

**Files:**
- Create: `src/hedonic_house_price/db_import.py`
- Create: `tests/test_db_import.py`

- [ ] **Step 1: Write failing import mapping tests**

Create `tests/test_db_import.py`:

```python
import unittest

from hedonic_house_price.db_import import (
    source_row_hash,
    transaction_to_db_params,
    validate_transaction_city,
)
from hedonic_house_price.transactions import Transaction


def sample_transaction():
    return Transaction(
        district="강남구",
        lawd_cd="11680",
        deal_year=2025,
        deal_month=6,
        deal_day=11,
        legal_dong="역삼동",
        building_name="테스트아파트",
        property_type="apartment",
        exclusive_area_m2=84.95,
        floor=14,
        build_year=2005,
        price_manwon=84500,
    )


class DbImportTests(unittest.TestCase):
    def test_validate_transaction_city_accepts_matching_lawd_prefix(self):
        validate_transaction_city(sample_transaction(), "seoul")

        busan = Transaction(
            district="해운대구",
            lawd_cd="26350",
            deal_year=2025,
            deal_month=6,
            deal_day=11,
            legal_dong="우동",
            building_name="부산테스트",
            property_type="apartment",
            exclusive_area_m2=84.95,
            floor=14,
            build_year=2005,
            price_manwon=84500,
        )
        validate_transaction_city(busan, "busan")

    def test_validate_transaction_city_rejects_mismatched_city(self):
        with self.assertRaisesRegex(ValueError, "does not belong to city_code"):
            validate_transaction_city(sample_transaction(), "busan")

    def test_source_row_hash_is_stable_for_same_transaction(self):
        tx = sample_transaction()

        first = source_row_hash(tx, city_code="seoul", source_system="data_go_kr")
        second = source_row_hash(tx, city_code="seoul", source_system="data_go_kr")

        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_transaction_to_db_params_preserves_csv_values(self):
        params = transaction_to_db_params(
            sample_transaction(),
            city_code="seoul",
            region_id=123,
            complex_id=456,
            source_system="data_go_kr",
        )

        self.assertEqual(params["source_system"], "data_go_kr")
        self.assertEqual(params["source_property_type"], "apartment")
        self.assertEqual(params["property_type"], "apartment")
        self.assertEqual(params["city_code"], "seoul")
        self.assertEqual(params["region_id"], 123)
        self.assertEqual(params["complex_id"], 456)
        self.assertEqual(params["lawd_cd"], "11680")
        self.assertEqual(params["district_name"], "강남구")
        self.assertEqual(params["legal_dong_name"], "역삼동")
        self.assertEqual(params["building_name"], "테스트아파트")
        self.assertEqual(params["deal_date"], "2025-06-11")
        self.assertEqual(params["deal_yyyymm"], "202506")
        self.assertEqual(params["exclusive_area_m2"], 84.95)
        self.assertEqual(params["floor"], 14)
        self.assertEqual(params["build_year"], 2005)
        self.assertEqual(params["price_manwon"], 84500)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_db_import -v
```

Expected: FAIL because `hedonic_house_price.db_import` does not exist.

- [ ] **Step 3: Implement import mapping and import helpers**

Create `src/hedonic_house_price/db_import.py`:

```python
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
```

- [ ] **Step 4: Run import tests**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_db_import -v
```

Expected: PASS.

---

### Task 5: Add Training-View Reader

**Files:**
- Create: `src/hedonic_house_price/db_training.py`
- Create: `tests/test_db_training.py`

- [ ] **Step 1: Write failing DB training tests**

Create `tests/test_db_training.py`:

```python
import unittest

from hedonic_house_price.db_training import training_view_row_to_transaction


class DbTrainingTests(unittest.TestCase):
    def test_training_view_row_to_transaction_preserves_model_fields(self):
        tx = training_view_row_to_transaction(
            {
                "property_type": "rowhouse",
                "district": "강남구",
                "lawd_cd": "11680",
                "deal_year": 2025,
                "deal_month": 6,
                "deal_day": 11,
                "legal_dong": "역삼동",
                "building_name": "테스트빌라",
                "house_type": "다세대",
                "land_area_m2": 18.2,
                "exclusive_area_m2": 84.95,
                "floor": 14,
                "build_year": 2005,
                "price_manwon": 84500,
            }
        )

        self.assertEqual(tx.property_type, "rowhouse")
        self.assertEqual(tx.district, "강남구")
        self.assertEqual(tx.lawd_cd, "11680")
        self.assertEqual(tx.deal_yyyymm, "202506")
        self.assertEqual(tx.legal_dong, "역삼동")
        self.assertEqual(tx.building_name, "테스트빌라")
        self.assertEqual(tx.house_type, "다세대")
        self.assertEqual(tx.land_area_m2, 18.2)
        self.assertEqual(tx.exclusive_area_m2, 84.95)
        self.assertEqual(tx.price_krw, 845_000_000)

    def test_training_view_row_to_transaction_raises_for_missing_required_column(self):
        with self.assertRaisesRegex(ValueError, "missing training view column"):
            training_view_row_to_transaction({"district": "강남구"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_db_training -v
```

Expected: FAIL because `hedonic_house_price.db_training` does not exist.

- [ ] **Step 3: Implement DB training reader**

Create `src/hedonic_house_price/db_training.py`:

```python
from __future__ import annotations

from typing import Any

from .transactions import Transaction


TRAINING_VIEW_COLUMNS = [
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


def training_view_row_to_transaction(row: dict[str, Any]) -> Transaction:
    missing = [column for column in TRAINING_VIEW_COLUMNS if column not in row]
    if missing:
        raise ValueError(f"missing training view column: {missing[0]}")

    return Transaction(
        property_type=str(row["property_type"]),
        district=str(row["district"]),
        lawd_cd=str(row["lawd_cd"]),
        deal_year=int(row["deal_year"]),
        deal_month=int(row["deal_month"]),
        deal_day=int(row["deal_day"]),
        legal_dong=str(row["legal_dong"]),
        building_name=str(row["building_name"] or ""),
        house_type=str(row["house_type"] or ""),
        land_area_m2=_optional_float(row["land_area_m2"]),
        exclusive_area_m2=float(row["exclusive_area_m2"]),
        floor=int(row["floor"]),
        build_year=int(row["build_year"]),
        price_manwon=int(row["price_manwon"]),
    )


def read_transactions_from_training_view(
    connection: Any,
    *,
    city_code: str | None = None,
    property_types: list[str] | None = None,
) -> list[Transaction]:
    where_parts: list[str] = []
    params: list[object] = []
    if city_code:
        where_parts.append("city_code = %s")
        params.append(city_code.strip().lower())
    if property_types:
        placeholders = ", ".join(["%s"] * len(property_types))
        where_parts.append(f"property_type IN ({placeholders})")
        params.extend(property_types)

    where_sql = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""
    query = f"""
        SELECT {', '.join(TRAINING_VIEW_COLUMNS)}
        FROM model_training_features
        {where_sql}
        ORDER BY deal_date, transaction_id
    """

    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
    finally:
        cursor.close()

    return [training_view_row_to_transaction(row) for row in rows]


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return float(text)
```

- [ ] **Step 4: Run DB training tests**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_db_training -v
```

Expected: PASS.

---

### Task 6: Wire MySQL Commands Into The CLI

**Files:**
- Modify: `src/hedonic_house_price/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI parser and dispatch tests**

Add tests to `tests/test_cli.py`:

```python
    def test_db_init_command_parses_schema_and_seed_options(self):
        args = build_parser().parse_args(
            [
                "db-init",
                "--schema",
                "sql/mysql_schema.sql",
                "--seed",
                "sql/mysql_seed_regions.sql",
                "--skip-seed",
            ]
        )

        self.assertEqual(args.command, "db-init")
        self.assertEqual(args.schema, "sql/mysql_schema.sql")
        self.assertEqual(args.seed, "sql/mysql_seed_regions.sql")
        self.assertTrue(args.skip_seed)

    def test_db_import_csv_command_parses_city_and_input(self):
        args = build_parser().parse_args(
            [
                "db-import-csv",
                "--input",
                "data/seoul_apartment_trades.csv",
                "--city-code",
                "seoul",
            ]
        )

        self.assertEqual(args.command, "db-import-csv")
        self.assertEqual(args.input, "data/seoul_apartment_trades.csv")
        self.assertEqual(args.city_code, "seoul")

    def test_train_command_parses_db_training_options(self):
        args = build_parser().parse_args(
            [
                "train",
                "--from-db",
                "--city-code",
                "busan",
                "--property-types",
                "apartment,rowhouse",
            ]
        )

        self.assertTrue(args.from_db)
        self.assertEqual(args.city_code, "busan")
        self.assertEqual(args.property_types, "apartment,rowhouse")

    def test_train_from_db_uses_training_view_reader(self):
        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as model_file:
            model_path = model_file.name

        stderr = io.StringIO()
        stdout = io.StringIO()
        try:
            with (
                patch("hedonic_house_price.cli.get_mysql_connection", return_value=object()),
                patch("hedonic_house_price.cli.read_transactions_from_training_view", return_value=sample_transactions()),
                redirect_stderr(stderr),
                redirect_stdout(stdout),
            ):
                exit_code = main(
                    [
                        "train",
                        "--from-db",
                        "--city-code",
                        "seoul",
                        "--model-output",
                        model_path,
                        "--alpha",
                        "0.1",
                        "--min-apartment-count",
                        "2",
                        "--validation-months",
                        "2",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("[train] DB 로드 시작", stderr.getvalue())
            self.assertIn("[train] DB 로드 완료", stderr.getvalue())
            self.assertIn('"model_output"', stdout.getvalue())
        finally:
            os.unlink(model_path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_cli -v
```

Expected: FAIL because new CLI commands and `train --from-db` do not exist.

- [ ] **Step 3: Modify CLI imports**

In `src/hedonic_house_price/cli.py`, add:

```python
from .db import bootstrap_database, get_mysql_connection
from .db_import import import_transactions_csv
from .db_training import read_transactions_from_training_view
```

- [ ] **Step 4: Add parser options**

In `build_parser()`, after `train_parser.add_argument("--validation-months", type=int, default=6)`, add:

```python
    train_parser.add_argument("--from-db", action="store_true", help="Train from MySQL model_training_features instead of CSV.")
    train_parser.add_argument("--city-code", choices=["seoul", "busan"], default=None, help="Filter DB training rows by city.")
    train_parser.add_argument(
        "--property-types",
        default=None,
        help="Comma-separated DB training property types. Defaults to all property types.",
    )
```

After the `gui` parser block, add:

```python
    db_init_parser = subparsers.add_parser("db-init", help="Create MySQL schema and seed administrative regions.")
    db_init_parser.add_argument("--schema", default="sql/mysql_schema.sql")
    db_init_parser.add_argument("--seed", default="sql/mysql_seed_regions.sql")
    db_init_parser.add_argument("--skip-seed", action="store_true")

    db_import_parser = subparsers.add_parser("db-import-csv", help="Import a transaction CSV into MySQL.")
    db_import_parser.add_argument("--input", required=True)
    db_import_parser.add_argument("--city-code", required=True, choices=["seoul", "busan"])
```

- [ ] **Step 5: Add command dispatch**

In `main()`, before the final `parser.error`, add:

```python
    if args.command == "db-init":
        return _handle_db_init(args)
    if args.command == "db-import-csv":
        return _handle_db_import_csv(args)
```

- [ ] **Step 6: Implement DB handlers and train branch**

Replace `_handle_train()` with:

```python
def _handle_train(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    if args.from_db:
        _print_train_progress("DB 로드 시작", city_code=args.city_code or "all")
        connection = get_mysql_connection()
        property_types = _parse_property_types(args.property_types) if args.property_types else None
        transactions = read_transactions_from_training_view(
            connection,
            city_code=args.city_code,
            property_types=property_types,
        )
        _print_train_progress("DB 로드 완료", rows=len(transactions), elapsed_s=_elapsed(started))
    else:
        _print_train_progress("CSV 로드 시작", input=args.input)
        transactions = read_transactions_csv(args.input)
        _print_train_progress("CSV 로드 완료", rows=len(transactions), elapsed_s=_elapsed(started))

    model = train_hedonic_model(
        transactions,
        alpha=args.alpha,
        min_apartment_count=args.min_apartment_count,
        validation_months=args.validation_months,
        progress=lambda event: _print_model_progress(event, started),
    )
    _print_train_progress("모델 저장 시작", output=args.model_output, elapsed_s=_elapsed(started))
    save_model(model, args.model_output)
    _print_train_progress("모델 저장 완료", output=args.model_output, elapsed_s=_elapsed(started))

    print(
        json.dumps(
            {
                "model_output": args.model_output,
                "training_rows": model.training_rows,
                "validation_rows": model.validation_rows,
                "metrics": model.metrics,
                "residuals_by_floor_band": model.residuals_by_floor_band,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0
```

Add these functions near `_handle_gui()`:

```python
def _handle_db_init(args: argparse.Namespace) -> int:
    connection = get_mysql_connection()
    result = bootstrap_database(
        connection,
        schema_path=args.schema,
        seed_path=args.seed,
        include_seed=not args.skip_seed,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _handle_db_import_csv(args: argparse.Namespace) -> int:
    connection = get_mysql_connection()
    result = import_transactions_csv(
        connection,
        args.input,
        city_code=args.city_code,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
```

- [ ] **Step 7: Run CLI tests**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_cli -v
```

Expected: PASS.

---

### Task 7: Update README With MySQL Workflow

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add MySQL documentation**

Add this section before `## 검증`:

```markdown
## MySQL 데이터베이스 사용

CSV 흐름은 그대로 유지하면서 MySQL을 구조화된 저장소로 사용할 수 있습니다. MySQL 기능은 선택 사항이며, 사용하려면 MySQL 커넥터 의존성을 설치합니다.

```bash
python3 -m pip install -e ".[mysql]"
```

`.env` 또는 환경변수에 MySQL 접속 정보를 설정합니다.

```bash
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=your_user
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=hedonic_house_price
```

스키마와 서울/부산 행정구역 seed를 생성합니다.

```bash
PYTHONPATH=src python3 -m hedonic_house_price db-init
```

기존 서울 CSV를 MySQL로 적재합니다.

```bash
PYTHONPATH=src python3 -m hedonic_house_price db-import-csv \
  --input data/seoul_apartment_trades.csv \
  --city-code seoul
```

부산 CSV가 준비되면 같은 스키마에 `city-code busan`으로 적재합니다.

```bash
PYTHONPATH=src python3 -m hedonic_house_price db-import-csv \
  --input data/busan_apartment_trades.csv \
  --city-code busan
```

MySQL의 `model_training_features` 뷰에서 거래를 읽어 학습하려면 `train --from-db`를 사용합니다.

```bash
PYTHONPATH=src python3 -m hedonic_house_price train \
  --from-db \
  --city-code seoul \
  --model-output artifacts/hedonic_mysql_seoul_model.pkl
```

`housing_transactions.city_code`와 `administrative_regions.city_code`는 `seoul` 또는 `busan` 값으로 서울/부산 여부를 명확히 구분합니다. 교통, 생활·교육·자연환경, 도시 경쟁력 값은 각 snapshot 테이블에 월 단위로 적재하면 `model_training_features` 뷰에서 거래 월과 정확히 일치하는 값만 조인됩니다.
```

- [ ] **Step 2: Verify README mentions new commands**

Run:

```bash
rg -n "db-init|db-import-csv|train --from-db|city-code busan" README.md
```

Expected: all four patterns appear.

---

### Task 8: Run Full Verification

**Files:**
- No edits.

- [ ] **Step 1: Run all unit tests**

Run:

```bash
PYTHONPATH=src python3 -m unittest discover -v
```

Expected: PASS.

- [ ] **Step 2: Verify SQL and docs files exist**

Run:

```bash
ls sql/mysql_schema.sql sql/mysql_seed_regions.sql docs/superpowers/specs/2026-06-08-mysql-housing-price-factor-db-design.md docs/superpowers/plans/2026-06-08-mysql-housing-price-factor-db.md
```

Expected: all four paths are printed.

- [ ] **Step 3: Verify Git status or report unavailable Git**

Run:

```bash
git status --short
```

Expected in current workspace: `fatal: not a git repository (or any of the parent directories): .git`. Report this in the final implementation summary and do not attempt commit commands.
