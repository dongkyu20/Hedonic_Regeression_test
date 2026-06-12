import unittest

from hedonic_house_price.db_maintenance import (
    CLEAR_DATA_TABLES,
    PROPERTY_CONDITION_DERIVED_SQL,
    clear_transaction_data,
    refresh_transaction_derived_snapshots,
)


class FakeCursor:
    def __init__(self):
        self.statements = []
        self.rowcount = 7

    def execute(self, statement):
        self.statements.append(statement)

    def close(self):
        self.statements.append("CLOSE")


class FakeConnection:
    def __init__(self):
        self.cursor_obj = FakeCursor()
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class DbMaintenanceTests(unittest.TestCase):
    def test_clear_transaction_data_deletes_child_tables_before_core_tables(self):
        connection = FakeConnection()

        result = clear_transaction_data(connection)

        delete_statements = [
            statement for statement in connection.cursor_obj.statements
            if statement.startswith("DELETE FROM")
        ]
        self.assertEqual(
            delete_statements,
            [f"DELETE FROM {table_name}" for table_name in CLEAR_DATA_TABLES],
        )
        self.assertEqual(result["cleared_tables"], len(CLEAR_DATA_TABLES))
        self.assertEqual(connection.commits, 1)
        self.assertEqual(connection.rollbacks, 0)

    def test_refresh_transaction_derived_snapshots_rebuilds_only_derived_sources(self):
        connection = FakeConnection()

        result = refresh_transaction_derived_snapshots(connection)

        statements = "\n".join(connection.cursor_obj.statements)
        self.assertIn("DELETE FROM property_condition_snapshots WHERE source_name = 'transactions_derived'", statements)
        self.assertIn("DELETE FROM urban_competitiveness_snapshots WHERE source_name = 'transactions_derived'", statements)
        self.assertIn("INSERT INTO property_condition_snapshots", statements)
        self.assertIn("INSERT INTO urban_competitiveness_snapshots", statements)
        self.assertEqual(result["property_condition_rows"], 7)
        self.assertEqual(result["urban_competitiveness_rows"], 7)
        self.assertEqual(connection.commits, 1)

    def test_property_condition_sql_excludes_building_age_years(self):
        self.assertIn("MIN(build_year)", PROPERTY_CONDITION_DERIVED_SQL)
        self.assertNotIn("building_age_years", PROPERTY_CONDITION_DERIVED_SQL)
        self.assertNotIn("CAST(LEFT(deal_yyyymm, 4) AS SIGNED)", PROPERTY_CONDITION_DERIVED_SQL)
        self.assertNotIn("CAST(MIN(build_year) AS SIGNED)", PROPERTY_CONDITION_DERIVED_SQL)


if __name__ == "__main__":
    unittest.main()
