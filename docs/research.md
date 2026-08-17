# VCB-Alt Deep Research Report

작성일: 2026-05-17 KST

## 1. 한 줄 정의

VCB-Alt는 단일 운영자가 미국 주식 watchlist를 관리하고, 샘플/수동/자동 EOD 시장데이터를 기반으로 종목을 평가한 뒤, 후보 종목을 선별하고 운영 로그를 남기는 Python 표준 라이브러리 기반 의사결정 보조 시스템이다.

## 2. 현재 제품 상태

현재 제품은 세 가지 사용 표면을 가진다.

1. CLI: `python -m vcb_alt ...`
2. 로컬/토큰 보호 웹 대시보드: `python -m vcb_alt web`
3. JSON API: 웹 대시보드가 호출하는 `/api/*` 엔드포인트

현재 구현은 공개 SaaS라기보다 controlled private beta 또는 shared-token public demo에 가깝다. 다중 사용자 계정, 테넌트 격리, PostgreSQL, 결제, 법무 검토, 운영 관측성은 아직 없다.

## 3. 기술 스택과 런타임

- 언어: Python 3.11+
- 런타임 의존성: Python standard library only
- DB: SQLite
- CLI: `argparse`
- 웹 서버: `http.server.ThreadingHTTPServer`
- 테스트: `unittest`
- 빌드 검증: `compileall`
- 타입 힌트 검증: `tools/typecheck.py`
- 린트: `tools/lint.py`
- 배포 준비물: `Dockerfile`, `render.yaml`

`requirements.txt`에는 서드파티 패키지가 없다. 이는 설치 안정성에는 유리하지만, 공개 웹서비스 수준의 인증, 라우팅, 마이그레이션, ORM, 테스트 서버 기능은 직접 구현하거나 향후 프레임워크를 도입해야 한다는 뜻이다.

## 4. 파일 구조

핵심 애플리케이션 코드는 `vcb_alt/`에 있다.

- `__main__.py`: `python -m vcb_alt` 진입점.
- `__init__.py`: 패키지 버전.
- `cli.py`: CLI parser, command dispatch, CLI 출력 포맷.
- `web.py`: HTTP 서버, HTML/CSS/JS, API router, public token gate.
- `config.py`: `.env`와 환경변수 로딩, 안전 기본값, config validation.
- `db.py`: SQLite 연결, 스키마, watchlist/evaluation/log/failure CRUD.
- `providers.py`: sample/manual/yahoo/stooq data provider, market bar parsing, cache.
- `models.py`: dataclass 모델과 archetype 상수.
- `scoring.py`: archetype scoring, technical momentum scoring, evaluation 생성.
- `portfolio.py`: 후보 정렬, 포지션 한도, 중복 archetype 제한.
- `sample_data.py`: deterministic sample snapshots.
- `validation.py`: ticker, percentage, positive number, destructive confirmation validation.
- `errors.py`: public-safe exception hierarchy.
- `logging_utils.py`: file log append, UTC timestamp.
- `security.py`: secret redaction.
- `performance.py`: scoring benchmark.
- `saas_readiness.py`: 1000-user SaaS blocker report.

테스트는 `tests/`에 있고, 현재 validation, DB, CLI, provider, scoring, portfolio, web, SaaS readiness를 검증한다.

## 5. 실행 흐름

### 5.1 CLI 진입

`python -m vcb_alt`는 `vcb_alt/__main__.py`에서 `cli.main()`을 호출한다.

`cli.main()` 흐름:

1. `build_parser()`로 command/subcommand parser 구성.
2. 인자가 없으면 help 출력 후 종료.
3. `dispatch(args)` 실행.
4. `AppError`는 `OperationResult.failure(...)`로 변환.
5. 예상하지 못한 예외도 public-safe error로 감싸고 `_capture_failure(...)` 호출.
6. `print_result(...)`가 JSON 또는 사람이 읽는 CLI 출력으로 변환.
7. 성공이면 exit code `0`, 실패면 `1`.

### 5.2 Config 로딩

`load_config()`는 다음 우선순위로 값을 읽는다.

1. `VCB_ALT_*` 환경변수
2. `.env` 안의 `VCB_ALT_*`
3. unprefixed 환경변수
4. `.env` 안의 unprefixed key
5. 코드 기본값

중요 validation:

- SQLite URL만 지원한다.
- `sample`, `manual`이 아닌 provider는 `VCB_ALT_EXTERNAL_API_ENABLED=true`가 필요하다.
- public web mode는 16자 이상 `VCB_ALT_WEB_ACCESS_TOKEN`이 필요하다.
- market data timeout/cache TTL은 양수여야 한다.

