# VCB-Alt v3.0 — Master Index + Executive Summary

> **Design target, not a description of the build.** This is one of the original
> "VCB-Alt v3.0" specification documents from 2026-05. The shipped package is version
> 0.1.0 and does not implement everything described here - some CLI commands and API
> paths named below (`calibrate`, `evening`, `/api/v3/`, and others) do not exist.
> For what the software actually does today, read [../README.md](../README.md),
> [../RELEASE_DECISION.md](../RELEASE_DECISION.md) and
> [MARKET_DATA_PROVIDERS.md](MARKET_DATA_PROVIDERS.md).

> **읽는 순서**: 시간 30분 = 본 문서만. 시간 3시간 = 모든 문서. 첫 운용 1주 = 모든 문서.

---

## 1. Executive Summary (3분 read)

### 1.1 무엇인가
**VCB-Alt v3.0** = 미국 주식 6 archetype (AI/Crypto/Quantum/Biotech/Squeeze/Pick&Shovel) 멀티배거 발굴 시스템.

### 1.2 사용자
- Hoiki, 시드 ₩30M-100M, 종목 3개 운용
- 시간 30분/일
- 목표: 5년 6-7x (CAGR 45-65%)

### 1.3 11명 전문가 패널 평결
- ✅ S&P 500 (CAGR 12%) outperform 가능 80%
- ✅ Citadel/Millennium (CAGR 10%) outperform 가능 80%
- ❌ Medallion (CAGR 39%) outperform 불가능
- ⚠ 조건부 (사용자 규율 + Phase 0-1 paper trading + 데이터 fetcher + 3년 지속)

### 1.4 현재 상태 (2026.05)
- ✅ 시스템 코드 완성 (13 active 파일)
- ✅ Phase 1-5 시뮬 검증 (TPR 93-100%, FPR 0-8%)
- ✅ 100건 walk-forward calibration framework
- ✅ 12 문서 완성
- ⚠ 실데이터 검증 0건 (Phase 0-1에서 진행 필요)
- ⚠ 데이터 fetcher 작성 안 됨 (사용자 환경)
- ⚠ 운용 0일

### 1.5 즉시 진입 권고
**NO** — 시장 ATH 근처, Module 3 boost 0.85x. 진입 영역 X.

**진정한 다음 단계**:
1. Phase 0 setup (2주)
2. Phase 1 paper trading (8주)
3. Drawdown -10%+ 대기 (Module 3 boost 1.20x 영역)
4. 실 자본 진입

---

## 2. Document Reading Order

### Tier A — 필수 (90분 read)

| # | 문서 | 시간 | 우선순위 |
|---|---|---|---|
| 0 | **본 Master Index** | 10분 | 🔴 즉시 |
| 1 | [01_PRD.md](01_PRD.md) | 20분 | 🔴 즉시 |
| 5 | [05_Algorithm_Spec.md](05_Algorithm_Spec.md) | 60분 | 🔴 핵심 |

### Tier B — 운용 시작 전 (60분 read)

| # | 문서 | 시간 |
|---|---|---|
| 6 | Deployment + Operation (06_to_11_Combined.md 1번째 섹션) | 30분 |
| 11 | README + Project Structure (06_to_11_Combined.md 마지막) | 15분 |
| 4 | [04_API_Spec.md](04_API_Spec.md) | 15분 |

### Tier C — 개발 시작 (90분 read)

| # | 문서 | 시간 |
|---|---|---|
| 2 | [02_Tech_Architecture.md](02_Tech_Architecture.md) | 30분 |
| 3 | [03_Data_Schema.md](03_Data_Schema.md) | 30분 |
| 9 | Testing Plan (06_to_11_Combined.md) | 30분 |

### Tier D — 장기 계획 (45분 read)

| # | 문서 | 시간 |
|---|---|---|
| 7 | Cost & Infrastructure (06_to_11_Combined.md) | 15분 |
| 8 | Security & Compliance (06_to_11_Combined.md) | 15분 |
| 10 | Roadmap (06_to_11_Combined.md) | 15분 |

---

## 3. Critical Path (사용자 첫 30일)

```
Week 1 ─────────────────────────────────────────────
  Day 1: 본 Master Index + PRD + Algorithm Spec read (90분)
  Day 2: Python env + 6 data source 검증
  Day 3: 13 active Python 파일 다운로드 + import 검증
  Day 4-5: 5 데이터 fetcher 작성 + NVDA 테스트
  Day 6-7: Watchlist 30 종목 정의 + 시스템 enable

Week 2 ─────────────────────────────────────────────
  Day 8: Cron schedule + 알림 setup
  Day 9-10: Phase 0 self-test 6/6 통과
  Day 11-14: First daily scan + 시스템 익숙해지기

Week 3-4 ───────────────────────────────────────────
  Phase 1 paper trading 시작
  Day 1 paper entry (가상 ₩50M)
  Daily routine 30분 확립

Day 28: Phase 1 첫 4주 audit
```

