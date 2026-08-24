from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .config import doctor_report, load_config
from .db import (
    add_watchlist,
    connect,
    delete_local_data,
    ensure_initialized,
    export_data,
    init_db,
    list_watchlist,
    log_operation,
    recent_failures,
    recent_logs,
    record_failure,
    remove_watchlist,
    save_evaluation,
    seed_watchlist,
)
from .errors import AppError
from .job_queue import run_queued_scan_jobs, validate_job_limit
from .logging_utils import append_file_log
from .market_universe import scan_market_universe, scan_pipeline_readiness
from .models import OperationResult
from .performance import benchmark_scoring
from .portfolio import select_portfolio
from .providers import get_snapshot
from .sample_data import SAMPLE_TICKERS
from .saas_readiness import get_saas_readiness
from .scoring import evaluate_snapshot
from .tenant_store import init_saas_db
from .validation import require_delete_confirmation, validate_ticker
from .web import run_web


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m vcb_alt",
        description="VCB-Alt local-first stock screening decision-support CLI.",
    )
    parser.add_argument("--version", action="version", version=f"vcb-alt {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init-db", help="Create local SQLite tables.")
    init_parser.add_argument("--seed", action="store_true", help="Add sample watchlist tickers.")
    init_parser.add_argument("--json", action="store_true", help="Print JSON output.")

    doctor_parser = subparsers.add_parser("doctor", help="Validate local configuration.")
    doctor_parser.add_argument("--json", action="store_true")

    watchlist_parser = subparsers.add_parser("watchlist", help="Manage watchlist tickers.")
    watchlist_sub = watchlist_parser.add_subparsers(dest="watchlist_command")
    watchlist_add = watchlist_sub.add_parser("add", help="Add tickers.")
    watchlist_add.add_argument("tickers", nargs="+")
    watchlist_add.add_argument("--hint", default=None, help="Optional archetype hint.")
    watchlist_add.add_argument("--json", action="store_true")
    watchlist_remove = watchlist_sub.add_parser("remove", help="Remove tickers.")
    watchlist_remove.add_argument("tickers", nargs="+")
    watchlist_remove.add_argument("--json", action="store_true")
    watchlist_list = watchlist_sub.add_parser("list", help="List watchlist.")
    watchlist_list.add_argument("--json", action="store_true")
    watchlist_seed = watchlist_sub.add_parser("seed", help="Add sample tickers.")
    watchlist_seed.add_argument("--json", action="store_true")

    evaluate_parser = subparsers.add_parser("evaluate", help="Evaluate one ticker.")
    evaluate_parser.add_argument("ticker")
    evaluate_parser.add_argument("--json", action="store_true")

    scan_parser = subparsers.add_parser("scan", help="Run the configured scan mode.")
    scan_parser.add_argument("--limit", type=int, default=None, help="Optional max ticker count.")
    scan_parser.add_argument("--watchlist", action="store_true", help="Force legacy watchlist scan.")
    scan_parser.add_argument("--json", action="store_true")

    select_parser = subparsers.add_parser("select", help="Select final portfolio candidates from the watchlist.")
    select_parser.add_argument("--max-positions", type=int, default=3)
    select_parser.add_argument("--max-total-size", type=float, default=75.0)
    select_parser.add_argument("--high-vol-max", type=int, default=1)
    select_parser.add_argument("--json", action="store_true")

    morning_parser = subparsers.add_parser("morning", help="Alias for scan.")
    morning_parser.add_argument("--json", action="store_true")

    weekly_parser = subparsers.add_parser("weekly", help="Alias for scan.")
    weekly_parser.add_argument("--json", action="store_true")

    admin_parser = subparsers.add_parser("admin", help="Operator/admin commands.")
    admin_sub = admin_parser.add_subparsers(dest="admin_command")
    admin_logs = admin_sub.add_parser("logs", help="Show recent operation logs.")
    admin_logs.add_argument("--limit", type=int, default=20)
    admin_logs.add_argument("--json", action="store_true")
    admin_failures = admin_sub.add_parser("failures", help="Show recent failed jobs.")
    admin_failures.add_argument("--limit", type=int, default=20)
    admin_failures.add_argument("--json", action="store_true")
    admin_export = admin_sub.add_parser("export", help="Export local data to JSON.")
    admin_export.add_argument("--out", required=True)
    admin_export.add_argument("--json", action="store_true")
    admin_delete = admin_sub.add_parser("delete-data", help="Delete local app data.")
    admin_delete.add_argument("--confirm", required=False)
    admin_delete.add_argument("--json", action="store_true")

    self_test_parser = subparsers.add_parser("self-test", help="Run a lightweight local smoke check.")
    self_test_parser.add_argument("--json", action="store_true")

    saas_parser = subparsers.add_parser("saas-readiness", help="Show blockers for 1000-user SaaS readiness.")
    saas_parser.add_argument("--json", action="store_true")

    benchmark_parser = subparsers.add_parser("benchmark", help="Measure local screening throughput.")
    benchmark_parser.add_argument("--repeat", type=int, default=200)
    benchmark_parser.add_argument("--json", action="store_true")

    web_parser = subparsers.add_parser("web", help="Run the local web dashboard.")
    web_parser.add_argument("--host", default="127.0.0.1")
    web_parser.add_argument("--port", type=int, default=8765)

    worker_parser = subparsers.add_parser("worker", help="Run durable background workers.")
    worker_sub = worker_parser.add_subparsers(dest="worker_command")
    worker_once = worker_sub.add_parser("run-once", help="Process queued scan jobs once.")
    worker_once.add_argument("--limit", type=int, default=5)
    worker_once.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0

    try:
        result = dispatch(args)
    except AppError as exc:
        result = OperationResult.failure(
            exc.message,
            status_code=exc.status_code,
            code=exc.code,
            detail=exc.detail,
        )
        _capture_failure(argv, exc.code, exc.message)
    except Exception as exc:  # pragma: no cover - safety net
        result = OperationResult.failure(
            "Unexpected internal error. See admin failures or logs for details.",
            status_code=500,
            code="INTERNAL_ERROR",
        )
        _capture_failure(argv, "INTERNAL_ERROR", str(exc))

    print_result(result, json_output=bool(getattr(args, "json", False)))
    return 0 if result.ok else 1


