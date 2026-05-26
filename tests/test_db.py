from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from vcb_alt.config import AppConfig
from vcb_alt.db import (
    add_watchlist,
    connect,
    delete_local_data,
    export_data,
    init_db,
    list_watchlist,
    log_operation,
    recent_logs,
    save_evaluation,
    _row_with_json,
)
from vcb_alt.sample_data import get_snapshot
from vcb_alt.scoring import evaluate_snapshot


def make_config(root: Path) -> AppConfig:
    return AppConfig(
        database_url="sqlite:///./data/test.db",
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
