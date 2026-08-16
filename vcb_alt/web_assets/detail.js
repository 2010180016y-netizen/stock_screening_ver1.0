
const detailState = {
  lang: localStorage.getItem('vcb_lang') || 'en',
  data: null
};

const DETAIL_I18N = {
  en: {
    ticker_analysis: 'Ticker analysis',
    dashboard: 'Dashboard',
    five_year_chart: 'Five-year price and volume',
    current_status: 'Current status',
    ai_summary: 'Explanation summary',
    industry_profile: 'Industry and profile',
    selection_reason: 'Selection reason',
    expert_consensus: 'Expert consensus',
    required_review: 'Required review set',
    score: 'Score',
    review_state: 'Review state',
    allocation_guide: 'Research size reference',
    risk_reference: 'Risk marker',
    return_12w: '12w price change',
    return_12m: '12m price change',
    drawdown_52w: '52w drawdown',
    trend_score: 'Trend score',
    surge_score: 'Surge score',
    rs_vs_spy: 'RS vs SPY',
    intraday: 'Intraday',
    short_interest: 'Short interest',
    options_pcr: 'Options PCR',
    analyst_score: 'Analyst score',
    data_coverage: 'Data coverage',
    coverage_state: 'Coverage state',
    sector: 'Sector',
    industry: 'Industry',
    company: 'Company',
    data_note: 'Data note',
    daily_points: '{count} daily points / {freshness}',
    no_chart: 'No chart data available.',
    close_range: 'Close {min} - {max}',
    why_selected: 'Why selected',
    positive_factors: 'Positive factors',
    risks: 'Risks',
    to: 'to'
  },
  ko: {
    ticker_analysis: '종목 분석',
    dashboard: '대시보드',
    five_year_chart: '최근 5년 가격과 거래량',
    current_status: '현재 상태',
    ai_summary: '설명 요약',
    industry_profile: '업종 및 종목 정보',
    selection_reason: '종목 선정 이유',
    expert_consensus: '전문가 검토 항목',
    required_review: '필수 검토 항목',
    score: '점수',
    review_state: '검토 상태',
    allocation_guide: '검토 비중 참고',
    risk_reference: '위험 기준',
    return_12w: '12주 가격 변화',
    return_12m: '12개월 가격 변화',
    drawdown_52w: '52주 낙폭',
    trend_score: '추세 점수',
    surge_score: '급등 점수',
    rs_vs_spy: 'SPY 대비 상대강도',
    intraday: '장중 시세',
    short_interest: '공매도 비율',
    options_pcr: '옵션 풋/콜 비율',
    analyst_score: '애널리스트 점수',
    data_coverage: '데이터 커버리지',
    coverage_state: '커버리지 상태',
    sector: '섹터',
    industry: '업종',
    company: '기업명',
    data_note: '데이터 안내',
    daily_points: '일봉 {count}개 / {freshness}',
    no_chart: '차트 데이터가 없습니다.',
    close_range: '종가 범위 {min} - {max}',
    why_selected: '선정 이유',
    positive_factors: '긍정 요인',
    risks: '위험 요인',
    to: '~'
  }
};

function t(key, values = {}) {
  const text = (DETAIL_I18N[detailState.lang] && DETAIL_I18N[detailState.lang][key]) || DETAIL_I18N.en[key] || key;
  return Object.entries(values).reduce((acc, [name, value]) => acc.replaceAll(`{${name}}`, value), text);
}

function applyTranslations() {
  document.documentElement.lang = detailState.lang;
  document.querySelectorAll('[data-i18n]').forEach((element) => {
    element.textContent = t(element.dataset.i18n);
  });
  document.querySelectorAll('[data-lang-option]').forEach((button) => {
    button.classList.toggle('active', button.dataset.langOption === detailState.lang);
    button.setAttribute('aria-pressed', String(button.dataset.langOption === detailState.lang));
  });
}

function setLanguage(lang) {
  detailState.lang = lang === 'ko' ? 'ko' : 'en';
  localStorage.setItem('vcb_lang', detailState.lang);
  applyTranslations();
  if (detailState.data) renderDetail(detailState.data);
}