def dispatch(args: argparse.Namespace) -> OperationResult:
    config = load_config()

    if args.command == "doctor":
        report = doctor_report(config)
        # Listing settings does not tell an operator whether a scan will reach a
        # selection. Open a connection when one exists so the watchlist counts as a
        # universe, but never fail the check just because the database is not there yet.
        try:
            with connect(config) as conn:
                report["scan_pipeline"] = scan_pipeline_readiness(config, conn)
        except Exception:
            report["scan_pipeline"] = scan_pipeline_readiness(config)
        return OperationResult.success("Configuration check completed.", report)

    if args.command == "saas-readiness":
        data = get_saas_readiness()
        return OperationResult.success("SaaS readiness checked.", data)

    if args.command == "benchmark":
        with connect(config) as conn:
            ensure_initialized(conn)
            tickers = [item["ticker"] for item in list_watchlist(conn)]
        if not tickers:
            tickers = list(SAMPLE_TICKERS)
        data = benchmark_scoring(config, tickers, repeat=args.repeat)
        return OperationResult.success("Benchmark completed.", data)

    if args.command == "web":
        run_web(args.host, args.port)
        return OperationResult.success("Web server stopped.")

    with connect(config) as conn:
        if args.command == "init-db":
            init_db(conn)
            if config.user_auth_enabled:
                init_saas_db(conn)
            seeded: dict[str, Any] | None = None
            if args.seed:
                seeded = seed_watchlist(conn, SAMPLE_TICKERS)
            log_operation(conn, "init-db", "success", "Database initialized.", {"seeded": seeded})
            append_file_log(config, "INFO", "Database initialized.", {"seeded": seeded})
            return OperationResult.success(
                "Database initialized.",
                {
                    "database_backend": config.database_backend,
                    "database_path": config.database_path if config.database_backend == "sqlite" else "<postgresql>",
                    "seeded": seeded,
                },
                status_code=201,
            )

        ensure_initialized(conn)

        if args.command == "watchlist":
            if args.watchlist_command == "add":
                data = add_watchlist(conn, args.tickers, args.hint)
                log_operation(conn, "watchlist add", "success", "Watchlist updated.", data)
                return OperationResult.success("Watchlist updated.", data)
            if args.watchlist_command == "remove":
                data = remove_watchlist(conn, args.tickers)
                log_operation(conn, "watchlist remove", "success", "Watchlist updated.", data)
                return OperationResult.success("Watchlist updated.", data)
            if args.watchlist_command == "list":
                data = list_watchlist(conn)
                message = "Watchlist is empty. Add tickers with: python -m vcb_alt watchlist add PLTR"
                if data:
                    message = "Watchlist loaded."
                return OperationResult.success(message, {"items": data, "count": len(data)})
            if args.watchlist_command == "seed":
                data = seed_watchlist(conn, SAMPLE_TICKERS)
                log_operation(conn, "watchlist seed", "success", "Sample watchlist seeded.", data)
                return OperationResult.success("Sample watchlist seeded.", data)
            raise AppError("Unknown watchlist command.", detail="Use add, remove, list, or seed.")

        if args.command == "evaluate":
            ticker = validate_ticker(args.ticker)
            result = evaluate_snapshot(get_snapshot(config, ticker))
            save_evaluation(conn, result)
            log_operation(conn, "evaluate", "success", f"Evaluated {ticker}.", {"ticker": ticker})
            return OperationResult.success(f"Evaluated {ticker}.", {"evaluation": result.to_dict()})

        if args.command in {"scan", "morning", "weekly"}:
            if config.scan_mode == "market_universe" and not getattr(args, "watchlist", False):
                return _scan_market_universe(config, conn, limit=getattr(args, "limit", None))
            return _scan_watchlist(config, conn, command=args.command, limit=getattr(args, "limit", None))

        if args.command == "select":
            if config.scan_mode == "market_universe":
                report = scan_market_universe(config, conn=conn, max_positions=args.max_positions)
                for item in report.evaluations:
                    save_evaluation(conn, item)
                log_operation(
                    conn,
                    "market universe select",
                    "success" if not report.failures else "partial_success",
                    f"Selected {len(report.selection.selected)} candidates from market universe.",
                    {"elapsed_ms": report.elapsed_ms, "prefilter_count": report.prefilter.get("count", 0)},
                )
                return OperationResult.success(
                    "Market-universe portfolio candidate selection completed.",
                    report.to_api_dict(),
                )
            evaluations, failures = _evaluate_watchlist(config, conn, command="select")
            selection = select_portfolio(
                evaluations,
                max_positions=args.max_positions,
                max_total_size_pct=args.max_total_size,
                high_vol_max=args.high_vol_max,
            )
            log_operation(
                conn,
                "select",
                "success" if not failures else "partial_success",
                f"Selected {len(selection.selected)} candidates with {len(failures)} scan failures.",
                {"selected": [item.ticker for item in selection.selected], "failures": len(failures)},
            )
            return OperationResult.success(
                "Portfolio candidate selection completed.",
                {"selection": selection.to_dict(), "failures": failures},
            )

        if args.command == "admin":
            if args.admin_command == "logs":
                data = recent_logs(conn, limit=args.limit)
                return OperationResult.success("Recent operation logs loaded.", {"items": data, "count": len(data)})
            if args.admin_command == "failures":
                data = recent_failures(conn, limit=args.limit)
                return OperationResult.success("Recent failed jobs loaded.", {"items": data, "count": len(data)})
            if args.admin_command == "export":
                payload = export_data(conn)
                out_path = Path(args.out)
                if not out_path.is_absolute():
                    out_path = config.root_dir / out_path
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
                log_operation(conn, "admin export", "success", "Local data exported.", {"out": str(out_path)})
                return OperationResult.success("Local data exported.", {"out": str(out_path)})
            if args.admin_command == "delete-data":
                require_delete_confirmation(args.confirm)
                deleted = delete_local_data(conn)
                append_file_log(config, "WARNING", "Local data deleted.", deleted)
                return OperationResult.success("Local data deleted.", {"deleted": deleted})
            raise AppError("Unknown admin command.", detail="Use logs, failures, export, or delete-data.")

        if args.command == "self-test":
            sample = evaluate_snapshot(get_snapshot(config, "PLTR"))
            data = {
                "config": doctor_report(config),
                "sample_evaluation": sample.to_dict(),
                "database_initialized": True,
            }
            log_operation(conn, "self-test", "success", "Self-test completed.", {"ticker": "PLTR"})
            return OperationResult.success("Self-test completed.", data)

        if args.command == "worker":
            if args.worker_command == "run-once":
                if not config.scan_queue_enabled:
                    raise AppError("Scan queue is not enabled.", detail="Set VCB_ALT_SCAN_QUEUE_ENABLED=true.")
                init_saas_db(conn)
                data = run_queued_scan_jobs(config, conn, limit=validate_job_limit(args.limit))
                return OperationResult.success("Worker run completed.", data)
            raise AppError("Unknown worker command.", detail="Use worker run-once.")

    raise AppError("Unknown command.")


