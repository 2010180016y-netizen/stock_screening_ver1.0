from __future__ import annotations

from .models import ARCHETYPE_CAPS, ARCHETYPE_LABELS, SCORING_VERSION, EvaluationResult, StockSnapshot
from .validation import validate_positive_number, validate_ticker

MIN_DATA_COVERAGE_FOR_ENTRY = 60
# The score a candidate must reach before the coverage gate is even considered.
ENTRY_SCORE_THRESHOLD = 55

# Which archetypes already price each cross-cutting factor in their own base score.
# score_complexity_modifier pays a factor only to archetypes absent from its set, so the
# same evidence is never counted twice. Read these against score_archetypes: every entry
# below corresponds to a line there that scores the same fact.
CATALYST_ARCHETYPES = frozenset({"B_CRYPTO_PIVOT", "C_QUANTUM", "D_BIOTECH", "E_SHORT_SQUEEZE"})
OPTION_INTEREST_ARCHETYPES = frozenset({"E_SHORT_SQUEEZE"})
# D_BIOTECH is here without scoring short interest positively: it scores a *low* band
# (0-10%) and separately penalises >=20%, so paying it a high-short-interest bonus would
# work against its own formula.
SHORT_INTEREST_ARCHETYPES = frozenset({"D_BIOTECH", "E_SHORT_SQUEEZE"})
VOLUME_SPIKE_ARCHETYPES = frozenset({"B_CRYPTO_PIVOT", "C_QUANTUM", "E_SHORT_SQUEEZE"})

# Most a second archetype can add. Small on purpose: corroboration is evidence, but the
# primary thesis is what the candidate is being put forward on.
CONFIRMATION_BONUS_MAX = 10


def _points(condition: bool, value: int) -> int:
    return value if condition else 0


def _ramped(value: float, threshold: float, points: int, *, band: float | None = None) -> int:
    """Award points on a ramp rather than a cliff.

    A hard comparison turns a rounding difference into a large award: a 20% revenue
    surprise scored 25 points and a 19.9% surprise scored nothing. Provider revisions of
    that size are routine, so candidates appeared and disappeared on noise.

    Full points at or above the threshold, nothing at or below threshold minus band, and
    a straight line between. The band defaults to a quarter of the threshold, which keeps
    the ramp proportional to the quantity being measured.

    Only continuous quantities use this. Booleans stay binary because they are, counts
    stay binary because a half-insider does not exist, and range conditions keep their own
    shape.
    """
    if band is None:
        band = abs(threshold) * 0.25
    if band <= 0:
        return points if value >= threshold else 0
    if value >= threshold:
        return points
    if value <= threshold - band:
        return 0
    return round(points * (value - (threshold - band)) / band)


def _clamp_score(value: int) -> int:
    return max(0, min(100, int(value)))


# The most points each archetype's formula can award, which is not 100 and is not the
# same across archetypes. Raw sums were simply clipped at 100, with two consequences:
# strong names piled up on the ceiling and stopped being distinguishable, and max() -
# which picks the primary archetype - compared scores drawn from different denominators,
# so C_QUANTUM's 130 available points beat B/D/E's 110 for equivalent evidence.
#
# Scores are now a percentage of what the archetype can award, so a score means "how much
# of this archetype's available evidence this name has" and the archetypes are comparable.
# test_archetype_maxima_are_current pins these against the formulas.
ARCHETYPE_MAX_POINTS = {
    "A_AI_TECH": 123,
    "B_CRYPTO_PIVOT": 110,
    "C_QUANTUM": 130,
    "D_BIOTECH": 110,
    "E_SHORT_SQUEEZE": 110,
    "F_PICK_SHOVEL": 115,
    "G_TECHNICAL_MOMENTUM": 100,
}


# G_TECHNICAL_MOMENTUM has two formulas with different totals; see _market_momentum_score.
MOMENTUM_MAX_POINTS = {"alpaca": 100, "end_of_day": 115}


def _normalise(raw: int, archetype: str) -> int:
    return _normalise_to(raw, ARCHETYPE_MAX_POINTS[archetype])


def _normalise_to(raw: int, maximum: int) -> int:
    return max(0, min(100, round(raw * 100 / maximum)))


