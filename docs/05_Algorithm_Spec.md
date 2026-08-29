# VCB-Alt v3.0 — Algorithm Specification

> **Design target, not a description of the build.** This is one of the original
> "VCB-Alt v3.0" specification documents from 2026-05. The shipped package is version
> 0.1.0 and does not implement everything described here - some CLI commands and API
> paths named below (`calibrate`, `evening`, `/api/v3/`, and others) do not exist.
> For what the software actually does today, read [../README.md](../README.md),
> [../RELEASE_DECISION.md](../RELEASE_DECISION.md) and
> [MARKET_DATA_PROVIDERS.md](MARKET_DATA_PROVIDERS.md).

## 1. System Overview

**Funnel**: 5,000 종목 (US 주식) → 1-3 종목 진입 결정.

7-step:
```
Step 1: Market Regime Gate           → 진입 허용 여부
Step 2: F1 Trend Template            → 5,000 → 500-800 (10-16% pass)
Step 3: F2 Multi-Pattern             → 500 → 100-200 (15-25% pass)
Step 4: Module 1 v2 Surge Predictor  → 매집/급등 leading 신호
Step 5: F3 v2 Alt Data               → 100 → 20-40
Step 6: F4 Cross-Reference + Modifiers → 20 → 5-10
Step 7: F5 Pivot Breakout + R:R       → 5 → 1-3 진입
```

각 step 알고리즘 상세:

---

## 2. Step 1: Market Regime (Module 3)

### 2.1 Base Regime Classification

```
Inputs:
  - SPX_close: 현재 S&P 500 종가
  - SPX_200dma: 200일 simple moving average
  - SPX_12m_return: 12개월 return %

Logic:
  if SPX_close > SPX_200dma AND SPX_12m_return >= 10%:
      regime = "Bull"
  elif SPX_close > SPX_200dma AND SPX_12m_return >= 0%:
      regime = "Mid"
  elif SPX_close > SPX_200dma AND SPX_12m_return < 0%:
      regime = "Caution"
  elif SPX_close <= SPX_200dma AND SPX_12m_return >= -15%:
      regime = "Bear"
  else:
      regime = "Crisis"
```

### 2.2 Drawdown Phase

```
Inputs:
  - SPX_drawdown_from_ath_pct: -X% (음수)

Logic:
  abs_dd = abs(SPX_drawdown_from_ath_pct)
  if abs_dd < 5: "normal"
  elif abs_dd < 10: "shallow"
  elif abs_dd < 15: "moderate"
  elif abs_dd < 25: "deep"
  else: "crisis"
```

### 2.3 5 Leading Indicators

| Indicator | Formula | Threshold (RED) |
|---|---|---|
| NYSE A-D line | cumulative (advancers - decliners) | 20DMA < -500 |
| Defensive Rotation | (XLU/SPY) 12W return diff | >+5pp |
| VIX Backwardation | VIX > VIX3M > VIX6M | true |
| Credit Spread | HYG/LQD ratio 12W change | -3%+ widening |
| High-Low Beta | RSP/SPHQ 12W change | -2pp |

```
warning_count = sum(indicator == RED for indicator in 5_indicators)

if warning_count >= 4: early_warning = "Red"
elif warning_count >= 2: early_warning = "Orange"
elif warning_count >= 1: early_warning = "Yellow"
else: early_warning = "Green"
```

### 2.4 Transition Detection

```
if regime in ["Bull", "Mid"] AND early_warning == "Red" for 5 consecutive days:
    transition = "Transition_to_Bear"
    new_entry_allowed = False

if regime in ["Bear", "Caution"] AND positive_indicators >= 3 for 5 consecutive days:
    transition = "Transition_to_Bull"
    new_entry_allowed = True
```

---

## 3. Step 2: F1 Trend Template (8 조건)