def _scan_watchlist(config: Any, conn: Any, *, command: str, limit: int | None = None) -> OperationResult:
    evaluations, failures = _evaluate_watchlist(config, conn, command=command, limit=limit)
    if not evaluations and not failures:
        return OperationResult.success(
            "Watchlist is empty. Add tickers with: python -m vcb_alt watchlist add PLTR",
            {"state": "empty", "items": [], "count": 0},
        )
    status = "success" if not failures else "partial_success"
    log_operation(
        conn,
        command,
        status,
        f"Scanned {len(evaluations)} tickers with {len(failures)} failures.",
        {"evaluated": len(evaluations), "failures": len(failures)},
    )
    return OperationResult.success(
        "Scan completed.",
        {"state": status, "items": [item.to_dict() for item in evaluations], "failures": failures, "count": len(evaluations)},
    )


def _scan_market_universe(config: Any, conn: Any, *, limit: int | None = None) -> OperationResult:
    report = scan_market_universe(config, conn=conn, universe_limit=limit)
    for item in report.evaluations:
        save_evaluation(conn, item)
    status = "success" if not report.failures else "partial_success"
    log_operation(
        conn,
        "market universe scan",
        status,
        f"Scanned {report.universe.get('count', 0)} market symbols and scored {len(report.evaluations)} candidates.",
        {"elapsed_ms": report.elapsed_ms, "prefilter_count": report.prefilter.get("count", 0)},
    )
    return OperationResult.success("Market-universe scan completed.", report.to_api_dict())


