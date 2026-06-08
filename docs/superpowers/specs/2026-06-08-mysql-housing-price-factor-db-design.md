# MySQL Housing Price Factor Database Design

## Goal

Build a MySQL database foundation for the hedonic house price project so Seoul and Busan housing transactions can be stored with administrative region codes and joined to four price-factor groups:

- Property condition
- Transport accessibility
- Living, education, and natural environment
- Urban competitiveness

The database will support two near-term workflows:

- Persist public transaction data that is currently cached in CSV files.
- Produce a model-training feature table or view that can replace or supplement the current CSV input.

## Scope

This design covers the database schema, core indexes, seed data strategy, and integration points for the existing Python package.

The first implementation will target MySQL 8.0 or later. It will create executable SQL files and focused Python integration code after this design is approved.

## City And Region Model

The project will handle Seoul and Busan together. Every administrative-region row and transaction row stores a city classifier so queries can filter or train by city without parsing code prefixes.

Use these city fields:

- `city_code`: stable lowercase code, either `seoul` or `busan`
- `city_name`: display name, either `서울특별시` or `부산광역시`

Use administrative region codes as the main join key:

- `lawd_cd`: district-level 5-digit legal-dong code, matching the existing public transaction API usage
- `legal_dong_cd`: optional full 10-digit legal-dong code when source data provides it
- `region_level`: `city`, `district`, or `legal_dong`

The initial seed will include district-level rows for Seoul and Busan. Legal-dong rows are compatible with the same table shape and can be inserted as source data becomes available.

## Core Tables

### `administrative_regions`

Stores city, district, and optional legal-dong metadata.

Important columns:

- `region_id`
- `city_code`
- `city_name`
- `district_name`
- `legal_dong_name`
- `lawd_cd`
- `legal_dong_cd`
- `region_level`
- `is_active`

Constraints:

- Unique `lawd_cd`, `legal_dong_cd` where available
- Indexes on `city_code`, `district_name`, and `(city_code, lawd_cd)`

### `housing_complexes`

Stores building or complex identity. A complex is connected to an administrative region, but the schema does not require perfect complex master data before transactions can be stored.

Important columns:

- `complex_id`
- `region_id`
- `property_type`: `apartment`, `officetel`, or `rowhouse`
- `complex_name`
- `road_address`
- `jibun_address`
- `latitude`
- `longitude`

Indexes:

- `(region_id, property_type, complex_name)`
- `(latitude, longitude)` for future spatial enrichment

### `housing_transactions`

Stores transaction-level observations. This table keeps the fields already used by the current CSV-backed model and adds region and complex links.

Important columns:

- `transaction_id`
- `source_system`
- `source_property_type`
- `property_type`
- `city_code`
- `region_id`
- `complex_id`
- `lawd_cd`
- `district_name`
- `legal_dong_name`
- `building_name`
- `house_type`
- `deal_date`
- `deal_yyyymm`
- `exclusive_area_m2`
- `land_area_m2`
- `floor`
- `build_year`
- `price_manwon`
- `price_krw`
- `raw_payload_json`

Constraints:

- `price_krw = price_manwon * 10000` can be stored by application code or as a generated column.
- `city_code` must be `seoul` or `busan`, and import code must validate that it matches the linked `administrative_regions.city_code`.
- A de-duplication unique key will cover source, property type, region code, legal dong, building name, deal date, area, floor, build year, and price.

Indexes:

- `(deal_yyyymm, property_type)`
- `(city_code, deal_yyyymm)`
- `(region_id, deal_yyyymm)`
- `(lawd_cd, deal_yyyymm)`
- `(complex_id, deal_yyyymm)`

## Price-Factor Tables

The four factor groups use snapshot dates so model training can join each transaction to the factor values valid near its deal month.

All factor snapshot tables include:

- `snapshot_id`
- `region_id` or `complex_id`
- `snapshot_yyyymm`
- `source_name`
- `created_at`
- `updated_at`

### `property_condition_snapshots`

Granularity: usually `complex_id`, with optional transaction-derived values.

Columns:

- `exclusive_area_m2`
- `representative_floor`
- `build_year`
- `building_age_years`
- `household_count`
- `building_count`
- `total_parking_spaces`
- `parking_spaces_per_household`
- `has_community_facilities`
- `monthly_maintenance_fee_krw`

