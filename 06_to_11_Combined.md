# VCB-Alt v3.0 — Deployment & Operation Guide

## 1. Phase 1 Deployment (Personal, Local)

### 1.1 System Requirements
- OS: macOS 12+ / Ubuntu 20.04+ / Windows 11 (WSL2)
- RAM: 8GB+
- Disk: 20GB+ (data cache 포함)
- Python: 3.11+
- Internet: 안정 (daily API calls 100-500)

### 1.2 Installation Steps

```bash
# Step 1: 가상환경
python3.11 -m venv vcb_env
source vcb_env/bin/activate  # macOS/Linux
# vcb_env\Scripts\activate    # Windows

# Step 2: 패키지 설치
pip install --upgrade pip
pip install -r requirements.txt

# Step 3: 디렉토리 생성
mkdir -p data logs cache
chmod 700 .env  # API key 보안

# Step 4: 환경변수 설정
cp .env.example .env
nano .env  # API keys 입력

# Step 5: DB 초기화
python -m vcb_alt init_db

# Step 6: Watchlist 초기 설정
python -m vcb_alt watchlist add PLTR MSTR RGTI SMMT VST

# Step 7: 첫 scan 테스트
python -m vcb_alt scan --dry-run
```

### 1.3 requirements.txt
```
yfinance==0.2.40
pandas==2.2.2
numpy==1.26.4
scipy==1.13.1
scikit-learn==1.5.0
scikit-optimize==0.10.2
sec-edgar-downloader==5.0.3
pycoingecko==3.1.0
requests==2.32.3
anthropic==0.34.0
python-telegram-bot==21.4
streamlit==1.36.0
PyYAML==6.0.1
python-dotenv==1.0.1
matplotlib==3.9.0
seaborn==0.13.2
```

### 1.4 Cron Setup (macOS / Linux)

```bash
crontab -e

# Daily morning (KST 09:00 = UTC 00:00)
0 0 * * 1-5 cd /path/to/vcb_alt && /path/to/python -m vcb_alt morning >> logs/cron.log 2>&1

# Daily evening (KST 22:00 = UTC 13:00)
0 13 * * 1-5 cd /path/to/vcb_alt && /path/to/python -m vcb_alt evening >> logs/cron.log 2>&1

# Weekly Sunday 18:00 KST
0 9 * * 0 cd /path/to/vcb_alt && /path/to/python -m vcb_alt weekly >> logs/cron.log 2>&1

# Monthly last Saturday
0 12 25-31 * 6 cd /path/to/vcb_alt && /path/to/python -m vcb_alt monthly >> logs/cron.log 2>&1
```

### 1.5 Backup Strategy

```bash
# Daily DB backup (cron)
0 23 * * * sqlite3 /path/to/data/vcb_alt.db ".backup /path/to/backup/vcb_$(date +\%Y\%m\%d).db"

# Weekly cloud backup (rclone to Google Drive)
0 0 * * 0 rclone copy /path/to/data gdrive:vcb_backup
```

---

## 2. Daily Operation Routine

### 2.1 Tier 1 — 매일 (30분)

**아침 09:00 KST**:
```
1. python -m vcb_alt morning (자동 5분)
   - 시장 환경 확인 (Module 3)
   - 보유 종목 stop check
   - Watchlist Strong Setup 알림

2. 알림 검토 (사용자 5분)
   - 이메일 / Telegram

3. 진입 결정 (사용자 15분, 신규 후보 있을 시만)
   - System 권고 검토
   - 진입 가격 / size 확인
   - Broker 주문 입력

4. 기록 (사용자 5분)
   - Trade 진입 시 positions 테이블에 기록
```

**저녁 22:00 KST**:
```
1. python -m vcb_alt evening (자동 5분)
   - 8-K filings 오늘
   - News mention 가속 종목

2. 검토 (사용자 10분)
   - 내일 catalyst 종목 mark
   - 보유 종목 P&L 확인
```

### 2.2 Tier 2 — 주간 (1시간, 일요일)

```
1. Weekly scan (자동 30분)
   - python -m vcb_alt weekly
   - Watchlist 30 종목 모든 archetype 평가
   - 4 복잡계 update
   
2. Rebalancing 검토 (사용자 20분)
   - Target 1 도달 종목: 1/3 청산
   - Stop 근접 종목: 청산 검토
   - Strong Setup 신규: 진입 검토 (cooldown 확인)

3. Universe update (사용자 10분)
   - 신규 후보 종목 watchlist 추가
   - 6개월+ 보유했지만 score 떨어진 종목 제거
```