### 5.3 DB 초기화

`init_db(conn)`은 `SCHEMA_SQL`을 실행한다.

현재 테이블:

- `watchlist`
- `evaluations`
- `operation_logs`
- `failed_jobs`

현재 인덱스:

- `idx_evaluations_ticker_time` on `(ticker, evaluated_at DESC)`
- `idx_operation_logs_time` on `(created_at DESC)`
- `idx_failed_jobs_time` on `(created_at DESC)`

주의: `watchlist`는 `ticker TEXT PRIMARY KEY`이고 `ORDER BY ticker`로 조회된다. 운영 로그와 실패 목록은 `ORDER BY id DESC LIMIT ?`로 조회되며 현재 offset/cursor 개념은 없다.

## 6. 데이터 모델

### 6.1 OperationResult

모든 주요 command/API 응답은 같은 envelope을 따른다.

- `ok`
- `status_code`
- `message`
- `data`
- `error`

이 구조는 CLI와 웹 API 사이에서 일관된 성공/실패 처리를 가능하게 한다.

### 6.2 StockSnapshot

`StockSnapshot`은 종목 평가의 입력 모델이다. 크게 네 종류의 필드를 담는다.

1. 회사/가격 기본값: `ticker`, `company_name`, `price`
2. fundamental/catalyst 성격의 수동 지표: revenue surprise, insider purchase activity, short interest 등
3. market-derived 지표: return, drawdown, moving average distance, trend score, surge score
4. source metadata: `source`, `data_as_of`, `data_quality`

자동 provider는 price/volume 기반 지표만 채운다. fundamentals, news, options, short interest는 자동화되어 있지 않다.

### 6.3 EvaluationResult

`EvaluationResult`는 scoring 결과다.

- primary archetype
- archetype별 점수
- complexity modifier
- combined score
- setup strength
- can enter 여부
- suggested size
- stop loss
- rationale/warnings/precision notes

### 6.4 PortfolioSelection

`PortfolioSelection`은 최종 선별 결과다.

- selected
- rejected
- max positions
- max total size
- total selected size
- data provider

## 7. Provider 시스템

`providers.get_snapshot(config, ticker)`가 모든 provider의 단일 진입점이다.

### 7.1 sample provider

`sample_data.py`에 하드코딩된 deterministic snapshot을 반환한다.

특징:

- 네트워크 없음
- 빠르고 테스트 친화적
- 알려진 tickers: `PLTR`, `MSTR`, `RGTI`, `SMMT`, `VST`, `GME`, `AAPL`
- 알 수 없는 ticker는 deterministic placeholder 생성

### 7.2 manual provider

`data/snapshots.csv`를 읽는다.

특징:

- `data/snapshots.example.csv` header와 `StockSnapshot` field set을 맞춘다.
- 알 수 없는 컬럼이 있으면 `ValidationError`.
- 누락 numeric field는 `0.0`.
- 누락 bool field는 false.
- ticker는 `validate_ticker()`로 정규화된다.

### 7.3 yahoo provider

`https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1y&interval=1d` 형식의 chart JSON을 가져온다.

특징:

- `VCB_ALT_EXTERNAL_API_ENABLED=true` 필요.
- cache path: `data/market_cache/yahoo/v1/{ticker}.json`
- cache TTL: `VCB_ALT_MARKET_DATA_CACHE_TTL_HOURS`
- timeout: `VCB_ALT_MARKET_DATA_TIMEOUT_SECONDS`
- OHLCV 배열을 `MarketBar` 리스트로 변환.
- benchmark로 `SPY`도 가져와 12주 상대강도 계산.

### 7.4 stooq provider

Stooq CSV endpoint를 지원하지만, 일부 다운로드는 API key/captcha 안내 페이지를 반환한다.

특징:

- cache path: `data/market_cache/stooq/v1/{ticker}.csv`
- `VCB_ALT_STOOQ_API_KEY`를 지원한다.
- API key/captcha 안내 페이지가 오면 sample로 조용히 fallback하지 않고 명확한 `NotFoundError`를 반환한다.

### 7.5 Market-derived metrics

`build_snapshot_from_bars()`는 OHLCV에서 다음을 계산한다.

- latest close
- SMA 50/150/200
- prior SMA200
- 52-week high/low
- 50-day average volume
- breakout volume ratio
- volume z-score
- 12-week return
- 12-month return
- SPY 대비 12-week relative strength
- 52-week drawdown/recovery
- price vs 50/150/200 DMA
- trend template score
- surge score
- risk/reward ratio
- data quality

## 8. Scoring 시스템

`scoring.py`는 7개 archetype을 평가한다.