def _evaluate_watchlist(config: Any, conn: Any, *, command: str, limit: int | None = None) -> tuple[list[Any], list[dict[str, Any]]]:
    items = list_watchlist(conn)
    if limit is not None:
        items = items[: max(0, limit)]
    if not items:
        return [], []

    evaluations: list[Any] = []
    failures: list[dict[str, Any]] = []
    for item in items:
        ticker = item["ticker"]
        try:
            result = evaluate_snapshot(get_snapshot(config, ticker))
            save_evaluation(conn, result)
            evaluations.append(result)
        except AppError as exc:
            failure = {"ticker": ticker, "code": exc.code, "message": exc.message}
            record_failure(conn, command, exc.code, exc.message, failure)
            failures.append(failure)
    return evaluations, failures


def _capture_failure(argv: list[str], code: str, message: str) -> None:
    try:
        config = load_config()
        append_file_log(config, "ERROR", message, {"command": " ".join(argv), "code": code})
        with connect(config) as conn:
            ensure_initialized(conn)
            record_failure(conn, " ".join(argv), code, message)
    except Exception:
        return


def print_result(result: OperationResult, *, json_output: bool = False) -> None:
    if json_output:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
        return

    prefix = "OK" if result.ok else "ERROR"
    print(f"{prefix} [{result.status_code}] {result.message}")
    if not result.ok:
        if result.error and result.error.get("detail"):
            print(f"Detail: {result.error['detail']}")
        return

    data = result.data
    if not data:
        return
    if isinstance(data, dict) and "evaluation" in data:
        _print_evaluation(data["evaluation"])
        return
    if isinstance(data, dict) and "selection" in data:
        _print_selection(data["selection"], data.get("failures", []))
        return
    if isinstance(data, dict) and "ready_for_1000_users" in data:
        _print_saas_readiness(data)
        return
    if isinstance(data, dict) and "items" in data:
        _print_items(data)
        return
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def _print_evaluation(evaluation: dict[str, Any]) -> None:
    print(f"Ticker: {evaluation['ticker']} - {evaluation['company_name']}")
    print(f"Status: {evaluation['decision_label']} ({evaluation['status']} / {evaluation['setup_strength']})")
    print(f"Scoring version: {evaluation['scoring_version']}")
    print(f"Data source: {evaluation['source']} as of {evaluation['data_as_of']}")
    print(f"Primary: {evaluation['primary_archetype_label']} ({evaluation['primary_archetype']})")
    print(f"Combined score: {evaluation['combined_score']}")
    print(f"Can enter: {evaluation['can_enter']}")
    print(f"Suggested size: {evaluation['suggested_size_pct']}%")
    print(f"Risk marker: {evaluation['stop_loss']}")
    print("Rationale:")
    for item in evaluation["rationale"]:
        print(f"- {item}")
    print("Warnings:")
    for item in evaluation["warnings"]:
        print(f"- {item}")


