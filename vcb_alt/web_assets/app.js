
const state = {
  scan: [],
  selection: null,
  failures: [],
  config: null,
  providerStatus: null,
  sessionToken: localStorage.getItem('vcb_session_token') || '',
  sessionUser: null,
  lang: localStorage.getItem('vcb_lang') || 'en'
};

const I18N = {
  en: {
    access_required: 'Access required',
    access_help: 'Enter the deployment access token configured by the operator.',
    access_token: 'Access token',
    open_dashboard: 'Open dashboard',
    dashboard_title: 'Market-wide stock discovery',
    data_not_loaded: 'Data as of: not loaded',
    provider_not_loaded: 'Provider: not loaded',
    ops_checking: 'Operational status: checking',
    discovery_primary_label: 'Market-wide discovery',
    discovery_primary_title: 'Find the latest research candidates across the market',
    discovery_primary_help: 'The worker-owned market scan reads the latest fresh snapshot or queues one durable scan job.',
    scan_freshness: 'Scan freshness',
    provider_source: 'Provider source',
    data_coverage: 'Data coverage',
    fail_closed: 'Fail-closed state',
    no_snapshot_yet: 'No snapshot yet',
    queued_snapshot: 'Snapshot queued',
    fresh_snapshot: 'Fresh snapshot',
    stale_snapshot: 'Refresh needed',
    coverage_pending: 'Pending',
    fail_closed_active: 'Live data required',
    rationale_visible: 'Candidate rationale visible',
    add_tickers: 'Add research tickers',
    add: 'Add',
    run_scan: 'Scan full market / latest candidates',
    select_final: 'Rebuild selected set',
    refresh: 'Refresh status',
    watchlist: 'Optional manual research',
    watchlist_drawer_label: 'Secondary drawer',
    watchlist_help: 'Manual watchlist notes are separate from the market-wide discovery result '
      + 'and never seed candidate output automatically.',
    starter_research: 'Add optional starter research list',
    optional_research: 'Optional research list',
    operations: 'Operations',
    decision_first: 'Market-wide candidate review',
    entry_candidates: 'Latest research candidates',
    final_selection: 'Selected research set',
    run_selection_empty: 'Scan the market to see the latest selected research set.',
    actionable_setups: 'Research candidates',
    ticker: 'Ticker',
    archetype: 'Archetype',
    score: 'Score',
    status: 'Status',
    allocation: 'Allocation',
    data: 'Data',
    reason: 'Reason',
    run_scan_empty: 'Scan the market to populate candidates.',
    monitor_excluded: 'Monitor or excluded',
    lower_confidence_empty: 'Lower-confidence market names appear here after scanning.',
    legal_notice: 'Decision support only. No automatic trading.',
    risk_disclosure: 'Risk disclosure',
    privacy: 'Privacy',
    terms: 'Terms',
    ready: 'ready',
    running: 'running',
    waiting: 'waiting for worker',
    scan_queued: 'Scan queued. A background worker is preparing the market snapshot.',
    scan_waiting: 'Preparing the market snapshot ({attempt}/{total}). This usually takes under a minute.',
    scan_ready_after_wait: 'Market snapshot ready. Showing the latest candidates.',
    scan_still_running: 'The snapshot is still being prepared. Leave this page open or press Refresh status in a moment.',
    scan_job_failed: 'The market scan could not finish: {reason}',
    scan_provider_blocked: 'Live market data provider rejected our credentials, so no candidates can be shown. An operator needs to update the provider keys.',
    provider_blocked_badge: 'fail-closed: provider auth failed',
    not_run: 'Not run',
    failures: 'failures',
    selection_completed: 'Selection completed in {ms} ms.',
    no_eligible: 'No eligible candidates. Check live data coverage or run again after data refresh.',
    allocation_guide: 'Research size reference',
    no_excluded: 'No excluded names.',
    no_actionable: 'No actionable setups.',
    provider: 'Provider',
    data_as_of: 'Data as of',
    ops_success: 'Operational status: success',
    ops_provider_issues: 'Operational status: {count} provider issue(s)'
  },
  ko: {
    access_required: '접근 권한 필요',
    access_help: '운영자가 설정한 배포 접근 토큰을 입력하세요.',
    access_token: '접근 토큰',
    open_dashboard: '대시보드 열기',
    dashboard_title: '시장 전체 종목 탐색',
    data_not_loaded: '데이터 기준: 아직 불러오지 않음',
    provider_not_loaded: '제공자: 아직 불러오지 않음',
    ops_checking: '운영 상태: 확인 중',
    discovery_primary_label: '시장 전체 탐색',
    discovery_primary_title: '시장 전체에서 최신 연구 후보 확인',
    discovery_primary_help: '최신 worker 스냅샷을 즉시 읽고, 없으면 하나의 durable 시장 스캔 작업만 대기열에 넣습니다.',
    scan_freshness: '스캔 신선도',
    provider_source: '데이터 제공자',
    data_coverage: '데이터 커버리지',
    fail_closed: 'Fail-closed 상태',
    no_snapshot_yet: '아직 스냅샷 없음',
    queued_snapshot: '스냅샷 생성 대기 중',
    fresh_snapshot: '최신 스냅샷 사용 중',
    stale_snapshot: '스냅샷 갱신 필요',
    coverage_pending: '대기 중',
    fail_closed_active: '실데이터 없으면 후보 미노출',
    rationale_visible: '후보별 선정 근거 표시',
    add_tickers: '연구용 티커 추가',
    add: '추가',
    run_scan: '시장 전체 스캔/최신 후보 확인',
    select_final: '후보 세트 다시 계산',
    refresh: '상태 새로고침',
    watchlist: '보조 수동 연구',
    watchlist_drawer_label: '보조 패널',
    watchlist_help: '수동 목록은 시장 전체 탐색 결과와 별개입니다. 후보 결과로 자동 시딩되지 않습니다.',
    starter_research: '선택적 시작 연구 목록 추가',
    optional_research: '보조 연구 목록',
    operations: '운영 상태',
    decision_first: '시장 전체 후보 검토',
    entry_candidates: '최신 연구 후보',
    final_selection: '선정 연구 세트',
    run_selection_empty: '시장 전체 스캔을 실행하면 최신 선정 연구 세트가 표시됩니다.',
    actionable_setups: '연구 후보',
    ticker: '티커',
    archetype: '유형',
    score: '점수',
    status: '상태',
    allocation: '검토 비중',
    data: '데이터',
    reason: '이유',
    run_scan_empty: '시장 전체 스캔을 실행하면 후보가 표시됩니다.',
    monitor_excluded: '모니터링 또는 제외',
    lower_confidence_empty: '스캔 후 낮은 신뢰도의 시장 종목이 여기에 표시됩니다.',
    legal_notice: '의사결정 보조 정보입니다. 자동매매를 실행하지 않습니다.',
    risk_disclosure: '위험 고지',
    privacy: '개인정보',
    terms: '약관',
    ready: '준비됨',
    running: '실행 중',
    waiting: '작업 대기 중',
    scan_queued: '스캔을 대기열에 등록했습니다. 백그라운드 작업이 시장 스냅샷을 준비하고 있습니다.',
    scan_waiting: '시장 스냅샷을 준비하는 중입니다 ({attempt}/{total}). 보통 1분 이내에 끝납니다.',
    scan_ready_after_wait: '시장 스냅샷이 준비되었습니다. 최신 후보를 표시합니다.',
    scan_still_running: '스냅샷이 아직 준비 중입니다. 이 페이지를 열어 두거나 잠시 후 상태 새로고침을 눌러 주세요.',
    scan_job_failed: '시장 스캔을 마치지 못했습니다: {reason}',
    scan_provider_blocked: '실시간 시장 데이터 제공자가 인증을 거부해 후보를 표시할 수 없습니다. 운영자가 제공자 키를 갱신해야 합니다.',
    provider_blocked_badge: 'fail-closed: 제공자 인증 실패',
    not_run: '미실행',
    failures: '실패',
    selection_completed: '후보 계산이 {ms} ms 안에 완료되었습니다.',
    no_eligible: '조건을 충족하는 후보가 없습니다. 데이터 커버리지를 확인하거나 갱신 후 다시 실행하세요.',
    allocation_guide: '검토 비중 참고',
    no_excluded: '제외된 종목이 없습니다.',
    no_actionable: '연구 후보가 없습니다.',
    provider: '제공자',
    data_as_of: '데이터 기준',
    ops_success: '운영 상태: 정상',
    ops_provider_issues: '운영 상태: 제공자 이슈 {count}건'
  }
};

