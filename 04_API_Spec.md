# VCB-Alt v3.0 — API Specification

## 1. Internal Python API

### 1.1 Phase 1: Archetype Detectors

```python
# vcb_phase1_archetypes.py

def detect_archetype_A_ai_tech(
    revenue_surprise_pct: float,
    revenue_4q_acceleration_pp: float,
    tech_sector_rs_12w_pp: float,
    insider_voluntary_buy_count_90d: int,
    chart_base_weeks: float,
    chart_breakout_volume_ratio: float,
    forward_guidance_raised: bool,
    f1_passed: bool = True,
) -> ArchetypeScore:
    """Archetype A — AI/Tech Megatrend score."""

def detect_archetype_B_crypto_pivot(
    btc_6m_return_pct: float,
    company_btc_announcement_30d: bool,
    company_mining_capacity_increase_pct: float,
    drawdown_recovery_pct: float,
    above_200dma: bool,
    volume_z_score_30d: float,
    news_catalyst_30d: str,
) -> ArchetypeScore: ...

# (5 more archetype functions...)
```

**Return type**:
```python
@dataclass
class ArchetypeScore:
    archetype: ArchetypeID
    total_score: int                  # 0-100
    signal_breakdown: Dict[str, int]
    strength: SetupStrength            # NO_SETUP / SETUP / STRONG_SETUP
    expected_holding_days: Tuple[int, int]
    expected_return_pct: Tuple[int, int]
    suggested_size_pct: float
    stop_loss_pct: float
    rationale: List[str]
    fired_signals: List[str]
```

### 1.2 Phase 2: Portfolio Manager

```python
# vcb_phase2_portfolio.py

class PortfolioManager:
    def __init__(self, total_capital: float):
        self.total_capital = total_capital
        self.last_entry_day: int = -999
        self.current_day: int = 0
        self.slots: List[PositionSlot] = [...]
    
    def evaluate_entry(
        self,
        ticker: str,
        archetype_score: ArchetypeScore,
        drawdown_state: MarketDrawdownState,
    ) -> EntryDecision:
        """진입 평가 + size 계산."""
    
    def add_position(
        self, ticker: str, archetype_score: ArchetypeScore,
        entry_price: float, size_pct: float, stop_loss: float,
        target_slot: SlotPriority,
    ) -> None: ...
    
    def update_current_prices(
        self, price_map: Dict[str, float]
    ) -> None: ...
    
    def check_stops(self) -> List[Tuple[str, str]]:
        """Stop 도달 종목 list."""
    
    def get_state(
        self, drawdown_state: MarketDrawdownState
    ) -> PortfolioState: ...
```

### 1.3 Phase 3: Complexity Modules

```python
# vcb_phase3_complexity.py

def score_short_interest(data: ShortInterestData) -> ShortInterestScore: ...
def score_options_flow(data: OptionsFlowData) -> OptionsFlowScore: ...
def score_edgar_8k(event: EDGAR_8K_Event) -> EDGAR_8K_Score: ...
def score_on_chain(data: OnChainData) -> OnChainScore: ...
```

### 1.4 Phase 4: Integration

```python
# vcb_phase4_5_integrated.py

def integrate_decision(
    inputs: StockInputs,
    market_dd: MarketDrawdownState,
    portfolio_manager: PortfolioManager,
) -> IntegratedDecision:
    """End-to-end 진입 결정."""
```

### 1.5 Data Fetcher (사용자 환경 작성 필요)

```python
# data_fetcher.py

def fetch_prices(ticker: str, period: str = '2y') -> pd.DataFrame:
    """Yfinance 가격 + 거래량.
    
    Returns: DataFrame with columns ['Open', 'High', 'Low', 'Close', 'Volume']
    """

def fetch_short_interest(ticker: str) -> ShortInterestData:
    """FINRA short interest (or yfinance fallback)."""

def fetch_8k_filings(ticker: str, days: int = 90) -> List[EDGAR_8K_Event]:
    """SEC EDGAR 8-K filings 최근 N일."""

def fetch_btc_on_chain() -> OnChainData:
    """BTC price + on-chain metrics."""

def fetch_sector_rs(
    sector_etf: str = 'XLK',
    benchmark: str = 'SPY',
    period: str = '3mo',
) -> float:
    """Sector RS vs benchmark (12W return diff)."""

def fetch_insider_transactions(ticker: str, days: int = 90) -> List[Dict]:
    """SEC Form 4 — insider buy/sell."""

def fetch_options_chain(ticker: str) -> OptionsFlowData:
    """Yfinance options chain."""
```