```
Inputs:
  - Price (current close)
  - 50DMA, 150DMA, 200DMA
  - 200DMA slope (직전 21일)
  - 52w_low, 52w_high

8 conditions (모두 충족 필수):
  1. price > 50DMA
  2. price > 150DMA
  3. price > 200DMA
  4. 150DMA > 200DMA
  5. 200DMA slope > 0 (직전 1개월+ 우상향)
  6. 50DMA > 150DMA AND 50DMA > 200DMA
  7. price >= 52w_low * 1.30 (52w 저점 +30% 이상)
  8. price <= 52w_high * 0.90 AND price >= 52w_high * 0.50
     (52w 고점 -10% ~ -50% 영역)

f1_passed = all 8 conditions
```

### F1 Archetype별 적용

| Archetype | F1 필수 | Exception |
|---|---|---|
| A AI/Tech | ✓ 필수 | - |
| B Crypto Pivot | ⚠ 부분 | 200DMA 회복 진행 중 OK |
| C Quantum | ✗ X | Penny stock (F1.7 통과 X 정상) |
| D Biotech | ⚠ 부분 | Catalyst-driven (F1.8 OK) |
| E Short Squeeze | ✗ X | -70% drawdown 영역에서 진입 |
| F Pick&Shovel | ✓ 필수 | - |

---

## 4. Step 3: F2 Multi-Pattern (5 patterns)

### 4.1 VCP (Volatility Contraction Pattern)
```
- Base duration: 6-52 주
- Contractions: 점진 축소 (12% → 8% → 5%)
- Last contraction: <= 12%
- Volume dry-up: last 4w / first 12w < 0.7
- Pivot point: base 고점
```

### 4.2 Cup & Handle
```
- Cup: U-shape, depth -12 ~ -33%, duration 7-65 weeks
- Handle: -2 ~ -15%, duration 1-6 weeks
- Volume dry-up in handle
- Pivot point: cup 고점
```

### 4.3 Double Bottom (W-Pattern)
```
- Two lows within ±5%
- Middle high
- Second decline from middle: >= -8%
- Recovery to middle high (volume increase)
```

### 4.4 Flat Base
```
- 5-12 weeks sideways
- Range <= ±15%
- Prior 6-month return >= +20%
- Volume dry-up
```

### 4.5 Bullish Flag (Module 1 추가)
```
- Pole: 5-15 days, +20%+
- Flag: 5-25 days, range <= 10%
- Prior 6-month return >= +50%
```

```
f2_passed = any pattern detected
```

---

## 5. Step 4: Module 1 v2 Surge Predictor (5 factors, 100 pts)

### BS1: Bollinger Band (200, 2) Squeeze (+20)
```
BB(200, 2):
  middle = SMA_200
  upper = middle + 2 * std_200
  lower = middle - 2 * std_200

BBW = (upper - lower) / middle

Squeeze trigger:
  current BBW <= min(BBW for past 6 months) * 1.05
```

### BS2: BB(200,2) W-Bottom (+25)
```
W-Bottom 패턴:
  1. price < BB Lower band (capitulation) — 직전 60일
  2. recovery > BB Middle (또는 -10% breach + 회복 15%+)
  3. 두 번째 breach가 첫 번째 -5% 이내 (W 형성)
```

### BS3: Anchored VWAP from major low (+20)
```
anchor_idx = argmin(price[-252:])  # 1년 최저

AVWAP[t] = sum(price[anchor:t] * volume[anchor:t]) / sum(volume[anchor:t])

조건:
  - price > AVWAP (현재)
  - AVWAP slope (직전 20일) > 0
```

### BS4: AVWAP ±3σ Recovery (+15)
```
ATH anchor: argmax(price[-252:])  # 1년 ATH

AVWAP + ±3σ bands:
  variance = sum(volume * (price - vwap)^2) / sum(volume)
  std = sqrt(variance)
  lower_3sigma = vwap - 3 * std

조건:
  - 직전 60일 가격이 lower_3sigma 통과 (capitulation)
  - 현재 가격 > lower_3sigma (회복)
```

### BS5: RSI Bullish Divergence (+15)
```
RSI(14):
  RS = avg_gain / avg_loss
  RSI = 100 - 100 / (1 + RS)

Divergence 조건:
  직전 60일을 두 반으로 나눔:
    - First half min price > Second half min price (price LL)
    - First half min RSI < Second half min RSI + 5 (RSI HL)
  AND 전체 추세 |change| < 30%
```

