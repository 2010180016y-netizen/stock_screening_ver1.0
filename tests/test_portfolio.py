from __future__ import annotations

import unittest

from vcb_alt.models import HIGH_VOL_ARCHETYPES, EvaluationResult, StockSnapshot
from vcb_alt.portfolio import select_portfolio
from vcb_alt.sample_data import get_snapshot
from vcb_alt.scoring import ENTRY_SCORE_THRESHOLD, MIN_DATA_COVERAGE_FOR_ENTRY, evaluate_snapshot


class PortfolioTests(unittest.TestCase):
    def _sample_selection(self, **kwargs: object):
        evaluations = [
            evaluate_snapshot(get_snapshot(ticker))
            for ticker in ["PLTR", "VST", "MSTR", "GME", "RGTI", "SMMT", "AAPL"]
        ]
        options = {"max_positions": 3, "max_total_size_pct": 75, "high_vol_max": 1}
        options.update(kwargs)
        return select_portfolio(evaluations, **options)  # type: ignore[arg-type]

    def test_select_portfolio_applies_position_and_high_vol_limits(self) -> None:
        """The limits, not which names happen to win them.

        This used to assert that PLTR and VST were selected. That held only because every
        strong sample name scored exactly 100 and the order came from tie-breaks; once
        scores were normalised and started separating, the assertion failed without any
        limit being violated. The limits are what this test is for.
        """
        selection = self._sample_selection()
        selected = selection.selected
        self.assertEqual(len(selected), 3)
        self.assertLessEqual(selection.total_size_pct, 75)

        archetypes = [item.primary_archetype for item in selected]
        self.assertEqual(len(archetypes), len(set(archetypes)), "duplicate archetype selected")
        high_vol = [name for name in archetypes if name in HIGH_VOL_ARCHETYPES]
        self.assertLessEqual(len(high_vol), 1)

        scores = [item.combined_score for item in selected]
        self.assertEqual(scores, sorted(scores, reverse=True), "selection is not score-ordered")

        rejected_reasons = {item["ticker"]: item["reason"] for item in selection.rejected}
        self.assertEqual(rejected_reasons["AAPL"], "Score below entry threshold.")

    def test_sample_selection_is_recorded(self) -> None:
        """A deliberate record of what the current engine picks from the sample set.

        Not a claim that this is the right answer - there is no outcome data to judge that
        yet. It exists so a scoring change shows up here as an explicit decision rather
        than sliding through unnoticed. Update it together with SCORING_VERSION, and use
        tools/scoring_diff.py to see what moved.
        """
        selected = [item.ticker for item in self._sample_selection().selected]
        self.assertEqual(selected, ["RGTI", "MSTR", "VST"])

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
