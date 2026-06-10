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
