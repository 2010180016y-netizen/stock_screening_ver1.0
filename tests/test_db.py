from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vcb_alt.config import AppConfig
from vcb_alt.db import (
    add_watchlist,
    connect,
    delete_local_data,
    ensure_initialized,
    export_data,
    init_db,
    list_watchlist,
    log_operation,
    recent_logs,
    recent_provider_alerts,
    record_provider_alert,
    save_evaluation,
    _row_with_json,
)
from vcb_alt.sample_data import get_snapshot
from vcb_alt.scoring import evaluate_snapshot


def make_config(root: Path, database_url: str = "sqlite:///./data/test.db") -> AppConfig:
    return AppConfig(
        database_url=database_url,
        log_level="INFO",
        timezone="Asia/Seoul",
        data_provider="sample",
        external_api_enabled=False,
        root_dir=root,
        data_dir=root / "data",
        log_dir=root / "logs",
    )


class DatabaseTests(unittest.TestCase):
    def test_watchlist_evaluation_log_export_and_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            with connect(config) as conn:
                init_db(conn)
                added = add_watchlist(conn, ["PLTR", "MSTR"])
                self.assertEqual(added["added"], ["PLTR", "MSTR"])
                self.assertEqual(len(list_watchlist(conn)), 2)

                result = evaluate_snapshot(get_snapshot("PLTR"))
                save_evaluation(conn, result)
                log_operation(conn, "test", "success", "ok", {"OPENAI_API_KEY": "sk-test-secret-value"})
                logs = recent_logs(conn)
                self.assertEqual(logs[0]["metadata"]["OPENAI_API_KEY"], "[REDACTED]")

                exported = export_data(conn)
                self.assertEqual(len(exported["watchlist"]), 2)
                self.assertEqual(len(exported["evaluations"]), 1)

                deleted = delete_local_data(conn)
                self.assertEqual(deleted["watchlist"], 2)
                self.assertEqual(list_watchlist(conn), [])

    def test_ensure_initialized_issues_no_ddl_on_the_hot_path(self) -> None:
        """ensure_initialized() runs on every database call, so it must not emit DDL.

        On PostgreSQL an ALTER TABLE takes an ACCESS EXCLUSIVE lock even when it is a
        no-op, which would serialize concurrent requests.
        """
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            with connect(config) as conn:
                init_db(conn)
                statements: list[str] = []
                original = conn.execute

                def recording(sql: str, params: Any = ()) -> Any:
                    statements.append(" ".join(str(sql).split()).upper())
                    return original(sql, params)

                conn.execute = recording  # type: ignore[method-assign]
                ensure_initialized(conn)
                list_watchlist(conn)
                recent_provider_alerts(conn, 5)

                self.assertTrue(statements, "expected the probe to record executed SQL")
                for sql in statements:
                    self.assertNotIn("ALTER TABLE", sql)
                    self.assertNotIn("CREATE INDEX", sql)
                    self.assertNotIn("PRAGMA TABLE_INFO", sql)

    def test_init_db_upgrades_a_database_created_before_tenant_id(self) -> None:
        """Running init-db against an existing database must not fail.

        The schema script builds an index over provider_alert_events(tenant_id), so on a
        database created before that column existed the index creation raised
        "no such column: tenant_id" and init-db returned a 500.
        """
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy.db"
            legacy = sqlite3.connect(db_path)
            legacy.execute(
                """
                CREATE TABLE provider_alert_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    code TEXT,
                    message TEXT,
                    recovery TEXT,
                    metadata_json TEXT,
                    resolved INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            legacy.commit()
            legacy.close()

            config = make_config(Path(tmp), database_url=f"sqlite:///{db_path.as_posix()}")
            with connect(config) as conn:
                init_db(conn)
                columns = {
                    str(row["name"])
                    for row in conn.execute("PRAGMA table_info(provider_alert_events)").fetchall()
                }
                self.assertIn("tenant_id", columns)
                add_watchlist(conn, ["PLTR"])
                self.assertEqual(len(list_watchlist(conn)), 1)

    def test_ensure_initialized_backfills_legacy_provider_alert_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = make_config(root)
            with connect(config) as conn:
                init_db(conn)
                conn.execute("DROP TABLE provider_alert_events")
                conn.execute(
                    """
                    CREATE TABLE provider_alert_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        provider TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        code TEXT,
                        message TEXT,
                        recovery TEXT,
                        metadata_json TEXT,
                        resolved INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                conn.commit()

            with connect(config) as conn:
                ensure_initialized(conn)
                columns = {
                    str(row["name"])
                    for row in conn.execute("PRAGMA table_info(provider_alert_events)").fetchall()
                }
                self.assertIn("tenant_id", columns)
                record_provider_alert(conn, "alpaca", "auth_failure", "critical", "401", "denied", tenant_id="t1")
                conn.commit()
                alerts = recent_provider_alerts(conn, 5, tenant_id="t1")
                self.assertEqual(len(alerts), 1)

    def test_row_with_json_accepts_postgres_json_and_datetime_values(self) -> None:
        row = {
            "id": 1,
            "metadata_json": {"provider": "postgres"},
            "result_json": {"count": 3},
            "created_at": datetime(2026, 5, 22, tzinfo=timezone.utc),
        }

        decoded = _row_with_json(row)

        self.assertEqual(decoded["metadata"]["provider"], "postgres")
        self.assertEqual(decoded["result"]["count"], 3)
        self.assertEqual(decoded["created_at"], "2026-05-22T00:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
