"""Cover the PostgreSQL branches of db.py, which local SQLite runs never reach.

Two layers: a stub connection that runs everywhere and asserts which statements the
migration issues, and an integration suite that runs against a real server when
VCB_ALT_TEST_DATABASE_URL is set (CI provides one; see .github/workflows/ci.yml).
"""

from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path
from typing import Any

from vcb_alt.config import AppConfig
from vcb_alt.db import (
    _ensure_provider_alert_tenant_column,
    connect,
    ensure_initialized,
    init_db,
    recent_provider_alerts,
    record_provider_alert,
)


class _StubCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows

    def fetchone(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None


class _StubPostgresConnection:
    """Looks like a PostgreSQL connection to db.py, records every statement."""

    dialect = "postgresql"

    def __init__(self, columns: list[str]) -> None:
        self.columns = columns
        self.statements: list[str] = []

    def execute(self, sql: str, params: Any = None) -> _StubCursor:
        normalized = " ".join(str(sql).split())
        self.statements.append(normalized)
        if "information_schema.columns" in normalized:
            return _StubCursor([{"column_name": name} for name in self.columns])
        return _StubCursor([])

    def commit(self) -> None:
        return None

    def ddl_statements(self) -> list[str]:
        return [sql for sql in self.statements if sql.startswith(("ALTER TABLE", "CREATE INDEX"))]


class PostgresMigrationBranchTests(unittest.TestCase):
    def test_no_ddl_when_the_column_already_exists(self) -> None:
        conn = _StubPostgresConnection(["id", "provider", "tenant_id", "created_at"])
        _ensure_provider_alert_tenant_column(conn)
        self.assertEqual(conn.ddl_statements(), [])
        self.assertEqual(len(conn.statements), 1, conn.statements)
        self.assertIn("information_schema.columns", conn.statements[0])

    def test_adds_column_and_index_when_missing(self) -> None:
        conn = _StubPostgresConnection(["id", "provider", "created_at"])
        _ensure_provider_alert_tenant_column(conn)
        ddl = conn.ddl_statements()
        self.assertEqual(len(ddl), 2, ddl)
        self.assertIn("ADD COLUMN IF NOT EXISTS tenant_id TEXT", ddl[0])
        self.assertIn("idx_provider_alert_events_tenant_time", ddl[1])

    def test_does_nothing_when_the_table_does_not_exist_yet(self) -> None:
        """A fresh database: the schema script creates the table with the column."""
        conn = _StubPostgresConnection([])
        _ensure_provider_alert_tenant_column(conn)
        self.assertEqual(conn.ddl_statements(), [])

    def test_result_is_cached_per_connection(self) -> None:
        conn = _StubPostgresConnection(["id", "tenant_id"])
        _ensure_provider_alert_tenant_column(conn)
        _ensure_provider_alert_tenant_column(conn)
        _ensure_provider_alert_tenant_column(conn)
        self.assertEqual(len(conn.statements), 1, conn.statements)

    def test_missing_table_is_not_cached(self) -> None:
        conn = _StubPostgresConnection([])
        _ensure_provider_alert_tenant_column(conn)
        conn.columns = ["id", "tenant_id"]
        _ensure_provider_alert_tenant_column(conn)
        self.assertEqual(len(conn.statements), 2, conn.statements)


TEST_DATABASE_URL = os.environ.get("VCB_ALT_TEST_DATABASE_URL", "")
HAS_PSYCOPG = importlib.util.find_spec("psycopg") is not None


@unittest.skipUnless(TEST_DATABASE_URL, "VCB_ALT_TEST_DATABASE_URL is not set")
@unittest.skipUnless(HAS_PSYCOPG, "psycopg is not installed")
class PostgresIntegrationTests(unittest.TestCase):
    """Runs the real bootstrap path against a live PostgreSQL server."""

    def setUp(self) -> None:
        if "test" not in TEST_DATABASE_URL.lower():
            self.skipTest("refusing to run destructive tests against a URL without 'test' in it")
        self.config = AppConfig(
            database_url=TEST_DATABASE_URL,
            log_level="INFO",
            timezone="Asia/Seoul",
            data_provider="sample",
            external_api_enabled=False,
            root_dir=Path("."),
            data_dir=Path("."),
            log_dir=Path("."),
            database_backend="postgresql",
        )

    def drop_schema(self) -> None:
        with connect(self.config) as conn:
            conn.execute("DROP SCHEMA public CASCADE")
            conn.execute("CREATE SCHEMA public")
            conn.commit()

    def test_init_db_bootstraps_a_fresh_database(self) -> None:
        self.drop_schema()
        with connect(self.config) as conn:
            init_db(conn)
            ensure_initialized(conn)
            record_provider_alert(conn, "alpaca", "auth_failure", "critical", "401", "denied", tenant_id="t1")
            conn.commit()
            self.assertEqual(len(recent_provider_alerts(conn, 5, tenant_id="t1")), 1)
            self.assertEqual(recent_provider_alerts(conn, 5, tenant_id="other"), [])

    def test_init_db_upgrades_a_database_created_before_tenant_id(self) -> None:
        self.drop_schema()
        with connect(self.config) as conn:
            conn.execute(
                """
                CREATE TABLE provider_alert_events (
                    id BIGSERIAL PRIMARY KEY,
                    provider TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    code TEXT,
                    message TEXT,
                    recovery TEXT,
                    metadata_json TEXT,
                    resolved INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMPTZ NOT NULL
                )
                """
            )
            conn.commit()

        with connect(self.config) as conn:
            init_db(conn)
            columns = {
                str(row["column_name"])
                for row in conn.execute(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'provider_alert_events'
                    """
                ).fetchall()
            }
            self.assertIn("tenant_id", columns)

    def test_hot_path_issues_no_ddl(self) -> None:
        with connect(self.config) as conn:
            init_db(conn)

        with connect(self.config) as conn:
            ensure_initialized(conn)
            statements: list[str] = []
            original = conn.execute

            def recording(sql: str, params: Any = None) -> Any:
                statements.append(" ".join(str(sql).split()).upper())
                return original(sql, params)

            conn.execute = recording  # type: ignore[method-assign]
            ensure_initialized(conn)
            recent_provider_alerts(conn, 5)
            for sql in statements:
                self.assertFalse(sql.startswith("ALTER TABLE"), sql)
                self.assertFalse(sql.startswith("CREATE INDEX"), sql)


if __name__ == "__main__":
    unittest.main()