The transaction table remains the source of truth for actual traded area and floor. This snapshot stores stable or periodically collected property-condition attributes.

### `transport_access_snapshots`

Granularity: `complex_id` when coordinates are known; otherwise `region_id`.

Columns:

- `nearest_subway_distance_m`
- `subway_count_radius`
- `nearest_bus_stop_distance_m`
- `bus_stop_count_radius`
- `car_intercity_bus_terminal_minutes`
- `car_airport_minutes`
- `car_rail_station_minutes`
- `car_general_hospital_minutes`
- `transit_intercity_bus_terminal_minutes`
- `transit_airport_minutes`
- `transit_rail_station_minutes`
- `transit_general_hospital_minutes`

Radius size will be stored in metadata or a source note so future runs do not mix incompatible counts.

### `living_environment_snapshots`

Granularity: `complex_id` when coordinates are known; otherwise `region_id`.

Columns:

- `nearest_elementary_school_distance_m`
- `nearest_middle_school_distance_m`
- `nearest_high_school_distance_m`
- `school_count_radius`
- `academy_count_radius`
- `nearest_hospital_distance_m`
- `nearest_pharmacy_distance_m`
- `nearest_park_distance_m`
- `park_area_total_m2_radius`

### `urban_competitiveness_snapshots`

Granularity: `region_id`, usually district-level and monthly or yearly.

Columns:

- `population_count`
- `population_growth_rate`
- `employment_rate`
- `recent_transaction_count`
- `income_level_krw`
- `unsold_housing_count`
- `completed_housing_supply_count`

`recent_transaction_count` can be computed from `housing_transactions` for a rolling period, but storing it in a snapshot makes the training view reproducible.

## Training Feature View

Create `model_training_features` as a view that joins transactions to the nearest matching factor snapshots by:

- `housing_transactions.region_id`
- `housing_transactions.complex_id` when available
- `housing_transactions.deal_yyyymm = factor.snapshot_yyyymm`

The view will expose the current model fields plus the new factor columns:

- Existing transaction features: city, district, legal dong, property type, deal date, area, floor, build year, price
- Property condition features
- Transport accessibility features
- Living, education, and natural environment features
- Urban competitiveness features

The first SQL view will use exact month joins for transparency. If factor data is less frequent than monthly data, the implementation will expose the missing factor columns as `NULL` rather than silently substituting current or future values.

## Python Integration

After schema approval, add a small database layer rather than replacing the whole project structure.

Planned additions:

- MySQL connection configuration through environment variables such as `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, and `MYSQL_DATABASE`
- A schema migration or bootstrap command that executes the SQL DDL
- A loader that imports existing transaction CSV rows into `housing_transactions`
- A reader that converts rows from `model_training_features` back into the existing `Transaction` and feature-building flow where possible

The current CSV workflow will stay available so model development does not depend on MySQL being installed on every machine.

## Error Handling

Database bootstrap will fail clearly when:

- MySQL connection settings are missing
- MySQL version is too old for required features
- Required tables already exist with incompatible definitions

CSV import will fail clearly when:

- Required CSV columns are missing
- A transaction references an unknown `lawd_cd`
- Numeric values cannot be parsed
- Duplicate rows exceed the expected idempotent import behavior

Training from DB will fail clearly when:

- The training view returns no usable rows
- Required model feature columns are missing
- A selected city has no transaction rows

## Testing

Tests will cover:

- Generated DDL contains all core tables, factor snapshot tables, foreign keys, and key indexes
- Seoul and Busan district seed data includes `city_code` and `city_name`
- CSV-to-DB mapping preserves existing transaction values
- City filtering can return only Seoul or only Busan rows
- Training feature extraction works with rows shaped like `model_training_features`

Tests that require a live MySQL server will be isolated from normal unit tests. The default unit test suite can validate SQL text, row mapping, and feature conversion without network access.

## Out Of Scope

This phase will not build external collectors for subway, bus, school, park, hospital, population, employment, income, unsold housing, or supply data. The schema will be ready for those sources, and each source can be added as a separate importer with its own validation rules.

This phase will not remove the CSV workflow. MySQL will become an additional structured data backend first.
