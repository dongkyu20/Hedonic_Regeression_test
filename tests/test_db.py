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


if __name__ == "__main__":
    unittest.main()