### Surge Total
```
total = bs1 + bs2 + bs3 + bs4 + bs5  # max 95

if total >= 75: STRONG_SURGE
elif total >= 50: SURGE_SETUP
elif total >= 30: WEAK_SETUP
else: NO_SETUP
```

---

## 6. Step 5: F3 v2 Alt Data (5 components, max 100)

### 6.1 CRV (Capital Reallocation Velocity)
```
5 components, each 0-20:
  CRV.1: Capex/Revenue 4Q 변화 >= +2pp → 20
  CRV.2: R&D/Revenue 4Q 변화 >= +1.5pp → 20
  CRV.3: 신규 segment 매출 성장 >= +50% → 20
  CRV.4: 24개월 M&A 인수 >= 2건 → 20
  CRV.5: Capex 절대 YoY >= +25% → 20

CRV_score = sum / 5 * 100 (max 100)
fired = CRV_score >= 60
```

### 6.2 ICA (Insider Conviction Asymmetry)
```
ICA.1: tier-weighted (CEO×3, CFO×3, EVP×1.5)
  net_score = sum(insider_purchases * tier_weight - insider_sells * tier_weight)
  fire if net_score >= 5

ICA.2: 시총 대비 내부자 취득액 >= 0.05%
ICA.3: CEO/CFO 자발적 취득 (binary)
ICA.4: 180일 자발적 매도 부재
ICA.5: Quality 13F holder 신규 진입 (Berkshire, GMO 등)

ICA_score = sum * 20 (max 100)
```

### 6.3 CEI (Capital Efficiency Inflection)
```
CEI.1: ROIC trough 후 분기 회복 >= +1pp
CEI.2: Operating Margin 5Y 25 percentile 통과
CEI.3: 매출 4Q 가속 >= +3pp
CEI.4: FCF 회복 (음수 → 양수 또는 +50%)
CEI.5: 재고일수 정점 후 감소

CEI_score = fired_count * 20 (max 100)
```

### 6.4 TLS (Transcript Linguistic Shift) — LLM 호출
```
LLM (Claude Haiku) prompt:
  6 components:
    1. 자신감 어휘 ↑
    2. Hedging 어휘 ↓
    3. 신규 product/tech 키워드 첫 등장
    4. Q&A 구체성 ↑
    5. Forward guidance 명확 상향
    6. 경쟁사 언급 ↓
  
  output: JSON with each component 0-100

TLS_score = avg of 6 components
```

### 6.5 WAS (Web Activity Stack) — sector-specific
```
For B2C / Semi / B2B Software:
  WAS.1: Similarweb traffic 6M trend >= +20%
  WAS.2: App Store ranking improvement
  WAS.3: Reddit mention z-score >= +1
  WAS.4: Google Trends 6M trend >= +30%
  WAS.5: 채용 증가 >= +20%

WAS_score = fired * 20 (max 100)
WAS = N/A for Pharma, Utilities, Industrial
```

### F3 Composite
```
universal_fires = sum(score >= 60 for score in [CRV, ICA, CEI, TLS])

if universal_fires >= 4 AND composite >= 75:
    PREMIUM (Mode 2 후보)
elif universal_fires >= 3 AND composite >= 60:
    STANDARD (Mode 1 후보)
else:
    FAIL
```

---

## 7. Step 6: F4 Cross-Reference + Multi-Modifier

### 7.1 6 Anomaly 검증
```
1. Reflexive Recovery:
   WAS 가속 (>50) AND 매출 둔화 (4Q acceleration < 0)
   → alt data leading 펀더 회복
   modifier: +10

2. Capex-Hiring Divergence:
   CRV 가속 (>70) AND 채용 보통 (<30%)
   → 자동화 factor
   modifier: +8

3. Patent-Product Lag:
   R&D 가속 AND 신규 키워드 등장 (TLS)
   → launch 임박
   modifier: +10

4. Reflexivity Trigger:
   차트 base (F2 fired) AND alt 모두 강함 (composite > 80)
   modifier: +20

5. Industry vs Stock Divergence:
   산업 약세 (sector RS < 0) AND 종목 outperform (RS > +10)
   → 진짜 winner
   modifier: +12

6. Insider-Quality Divergence:
   CEO 취득 (ICA.3) AND 13F quality (ICA.5) 동시
   modifier: +15
```