function t(key, values = {}) {
  const text = (I18N[state.lang] && I18N[state.lang][key]) || I18N.en[key] || key;
  return Object.entries(values).reduce((acc, [name, value]) => acc.replaceAll(`{${name}}`, value), text);
}

function applyTranslations() {
  document.documentElement.lang = state.lang;
  document.querySelectorAll('[data-i18n]').forEach((element) => {
    element.textContent = t(element.dataset.i18n);
  });
  document.querySelectorAll('[data-lang-option]').forEach((button) => {
    button.classList.toggle('active', button.dataset.langOption === state.lang);
    button.setAttribute('aria-pressed', String(button.dataset.langOption === state.lang));
  });
  document.getElementById('runtime').textContent = t('ready');
}

function setLanguage(lang) {
  state.lang = lang === 'ko' ? 'ko' : 'en';
  localStorage.setItem('vcb_lang', state.lang);
  applyTranslations();
  if (state.config && state.providerStatus) {
    const mode = state.providerStatus.capabilities?.mode || state.providerStatus.scan_mode || 'unknown';
    document.getElementById('provider').textContent = isKo()
      ? `${translateSource(state.providerStatus.provider)} 데이터`
      : `${state.providerStatus.provider} data`;
    document.getElementById('data-source').textContent =
      `${t('provider')}: ${translateSource(state.providerStatus.provider)} / ${translateMode(mode)}`;
    document.getElementById('provider-source').textContent =
      `${translateSource(state.providerStatus.provider)} / ${translateMode(mode)}`;
  }
  if (state.selection) renderSelection(state.selection, state.selection.elapsed_ms || 0);
  if (state.scan.length) renderScan(state.scan);
  updateDataStatus([...(state.scan || []), ...((state.selection && state.selection.selected) || [])], state.failures || []);
  updateDiscoverySummary({ items: state.scan, selection: state.selection, failures: state.failures });
  if (state.config) {
    loadWatchlist().catch(() => {});
    loadOps().catch(() => {});
  }
}

