"""Show exactly what a scoring change does to the numbers.

Changing scoring.py or portfolio.py changes what the product recommends, and the effect
is not visible from a diff: a two-line edit to a weight moves candidates across the entry
threshold in ways nobody can predict by reading. This records the engine's output over a
fixed corpus so a change can be stated in candidates gained and lost rather than asserted.

The corpus is deliberately built around the decision boundary. Names comfortably above or
below the entry threshold reveal nothing about a weight change; names within a few points
of it reveal everything.

Usage:
    python tools/scoring_diff.py --save baseline.json     # before the change
    python tools/scoring_diff.py --compare baseline.json  # after it
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vcb_alt.models import StockSnapshot  # noqa: E402
from vcb_alt.portfolio import select_portfolio  # noqa: E402
from vcb_alt.sample_data import SAMPLE_TICKERS, get_snapshot  # noqa: E402
from vcb_alt.scoring import (  # noqa: E402
    ENTRY_SCORE_THRESHOLD,
    evaluate_snapshot,
    score_archetypes,
    score_complexity_modifier,
)


def _synthetic(name: str, **fields: Any) -> tuple[str, StockSnapshot]:
    base = {
        "ticker": name.upper()[:5].replace("_", ""),
        "company_name": name,
        "price": 12.0,
        "source": "yahoo",
        "data_as_of": "2026-09-01",
    }
    base.update(fields)
    return name, StockSnapshot(**base)


def corpus() -> list[tuple[str, StockSnapshot]]:
    """Sample tickers plus shapes that sit on the entry boundary for each archetype."""
    rows = [(f"sample:{ticker}", get_snapshot(ticker)) for ticker in SAMPLE_TICKERS]
    rows += [
        _synthetic("squeeze_thin", short_interest_pct=30.0, days_to_cover=6.0),
        _synthetic("squeeze_catalyst", short_interest_pct=30.0, days_to_cover=6.0, news_catalyst_30d=True),
        _synthetic(
            "squeeze_full", short_interest_pct=30.0, days_to_cover=6.0, borrow_rate_pct=60.0,
            call_oi_change_pct=250.0, volume_z_score_30d=3.0, news_catalyst_30d=True,
        ),
        _synthetic("fundamental_thin", revenue_surprise_pct=25.0, revenue_acceleration_pp=7.0),
        _synthetic(
            "fundamental_mid", revenue_surprise_pct=25.0, revenue_acceleration_pp=7.0, sector_rs_12w_pp=15.0,
        ),
        _synthetic(
            "fundamental_full", revenue_surprise_pct=25.0, revenue_acceleration_pp=7.0,
            sector_rs_12w_pp=15.0, insider_buy_count_90d=3, forward_guidance_raised=True,
            analyst_revision_score=40.0,
        ),
        # Just under and just over every hard threshold the archetypes use.
        _synthetic("cliff_surprise_under", revenue_surprise_pct=19.9, revenue_acceleration_pp=7.0),
        _synthetic("cliff_surprise_over", revenue_surprise_pct=20.0, revenue_acceleration_pp=7.0),
        _synthetic("cliff_shortint_under", short_interest_pct=24.9, days_to_cover=6.0),
        _synthetic("cliff_shortint_over", short_interest_pct=25.0, days_to_cover=6.0),
        _synthetic("cliff_sector_under", sector_rs_12w_pp=9.9, revenue_surprise_pct=25.0),
        _synthetic("cliff_sector_over", sector_rs_12w_pp=10.0, revenue_surprise_pct=25.0),
        # Strong on several archetypes at once, versus strong on exactly one.
        _synthetic(
            "multi_archetype", revenue_surprise_pct=25.0, revenue_acceleration_pp=7.0,
            sector_rs_12w_pp=25.0, data_center_narrative=True, above_200dma=True,
            eps_revision_pct=25.0, breakout_volume_ratio=1.6,
        ),
        _synthetic("single_archetype", revenue_surprise_pct=25.0, revenue_acceleration_pp=7.0, sector_rs_12w_pp=15.0),
        _synthetic("crypto", btc_6m_return_pct=40.0, news_catalyst_30d=True, above_200dma=True),
        _synthetic("quantum", float_shares_m=30.0, market_cap_m=300.0, news_catalyst_30d=True, price=6.0),
        _synthetic("biotech", fda_milestone_90d=True, market_cap_m=300.0, news_catalyst_30d=True),
    ]
    return rows


def snapshot_rows() -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for label, snapshot in corpus():
        scores = score_archetypes(snapshot)
        primary = max(scores, key=lambda key: scores[key])
        result = evaluate_snapshot(snapshot)
        rows[label] = {
            "primary": primary,
            "base": scores[primary],
            "modifier": score_complexity_modifier(snapshot, primary),
            "combined": result.combined_score,
            "can_enter": result.can_enter,
            "size_pct": result.suggested_size_pct,
            "coverage": result.data_coverage_score,
        }
    return rows


def selection_row() -> dict[str, Any]:
    evaluations = [evaluate_snapshot(snapshot) for _, snapshot in corpus()]
    selection = select_portfolio(evaluations)
    return {
        "selected": [item.ticker for item in selection.selected],
        "total_size_pct": selection.total_size_pct,
    }


def build() -> dict[str, Any]:
    from vcb_alt.models import SCORING_VERSION

    return {
        "scoring_version": SCORING_VERSION,
        "entry_threshold": ENTRY_SCORE_THRESHOLD,
        "rows": snapshot_rows(),
        "selection": selection_row(),
    }


def compare(before: dict[str, Any], after: dict[str, Any]) -> int:
    print(f"scoring version: {before['scoring_version']} -> {after['scoring_version']}")
    old_rows, new_rows = before["rows"], after["rows"]

    changed = 0
    crossings: list[str] = []
    print(f"\n{'name':24} {'primary':20} {'base':>10} {'mod':>9} {'combined':>12} {'entry':>14}")
    for name in sorted(set(old_rows) | set(new_rows)):
        old, new = old_rows.get(name), new_rows.get(name)
        if old is None or new is None:
            print(f"{name:24} {'(corpus changed)':20}")
            continue
        if old == new:
            continue
        changed += 1
        entry = f"{old['can_enter']}->{new['can_enter']}" if old["can_enter"] != new["can_enter"] else ""
        if entry:
            crossings.append(f"{name}: {entry}")
        print(
            f"{name:24} {new['primary']:20} "
            f"{old['base']:>4}->{new['base']:<4} {new['modifier']:>+4} (was {old['modifier']:+}) "
            f"{old['combined']:>4}->{new['combined']:<4} {entry:>14}"
        )

    if not changed:
        print("(no row changed)")

    print(f"\nrows changed: {changed} of {len(new_rows)}")
    print(f"entry decisions flipped: {len(crossings)}")
    for line in crossings:
        print(f"  {line}")
    print(f"\nselection before: {before['selection']}")
    print(f"selection after:  {after['selection']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--save", metavar="PATH", help="Write the current engine's output.")
    group.add_argument("--compare", metavar="PATH", help="Compare a saved baseline against the current engine.")
    args = parser.parse_args()

    if args.save:
        Path(args.save).write_text(json.dumps(build(), indent=1, sort_keys=True), encoding="utf-8")
        print(f"saved {len(build()['rows'])} rows to {args.save}")
        return 0

    baseline = json.loads(Path(args.compare).read_text(encoding="utf-8"))
    return compare(baseline, build())


if __name__ == "__main__":
    raise SystemExit(main())
