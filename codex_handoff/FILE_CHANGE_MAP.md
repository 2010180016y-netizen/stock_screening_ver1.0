# FILE_CHANGE_MAP.md

> **기록 문서 (2026-08 작업 완료).** 이 패키지는 재설계 착수 시점의 진단과 계획입니다.
> 이후 티켓 13개가 모두 수행되어 아래 내용 중 다수는 더 이상 현재 상태가 아닙니다.
> 현재 상태는 [../README.md](../README.md)와 [../RELEASE_DECISION.md](../RELEASE_DECISION.md)를 보세요.

분류: **반드시 수정** / **수정 권장** / **읽기만** / **금지(건드리지 말 것)** / **확인 필요**

| 파일/디렉터리 | 현재 역할 | 문제점 | 권장 변경 | 관련 Task | 위험도 | 검증 방법 |
| --- | --- | --- | --- | --- | --- | --- |
| (git working tree) | 미커밋 +1,335/-97줄 (13개 파일) | 한 달간 방치, 롤백 기준선 없음 | 리뷰 후 기준선 커밋 **[반드시 수정]** | T1 | 낮음 | 검증 4종 + git log |
| `vcb_alt/web.py` | 웹 모놀리스 4,854줄 | ①`DETAIL_TEXT_JS` 중복 정의(1858, 2571행) ②임베디드 프론트 폴백 ~3,000줄 이중 관리 ③런타임 JS 치환 핵 ④단일 파일 과대 | 중복 제거 → i18n 핵 제거 → 폴백 삭제 → 모듈 분리 (반드시 이 순서, 커밋 소분할) **[반드시 수정]** | T2, T6, T7, T8 | **높음** | 검증 4종 + 웹 스모크 + `_detail_js()` 길이 비교 |
| `OPERATOR_TRIAL_GUIDE.md`, `PROVIDER_KEYS_SETUP.md`, `RELEASE_DECISION.md` | 운영/키/릴리스 문서 | 프로덕션 접근 토큰 평문 커밋 | 토큰 플레이스홀더 치환 **[반드시 수정]** | T3 | 낮음 | `git grep vcb-beta` 0건 |
| `.github/workflows/` | 수동 부하테스트 1개 | push CI 부재 | `ci.yml` 신규 **[반드시 수정]** | T4 | 낮음 | GitHub Actions 그린(사용자 확인) |
| `vcb_alt/web_assets/app.js` | 대시보드 JS 893줄 | 202 대기 UX 불명확(추정), i18n은 서빙 시 치환에 의존 | 폴링 UX + I18N 자체 완결 **[반드시 수정]** | T5, T6, T10, T12 | 중간 | 브라우저 수동(EN/KO/모바일) + 콘솔 0에러 |
| `vcb_alt/web_assets/detail.js` | 상세 페이지 JS | 서빙 시 `detailText` 치환 의존 | 파일 자체 완결화 **[반드시 수정]** | T6 | 중간 | `/ticker/AAPL` KO 확인 |
| `vcb_alt/web_assets/index.html`, `app.css`, `detail.html` | 대시보드/상세 마크업·스타일 | 빈 상태 카피, 스켈레톤 부재 | 폴리시 **[수정 권장]** | T5, T10, T12 | 낮음 | 수동 QA 시나리오 |
| `pyproject.toml` | 패키징 설정 | package-data 미설정 → pip 설치 시 web_assets 누락, psycopg 강제 | package-data 추가(7a), psycopg extra화 **[반드시 수정]** | T7, T11 | 중간 | pip --target 설치 스모크 |
| `requirements.txt` | Vercel 의존성 | 없음 | psycopg 라인 **유지** **[금지에 준함]** | T11 | 높음(배포) | 프로덕션 health |
| `api/index.py` | Vercel 어댑터 | 없음 (양호) | 무변경 목표 **[읽기만]** | T7, T8 | 높음(배포) | 배포 후 `/api/health` |
| `vercel.json` | rewrite + 일일 cron | 없음 | **[금지]** | - | 높음 | - |
| `vcb_alt/scoring.py`, `vcb_alt/portfolio.py` | 결정론적 점수/선정 | 없음 | **[금지]** — 제품 핵심, 수치 결과 불변 | - | 치명 | 기존 테스트 |
| `vcb_alt/job_queue.py` | 스캔 큐/워커/스냅샷 | 없음(로컬 1000잡 검증 이력) | **[읽기만]** (T5에서 상태 스키마 참조) | T5 | 높음 | 기존 테스트 |
| `vcb_alt/db.py` | SQLite/PG 어댑터 | psycopg import 방식 확인 필요 | 지연 import 에러 메시지만 **[수정 권장]** | T11 | 중간 | 검증 4종 |
| `vcb_alt/config.py` | AppConfig/env | 없음 (양호) | 신규 설정 추가 시에만 **[읽기만]** | - | 중간 | 검증 4종 |
| `vcb_alt/providers.py`, `provider_resilience.py`, `market_universe.py` | 데이터 계층 | 없음(잘 구성됨) | **[읽기만]** | T10 | 높음 | 기존 테스트 |
| `vcb_alt/tenant_store.py`, `auth.py`, `rate_limit.py` | SaaS 계층 | OAuth/MFA 부재(장기 과제, 이번 범위 아님) | **[읽기만]** | - | 높음 | 기존 테스트 |
| `tests/` | 82개 테스트 | CI 미연결 | 신규 기능 테스트 추가 **[수정 권장]** | 전체 | 낮음 | unittest |
| 루트 `*.md` 40여 개 | 설계/운영 문서 | 루트 오염, 상호 모순(시점별) | docs/ 이동 + 링크 갱신 **[수정 권장]** | T9 | 낮음 | 링크 grep |
| 루트 `*.png` 8개, `logs/`, `data/*.db`, `.playwright-mcp/` | 세션 산출물 | 트리 오염(대부분 gitignore됨) | 추적분만 `git rm --cached` **[수정 권장]** | T9 | 낮음 | git status |
| `data/hosted_scan_heavy_1000_*.json` | 부하테스트 증적 (커밋됨) | 비밀 미포함 확인됨 | 유지 **[읽기만]** | - | 낮음 | - |
| `migrations/postgres/001_saas_core.sql` | PG 타깃 스키마 | 마이그레이션 러너/버저닝 부재(장기) | **[금지]** — DB 변경은 이번 범위 아님 | - | 치명 | - |
| `Dockerfile`, `render.yaml`, `deploy/` | 대체 배포 경로 | 사용 여부 불명 | **[확인 필요]** — 사용자에게 Render/Docker 실사용 여부 질문 | - | 낮음 | - |
| `.env` (존재 시), Vercel/Neon 환경변수 | 실 비밀 | 노출 토큰 회전 필요 | **[금지]** — 사용자 전담 | T3 | 치명 | 사용자 확인 |