### 7.2 Multi-Modifier

```python
def calc_f4_composite(base, modifiers):
    """
    base: F3 v2 composite (0-100)
    modifiers: dict of additional factors
    """
    base_capped = min(base, 80)  # base cap, modifier 효과 보장
    
    bottom_phase = modifiers.get('bottom_phase', 0)      # Wyckoff Phase D: +15
    indicator_mod = modifiers.get('indicator', 0)        # RSI/OBV/MACD: -25 ~ +25
    catalyst_mod = modifiers.get('catalyst', 0)          # News 8-K: -15 ~ +15
    sentiment_mod = modifiers.get('sentiment', 0)        # Reddit: -20 ~ +15
    sector_boost = modifiers.get('sector_boost', 1.0)    # Module 3 sector: 1.0-1.20x
    
    composite = (base_capped + bottom_phase + indicator_mod + 
                  catalyst_mod + sentiment_mod) * sector_boost
    
    return max(0, min(100, composite))
```

### 7.3 Pass criteria
```
f4_passed = composite >= 65
```

---

## 8. Step 7: F5 Pivot Breakout + R:R

### 8.1 Breakout Trigger
```
3 conditions (모두):
  1. close > pivot_point (F2 base 고점)
  2. volume >= 50DMA_volume * 1.5
  3. close_strength >= 70
     (close_strength = (close - day_low) / (day_high - day_low) * 100)
```

### 8.2 R:R Calculation
```
Upside (2-method avg):
  Method 1 (Measured Move): pivot + (base_high - base_low)
  Method 2 (Extension): pivot + (base_high - base_low) * 1.5
  upside_target_1 = method_1
  upside_target_2 = method_2

Downside (3중 결합 — entry에 가장 가까운 것):
  Method A: entry * 0.92 (-8% 절대)
  Method B: entry - ATR(14) * 1.5
  Method C: pivot * 0.97 (pivot - 3%)
  stop = max(A, B, C)  # entry에 가장 가까운

R:R = (upside_target_1 - entry) / (entry - stop)
```

### 8.3 Mode Decision
```
if f3_premium AND r_r >= 5 AND market_mode2_allowed:
    Mode 2 (HIGH_RESEARCH_CANDIDATE, research size reference 23%)
elif r_r >= 3:
    Mode 1 (RESEARCH_CANDIDATE, research size reference 12%)
else:
    WAIT
```

---

## 9. Phase 1: 6 Archetype Detection

각 archetype은 *F1-F5 funnel 통과 후* 추가 evaluation:

### 9.1 Archetype A — AI/Tech Megatrend
```
A1 매출 가속: surprise >= 20% AND 4Q acceleration >= 5pp → +25
A2 Tech sector RS: 12W vs SPY >= +10pp → +20
A3 Insider purchase activity: CEO/CFO 90일 >= 2건 → +20
A4 Chart base + breakout: 6-24w base + vol 1.5x → +20
A5 Forward guidance 상향: binary → +15

Score: 0-100
```

### 9.2 Archetype B — Crypto Pivot
```
B1 BTC 6M return >= 30% → +25
B2 Company BTC announcement OR mining +30% → +25
B3 Chart -50% drawdown 후 회복 + 200DMA 위 → +20
B4 Volume z-score >= 2.5 → +15
B5 News catalyst (convertible, GPU 구매) → +15

Score: 0-100
```

### 9.3 Archetype C — Quantum/Emerging
```
C1 Float < 50M AND market cap < $500M → +20
C2 정부/기업 계약 announcement → +25
C3 Peer 30일 평균 >= +30% → +20
C4 Volume spike 5x+ → +15
C5 12-12M base + 가격 $1-10 → +20

Score: 0-100
```

### 9.4 Archetype D — Biotech Catalyst
```
D1 FDA milestone (Phase 3 / PDUFA) 30-90일 → +30
D2 Chart base + volume dry-up → +20
D3 Insider purchase activity cluster → +15
D4 Short interest < 10% (squeeze 회피) → +15
D5 시총 $50M-$500M → +20

Score: 0-100
```