function initLanguageToggle() {
  document.querySelectorAll('[data-lang-option]').forEach((button) => {
    button.addEventListener('click', () => setLanguage(button.dataset.langOption));
  });
  applyTranslations();
}

async function api(path) {
  const response = await fetch(path);
  const payload = await response.json();
  if (!payload.ok) throw new Error(payload.error?.message || payload.message || 'Request failed');
  return payload.data;
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

const DETAIL_KO_DYNAMIC = {
  archetypes: {
    A_AI_TECH: 'AI/기술 메가트렌드',
    B_CRYPTO_PIVOT: '가상자산 전환',
    C_QUANTUM: '양자/신흥 기술',
    D_BIOTECH: '바이오 촉매',
    E_SHORT_SQUEEZE: '숏 스퀴즈',
    F_PICK_SHOVEL: 'AI 인프라 수혜',
    G_TECHNICAL_MOMENTUM: '기술적 모멘텀'
  },
  publicLabels: {
    'High-priority review candidate': '우선 검토 후보',
    'High-priority research candidate': '우선 연구 후보',
    'Review candidate': '연구 후보',
    'Research candidate': '연구 후보',
    'Monitor only': '모니터링 후보',
    'Monitoring candidate': '모니터링 후보',
    'Needs review': '검토 필요',
    'High-scoring watchlist candidate': '고득점 연구 후보',
    'High-scoring research candidate': '고득점 연구 후보',
    'Watchlist candidate': '연구 후보',
    'No current setup': '현재 조건 미충족'
  },
  coverageLabels: {
    'multi-source': '다중 데이터',
    enriched: '보강 데이터',
    'price-volume-only': '가격/거래량 한정',
    insufficient: '부족',
    unknown: '알 수 없음'
  },
  sources: {
    sample: '샘플',
    'sample-placeholder': '샘플 대체값',
    yahoo: 'Yahoo',
    yahoo_chart: 'Yahoo 차트',
    stooq: 'Stooq',
    manual: '수동 CSV',
    finnhub: 'Finnhub',
    alpaca: 'Alpaca',
    'alpaca-intraday': 'Alpaca 장중',
    template: '템플릿 설명',
    'template-fallback': '템플릿 설명 대체',
    'template summary': '템플릿 설명',
    'template summary fallback': '템플릿 설명 대체',
    'OpenAI explanation summary': 'OpenAI 설명 요약',
    'deterministic-vcb-alt-v1': '결정론 점수 템플릿 v1',
    openai: 'OpenAI 설명',
    local: '로컬'
  },
  dataQuality: {
    offline: '오프라인',
    'eod-market': '일봉 시장 데이터',
    'partial-eod-market': '부분 일봉 시장 데이터',
    'thin-eod-market': '부족한 일봉 시장 데이터',
    'stale-eod-market': '오래된 일봉 시장 데이터'
  },
  consensusRoles: {
    Quant: '정량',
    Risk: '위험',
    Product: '제품'
  },
  consensusTitles: {
    'Score and trend state': '점수와 추세 상태',
    'Risk marker': '위험 참고',
    'Selection reason': '선정 이유'
  }
};

function isDetailKo() {
  return detailState.lang === 'ko';
}

function detailArchetypeLabel(item) {
  if (!isDetailKo()) return item.primary_archetype_label;
  return DETAIL_KO_DYNAMIC.archetypes[item.primary_archetype] || item.primary_archetype_label;
}

function detailPublicLabel(item) {
  const label = item.public_label || item.decision_label || item.status || 'Needs review';
  return isDetailKo() ? DETAIL_KO_DYNAMIC.publicLabels[label] || label : label;
}

function detailCoverageLabel(value) {
  return isDetailKo() ? DETAIL_KO_DYNAMIC.coverageLabels[value] || value || '-' : value || '-';
}

function detailSource(value) {
  if (!isDetailKo()) return value || '-';
  return String(value || '-')
    .split('+')
    .map((part) => DETAIL_KO_DYNAMIC.sources[part] || part)
    .join('+');
}

function detailDataQuality(value) {
  if (!isDetailKo()) return value || '-';
  return String(value || '-')
    .split('+')
    .map((part) => DETAIL_KO_DYNAMIC.dataQuality[part] || DETAIL_KO_DYNAMIC.sources[part] || part)
    .join('+');
}

function detailMissingList(value) {
  return String(value || '')
    .replaceAll('market price/volume', '시장 가격/거래량')
    .replaceAll('fundamentals/earnings', '재무/실적')
    .replaceAll('catalyst/news', '촉매/뉴스')
    .replaceAll('float/short/options/insider positioning', '유통주식/공매도/옵션/내부자 포지셔닝');
}

function detailText(value, item = {}) {
  const text = String(value || '');
  if (!isDetailKo() || !text) return text;
  let match = text.match(/^Primary archetype is (.+) with base score ([-0-9.]+)\.$/);
  if (match) return `주요 유형은 ${detailArchetypeLabel(item)}이며 기본 점수는 ${match[2]}점입니다.`;
  match = text.match(/^Complexity modifier is ([-0-9.]+); combined score is ([-0-9.]+)\.$/);
  if (match) return `복합 보정값은 ${match[1]}점이고 최종 점수는 ${match[2]}점입니다.`;
  match = text.match(/^Data quality: (.+)\.$/);
  if (match) return `데이터 품질: ${detailDataQuality(match[1])}.`;
  match = text.match(/^Trend template score: ([-0-9.]+)\/100\.$/);
  if (match) return `추세 점수는 100점 만점에 ${match[1]}점입니다.`;
  match = text.match(/^Surge score: ([-0-9.]+)\/100\.$/);
  if (match) return `급등 점수는 100점 만점에 ${match[1]}점입니다.`;
  match = text.match(/^Data coverage: ([-0-9.]+)\/100 \(([^)]+)\)\. (.+)$/);
  if (match) return `데이터 커버리지는 100점 만점에 ${match[1]}점(${detailCoverageLabel(match[2])})입니다. ${detailText(match[3], item)}`;
  match = text.match(/^Missing: (.+)\.$/);
  if (match) return `부족한 데이터: ${detailMissingList(match[1])}.`;
  match = text.match(/^Research enrichment applied from (.+) as of (.+)\.$/);
  if (match) return `리서치 보강 데이터가 ${detailSource(match[1])}에서 적용되었습니다. 기준 시점은 ${match[2]}입니다.`;
  match = text.match(/^Intraday quote layer: (.+) price (.+) as of (.+)\.$/);
  if (match) return `장중 시세 계층: ${detailSource(match[1])} 가격 ${match[2]}, 기준 시각 ${match[3]}.`;
  match = text.match(/^Composite score is above the internal review threshold\.$/);
  if (match) return '종합 점수가 내부 검토 기준을 넘었습니다.';
  match = text.match(/^12-week momentum is positive at (.+)%\.$/);
  if (match) return `12주 모멘텀이 +${match[1]}%로 양호합니다.`;
  match = text.match(/^Analyst\/revision score is positive at (.+)\.$/);
  if (match) return `애널리스트 추정치 수정 점수가 ${match[1]}점으로 양호합니다.`;
  match = text.match(/^Call open interest is greater than put open interest\.$/);
  if (match) return '콜 옵션 미결제약정이 풋 옵션보다 큽니다.';
  match = text.match(/^Short interest is elevated at (.+)%\.$/);
  if (match) return `공매도 비율이 ${match[1]}%로 높습니다.`;
  const exact = {
    'Score is above the MVP portfolio-manager threshold of 55.': '점수가 내부 연구 후보 기준 55점을 넘었습니다.',
    'Score passed the numeric threshold, but final selection is blocked until enrichment data is present.':
      '점수 기준은 통과했지만 보강 데이터가 없어 최종 선정은 보류됩니다.',
    'Score is below the MVP portfolio-manager threshold of 55; wait.': '점수가 내부 연구 후보 기준 55점보다 낮아 대기합니다.',
    'Decision support only; not a trading instruction.': '의사결정 보조 정보이며 매매 지시가 아닙니다.',
    'No automatic trading is performed.': '자동매매는 실행되지 않습니다.',
    'Result uses sample/offline data, not live market data.': '이 결과는 실시간 시장 데이터가 아니라 샘플/오프라인 데이터를 사용합니다.',
    'Required market, fundamental, catalyst, and positioning groups present.': '시장, 재무, 촉매, 포지셔닝 데이터 그룹이 모두 존재합니다.',
    'Data coverage is below the final-selection gate.': '데이터 커버리지가 최종 선정 기준보다 낮습니다.',
    'Current provider supplies end-of-day/delayed chart data, not tick-by-tick real-time data.':
      '현재 제공자는 틱 단위 실시간 데이터가 아니라 일봉/지연 차트 데이터를 제공합니다.',
    'No selection rationale is available for this ticker.': '이 종목의 선정 근거가 없습니다.'
  };
  return exact[text] || text;
}

