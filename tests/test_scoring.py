from __future__ import annotations

import unittest

from vcb_alt.sample_data import get_snapshot
from vcb_alt.scoring import evaluate_snapshot, score_archetypes


class ScoringTests(unittest.TestCase):
    def test_pltr_sample_is_strong_ai_candidate(self) -> None:
        result = evaluate_snapshot(get_snapshot("PLTR"))
        self.assertEqual(result.primary_archetype, "A_AI_TECH")
        self.assertEqual(result.setup_strength, "STRONG_SETUP")
        self.assertTrue(result.can_enter)
        self.assertGreaterEqual(result.combined_score, 70)
        self.assertEqual(result.decision_label, "High-scoring watchlist candidate")
        self.assertEqual(result.public_label, "High-priority review candidate")
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