### 9.5 Archetype E — Short Squeeze
```
E1 Short interest >= 25% (★ absolute) → +30
E2 Days to cover >= 5 → +15
E3 Borrow rate >= 50% APY → +15
E4 Drawdown ATH -70%+ → +15
E5 Positive catalyst + sentiment spike → +15
E6 Options call OI 30일 +200%+ → +10

Score: 0-100
```

### 9.6 Archetype F — AI Pick & Shovel
```
F1 AI sector rally 6-12개월 진행 → +25
F2 Sector RS 12W >= +20pp → +20
F3 Long base 12-24개월 → +20
F4 AI data center narrative → +15
F5 EPS revision +20%+ → +20

Score: 0-100
```

### Setup Classification
```
score >= 70: STRONG_SETUP
score >= 50: SETUP
score < 50: NO_SETUP
```

---

## 10. Phase 3: 4 Complexity Modifiers

### 10.1 Short Interest Score
```
SI Level: 0-40 (>= 50% extreme)
Days to Cover: 0-25 (>= 10)
Borrow Rate: 0-20 (>= 100% APY)
SI Trend 7-day: 0-15 (>= +5pp)

Total: 0-100
```

### 10.2 Options Flow Score
```
Unusual call volume vs 30DMA: 0-30 (10x+)
C/P ratio: 0-25 (>= 5)
Weekly OTM call concentration: 0-25 (>= 40%)
30D OI change: 0-20 (>= 300%)

Total: 0-100
```

### 10.3 EDGAR 8-K Score
```
Catalyst type: 0-40 (FDA approval, Pentagon, AI partnership)
Materiality: 0-25 ($ amount)
Recency: 0-20 (1-day = 20)
Source quality (8-K SEC): +15

Total: 0-100
```

### 10.4 On-Chain Score (Archetype B만)
```
BTC 6M return: 0-35 (>= 80% extreme)
BTC dominance: 0-15 (50-65% healthy)
F&G index: 0-15 (50-75 healthy)
Stablecoin flow: 0-20 (>= 5% increase)
Funding rate: 0-15 (0.5-2%)

Total: 0-100
```

### Archetype별 Weight
```
Module           | A   | B   | C   | D   | E   | F
─────────────────|─────|─────|─────|─────|─────|─────
Short Interest   | 0.3 | 0.5 | 0.5 | -1.0| 1.0 | 0.3
Options Flow     | 0.5 | 0.7 | 1.0 | 0.5 | 1.0 | 0.5
8-K SEC EDGAR    | 1.0 | 0.7 | 0.7 | 1.0 | 0.5 | 0.7
On-Chain Crypto  | 0.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0
```

### Modifier 계산
```python
def calc_modifier(complexity_score, archetype, weight_table):
    """
    complexity_score: 0-100 (Phase 3)
    Return: signed modifier (-25 ~ +25)
    """
    weight = weight_table[archetype][module]
    raw_modifier = (complexity_score - 50) * 0.30
    return int(raw_modifier * weight)
```

---

## 11. Phase 4: Integration

```python
def integrate_decision(inputs, market_dd, portfolio_manager):
    # 1. 6 archetype 모두 평가
    all_scores = evaluate_all_archetypes(inputs)
    
    # 2. Primary + secondary 선정 (top 2 by score)
    sorted_scores = sorted(all_scores.items(), key=lambda x: x[1].total_score, reverse=True)
    primary = sorted_scores[0]
    secondary = sorted_scores[1] if sorted_scores[1].total_score >= 50 else None
    
    # 3. 4 복잡계 modifier (primary archetype 기준)
    modifiers = evaluate_complexity_modifiers(inputs, primary.archetype)
    total_modifier = sum(modifiers.values())
    
    # 4. Combined score
    combined = max(0, min(100, primary.total_score + total_modifier))
    
    # 5. Portfolio Manager 진입 결정
    pm_decision = portfolio_manager.evaluate_entry(
        ticker=inputs.ticker,
        archetype_score=primary,  # with combined score
        drawdown_state=market_dd,
    )
    
    return IntegratedDecision(...)
```