function detailMissingList(value) {
  return String(value || '')
    .replaceAll('market price/volume', '시장 가격/거래량')
    .replaceAll('fundamentals/earnings', '재무/실적')
    .replaceAll('catalyst/news', '촉매/뉴스')
    .replaceAll('float/short/options/insider positioning', '유통주식/공매도/옵션/내부자 포지셔닝');
}

function tickerFromPath() {
  const parts = window.location.pathname.split('/').filter(Boolean);
  return decodeURIComponent(parts[1] || '').toUpperCase();
}

function showDetailNotice(message, error = false) {
  const box = document.getElementById('detail-notice');
  box.hidden = false;
  box.className = `notice${error ? ' error' : ''}`;
  box.textContent = message;
}

async function bootstrapDetail() {
  const ticker = tickerFromPath();
  try {
    const data = await api(`/api/ticker-analysis?ticker=${encodeURIComponent(ticker)}`);
    detailState.data = data;
    renderDetail(data);
  } catch (error) {
    showDetailNotice(error.message, true);
  }
}

function renderDetail(data) {
  const evaluation = data.evaluation;
  const profile = data.profile;
  const history = data.history;
  document.title = isDetailKo() ? `${data.ticker} 분석 - VCB-Alt` : `${data.ticker} Analysis - VCB-Alt`;
  document.getElementById('detail-symbol').textContent = `${data.ticker} ${profile.company_name}`;
  document.getElementById('detail-provider').textContent = `${detailSource(history.source)} / ${history.range}`;
  document.getElementById('chart-meta').textContent =
    t('daily_points', { count: history.points.length, freshness: detailDataQuality(history.freshness) });
  document.getElementById('review-state').textContent = detailPublicLabel(evaluation);
  document.getElementById('score-version').textContent = evaluation.scoring_version;
  document.getElementById('profile-source').textContent = profile.profile_source;
  renderChart(history.points);
  renderStatusGrid(evaluation, data.metrics || {});
  renderAiSummary(data.ai_summary || {});
  renderProfile(profile, history);
  renderRationale(evaluation);
  renderConsensus(data.expert_consensus);
}