def _setup_strength(score: int) -> str:
    if score >= 70:
        return "STRONG_SETUP"
    if score >= 50:
        return "SETUP"
    return "NO_SETUP"


def score_archetypes(snapshot: StockSnapshot) -> dict[str, int]:
    """Each archetype's evidence as a percentage of what that archetype can award."""
    raw = _raw_archetype_points(snapshot)
    return {
        name: value if name == "G_TECHNICAL_MOMENTUM" else _normalise(value, name)
        for name, value in raw.items()
    }


def _raw_archetype_points(snapshot: StockSnapshot) -> dict[str, int]:
    """Unnormalised sums. The maxima in ARCHETYPE_MAX_POINTS are the ceilings of these."""
    price = validate_positive_number(snapshot.price, "price")
    trend_bonus = min(15, max(0, snapshot.trend_template_score // 6))
    surge_bonus = min(10, max(0, snapshot.surge_score // 10))
    market_momentum_score = _market_momentum_score(snapshot)
    scores = {
        "A_AI_TECH": (
            _ramped(max(snapshot.revenue_surprise_pct, snapshot.earnings_surprise_pct), 20, 25)
            + _ramped(snapshot.revenue_acceleration_pp, 5, 20)
            + _ramped(snapshot.sector_rs_12w_pp, 10, 20)
            + _points(snapshot.insider_buy_count_90d >= 2, 15)
            + _ramped(snapshot.breakout_volume_ratio, 1.5, 10)
            + _points(snapshot.forward_guidance_raised, 10)
            + _ramped(snapshot.analyst_revision_score, 35, 8)
            + trend_bonus
        ),
        "B_CRYPTO_PIVOT": (
            _ramped(snapshot.btc_6m_return_pct, 30, 25)
            + _points(snapshot.news_catalyst_30d, 25)
            + _ramped(snapshot.mining_capacity_increase_pct, 30, 15)
            + _points(snapshot.above_200dma, 10)
            + _ramped(snapshot.volume_z_score_30d, 2.5, 15)
            + _ramped(snapshot.drawdown_recovery_pct, 20, 10)
            + surge_bonus
        ),
        "C_QUANTUM": (
            _points(snapshot.float_shares_m > 0 and snapshot.float_shares_m < 50, 20)
            + _points(0 < snapshot.market_cap_m < 500, 20)
            + _points(snapshot.news_catalyst_30d, 25)
            + _ramped(snapshot.peer_30d_return_pct, 30, 20)
            + _ramped(snapshot.volume_z_score_30d, 3, 15)
            + _points(1 <= price <= 10, 20)
            + surge_bonus
        ),
        "D_BIOTECH": (
            _points(snapshot.fda_milestone_90d, 30)
            + _points(snapshot.insider_buy_count_90d >= 2, 15)
            + _points(0 < snapshot.short_interest_pct < 10, 15)
            + _points(50 <= snapshot.market_cap_m <= 500, 20)
            + _points(snapshot.news_catalyst_30d, 20)
            + _ramped(snapshot.trend_template_score, 50, 10)
        ),
        "E_SHORT_SQUEEZE": (
            _ramped(snapshot.short_interest_pct, 25, 30)
            + _ramped(snapshot.days_to_cover, 5, 15)
            + _ramped(snapshot.borrow_rate_pct, 50, 15)
            + _ramped(snapshot.call_oi_change_pct, 200, 10)
            + _ramped(snapshot.volume_z_score_30d, 2.5, 15)
            + _points(snapshot.news_catalyst_30d, 15)
            + surge_bonus
        ),
        "F_PICK_SHOVEL": (
            _points(snapshot.data_center_narrative, 25)
            + _ramped(snapshot.sector_rs_12w_pp, 20, 20)
            + _points(snapshot.above_200dma, 15)
            + _ramped(max(snapshot.eps_revision_pct, snapshot.analyst_revision_score), 20, 20)
            + _ramped(snapshot.revenue_acceleration_pp, 3, 10)
            + _ramped(snapshot.breakout_volume_ratio, 1.4, 10)
            + trend_bonus
        ),
        "G_TECHNICAL_MOMENTUM": market_momentum_score,
    }
    return scores


def _market_momentum_score(snapshot: StockSnapshot) -> int:
    """Technical momentum, normalised so both data sources mean the same thing.

    This archetype has two formulas - one for intraday snapshots, one for end-of-day bars
    - and they do not award the same totals: 100 against 115. Both were clipped at 100, so
    an end-of-day name needed more of its available evidence to reach any given score than
    an intraday one, and the two were then compared directly against each other and
    against the six fundamental archetypes.
    """
    base_source = snapshot.source.split("+", 1)[0]
    if snapshot.data_quality.startswith("stale"):
        return 0
    if base_source.startswith("alpaca"):
        score = int(snapshot.surge_score * 0.45)
        score += _ramped(snapshot.intraday_change_pct, 2, 10)
        score += _ramped(snapshot.intraday_change_pct, 5, 15)
        score += _ramped(snapshot.breakout_volume_ratio, 1.5, 10)
        score += _ramped(snapshot.breakout_volume_ratio, 2.5, 10)
        score += _ramped(snapshot.intraday_volume, 500_000, 5)
        score += _ramped(snapshot.intraday_volume, 2_000_000, 5)
        return _normalise_to(score, MOMENTUM_MAX_POINTS["alpaca"])
    if base_source not in {"stooq", "yahoo"}:
        return 0
    score = int(snapshot.trend_template_score * 0.45)
    score += int(snapshot.surge_score * 0.25)
    score += _ramped(snapshot.return_12w_pct, 8, 10)
    score += _ramped(snapshot.return_12w_pct, 20, 10)
    # A threshold of zero has no proportional band, so this stays a plain comparison.
    score += _points(snapshot.sector_rs_12w_pp >= 0, 5)
    score += _ramped(snapshot.sector_rs_12w_pp, 10, 10)
    score += _ramped(snapshot.price_vs_50dma_pct, -3, 5)
    score += _ramped(snapshot.drawdown_52w_pct, -12, 5)
    return _normalise_to(score, MOMENTUM_MAX_POINTS["end_of_day"])


def score_complexity_modifier(snapshot: StockSnapshot, primary_archetype: str) -> int:
    """Cross-cutting evidence the primary archetype has not already priced.

    Each generic factor below is paid only when the primary archetype's own formula does
    not score it. Previously all four were paid unconditionally, so a squeeze-shaped name
    was paid twice for the same facts: short interest, catalyst, volume and call-option
    interest are all inside E_SHORT_SQUEEZE's base score, and were then re-paid here.

    Measured at the entry threshold, that was worth +14 to +19 to a squeeze-shaped name
    and +0 to a fundamentals-shaped one, with zero independent information behind the
    difference. A single boolean, news_catalyst_30d, was worth 15 base + 8 modifier = 23
    points to a squeeze name - 42% of the score needed to be selected.
    """
    modifier = 0
    for factor, value, priced_by in (
        (snapshot.news_catalyst_30d, 8, CATALYST_ARCHETYPES),
        (snapshot.call_oi_change_pct >= 200, 6, OPTION_INTEREST_ARCHETYPES),
        (snapshot.short_interest_pct >= 25, 6, SHORT_INTEREST_ARCHETYPES),
        (snapshot.volume_z_score_30d >= 2.5, 5, VOLUME_SPIKE_ARCHETYPES),
    ):
        if primary_archetype not in priced_by:
            modifier += _points(factor, value)

    if primary_archetype == "B_CRYPTO_PIVOT":
        modifier += _points(snapshot.btc_6m_return_pct >= 50, 8)
    if primary_archetype == "D_BIOTECH" and snapshot.short_interest_pct >= 20:
        modifier -= 10
    if primary_archetype in {"A_AI_TECH", "F_PICK_SHOVEL"} and snapshot.sector_rs_12w_pp < -5:
        modifier -= 8

    return max(-25, min(25, modifier))


def score_confirmation_bonus(archetype_scores: dict[str, int], primary_archetype: str) -> int:
    """Credit a name whose case is made by more than one archetype.

    max() keeps the best archetype and discards the rest, so a name that independently
    reaches a strong score under two different theses ranked exactly level with one that
    only worked under a single thesis. Corroboration from a second angle is evidence, and
    it was being thrown away.

    The bar is deliberately high: the second archetype must clear the entry threshold on
    its own before it counts for anything, and the credit is capped at
    CONFIRMATION_BONUS_MAX so the primary thesis still decides the score. Some evidence is
    shared between archetypes - a catalyst flag appears in four of them - so a lower bar
    would quietly re-introduce the double counting removed from the modifier.
    """
    others = [score for name, score in archetype_scores.items() if name != primary_archetype]
    second = max(others, default=0)
    if second < ENTRY_SCORE_THRESHOLD:
        return 0
    span = 100 - ENTRY_SCORE_THRESHOLD
    return min(CONFIRMATION_BONUS_MAX, round((second - ENTRY_SCORE_THRESHOLD) / span * CONFIRMATION_BONUS_MAX))


def evaluate_snapshot(snapshot: StockSnapshot) -> EvaluationResult:
    ticker = validate_ticker(snapshot.ticker)
    price = validate_positive_number(snapshot.price, "price")
    archetype_scores = score_archetypes(snapshot)
    primary_archetype = max(archetype_scores, key=archetype_scores.get)
    primary_score = archetype_scores[primary_archetype]
    modifier = score_complexity_modifier(snapshot, primary_archetype)
    confirmation = score_confirmation_bonus(archetype_scores, primary_archetype)
    combined_score = _clamp_score(primary_score + modifier + confirmation)
    setup = _setup_strength(combined_score)
    coverage = assess_data_coverage(snapshot)
    can_enter = combined_score >= ENTRY_SCORE_THRESHOLD and bool(coverage["allows_entry"])

    cap = ARCHETYPE_CAPS[primary_archetype]
    score_factor = 0.55 + (combined_score / 100) * 0.45
    suggested_size = round(min(cap, cap * score_factor), 2) if can_enter else 0.0
    stop_loss = round(price * 0.92, 2)

    rationale = [
        f"Primary archetype is {ARCHETYPE_LABELS[primary_archetype]} with base score {primary_score}.",
        f"Complexity modifier is {modifier}; combined score is {combined_score}.",
    ]
    if can_enter:
        rationale.append("Score is above the MVP portfolio-manager threshold of 55.")
    elif combined_score >= ENTRY_SCORE_THRESHOLD and not coverage["allows_entry"]:
        rationale.append("Score passed the numeric threshold, but final selection is blocked until enrichment data is present.")
    else:
        rationale.append("Score is below the MVP portfolio-manager threshold of 55; wait.")

    warnings = [
        "Decision support only; not a trading instruction.",
        "No automatic trading is performed.",
    ]
    if snapshot.source.startswith("sample"):
        warnings.append("Result uses sample/offline data, not live market data.")
    if primary_archetype in {"C_QUANTUM", "D_BIOTECH", "E_SHORT_SQUEEZE"}:
        warnings.append("High-volatility archetype: avoid stacking multiple simultaneous positions.")
    precision_notes = [
        f"Data quality: {snapshot.data_quality}.",
        f"Trend template score: {snapshot.trend_template_score}/100.",
        f"Surge score: {snapshot.surge_score}/100.",
    ]
    base_source = snapshot.source.split("+", 1)[0]
    has_research = bool(snapshot.enrichment_source)
    if base_source in {"stooq", "yahoo"} and not has_research:
        precision_notes.append(
            "Market-data provider supplies EOD price/volume only; "
            "fundamentals and catalysts remain unavailable unless research data is configured."
        )
    if has_research:
        enrichment_source = snapshot.enrichment_source or "data/enrichment.csv"
        enrichment_as_of = snapshot.enrichment_as_of or "unknown"
        precision_notes.append(f"Research enrichment applied from {enrichment_source} as of {enrichment_as_of}.")
    if snapshot.intraday_source:
        precision_notes.append(
            f"Intraday quote layer: {snapshot.intraday_source} price {snapshot.intraday_price} "
            f"as of {snapshot.intraday_as_of or 'unknown'}."
        )
    precision_notes.append(
        f"Data coverage: {coverage['score']}/100 ({coverage['label']}). {coverage['detail']}"
    )

    status = "RESEARCH_CANDIDATE" if can_enter and setup == "STRONG_SETUP" else "MONITOR" if can_enter else "WAIT"
    decision_label = _decision_label(status)
    public_label = _public_label(status)

    return EvaluationResult(
        ticker=ticker,
        company_name=snapshot.company_name,
        scoring_version=SCORING_VERSION,
        primary_archetype=primary_archetype,
        primary_archetype_label=ARCHETYPE_LABELS[primary_archetype],
        archetype_scores=archetype_scores,
        complexity_modifier=modifier,
        combined_score=combined_score,
        setup_strength=setup,
        can_enter=can_enter,
        suggested_size_pct=suggested_size,
        stop_loss=stop_loss,
        status=status,
        decision_label=decision_label,
        public_label=public_label,
        rationale=rationale,
        warnings=warnings,
        source=snapshot.source,
        data_as_of=snapshot.data_as_of,
        data_quality=snapshot.data_quality,
        precision_notes=precision_notes,
        data_coverage_score=int(coverage["score"]),
        data_coverage_label=str(coverage["label"]),
        data_coverage_detail=str(coverage["detail"]),
    )


def assess_data_coverage(snapshot: StockSnapshot) -> dict[str, object]:
    market_present = snapshot.price > 0 and (
        snapshot.trend_template_score > 0
        or snapshot.surge_score > 0
        or snapshot.return_12w_pct != 0
        or snapshot.breakout_volume_ratio != 1
        or bool(snapshot.intraday_source and snapshot.intraday_price > 0)
    )
    fundamental_present = any(
        [
            snapshot.market_cap_m > 0,
            snapshot.revenue_surprise_pct != 0,
            snapshot.earnings_surprise_pct != 0,
            snapshot.revenue_acceleration_pp != 0,
            snapshot.eps_revision_pct != 0,
            snapshot.analyst_revision_score != 0,
            snapshot.forward_guidance_raised,
        ]
    )
    catalyst_present = any(
        [
            snapshot.news_catalyst_30d,
            snapshot.news_headline_count_30d > 0,
            snapshot.filing_catalyst_30d,
            snapshot.fda_milestone_90d,
            snapshot.data_center_narrative,
            snapshot.btc_6m_return_pct != 0,
            snapshot.mining_capacity_increase_pct != 0,
            snapshot.peer_30d_return_pct != 0,
        ]
    )
    positioning_present = any(
        [
            snapshot.float_shares_m > 0,
            snapshot.insider_buy_count_90d > 0,
            snapshot.short_interest_pct > 0,
            snapshot.days_to_cover > 0,
            snapshot.borrow_rate_pct > 0,
            snapshot.call_open_interest > 0,
            snapshot.put_open_interest > 0,
            snapshot.analyst_buy_count > 0,
            snapshot.call_oi_change_pct != 0,
        ]
    )
    score = (
        _points(market_present, 35)
        + _points(fundamental_present, 25)
        + _points(catalyst_present, 20)
        + _points(positioning_present, 20)
    )
    missing = []
    if not market_present:
        missing.append("market price/volume")
    if not fundamental_present:
        missing.append("fundamentals/earnings")
    if not catalyst_present:
        missing.append("catalyst/news")
    if not positioning_present:
        missing.append("float/short/options/insider positioning")
    if score >= 80:
        label = "multi-source"
    elif score >= MIN_DATA_COVERAGE_FOR_ENTRY:
        label = "enriched"
    elif score >= 35:
        label = "price-volume-only"
    else:
        label = "insufficient"
    detail = (
        "Missing: " + ", ".join(missing) + "."
        if missing
        else "Required market, fundamental, catalyst, and positioning groups present."
    )
    return {
        "score": score,
        "label": label,
        "detail": detail,
        "allows_entry": score >= MIN_DATA_COVERAGE_FOR_ENTRY,
    }


def _decision_label(status: str) -> str:
    labels = {
        "RESEARCH_CANDIDATE": "High-scoring research candidate",
        "MONITOR": "Monitoring candidate",
        "WAIT": "No current setup",
    }
    return labels.get(status, "Needs review")


def _public_label(status: str) -> str:
    # Public/SaaS UI copy must describe a research workflow state, not an instruction to trade.
    labels = {
        "RESEARCH_CANDIDATE": "High-priority research candidate",
        "MONITOR": "Research candidate",
        "WAIT": "Monitoring candidate",
    }
    return labels.get(status, "Needs review")
