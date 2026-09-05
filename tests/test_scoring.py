from __future__ import annotations

import unittest

from vcb_alt.models import StockSnapshot
from vcb_alt.sample_data import get_snapshot
from vcb_alt.scoring import evaluate_snapshot, score_archetypes, score_complexity_modifier


class ScoringTests(unittest.TestCase):
    def test_pltr_sample_is_strong_ai_candidate(self) -> None:
        result = evaluate_snapshot(get_snapshot("PLTR"))
        self.assertEqual(result.primary_archetype, "A_AI_TECH")
        self.assertEqual(result.setup_strength, "STRONG_SETUP")
        self.assertTrue(result.can_enter)
        self.assertGreaterEqual(result.combined_score, 70)
        self.assertEqual(result.status, "RESEARCH_CANDIDATE")
        self.assertEqual(result.decision_label, "High-scoring research candidate")
        self.assertEqual(result.public_label, "High-priority research candidate")
        self.assertTrue(result.scoring_version.startswith("mvp-market-"))

    def test_aapl_sample_is_not_entry_candidate(self) -> None:
        result = evaluate_snapshot(get_snapshot("AAPL"))
        self.assertFalse(result.can_enter)
        self.assertEqual(result.status, "WAIT")

    def test_archetype_scores_are_bounded(self) -> None:
        scores = score_archetypes(get_snapshot("GME"))
        self.assertTrue(all(0 <= score <= 100 for score in scores.values()))

    def test_unknown_ticker_uses_neutral_placeholder(self) -> None:
        result = evaluate_snapshot(get_snapshot("XYZ"))
        self.assertEqual(result.source, "sample-placeholder")
        self.assertFalse(result.can_enter)


if __name__ == "__main__":
    unittest.main()


class ComplexityModifierTests(unittest.TestCase):
    """The modifier must add evidence the primary archetype has not already priced.

    All four generic factors used to be paid unconditionally, so a squeeze-shaped name was
    paid twice for the same facts - short interest, catalyst, volume spike and call-option
    interest are all inside E_SHORT_SQUEEZE's own formula. Measured at the entry threshold
    that was worth +14 to +19 to a squeeze name and +0 to a fundamentals-shaped one.
    """

    def _snapshot(self, **fields: object) -> StockSnapshot:
        base = {
            "ticker": "TST", "company_name": "Test", "price": 12.0,
            "source": "yahoo", "data_as_of": "2026-09-01",
        }
        base.update(fields)
        return StockSnapshot(**base)  # type: ignore[arg-type]

    def test_a_squeeze_name_is_not_paid_twice_for_its_own_evidence(self) -> None:
        snapshot = self._snapshot(
            short_interest_pct=30.0, days_to_cover=6.0, borrow_rate_pct=60.0,
            call_oi_change_pct=250.0, volume_z_score_30d=3.0, news_catalyst_30d=True,
        )
        scores = score_archetypes(snapshot)
        self.assertEqual(max(scores, key=lambda key: scores[key]), "E_SHORT_SQUEEZE")
        # Every one of those facts is already in E's base score.
        self.assertEqual(score_complexity_modifier(snapshot, "E_SHORT_SQUEEZE"), 0)

    def test_the_same_evidence_still_counts_for_an_archetype_that_ignores_it(self) -> None:
        """G_TECHNICAL_MOMENTUM scores price and volume trend only.

        A catalyst, heavy short interest and a call-option surge are genuinely new
        information there, so they must still be paid.
        """
        snapshot = self._snapshot(
            news_catalyst_30d=True, short_interest_pct=30.0,
            call_oi_change_pct=250.0, volume_z_score_30d=3.0,
        )
        self.assertEqual(score_complexity_modifier(snapshot, "G_TECHNICAL_MOMENTUM"), 8 + 6 + 6 + 5)

    def test_biotech_keeps_its_own_short_interest_handling(self) -> None:
        """D_BIOTECH rewards a low short-interest band and penalises a high one.

        Paying it a generic high-short-interest bonus would work against its own formula,
        so it is excluded from that factor and its penalty still applies.
        """
        snapshot = self._snapshot(fda_milestone_90d=True, market_cap_m=300.0, short_interest_pct=30.0)
        self.assertEqual(score_complexity_modifier(snapshot, "D_BIOTECH"), -10)

    def test_archetype_specific_adjustments_are_unchanged(self) -> None:
        crypto = self._snapshot(btc_6m_return_pct=60.0)
        self.assertEqual(score_complexity_modifier(crypto, "B_CRYPTO_PIVOT"), 8)

        weak_sector = self._snapshot(sector_rs_12w_pp=-10.0)
        self.assertEqual(score_complexity_modifier(weak_sector, "A_AI_TECH"), -8)

    def test_a_fundamentals_name_and_a_squeeze_name_are_now_paid_alike(self) -> None:
        """Neither gets a bonus for evidence its own archetype already scores."""
        squeeze = self._snapshot(short_interest_pct=30.0, days_to_cover=6.0, news_catalyst_30d=True)
        fundamental = self._snapshot(
            revenue_surprise_pct=25.0, revenue_acceleration_pp=7.0, sector_rs_12w_pp=15.0,
        )
        self.assertEqual(score_complexity_modifier(squeeze, "E_SHORT_SQUEEZE"), 0)
        self.assertEqual(score_complexity_modifier(fundamental, "A_AI_TECH"), 0)
