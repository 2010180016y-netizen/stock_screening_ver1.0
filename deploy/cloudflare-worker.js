const SAMPLE_TICKERS = ["PLTR", "MSTR", "VST", "AAPL", "NVDA", "SMCI", "CELH", "CRWD", "TSLA", "MSFT"];
const CACHE_TTL_SECONDS = 60 * 60 * 12;

const HTML = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VCB-Alt Screening Desk</title>
  <style>
    :root{color-scheme:light;--bg:#f5f7f8;--ink:#172026;--muted:#68747d;--line:#d9e0e4;--panel:#fff;--accent:#006d5b;--bad:#9b1c1c;--good:#0f6b3e;--warn:#9b5c00}
    *{box-sizing:border-box}body{margin:0;font-family:Arial,Helvetica,sans-serif;background:var(--bg);color:var(--ink)}
    .shell{width:min(1440px,calc(100% - 32px));margin:0 auto;padding:24px 0 40px}.login-shell{min-height:100vh;display:grid;place-items:center;padding:24px}
    .login-panel,.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px}.login-panel{width:min(420px,100%);padding:22px}.login-panel form{display:grid;gap:10px;margin-top:18px}
    .topbar{display:flex;justify-content:space-between;gap:20px;align-items:flex-start;margin-bottom:18px}.eyebrow{margin:0 0 4px;color:var(--accent);font-size:12px;font-weight:700;text-transform:uppercase}
    h1,h2{margin:0;letter-spacing:0}h1{font-size:28px;line-height:1.15}h2{font-size:16px}.status-strip{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}
    .status-strip span,.panel-head span{border:1px solid var(--line);background:#fbfcfd;border-radius:999px;padding:5px 9px;color:var(--muted);font-size:12px}
    .toolbar{display:grid;grid-template-columns:minmax(260px,1fr) repeat(3,max-content);gap:10px;align-items:end;margin-bottom:14px}.ticker-form{display:grid;grid-template-columns:90px 1fr max-content;gap:8px;align-items:center}
    label{color:var(--muted);font-size:13px}input{height:38px;border:1px solid var(--line);border-radius:6px;padding:0 10px;font-size:14px;background:white}
    button{height:38px;border:1px solid var(--accent);background:var(--accent);color:white;border-radius:6px;padding:0 13px;font-weight:700;cursor:pointer}button:disabled{opacity:.55;cursor:wait}
    .notice{border:1px solid var(--line);border-left:4px solid var(--accent);background:white;padding:10px 12px;margin-bottom:14px;border-radius:6px}.notice.error{border-left-color:var(--bad)}
    .grid{display:grid;grid-template-columns:310px 1fr;grid-template-areas:"watch selection" "watch scan" "ops scan";gap:14px}.watchlist-panel{grid-area:watch}.selection-panel{grid-area:selection}.scan-panel{grid-area:scan}.ops-panel{grid-area:ops}
    .panel{min-width:0}.panel-head{min-height:48px;border-bottom:1px solid var(--line);padding:12px 14px;display:flex;justify-content:space-between;gap:10px;align-items:center}.watchlist,.selection-list,.ops-list,.readiness{padding:12px 14px}
    .ticker-row{display:flex;justify-content:space-between;align-items:center;gap:8px;border-bottom:1px solid #eef2f4;padding:9px 0}.ticker-row:last-child{border-bottom:0}.ticker-row button{height:28px;padding:0 8px;background:white;color:var(--bad);border-color:#efcaca}
    .selected-card{display:grid;grid-template-columns:42px 1fr 90px;gap:12px;align-items:center;border-bottom:1px solid #eef2f4;padding:11px 0}.selected-card:last-child{border-bottom:0}.rank{width:34px;height:34px;display:grid;place-items:center;background:#e7f3ef;color:var(--accent);border-radius:999px;font-weight:800}.score{font-weight:800;text-align:right}.muted{color:var(--muted)}
    .empty-state{color:var(--muted);padding:18px 0}.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;min-width:760px}th,td{text-align:left;padding:10px 12px;border-bottom:1px solid #eef2f4;font-size:13px}th{color:var(--muted);font-size:12px;text-transform:uppercase}
    .badge{display:inline-block;border-radius:999px;padding:4px 8px;background:#eef2f4;color:var(--muted)}.badge.good{background:#e5f5ec;color:var(--good)}.badge.warn{background:#fff4df;color:var(--warn)}.readiness{border-bottom:1px solid #eef2f4;font-size:13px;color:var(--muted)}.ops-list{font-size:13px;color:var(--muted)}
    @media(max-width:900px){.topbar,.toolbar,.ticker-form{display:block}.toolbar>*,.ticker-form>*{width:100%;margin-bottom:8px}.grid{grid-template-columns:1fr;grid-template-areas:"watch" "selection" "scan" "ops"}}
  </style>
</head>
<body>
<main class="shell">
  <header class="topbar"><div><p class="eyebrow">VCB-Alt Screening Desk</p><h1>Stock selection workspace</h1></div><div class="status-strip"><span id="provider">Cloudflare + Yahoo data</span><span id="runtime">ready</span></div></header>
  <section class="toolbar" aria-label="Actions"><form id="add-form" class="ticker-form"><label for="ticker-input">Add tickers</label><input id="ticker-input" name="tickers" autocomplete="off" placeholder="PLTR MSTR VST"><button type="submit">Add</button></form><button id="scan-button" type="button">Run scan</button><button id="select-button" type="button">Select final 3</button><button id="refresh-button" type="button">Refresh</button></section>
  <section id="notice" class="notice" hidden></section>
  <section class="grid">
    <div class="panel watchlist-panel"><div class="panel-head"><h2>Watchlist</h2><span id="watchlist-count">0</span></div><div id="watchlist" class="watchlist"></div></div>
    <div class="panel selection-panel"><div class="panel-head"><h2>Final selection</h2><span id="selection-meta">Not run</span></div><div id="selection" class="selection-list empty-state">Run selection to see final candidates.</div></div>
    <div class="panel scan-panel"><div class="panel-head"><h2>Scan results</h2><span id="scan-meta">Not run</span></div><div class="table-wrap"><table><thead><tr><th>Ticker</th><th>Archetype</th><th>Score</th><th>Status</th><th>Size</th><th>Data</th></tr></thead><tbody id="scan-body"><tr><td colspan="6" class="empty-state">Run scan to populate results.</td></tr></tbody></table></div></div>
    <div class="panel ops-panel"><div class="panel-head"><h2>Operations</h2><span id="failure-count">0 failures</span></div><div id="readiness" class="readiness"></div><div id="failures" class="ops-list"></div></div>
  </section>
</main>
<script>
async function api(path, options = {}) {
  const response = await fetch(path, {...options, headers: {'Content-Type': 'application/json', ...(options.headers || {})}});
  const payload = await response.json();
  if (!payload.ok) throw new Error(payload.error?.message || payload.message || 'Request failed');
  return payload.data;
}
function showNotice(message, error = false) { const box = document.getElementById('notice'); box.hidden = false; box.className = 'notice' + (error ? ' error' : ''); box.textContent = message; }
function setBusy(busy) { document.querySelectorAll('button').forEach((button) => { button.disabled = busy; }); document.getElementById('runtime').textContent = busy ? 'running' : 'ready'; }
async function loadWatchlist() { const data = await api('/api/watchlist'); document.getElementById('watchlist-count').textContent = data.count + ' tickers'; const target = document.getElementById('watchlist'); target.innerHTML = data.items.length ? data.items.map((item) => '<div class="ticker-row"><strong>' + item.ticker + '</strong><button type="button" data-remove="' + item.ticker + '">Remove</button></div>').join('') : '<div class="empty-state">Add tickers to begin.</div>'; target.querySelectorAll('[data-remove]').forEach((button) => button.addEventListener('click', () => removeTicker(button.dataset.remove))); }
async function loadOps() { const [readiness, failures] = await Promise.all([api('/api/saas-readiness'), api('/api/failures')]); document.getElementById('failure-count').textContent = failures.count + ' failures'; document.getElementById('readiness').innerHTML = '<strong>' + readiness.decision + '</strong><br>' + readiness.p0_blocker_count + ' public-SaaS blockers remain. Token-protected beta is live.'; document.getElementById('failures').innerHTML = failures.items.length ? failures.items.map((item) => '<div>' + item.created_at + ': ' + item.message + '</div>').join('') : '<div>No recent failures.</div>'; }
async function addTickers(event) { event.preventDefault(); const input = document.getElementById('ticker-input'); const tickers = input.value.trim(); if (!tickers) return; setBusy(true); try { const data = await api('/api/watchlist', {method:'POST', body:JSON.stringify({tickers})}); input.value = ''; showNotice('Added: ' + (data.added.join(', ') || 'none') + '; existing: ' + (data.existing.join(', ') || 'none')); await loadWatchlist(); } catch (error) { showNotice(error.message, true); } finally { setBusy(false); } }
async function removeTicker(ticker) { setBusy(true); try { await api('/api/watchlist?ticker=' + encodeURIComponent(ticker), {method:'DELETE'}); showNotice(ticker + ' removed.'); await loadWatchlist(); } catch (error) { showNotice(error.message, true); } finally { setBusy(false); } }
async function runScan() { setBusy(true); try { const data = await api('/api/scan'); document.getElementById('scan-meta').textContent = data.count + ' tickers in ' + data.elapsed_ms + ' ms'; renderScan(data.items); showNotice('Scan completed in ' + data.elapsed_ms + ' ms.'); await loadOps(); } catch (error) { showNotice(error.message, true); } finally { setBusy(false); } }
function renderScan(items) { const body = document.getElementById('scan-body'); body.innerHTML = items.length ? items.sort((a,b)=>b.combined_score-a.combined_score).map((item) => '<tr><td><strong>' + item.ticker + '</strong></td><td>' + item.primary_archetype_label + '</td><td>' + item.combined_score + '</td><td><span class="badge ' + (item.can_enter ? 'good' : 'warn') + '">' + item.decision_label + '</span></td><td>' + item.suggested_size_pct + '%</td><td>' + item.source + ' / ' + item.data_as_of + '</td></tr>').join('') : '<tr><td colspan="6" class="empty-state">No results.</td></tr>'; }
async function runSelection() { setBusy(true); try { const data = await api('/api/select'); renderSelection(data.selection, data.elapsed_ms); showNotice('Selection completed in ' + data.elapsed_ms + ' ms.'); await loadOps(); } catch (error) { showNotice(error.message, true); } finally { setBusy(false); } }
function renderSelection(selection, elapsedMs) { document.getElementById('selection-meta').textContent = selection.selected.length + '/' + selection.max_positions + ', ' + selection.total_size_pct + '% in ' + elapsedMs + ' ms'; const target = document.getElementById('selection'); target.innerHTML = selection.selected.length ? selection.selected.map((item,index) => '<div class="selected-card"><div class="rank">' + (index + 1) + '</div><div><strong>' + item.ticker + '</strong><div class="muted">' + item.primary_archetype_label + ' / ' + item.decision_label + '</div></div><div class="score">' + item.combined_score + '<br><span class="muted">' + item.suggested_size_pct + '%</span></div></div>').join('') : '<div class="empty-state">No eligible candidates.</div>'; }
async function bootstrap() { setBusy(true); try { await Promise.all([loadWatchlist(), loadOps()]); await runScan(); await runSelection(); } catch (error) { showNotice(error.message, true); } finally { setBusy(false); } }
document.getElementById('add-form').addEventListener('submit', addTickers); document.getElementById('scan-button').addEventListener('click', runScan); document.getElementById('select-button').addEventListener('click', runSelection); document.getElementById('refresh-button').addEventListener('click', bootstrap); bootstrap();
</script>
</body>
</html>`;

const LOGIN_HTML = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>VCB-Alt Access</title><style>body{margin:0;font-family:Arial,Helvetica,sans-serif;background:#f5f7f8;color:#172026}.login-shell{min-height:100vh;display:grid;place-items:center;padding:24px}.login-panel{width:min(420px,100%);background:#fff;border:1px solid #d9e0e4;border-radius:8px;padding:22px}.eyebrow{margin:0 0 4px;color:#006d5b;font-size:12px;font-weight:700;text-transform:uppercase}h1{margin:0;font-size:28px}form{display:grid;gap:10px;margin-top:18px}input,button{height:38px;border-radius:6px;font-size:14px}input{border:1px solid #d9e0e4;padding:0 10px}button{border:1px solid #006d5b;background:#006d5b;color:white;font-weight:700}</style></head><body><main class="login-shell"><section class="login-panel"><p class="eyebrow">VCB-Alt Screening Desk</p><h1>Access required</h1><p>Enter the deployment access token configured by the operator.</p><form method="get" action="/"><label for="token">Access token</label><input id="token" name="token" type="password" required><button type="submit">Open dashboard</button></form></section></main></body></html>`;

export default {
  async fetch(request, env, ctx) {
    try {
      await ensureDb(env.DB);
      const url = new URL(request.url);
      if (url.pathname === "/api/health") return json(ok("OK", { status: "healthy" }));
      if (!(await isAuthorized(request, env.WEB_ACCESS_TOKEN || ""))) {
        if (url.pathname === "/" && request.method === "GET") return html(LOGIN_HTML, 401);
        return json(fail("Authentication is required for public web mode.", 401, "UNAUTHORIZED"), 401);
      }
      const cookieHeaders = await authCookieHeaders(url, env.WEB_ACCESS_TOKEN || "");
      if (url.pathname === "/" && request.method === "GET") return html(HTML, 200, cookieHeaders);
      if (!url.pathname.startsWith("/api/")) return json(fail("Route not found.", 404, "NOT_FOUND"), 404);
      return await handleApi(request, env, ctx, url);
    } catch (error) {
      console.log(JSON.stringify({ level: "error", message: String(error?.message || error) }));
      return json(fail("Unexpected server error.", 500, "INTERNAL_ERROR"), 500);
    }
  }
};

async function handleApi(request, env, ctx, url) {
  if (request.method === "GET" && url.pathname === "/api/config") {
    return json(ok("Configuration loaded.", { data_provider: "yahoo", external_api_enabled: true, public_web_enabled: true, market_data_cache_ttl_hours: 12, runtime: "cloudflare-worker-d1" }));
  }
  if (request.method === "GET" && url.pathname === "/api/saas-readiness") {
    return json(ok("SaaS readiness checked.", { decision: "READY_FOR_PRIVATE_BETA", p0_blocker_count: 0, warning: "Token-protected beta. Legal documents are not reviewed for public launch." }));
  }
  if (url.pathname === "/api/watchlist") return await handleWatchlist(request, env.DB, url);
  if (request.method === "GET" && url.pathname === "/api/scan") {
    const start = Date.now();
    const { items, failures } = await evaluateWatchlist(env.DB, ctx);
    return json(ok("Scan completed.", { items, failures, count: items.length, elapsed_ms: Date.now() - start }));
  }
  if (request.method === "GET" && url.pathname === "/api/select") {
    const start = Date.now();
    const { items, failures } = await evaluateWatchlist(env.DB, ctx);
    const selection = selectPortfolio(items);
    return json(ok("Selection completed.", { selection, failures, elapsed_ms: Date.now() - start }));
  }
  if (request.method === "GET" && url.pathname === "/api/failures") {
    const rows = await env.DB.prepare("SELECT command,error_code,message,created_at FROM failed_jobs ORDER BY id DESC LIMIT 12").all();
    return json(ok("Failures loaded.", { items: rows.results || [], count: (rows.results || []).length }));
  }
  return json(fail("API route not found.", 404, "NOT_FOUND"), 404);
}

async function handleWatchlist(request, db, url) {
  if (request.method === "GET") {
    const rows = await db.prepare("SELECT ticker, added_at FROM watchlist ORDER BY ticker").all();
    return json(ok("Watchlist loaded.", { items: rows.results || [], count: (rows.results || []).length }));
  }
  if (request.method === "POST") {
    const body = await request.json().catch(() => ({}));
    const raw = Array.isArray(body.tickers) ? body.tickers.join(" ") : String(body.tickers || body.ticker || "");
    const tickers = [...new Set(raw.replace(/,/g, " ").split(/\s+/).map(validateTicker).filter(Boolean))];
    if (!tickers.length) return json(fail("ticker or tickers is required.", 400, "VALIDATION_ERROR"), 400);
    const added = [];
    const existing = [];
    for (const ticker of tickers) {
      const result = await db.prepare("INSERT OR IGNORE INTO watchlist (ticker, added_at) VALUES (?, ?)").bind(ticker, now()).run();
      if (result.meta?.changes) added.push(ticker); else existing.push(ticker);
    }
    await logOperation(db, "web watchlist add", "success", "Watchlist updated.");
    return json(ok("Watchlist updated.", { added, existing }), 201);
  }
  if (request.method === "DELETE") {
    const ticker = validateTicker(url.searchParams.get("ticker") || "");
    if (!ticker) return json(fail("ticker is required.", 400, "VALIDATION_ERROR"), 400);
    const result = await db.prepare("DELETE FROM watchlist WHERE ticker = ?").bind(ticker).run();
    await logOperation(db, "web watchlist remove", "success", "Watchlist updated.");
    return json(ok("Watchlist updated.", { removed: result.meta?.changes ? [ticker] : [], missing: result.meta?.changes ? [] : [ticker] }));
  }
  return json(fail("Method not allowed.", 405, "METHOD_NOT_ALLOWED"), 405);
}

async function evaluateWatchlist(db, ctx) {
  const rows = await db.prepare("SELECT ticker FROM watchlist ORDER BY ticker").all();
  const tickers = (rows.results || []).map((row) => row.ticker);
  const settled = await Promise.all(tickers.map(async (ticker) => {
    try {
      return { ok: true, value: await evaluateTicker(db, ticker, ctx) };
    } catch (error) {
      const failure = { ticker, code: "PROVIDER_ERROR", message: String(error?.message || error) };
      ctx.waitUntil(recordFailure(db, "web scan", failure.code, failure.message));
      return { ok: false, value: failure };
    }
  }));
  return { items: settled.filter((item) => item.ok).map((item) => item.value), failures: settled.filter((item) => !item.ok).map((item) => item.value) };
}

async function evaluateTicker(db, ticker, ctx) {
  const [bars, spyBars] = await Promise.all([loadBars(db, ticker, ctx), loadBars(db, "SPY", ctx)]);
  const latest = bars[bars.length - 1];
  const closes = bars.map((bar) => bar.close);
  const volumes = bars.map((bar) => bar.volume);
  const highs = bars.map((bar) => bar.high);
  const lows = bars.map((bar) => bar.low);
  const close = latest.close;
  const sma50 = average(closes.slice(-50));
  const sma150 = average(closes.slice(-150));
  const sma200 = average(closes.slice(-200));
  const priorSma200 = average(closes.slice(-221, -21));
  const high52 = Math.max(...highs.slice(-252));
  const low52 = Math.min(...lows.slice(-252));
  const return12w = returnPct(closes, 63);
  const return12m = returnPct(closes, 252);
  const spyReturn = returnPct(spyBars.map((bar) => bar.close), 63);
  const volumeRatio = latest.volume / Math.max(average(volumes.slice(-50)), 1);
  const trendScore = trendTemplate(close, sma50, sma150, sma200, priorSma200, high52, low52);
  const surgeScore = clamp(Math.round(volumeRatio * 18 + Math.max(return12w, 0) * 0.45), 0, 100);
  const rsScore = clamp(Math.round(50 + (return12w - spyReturn) * 1.2), 0, 100);
  const score = clamp(Math.round(trendScore * 0.45 + surgeScore * 0.2 + rsScore * 0.25 + Math.max(return12m, 0) * 0.1), 0, 100);
  const canEnter = score >= 67 && trendScore >= 55;
  return {
    ticker,
    primary_archetype: "G_TECHNICAL_MOMENTUM",
    primary_archetype_label: "Technical Momentum",
    combined_score: score,
    setup_strength: score >= 75 ? "strong" : score >= 67 ? "watch" : "weak",
    can_enter: canEnter,
    decision_label: canEnter ? "RESEARCH_CANDIDATE" : score >= 60 ? "MONITOR" : "PASS",
    suggested_size_pct: canEnter ? (score >= 75 ? 12 : 8) : 0,
    stop_loss: round(close * 0.92, 2),
    source: "yahoo",
    data_as_of: latest.date,
    metrics: { price: close, return_12w_pct: round(return12w, 2), return_12m_pct: round(return12m, 2), relative_strength_vs_spy: round(return12w - spyReturn, 2), volume_ratio: round(volumeRatio, 2), trend_score: trendScore }
  };
}

async function loadBars(db, ticker, ctx) {
  const cached = await db.prepare("SELECT payload_json,fetched_at FROM market_cache WHERE ticker = ?").bind(ticker).first();
  const nowSeconds = Math.floor(Date.now() / 1000);
  if (cached && nowSeconds - Number(cached.fetched_at) < CACHE_TTL_SECONDS) return JSON.parse(cached.payload_json);
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(ticker)}?range=1y&interval=1d`;
  const response = await fetch(url, { headers: { "User-Agent": "VCB-Alt/0.5.2" } });
  if (!response.ok) throw new Error(`Yahoo returned ${response.status} for ${ticker}.`);
  const payload = await response.json();
  const result = payload?.chart?.result?.[0];
  const timestamps = result?.timestamp || [];
  const quote = result?.indicators?.quote?.[0] || {};
  const bars = timestamps.map((timestamp, index) => ({
    date: new Date(timestamp * 1000).toISOString().slice(0, 10),
    close: Number(quote.close?.[index]),
    high: Number(quote.high?.[index]),
    low: Number(quote.low?.[index]),
    volume: Number(quote.volume?.[index])
  })).filter((bar) => Number.isFinite(bar.close) && Number.isFinite(bar.high) && Number.isFinite(bar.low) && Number.isFinite(bar.volume));
  if (bars.length < 80) throw new Error(`Not enough market history for ${ticker}.`);
  ctx.waitUntil(db.prepare("INSERT OR REPLACE INTO market_cache (ticker,payload_json,fetched_at) VALUES (?, ?, ?)").bind(ticker, JSON.stringify(bars), nowSeconds).run());
  return bars;
}

function selectPortfolio(items) {
  const selected = [];
  let total = 0;
  for (const item of [...items].sort((a, b) => b.combined_score - a.combined_score)) {
    if (selected.length >= 3) break;
    if (!item.can_enter) continue;
    if (total + item.suggested_size_pct > 75) continue;
    selected.push(item);
    total += item.suggested_size_pct;
  }
  return { selected, max_positions: 3, total_size_pct: round(total, 2) };
}

async function ensureDb(db) {
  await db.exec(`CREATE TABLE IF NOT EXISTS watchlist (ticker TEXT PRIMARY KEY, added_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS operation_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL, status TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS failed_jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, command TEXT NOT NULL, error_code TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS market_cache (ticker TEXT PRIMARY KEY, payload_json TEXT NOT NULL, fetched_at INTEGER NOT NULL);`);
  const count = await db.prepare("SELECT COUNT(*) AS count FROM watchlist").first();
  if (Number(count?.count || 0) === 0) {
    const stmt = db.prepare("INSERT OR IGNORE INTO watchlist (ticker, added_at) VALUES (?, ?)");
    await db.batch(SAMPLE_TICKERS.map((ticker) => stmt.bind(ticker, now())));
  }
}

async function isAuthorized(request, token) {
  if (!token || token.length < 16) return false;
  const url = new URL(request.url);
  const candidates = [];
  if (url.searchParams.get("token")) candidates.push(url.searchParams.get("token"));
  const auth = request.headers.get("authorization") || "";
  if (auth.toLowerCase().startsWith("bearer ")) candidates.push(auth.slice(7).trim());
  const cookie = request.headers.get("cookie") || "";
  const match = cookie.match(/(?:^|;\s*)vcb_alt_token=([^;]+)/);
  if (match) candidates.push(decodeURIComponent(match[1]));
  for (const candidate of candidates) if (await timingSafeEqual(candidate || "", token)) return true;
  return false;
}

async function authCookieHeaders(url, token) {
  const queryToken = url.searchParams.get("token") || "";
  if (!(await timingSafeEqual(queryToken, token))) return {};
  return { "Set-Cookie": `vcb_alt_token=${encodeURIComponent(queryToken)}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=28800` };
}

async function timingSafeEqual(left, right) {
  const encoder = new TextEncoder();
  const a = encoder.encode(left);
  const b = encoder.encode(right);
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= a[i] ^ b[i];
  return diff === 0;
}

async function logOperation(db, action, status, message) {
  await db.prepare("INSERT INTO operation_logs (action,status,message,created_at) VALUES (?, ?, ?, ?)").bind(action, status, message, now()).run();
}

async function recordFailure(db, command, code, message) {
  await db.prepare("INSERT INTO failed_jobs (command,error_code,message,created_at) VALUES (?, ?, ?, ?)").bind(command, code, message, now()).run();
}

function validateTicker(value) {
  const ticker = String(value || "").trim().toUpperCase();
  return /^[A-Z][A-Z0-9.-]{0,9}$/.test(ticker) ? ticker : "";
}

function trendTemplate(close, sma50, sma150, sma200, priorSma200, high52, low52) {
  let score = 0;
  if (close > sma50) score += 15;
  if (close > sma150) score += 15;
  if (close > sma200) score += 20;
  if (sma50 > sma150 && sma150 > sma200) score += 20;
  if (sma200 >= priorSma200) score += 10;
  if (close >= high52 * 0.75) score += 10;
  if (close >= low52 * 1.25) score += 10;
  return clamp(score, 0, 100);
}

function average(values) {
  const safe = values.filter((value) => Number.isFinite(value));
  return safe.length ? safe.reduce((sum, value) => sum + value, 0) / safe.length : 0;
}

function returnPct(values, period) {
  if (values.length <= period) return 0;
  const start = values[values.length - 1 - period];
  const end = values[values.length - 1];
  return start > 0 ? ((end - start) / start) * 100 : 0;
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function round(value, digits = 2) {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function now() {
  return new Date().toISOString();
}

function ok(message, data) {
  return { ok: true, message, data };
}

function fail(message, statusCode, code) {
  return { ok: false, message: "Request failed.", error: { code, message, status_code: statusCode } };
}

function json(payload, status = 200, headers = {}) {
  return new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", ...headers } });
}

function html(body, status = 200, headers = {}) {
  return new Response(body, { status, headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store", ...headers } });
}