function initLanguageToggle() {
  document.querySelectorAll('[data-lang-option]').forEach((button) => {
    button.addEventListener('click', () => setLanguage(button.dataset.langOption));
  });
  applyTranslations();
}

async function api(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (state.sessionToken) headers.Authorization = `Bearer ${state.sessionToken}`;
  const response = await fetch(path, {
    ...options,
    headers
  });
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

const KO_DYNAMIC = {
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
  modes: {
    offline: '오프라인',
    operator_csv: '운영자 CSV',
    eod_market_data: '일봉 시장 데이터',
    market_universe: '시장 전체 탐색',
    unknown: '알 수 없음'
  },
  dataQuality: {
    offline: '오프라인',
    'eod-market': '일봉 시장 데이터',
    'partial-eod-market': '부분 일봉 시장 데이터',
    'thin-eod-market': '부족한 일봉 시장 데이터',
    'stale-eod-market': '오래된 일봉 시장 데이터'
  },
  rejectionReasons: {
    'Score below entry threshold.': '점수가 연구 후보 기준보다 낮습니다.',
    'Monitor only.': '모니터링 후보입니다.',
    'Portfolio slot limit reached.': '선정 후보 수 한도에 도달했습니다.',
    'Duplicate primary archetype avoided.': '동일한 주요 유형의 중복 선정을 피했습니다.',
    'High-volatility archetype limit reached.': '고변동성 유형 한도에 도달했습니다.',
    'Total suggested exposure limit reached.': '총 검토 비중 한도에 도달했습니다.'
  }
};

function isKo() {
  return state.lang === 'ko';
}

function translateSource(value) {
  if (!isKo()) return value || '-';
  return String(value || '-')
    .split('+')
    .map((part) => KO_DYNAMIC.sources[part] || part)
    .join('+');
}

function translateMode(value) {
  if (!isKo()) return value || 'unknown';
  return KO_DYNAMIC.modes[value] || value || KO_DYNAMIC.modes.unknown;
}

function translateDataQuality(value) {
  if (!isKo()) return value || '-';
  return String(value || '-')
    .split('+')
    .map((part) => KO_DYNAMIC.dataQuality[part] || KO_DYNAMIC.sources[part] || part)
    .join('+');
}

function archetypeLabel(item) {
  if (!isKo()) return item.primary_archetype_label;
  return KO_DYNAMIC.archetypes[item.primary_archetype] || item.primary_archetype_label;
}

function publicLabel(item) {
  const label = item.public_label || item.decision_label || item.status || 'Needs review';
  return isKo() ? KO_DYNAMIC.publicLabels[label] || label : label;
}

function coverageLabel(value) {
  return isKo() ? KO_DYNAMIC.coverageLabels[value] || value || '-' : value || '-';
}

function translateMissingList(value) {
  return String(value || '')
    .replaceAll('market price/volume', '시장 가격/거래량')
    .replaceAll('fundamentals/earnings', '재무/실적')
    .replaceAll('catalyst/news', '촉매/뉴스')
    .replaceAll('float/short/options/insider positioning', '유통주식/공매도/옵션/내부자 포지셔닝');
}

function translateText(value, item = {}) {
  const text = String(value || '');
  if (!isKo() || !text) return text;
  let match = text.match(/^Primary archetype is (.+) with base score ([-0-9.]+)\.$/);
  if (match) return `주요 유형은 ${archetypeLabel(item)}이며 기본 점수는 ${match[2]}점입니다.`;
  match = text.match(/^Complexity modifier is ([-0-9.]+); combined score is ([-0-9.]+)\.$/);
  if (match) return `복합 보정값은 ${match[1]}점이고 최종 점수는 ${match[2]}점입니다.`;
  match = text.match(/^Data quality: (.+)\.$/);
  if (match) return `데이터 품질: ${translateDataQuality(match[1])}.`;
  match = text.match(/^Trend template score: ([-0-9.]+)\/100\.$/);
  if (match) return `추세 점수는 100점 만점에 ${match[1]}점입니다.`;
  match = text.match(/^Surge score: ([-0-9.]+)\/100\.$/);
  if (match) return `급등 점수는 100점 만점에 ${match[1]}점입니다.`;
  match = text.match(/^Data coverage: ([-0-9.]+)\/100 \(([^)]+)\)\. (.+)$/);
  if (match) return `데이터 커버리지는 100점 만점에 ${match[1]}점(${coverageLabel(match[2])})입니다. ${translateText(match[3], item)}`;
  match = text.match(/^Missing: (.+)\.$/);
  if (match) return `부족한 데이터: ${translateMissingList(match[1])}.`;
  match = text.match(/^Research enrichment applied from (.+) as of (.+)\.$/);
  if (match) return `리서치 보강 데이터가 ${translateSource(match[1])}에서 적용되었습니다. 기준 시점은 ${match[2]}입니다.`;
  match = text.match(/^Intraday quote layer: (.+) price (.+) as of (.+)\.$/);
  if (match) return `장중 시세 계층: ${translateSource(match[1])} 가격 ${match[2]}, 기준 시각 ${match[3]}.`;
  match = text.match(/^(.+) score is ([-0-9.]+)\.$/);
  if (match) return `${archetypeLabel(item)} 점수는 ${match[2]}점입니다.`;
  match = text.match(/^Allocation guide is ([-0-9.]+)%\.$/);
  if (match) return `검토 비중 가이드는 ${match[1]}%입니다.`;
  const exact = {
    'Score is above the MVP portfolio-manager threshold of 55.': '점수가 내부 연구 후보 기준 55점을 넘었습니다.',
    'Score passed the numeric threshold, but final selection is blocked until enrichment data is present.':
      '점수 기준은 통과했지만 보강 데이터가 없어 최종 선정은 보류됩니다.',
    'Score is below the MVP portfolio-manager threshold of 55; wait.': '점수가 내부 연구 후보 기준 55점보다 낮아 대기합니다.',
    'Decision support only; not a trading instruction.': '의사결정 보조 정보이며 매매 지시가 아닙니다.',
    'No automatic trading is performed.': '자동매매는 실행되지 않습니다.',
    'Result uses sample/offline data, not live market data.': '이 결과는 실시간 시장 데이터가 아니라 샘플/오프라인 데이터를 사용합니다.',
    'Required market, fundamental, catalyst, and positioning groups present.': '시장, 재무, 촉매, 포지셔닝 데이터 그룹이 모두 존재합니다.',
    'Entry threshold is met.': '연구 후보 기준을 충족했습니다.',
    'Entry threshold is not met.': '연구 후보 기준을 충족하지 못했습니다.',
    'Data coverage is below the final-selection gate.': '데이터 커버리지가 최종 선정 기준보다 낮습니다.',
    'Current provider supplies end-of-day/delayed chart data, not tick-by-tick real-time data.':
      '현재 제공자는 틱 단위 실시간 데이터가 아니라 일봉/지연 차트 데이터를 제공합니다.',
    ...KO_DYNAMIC.rejectionReasons
  };
  return exact[text] || text;
}