function renderStatusGrid(item, metrics) {
  document.getElementById('status-grid').innerHTML = `
    <div class="metric-box"><span>${t('score')}</span><strong>${item.combined_score}</strong></div>
    <div class="metric-box"><span>${t('review_state')}</span><strong>${escapeHtml(detailPublicLabel(item))}</strong></div>
    <div class="metric-box"><span>${t('allocation_guide')}</span><strong>${item.suggested_size_pct}%</strong></div>
    <div class="metric-box"><span>${t('risk_reference')}</span><strong>${item.stop_loss}</strong></div>
    <div class="metric-box"><span>${t('return_12w')}</span><strong>${metric(metrics, 'return_12w_pct')}%</strong></div>
    <div class="metric-box"><span>${t('return_12m')}</span><strong>${metric(metrics, 'return_12m_pct')}%</strong></div>
    <div class="metric-box"><span>${t('drawdown_52w')}</span><strong>${metric(metrics, 'drawdown_52w_pct')}%</strong></div>
    <div class="metric-box"><span>${t('trend_score')}</span><strong>${metric(metrics, 'trend_template_score')}</strong></div>
    <div class="metric-box"><span>${t('surge_score')}</span><strong>${metric(metrics, 'surge_score')}</strong></div>
    <div class="metric-box"><span>${t('rs_vs_spy')}</span><strong>${metric(metrics, 'relative_strength_12w_pp')}pp</strong></div>
    <div class="metric-box"><span>${t('intraday')}</span><strong>${metric(metrics, 'intraday_price')}</strong></div>
    <div class="metric-box"><span>${t('short_interest')}</span><strong>${metric(metrics, 'short_interest_pct')}%</strong></div>
    <div class="metric-box"><span>${t('options_pcr')}</span><strong>${metric(metrics, 'put_call_ratio')}</strong></div>
    <div class="metric-box"><span>${t('analyst_score')}</span><strong>${metric(metrics, 'analyst_revision_score')}</strong></div>
    <div class="metric-box"><span>${t('data_coverage')}</span><strong>${item.data_coverage_score}/100</strong></div>
    <div class="metric-box">
      <span>${t('coverage_state')}</span><strong>${escapeHtml(detailCoverageLabel(item.data_coverage_label))}</strong>
    </div>
  `;
}