1. `A_AI_TECH`
2. `B_CRYPTO_PIVOT`
3. `C_QUANTUM`
4. `D_BIOTECH`
5. `E_SHORT_SQUEEZE`
6. `F_PICK_SHOVEL`
7. `G_TECHNICAL_MOMENTUM`

기존 6개 archetype은 fundamental/catalyst/manual field 영향을 많이 받는다. 자동 provider만 사용할 때 모든 점수가 낮아지는 문제를 막기 위해 `G_TECHNICAL_MOMENTUM`이 추가되어 price/volume-only 데이터만으로도 후보를 산출한다.

### 8.1 Technical Momentum

조건:

- source가 `stooq` 또는 `yahoo`
- stale data는 0점 처리
- trend template score 45%
- surge score 25%
- 12-week return threshold
- SPY 대비 relative strength
- price vs 50DMA
- 52-week drawdown proximity

### 8.2 Entry threshold

- combined score >= 55: can enter
- score >= 70: `STRONG_SETUP`
- score >= 50: `SETUP`
- else: `NO_SETUP`

### 8.3 Position sizing

각 archetype에는 cap이 있다. 점수가 높을수록 cap에 가까워진다.

`G_TECHNICAL_MOMENTUM` cap은 18%다.

## 9. Portfolio selection

`select_portfolio()`는 다음 순서로 후보를 정렬한다.

1. combined score
2. high-volatility archetype이 아닌 후보 우선
3. suggested size

제약:

- max positions 기본 3
- max total size 기본 75%
- high-volatility archetype은 기본 1개
- primary archetype 중복 회피

예외:

- `G_TECHNICAL_MOMENTUM`은 `ARCHETYPE_DIVERSIFICATION_EXEMPT`에 들어 있다.
- 이유: 자동 price/volume provider에서는 후보가 모두 Technical Momentum으로 수렴할 수 있으므로, 이 archetype만 중복 제한을 적용하지 않는다.

## 10. 웹 시스템

`web.py`는 Python 표준 라이브러리 `ThreadingHTTPServer` 기반이다.

### 10.1 서버 시작

`run_web(host, port)`:

1. config 로딩
2. DB init
3. `auto_seed_sample`이 true이고 watchlist가 비어 있으면 sample tickers seed
4. handler factory 생성
5. `ThreadingHTTPServer` 시작

### 10.2 Public token gate

public mode 조건:

- `VCB_ALT_PUBLIC_WEB_ENABLED=true`
- `VCB_ALT_WEB_ACCESS_TOKEN` 16자 이상

인증 허용 방식:

- query string: `?token=...`
- Authorization header: `Bearer ...`
- cookie: `vcb_alt_token`

`/api/health`는 public mode에서도 열린다. 나머지 API와 `/`는 token이 필요하다. query token이 맞으면 HTTP-only, SameSite=Lax cookie를 설정한다.

### 10.3 API endpoints

- `GET /api/health`
- `GET /api/config`
- `GET /api/saas-readiness`
- `GET /api/watchlist`
- `POST /api/watchlist`
- `DELETE /api/watchlist?ticker=...`
- `GET /api/scan`
- `GET /api/select`
- `GET /api/logs`
- `GET /api/failures`

현재 list endpoint들은 paging input이 없다. `logs`와 `failures`는 내부적으로 fixed limit `12`를 사용한다. CLI admin logs/failures는 `--limit`만 받는다.

### 10.4 Frontend

HTML/CSS/JS는 모두 `web.py` 문자열 상수다.

Frontend behavior:

- first load: config/watchlist/ops load
- then scan
- then final selection
- add/remove ticker
- loading state: all buttons disabled, runtime text changes
- empty/error/success state: notice and table/panel content 변경

프론트엔드는 별도 빌드가 없다. 따라서 배포 단순성은 높지만, UI가 커지면 `web.py`가 커지는 문제가 있다.

## 11. CLI commands

주요 command:

- `init-db`
- `doctor`
- `watchlist add/remove/list/seed`
- `evaluate`
- `scan`
- `select`
- `morning`
- `weekly`
- `admin logs/failures/export/delete-data`
- `self-test`
- `saas-readiness`
- `benchmark`
- `web`

`scan --limit`은 리스트 전체 중 앞 N개만 잘라 평가한다. 이 역시 offset/cursor가 아니고 단순 slicing이다.

## 12. Error handling

Exception hierarchy:

- `AppError`: 500
- `ValidationError`: 400
- `UnauthorizedError`: 401
- `ForbiddenError`: 403
- `NotFoundError`: 404
- `ConflictError`: 409
- `RateLimitError`: 429

