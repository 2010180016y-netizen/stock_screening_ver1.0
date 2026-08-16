from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from vcb_alt.auth import hash_password, verify_password
from vcb_alt.config import AppConfig, load_config
from vcb_alt.db import connect, init_db, record_provider_alert
from vcb_alt.errors import UnauthorizedError
from vcb_alt.job_queue import (
    _claim_next_job,
    _complete_market_scan_job,
    _decode_job,
    enqueue_scan_job,
    get_fresh_market_scan_snapshot,
    queue_status,
    recover_stale_jobs,
    recover_stale_market_scan_jobs,
    run_queued_scan_jobs,
)
from vcb_alt.rate_limit import DatabaseRateLimiter, InMemoryRateLimiter
from vcb_alt.tenant_store import (
    add_user_watchlist,
    authenticate_session,
    create_user,
    init_saas_db,
    list_user_watchlist,
    login_user,
    require_role,
    require_user,
)
from vcb_alt.web import _allow_request, handle_api


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
        user_auth_enabled=True,
        user_registration_enabled=True,
    )


class SaasAuthTests(unittest.TestCase):
    def test_password_hash_verifies_without_plaintext_storage(self) -> None:
        encoded = hash_password("very-secure-password")
        self.assertNotIn("very-secure-password", encoded)
        self.assertTrue(verify_password("very-secure-password", encoded))
        self.assertFalse(verify_password("wrong-password", encoded))

    def test_tenant_watchlists_are_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            with connect(config) as conn:
                init_db(conn)
                init_saas_db(conn)
                alice = create_user(conn, email="alice@example.com", password="very-secure-password")
                bob = create_user(conn, email="bob@example.com", password="very-secure-password")
                add_user_watchlist(conn, alice, ["AAPL"])
                add_user_watchlist(conn, bob, ["MSTR"])

                self.assertEqual([item["ticker"] for item in list_user_watchlist(conn, alice)], ["AAPL"])
                self.assertEqual([item["ticker"] for item in list_user_watchlist(conn, bob)], ["MSTR"])

    def test_user_auth_api_flow_uses_bearer_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            with connect(config) as conn:
                init_db(conn)

            registered = handle_api(
                config,
                "POST",
                "/api/auth/register",
                "",
                {"email": "owner@example.com", "password": "very-secure-password", "tenant_name": "Owner"},
            )
            self.assertTrue(registered.ok)
            token = registered.data["session_token"]

            me = handle_api(config, "GET", "/api/me", "", None, {"authorization": f"Bearer {token}"})
            self.assertTrue(me.ok)
            self.assertEqual(me.data["email"], "owner@example.com")

            add = handle_api(
                config,
                "POST",
                "/api/user/watchlist",
                "",
                {"tickers": "AAPL MSTR"},
                {"authorization": f"Bearer {token}"},
            )
            self.assertTrue(add.ok)

            listed = handle_api(config, "GET", "/api/user/watchlist", "", None, {"authorization": f"Bearer {token}"})
            self.assertEqual([item["ticker"] for item in listed.data["items"]], ["AAPL", "MSTR"])

            scan = handle_api(config, "POST", "/api/user/scan", "", {}, {"authorization": f"Bearer {token}"})
            self.assertTrue(scan.ok)
            self.assertEqual(scan.data["count"], 2)
            self.assertIn("selection", scan.data)

            selection = handle_api(config, "POST", "/api/user/select", "", {}, {"authorization": f"Bearer {token}"})
            self.assertTrue(selection.ok)
            self.assertIn("selected", selection.data["selection"])

            users = handle_api(config, "GET", "/api/admin/users", "", None, {"authorization": f"Bearer {token}"})
            self.assertTrue(users.ok)
            self.assertEqual(users.data["items"][0]["email"], "owner@example.com")

    def test_rbac_helper_rejects_insufficient_role(self) -> None:
        owner = {"role": "owner"}
        member = {"role": "member"}

        self.assertEqual(require_role(owner, {"owner", "admin"}), owner)
        with self.assertRaises(Exception):
            require_role(member, {"owner", "admin"})

    def test_login_rejects_wrong_password(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            with connect(config) as conn:
                init_db(conn)
                init_saas_db(conn)
                create_user(conn, email="alice@example.com", password="very-secure-password")
                with self.assertRaises(Exception):
                    login_user(conn, email="alice@example.com", password="bad-password")

    def test_rate_limiter_blocks_after_limit(self) -> None:
        limiter = InMemoryRateLimiter(window_seconds=60)
        self.assertTrue(limiter.allow("ip", 2))
        self.assertTrue(limiter.allow("ip", 2))
        self.assertFalse(limiter.allow("ip", 2))

    def test_database_rate_limiter_blocks_across_connections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            limiter = DatabaseRateLimiter(window_seconds=60)
            with connect(config) as conn:
                init_db(conn)
                self.assertTrue(limiter.allow(conn, "tenant:user", 2))
            with connect(config) as conn:
                self.assertTrue(limiter.allow(conn, "tenant:user", 2))
            with connect(config) as conn:
                self.assertFalse(limiter.allow(conn, "tenant:user", 2))

    def test_scan_queue_is_tenant_scoped_and_worker_processes_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            config = AppConfig(
                **{
                    **config.__dict__,
                    "scan_queue_enabled": True,
                    "worker_token": "worker-token-123456",
                    "worker_cron_enabled": True,
                }
            )
            with connect(config) as conn:
                init_db(conn)
                init_saas_db(conn)
                user = create_user(conn, email="queue@example.com", password="very-secure-password")
                add_user_watchlist(conn, user, ["PLTR", "MSTR"])
                login = login_user(conn, email="queue@example.com", password="very-secure-password")
                auth_headers = {"authorization": f"Bearer {login['session_token']}"}
                queued = handle_api(
                    config,
                    "POST",
                    "/api/jobs/scan",
                    "",
                    {},
                    auth_headers,
                )
                self.assertTrue(queued.ok)
                worker = run_queued_scan_jobs(config, conn, limit=1)
                self.assertEqual(worker["processed"], 1)
                jobs = handle_api(
                    config,
                    "GET",
                    "/api/jobs",
                    "",
                    None,
                    auth_headers,
                )
                self.assertEqual(jobs.data["items"][0]["status"], "completed")
                self.assertEqual(jobs.data["items"][0]["result"]["count"], 2)
                queue = handle_api(config, "GET", "/api/admin/queue-status", "", None, auth_headers)
                self.assertTrue(queue.ok)
                self.assertEqual(queue.data["completed"], 1)
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM tenant_evaluations
                    WHERE tenant_id = ? AND user_id = ?
                    """,
                    (user["tenant_id"], user["id"]),
                ).fetchone()
                self.assertEqual(int(row["count"]), 2)

                exported = handle_api(config, "GET", "/api/user/export", "", None, auth_headers)
                self.assertTrue(exported.ok)
                self.assertEqual(len(exported.data["watchlist"]), 2)
                self.assertEqual(len(exported.data["evaluations"]), 2)
                audit = handle_api(config, "GET", "/api/admin/audit-events", "", None, auth_headers)
                self.assertTrue(audit.ok)
                self.assertGreaterEqual(len(audit.data["items"]), 1)

                delete = handle_api(
                    config,
                    "DELETE",
                    "/api/user/account",
                    "confirm=DELETE_MY_ACCOUNT",
                    None,
                    auth_headers,
                )
                self.assertTrue(delete.ok)
                with self.assertRaises(UnauthorizedError):
                    require_user(conn, login["session_token"])

    def test_production_market_scan_uses_worker_owned_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            config = AppConfig(
                **{
                    **config.__dict__,
                    "scan_mode": "market_universe",
                    "scan_queue_enabled": True,
                    "worker_token": "worker-token-123456",
                    "worker_cron_enabled": True,
                    "production_saas_mode": True,
                    "intraday_cache_ttl_seconds": 120,
                }
            )
            with connect(config) as conn:
                init_db(conn)
                init_saas_db(conn)
                user = create_user(conn, email="market-owner@example.com", password="very-secure-password")
                login = login_user(conn, email="market-owner@example.com", password="very-secure-password")
                headers = {"authorization": f"Bearer {login['session_token']}"}

                first = handle_api(config, "POST", "/api/user/scan", "", {}, headers)
                self.assertTrue(first.ok)
                self.assertEqual(first.status_code, 202)
                self.assertEqual(first.data["state"], "queued")
                job_id = first.data["job"]["id"]

                second = handle_api(config, "POST", "/api/user/scan", "", {}, headers)
                self.assertTrue(second.ok)
                self.assertEqual(second.status_code, 202)
                self.assertEqual(second.data["job"]["id"], job_id)

                worker = run_queued_scan_jobs(config, conn, limit=1)
                self.assertEqual(worker["processed"], 1)
                self.assertEqual(worker["failed"], 0)

                job_status = handle_api(config, "GET", f"/api/jobs/market-scan/{job_id}", "", None, headers)
                self.assertTrue(job_status.ok)
                self.assertEqual(job_status.data["status"], "completed")
                self.assertEqual(job_status.data["report"]["scan_mode"], "market_universe")

                fresh = handle_api(config, "POST", "/api/user/scan", "", {}, headers)
                self.assertTrue(fresh.ok)
                self.assertEqual(fresh.status_code, 200)
                self.assertEqual(fresh.data["scan_mode"], "market_universe")
                self.assertEqual(fresh.data["snapshot"]["served_from"], "durable_snapshot")
                self.assertGreaterEqual(fresh.data["count"], 1)

                row = conn.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM tenant_evaluations
                    WHERE tenant_id = ? AND user_id = ?
                    """,
                    (user["tenant_id"], user["id"]),
                ).fetchone()
                self.assertEqual(int(row["count"]), fresh.data["count"])

    def test_live_data_required_does_not_serve_sample_durable_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            config = AppConfig(
                **{
                    **config.__dict__,
                    "scan_mode": "market_universe",
                    "scan_queue_enabled": True,
                    "production_saas_mode": True,
                    "market_scan_requires_live_data": True,
                    "intraday_cache_ttl_seconds": 120,
                }
            )
            sample_report = {
                "scan_mode": "market_universe",
                "items": [{"ticker": "PLTR", "source": "sample-placeholder"}],
                "count": 1,
                "universe": {"source": "sample"},
                "prefilter": {"source": "unavailable", "fallback": "sample_universe"},
                "selection": {"selected": []},
                "failures": [],
                "snapshot_ttl_seconds": 120,
            }
            with connect(config) as conn:
                init_db(conn)
                init_saas_db(conn)
                create_user(conn, email="live-gate@example.com", password="very-secure-password")
                login = login_user(conn, email="live-gate@example.com", password="very-secure-password")
                _complete_market_scan_job(conn, "market_sample_snapshot", sample_report, insert_if_missing=True)

                self.assertIsNone(get_fresh_market_scan_snapshot(config, conn))

                response = handle_api(
                    config,
                    "POST",
                    "/api/user/scan",
                    "",
                    {},
                    {"authorization": f"Bearer {login['session_token']}"},
                )
                self.assertTrue(response.ok)
                self.assertEqual(response.status_code, 202)
                self.assertEqual(response.data["state"], "queued")
                self.assertNotIn("items", response.data)

    def test_market_universe_tenant_job_does_not_inline_provider_scan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            config = AppConfig(
                **{
                    **config.__dict__,
                    "scan_mode": "market_universe",
                    "scan_queue_enabled": True,
                    "worker_token": "worker-token-123456",
                    "worker_cron_enabled": True,
                    "production_saas_mode": True,
                }
            )
            with connect(config) as conn:
                init_db(conn)
                init_saas_db(conn)
                user = create_user(conn, email="tenant-job@example.com", password="very-secure-password")
                enqueue_scan_job(conn, user)
                with patch("vcb_alt.job_queue.scan_market_universe", side_effect=AssertionError("inline scan")):
                    worker = run_queued_scan_jobs(config, conn, limit=1)

                self.assertEqual(worker["processed"], 1)
                self.assertEqual(worker["failed"], 0)
                login = login_user(conn, email="tenant-job@example.com", password="very-secure-password")
                tenant_job = handle_api(
                    config,
                    "GET",
                    "/api/jobs",
                    "",
                    None,
                    {"authorization": f"Bearer {login['session_token']}"},
                )
                self.assertEqual(tenant_job.data["items"][0]["result"]["state"], "pending")
                status = queue_status(conn, user["tenant_id"])
                self.assertEqual(status["market_scan_snapshots"]["queued"], 1)

    def test_market_scan_worker_retries_then_dead_letters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            config = AppConfig(
                **{
                    **config.__dict__,
                    "scan_mode": "market_universe",
                    "scan_queue_enabled": True,
                    "worker_token": "worker-token-123456",
                    "worker_cron_enabled": True,
                    "production_saas_mode": True,
                }
            )
            with connect(config) as conn:
                init_db(conn)
                init_saas_db(conn)
                create_user(conn, email="retry@example.com", password="very-secure-password")
                login = login_user(conn, email="retry@example.com", password="very-secure-password")
                headers = {"authorization": f"Bearer {login['session_token']}"}
                queued = handle_api(config, "POST", "/api/user/scan", "", {}, headers)
                job_id = queued.data["job"]["id"]

                with patch("vcb_alt.job_queue.scan_market_universe", side_effect=RuntimeError("provider down")):
                    worker = run_queued_scan_jobs(config, conn, limit=1)
                self.assertEqual(worker["processed"], 1)
                self.assertEqual(worker["failed"], 1)
                retry_row = handle_api(config, "GET", f"/api/jobs/market-scan/{job_id}", "", None, headers)
                self.assertEqual(retry_row.data["status"], "queued")
                self.assertEqual(retry_row.data["error_code"], "MARKET_SCAN_FAILED")
                self.assertIsNotNone(retry_row.data["next_attempt_at"])

                old_started = "2026-05-22T00:00:00+00:00"
                conn.execute(
                    """
                    UPDATE market_scan_snapshots
                    SET status = ?, attempts = ?, started_at = ?, next_attempt_at = ?
                    WHERE id = ?
                    """,
                    ("running", 3, old_started, None, job_id),
                )
                conn.commit()
                recovered = recover_stale_market_scan_jobs(conn, max_running_seconds=1, max_attempts=3)
                self.assertEqual(recovered["dead_lettered"], 1)
                dead = handle_api(config, "GET", f"/api/jobs/market-scan/{job_id}", "", None, headers)
                self.assertEqual(dead.data["status"], "dead_letter")

    def test_worker_endpoint_requires_token_and_processes_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            config = AppConfig(
                **{
                    **config.__dict__,
                    "scan_queue_enabled": True,
                    "worker_token": "worker-token-123456",
                    "worker_cron_enabled": True,
                }
            )
            with connect(config) as conn:
                init_db(conn)
                init_saas_db(conn)
                create_user(conn, email="worker@example.com", password="very-secure-password")
                login = login_user(conn, email="worker@example.com", password="very-secure-password")
                headers = {"authorization": f"Bearer {login['session_token']}"}
                add = handle_api(config, "POST", "/api/user/watchlist", "", {"tickers": "PLTR"}, headers)
                self.assertTrue(add.ok)
                queued = handle_api(config, "POST", "/api/jobs/scan", "", {}, headers)
                self.assertTrue(queued.ok)

            with self.assertRaises(UnauthorizedError):
                handle_api(config, "POST", "/api/admin/run-worker", "", {}, {})

            worker = handle_api(config, "POST", "/api/admin/run-worker", "worker_token=worker-token-123456", {}, {})
            self.assertTrue(worker.ok)
            self.assertEqual(worker.data["processed"], 1)

    def test_production_worker_endpoint_rejects_get_and_query_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            config = AppConfig(
                **{
                    **config.__dict__,
                    "scan_queue_enabled": True,
                    "worker_token": "worker-token-123456",
                    "worker_cron_enabled": True,
                    "production_saas_mode": True,
                    "allow_query_token_auth": False,
                }
            )
            with connect(config) as conn:
                init_db(conn)
                init_saas_db(conn)

            with self.assertRaises(Exception):
                handle_api(
                    config,
                    "GET",
                    "/api/admin/run-worker",
                    "",
                    None,
                    {"x-vcb-worker-token": "worker-token-123456"},
                )

            with self.assertRaises(UnauthorizedError):
                handle_api(config, "POST", "/api/admin/run-worker", "worker_token=worker-token-123456", {}, {})

            header_response = handle_api(
                config,
                "POST",
                "/api/admin/run-worker",
                "",
                {},
                {"x-vcb-worker-token": "worker-token-123456"},
            )
            self.assertTrue(header_response.ok)

    def test_admin_provider_alerts_are_owner_scoped_and_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            with connect(config) as conn:
                init_db(conn)
                init_saas_db(conn)
                owner = create_user(conn, email="alerts@example.com", password="very-secure-password")
                create_user(conn, email="operator@example.com", password="very-secure-password", role="operator")
                login = login_user(conn, email="alerts@example.com", password="very-secure-password")
                operator_login = login_user(conn, email="operator@example.com", password="very-secure-password")
                record_provider_alert(
                    conn,
                    "alpaca",
                    "fixture",
                    "critical",
                    "PROVIDER_AUTH_FAILED",
                    "bad key alpaca-secret-value-1234567890",
                    metadata={"api_key": "alpaca-key-id-1234567890"},
                    tenant_id=owner["tenant_id"],
                )
                record_provider_alert(
                    conn,
                    "finnhub",
                    "fixture",
                    "warning",
                    "PROVIDER_RATE_LIMITED",
                    "global provider budget event",
                    metadata={"tenant_id": "other-tenant"},
                )

            alerts = handle_api(
                config,
                "GET",
                "/api/admin/provider-alerts",
                "",
                None,
                {"authorization": f"Bearer {login['session_token']}"},
            )

            rendered = str(alerts.data)
            self.assertTrue(alerts.ok)
            self.assertEqual(alerts.data["visibility"], "tenant_scoped")
            self.assertEqual(len(alerts.data["items"]), 1)
            self.assertEqual(alerts.data["items"][0]["provider"], "alpaca")
            self.assertNotIn("alpaca-secret-value-1234567890", rendered)
            self.assertNotIn("alpaca-key-id-1234567890", rendered)

            global_alerts = handle_api(
                config,
                "GET",
                "/api/admin/provider-alerts",
                "",
                None,
                {"authorization": f"Bearer {operator_login['session_token']}"},
            )
            self.assertTrue(global_alerts.ok)
            self.assertEqual(global_alerts.data["visibility"], "global_operator")
            self.assertEqual({item["provider"] for item in global_alerts.data["items"]}, {"alpaca", "finnhub"})

    def test_job_decode_handles_postgres_datetime_and_json_objects(self) -> None:
        decoded = _decode_job(
            {
                "id": "job_1",
                "status": "completed",
                "request_json": {"kind": "tenant_watchlist_scan"},
                "result_json": {"count": 1},
                "created_at": datetime(2026, 5, 22, tzinfo=timezone.utc),
                "started_at": None,
                "finished_at": datetime(2026, 5, 22, 0, 1, tzinfo=timezone.utc),
            }
        )
        self.assertEqual(decoded["result"]["count"], 1)
        self.assertEqual(decoded["created_at"], "2026-05-22T00:00:00+00:00")

    def test_authenticate_session_accepts_postgres_datetime_expiry(self) -> None:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        conn = _SingleSessionConnection(
            {
                "id": "user_1",
                "tenant_id": "tenant_1",
                "email": "pg@example.com",
                "role": "owner",
                "expires_at": expires_at,
            }
        )

        user = authenticate_session(conn, "session-token")

        self.assertEqual(user["email"], "pg@example.com")

    def test_database_rate_limiter_uses_postgres_bucket_lock(self) -> None:
        conn = _FakePostgresLimiterConnection(existing_count=0)
        limiter = DatabaseRateLimiter(window_seconds=60)

        self.assertTrue(limiter.allow(conn, "tenant:user", 5))

        self.assertIn("pg_advisory_xact_lock", conn.sql[0])
        self.assertTrue(conn.committed)

    def test_authenticated_rate_limit_is_per_user_not_shared_ip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            config = AppConfig(
                **{
                    **config.__dict__,
                    "rate_limit_backend": "database",
                    "rate_limit_per_minute": 2,
                }
            )
            with connect(config) as conn:
                init_db(conn)
                init_saas_db(conn)
                create_user(conn, email="rate-a@example.com", password="very-secure-password")
                create_user(conn, email="rate-b@example.com", password="very-secure-password")
                token_a = login_user(conn, email="rate-a@example.com", password="very-secure-password")["session_token"]
                token_b = login_user(conn, email="rate-b@example.com", password="very-secure-password")["session_token"]

            handler_a = _FakeRateLimitHandler({"Authorization": f"Bearer {token_a}"}, "203.0.113.10")
            handler_b = _FakeRateLimitHandler({"Authorization": f"Bearer {token_b}"}, "203.0.113.10")

            self.assertTrue(_allow_request(handler_a, config, "POST", "/api/jobs/scan"))
            self.assertTrue(_allow_request(handler_a, config, "POST", "/api/jobs/scan"))
            self.assertTrue(_allow_request(handler_b, config, "POST", "/api/jobs/scan"))

    def test_postgres_queue_claim_uses_skip_locked(self) -> None:
        conn = _FakePostgresQueueConnection()

        job = _claim_next_job(conn)

        self.assertEqual(job["id"], "job_1")
        self.assertIn("FOR UPDATE SKIP LOCKED", conn.sql[0])
        self.assertTrue(conn.committed)

    def test_postgres_saas_schema_initialization_uses_advisory_lock(self) -> None:
        conn = _FakePostgresSchemaConnection()

        init_saas_db(conn)

        self.assertIn("pg_advisory_xact_lock", conn.sql[0])
        self.assertTrue(conn.script_ran)
        self.assertTrue(conn.committed)

    def test_recover_stale_running_jobs_requeues_or_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            old_started = "2026-05-22T00:00:00+00:00"
            with connect(config) as conn:
                init_db(conn)
                init_saas_db(conn)
                user = create_user(conn, email="stale@example.com", password="very-secure-password")
                conn.execute(
                    """
                    INSERT INTO scan_jobs (
                        id, tenant_id, user_id, status, requested_by, request_json, attempts, created_at, started_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "job_retry",
                        user["tenant_id"],
                        user["id"],
                        "running",
                        user["email"],
                        "{}",
                        1,
                        old_started,
                        old_started,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO scan_jobs (
                        id, tenant_id, user_id, status, requested_by, request_json, attempts, created_at, started_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "job_fail",
                        user["tenant_id"],
                        user["id"],
                        "running",
                        user["email"],
                        "{}",
                        3,
                        old_started,
                        old_started,
                    ),
                )
                conn.commit()

                recovered = recover_stale_jobs(conn, max_running_seconds=1, max_attempts=3)
                status = queue_status(conn, user["tenant_id"])

                self.assertEqual(recovered["requeued"], 1)
                self.assertEqual(recovered["failed"], 1)
                self.assertEqual(status["queued"], 1)
                self.assertEqual(status["failed"], 1)

    def test_production_saas_mode_requires_durable_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("VCB_ALT_PRODUCTION_SAAS_MODE=true\n", encoding="utf-8")
            with self.assertRaises(Exception):
                load_config(Path(tmp))

class _SingleSessionConnection:
    def __init__(self, row: dict[str, object]) -> None:
        self.row = row

    def execute(self, sql: str, params: tuple[object, ...]) -> "_SingleRowCursor":
        return _SingleRowCursor(self.row)


class _SingleRowCursor:
    def __init__(self, row: dict[str, object]) -> None:
        self.row = row

    def fetchone(self) -> dict[str, object]:
        return self.row


class _FakePostgresLimiterConnection:
    dialect = "postgresql"

    def __init__(self, existing_count: int) -> None:
        self.existing_count = existing_count
        self.sql: list[str] = []
        self.committed = False

    def execute(self, sql: str, params: tuple[object, ...]) -> "_FakeLimiterCursor":
        self.sql.append(sql)
        if sql.startswith("SELECT COUNT"):
            return _FakeLimiterCursor({"count": self.existing_count})
        return _FakeLimiterCursor({"count": 0})

    def commit(self) -> None:
        self.committed = True


class _FakeLimiterCursor:
    def __init__(self, row: dict[str, object]) -> None:
        self.row = row

    def fetchone(self) -> dict[str, object]:
        return self.row


class _FakePostgresQueueConnection:
    dialect = "postgresql"

    def __init__(self) -> None:
        self.sql: list[str] = []
        self.committed = False

    def execute(self, sql: str, params: tuple[object, ...]) -> "_FakeQueueCursor":
        self.sql.append(sql)
        return _FakeQueueCursor({"id": "job_1", "tenant_id": "tenant_1", "user_id": "user_1", "attempts": 1})

    def commit(self) -> None:
        self.committed = True


class _FakeQueueCursor:
    def __init__(self, row: dict[str, object]) -> None:
        self.row = row

    def fetchone(self) -> dict[str, object]:
        return self.row


class _FakePostgresSchemaConnection:
    dialect = "postgresql"

    def __init__(self) -> None:
        self.sql: list[str] = []
        self.script_ran = False
        self.committed = False

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> "_FakeQueueCursor":
        self.sql.append(sql)
        return _FakeQueueCursor({"ok": True})

    def executescript(self, script: str) -> None:
        self.script_ran = "audit_events" in script

    def commit(self) -> None:
        self.committed = True


class _FakeRateLimitHandler:
    def __init__(self, headers: dict[str, str], ip: str) -> None:
        self.headers = headers
        self.client_address = (ip, 12345)


if __name__ == "__main__":
    unittest.main()
