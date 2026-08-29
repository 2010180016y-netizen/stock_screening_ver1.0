# AGENTS.md

> **기록 문서 (2026-08 작업 완료).** 이 패키지는 재설계 착수 시점의 진단과 계획입니다.
> 이후 티켓 13개가 모두 수행되어 아래 내용 중 다수는 더 이상 현재 상태가 아닙니다.
> 현재 상태는 [../README.md](../README.md)와 [../RELEASE_DECISION.md](../RELEASE_DECISION.md)를 보세요.

## Project Mission

VCB-Alt는 미국 주식 시장 전체를 스캔해 7개 종목 유형(archetype) 기준으로 결정지원(decision-support) 후보 종목을 골라주는 개인용/운영자용 도구다. Python 3.11 표준 라이브러리 중심의 CLI + 토큰 보호 웹 대시보드로 구성되며, 로컬은 SQLite, 프로덕션(Vercel + Neon PostgreSQL)은 SaaS 시험 운영(operator trial) 단계다. 자동 매매는 하지 않으며, 현재 상태는 `public_launch_ready=false` — 소유자/운영자 시험용이다. 목표는 "실제 유저가 써도 어색하지 않은 프로덕션 수준"으로 안정화·정리하는 것이다.

## Non-Negotiable Rules

1. **대규모 전면 재작성 금지.** 이 코드베이스는 테스트 82개가 전부 통과하는 동작하는 시스템이다. 작은 단위로만 수정한다.
2. **수정 전 반드시 관련 파일을 먼저 읽는다.** 특히 `vcb_alt/web.py`(4,854줄)는 수정 지점 주변 ±100줄을 읽고 수정한다.
3. **모든 변경 후 검증 4종을 실행한다** (Important Commands 참조: unittest, lint, typecheck, compileall). 하나라도 실패하면 커밋하지 않는다.
4. **비밀키/.env/토큰 값을 출력·커밋하지 않는다.** 이 저장소는 이미 문서에 프로덕션 토큰이 노출된 이력이 있다 (Task 3 참조).
5. **스코어링/포트폴리오 로직(`scoring.py`, `portfolio.py`)은 UI/구조 개선을 이유로 변경하지 않는다.** 이 로직은 제품의 핵심이고 결정론적(deterministic)이어야 한다.
6. **fail-closed 동작을 절대 약화시키지 않는다.** 라이브 데이터가 없을 때 샘플 데이터를 후보로 추천하는 방향의 변경은 금지다 (`VCB_ALT_MARKET_SCAN_REQUIRES_LIVE_DATA` 관련 로직).
7. UI 수정 시 데스크톱과 모바일(375px), 한국어/영어 토글 상태를 모두 확인한다.
8. 에러/로딩/빈 상태(empty state)를 항상 함께 처리한다. 특히 스캔 API는 202(pending) 응답을 반환할 수 있다.
9. 임시 하드코딩 대신 `vcb_alt/config.py`의 `AppConfig` 필드 + `.env.example` 문서화로 관리한다.
10. 확신할 수 없는 내용은 추측하지 말고 코드에 `TODO(확인 필요):` 주석 또는 보고서에 "확인 필요"로 표시한다.
11. `web.py`의 임베디드 폴백 상수(`INDEX_HTML`, `APP_JS` 등)는 Task 7의 패키징 수정이 완료되기 전까지 삭제하지 않는다.

## Tech Stack

- Python 3.11+ (표준 라이브러리 중심: `http.server`, `sqlite3`, `argparse`, `unittest`)
- 외부 의존성: `psycopg[binary]` 하나뿐 (PostgreSQL 모드용)
- 프론트엔드: 프레임워크 없는 vanilla HTML/CSS/JS (`vcb_alt/web_assets/`), 빌드 단계 없음
- DB: SQLite(로컬) / Neon PostgreSQL(프로덕션) — `vcb_alt/db.py`가 양쪽 어댑터
- 배포: Vercel 서버리스 (`api/index.py`, `vercel.json`), Docker/Render 설정도 존재
- 테스트: `unittest` (tests/ 12개 파일, 82개 테스트), 자체 lint/typecheck 스크립트 (`tools/lint.py`, `tools/typecheck.py`)

