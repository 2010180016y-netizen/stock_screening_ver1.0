# VCB-Alt v3.0 — Product Requirements Document (PRD)

> **버전**: 1.0 — 2026.05  
> **작성자**: Hoiki + 11명 전문가 패널 (Renaissance, Citadel, Bridgewater 등)  
> **상태**: Active Development  

---

## 1. Executive Summary

### 1.1 무엇을 만드는가
**VCB-Alt v3.0** — 미국 주식 시장에서 단기 폭등 종목 + 장기 우상향 종목을 *6 archetype 정량 알고리즘*으로 발굴하는 **Personal Trading System**.

### 1.2 누구를 위해
- **Primary user**: Hoiki (CJ ENM 전략기획, 시드 ₩30M-100M)
- **Secondary user** (future SaaS): retail 투자자 (시드 ₩10M-₩1B)
- **Anti-user**: 헤지펀드 (시드 $10M+ — agility 떨어짐)

### 1.3 핵심 가치 제안 (Value Prop)
**S&P 500 대비 +30-50%pp alpha, 5년 expected 6-7x (₩100M → ₩600-700M).**

11명 전문가 패널 합의:
- 평균 헤지펀드 (CAGR 10%) outperform 가능 80%
- S&P 500 (CAGR 12%) outperform 가능 80%
- Medallion (CAGR 39%) outperform 불가능
- Berkshire long-term outperform 5년 단위 가능, 15년+ 불가능

### 1.4 차별화 — 6 Archetype 동시 추적

| Archetype | 대상 | Holding | Target |
|---|---|---|---|
| A. AI/Tech Megatrend | NVDA, PLTR, APP | 6-18M | +200-700% |
| B. Crypto Pivot | MSTR, IREN, MARA | 3-9M | +200-500% |
| C. Quantum/Emerging | RGTI, QBTS, IONQ | 1-3M | +500-1500% |
| D. Biotech Catalyst | SLNO, MNPR, SMMT | 1-30D | +50-500% |
| E. Short Squeeze | GME, AMC, RKLB | 2-12W | +200-1700% |
| F. AI Pick & Shovel | VST, SMR, CEG | 3-6M | +200-500% |

---

## 2. Goals & Non-Goals

### 2.1 Goals (Year 1)

**Quantitative**:
- 시드 ₩30M → 12개월 후 ₩50M+ (CAGR 65%+) — *optimistic*
- 시드 ₩30M → 12개월 후 ₩40M+ (CAGR 30%) — *realistic*
- Max drawdown ≤ -25%
- Sharpe Ratio ≥ 1.2
- Win rate ≥ 50%

**Qualitative**:
- 매일 30분 이내 운용
- 시스템이 *진입 결정* 자동화 (사용자는 trigger 확인 + 실행)
- 6 archetype 모두 추적
- 단기 (1-3개월) + 장기 (5-7년) 둘 다 cover

### 2.2 Non-Goals

❌ HFT (High Frequency Trading) — 우리는 1-12개월 holding  
❌ 실시간 가격 streaming — 일별 close price 충분  
❌ Options trading — 주식만  
❌ Margin / 레버리지 — Cash account 운용  
❌ Multi-user SaaS (Phase 1) — 1인 사용 우선  
❌ Mobile app (Phase 1) — Web/CLI 우선  
❌ Korean stock (KOSPI/KOSDAQ) — 미국만 (NYSE/NASDAQ)  

### 2.3 Success Criteria (12개월 후)

| 측정 | Target | Critical Failure |
|---|---|---|
| Annual return | +30% | < 0% (S&P 500 못 미침) |
| Max drawdown | -25% | -40%+ |
| 운용 시간/일 | 30분 | 2시간+ |
| 시스템 안정성 | 99% uptime | < 90% |
| 사용자 규율 (Stop 준수) | 95%+ | < 70% |

---

## 3. User Personas

### Persona 1: Hoiki (Primary)
- 35세, 한국 거주, 영어/중국어/한국어
- 직업: CJ ENM 전략기획 (10년 경력)
- 시드: ₩30M-100M
- 시간: 30분-1시간/일 (본업 외)
- 기술: Python 중급, Quant/ML 경험 있음
- 목표: *시드 적은 시간에 최대 자산 증식*
- 위험 감수: 보통 (시드 -25% drawdown 견딜 수 있음)
- 심리: Revenge trading 경험 있음 (관리 필요)

### Persona 2 (Future): Retail Trader
- 25-45세, 미국/한국 거주
- 시드: $10K-$1M
- 시간: 1시간/일
- 기술: Python 초보 또는 GUI 사용자
- 차이: GUI 필요, 시스템 자동화 ↑

---

## 4. User Stories

### Epic 1: Daily Operation
**US-1.1**: 사용자로서, 매일 아침 시장 환경 + 보유 종목 stop 확인을 30분 이내 완료하고 싶다.
- AC: Module 3 (Market Regime) 자동 실행, 결과 dashboard 표시
- AC: 보유 3 종목 가격 + stop 거리 자동 표시
- AC: 진입 후보 watchlist (Strong Setup 종목) 자동 추출

**US-1.2**: 사용자로서, 저녁 시장 마감 후 catalyst (8-K, 뉴스) 빠르게 검토하고 싶다.
- AC: SEC EDGAR 8-K filing 자동 fetch (oneself 종목)
- AC: 키워드 검색 (FDA, contract, Bitcoin, partnership)

### Epic 2: Stock Discovery
**US-2.1**: 사용자로서, 6 archetype 별 신규 후보 종목 매주 자동 발견하고 싶다.
- AC: 매주 일요일 자동 스캔
- AC: 각 archetype score >= 50 종목 list
- AC: Combined score (Phase 4) >= 55 종목 priority