---

## 12. Phase 2: Portfolio Manager

### 12.1 Entry Decision Logic

```python
def evaluate_entry(ticker, archetype_score, drawdown_state):
    # 1. Setup strength
    if score.strength == NO_SETUP:
        return reject("Score < 50")
    
    # 2. P0-2 Cooldown (7일)
    if (current_day - last_entry_day) < 7:
        return reject("Cooldown")
    
    # 3. P1 High-vol archetype 1개 max
    if archetype in [C, D, E]:
        if any other slot has archetype in [C, D, E]:
            return reject("High-vol 1개 max")
    
    # 4. Archetype 중복 (Bull market + Strong Setup만 허용)
    if same_archetype_count >= 2:
        return reject("이미 2건")
    elif same_archetype_count == 1:
        if not (is_bull_market AND strength == STRONG_SETUP):
            return reject("중복 제한")
    
    # 5. 빈 slot 찾기
    target_slot = first empty slot
    if not target_slot:
        return reject("5/5 full")
    
    # 6. Drawdown size boost
    boost = calc_drawdown_size_boost(drawdown_state, archetype)
    
    # 7. 최종 size
    base = archetype.suggested_size_pct  # 18-25
    strength_factor = 1.0 if STRONG else 0.7
    score_factor = 0.7 + 0.3 * (score - 50) / 50
    slot_factor = {0: 1.0, 1: 1.0, 2: 1.0, 3: 0.7, 4: 0.5}[occupied_slots]
    
    final = base * strength_factor * score_factor * boost * slot_factor
    
    # P0-1 Archetype cap
    archetype_caps = {A: 25, B: 22, C: 18, D: 18, E: 18, F: 25}
    final = min(archetype_caps[archetype], final)
    
    return accept(target_slot, final)
```

### 12.2 Drawdown Boost

```python
def calc_drawdown_size_boost(drawdown_state, archetype):
    base_boost = {
        'normal': 0.85,        # cash 보존
        'shallow': 1.0,
        'moderate': 1.20,      # 진입 최적 영역
        'deep': 1.25,
        'crisis': 1.20 if recovering else 0.5,
    }[drawdown_state.phase]
    
    archetype_factor = {
        A: 1.0,    # full market sensitivity
        B: 0.7,    # BTC cycle 별개
        C: 0.5,    # quantum 독립
        D: 0.7,    # FDA calendar 자체
        E: 0.5,    # squeeze 독립
        F: 1.0,
    }[archetype]
    
    if base_boost > 1.0:
        boost = 1.0 + (base_boost - 1.0) * archetype_factor
    else:
        boost = base_boost
    
    return boost
```

---

## 13. Validation & Calibration

### 13.1 Walk-Forward Backtest
```
For each fold (test_year 2015-2024):
    train_cases = cases where year ∈ [test_year-5, test_year-1]
    test_cases = cases where year == test_year
    
    # Bayesian optimization on train (4 groups)
    optimized_thresholds = bayesian_optimize(train_cases, threshold_groups)
    
    # Test
    metrics = evaluate(test_cases, optimized_thresholds)
```

### 13.2 4 Threshold Groups
```
Group 1: Setup Strength (3 thresholds)
Group 2: Archetype A/F Fundamental (3 thresholds)
Group 3: Archetype B/C/D Catalyst (3 thresholds)
Group 4: Archetype E + Position Sizing (3 thresholds)
```

### 13.3 Sensitivity Test
```
For each threshold:
    plus_20 = base * 1.20
    minus_20 = base * 0.80
    
    impact = (metric_plus - metric_base) / abs(metric_base)
    is_robust = max(|impact_plus|, |impact_minus|) < 0.30
```

---

## 14. Performance Targets

| Metric | Target | Validation |
|---|---|---|
| TPR (multibagger 적중) | >= 70% | walk-forward |
| FPR (failure 진입) | <= 20% | walk-forward |
| Avg holding | 1-12개월 | live |
| Win rate | >= 50% | live |
| Sharpe ratio | >= 1.2 | live |
| Max drawdown | <= -25% | live |
| Annual return | >= +30% | live |