## Important Commands

**인터프리터 (2026-07-06 Task 1에서 정정)**: 저장소 문서(README/SETUP 등)는 `C:\stable-diffusion-ui\installer_files\env\python.exe`를 쓰라고 안내하지만, **그 경로는 현재 존재하지 않는다**. 지금 PATH의 `python`이 3.11.9이며 검증에 사용된다.

```powershell
python --version   # Python 3.11.9 (C:\Users\a\AppData\Local\Programs\Python\Python311\python.exe)

# 테스트 (2026-07-06 검증: 82 tests OK, ~9초)
python -m unittest discover -s tests -v

# 린트 (검증: lint ok, 44 files)
python tools\lint.py

# 타입체크 (검증: type hints ok, 428 objects)
python tools\typecheck.py

# 빌드 검증 (프론트 번들 없음, 바이트코드 컴파일이 빌드 검증)
python -m compileall vcb_alt tests tools api

# 로컬 DB 초기화 + 웹 실행
python -m vcb_alt init-db --seed
python -m vcb_alt web --host 127.0.0.1 --port 8765

# 설정 진단 / SaaS 준비상태
python -m vcb_alt doctor
python -m vcb_alt saas-readiness
```

주의: PowerShell에서 `A && B`는 문법 오류다. `A; if ($?) { B }`를 쓴다.

배포: `vercel deploy` — 확인 필요(이 머신에서 Vercel CLI 로그인 상태 미확인). 배포는 사용자 승인 없이 실행하지 않는다.

## Architecture Overview

- **진입점**: CLI는 `vcb_alt/__main__.py` → `cli.py`. 웹은 `cli.py`의 `web` 커맨드 → `web.py:run_web()`. Vercel은 `api/index.py`가 모든 경로를 받아 `web.py:route_request()`로 위임 (`vercel.json`의 rewrite).
- **웹 계층**: `web.py`가 라우팅·인증·레이트리밋·API 핸들러·에셋 서빙·임베디드 폴백 HTML/JS를 전부 담고 있는 모놀리스(4,854줄). 정적 파일은 `web_assets/` 파일 우선, 파일이 없으면 임베디드 상수 폴백 (`_web_asset()`).
- **데이터 파이프라인**: `market_universe.py`(유니버스 수집/프리필터) → `providers.py`(yahoo/stooq/alpaca/finnhub/sec/manual/sample) → `scoring.py`(7 archetype 점수) → `portfolio.py`(최종 선정 제약). 회복탄력성은 `provider_resilience.py`(재시도/서킷브레이커/일일 budget).
- **SaaS 계층**: `tenant_store.py`(멀티테넌트 사용자/세션/워치리스트), `job_queue.py`(스캔 잡 큐 + 워커), `rate_limit.py`, `auth.py`. 프로덕션은 워커가 `market_scan_snapshots`에 스냅샷을 쓰고, 사용자 스캔 요청은 신선한 스냅샷을 읽거나 202를 반환한다.
- **DB 스키마**: SQLite는 `db.py`의 `init_db()`, PostgreSQL 타깃 스키마는 `migrations/postgres/001_saas_core.sql`.

## Key Directories

| 디렉터리/파일 | 역할 |
| --- | --- |
| `vcb_alt/` | 애플리케이션 패키지 전체 |
| `vcb_alt/web.py` | 웹 서버 모놀리스 (라우팅+API+인증+임베디드 프론트 폴백) |
| `vcb_alt/web_assets/` | 실제 서빙되는 HTML/CSS/JS (파일 우선 로딩) |
| `api/index.py` | Vercel 서버리스 어댑터 |
| `migrations/postgres/` | PostgreSQL 타깃 스키마 |
| `tests/` | unittest 스위트 (82개) |
| `tools/` | lint/typecheck/부하테스트 스크립트 |
| `data/` | 예제 CSV, 시장 캐시, 로컬 DB (대부분 gitignore) |
| 루트 `*.md` (40여 개) | 설계/운영/QA 문서. `README.md`, `RELEASE_DECISION.md`, `QA_REPORT.md`가 최신·권위 문서 |

