# PROJECT_CONTEXT.md

조사 기준일: 2026-07-06. 아래 내용은 Fable이 실제 파일·명령 실행으로 확인한 사실이다. 추정은 Assumptions 섹션에 분리했다.

## What This Project Is

VCB-Alt는 "미국 주식 시장 전체에서 오늘 볼 만한 리서치 후보 종목을 골라주는" 결정지원 도구다. 사용자가 종목을 입력하지 않아도 시장 유니버스(최대 5,000 심볼)를 스캔 → 급등/추세 프리필터 → 상위 후보를 펀더멘털/뉴스/공매도/옵션 데이터로 보강 → 7개 종목 유형별 결정론적 점수화 → 포트폴리오 제약(최대 3종목, 노출 75% 상한 등)을 적용해 최종 후보 소수를 보여준다. 자동 매매·투자 자문이 아닌 "리서치 후보 제시"로 라벨링되어 있다(법적 이유).

두 가지 사용 형태:
1. **로컬 CLI + 로컬 웹 대시보드** (SQLite, 오프라인 sample 데이터 기본)
2. **Vercel 배포 SaaS 시험판** (`https://stockscreeningver10.vercel.app`, Neon PostgreSQL, 사용자별 인증/큐/워커) — 현재 소유자/운영자 전용

## Current Product State

**동작 확인됨 (2026-07-06 로컬 검증):**
- 82개 unittest 전부 통과, lint(44 files)/typecheck(428 objects)/compileall 통과
- CLI: init-db, watchlist 관리, evaluate, scan, select, benchmark, doctor, saas-readiness, admin 명령
- 웹: 대시보드, 티커 상세(5년 차트), 로그인, 법적 문서 페이지, EN/KO 토글, 반응형
- 프로바이더: sample(오프라인 기본)/manual CSV/yahoo EOD/stooq/alpaca(인트라데이)/finnhub(리서치)/SEC — 재시도·서킷브레이커·일일 budget 가드 포함
- SaaS 계층: 사용자 등록/로그인/세션, 테넌트 워치리스트, DB 레이트리밋, 스캔 잡 큐 + 워커, 감사 로그, export/delete API

**미완성 / 차단됨:**
- **핵심 차단**: 프로덕션 라이브 시장 스캔이 Alpaca `HTTP 401`(자격증명 불일치)로 실패. `/api/user/scan`은 fail-closed로 정확히 동작하지만, 결과적으로 배포판의 핵심 기능(시장 스캔)이 빈 상태다. → **Codex가 코드로 못 고침. 사용자가 Alpaca 키 재발급 필요.**
- 호스팅 1000-유저 워커 완료 부하테스트 미통과 (preflight까지만 성공)
- OAuth/MFA, 이메일 인증 없음 (자체 이메일+비밀번호만)
- Neon 백업/복원 드릴 미실행, 법률 검토 미완료
- **미커밋 작업 트리**: 13개 파일 +1,335/-97줄이 커밋되지 않은 채 방치 (마지막 커밋 2026-06-04, 문서상 2026-06-10 하드닝 작업으로 추정). 이 상태에서 작업 시작하면 안 됨.

## User Journey

1. 첫 접속 → 토큰 로그인(운영자 트라이얼) 또는 데모 세션 자동 생성(SaaS 모드) → 대시보드
2. 대시보드에서 "Scan full market" 클릭 → SaaS 모드에선 신선한 워커 스냅샷을 읽거나 202(대기) 반환 → 후보 테이블 렌더
3. "Selected research set"(최종 선정)과 "Monitor or excluded"(제외) 두 그룹으로 표시
4. 티커 클릭 → `/ticker/{SYMBOL}` 상세: 5년 차트, 섹터/산업, 점수 근거, 데이터 커버리지, 뉴스/공시/애널리스트 컨텍스트, 설명 요약(기본 template, 옵션 OpenAI)
5. 보조: 수동 워치리스트 서랍(주 발견 경로 아님), 운영 상태 패널(실패 이력, 준비 상태)

## Current Architecture

- 요청 흐름: Vercel rewrite(모든 경로) → `api/index.py` handler → `vcb_alt/web.py:route_request()` → 인증(`_is_authorized`) → 레이트리밋(`_allow_request`) → `handle_api()` 분기 → DB/프로바이더 → JSON/HTML 응답
- 정적 에셋: `_web_asset(name, fallback)`이 `vcb_alt/web_assets/{name}` 파일을 먼저 읽고, 없으면 web.py 안의 임베디드 상수 사용. **폴백 상수가 존재하는 이유: `pyproject.toml`에 package-data 설정이 없어 `pip install .` 시 web_assets가 패키지에 포함되지 않기 때문** (확인됨: `[tool.setuptools] packages = ["vcb_alt"]`만 존재)
- 서빙되는 JS는 응답 직전에 `_replace_js_ko_block()` 등으로 한국어 i18n 블록을 런타임 문자열 치환한다 — 과거 인코딩 손상의 우회책
- 프로덕션 스캔: 사용자 요청이 직접 프로바이더를 호출하지 않고, cron/워커(`/api/admin/run-worker`, vercel.json cron 일 1회)가 `market_scan_snapshots`에 durable 스냅샷을 기록

## Confirmed Files