**US-2.2**: 사용자로서, 종목별 시스템 score 상세를 확인하고 싶다.
- AC: F1, F2, F3, F4, F5 + 6 archetype + 4 복잡계 모두 표시
- AC: 진입 결정 (Mode 1/2 + size) 자동 계산

### Epic 3: Portfolio Management
**US-3.1**: 사용자로서, 종목 3개 (최적) + 5개 (최대) 자동 관리하고 싶다.
- AC: Slot-based portfolio (Primary 1-3, Secondary 4-5)
- AC: 신규 진입 시 archetype 분산 자동 검증
- AC: Position size archetype별 cap (18-25%) 자동 적용

**US-3.2**: 사용자로서, Drawdown 환경별 size 자동 조정하고 싶다.
- AC: S&P 500 drawdown 자동 측정
- AC: Normal/Shallow/Moderate/Deep/Crisis 분류
- AC: Size boost 0.85x ~ 1.20x 자동 적용

### Epic 4: Risk Management
**US-4.1**: 사용자로서, Stop -8% 자동 알림 받고 싶다.
- AC: 가격이 stop 도달 시 즉시 알림 (이메일 / Telegram)
- AC: 청산 트리거 자동 (실 거래 X, 알림만)

**US-4.2**: 사용자로서, 신규 진입 cooldown (7일) 자동 강제하고 싶다.
- AC: 직전 진입 후 7일 내 신규 진입 차단
- AC: High-vol archetype (C/D/E) 동시 1개 max 강제

### Epic 5: Audit & Learning
**US-5.1**: 사용자로서, 월간 audit 자동 생성 받고 싶다.
- AC: 종목별 P&L, archetype별 성과, win rate, Sharpe
- AC: 놓친 multibagger 분석 (왜 차단됐나)
- AC: False positive 분석 (왜 진입했나)

---

## 5. Functional Requirements

### FR-1: Market Regime Detection
- 입력: S&P 500 daily price (1년+)
- 출력: regime (Bull/Mid/Caution/Bear/Crisis) + drawdown phase
- 처리 시간: < 5초

### FR-2: Archetype Detection
- 입력: 종목별 StockInputs (펀더 + 차트 + insider + sector)
- 출력: 6 archetype score (0-100 each) + primary/secondary
- 처리 시간: 종목당 < 2초

### FR-3: Complexity Modifiers
- 입력: Short interest, options flow, 8-K filing, on-chain
- 출력: archetype별 weighted modifier (-25 ~ +25)
- 처리 시간: 종목당 < 5초 (data fetch 포함)

### FR-4: Portfolio Manager
- 입력: New candidate + current portfolio + market regime
- 출력: Entry decision + size + stop + target
- 처리 시간: < 1초

### FR-5: Alert System
- Stop 도달 시 즉시 알림 (이메일 / Telegram)
- 신규 Strong Setup 종목 발견 시 알림
- 월간 audit 자동 발송

---

## 6. Non-Functional Requirements

### NFR-1: Performance
- Daily scan (universe 500 종목): < 30분
- Single stock evaluation: < 10초
- Portfolio rebalancing: < 5초

### NFR-2: Reliability
- Uptime: 99% (cron 매일 실행)
- Data fetch retry: 3회 (network failure 시)

### NFR-3: Security
- API key (yfinance / Alpaca) 환경변수 (절대 코드 X)
- 사용자 portfolio 정보 로컬 저장 (cloud 안 함)
- 2FA — 진입 결정 시 사용자 확인 필수 (자동 거래 X)

### NFR-4: Scalability (Future)
- Phase 1: 1 user, local 운용
- Phase 2: Multi-user (10-100명) → cloud DB
- Phase 3: SaaS (1,000+ users) → Kubernetes

### NFR-5: Cost
- Phase 1 (Personal): $30/월 이내
- Phase 2 (Multi-user): $300/월 이내
- Phase 3 (SaaS): user당 $15-30 marginal cost

---

## 7. Constraints & Assumptions

### Constraints
- 미국 주식만 (한국 broker 통해 거래)
- 시드 ₩30M-100M (개인 자본)
- 사용자 시간 30분-1시간/일
- 데이터 source 무료 우선 (유료 source ROI 검증 후 도입)

### Assumptions
- 시장 환경 *주기적* (Bull-Mid-Caution 회전)
- 멀티배거 종목 6 archetype 패턴 *재발* (2020-2025 검증)
- 사용자 규율 95%+ 유지 가능

---

## 8. Risks & Mitigation

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| 시장 환경 변화 (regime shift) | High | High | Module 3 자동 인식 + 진입 동결 |
| 사용자 규율 실패 (Stop 미준수) | Medium | Critical | Phase 1 paper trading 강제 + 알림 자동화 |
| 데이터 quality (yfinance fail) | Medium | Medium | Fallback source (Alpaca, FMP) |
| 임계값 calibration 실패 | Medium | High | 분기당 Bayesian opt + sensitivity test |
| Alpha decay (학술 신호 효과 ↓) | Low | Medium | 신규 archetype 추가 (Year 2+) |
| 법적 risk (개인 운용은 N/A) | Low | Low | 본인 자본만 운용, 자문 X |
| 심리 압박 (-25% drawdown) | High | Medium | Phase 1 paper trading 8주 |

---

## 9. Out of Scope (Year 1)

- 자동 거래 (사용자가 직접 실행)
- Mobile app
- Korean stock
- Crypto futures
- Options
- 다중 broker 통합
- 다국어 (Korean only)