function translateMissingList(value) {
  return String(value || '')
    .replaceAll('market price/volume', '시장 가격/거래량')
    .replaceAll('fundamentals/earnings', '재무/실적')
    .replaceAll('catalyst/news', '촉매/뉴스')
    .replaceAll('float/short/options/insider positioning', '유통주식/공매도/옵션/내부자 포지셔닝');
}

function translateReadinessDecision(value) {
  if (!isKo()) return value || '';
  const labels = {
    READY_FOR_PRIVATE_BETA: '제한적 내부 베타 가능',
    NOT_READY: '출시 불가',
    NOT_READY_FOR_1000_USER_SAAS: '1000명 SaaS 공개 전 보완 필요'
  };
  return labels[value] || value || '';
}

function showNotice(message, error = false) {
  const box = document.getElementById('notice');
  box.hidden = false;
  box.className = `notice${error ? ' error' : ''}`;
  box.textContent = message;
}

function setBusy(busy) {
  document.querySelectorAll('button').forEach((button) => { button.disabled = busy; });
  document.getElementById('runtime').textContent = busy ? t('running') : t('ready');
}

function endpoint(legacyPath, tenantPath) {
  return state.config && state.config.user_auth_enabled ? tenantPath : legacyPath;
}

function starterTickers() {
  return 'PLTR MSTR VST AAPL GME RGTI SMMT';
}

function randomId() {
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID().replaceAll('-', '');
  return `${Date.now()}${Math.random().toString(16).slice(2)}`;
}

function storeGeneratedCredentials() {
  const id = randomId();
  const email = `browser-${id}@example.invalid`;
  const password = `Browser-${id}-password`;
  localStorage.setItem('vcb_user_email', email);
  localStorage.setItem('vcb_user_password', password);
  return { email, password };
}

async function ensureUserSession() {
  if (!state.config || !state.config.user_auth_enabled) return;
  if (state.sessionToken) {
    try {
      state.sessionUser = await api('/api/me');
      return;
    } catch (error) {
      localStorage.removeItem('vcb_session_token');
      state.sessionToken = '';
    }
  }
  let email = localStorage.getItem('vcb_user_email');
  let password = localStorage.getItem('vcb_user_password');
  if (!email || !password) {
    ({ email, password } = storeGeneratedCredentials());
  }
  // Public demo browsers get an isolated tenant automatically so the scan button never
  // falls back to blocked legacy global APIs when SaaS auth is enabled.
  try {
    const registered = await api('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, tenant_name: 'Browser workspace' })
    });
    state.sessionToken = registered.session_token;
    state.sessionUser = registered.user;
  } catch (error) {
    try {
      const loggedIn = await api('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password })
      });
      state.sessionToken = loggedIn.session_token;
      state.sessionUser = loggedIn.user;
    } catch (loginError) {
      ({ email, password } = storeGeneratedCredentials());
      const registered = await api('/api/auth/register', {
        method: 'POST',
        body: JSON.stringify({ email, password, tenant_name: 'Browser workspace' })
      });
      state.sessionToken = registered.session_token;
      state.sessionUser = registered.user;
    }
  }
  localStorage.setItem('vcb_session_token', state.sessionToken);
}

async function ensureStarterWatchlist() {
  return;
}