---

## 2. External APIs Used

### 2.1 yfinance (Yahoo Finance) — 무료

**Endpoints**:
```python
ticker = yf.Ticker("PLTR")

# Prices
ticker.history(period="2y")
# → DataFrame: Open, High, Low, Close, Volume

# Info
ticker.info
# → dict: marketCap, floatShares, sharesShort, shortRatio, ...

# Options
ticker.options                # available expiration dates
ticker.option_chain("2026-06-21")
# → namedtuple: calls, puts (each DataFrame)
```

**Rate limit**: 무료, 2,000 req/h (안정적)  
**Caveats**: 일별 cache 권장 (서버 부담), real-time 가격 X (15-20분 delay)

### 2.2 SEC EDGAR — 무료

**API**: `https://data.sec.gov/submissions/CIK{cik}.json`  
**Python lib**: `sec-edgar-downloader`

```python
from sec_edgar_downloader import Downloader

dl = Downloader("YourCompany", "your@email.com")

# 8-K filings
dl.get("8-K", "PLTR", after="2024-01-01")

# Form 4 (insider transactions)
dl.get("4", "PLTR", after="2024-01-01")

# 10-K (annual)
dl.get("10-K", "PLTR", limit=3)
```

**Rate limit**: 10 req/sec (정중)  
**Required**: User-Agent header (회사명 + 이메일)

### 2.3 CoinGecko — 무료 tier

**Endpoint**: `https://api.coingecko.com/api/v3/`

```python
from pycoingecko import CoinGeckoAPI

cg = CoinGeckoAPI()

# BTC price + market data
cg.get_coin_market_chart_by_id('bitcoin', vs_currency='usd', days=180)
# → {'prices': [[ts, price], ...], 'market_caps': [...], 'total_volumes': [...]}

# BTC dominance
cg.get_global()
# → {'data': {'market_cap_percentage': {'btc': 58.2, ...}}}
```

**Rate limit**: 30 req/min (free tier)  
**Paid tier**: $129/월 (필요 X — free 충분)

### 2.4 Alternative.me — BTC Fear & Greed

**Endpoint**: `https://api.alternative.me/fng/`

```python
import requests

r = requests.get("https://api.alternative.me/fng/?limit=30")
# → {'data': [{'value': '72', 'value_classification': 'Greed', 'timestamp': ...}]}
```

**Rate limit**: unlimited  
**Cost**: free

### 2.5 FINRA Short Interest

**Source**: https://www.finra.org/finra-data/browse-catalog/short-sale-volume-data  
**Format**: CSV download (월 2회)  
**Cost**: free  
**Latency**: 2주 lag

**Alternative** (real-time, paid):
- S3 Partners ($300/월)
- Ortex ($150/월)

### 2.6 OpenAI / Claude API (NLP for TLS)

**Use case**: Earnings transcript 분석 (F3 v2 TLS)

```python
import anthropic

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

response = client.messages.create(
    model="claude-haiku-4-5-20251001",  # Cheapest
    max_tokens=1000,
    messages=[{
        "role": "user",
        "content": f"""다음 earnings call에서 6개 차원 분석:
        1. 자신감 어휘
        2. Hedging 어휘
        3. 신규 product/tech 키워드
        4. Q&A 구체성
        5. Forward guidance 명확성
        6. 경쟁사 언급
        
        Transcript: {transcript_text}
        
        JSON으로 답변."""
    }]
)
```

**Cost**: $0.05-0.50/transcript (Haiku 4.5)  
**Frequency**: 분기당 watchlist 30 종목 = $1.50-15/quarter

### 2.7 News / Sentiment (Optional)

**Reddit**:
- Pushshift (free, often broken)
- PRAW (Reddit official, free)
- 직접 JSON scraping (free)