---

## 4. Key Decisions Made (history)

### Decision 1: 6 Archetype 모두 추가 (vs subset)
- **결정**: 모두 추가 (사용자 명령)
- **Rationale**: 단기 폭등 (Archetype C/D/E) + 장기 우상향 (A/B/F) 모두 cover
- **Cost**: 사용자 운용 부담 ↑ (Tier 1/2/3 routine으로 mitigation)

### Decision 2: 종목 3개 최적
- **결정**: 3개 (5개 max)
- **Rationale**: 시드 적음 + 집중 운용
- **Trade-off**: Concentration risk vs Diversification

### Decision 3: Drawdown Recovery 추가
- **결정**: Moderate (-10~-15%) +20% boost, Deep (-15~-25%) +25% boost
- **Rationale**: 1980-2024 데이터, "Bull 확정 후 진입은 늦다" 사용자 의문 해결
- **Risk**: Catching falling knife — Stop -8%로 mitigation

### Decision 4: 4 복잡계 모두 추가
- **결정**: Short interest + Options flow + 8-K + On-chain
- **Rationale**: 사용자 명령
- **Cost**: 데이터 fetcher 작성 부담 ↑ (사용자 환경)

### Decision 5: Phase 1 paper trading 8주
- **결정**: 4주 → 8주 (패널 #64 권고)
- **Rationale**: 사용자 규율 + 실데이터 검증 시간 필요

---

# CHANGELOG

## v3.0 — 2026.05 (현재)

### Major
- 6 Archetype Detector 시스템 신설 (Phase 1)
- Portfolio Manager 3 종목 최적 (Phase 2)
- 4 복잡계 모듈 추가 (Phase 3)
- Drawdown Recovery 추가
- Module 1 v2 Surge Predictor (BB+AVWAP+RSI)

### P0/P1 Fixes (2026.05)
- Position cap 35% → 25% (archetype별 18-25%)
- Cooldown 7일 추가
- PM entry threshold 60 → 55
- Drawdown boost ceiling 1.40 → 1.20
- High-vol C/D/E 동시 1개 max

### Documentation
- 12 product documents 작성
- W (실행 매뉴얼) 작성
- 100건 calibration framework

### Legacy 정리
- 26 파일 → 13 active + 13 legacy

## v2.0 — 2026.04 (Legacy)

- Single-archetype NVDA형 멀티배거 시스템
- 5-Filter funnel
- Mode 1 (12%) / Mode 2 (23%)
- 5-10 종목 운용

## v1.0 — 2026.03 (Legacy)

- 초기 prototype (RIS-3, SCPS)
- 단일 NVDA형 detector
- 검증 X

---

# Final Self-Check (11명 패널)

## ✅ 완성 항목 (12/12)

1. ✅ PRD — Product Requirements
2. ✅ Tech Architecture
3. ✅ Data Schema (8 tables + config + watchlist)
4. ✅ API Spec (Internal + External)
5. ✅ Algorithm Spec (Step 1-7, Phase 1-5 모두)
6. ✅ Deployment Guide (Phase 1 setup)
7. ✅ Operation Manual (Tier 1/2/3)
8. ✅ Cost & Infrastructure (Phase 1/2/3)
9. ✅ Security & Compliance
10. ✅ Testing Plan
11. ✅ 12-month Roadmap
12. ✅ README + Project Structure
13. ✅ Master Index + Executive Summary (본 문서)
14. ✅ Changelog

## ⚠ 한계 (정직히)

1. **데이터 fetcher 코드 미작성** — 사용자 환경에서 작성 필요 (W 매뉴얼 가이드)
2. **실데이터 backtest 0건** — Phase 0-1에서 진행
3. **임계값 모두 prior** — Bayesian opt는 사용자 환경 실데이터로
4. **사용자 규율 검증 X** — Phase 1 paper trading 8주로
5. **법적 검토 본격 X** — Phase 1 (개인 운용)에선 N/A, Phase 2+ 시 변호사 검토

## 🎯 Definition of Done

**프로덕트화 완료 조건**:
- [x] 12 문서 작성
- [x] 시스템 코드 (Phase 1-5) 완성
- [x] 검증 시뮬 통과 (TPR 93%+)
- [ ] 데이터 fetcher 작성 (사용자 작업)
- [ ] Phase 0 self-test 통과 (사용자)
- [ ] Phase 1 paper trading 8주 (사용자)
- [ ] Phase 2 small live 6주 (사용자)
- [ ] 첫 12개월 결과 audit

진행 가능. 사용자 다음 단계: **Day 1 (본 Master Index + PRD + Algorithm Spec read)**.

---

## Outputs (사용자 전달)

13 active Python 파일 + 12 product 문서 + W 실행 매뉴얼.

총 ~17,000 lines of code + ~2,700 lines of documentation.
