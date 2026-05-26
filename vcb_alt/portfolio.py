from __future__ import annotations

from .models import HIGH_VOL_ARCHETYPES, EvaluationResult, PortfolioSelection

ARCHETYPE_DIVERSIFICATION_EXEMPT = {"G_TECHNICAL_MOMENTUM"}


def select_portfolio(
    evaluations: list[EvaluationResult],
    *,
    max_positions: int = 3,
    max_total_size_pct: float = 75.0,
    high_vol_max: int = 1,
) -> PortfolioSelection:
    eligible = sorted(
        [item for item in evaluations if item.can_enter],
        key=_selection_sort_key,
    )
    selected: list[EvaluationResult] = []
    rejected: list[dict[str, str]] = []
    selected_archetypes: set[str] = set()
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
        )
        if reason:
            rejected.append({"ticker": item.ticker, "reason": reason})
            continue
        selected.append(item)
        selected_archetypes.add(item.primary_archetype)
        total_size = round(total_size + item.suggested_size_pct, 2)
        if item.primary_archetype in HIGH_VOL_ARCHETYPES:
            high_vol_count += 1

    for item in evaluations:
        if not item.can_enter:
            rejected.append({"ticker": item.ticker, "reason": "Score below entry threshold."})

    return PortfolioSelection(
        selected=selected,
        rejected=rejected,
        max_positions=max_positions,
        max_total_size_pct=max_total_size_pct,
        total_size_pct=total_size,
        data_provider=_infer_provider(evaluations),
    )


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
) -> str | None:
    if selected_count >= max_positions:
        return "Portfolio slot limit reached."
    if item.primary_archetype in selected_archetypes and item.primary_archetype not in ARCHETYPE_DIVERSIFICATION_EXEMPT:
        return "Duplicate primary archetype avoided."
    if item.primary_archetype in HIGH_VOL_ARCHETYPES and high_vol_count >= high_vol_max:
        return "High-volatility archetype limit reached."
    if total_size + item.suggested_size_pct > max_total_size_pct:
        return "Total suggested exposure limit reached."
    return None


def _infer_provider(evaluations: list[EvaluationResult]) -> str:
    providers = sorted({item.source for item in evaluations})
    return providers[0] if len(providers) == 1 else "mixed"