def _print_items(data: dict[str, Any]) -> None:
    print(f"Count: {data.get('count', 0)}")
    items = data.get("items", [])
    if not items:
        return
    for item in items:
        if "ticker" in item and "combined_score" in item:
            print(f"- {item['ticker']}: {item['status']} score={item['combined_score']}")
        elif "ticker" in item:
            print(f"- {item['ticker']}")
        else:
            print(f"- {json.dumps(item, ensure_ascii=False, sort_keys=True)}")


def _print_saas_readiness(data: dict[str, Any]) -> None:
    print(f"Decision: {data['decision']}")
    print(f"Ready for 1000 users: {data['ready_for_1000_users']}")
    print(f"P0 blockers: {data['p0_blocker_count']}")
    print(data["summary"])
    for item in data["items"]:
        print(f"- {item['priority']} {item['label']}: {item['status']}")


def _print_selection(selection: dict[str, Any], failures: list[dict[str, Any]]) -> None:
    print(f"Selected: {len(selection['selected'])}/{selection['max_positions']}")
    print(f"Total suggested size: {selection['total_size_pct']}% / {selection['max_total_size_pct']}%")
    print(f"Data provider: {selection['data_provider']}")
    for index, item in enumerate(selection["selected"], start=1):
        print(
            f"{index}. {item['ticker']} - {item['primary_archetype_label']} "
            f"score={item['combined_score']} size={item['suggested_size_pct']}% "
            f"label={item['decision_label']}"
        )
    if selection["rejected"]:
        print("Rejected / not selected:")
        for item in selection["rejected"]:
            print(f"- {item['ticker']}: {item['reason']}")
    if failures:
        print("Failures:")
        for item in failures:
            print(f"- {item['ticker']}: {item['message']}")
