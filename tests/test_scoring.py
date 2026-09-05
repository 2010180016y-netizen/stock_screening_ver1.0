from __future__ import annotations

import unittest

from vcb_alt.models import StockSnapshot
from vcb_alt.sample_data import get_snapshot
from vcb_alt.scoring import (
    ARCHETYPE_MAX_POINTS,
    CONFIRMATION_BONUS_MAX,
    ENTRY_SCORE_THRESHOLD,
    score_confirmation_bonus,
    _raw_archetype_points,
    evaluate_snapshot,
    score_archetypes,
    score_complexity_modifier,
)


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


class ArchetypeNormalisationTests(unittest.TestCase):
    """Raw sums were clipped at 100, which cost discrimination and skewed max().

    Eight of a 24-name corpus scored exactly 100, so at the top the score stopped
    separating anything and a one-point move decided a portfolio slot. The archetypes also
    award different totals - 110 to 130 - and max() compared those directly, so
    C_QUANTUM's larger denominator beat B/D/E for equivalent evidence.
    """

    IDEAL: dict[str, dict[str, object]] = {
        "A_AI_TECH": dict(
            revenue_surprise_pct=99.0, revenue_acceleration_pp=50.0, sector_rs_12w_pp=50.0,
            insider_buy_count_90d=9, breakout_volume_ratio=5.0, forward_guidance_raised=True,
            analyst_revision_score=99.0, trend_template_score=100,
        ),
        "B_CRYPTO_PIVOT": dict(
            btc_6m_return_pct=99.0, news_catalyst_30d=True, mining_capacity_increase_pct=99.0,
            above_200dma=True, volume_z_score_30d=9.0, drawdown_recovery_pct=99.0, surge_score=100,
        ),
        "C_QUANTUM": dict(
            float_shares_m=30.0, market_cap_m=300.0, news_catalyst_30d=True,
            peer_30d_return_pct=99.0, volume_z_score_30d=9.0, surge_score=100,
        ),
        "D_BIOTECH": dict(
            fda_milestone_90d=True, insider_buy_count_90d=9, short_interest_pct=5.0,
            market_cap_m=300.0, news_catalyst_30d=True, trend_template_score=100,
        ),
        "E_SHORT_SQUEEZE": dict(
            short_interest_pct=30.0, days_to_cover=9.0, borrow_rate_pct=99.0,
            call_oi_change_pct=999.0, volume_z_score_30d=9.0, news_catalyst_30d=True, surge_score=100,
        ),
        "F_PICK_SHOVEL": dict(
            data_center_narrative=True, sector_rs_12w_pp=50.0, above_200dma=True,
            eps_revision_pct=99.0, revenue_acceleration_pp=50.0, breakout_volume_ratio=5.0,
            trend_template_score=100,
        ),
    }

    def _ideal(self, archetype: str) -> StockSnapshot:
        base: dict[str, object] = {
            "ticker": "MAX", "company_name": "Max", "price": 5.0,
            "source": "yahoo", "data_as_of": "2026-09-01",
        }
        base.update(self.IDEAL[archetype])
        return StockSnapshot(**base)  # type: ignore[arg-type]

    def test_archetype_maxima_are_current(self) -> None:
        """ARCHETYPE_MAX_POINTS must match what the formulas can actually award.

        If a weight in score_archetypes changes and this constant does not, every score
        for that archetype is quietly scaled against the wrong denominator. This fails
        loudly instead, and the number in the message is the one to write down.
        """
        for archetype in self.IDEAL:
            with self.subTest(archetype=archetype):
                raw = _raw_archetype_points(self._ideal(archetype))[archetype]
                self.assertEqual(
                    raw, ARCHETYPE_MAX_POINTS[archetype],
                    f"{archetype} can award {raw} points; update ARCHETYPE_MAX_POINTS",
                )

    def test_a_maxed_archetype_scores_100(self) -> None:
        for archetype in self.IDEAL:
            with self.subTest(archetype=archetype):
                self.assertEqual(score_archetypes(self._ideal(archetype))[archetype], 100)

    def test_equivalent_evidence_scores_alike_across_archetypes(self) -> None:
        """Half of each archetype's available evidence should score about the same.

        Before normalisation the same fraction produced different scores depending on how
        many points the archetype happened to award.
        """
        halves = {
            archetype: score_archetypes(self._ideal(archetype))[archetype]
            for archetype in self.IDEAL
        }
        self.assertEqual(set(halves.values()), {100})

    def test_strong_names_are_still_distinguishable(self) -> None:
        """The ceiling used to collapse every strong name onto the same number."""
        scores = sorted(
            evaluate_snapshot(get_snapshot(ticker)).combined_score
            for ticker in ("PLTR", "MSTR", "RGTI", "SMMT", "VST", "GME")
        )
        self.assertGreater(len(set(scores)), 1, "strong names all collapsed to one score")
        self.assertLess(max(scores), 100, "a name is still pinned to the ceiling")


class ConfirmationBonusTests(unittest.TestCase):
    """max() kept the best archetype and discarded the rest.

    A name whose case was independently made by two archetypes ranked exactly level with
    one that only worked under a single thesis. Corroboration is evidence; it was being
    thrown away.
    """

    def test_a_second_archetype_below_the_entry_bar_counts_for_nothing(self) -> None:
        """Shared evidence would otherwise creep back in.

        A catalyst flag appears in four archetypes, so a low bar would pay a name twice
        for one fact - the same defect removed from the complexity modifier.
        """
        for second in (0, 20, 54):
            with self.subTest(second=second):
                scores = {"A_AI_TECH": 80, "B_CRYPTO_PIVOT": second}
                self.assertEqual(score_confirmation_bonus(scores, "A_AI_TECH"), 0)

    def test_credit_scales_with_the_second_archetype_and_is_capped(self) -> None:
        at_bar = score_confirmation_bonus({"A_AI_TECH": 80, "F_PICK_SHOVEL": ENTRY_SCORE_THRESHOLD}, "A_AI_TECH")
        midway = score_confirmation_bonus({"A_AI_TECH": 80, "F_PICK_SHOVEL": 78}, "A_AI_TECH")
        maxed = score_confirmation_bonus({"A_AI_TECH": 80, "F_PICK_SHOVEL": 100}, "A_AI_TECH")
        self.assertEqual(at_bar, 0)
        self.assertGreater(midway, at_bar)
        self.assertEqual(maxed, CONFIRMATION_BONUS_MAX)
        self.assertLess(midway, maxed)

    def test_the_primary_archetype_never_confirms_itself(self) -> None:
        self.assertEqual(score_confirmation_bonus({"A_AI_TECH": 100}, "A_AI_TECH"), 0)

    def test_two_theses_outrank_one_at_equal_primary_strength(self) -> None:
        single = {"A_AI_TECH": 70, "F_PICK_SHOVEL": 20}
        double = {"A_AI_TECH": 70, "F_PICK_SHOVEL": 70}
        self.assertEqual(score_confirmation_bonus(single, "A_AI_TECH"), 0)
        self.assertGreater(score_confirmation_bonus(double, "A_AI_TECH"), 0)
