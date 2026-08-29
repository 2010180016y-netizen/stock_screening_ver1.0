# RISK_AND_ROLLBACK.md

> **기록 문서 (2026-08 작업 완료).** 이 패키지는 재설계 착수 시점의 진단과 계획입니다.
> 이후 티켓 13개가 모두 수행되어 아래 내용 중 다수는 더 이상 현재 상태가 아닙니다.
> 현재 상태는 [../README.md](../README.md)와 [../RELEASE_DECISION.md](../RELEASE_DECISION.md)를 보세요.

## High Risk Areas

| 영역 | 왜 위험한가 | 취급 원칙 |
| --- | --- | --- |
| `vcb_alt/web.py` | 4,854줄 모놀리스. 라우팅·인증·레이트리밋·API·에셋이 얽혀 있고, 임베디드 상수와 파일이 이중 관리됨 | 커밋 소분할, 수정 지점 ±100줄 정독, 매 커밋 검증 4종 |
| `vcb_alt/scoring.py`, `portfolio.py` | 제품의 핵심 결정 로직. 수치가 바뀌면 "추천이 달라지는" 사고 | **수정 금지.** 리팩토링 대상에서도 제외 |
| `api/index.py`, `vercel.json`, `requirements.txt` | 프로덕션 배포 경로. 로컬에서 완전 검증 불가 | 원칙적으로 무변경. 변경 시 사용자에게 배포 스모크 필요 고지 |
| `migrations/postgres/001_saas_core.sql`, `db.py`의 스키마 | 프로덕션 Neon PostgreSQL이 이 스키마로 운영 중 | **이번 범위에서 스키마 변경 금지** |
| `web_assets/*` 인코딩 | 한국어 인코딩 손상 이력 있음 | UTF-8(BOM 없음) 보장, PowerShell `Out-File` 기본 인코딩(UTF-16) 사용 금지 |
| fail-closed 스캔 로직 | 약화 시 샘플 데이터를 실제 후보처럼 추천 → 신뢰/법적 사고 | 관련 조건문 수정 금지 |
| 보안 강제(프로덕션 query-token off, worker POST, JSON 바디 제한) | 완화 시 공개 접근 경로 부활 | 수정 금지 |

## Safe Change Strategy

1. **Task 1(기준선 커밋)이 모든 작업의 선행 조건.** 미커밋 트리 위에서 작업 시작 금지.
2. 작업 전 브랜치 생성: `git checkout -b codex/task-N-짧은설명`. main 직접 커밋 금지.
3. 한 Task = 한 브랜치 = 1~수 개의 작은 커밋. 커밋마다 검증 4종.
4. 순서 의존 준수: T2(중복 제거) → T6(i18n 핵) → T7a(패키징) → T7b(폴백 삭제) → T8(모듈 분리). 순서를 건너뛰면 폴백 경로가 깨진다.
5. 서빙 결과 비교 기법: 프론트 관련 수정 전후로 `/assets/app.js`, `/assets/detail.js`, `/` 응답을 파일로 덤프해 diff. "의도한 차이만 있는가"를 확인.
6. 로컬에서 검증 불가한 것(PostgreSQL 모드, Vercel 런타임)은 추측으로 통과 처리하지 말고 보고서에 "확인 필요 — 배포 스모크 요망"으로 남긴다.

## Rollback Plan

- 커밋 단위 롤백: `git revert <sha>` (히스토리 보존 방식 우선. `reset --hard`는 사용자 지시 없이 금지)
- Task 단위 롤백: 해당 브랜치 폐기 또는 merge 커밋 revert
- 프로덕션 롤백: Vercel 대시보드에서 이전 배포(deployment)로 "Promote to Production" — 사용자가 수행. Codex는 배포를 직접 실행하지 않는다.
- DB 롤백: 이번 범위에 스키마 변경이 없으므로 해당 없음. 만약 스키마 변경이 필요해지면 작업 중단 후 사용자 승인 요청.

## Migration Risks

이번 재설계 범위에는 DB 마이그레이션이 **없다**. 주의할 잠재 지점:
- `db.py:init_db()`는 부팅 시 idempotent DDL을 실행한다. 여기에 컬럼 추가 등을 끼워 넣지 말 것 — 프로덕션 Neon에 즉시 반영되는 경로다.
- Neon 백업/복원 드릴이 미실행 상태다(`NEON_BACKUP_RESTORE_DRILL.md`). 스키마를 건드리는 어떤 미래 작업도 이 드릴 완료가 선행 조건이다.

## Security Risks

1. **노출 토큰(최우선)**: `vcb-beta-20260518-…` 토큰이 git 히스토리에 영구 잔존. 문서 스크럽(T3)만으로는 불충분 — **사용자가 Vercel의 `VCB_ALT_WEB_ACCESS_TOKEN`을 회전해야 실질 무효화**된다. 회전 전까지 저장소를 공개로 전환하면 안 된다.
2. Alpaca/Finnhub/OpenAI 키: Vercel 환경변수에만 존재해야 한다. 로그·문서·커밋에 값 기재 금지. 진단은 secret-safe 엔드포인트만 사용.
3. 개인정보: SaaS 사용자 테이블(이메일, 비밀번호 해시)이 Neon에 있다. export/delete API가 이미 존재 — 이 API의 인증 검사를 약화시키지 말 것.
4. 로그: `logging_utils.py`의 redaction을 우회하는 직접 `print`/로그 추가 금지.
5. `.env`는 gitignore되어 있으나, 실수 방지를 위해 어떤 도구로도 `.env`를 읽어 출력하지 않는다.

## Things Codex Should Not Do

- 전체 프로젝트 또는 web.py를 한 번에 새로 만들지 말 것 (단계적 티켓만)
- 정상 작동하는 프로바이더/큐/인증 코드를 "개선"을 이유로 재작성하지 말 것
- UI 개선을 이유로 `scoring.py`/`portfolio.py`의 수치·로직을 바꾸지 말 것
- `.env` 내용, Vercel 환경변수 값, 토큰·키를 출력하거나 문서에 쓰지 말 것
- 테스트 없이 web.py 대규모 이동을 하지 말 것 (모듈 분리는 T8 절차대로)
- "사용하지 않는 것 같다"는 이유로 임베디드 폴백 상수를 T7a(패키징 수정) 전에 삭제하지 말 것
- git 히스토리 재작성(filter-branch/filter-repo/force push) 금지
- Vercel 배포, Neon 스키마 변경, 외부 API 유료 호출을 사용자 승인 없이 실행하지 말 것
- 프로덕션 URL에 부하테스트를 임의 실행하지 말 것 (`--confirm-production-load` 플래그가 있는 도구 포함)
- 82개 테스트 중 실패하는 것을 skip 처리로 "통과"시키지 말 것