## Coding Conventions

- 모든 모듈 첫 줄 `from __future__ import annotations`, 전 함수 타입 힌트 필수 (`tools/typecheck.py`가 검사).
- 표준 라이브러리 우선. 새 외부 패키지 추가는 사용자 승인 필요.
- snake_case 함수, 모듈 내부 전용 함수는 `_` 접두사.
- 환경변수는 전부 `VCB_ALT_` 접두사, `config.py`의 `AppConfig` dataclass 필드로 매핑, `.env.example`에 주석과 함께 문서화.
- 에러는 `errors.py`의 예외 계층 사용. 로그는 `logging_utils.py` (secret redaction 내장).
- JS는 빌드 없는 ES2020, `data-i18n` 속성 기반 수동 i18n (EN/KO).

## UI/UX Rules

- 대시보드의 1순위 행동은 "시장 전체 스캔"(`#scan-button`). 워치리스트는 보조 리서치 서랍이며 절대 주 발견 경로처럼 보이게 하지 않는다.
- 모든 비동기 액션: 버튼 disabled + 진행 표시 + 성공/실패/pending(202) 메시지 3종 처리.
- 한국어/영어 토글이 모든 신규 문자열에 적용되어야 한다 (`I18N` 객체에 EN/KO 쌍 추가).
- 매매 지시 어감 금지: "매수/매도" 대신 "리서치 후보", "검토 대상" 등 중립 라벨 유지 (법적 요구사항).
- 반응형: 기존 CSS는 미디어쿼리 기반. 375px 모바일에서 가로 스크롤이 생기면 안 된다.
- 파일 인코딩: `web_assets/*`는 반드시 UTF-8(BOM 없이). 이 프로젝트는 한국어 인코딩 손상 이력이 있다.

## Security Rules

- `.env`, 실제 토큰, API 키를 코드·문서·로그·커밋 메시지에 절대 쓰지 않는다. 문서 예시는 `replace-with-...` 플레이스홀더만.
- 프로덕션 모드는 query-string 토큰 인증이 강제로 꺼진다 — 이 동작을 되돌리지 않는다.
- `X-Forwarded-For`는 `trusted_proxy_headers=true`일 때만 신뢰 — 유지.
- JSON 바디는 `max_json_body_bytes` 제한 — 유지.
- 로깅은 `logging_utils.py`의 redaction을 거친다 — 새 로그 추가 시에도 준수.

## Testing Rules

- 모든 코드 변경 후: `unittest` + `lint.py` + `typecheck.py` + `compileall` 4종 통과 확인.
- 웹/API 변경 시: 로컬 웹 서버를 띄워 대시보드 로딩, 스캔 버튼, 티커 상세 페이지(`/ticker/AAPL`)를 수동 확인.
- JS 변경 시: 브라우저 콘솔 에러 0건 확인, EN/KO 토글 양쪽 확인.
- 새 기능에는 `tests/`에 최소 1개 테스트 추가.
- 프로덕션 SaaS 경로(PostgreSQL)는 로컬에서 검증 불가 — "확인 필요"로 보고하고 배포 전 사용자에게 알린다.

## Definition of Done

작업 하나가 완료되었다고 판단하는 기준:

1. 검증 4종(unittest/lint/typecheck/compileall) 전부 통과.
2. 해당 Task의 Acceptance criteria 전 항목 충족.
3. 기존 82개 테스트가 깨지지 않음 (수 감소 금지, 의도적 삭제는 보고).
4. UI 변경이면 데스크톱+모바일+EN/KO 수동 확인 완료.
5. 변경 파일 목록, 검증 결과, 남은 리스크를 사용자에게 보고.
6. 커밋 메시지가 변경 내용을 정확히 설명 (한 Task = 한 커밋 원칙).
