# VCB-Alt v3.0 — Data Schema

## 1. Database Schema (SQLite Phase 1 / PostgreSQL Phase 2+)

### 1.1 ER Diagram

```
┌──────────────┐       ┌─────────────────┐       ┌──────────────┐
│   stocks     │←──────│   evaluations   │──────→│  archetypes  │
└──────────────┘       └─────────────────┘       └──────────────┘
       ↑                       ↑                          
       │                       │                          
       │              ┌─────────────────┐
       └──────────────│   positions     │
                      └─────────────────┘
                              │
                              ↓
                      ┌─────────────────┐
                      │  trade_history  │
                      └─────────────────┘
```

### 1.2 Tables

#### `stocks` — Master 종목 table
```sql
CREATE TABLE stocks (
    ticker          TEXT PRIMARY KEY,
    company_name    TEXT NOT NULL,
    sector          TEXT,
    industry        TEXT,
    market_cap_m    REAL,
    float_shares_m  REAL,
    listed_date     DATE,
    added_to_watchlist DATE,
    is_active       BOOLEAN DEFAULT 1,
    notes           TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### `daily_prices` — 일별 가격 cache
```sql
CREATE TABLE daily_prices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    date            DATE NOT NULL,
    open            REAL,
    high            REAL,
    low             REAL,
    close           REAL,
    volume          INTEGER,
    adj_close       REAL,
    UNIQUE(ticker, date),
    FOREIGN KEY (ticker) REFERENCES stocks(ticker)
);
CREATE INDEX idx_prices_ticker_date ON daily_prices(ticker, date);
```

#### `archetype_scores` — 평가 결과 (일별)
```sql
CREATE TABLE archetype_scores (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    eval_date       DATE NOT NULL,
    
    -- 6 archetype scores
    archetype_A_score   INTEGER,
    archetype_B_score   INTEGER,
    archetype_C_score   INTEGER,
    archetype_D_score   INTEGER,
    archetype_E_score   INTEGER,
    archetype_F_score   INTEGER,
    
    primary_archetype   TEXT,    -- "A_AI_TECH" etc
    primary_score       INTEGER,
    secondary_archetype TEXT,
    secondary_score     INTEGER,
    
    -- 4 complexity modifiers (archetype별 weighted)
    short_interest_score    INTEGER,
    options_flow_score      INTEGER,
    edgar_8k_score          INTEGER,
    on_chain_score          INTEGER,
    
    -- Combined + decision
    combined_score      INTEGER NOT NULL,
    setup_strength      TEXT NOT NULL,  -- "STRONG_SETUP" etc
    can_enter           BOOLEAN,
    suggested_size_pct  REAL,
    suggested_stop_pct  REAL,
    
    -- Raw inputs (JSON for replay)
    inputs_json         TEXT,
    
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(ticker, eval_date),
    FOREIGN KEY (ticker) REFERENCES stocks(ticker)
);
CREATE INDEX idx_scores_ticker_date ON archetype_scores(ticker, eval_date);
CREATE INDEX idx_scores_combined ON archetype_scores(combined_score DESC);
```

#### `positions` — 현재 보유 포지션
```sql
CREATE TABLE positions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    slot_id         TEXT,           -- "PRIMARY_1" ~ "SECONDARY_5"
    archetype       TEXT NOT NULL,
    
    -- Entry
    entry_date      DATE NOT NULL,
    entry_price     REAL NOT NULL,
    size_pct        REAL NOT NULL,
    size_usd        REAL NOT NULL,
    
    -- Targets / Stop
    stop_loss       REAL NOT NULL,
    target_1        REAL,
    target_2        REAL,
    
    -- Current state
    current_price   REAL,
    pnl_pct         REAL,
    pnl_usd         REAL,
    
    -- Exit (NULL until exited)
    exit_date       DATE,
    exit_price      REAL,
    exit_reason     TEXT,           -- "stop", "target_1", "target_2", "manual"
    
    -- Notes
    rationale       TEXT,            -- 진입 이유
    
    is_open         BOOLEAN DEFAULT 1,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (ticker) REFERENCES stocks(ticker)
);
CREATE INDEX idx_positions_open ON positions(is_open);
```

#### `market_regime` — 일별 시장 환경
```sql
CREATE TABLE market_regime (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            DATE NOT NULL UNIQUE,
    
    -- S&P 500
    spx_close       REAL,
    spx_above_200dma BOOLEAN,
    spx_12m_return_pct REAL,
    spx_drawdown_from_ath_pct REAL,
    drawdown_phase  TEXT,            -- "normal", "shallow", "moderate", "deep", "crisis"
    
    -- Regime
    base_regime     TEXT,            -- "Bull", "Mid", "Caution", "Bear", "Crisis"
    transition_state TEXT,           -- "Stable", "Transition_to_Bull", "Transition_to_Bear"
    
    -- 5 leading indicators
    breadth_ad_line REAL,            -- NYSE A-D line
    defensive_rotation_signal BOOLEAN,
    vix_term_backwardation BOOLEAN,
    credit_spread_widening BOOLEAN,
    high_low_beta_signal BOOLEAN,
    
    -- Warning
    early_warning_level TEXT,        -- "Green", "Yellow", "Orange", "Red"
    
    -- Sector flow
    sector_rotation_phase TEXT,
    top_3_sectors   TEXT,            -- JSON array
    
    -- Decision impact
    new_entry_allowed BOOLEAN,
    size_modifier   REAL,            -- 0.5 ~ 1.30
    
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### `alerts` — 알림 history
```sql
CREATE TABLE alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT,
    alert_type      TEXT NOT NULL,   -- "strong_setup", "stop_hit", "target_hit", "earnings_alert"
    alert_level     TEXT,            -- "info", "warning", "critical"
    message         TEXT NOT NULL,
    channel         TEXT,            -- "email", "telegram", "log"
    sent_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_acknowledged BOOLEAN DEFAULT 0
);
```

#### `complexity_data` — 4 복잡계 raw data cache
```sql
CREATE TABLE complexity_data (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    data_type       TEXT NOT NULL,   -- "short_interest", "options_flow", "edgar_8k", "on_chain"
    fetch_date      DATE NOT NULL,
    raw_data_json   TEXT,            -- JSON serialized
    UNIQUE(ticker, data_type, fetch_date),
    FOREIGN KEY (ticker) REFERENCES stocks(ticker)
);
```

#### `audit_log` — 시스템 audit
```sql
CREATE TABLE audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    log_type        TEXT NOT NULL,   -- "daily_scan", "weekly_audit", "monthly_audit", "calibration"
    period_start    DATE,
    period_end      DATE,
    
    -- Metrics
    n_positions     INTEGER,
    win_rate        REAL,
    avg_return_pct  REAL,
    sharpe_ratio    REAL,
    max_drawdown_pct REAL,
    
    -- Per archetype
    archetype_metrics_json TEXT,
    
    -- Findings
    findings_text   TEXT,            -- LLM-generated insights
    
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### `calibration_history` — 임계값 calibration 결과
```sql
CREATE TABLE calibration_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    calibration_date DATE NOT NULL,
    
    -- Old vs new
    threshold_name  TEXT NOT NULL,
    old_value       REAL,
    new_value       REAL,
    
    -- Test metrics
    train_tpr       REAL,
    test_tpr        REAL,
    train_fpr       REAL,
    test_fpr        REAL,
    
    -- Whether applied
    applied         BOOLEAN DEFAULT 0,
    applied_at      TIMESTAMP,
    
    notes           TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 2. File-based Data (Phase 1)

### 2.1 Configuration File (`config.yaml`)
```yaml
system:
  version: "3.0"
  user_name: "Hoiki"
  base_currency: "USD"
  reporting_currency: "KRW"
  exchange_rate: 1340  # KRW/USD

portfolio:
  total_capital_krw: 50000000
  max_positions: 5
  optimal_positions: 3
  
position_sizing:
  archetype_caps:
    A_AI_TECH: 25
    B_CRYPTO_PIVOT: 22
    C_QUANTUM: 18
    D_BIOTECH: 18
    E_SHORT_SQUEEZE: 18
    F_PICK_SHOVEL: 25
  cooldown_days: 7
  high_vol_archetypes_concurrent_max: 1
  pm_entry_threshold: 55

drawdown_buying:
  normal: 0.85
  shallow: 1.0
  moderate: 1.20
  deep: 1.25
  crisis: 1.20  # only if recovering
  crisis_falling: 0.5

complexity_weights:
  A_AI_TECH: {si: 0.3, of: 0.5, edgar: 1.0, oc: 0.0}
  B_CRYPTO_PIVOT: {si: 0.5, of: 0.7, edgar: 0.7, oc: 1.0}
  # ... etc

data_sources:
  primary: yfinance
  fallback: alpha_vantage
  edgar: sec_edgar
  short_interest: finra
  on_chain: coingecko

alerts:
  email:
    enabled: true
    address: "your@email.com"
    smtp_server: "smtp.gmail.com"
    smtp_port: 587
  telegram:
    enabled: false
    bot_token: ""
    chat_id: ""

scheduling:
  daily_scan_time: "09:00 KST"
  evening_review_time: "22:00 KST"
  weekly_review_day: "Sunday 18:00"
```

### 2.2 Watchlist File (`watchlist.json`)
```json
{
  "version": "1.0",
  "last_updated": "2026-05-14",
  "watchlist": [
    {"ticker": "PLTR", "added": "2024-05-30", "archetype_hint": "A_AI_TECH"},
    {"ticker": "MSTR", "added": "2024-10-30", "archetype_hint": "B_CRYPTO_PIVOT"},
    {"ticker": "RGTI", "added": "2024-11-15", "archetype_hint": "C_QUANTUM"},
    {"ticker": "SMMT", "added": "2025-04-01", "archetype_hint": "D_BIOTECH"},
    {"ticker": "VST",  "added": "2024-04-01", "archetype_hint": "F_PICK_SHOVEL"}
  ],
  "max_size": 30
}
```

### 2.3 Logs Structure
```
logs/
├── daily/
│   ├── 2026-05-14_morning.log
│   ├── 2026-05-14_evening.log
├── weekly/
│   └── 2026-W19.log
├── monthly/
│   └── 2026-05.log
├── errors/
│   └── error_2026-05-14.log
└── trades/
    └── trade_history.csv
```

---

## 3. Data Validation Rules

| Field | Rule |
|---|---|
| `ticker` | UPPERCASE, 1-5 chars, exists in NYSE/NASDAQ |
| `entry_price` | > 0 |
| `size_pct` | 0 < x <= 35 (archetype cap) |
| `stop_loss` | < entry_price |
| `combined_score` | 0 <= x <= 100 |
| `eval_date` | weekday only (NYSE 거래일) |

---

## 4. Data Retention Policy

| Table | Retention | Reason |
|---|---|---|
| `daily_prices` | 5년 | backtest용 |
| `archetype_scores` | 3년 | calibration 학습 |
| `positions` | 영구 | tax / audit |
| `alerts` | 1년 | history |
| `market_regime` | 5년 | regime history |
| `audit_log` | 영구 | system learning |
