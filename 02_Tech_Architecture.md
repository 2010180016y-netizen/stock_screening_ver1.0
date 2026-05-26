# VCB-Alt v3.0 — Tech Architecture

## 1. System Architecture Overview

### 1.1 Architecture Layers

```
┌─────────────────────────────────────────────────────┐
│             Presentation Layer                       │
│  - CLI (Phase 1) / Web Dashboard (Phase 2)          │
│  - Telegram / Email Alerts                          │
└─────────────────────────────────────────────────────┘
                      ↑↓
┌─────────────────────────────────────────────────────┐
│             Application Layer                        │
│  - Phase 4: Integrated System (decision)            │
│  - Phase 2: Portfolio Manager                       │
│  - Phase 5: Validation + Monitoring                 │
└─────────────────────────────────────────────────────┘
                      ↑↓
┌─────────────────────────────────────────────────────┐
│             Domain Logic Layer                       │
│  - Phase 1: 6 Archetype Detectors                   │
│  - Phase 3: 4 Complexity Modules                    │
│  - Module 1 v2: Surge Predictor (BB/AVWAP/RSI)      │
│  - Module 3: Market Regime + Sector Flow            │
│  - F3 v2: Alt Data (CRV/ICA/CEI/TLS/WAS)            │
└─────────────────────────────────────────────────────┘
                      ↑↓
┌─────────────────────────────────────────────────────┐
│             Data Access Layer                        │
│  - yfinance (price, volume)                         │
│  - SEC EDGAR (8-K, Form 4)                          │
│  - FINRA (short interest)                           │
│  - CoinGecko (BTC/on-chain)                         │
│  - Alpha Vantage / FMP (fallback)                   │
└─────────────────────────────────────────────────────┘
                      ↑↓
┌─────────────────────────────────────────────────────┐
│             Persistence Layer                        │
│  - SQLite (Phase 1, local)                          │
│  - PostgreSQL (Phase 2+)                            │
│  - Redis (caching, Phase 2+)                        │
└─────────────────────────────────────────────────────┘
```

### 1.2 Component Diagram

```
                    [User CLI]
                        |
                        v
              ┌─────────────────┐
              │  daily_pipeline │ (orchestrator)
              └─────────────────┘
                  /     |     \
                 v      v      v
        ┌──────────┐ ┌────┐ ┌────────┐
        │ fetch    │ │eval│ │ alert  │
        │ data     │ │6arc│ │  send  │
        └──────────┘ └────┘ └────────┘
              |       |       |
              v       v       v
        ┌──────────────────────────┐
        │     SQLite (local DB)    │
        └──────────────────────────┘
```

---

## 2. Technology Stack

### 2.1 Phase 1 (Personal, Local)

| Layer | Technology | Reason |
|---|---|---|
| Language | Python 3.11+ | 데이터 분석 표준, 사용자 익숙 |
| Data fetch | yfinance, sec-edgar-downloader, pycoingecko | 무료 source |
| Numerical | NumPy, pandas, scipy | 표준 |
| ML / Optimization | scikit-optimize, scikit-learn | Bayesian opt |
| NLP (TLS) | OpenAI / Claude API | Earnings transcript 분석 |
| Database | SQLite | Local, 설치 X |
| Scheduling | cron + Python script | 간단 |
| Alert | smtplib (email), python-telegram-bot | 무료 |
| Dashboard | Streamlit (optional) | Python only, 빠른 prototype |

### 2.2 Phase 2 (Multi-user, Cloud)

| Layer | Technology |
|---|---|
| Backend | FastAPI |
| Frontend | React + Tailwind |
| Database | PostgreSQL + Redis |
| Hosting | AWS (EC2 + RDS) 또는 Vercel + Supabase |
| Queue | Celery + Redis |
| Monitoring | Sentry + Grafana |

### 2.3 Phase 3 (SaaS, 1,000+ users)

| Layer | Technology |
|---|---|
| Orchestration | Kubernetes |
| API Gateway | Kong / AWS API Gateway |
| Database | PostgreSQL (sharded) + TimescaleDB (시계열) |
| Cache | Redis Cluster |
| Stream | Kafka (real-time alerts) |
| CDN | CloudFront |

---

## 3. Data Flow

### 3.1 Daily Scan Pipeline

```
[09:00 KST cron trigger]
         |
         v
[1. fetch S&P 500 price] → Market Regime (Module 3)
         |
         v (Bull/Mid/Caution/Bear/Crisis)
[2. fetch Watchlist 30 종목 prices] (1-2 분)
         |
         v
[3. parallel: each stock]
   ├── F1 Trend Template
   ├── F2 Multi-Pattern
   ├── Module 1 v2 Surge Predictor
   ├── F3 v2 Alt Data
   ├── 6 Archetype Scores
   ├── 4 Complexity Modifiers
   ├── F4 Cross-Reference
   └── F5 Pivot Breakout
         |
         v
[4. Phase 4 Integrated Decision]
   - Primary archetype 선정
   - Combined score 계산
   - Portfolio Manager 진입 평가
         |
         v
[5. Filter: combined_score >= 55 + can_enter]
         |
         v
[6. Generate alerts]
   - Strong Setup 알림 (이메일/Telegram)
   - 보유 종목 stop check
   - Audit log 저장
         |
         v
[7. Update SQLite]
```