### 2.3 Tier 3 — 월간 (2시간, 마지막 주)

```
1. Monthly audit (자동 30분)
   - python -m vcb_alt audit monthly
   - P&L, Sharpe, win rate
   - Archetype별 성과
   - 놓친 multibagger (FN) 분석
   - False positive (FP) 분석

2. 임계값 calibration (자동 1시간, 분기당 1회)
   - python -m vcb_alt calibrate
   - Walk-forward 10 fold
   - 새 임계값 제안

3. 시스템 audit (사용자 30분)
   - 알고리즘 변경 사항 검토
   - 시장 환경 변화 인식
```

---

# VCB-Alt v3.0 — Cost & Infrastructure

## 1. Phase 1 Cost (Personal, Local)

| 항목 | 비용/월 | 비고 |
|---|---|---|
| 컴퓨터 (이미 있음) | ₩0 | - |
| 전기료 | ₩2,000 | 추가 부담 |
| Internet | ₩0 | 이미 있음 |
| yfinance | ₩0 | Free |
| SEC EDGAR | ₩0 | Free |
| CoinGecko | ₩0 | Free |
| FINRA short interest | ₩0 | Free (2주 lag) |
| Alpha Vantage (fallback) | ₩0 | Free tier (500 req/day) |
| Anthropic Claude API | ₩6,000 ($5) | TLS NLP, 분기 30 종목 |
| Telegram bot | ₩0 | Free |
| Email | ₩0 | Gmail |
| **합계 (Phase 1)** | **₩8,000/월** | **₩96,000/년** |

## 2. Phase 1 Pro (Optional 유료)

| 항목 | 비용/월 | ROI 검증 후 |
|---|---|---|
| Ortex (real-time short interest) | $150 (₩200K) | Archetype E 적중률 ↑ 확인 후 |
| Unusual Whales (options flow) | $60 (₩80K) | Archetype C/E 적중률 ↑ 확인 후 |
| Glassnode (on-chain) | $30 (₩40K) | Archetype B 적중률 ↑ 확인 후 |
| **Pro 합계** | **₩320K/월** | **년 ₩3.8M (실 자본 ₩100M+ 시 ROI ✓)** |

## 3. Phase 2 (Multi-user 10-100명) Cost

| 항목 | 비용/월 |
|---|---|
| AWS EC2 t3.medium | $30 |
| RDS PostgreSQL db.t3.small | $25 |
| Redis ElastiCache | $15 |
| S3 storage | $5 |
| CloudWatch logs | $10 |
| Domain + SSL | $5 |
| Anthropic API | $200 (100 users × $2) |
| **합계** | **$290/월 (~₩400K)** |

Revenue model: $30/user/월 → 10 users $300, 100 users $3,000.

## 4. Phase 3 (SaaS 1,000+ users) Cost

| 항목 | 비용/월 |
|---|---|
| AWS Kubernetes (3-node) | $300 |
| RDS PostgreSQL (sharded) | $500 |
| Redis Cluster | $200 |
| Kafka (real-time) | $100 |
| CDN (CloudFront) | $50 |
| Monitoring (Datadog) | $200 |
| API costs (Anthropic) | $2,000 (1,000 users × $2) |
| **합계** | **$3,350/월 (~₩4.5M)** |

Revenue model: $30/user/월 × 1,000 = $30,000/월. Gross margin 88%.

---

# VCB-Alt v3.0 — Security & Compliance

## 1. Phase 1 Security (Personal)

### 1.1 API Key 관리
- `.env` 파일에만 저장 (코드 X)
- `.gitignore`에 `.env` 포함
- `chmod 600 .env` (소유자만 읽기)
- API key 정기 rotation (분기당)

### 1.2 데이터 보안
- 모든 데이터 로컬 저장 (cloud 동기화 X)
- DB encryption (SQLCipher 권장)
- Backup도 encrypted (gpg)

### 1.3 네트워크
- VPN 사용 (American 시장 접속)
- HTTPS only
- 거래소 API 사용 X (Phase 1 — broker 직접 입력)

## 2. Phase 2+ Security (Multi-user)

### 2.1 Authentication
- OAuth 2.0 (Google / Apple)
- 2FA 필수
- Session token 1시간 만료