| 파일 | 줄수 | 역할 |
| --- | --- | --- |
| `vcb_alt/web.py` | 4,854 | 웹 모놀리스. ~1,000줄 로직 + ~3,800줄 임베디드 폴백 HTML/JS/i18n 상수 |
| `vcb_alt/providers.py` | 1,472 | 전 데이터 프로바이더 |
| `vcb_alt/market_universe.py` | 778 | 유니버스 수집/프리필터 |
| `vcb_alt/job_queue.py` | 766 | 스캔 잡 큐/워커/스냅샷 |
| `vcb_alt/db.py` | 679 | SQLite/PostgreSQL 어댑터 + 스키마 |
| `vcb_alt/provider_resilience.py` | 483 | 재시도/서킷/budget |
| `vcb_alt/cli.py` | 475 | CLI 진입 |
| `vcb_alt/config.py` | 455 | AppConfig + env 로딩 |
| `vcb_alt/tenant_store.py` | 436 | 멀티테넌트 저장소 |
| `vcb_alt/scoring.py` | 326 | 7-archetype 점수 (건드리지 말 것) |
| `vcb_alt/portfolio.py` | 96 | 최종 선정 제약 (건드리지 말 것) |
| `vcb_alt/web_assets/app.js` | 893 | 대시보드 JS |
| `vcb_alt/web_assets/detail.js` | 497 | 상세 페이지 JS |
| `vcb_alt/web_assets/app.css` | 537 | 전체 스타일 |
| `vcb_alt/web_assets/index.html` | 190 | 대시보드 HTML |
| `api/index.py` | 71 | Vercel 어댑터 |
| `migrations/postgres/001_saas_core.sql` | - | PG 타깃 스키마 |

## Known Problems

심각도 순 (상세 근거는 FILE_CHANGE_MAP.md):

1. **[Critical/보안] 프로덕션 접근 토큰이 저장소 문서에 커밋됨.** `git grep vcb-beta-20260518` → `OPERATOR_TRIAL_GUIDE.md`, `PROVIDER_KEYS_SETUP.md`, `RELEASE_DECISION.md` 3개 파일에 라이브 URL과 함께 토큰 전문 노출.
2. **[Critical/제품] Alpaca 401로 프로덕션 핵심 기능(라이브 시장 스캔) 정지.** 코드 수정으로 해결 불가, 사용자 자격증명 재발급 필요.
3. **[High/안정성] 미커밋 1,335줄 작업 트리.** 리뷰·커밋 전에는 어떤 작업도 시작 불가.
4. **[High/유지보수] web.py 내 프론트엔드 이중 관리.** `web_assets/` 파일과 임베디드 상수가 같은 내용을 두 벌 유지. 이미 어긋남 발생: **`DETAIL_TEXT_JS`가 web.py 1858줄과 2571줄에 두 번 정의**되어 있고 내용이 미묘하게 다름(첫 번째는 완전한 데드코드, 두 번째가 silent하게 적용됨).
5. **[High/품질] push/PR 시 테스트를 돌리는 CI가 없음.** `.github/workflows/`엔 수동 부하테스트 워크플로 1개뿐.
6. **[Medium/유지보수] 런타임 JS 문자열 치환 i18n 핵** (`_replace_js_ko_block` 등) — 파일 자체를 고치면 불필요한 취약 구조.
7. **[Medium/구조] 루트 디렉터리 오염**: md 문서 40여 개 + 스크린샷 PNG 8개 + 로그/DB 파일이 루트와 트리에 산재. 신규 작업자가 권위 문서를 찾기 어려움.
8. **[Medium/배포] `pip install .` 시 web_assets 미포함** (package-data 미설정) — 폴백 상수 제거의 선행 조건.
9. **[Low] psycopg가 SQLite 전용 로컬 사용에도 필수 의존성** (선택적 extra가 적절).
10. **[Low] `.gitignore` 말미의 `.env*` 패턴이 `.env.example`도 매칭** (이미 추적 중이라 실해는 없으나 혼란 요소).

## Assumptions

**확인된 사실이 아닌 추정 (Codex는 작업 전 재확인할 것):**
- 미커밋 변경분 = 문서(RELEASE_DECISION.md 2026-06-10 항목)에 기술된 "프로덕션 하드닝 + web_assets 추출" 작업으로 추정. diff 위치가 문서 내용과 일치하나, 전체 리뷰는 안 됨.
- Vercel/Neon의 현재 라이브 상태(배포 살아있는지, 토큰 아직 유효한지)는 이 머신에서 미확인. **확인 필요.**
- `stooq` 프로바이더 실동작, OpenAI 요약 모드 실동작은 키가 없어 미검증. **확인 필요.**
- Vercel CLI 로그인 상태, `gh` CLI 가용 여부 미확인 (문서상 `gh` 없음). **확인 필요.**

## Do Not Break

- 82개 기존 테스트 전부
- fail-closed 스캔 동작 (라이브 데이터 없으면 후보 미제공, 샘플 폴백 금지)
- 결정론적 스코어링(`scoring.py`)과 포트폴리오 제약(`portfolio.py`)의 수치 결과
- 프로덕션 모드의 보안 강제: query-token 인증 off, worker POST 강제, JSON 바디 제한
- EN/KO 언어 토글과 중립 리서치 라벨(매매 지시 어감 금지)
- 로그 secret redaction
- CLI 명령 인터페이스(스크립트/문서가 의존)
