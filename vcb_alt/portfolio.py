from __future__ import annotations

from .models import HIGH_VOL_ARCHETYPES, EvaluationResult, PortfolioSelection
from .scoring import ENTRY_SCORE_THRESHOLD, MIN_DATA_COVERAGE_FOR_ENTRY

ARCHETYPE_DIVERSIFICATION_EXEMPT = {"G_TECHNICAL_MOMENTUM"}

# Different archetypes are not always different bets. A_AI_TECH and F_PICK_SHOVEL are both
# funded by the same AI build-out - one buys the story, the other the infrastructure - and
# both are capped at 25%, so the archetype rule happily allowed a book that was half one
# trade. Grouping them lets the exposure cap see what the archetype rule cannot.
#
# Only the grouping that is obviously one bet is asserted here. The rest stay separate
# rather than inventing a factor taxonomy nothing in this repository can validate.
ARCHETYPE_RISK_FACTORS = {
    "A_AI_TECH": "ai_buildout",
    "F_PICK_SHOVEL": "ai_buildout",
    "B_CRYPTO_PIVOT": "crypto",
    "C_QUANTUM": "quantum",
    "D_BIOTECH": "biotech",
    "E_SHORT_SQUEEZE": "short_flow",
    "G_TECHNICAL_MOMENTUM": "price_momentum",
}

# Most of the book one shared risk factor may carry. Below the 75% total so that reaching
# the total cap requires more than one kind of bet.
MAX_FACTOR_EXPOSURE_PCT = 35.0


def select_portfolio(
    evaluations: list[EvaluationResult],
    *,
    max_positions: int = 3,
    max_total_size_pct: float = 75.0,
    high_vol_max: int = 1,
    max_factor_exposure_pct: float = MAX_FACTOR_EXPOSURE_PCT,
) -> PortfolioSelection:
    eligible = sorted(
        [item for item in evaluations if item.can_enter],
        key=_selection_sort_key,
    )
    selected: list[EvaluationResult] = []
    rejected: list[dict[str, str]] = []
    selected_archetypes: set[str] = set()
    factor_exposure: dict[str, float] = {}
    high_vol_count = 0
    total_size = 0.0

    for item in eligible:
        reason = _rejection_reason(
            item,
            selected_count=len(selected),
            max_positions=max_positions,
            selected_archetypes=selected_archetypes,
            high_vol_count=high_vol_count,
            high_vol_max=high_vol_max,
            total_size=total_size,
            max_total_size_pct=max_total_size_pct,
            factor_exposure=factor_exposure,
            max_factor_exposure_pct=max_factor_exposure_pct,
        )
        if reason:
            rejected.append({"ticker": item.ticker, "reason": reason})
            continue
        selected.append(item)
        selected_archetypes.add(item.primary_archetype)
        factor = ARCHETYPE_RISK_FACTORS.get(item.primary_archetype, item.primary_archetype)
        factor_exposure[factor] = round(factor_exposure.get(factor, 0.0) + item.suggested_size_pct, 2)
        total_size = round(total_size + item.suggested_size_pct, 2)
        if item.primary_archetype in HIGH_VOL_ARCHETYPES:
            high_vol_count += 1

    for item in evaluations:
        if not item.can_enter:
            rejected.append({"ticker": item.ticker, "reason": _blocked_reason(item)})

    return PortfolioSelection(
        selected=selected,
        rejected=rejected,
        max_positions=max_positions,
        max_total_size_pct=max_total_size_pct,
        total_size_pct=total_size,
        data_provider=_infer_provider(evaluations),
    )


def _blocked_reason(item: EvaluationResult) -> str:
    """Say which gate actually stopped a candidate.

    Every blocked name used to report "Score below entry threshold", including names that
    cleared the score comfortably and were held back by missing research data. That sent
    the reader looking at the score when the fix was to configure enrichment.
    """
    if item.combined_score >= ENTRY_SCORE_THRESHOLD and item.data_coverage_score < MIN_DATA_COVERAGE_FOR_ENTRY:
        return (
            f"Data coverage {item.data_coverage_score}/100 is below the {MIN_DATA_COVERAGE_FOR_ENTRY} "
            "required for selection; add research enrichment."
        )
    return "Score below entry threshold."


def _selection_sort_key(item: EvaluationResult) -> tuple[float, float, int, float, str]:
    # Tie-break on data coverage before portfolio ergonomics so equally scored names
    # with stronger market/fundamental/catalyst/positioning evidence rise first.
    high_vol_penalty = 1 if item.primary_archetype in HIGH_VOL_ARCHETYPES else 0
    return (
        -item.combined_score,
        -item.data_coverage_score,
        high_vol_penalty,
        -item.suggested_size_pct,
        item.ticker,
    )


def _rejection_reason(
    item: EvaluationResult,
    *,
    selected_count: int,
    max_positions: int,
    selected_archetypes: set[str],
    high_vol_count: int,
    high_vol_max: int,
    total_size: float,
    max_total_size_pct: float,
    factor_exposure: dict[str, float],
    max_factor_exposure_pct: float,
) -> str | None:
    if selected_count >= max_positions:
        return "Portfolio slot limit reached."
    if item.primary_archetype in selected_archetypes and item.primary_archetype not in ARCHETYPE_DIVERSIFICATION_EXEMPT:
        return "Duplicate primary archetype avoided."
    if item.primary_archetype in HIGH_VOL_ARCHETYPES and high_vol_count >= high_vol_max:
        return "High-volatility archetype limit reached."
    if total_size + item.suggested_size_pct > max_total_size_pct:
        return "Total suggested exposure limit reached."
    factor = ARCHETYPE_RISK_FACTORS.get(item.primary_archetype, item.primary_archetype)
    if factor_exposure.get(factor, 0.0) + item.suggested_size_pct > max_factor_exposure_pct:
        return (
            f"Shared risk factor '{factor}' would exceed {max_factor_exposure_pct:.0f}% of the book; "
            "a different archetype is not always a different bet."
        )
    return None


def _infer_provider(evaluations: list[EvaluationResult]) -> str:
    providers = sorted({item.source for item in evaluations})
    return providers[0] if len(providers) == 1 else "mixed"
