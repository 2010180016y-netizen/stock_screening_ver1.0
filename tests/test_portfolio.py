from __future__ import annotations

import unittest

from vcb_alt.models import EvaluationResult, StockSnapshot
from vcb_alt.portfolio import select_portfolio
from vcb_alt.sample_data import get_snapshot
from vcb_alt.scoring import ENTRY_SCORE_THRESHOLD, MIN_DATA_COVERAGE_FOR_ENTRY, evaluate_snapshot


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
        status="MONITOR",
        decision_label="Monitoring candidate",
        source="yahoo",
        data_coverage_score=coverage,
    )


if __name__ == "__main__":
    unittest.main()


class BlockedReasonTests(unittest.TestCase):
    """Every blocked name used to report "Score below entry threshold".

    That included names that cleared the score and were held back by missing research
    data, which pointed the reader at the score when the fix was to add enrichment.
    """

    def _evaluation(self, ticker: str, score: int, coverage: int) -> EvaluationResult:
        snapshot = StockSnapshot(
            ticker=ticker, company_name=ticker, price=100.0, source="yahoo",
            data_quality="eod-market",
            trend_template_score=100.0 if score > 50 else 5.0,
            surge_score=60.0 if score > 50 else 0.0,
            breakout_volume_ratio=2.0 if score > 50 else 1.0,
        )
        result = evaluate_snapshot(snapshot)
        self.assertEqual(result.data_coverage_score, coverage)
        return result

    def test_coverage_block_is_reported_as_coverage_not_score(self) -> None:
        strong = self._evaluation("KO", 75, 35)
        self.assertGreaterEqual(strong.combined_score, ENTRY_SCORE_THRESHOLD)
        self.assertFalse(strong.can_enter)

        selection = select_portfolio([strong])
        reason = selection.rejected[0]["reason"]
        self.assertIn("coverage", reason.lower())
        self.assertIn(str(MIN_DATA_COVERAGE_FOR_ENTRY), reason)
        self.assertNotIn("Score below", reason)

    def test_genuine_low_score_still_says_so(self) -> None:
        weak = self._evaluation("TSLA", 17, 35)
        self.assertLess(weak.combined_score, ENTRY_SCORE_THRESHOLD)
        selection = select_portfolio([weak])
        self.assertEqual(selection.rejected[0]["reason"], "Score below entry threshold.")

    def test_reason_wording_does_not_change_what_is_selected(self) -> None:
        strong = self._evaluation("KO", 75, 35)
        weak = self._evaluation("TSLA", 17, 35)
        selection = select_portfolio([strong, weak])
        self.assertEqual(selection.selected, [])
        self.assertEqual(len(selection.rejected), 2)