function metric(values, key) {
  return values[key] ?? '-';
}

function renderProfile(profile, history) {
  const metrics = detailState.data?.metrics || {};
  const intradayError = metrics.intraday_error
    ? `<p><strong>${t('intraday')}:</strong> ${escapeHtml(detailText(metrics.intraday_error))}</p>`
    : '';
  document.getElementById('profile-body').innerHTML = `
    <p><strong>${t('sector')}:</strong> ${escapeHtml(profile.sector)}</p>
    <p><strong>${t('industry')}:</strong> ${escapeHtml(profile.industry)}</p>
    <p><strong>${t('company')}:</strong> ${escapeHtml(profile.company_name)}</p>
    <p><strong>${t('data_note')}:</strong> ${escapeHtml(detailText(history.realtime_note))}</p>
    ${intradayError}
  `;
}

function detailSummaryProvider(summary) {
  const provider = summary.provider_label
    || (summary.provider === 'openai' ? 'OpenAI explanation summary'
      : summary.provider === 'template-fallback' ? 'template summary fallback'
        : 'template summary');
  const model = summary.model || (summary.provider === 'openai' ? 'OpenAI' : 'deterministic-vcb-alt-v1');
  return `${detailSource(provider)} / ${detailSource(model)}`;
}

function renderAiSummary(summary) {
  const data = detailState.data || {};
  const evaluation = data.evaluation || {};
  const profile = data.profile || {};
  document.getElementById('ai-provider').textContent = detailSummaryProvider(summary);
  const why = Array.isArray(summary.why_selected) ? summary.why_selected : [];
  const positives = Array.isArray(summary.positive_factors) ? summary.positive_factors : [];
  const risks = Array.isArray(summary.risk_flags) ? summary.risk_flags : [];
  const method = summary.selection_method
    || 'Deterministic scoring and portfolio constraints select research candidates; the summary layer only explains the scoring result.';
  const headline = isDetailKo()
    ? `${data.ticker || ''}는 ${detailPublicLabel(evaluation)} 상태입니다.`
    : (summary.headline || '');
  const body = isDetailKo()
    ? `${detailArchetypeLabel(evaluation)} 유형이며 종합 점수는 ${evaluation.combined_score ?? '-'}점입니다. `
      + `업종은 ${profile.sector || '-'} / ${profile.industry || '-'}입니다.`
    : (summary.summary || '');
  document.getElementById('ai-summary-body').innerHTML = `
    <p class="muted">${escapeHtml(detailText(method, evaluation))}</p>
    <p><strong>${escapeHtml(headline)}</strong></p>
    <p>${escapeHtml(body)}</p>
    <h3>${t('why_selected')}</h3>
    <ul>${why.map((item) => `<li>${escapeHtml(detailText(item, evaluation))}</li>`).join('')}</ul>
    <h3>${t('positive_factors')}</h3>
    <ul>${positives.map((item) => `<li>${escapeHtml(detailText(item, evaluation))}</li>`).join('')}</ul>
    <h3>${t('risks')}</h3>
    <ul>${risks.map((item) => `<li>${escapeHtml(detailText(item, evaluation))}</li>`).join('')}</ul>
  `;
}