### 2.2 Authorization
- User별 데이터 격리 (multi-tenant)
- RBAC (read/write/admin roles)

### 2.3 Compliance
- SOC 2 Type II (Phase 3+)
- GDPR (EU user)
- PIPA (한국 사용자)

## 3. 법적 고려사항

### 3.1 Phase 1 (Personal)
- **본인 자본만 운용**: 자문업 등록 불필요
- **거래 자동화 X**: 시스템은 *알림만*, 사용자가 직접 거래
- **수익 보고**: 자본이득세 (한국 양도소득세)

### 3.2 Phase 2+ (Multi-user)
- **투자자문업 등록 필요** (한국 금융위)
- **이용약관 + 면책 조항** 필수
- **개인정보 처리방침**

### 3.3 Disclaimer 필수
```
본 시스템은 정보 제공 목적이며 투자 권유가 아닙니다.
실제 투자 결정 및 그에 따른 모든 책임은 사용자에게 있습니다.
과거 실적이 미래 수익을 보장하지 않습니다.
```

---

# VCB-Alt v3.0 — Testing Plan

## 1. Test Levels

### 1.1 Unit Tests (Phase별)
```python
# tests/test_phase1_archetypes.py
def test_archetype_A_PLTR_2024_strong_setup():
    inputs = StockInputs(...)  # PLTR 2024 mock
    score = detect_archetype_A_ai_tech(...)
    assert score.strength == STRONG_SETUP
    assert score.total_score >= 70

def test_archetype_A_neutral_stock_no_setup():
    # ...
```

### 1.2 Integration Tests
```python
# tests/test_phase4_integrated.py
def test_pltr_full_pipeline():
    inputs = mock_pltr_2024_inputs()
    decision = integrate_decision(inputs, bull_dd, pm)
    assert decision.combined_score >= 80
    assert decision.can_enter
```

### 1.3 End-to-End Tests
```python
# tests/test_e2e.py
def test_daily_pipeline_with_mock_data():
    # 1. Fetch (mock)
    # 2. Evaluate watchlist 30 종목
    # 3. Verify alerts generated
    # 4. Verify positions updated
```

### 1.4 Performance Tests
- Daily scan < 30분 (500 종목)
- Single stock < 10초
- Portfolio rebalancing < 5초

### 1.5 Backtest Tests (Phase 5)
- 42 historical cases ground truth
- TPR >= 80%, FPR <= 20%

## 2. Test Coverage Target
- Unit: 80%+
- Integration: 60%+
- E2E: 핵심 path 100%

---

# VCB-Alt v3.0 — Roadmap (12개월)

## Quarter 1: Month 1-3 (Foundation)

### Month 1 — Phase 0: Setup
- Week 1: Python env + 6 data source 검증
- Week 2: Active 13 파일 + import 검증
- Week 3-4: 5 데이터 fetcher 작성 + 테스트

### Month 2-3 — Phase 1: Paper Trading
- Week 5-12: Paper trading 8주
- Daily routine 30분 정착
- 가상 ₩50M으로 시뮬
- Week 12: Phase 2 진입 자격 self-test

## Quarter 2: Month 4-6 (Live Small)

### Month 4-5 — Phase 2: Small Live
- 시드 ₩5M로 시작
- 종목 3개 max
- Stop -8% 100% 준수
- 첫 분기 calibration (Bayesian opt 실데이터)

### Month 6 — 평가
- 3개월 P&L
- Win rate, Sharpe
- Phase 3 진입 자격 검증

## Quarter 3: Month 7-9 (Scale)

### Phase 3: Full Scale
- 시드 ₩30M-100M
- 종목 3개 (최적)
- 자동화 추가 (스크립트화)
- 월간 audit routine

## Quarter 4: Month 10-12 (Optimize)

### Phase 4: Operation 안정화
- News + Sentiment 자동화
- 분기 Bayesian opt 자동
- 1년 결과 audit
- Year 2 계획

## Year 2+ Plans

### Phase 5: SaaS 변환 (Optional)
- Multi-user database
- Web dashboard
- 베타 user 10명
- Revenue $300/월

### Phase 6: 확장
- Korean market 추가 (KOSPI)
- Crypto futures 추가
- Mobile app

---

# VCB-Alt v3.0 — README + Project Structure

## 1. Project Structure