### 3.2 Weekly Pipeline

```
[일요일 18:00 KST]
         |
         v
[1. F3 v2 펀더 update] (분기 회사만, ~30 분)
         |
         v
[2. 4 복잡계 update]
   ├── Short interest (FINRA 월 2회)
   ├── Options flow (yfinance options chain)
   ├── 8-K filings (SEC EDGAR 30일 lookback)
   └── On-chain (CoinGecko + alternative.me)
         |
         v
[3. Sensitivity test (월간)]
   - 임계값 ±20% 변동 시 영향
         |
         v
[4. Watchlist 재정의]
   - Top 30 score 종목으로 update
         |
         v
[5. Weekly audit email 발송]
```

### 3.3 Monthly Pipeline

```
[월말 토요일]
         |
         v
[1. 월간 P&L 결과]
[2. Archetype별 성과]
[3. Bayesian opt 재실행 (분기당 1회)]
[4. Universe 확장 (신규 종목 후보)]
[5. 시스템 audit (FN/FP 분석)]
```

---

## 4. Module Dependencies

### Phase 1 (Detectors)
```
vcb_phase1_archetypes.py
    ├── Archetype A: F1 + F2 + F3.CRV + F3.ICA + EDGAR
    ├── Archetype B: BTC price + Company 8-K + chart
    ├── Archetype C: Float + Govt contract + Peer
    ├── Archetype D: FDA calendar + chart + insider
    ├── Archetype E: Short interest + Options + sentiment
    └── Archetype F: AI sector RS + EPS revision + chart
```

### Phase 2 (Portfolio)
```
vcb_phase2_portfolio.py
    ├── PortfolioManager
    │   ├── evaluate_entry()
    │   ├── add_position()
    │   ├── cooldown check (7일)
    │   ├── archetype 분산 check
    │   └── high-vol C/D/E 1개 max
    ├── classify_market_drawdown()
    └── calc_drawdown_size_boost()
```

### Phase 3 (Complexity)
```
vcb_phase3_complexity.py
    ├── score_short_interest()
    ├── score_options_flow()
    ├── score_edgar_8k()
    └── score_on_chain()
```

### Phase 4 (Integration)
```
vcb_phase4_5_integrated.py
    ├── evaluate_all_archetypes() — 6 모두
    ├── evaluate_complexity_modifiers() — 4 모두
    └── integrate_decision() — 통합
```

---

## 5. Deployment Architecture

### 5.1 Phase 1 — Local Machine

```
[User's Laptop / VPS]
    ├── /home/user/vcb_alt_v3/
    │   ├── src/  (Python code, 13 files)
    │   ├── data/ (SQLite, 캐시)
    │   ├── logs/
    │   ├── .env (API keys)
    │   └── cron jobs
    │
    └── External APIs (read-only)
```

**Spec**:
- OS: macOS / Linux / Windows
- RAM: 8GB+
- Disk: 10GB+
- Python: 3.11+

### 5.2 Phase 2 — Cloud (Multi-user)

```
[AWS / Vercel]
    ├── Web app (Next.js)
    ├── Backend API (FastAPI on EC2)
    ├── Worker (Celery)
    ├── DB (PostgreSQL on RDS)
    └── Cache (Redis on Elasticache)

[External]
    ├── yfinance (Yahoo Finance)
    ├── SEC EDGAR
    ├── CoinGecko
    └── OpenAI / Anthropic (NLP)
```

### 5.3 Phase 3 — SaaS

```
[Kubernetes Cluster]
    ├── API pods (autoscale)
    ├── Worker pods (Celery)
    ├── DB cluster (PostgreSQL sharded)
    ├── Cache cluster (Redis)
    └── Streaming (Kafka — real-time alerts)

[CDN]
    └── CloudFront (static assets)
```

---

## 6. Key Design Decisions

### 6.1 Local-first (Phase 1)
**Decision**: 사용자 로컬 운용 (cloud X)  
**Rationale**: (1) 사용자 portfolio 정보 보안, (2) 무료, (3) 의존성 ↓  
**Trade-off**: 24/7 uptime X, mobile access X

### 6.2 Modular Detector Design
**Decision**: 6 archetype 모두 *독립 모듈*  
**Rationale**: 각 archetype 별도 calibration 가능, 한 archetype fail 시 영향 격리

### 6.3 SQLite (Phase 1)
**Decision**: PostgreSQL 아닌 SQLite  
**Rationale**: 설치 0, 사용자 환경 부담 X  
**Trade-off**: 동시성 ↓ (multi-user 시 PostgreSQL 전환)

### 6.4 No auto-trading (Year 1)
**Decision**: 자동 거래 X — 알림만  
**Rationale**: (1) 법적 risk 회피, (2) 사용자 마지막 결정권, (3) bug 시 catastrophic loss 회피