**Twitter/X**:
- Twitter API v2 ($100/월)
- 또는 nitter scraping (free, unstable)

---

## 3. Configuration via Environment Variables

```bash
# .env file

# API Keys
ANTHROPIC_API_KEY=sk-ant-xxx
OPENAI_API_KEY=sk-xxx  # optional

# Email
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your@gmail.com
SMTP_PASSWORD=xxx
ALERT_EMAIL=your@gmail.com

# Telegram (optional)
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx

# Optional: Paid data sources
ORTEX_API_KEY=  # 비워둘 수 있음
S3_PARTNERS_KEY=

# Database
DATABASE_URL=sqlite:///./data/vcb_alt.db  # Phase 1
# DATABASE_URL=postgresql://user:pass@host/db  # Phase 2+

# System
LOG_LEVEL=INFO
TIMEZONE=Asia/Seoul
```

---

## 4. CLI Interface (Phase 1)

### 4.1 Daily Commands

```bash
# 아침 routine
$ python -m vcb_alt morning
> Market Regime: Bull-Normal (drawdown -3%)
> Boost: 0.85x
> 보유 종목:
>   PLTR: $135 (entry $133, +1.5%, stop $122)
>   SMR:  $35  (entry $28, +25%, stop $26)
>   IONQ: $52  (entry $45, +15%, stop $41)
> Watchlist Strong Setups (>=70):
>   None today

# 저녁 routine
$ python -m vcb_alt evening
> 8-K filings today:
>   PLTR: contract announcement (DOD $200M)
> Reddit mention spikes:
>   None

# 신규 종목 평가
$ python -m vcb_alt evaluate AAPL
> Primary: A_AI_TECH (38)
> Combined: 38
> Setup: NO_SETUP
> Can enter: False
> Reason: 매출 가속 부족 (+2pp), insider buy 0건
```

### 4.2 Weekly Commands

```bash
$ python -m vcb_alt weekly
> Watchlist scan (30 stocks)
> Strong Setups: 2
>   GEV   — Archetype F, score 78
>   IREN  — Archetype B, score 72
> Portfolio rebalancing suggestions:
>   None

$ python -m vcb_alt audit weekly
> Generated: audit/2026-W19.md
```

### 4.3 Monthly Commands

```bash
$ python -m vcb_alt audit monthly
> P&L: +12.5%
> Win rate: 4/7 = 57%
> Sharpe: 1.6
> Best: SMR (+45%)
> Worst: NVDA (-9%, stop hit)

$ python -m vcb_alt calibrate
> Walk-forward 10 fold...
> Old PM threshold: 55 → New: 53 (test TPR +3pp)
> Apply? [y/N]
```

---

## 5. Web Dashboard (Phase 2 — Streamlit prototype)

### 5.1 Pages

| Page | URL | Content |
|---|---|---|
| Dashboard | `/` | 보유 종목, 시장 환경, 알림 |
| Watchlist | `/watchlist` | 30 종목 + score |
| Stock detail | `/stock/{ticker}` | 6 archetype + 4 복잡계 + 차트 |
| Portfolio | `/portfolio` | Positions + history |
| Audit | `/audit` | 월간 결과 |
| Calibration | `/calibration` | 임계값 sensitivity |
| Settings | `/settings` | Config edit |

---

## 6. Error Handling

### 6.1 Data Fetch Failures

```python
@retry(max_attempts=3, backoff=2)
def fetch_with_fallback(ticker: str):
    try:
        return yfinance_fetch(ticker)
    except Exception as e:
        logger.warning(f"yfinance failed for {ticker}: {e}")
        return alpha_vantage_fetch(ticker)  # fallback
```

### 6.2 API Rate Limits

| API | Limit | Backoff |
|---|---|---|
| yfinance | 2,000/h | exponential |
| SEC EDGAR | 10/sec | sleep(0.1) |
| CoinGecko | 30/min | sleep(2) |
| Anthropic | 50/min | sleep(1.2) |

### 6.3 Critical Errors → 즉시 알림

- Stop loss 도달 종목 fetch 실패
- DB connection lost
- API key invalid
- Disk space < 10%
