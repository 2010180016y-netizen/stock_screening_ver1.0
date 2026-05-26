from __future__ import annotations

from .models import StockSnapshot
from .validation import validate_ticker


SAMPLE_TICKERS = ("PLTR", "MSTR", "RGTI", "SMMT", "VST", "GME", "AAPL")

SAMPLE_SNAPSHOTS: dict[str, StockSnapshot] = {
    "PLTR": StockSnapshot(
        ticker="PLTR",
        company_name="Palantir Technologies",
        price=125.20,
        market_cap_m=285000,
        float_shares_m=2200,
        revenue_surprise_pct=26,
        revenue_acceleration_pp=7,
        sector_rs_12w_pp=18,
        insider_buy_count_90d=2,
        breakout_volume_ratio=1.7,
        forward_guidance_raised=True,
        above_200dma=True,
        eps_revision_pct=24,
        data_as_of="sample-2026-05-16",
    ),
    "MSTR": StockSnapshot(
        ticker="MSTR",
        company_name="MicroStrategy",
        price=1680.50,
        market_cap_m=34000,
        float_shares_m=19,
        btc_6m_return_pct=62,
        mining_capacity_increase_pct=0,
        drawdown_recovery_pct=35,
        above_200dma=True,
        volume_z_score_30d=2.8,
        news_catalyst_30d=True,
        short_interest_pct=18,
        call_oi_change_pct=240,
        data_as_of="sample-2026-05-16",
    ),
    "RGTI": StockSnapshot(
        ticker="RGTI",
        company_name="Rigetti Computing",
        price=8.45,
        market_cap_m=420,
        float_shares_m=42,
        peer_30d_return_pct=38,
        volume_z_score_30d=3.4,
        news_catalyst_30d=True,
        above_200dma=True,
        data_as_of="sample-2026-05-16",
    ),
    "SMMT": StockSnapshot(
        ticker="SMMT",
        company_name="Summit Therapeutics",
        price=33.80,
        market_cap_m=360,
        float_shares_m=160,
        fda_milestone_90d=True,
        insider_buy_count_90d=2,
        short_interest_pct=6,
        volume_z_score_30d=1.4,
        news_catalyst_30d=True,
        data_as_of="sample-2026-05-16",
    ),
    "VST": StockSnapshot(
        ticker="VST",
        company_name="Vistra",
        price=146.70,
        market_cap_m=51000,
        float_shares_m=340,
        sector_rs_12w_pp=26,
        data_center_narrative=True,
        eps_revision_pct=28,
        revenue_acceleration_pp=4,
        above_200dma=True,
        breakout_volume_ratio=1.5,
        data_as_of="sample-2026-05-16",
    ),
    "GME": StockSnapshot(
        ticker="GME",
        company_name="GameStop",
        price=24.40,
        market_cap_m=10500,
        float_shares_m=305,
        short_interest_pct=31,
        days_to_cover=7,
        borrow_rate_pct=65,
        call_oi_change_pct=320,
        volume_z_score_30d=3.2,
        news_catalyst_30d=True,
        data_as_of="sample-2026-05-16",
    ),
    "AAPL": StockSnapshot(
        ticker="AAPL",
        company_name="Apple",
        price=192.30,
        market_cap_m=2950000,
        float_shares_m=15200,
        revenue_surprise_pct=4,
        revenue_acceleration_pp=1,
        sector_rs_12w_pp=2,
        insider_buy_count_90d=0,
        breakout_volume_ratio=1.1,
        above_200dma=True,
        eps_revision_pct=3,
        data_as_of="sample-2026-05-16",
    ),
}


def get_snapshot(ticker_value: str) -> StockSnapshot:
    ticker = validate_ticker(ticker_value)
    if ticker in SAMPLE_SNAPSHOTS:
        return SAMPLE_SNAPSHOTS[ticker]
    seed = sum((index + 1) * ord(char) for index, char in enumerate(ticker))
    price = round(10 + (seed % 190) + ((seed % 97) / 100), 2)
    return StockSnapshot(
        ticker=ticker,
        company_name=f"{ticker} sample placeholder",
        price=price,
        market_cap_m=1000 + (seed % 9000),
        float_shares_m=80 + (seed % 900),
        revenue_surprise_pct=seed % 8,
        revenue_acceleration_pp=seed % 3,
        sector_rs_12w_pp=(seed % 9) - 4,
        breakout_volume_ratio=1.0 + ((seed % 30) / 100),
        above_200dma=bool(seed % 2),
        source="sample-placeholder",
        data_as_of="generated-placeholder",
    )