function renderRationale(item) {
  const reasons = [...(item.rationale || []), ...(item.precision_notes || []), ...(item.warnings || [])];
  document.getElementById('rationale-body').innerHTML =
    `<ul>${reasons.map((reason) => `<li>${escapeHtml(detailText(reason, item))}</li>`).join('')}</ul>`;
}

function renderConsensus(items) {
  document.getElementById('consensus-body').innerHTML = items.map((item) => `
    <p>
      <strong>${escapeHtml(consensusRole(item.role))} - ${escapeHtml(consensusTitle(item.title))}:</strong>
      ${escapeHtml(consensusBody(item))}
    </p>
  `).join('');
}

function consensusRole(value) {
  return isDetailKo() ? DETAIL_KO_DYNAMIC.consensusRoles[value] || value : value;
}

function consensusTitle(value) {
  return isDetailKo() ? DETAIL_KO_DYNAMIC.consensusTitles[value] || value : value;
}

function consensusBody(item) {
  if (!isDetailKo()) return item.body;
  if (item.role === 'Quant') {
    return `종합 점수는 ${detailState.data.evaluation.combined_score}점이며 `
      + `${detailState.data.evaluation.scoring_version} 기준입니다. 실행 전 추세와 급등 지표를 함께 검토하세요.`;
  }
  if (item.role === 'Risk') {
    return '위험 기준과 배분 가이드는 매매 지시가 아니라 검토 입력값으로 사용하세요.';
  }
  if (item.role === 'Product') {
    return '첫 번째 근거 항목들이 이 종목이 검토 목록에 오른 주요 이유를 설명합니다.';
  }
  return item.body;
}

function renderChart(points) {
  const svg = document.getElementById('price-chart');
  if (!points.length) {
    svg.innerHTML = `<text x="20" y="40" fill="#a4ada9">${t('no_chart')}</text>`;
    return;
  }
  const width = 900;
  const height = 420;
  const pad = 42;
  const closes = points.map((point) => point.close);
  const volumes = points.map((point) => point.volume);
  const minClose = Math.min(...closes);
  const maxClose = Math.max(...closes);
  const maxVolume = Math.max(...volumes);
  const x = (index) => pad + (index / Math.max(1, points.length - 1)) * (width - pad * 2);
  const yPrice = (value) => height - pad - ((value - minClose) / Math.max(1, maxClose - minClose)) * (height - pad * 2);
  const yVolume = (value) => height - pad - (value / Math.max(1, maxVolume)) * 88;
  const line = points.map((point, index) => `${x(index)},${yPrice(point.close)}`).join(' ');
  const bars = points.filter((_, index) => index % Math.ceil(points.length / 120) === 0).map((point, index) => {
    const actualIndex = index * Math.ceil(points.length / 120);
    const barX = x(actualIndex);
    return `<line x1="${barX}" y1="${height - pad}" x2="${barX}" y2="${yVolume(point.volume)}" stroke="#2f5748" stroke-width="2" />`;
  }).join('');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.innerHTML = `
    <rect x="0" y="0" width="${width}" height="${height}" fill="#0c0f0e" rx="8"></rect>
    <line x1="${pad}" y1="${height - pad}" x2="${width - pad}" y2="${height - pad}" stroke="#2b3430"></line>
    <line x1="${pad}" y1="${pad}" x2="${pad}" y2="${height - pad}" stroke="#2b3430"></line>
    ${bars}
    <polyline points="${line}" fill="none" stroke="#82d6b4" stroke-width="3"></polyline>
    <text x="${pad}" y="24" fill="#e6e8e6" font-size="14">${t('close_range', { min: minClose.toFixed(2), max: maxClose.toFixed(2) })}</text>
    <text x="${width - pad - 180}" y="${height - 14}" fill="#a4ada9" font-size="12">
      ${escapeHtml(points[0].date)} ${t('to')} ${escapeHtml(points[points.length - 1].date)}
    </text>
  `;
}

initLanguageToggle();
bootstrapDetail();