Provider/network/validation failure는 API나 CLI에서 envelope으로 변환된다. Watchlist batch evaluation 중 한 ticker가 실패하면 전체 scan이 죽지 않고 `failed_jobs`에 기록한다.

## 13. Security and privacy

현재 적용된 보안:

- secret redaction: key 이름에 `KEY`, `TOKEN`, `SECRET`, `PASSWORD`, `PASS` 포함 시 redact
- long token-looking string redaction
- public web token gate
- destructive delete confirmation
- external provider explicit opt-in
- no auto trading
- no payment/personal data collection

현재 부족한 보안:

- user-specific auth 없음
- RBAC 없음
- CSRF 방어 없음
- rate limiting 없음
- TLS termination 없음
- real audit trail 없음
- tenant isolation 없음

## 14. Operations

운영자가 볼 수 있는 정보:

- operation logs
- failed jobs
- selection output
- provider failures
- SaaS readiness blockers

`logs/app.log`는 일부 CLI 작업에서 append된다. DB operation logs와 file logs가 완전히 동일한 이벤트를 담지는 않는다.

## 15. Test coverage

현재 테스트 범위:

- validation: ticker/numeric/delete confirmation
- scoring: sample scoring, score bounds, placeholder behavior
- DB: watchlist, evaluation save, redacted logs, export/delete
- CLI: init/seed/scan/logs/select/missing DB/invalid ticker
- provider: manual CSV, Stooq cache, Yahoo cache, technical momentum
- portfolio: position/high-vol limits, technical momentum multi-slot
- web: scan/select API, benchmark, public token guard
- SaaS readiness: public SaaS blocker state

현재 테스트 부족:

- live provider contract test는 CI에 없음
- web server full HTTP integration test는 제한적
- browser visual regression 없음
- pagination 관련 테스트 없음
- large table data volume test 없음

## 16. Performance

최근 QA 기준:

- 7000 evaluations
- 189.48 ms
- 약 36,943 eval/s
- 약 0.0271 ms/evaluation

이 benchmark는 provider fetch를 제외한 cached/sample scoring 중심이다. 실제 provider fetch가 포함되면 네트워크와 cache TTL에 따라 지연이 커진다.

## 17. 현재 리스트와 페이징 상태

현재 리스트성 함수:

- `list_watchlist(conn)`: 모든 watchlist row 반환, `ORDER BY ticker`.
- `recent_logs(conn, limit=20)`: `ORDER BY id DESC LIMIT ?`.
- `recent_failures(conn, limit=20)`: `ORDER BY id DESC LIMIT ?`.
- `export_data(conn)`: 전체 테이블 export.
- CLI `scan --limit`: watchlist list를 가져온 후 Python slicing.
- Web `/api/logs`: fixed limit 12.
- Web `/api/failures`: fixed limit 12.
- Web `/api/watchlist`: 전체 반환.

현재 문제:

- offset paging은 구현되어 있지 않지만, list APIs가 limit-only라 대규모 데이터에서 페이지 이동이 불가능하다.
- 앞으로 offset paging을 추가하면 SQLite에서 큰 offset일수록 느려지고, 동시 insert/delete 시 중복/누락 가능성이 생긴다.
- 따라서 새 기능 00은 offset이 아니라 input-based keyset/cursor paging으로 설계해야 한다.

## 18. 1000-user 관점의 시스템 한계

현재 제품은 단일 operator 또는 controlled demo에는 동작한다. 하지만 1000-user 공개 웹서비스에는 다음이 필요하다.

- managed PostgreSQL
- user/tenant schema
- auth/session/MFA/RBAC
- provider quota/circuit breaker
- background worker queue
- centralized logs/metrics/tracing
- legal-reviewed Terms/Privacy/Risk disclosure
- load/security tests
- deployment backup/restore procedure

## 19. 위험 요약

P0/P1 위험:

- token gate가 real auth처럼 오해될 수 있음
- SQLite가 public SaaS persistence로 오해될 수 있음
- Yahoo/Stooq 데이터가 licensed production feed로 오해될 수 있음
- price/volume-only scoring이 fundamentals/catalysts를 포함한 정밀 scoring으로 오해될 수 있음

운영 문서가 이 경계를 계속 명확히 말해야 한다.

## 20. 결론

VCB-Alt는 현재 기준으로 runnable, testable, locally operable한 stock screening decision-support tool이다. 자동 market data와 technical momentum scoring이 추가되어 실제 종목 산출까지 가능해졌다. 다음 구조 개선 우선순위는 list APIs의 input-based paging, auth/tenant 모델, provider reliability, 그리고 production database 전환이다.
