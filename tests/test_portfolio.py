from __future__ import annotations

import unittest

from vcb_alt.models import EvaluationResult
from vcb_alt.portfolio import select_portfolio
from vcb_alt.sample_data import get_snapshot
from vcb_alt.scoring import evaluate_snapshot


class PortfolioTests(unittest.TestCase):
    def test_select_portfolio_applies_position_and_high_vol_limits(self) -> None:
        evaluations = [
            evaluate_snapshot(get_snapshot(ticker))
            for ticker in ["PLTR", "VST", "MSTR", "GME", "RGTI", "SMMT", "AAPL"]
        ]
        selection = select_portfolio(evaluations, max_positions=3, max_total_size_pct=75, high_vol_max=1)
        selected = [item.ticker for item in selection.selected]
        self.assertEqual(len(selected), 3)
        self.assertIn("PLTR", selected)
        self.assertIn("VST", selected)
        self.assertLessEqual(selection.total_size_pct, 75)
        rejected_reasons = {item["ticker"]: item["reason"] for item in selection.rejected}
        self.assertEqual(rejected_reasons["AAPL"], "Score below entry threshold.")

    def test_technical_momentum_can_fill_multiple_slots(self) -> None:
        evaluations = [
            make_result("AAPL", 72),
            make_result("MSTR", 62),
            make_result("NVDA", 61),
        ]
        selection = select_portfolio(evaluations, max_positions=3)
        self.assertEqual([item.ticker for item in selection.selected], ["AAPL", "MSTR", "NVDA"])

    def test_equal_scores_prefer_higher_data_coverage(self) -> None:
        evaluations = [
            make_result("LOW", 80, coverage=35),
            make_result("HIGH", 80, coverage=100),
            make_result("MID", 80, coverage=65),
        ]
        selection = select_portfolio(evaluations, max_positions=3)
        self.assertEqual([item.ticker for item in selection.selected], ["HIGH", "MID", "LOW"])


def make_result(ticker: str, score: int, *, coverage: int = 0) -> EvaluationResult:
    return EvaluationResult(
        ticker=ticker,
        company_name=ticker,
        scoring_version="test",
        primary_archetype="G_TECHNICAL_MOMENTUM",
        primary_archetype_label="Technical Momentum",
        archetype_scores={"G_TECHNICAL_MOMENTUM": score},
        complexity_modifier=0,
        combined_score=score,
        setup_strength="SETUP",
        can_enter=True,
        suggested_size_pct=10.0,
        stop_loss=90.0,
        status="WATCH",
        decision_label="Watchlist candidate",
        source="yahoo",
        data_coverage_score=coverage,
    )


if __name__ == "__main__":
    unittest.main()