async function seedStarterResearchList() {
  setBusy(true);
  try {
    const data = await api(endpoint('/api/watchlist', '/api/user/watchlist'), {
      method: 'POST',
      body: JSON.stringify({ tickers: starterTickers(), source: 'optional_onboarding_helper' })
    });
    showNotice(state.lang === 'ko'
      ? `보조 연구 목록에 추가됨: ${data.added.join(', ') || '없음'}; 기존: ${data.existing.join(', ') || '없음'}`
      : `Starter research list added: ${data.added.join(', ') || 'none'}; existing: ${data.existing.join(', ') || 'none'}`);
    await loadWatchlist();
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    setBusy(false);
  }
}

async function loadConfig() {
  const [config, providerStatus] = await Promise.all([
    api('/api/config'),
    api('/api/provider-status')
  ]);
  state.config = config;
  state.providerStatus = providerStatus;
  const mode = providerStatus.capabilities?.mode || providerStatus.scan_mode || 'unknown';
  document.getElementById('provider').textContent = isKo()
    ? `${translateSource(providerStatus.provider)} 데이터`
    : `${providerStatus.provider} data`;
  document.getElementById('data-source').textContent =
    `${t('provider')}: ${translateSource(providerStatus.provider)} / ${translateMode(mode)}`;
  document.getElementById('provider-source').textContent =
    `${translateSource(providerStatus.provider)} / ${translateMode(mode)}`;
  document.getElementById('coverage-state').textContent = t('coverage_pending');
  document.getElementById('fail-closed-state').textContent =
    config.market_scan_requires_live_data ? t('fail_closed_active') : (isKo() ? '로컬/데모 대체 데이터 허용' : 'Local/demo fallback allowed');
  document.getElementById('ops-state').textContent = config.external_api_enabled
    ? (isKo() ? '운영 상태: 외부 데이터 활성화' : 'Operational status: external data enabled')
    : (isKo() ? '운영 상태: 오프라인/샘플 모드' : 'Operational status: offline/sample mode');
}

async function loadWatchlist() {
  const data = await api(endpoint('/api/watchlist', '/api/user/watchlist'));
  const metadata = data.metadata || {};
  const starterButton = document.getElementById('starter-research-button');
  if (starterButton) starterButton.hidden = metadata.starter_helper_available === false;
  document.getElementById('watchlist-count').textContent = state.lang === 'ko'
    ? `${data.count}개 보조`
    : `${data.count} optional`;
  const target = document.getElementById('watchlist');
  if (!data.items.length) {
    const boundary = metadata.result_boundary
      ? `<div class="empty-state">${escapeHtml(metadata.result_boundary)}</div>`
      : '';
    target.innerHTML = boundary + `<div class="empty-state">${state.lang === 'ko'
      ? '보조 연구가 필요할 때만 티커를 추가하세요.'
      : 'Add tickers only when you need secondary manual research.'}</div>`;
    return;
  }
  const helper = metadata.market_wide_discovery_primary
    ? `<div class="empty-state">${state.lang === 'ko'
        ? '아래 목록은 시장 전체 추천 결과가 아니라 보조 연구 목록입니다.'
        : 'This list is secondary research, not the market-wide discovery result.'}</div>`
    : '';
  target.innerHTML = helper + data.items.map((item) => `
    <div class="ticker-row">
      <strong>${escapeHtml(item.ticker)}</strong>
      <button type="button" data-remove="${escapeHtml(item.ticker)}">${state.lang === 'ko' ? '삭제' : 'Remove'}</button>
    </div>
  `).join('');
  target.querySelectorAll('[data-remove]').forEach((button) => {
    button.addEventListener('click', () => removeTicker(button.dataset.remove));
  });
}

async function loadOps() {
  const [readiness, failures] = await Promise.all([
    api('/api/saas-readiness'),
    api('/api/failures')
  ]);
  state.failures = failures.items || [];
  document.getElementById('failure-count').textContent = `${failures.count} ${t('failures')}`;
  const opsState = document.getElementById('ops-state');
  opsState.className = `status-dot ${failures.count ? 'warn' : 'good'}`;
  opsState.textContent = failures.count
    ? (state.lang === 'ko' ? '운영 상태: 실패 감지' : 'Operational status: failures detected')
    : t('ops_success');
  document.getElementById('readiness').innerHTML = `
    <strong>${escapeHtml(translateReadinessDecision(readiness.decision))}</strong><br>
    ${state.lang === 'ko'
      ? '운영자 시험 사용은 가능합니다. 공개 SaaS 출시는 인증 강화, 내구성 있는 운영, 부하 테스트, 법무 검토가 필요합니다.'
      : 'Owner/operator trial is available. Public SaaS launch still requires auth hardening, '
        + 'durable operations, load testing, and legal review.'}
  `;
  const target = document.getElementById('failures');
  target.innerHTML = failures.items.length
    ? failures.items.map((item) => `<div>${escapeHtml(item.created_at)}: ${escapeHtml(item.message)}</div>`).join('')
    : `<div>${state.lang === 'ko' ? '최근 실패가 없습니다.' : 'No recent failures.'}</div>`;
}

async function addTickers(event) {
  event.preventDefault();
  const input = document.getElementById('ticker-input');
  const tickers = input.value.trim();
  if (!tickers) return;
  setBusy(true);
  try {
    const data = await api(endpoint('/api/watchlist', '/api/user/watchlist'), { method: 'POST', body: JSON.stringify({ tickers }) });
    input.value = '';
    showNotice(state.lang === 'ko'
      ? `추가됨: ${data.added.join(', ') || '없음'}; 기존: ${data.existing.join(', ') || '없음'}`
      : `Added: ${data.added.join(', ') || 'none'}; existing: ${data.existing.join(', ') || 'none'}`);
    await loadWatchlist();
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    setBusy(false);
  }
}

