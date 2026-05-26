from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


ARCHETYPE_LABELS = {
    "A_AI_TECH": "AI/Tech Megatrend",
    "B_CRYPTO_PIVOT": "Crypto Pivot",
    "C_QUANTUM": "Quantum/Emerging",
    "D_BIOTECH": "Biotech Catalyst",
    "E_SHORT_SQUEEZE": "Short Squeeze",
    "F_PICK_SHOVEL": "AI Pick & Shovel",
    "G_TECHNICAL_MOMENTUM": "Technical Momentum",
}

ARCHETYPE_CAPS = {
    "A_AI_TECH": 25.0,
    "B_CRYPTO_PIVOT": 22.0,
    "C_QUANTUM": 18.0,
    "D_BIOTECH": 18.0,
    "E_SHORT_SQUEEZE": 18.0,
    "F_PICK_SHOVEL": 25.0,
    "G_TECHNICAL_MOMENTUM": 18.0,
}

HIGH_VOL_ARCHETYPES = {"C_QUANTUM", "D_BIOTECH", "E_SHORT_SQUEEZE"}
SCORING_VERSION = "mvp-market-v0.6.0"


@dataclass(frozen=True)
class OperationResult:
    ok: bool
    status_code: int
    message: str
    data: Any = None
    error: dict[str, Any] | None = None

    @classmethod
    def success(cls, message: str, data: Any = None, status_code: int = 200) -> "OperationResult":
        return cls(ok=True, status_code=status_code, message=message, data=data)

    @classmethod
    def failure(
        cls,
        message: str,
        *,
        status_code: int = 500,
        code: str = "INTERNAL_ERROR",
        detail: str | None = None,
    ) -> "OperationResult":
        error: dict[str, Any] = {"code": code, "message": message}
        if detail:
            error["detail"] = detail
        return cls(ok=False, status_code=status_code, message=message, error=error)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StockSnapshot:
    ticker: str
    company_name: str
    price: float
    market_cap_m: float = 0.0
    float_shares_m: float = 0.0
    revenue_surprise_pct: float = 0.0
    earnings_surprise_pct: float = 0.0
    revenue_acceleration_pp: float = 0.0
    sector_rs_12w_pp: float = 0.0
    insider_buy_count_90d: int = 0
    breakout_volume_ratio: float = 1.0
    forward_guidance_raised: bool = False
    btc_6m_return_pct: float = 0.0
    mining_capacity_increase_pct: float = 0.0
    drawdown_recovery_pct: float = 0.0
    above_200dma: bool = False
    volume_z_score_30d: float = 0.0
    news_catalyst_30d: bool = False
    peer_30d_return_pct: float = 0.0
    fda_milestone_90d: bool = False
    short_interest_pct: float = 0.0
    days_to_cover: float = 0.0
    borrow_rate_pct: float = 0.0
    call_open_interest: float = 0.0
    put_open_interest: float = 0.0
    put_call_ratio: float = 0.0
    call_oi_change_pct: float = 0.0
    analyst_revision_score: float = 0.0
    analyst_buy_count: int = 0
    analyst_hold_count: int = 0
    analyst_sell_count: int = 0
    news_headline_count_30d: int = 0
    filing_catalyst_30d: bool = False
    latest_filing_date: str = ""
    latest_filing_type: str = ""
    latest_filing_url: str = ""
    intraday_price: float = 0.0
    intraday_change_pct: float = 0.0
    intraday_volume: float = 0.0
    intraday_source: str = ""
    intraday_as_of: str = ""
    intraday_freshness_seconds: float = 0.0
    intraday_error: str = ""
    data_center_narrative: bool = False
    eps_revision_pct: float = 0.0
    source: str = "sample"
    data_as_of: str = "offline"
    data_quality: str = "offline"
    return_12w_pct: float = 0.0
    return_12m_pct: float = 0.0
    drawdown_52w_pct: float = 0.0
    price_vs_50dma_pct: float = 0.0
    price_vs_150dma_pct: float = 0.0
    price_vs_200dma_pct: float = 0.0
    trend_template_score: int = 0
    surge_score: int = 0
    rr_ratio: float = 0.0
    enrichment_source: str = ""
    enrichment_as_of: str = ""
    data_coverage_score: int = 0
    data_coverage_label: str = "unknown"
    data_coverage_detail: str = ""


@dataclass(frozen=True)
class EvaluationResult:
    ticker: str
    company_name: str
    scoring_version: str
    primary_archetype: str
    primary_archetype_label: str
    archetype_scores: dict[str, int]
    complexity_modifier: int
    combined_score: int
    setup_strength: str
    can_enter: bool
    suggested_size_pct: float
    stop_loss: float
    status: str
    decision_label: str
    public_label: str = ""
    rationale: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source: str = "sample"
    data_as_of: str = "offline"
    data_quality: str = "offline"
    precision_notes: list[str] = field(default_factory=list)
    data_coverage_score: int = 0
    data_coverage_label: str = "unknown"
    data_coverage_detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PortfolioSelection:
    selected: list[EvaluationResult]
    rejected: list[dict[str, Any]]
    max_positions: int
    max_total_size_pct: float
    total_size_pct: float
    data_provider: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected": [item.to_dict() for item in self.selected],
            "rejected": self.rejected,
            "max_positions": self.max_positions,
            "max_total_size_pct": self.max_total_size_pct,
            "total_size_pct": self.total_size_pct,
            "data_provider": self.data_provider,
        }