```
vcb_alt_v3/
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── config.yaml
├── pyproject.toml
│
├── src/
│   ├── __init__.py
│   ├── cli.py                          # CLI entry point
│   │
│   ├── phase1_archetypes.py            # 6 archetype detectors
│   ├── phase2_portfolio.py             # Portfolio Manager
│   ├── phase3_complexity.py            # 4 complexity modules
│   ├── phase4_integrated.py            # Integration
│   ├── phase5_validation.py            # Historical validation
│   │
│   ├── module1_v2_surge.py             # Surge Predictor (BB/AVWAP/RSI)
│   ├── module2a_news.py                # News Catalyst
│   ├── module2b_sentiment.py           # Sentiment
│   ├── module3_market_regime.py        # Market Regime + Sector
│   ├── f3_v2_alt_data.py               # F3 v2 Alt Data
│   │
│   ├── data_fetcher.py                 # External data API
│   ├── db.py                           # SQLite ORM
│   ├── alerts.py                       # Email + Telegram
│   ├── scheduler.py                    # Cron orchestration
│   └── utils.py
│
├── tests/
│   ├── test_phase1_archetypes.py
│   ├── test_phase2_portfolio.py
│   ├── test_phase3_complexity.py
│   ├── test_phase4_integrated.py
│   └── test_e2e.py
│
├── data/
│   ├── vcb_alt.db                      # SQLite (gitignore)
│   ├── watchlist.json
│   └── universe.csv
│
├── logs/                               # gitignore
│
├── cache/                              # gitignore
│
├── product_docs/
│   ├── 01_PRD.md
│   ├── 02_Tech_Architecture.md
│   ├── 03_Data_Schema.md
│   ├── 04_API_Spec.md
│   ├── 05_Algorithm_Spec.md
│   ├── 06_Deployment_Operation.md
│   ├── 07_Cost_Infrastructure.md
│   ├── 08_Security_Compliance.md
│   ├── 09_Testing_Plan.md
│   ├── 10_Roadmap.md
│   └── 11_README.md
│
└── scripts/
    ├── init_db.py
    ├── backup_db.sh
    └── deploy_phase2.sh                # Cloud 배포 (future)
```

## 2. README.md

```markdown
# VCB-Alt v3.0 — Multibagger Hunter

미국 주식 단기 폭등 + 장기 우상향 종목 발굴 Personal Trading System.

## Quick Start

```bash
# 1. 가상환경
python3.11 -m venv vcb_env
source vcb_env/bin/activate

# 2. 설치
pip install -r requirements.txt

# 3. 환경설정
cp .env.example .env
nano .env  # API keys 입력

# 4. DB 초기화
python -m vcb_alt init_db

# 5. 일별 scan
python -m vcb_alt morning
```

## Documentation

- [PRD](product_docs/01_PRD.md) — Product Requirements
- [Tech Architecture](product_docs/02_Tech_Architecture.md)
- [Data Schema](product_docs/03_Data_Schema.md)
- [API Spec](product_docs/04_API_Spec.md)
- [Algorithm Spec](product_docs/05_Algorithm_Spec.md) ← **핵심**
- [Operation Manual](product_docs/06_Deployment_Operation.md)
- [Roadmap](product_docs/10_Roadmap.md)

## License

Personal use only. No warranty.

## Disclaimer

본 시스템은 정보 제공 목적이며 투자 권유가 아닙니다.
실제 투자 결정 및 책임은 사용자에게 있습니다.
```

## 3. .env.example

```bash
# API Keys
ANTHROPIC_API_KEY=sk-ant-xxx

# Email
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your@gmail.com
SMTP_PASSWORD=xxx
ALERT_EMAIL=your@gmail.com

# Telegram (optional)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Database
DATABASE_URL=sqlite:///./data/vcb_alt.db

# System
LOG_LEVEL=INFO
TIMEZONE=Asia/Seoul
```

## 4. Initial Setup Commands

```bash
# Day 1
python -m vcb_alt init_db
python -m vcb_alt watchlist add PLTR MSTR RGTI SMMT VST CEG SMR OKLO IONQ QBTS

# Day 2: Test data fetcher
python -m vcb_alt test fetch_prices PLTR
python -m vcb_alt test fetch_8k PLTR
python -m vcb_alt test fetch_short_interest GME

# Day 3: First dry-run
python -m vcb_alt scan --dry-run

# Day 4: Schedule cron
crontab -e
# (paste cron from Operation Manual)

# Day 5+: Phase 0 self-test
python -m vcb_alt self_test
```