async function removeTicker(ticker) {
  setBusy(true);
  try {
    await api(`${endpoint('/api/watchlist', '/api/user/watchlist')}?ticker=${encodeURIComponent(ticker)}`, { method: 'DELETE' });
    showNotice(state.lang === 'ko' ? `${ticker} 삭제됨` : `${ticker} removed.`);
    await loadWatchlist();
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    setBusy(false);
  }
}

// In production the scan is owned by a background worker: the API answers 202 with a
// queued/pending job instead of a report. Without polling the dashboard would sit on
// "status: queued" and look broken, so wait for the worker and render the result.
const SCAN_POLL_INTERVAL_MS = 5000;
const SCAN_POLL_ATTEMPTS = 12;
let scanPollToken = 0;

function isQueuedScanOutcome(data) {
  return !Array.isArray(data.items) && (data.state === 'queued' || data.state === 'pending' || Boolean(data.job));
}

function looksProviderBlocked(text) {
  const value = String(text || '').toLowerCase();
  return value.includes('401') || value.includes('unauthorized') || value.includes('credential') || value.includes('auth');
}

function markFailClosed(providerBlocked) {
  document.getElementById('fail-closed-state').textContent = providerBlocked
    ? t('provider_blocked_badge')
    : (state.lang === 'ko' ? 'fail-closed: 후보 미노출' : 'fail-closed: candidates blocked');
}

