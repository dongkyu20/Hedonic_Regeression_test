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
        self.assertIn("road_address VARCHAR(512) NULL", sql)
        self.assertIn("jibun_address VARCHAR(512) NULL", sql)
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

    def test_property_condition_schema_excludes_maintenance_fee(self):
        sql = SCHEMA_SQL.read_text(encoding="utf-8")

        self.assertNotIn("monthly_maintenance_fee_krw", sql)

    def test_training_view_joins_property_condition_sources_once(self):
        sql = SCHEMA_SQL.read_text(encoding="utf-8")

        self.assertIn("pcs_tx.source_name = 'transactions_derived'", sql)
        self.assertIn("pcs_kapt.source_name = 'kapt_basic_info'", sql)
        self.assertIn("COALESCE(pcs_kapt.household_count, pcs_tx.household_count)", sql)

    def test_seed_contains_seoul_and_busan_district_rows(self):
        seed = SEED_SQL.read_text(encoding="utf-8")

        self.assertIn("'seoul', '서울특별시', '강남구', '11680'", seed)
        self.assertIn("'busan', '부산광역시', '해운대구', '26350'", seed)
        self.assertEqual(seed.count("'seoul', '서울특별시'"), 25)
        self.assertEqual(seed.count("'busan', '부산광역시'"), 16)


if __name__ == "__main__":
    unittest.main()
