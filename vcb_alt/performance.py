from __future__ import annotations

from time import perf_counter

from .config import AppConfig
from .providers import get_snapshot
from .scoring import evaluate_snapshot


def benchmark_scoring(config: AppConfig, tickers: list[str], repeat: int = 100) -> dict[str, float | int]:
    if repeat <= 0:
        repeat = 1
    expanded = tickers * repeat
    start = perf_counter()
    for ticker in expanded:
        evaluate_snapshot(get_snapshot(config, ticker))
    elapsed_ms = (perf_counter() - start) * 1000
    total = len(expanded)
    return {
        "tickers": len(tickers),
        "repeat": repeat,
        "evaluations": total,
        "elapsed_ms": round(elapsed_ms, 2),
        "evals_per_second": round(total / (elapsed_ms / 1000), 2) if elapsed_ms > 0 else total,
        "ms_per_evaluation": round(elapsed_ms / total, 4) if total else 0,
    }

