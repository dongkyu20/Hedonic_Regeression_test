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
  road_address VARCHAR(512) NULL,
  jibun_address VARCHAR(512) NULL,
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
  COALESCE(pcs_kapt.household_count, pcs_tx.household_count) AS household_count,
  COALESCE(pcs_kapt.building_count, pcs_tx.building_count) AS building_count,
  COALESCE(pcs_kapt.total_parking_spaces, pcs_tx.total_parking_spaces) AS total_parking_spaces,
  COALESCE(pcs_kapt.parking_spaces_per_household, pcs_tx.parking_spaces_per_household) AS parking_spaces_per_household,
  COALESCE(pcs_kapt.has_community_facilities, pcs_tx.has_community_facilities) AS has_community_facilities,
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
  COALESCE(les_school_complex.nearest_elementary_school_distance_m, les_school_region.nearest_elementary_school_distance_m) AS nearest_elementary_school_distance_m,
  COALESCE(les_school_complex.nearest_middle_school_distance_m, les_school_region.nearest_middle_school_distance_m) AS nearest_middle_school_distance_m,
  COALESCE(les_school_complex.school_count_radius, les_school_region.school_count_radius) AS school_count_radius,
  COALESCE(les_academy_complex.academy_count_radius, les_academy_region.academy_count_radius) AS academy_count_radius,
  COALESCE(les_healthcare_complex.nearest_hospital_distance_m, les_healthcare_region.nearest_hospital_distance_m) AS nearest_hospital_distance_m,
  COALESCE(les_healthcare_complex.nearest_pharmacy_distance_m, les_healthcare_region.nearest_pharmacy_distance_m) AS nearest_pharmacy_distance_m,
  COALESCE(les_park_complex.nearest_park_distance_m, les_park_region.nearest_park_distance_m) AS nearest_park_distance_m,
  COALESCE(les_park_complex.park_area_total_m2_radius, les_park_region.park_area_total_m2_radius) AS park_area_total_m2_radius,
  ucs.population_count,
  ucs.population_growth_rate,
  ucs.employment_rate,
  ucs.recent_transaction_count,
  ucs.income_level_krw,
  ucs.unsold_housing_count,
  ucs.completed_housing_supply_count
FROM housing_transactions t
JOIN administrative_regions r ON r.region_id = t.region_id
LEFT JOIN property_condition_snapshots pcs_tx
  ON pcs_tx.complex_id = t.complex_id
 AND pcs_tx.snapshot_yyyymm = t.deal_yyyymm
 AND pcs_tx.source_name = 'transactions_derived'
LEFT JOIN property_condition_snapshots pcs_kapt
  ON pcs_kapt.complex_id = t.complex_id
 AND pcs_kapt.snapshot_yyyymm = t.deal_yyyymm
 AND pcs_kapt.source_name = 'kapt_basic_info'
LEFT JOIN transport_access_snapshots tas_complex
  ON tas_complex.complex_id = t.complex_id
 AND tas_complex.snapshot_yyyymm = t.deal_yyyymm
LEFT JOIN transport_access_snapshots tas_region
  ON tas_region.region_id = t.region_id
 AND tas_region.complex_id IS NULL
 AND tas_region.snapshot_yyyymm = t.deal_yyyymm
LEFT JOIN living_environment_snapshots les_school_complex
  ON les_school_complex.complex_id = t.complex_id
 AND les_school_complex.snapshot_yyyymm = t.deal_yyyymm
 AND les_school_complex.source_name = 'school_location'
LEFT JOIN living_environment_snapshots les_school_region
  ON les_school_region.region_id = t.region_id
 AND les_school_region.complex_id IS NULL
 AND les_school_region.snapshot_yyyymm = t.deal_yyyymm
 AND les_school_region.source_name = 'school_location'
LEFT JOIN living_environment_snapshots les_academy_complex
  ON les_academy_complex.complex_id = t.complex_id
 AND les_academy_complex.snapshot_yyyymm = t.deal_yyyymm
 AND les_academy_complex.source_name = 'academy_nearby_complex_2604'
LEFT JOIN living_environment_snapshots les_academy_region
  ON les_academy_region.region_id = t.region_id
 AND les_academy_region.complex_id IS NULL
 AND les_academy_region.snapshot_yyyymm = t.deal_yyyymm
 AND les_academy_region.source_name = 'academy_nearby_complex_2604'
LEFT JOIN living_environment_snapshots les_healthcare_complex
  ON les_healthcare_complex.complex_id = t.complex_id
 AND les_healthcare_complex.snapshot_yyyymm = t.deal_yyyymm
 AND les_healthcare_complex.source_name = 'healthcare_facility'
LEFT JOIN living_environment_snapshots les_healthcare_region
  ON les_healthcare_region.region_id = t.region_id
 AND les_healthcare_region.complex_id IS NULL
 AND les_healthcare_region.snapshot_yyyymm = t.deal_yyyymm
 AND les_healthcare_region.source_name = 'healthcare_facility'
LEFT JOIN living_environment_snapshots les_park_complex
  ON les_park_complex.complex_id = t.complex_id
 AND les_park_complex.snapshot_yyyymm = t.deal_yyyymm
 AND les_park_complex.source_name = 'park_standard_data'
LEFT JOIN living_environment_snapshots les_park_region
  ON les_park_region.region_id = t.region_id
 AND les_park_region.complex_id IS NULL
 AND les_park_region.snapshot_yyyymm = t.deal_yyyymm
 AND les_park_region.source_name = 'park_standard_data'
LEFT JOIN urban_competitiveness_snapshots ucs
  ON ucs.region_id = t.region_id
 AND ucs.snapshot_yyyymm = t.deal_yyyymm;