function renderScanReport(data, { notice } = {}) {
  state.scan = data.items;
  state.failures = data.failures || [];
  renderScan(data.items, data.elapsed_ms);
  if (data.selection) {
    state.selection = data.selection;
    state.selection.elapsed_ms = data.elapsed_ms;
    renderSelection(data.selection, data.elapsed_ms);
  }
  updateDataStatus(data.items, data.failures || []);
  updateDiscoverySummary(data);
  showNotice(notice || (state.lang === 'ko'
    ? `시장 전체 스캔이 ${data.elapsed_ms} ms 안에 완료되었습니다.`
    : `Market scan completed in ${data.elapsed_ms} ms.`));
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function waitForMarketScanJob(jobId, token) {
  for (let attempt = 1; attempt <= SCAN_POLL_ATTEMPTS; attempt += 1) {
    await sleep(SCAN_POLL_INTERVAL_MS);
    if (token !== scanPollToken) return;  // a newer scan superseded this one
    let job;
    try {
      job = await api(`/api/jobs/market-scan/${encodeURIComponent(jobId)}`);
    } catch (error) {
      markFailClosed(looksProviderBlocked(error.message));
      showNotice(error.message, true);
      return;
    }
    if (job.status === 'completed' && job.report && Array.isArray(job.report.items)) {
      renderScanReport(job.report, { notice: t('scan_ready_after_wait') });
      await loadOps();
      return;
    }
    if (job.status === 'failed' || job.status === 'dead_letter') {
      const reason = job.message || job.error_code || job.status;
      const providerBlocked = looksProviderBlocked(`${job.error_code} ${job.message}`);
      markFailClosed(providerBlocked);
      showNotice(providerBlocked ? t('scan_provider_blocked') : t('scan_job_failed', { reason }), true);
      await loadOps();
      return;
    }
    showNotice(t('scan_waiting', { attempt, total: SCAN_POLL_ATTEMPTS }));
  }
  showNotice(t('scan_still_running'));
}

async function runScan() {
  const token = (scanPollToken += 1);
  setBusy(true);
  try {
    const data = await api(endpoint('/api/scan', '/api/user/scan'), { method: state.config?.user_auth_enabled ? 'POST' : 'GET' });
    if (isQueuedScanOutcome(data)) {
      const job = data.job || {};
      updateDiscoverySummary(data);
      showNotice(t('scan_queued'));
      document.getElementById('runtime').textContent = t('waiting');
      if (!job.id) {
        showNotice(t('scan_still_running'));
        return;
      }
      await waitForMarketScanJob(job.id, token);
      return;
    }
    renderScanReport(data);
    await loadOps();
  } catch (error) {
    markFailClosed(looksProviderBlocked(error.message));
    showNotice(error.message, true);
  } finally {
    if (token === scanPollToken) setBusy(false);
  }
}

function renderScan(items, elapsedMs = 0) {
  const sorted = [...items].sort((a, b) => b.combined_score - a.combined_score);
  const actionable = sorted.filter((item) => item.can_enter);
  const excluded = sorted.filter((item) => !item.can_enter);
  document.getElementById('actionable-meta').textContent = state.lang === 'ko'
    ? `${items.length}개 중 ${actionable.length}개 연구 후보 / ${elapsedMs} ms`
    : `${actionable.length} research candidates / ${items.length} in ${elapsedMs} ms`;
  document.getElementById('excluded-meta').textContent = state.lang === 'ko'
    ? `${excluded.length}개 모니터링`
    : `${excluded.length} monitoring`;
  renderTable('actionable-body', actionable, false);
  renderTable('excluded-body', excluded, true);
  wireDetailRows();
}

async function runSelection() {
  setBusy(true);
  try {
    const data = await api(endpoint('/api/select', '/api/user/select'), { method: state.config?.user_auth_enabled ? 'POST' : 'GET' });
    state.selection = data.selection;
    state.selection.elapsed_ms = data.elapsed_ms;
    updateDataStatus(data.selection.selected || [], data.failures || []);
    renderSelection(data.selection, data.elapsed_ms);
    showNotice(t('selection_completed', { ms: data.elapsed_ms }));
    await loadOps();
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    setBusy(false);
  }
}

function renderSelection(selection, elapsedMs) {
  document.getElementById('selection-meta').textContent =
    isKo()
      ? `${selection.selected.length}/${selection.max_positions}, 총 ${selection.total_size_pct}%, ${elapsedMs} ms`
      : `${selection.selected.length}/${selection.max_positions}, ${selection.total_size_pct}% in ${elapsedMs} ms`;
  const target = document.getElementById('selection');
  if (!selection.selected.length) {
    target.innerHTML = `<div class="empty-state">${t('no_eligible')}</div>`;
    return;
  }
  target.innerHTML = selection.selected.map((item, index) => `
    <article class="candidate-card clickable" data-ticker="${escapeHtml(item.ticker)}"
      aria-label="${escapeHtml(item.ticker)} ${escapeHtml(publicLabel(item))}">
      <div class="candidate-top">
        <div class="ticker-lockup">
          <div class="rank">${index + 1}</div>
          <div class="ticker-symbol">${escapeHtml(item.ticker)}</div>
        </div>
        <div class="score">${item.combined_score}<small>${t('score')}</small></div>
      </div>
      <div class="candidate-meta">
        ${escapeHtml(archetypeLabel(item))} / ${escapeHtml(publicLabel(item))}
      </div>
      <div class="candidate-data-row">
        <span>${t('data_coverage')}: ${item.data_coverage_score || 0}/100 (${escapeHtml(coverageLabel(item.data_coverage_label))})</span>
        <span>${t('provider')}: ${escapeHtml(translateSource(item.source))}</span>
      </div>
      <ul class="reason-list">
        ${reasonItems(item).slice(0, 3).map((reason) => `<li>${escapeHtml(translateText(reason, item))}</li>`).join('')}
      </ul>
      <div class="candidate-foot">
        <span>${t('allocation_guide')} ${item.suggested_size_pct}%</span>
        <span>${escapeHtml(item.data_as_of)} / ${escapeHtml(item.scoring_version)}</span>
      </div>
    </article>
  `).join('');
  wireDetailRows();
}

async function refreshAll() {
  setBusy(true);
  try {
    await loadConfig();
    await ensureUserSession();
    await ensureStarterWatchlist();
    await Promise.all([loadWatchlist(), loadOps()]);
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    setBusy(false);
  }
}

async function bootstrap() {
  await refreshAll();
}

function updateDiscoverySummary(data = {}) {
  const snapshot = data.snapshot || {};
  const items = Array.isArray(data.items) ? data.items : [];
  const selected = data.selection && Array.isArray(data.selection.selected) ? data.selection.selected : [];
  const combined = [...items, ...selected];
  const status = snapshot.status || data.status || data.state || '';
  if (status === 'fresh' || snapshot.served_from === 'durable_snapshot') {
    document.getElementById('scan-freshness').textContent = snapshot.completed_at
      ? `${t('fresh_snapshot')} / ${snapshot.completed_at}`
      : t('fresh_snapshot');
  } else if (status === 'queued' || status === 'pending' || data.job) {
    document.getElementById('scan-freshness').textContent = t('queued_snapshot');
  } else if (!combined.length) {
    document.getElementById('scan-freshness').textContent = t('no_snapshot_yet');
  }
  if (combined.length) {
    const providers = [...new Set(combined.map((item) => item.source).filter(Boolean))];
    if (providers.length) document.getElementById('provider-source').textContent = providers.map(translateSource).join(', ');
    const coverageValues = combined.map((item) => Number(item.data_coverage_score || 0)).filter((value) => value >= 0);
    const average = coverageValues.length
      ? Math.round(coverageValues.reduce((total, value) => total + value, 0) / coverageValues.length)
      : 0;
    document.getElementById('coverage-state').textContent = `${average}/100`;
  }
  const liveRequired = state.config && state.config.market_scan_requires_live_data;
  document.getElementById('fail-closed-state').textContent = liveRequired
    ? t('fail_closed_active')
    : (isKo() ? '로컬/데모 대체 데이터 허용' : 'Local/demo fallback allowed');
}

function renderTable(targetId, items, excluded) {
  const body = document.getElementById(targetId);
  if (!items.length) {
    body.innerHTML = `<tr><td colspan="6" class="empty-state">${excluded ? t('no_excluded') : t('no_actionable')}</td></tr>`;
    return;
  }
  body.innerHTML = items.map((item) => {
    const badgeClass = item.can_enter ? 'good' : item.combined_score >= 50 ? 'warn' : 'bad';
    const reason = excluded ? rejectionReason(item) : `${item.suggested_size_pct}%`;
    return `
      <tr class="clickable" data-ticker="${escapeHtml(item.ticker)}">
        <td data-label="${t('ticker')}"><strong>${escapeHtml(item.ticker)}</strong></td>
        <td data-label="${t('archetype')}">${escapeHtml(archetypeLabel(item))}</td>
        <td data-label="${t('score')}">${item.combined_score}</td>
        <td data-label="${t('status')}"><span class="badge ${badgeClass}">${escapeHtml(publicLabel(item))}</span></td>
        <td data-label="${excluded ? t('reason') : t('allocation')}">${escapeHtml(translateText(reason, item))}</td>
        <td data-label="${t('data')}">${escapeHtml(translateSource(item.source))} / ${escapeHtml(item.data_as_of)}</td>
      </tr>
    `;
  }).join('');
}

function updateDataStatus(items, failures = []) {
  const validDates = items.map((item) => item.data_as_of).filter(Boolean).sort();
  const latest = validDates.length ? validDates[validDates.length - 1] : (isKo() ? '불러오지 않음' : 'not loaded');
  const providers = [...new Set(items.map((item) => item.source).filter(Boolean))];
  document.getElementById('data-as-of').textContent = `${t('data_as_of')}: ${latest}`;
  if (providers.length) {
    document.getElementById('data-source').textContent =
      `${t('provider')}: ${providers.map(translateSource).join(', ')}`;
    document.getElementById('provider-source').textContent = providers.map(translateSource).join(', ');
  }
  if (items.length) {
    const coverageValues = items.map((item) => Number(item.data_coverage_score || 0)).filter((value) => value >= 0);
    const average = coverageValues.length
      ? Math.round(coverageValues.reduce((total, value) => total + value, 0) / coverageValues.length)
      : 0;
    document.getElementById('coverage-state').textContent = `${average}/100`;
  }
  const opsState = document.getElementById('ops-state');
  opsState.className = `status-dot ${failures.length ? 'warn' : 'good'}`;
  opsState.textContent = failures.length ? t('ops_provider_issues', { count: failures.length }) : t('ops_success');
}

function reasonItems(item) {
  const notes = [
    ...(item.rationale || []),
    ...(item.precision_notes || []),
    ...(item.warnings || [])
  ].filter(Boolean);
  if (notes.length) return notes;
  return [
    `${item.primary_archetype_label} score is ${item.combined_score}.`,
    item.can_enter ? 'Entry threshold is met.' : 'Entry threshold is not met.',
    `Allocation guide is ${item.suggested_size_pct}%.`
  ];
}

function rejectionReason(item) {
  if (item.warnings && item.warnings.length) return translateText(item.warnings[0], item);
  if (item.combined_score < 55) return translateText('Score below entry threshold.', item);
  return translateText('Monitor only.', item);
}

function findEvaluation(ticker) {
  return [...state.scan, ...((state.selection && state.selection.selected) || [])]
    .find((item) => item.ticker === ticker);
}

function wireDetailRows() {
  document.querySelectorAll('[data-ticker]').forEach((element) => {
    if (element.dataset.bound === 'true') return;
    element.dataset.bound = 'true';
    element.addEventListener('click', () => openDetailPage(element.dataset.ticker));
  });
}

function openDetailPage(ticker) {
  window.location.href = `/ticker/${encodeURIComponent(ticker)}`;
}

function openDetail(ticker) {
  const item = findEvaluation(ticker);
  if (!item) return;
  const modal = document.getElementById('detail-modal');
  const content = document.getElementById('detail-content');
  content.innerHTML = `
    <p class="eyebrow">${isKo() ? '점수 리포트' : 'Score report'}</p>
    <h2 id="detail-title">${escapeHtml(item.ticker)} <span class="muted">${escapeHtml(archetypeLabel(item))}</span></h2>
    <div class="detail-grid">
      <div class="metric-box"><span>${t('score')}</span><strong>${item.combined_score}</strong></div>
      <div class="metric-box"><span>${isKo() ? '검토 상태' : 'Review state'}</span><strong>${escapeHtml(publicLabel(item))}</strong></div>
      <div class="metric-box"><span>${t('allocation_guide')}</span><strong>${item.suggested_size_pct}%</strong></div>
      <div class="metric-box"><span>${isKo() ? '위험 참고' : 'Risk marker'}</span><strong>${item.stop_loss}</strong></div>
    </div>
    <p class="muted">
      ${t('data')}: ${escapeHtml(translateSource(item.source))} / ${escapeHtml(item.data_as_of)} /
      ${escapeHtml(translateDataQuality(item.data_quality))} / ${escapeHtml(item.scoring_version)}
    </p>
    <h3>${isKo() ? '선정 근거' : 'Rationale'}</h3>
    <ul class="reason-list">${reasonItems(item).map((reason) => `<li>${escapeHtml(translateText(reason, item))}</li>`).join('')}</ul>
  `;
  modal.hidden = false;
}

function closeDetail() {
  document.getElementById('detail-modal').hidden = true;
}

document.getElementById('add-form').addEventListener('submit', addTickers);
document.getElementById('starter-research-button').addEventListener('click', seedStarterResearchList);
document.getElementById('scan-button').addEventListener('click', runScan);
document.getElementById('select-button').addEventListener('click', runSelection);
document.getElementById('refresh-button').addEventListener('click', bootstrap);
document.getElementById('detail-close').addEventListener('click', closeDetail);
document.getElementById('detail-modal').addEventListener('click', (event) => {
  if (event.target.id === 'detail-modal') closeDetail();
});
initLanguageToggle();
bootstrap();
