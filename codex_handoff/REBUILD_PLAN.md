# REBUILD_PLAN.md

> **기록 문서 (2026-08 작업 완료).** 이 패키지는 재설계 착수 시점의 진단과 계획입니다.
> 이후 티켓 13개가 모두 수행되어 아래 내용 중 다수는 더 이상 현재 상태가 아닙니다.
> 현재 상태는 [../README.md](../README.md)와 [../RELEASE_DECISION.md](../RELEASE_DECISION.md)를 보세요.

## North Star

"동작하지만 정리가 필요한 운영자 시험판"을 "구조가 깨끗하고, 비밀이 새지 않고, 자동 검증이 돌고, 스캔 대기 상태까지 자연스러운 실서비스 수준"으로 끌어올린다. 전면 재작성은 하지 않는다. 순서는: ① 작업 트리·비밀·CI 안정화 → ② 스캔 UX와 상태 처리 개선 → ③ web.py 이중 프론트엔드 제거와 모듈 분리 → ④ 문서/디테일 폴리시 → ⑤ 운영 준비. 프로덕션 라이브 스캔의 최종 개통은 사용자(Alpaca 키 재발급) 몫이며, 코드 측은 그날 바로 켤 수 있는 상태를 만들어 둔다.

## Phase 0: Stabilize

- 목표: 안전한 작업 기준선 확보. 미커밋 변경 정리, 노출 토큰 무효화 절차, 데드코드 제거, CI 구축.
- 작업 범위: Task 1~4 (CODEX_TASKS.md)
- 수정 예상 파일: git 커밋만(T1), `vcb_alt/web.py`(T2), `OPERATOR_TRIAL_GUIDE.md`·`PROVIDER_KEYS_SETUP.md`·`RELEASE_DECISION.md`(T3), `.github/workflows/ci.yml` 신규(T4)
- 완료 기준: 클린 working tree + 검증 4종 통과 + push 시 CI 자동 실행 + 저장소 내 실토큰 문자열 0건
- 리스크: 낮음. T1은 코드 변경이 아니라 리뷰+커밋.
- Codex 작업 난이도: 하
- 선행 조건: 없음. **여기부터 시작한다.**

## Phase 1: Core UX Fix

- 목표: 사용자가 스캔을 눌렀을 때 일어나는 모든 경우(성공/202 대기/실패/빈 데이터/프로바이더 차단)를 대시보드가 명확히 설명하게 만든다.
- 작업 범위: Task 5, 6, 10
- 수정 예상 파일: `vcb_alt/web_assets/app.js`, `app.css`, `index.html`, `detail.js`, `vcb_alt/web.py`(i18n 핵 제거부)
- 완료 기준: 202 응답 시 자동 폴링+진행 표시, 프로바이더 차단 시 운영자용 안내 노출, 런타임 JS 치환 핵 제거 후에도 EN/KO 정상, 모바일 375px 무결
- 리스크: 중간 — i18n 핵 제거는 서빙 JS 바이트가 바뀌므로 브라우저 수동 검증 필수.
- Codex 작업 난이도: 중
- 선행 조건: Phase 0 완료 (특히 T2의 중복 상수 제거)

## Phase 2: Architecture Cleanup

- 목표: web.py에서 임베디드 프론트엔드 두 벌 관리를 끝내고, 모놀리스를 기능별 모듈로 단계 분리한다.
- 작업 범위: Task 7, 8, 11
- 수정 예상 파일: `pyproject.toml`, `vcb_alt/web.py`(대폭 축소), 신규 `vcb_alt/web_routes.py`·`vcb_alt/web_auth.py` 등
- 완료 기준: web.py에서 임베디드 HTML/JS 상수 삭제(약 2,500~3,000줄 감소), `pip install .` 후에도 web_assets 서빙 정상, 모듈 분리 후 전 테스트 통과
- 리스크: 높음 — 반드시 티켓 단위(상수군 하나씩 / 함수군 하나씩)로 쪼개 진행. 한 커밋에 몰지 않는다.
- Codex 작업 난이도: 중~상
- 선행 조건: Phase 0 완료 + T7의 packaging 수정이 T8보다 선행

## Phase 3: Product Polish

- 목표: 실서비스 인상 완성 — 빈 상태 카피, 로딩 스켈레톤, 에러 문구, 접근성, 마이크로카피 정돈.
- 작업 범위: Task 12, 9(문서/루트 정리 포함)
- 수정 예상 파일: `web_assets/*`, 루트 md 문서 이동(docs/)
- 완료 기준: 첫 접속 10초 안에 "무엇을 하는 서비스이고 지금 눌러야 할 버튼이 무엇인지" 이해 가능, 스크린리더 기본 항행 가능, 루트에 핵심 문서만 남음
- 리스크: 낮음
- Codex 작업 난이도: 하~중
- 선행 조건: Phase 1 완료

## Phase 4: Operational Readiness

- 목표: 사용자(운영자)가 Alpaca 키를 재발급하는 즉시 라이브 개통 검증이 가능하도록 준비. 배포 체크리스트·모니터링 정리.
- 작업 범위: Task 13 + 기존 `tools/ops_health_report.py`, `MONITORING_ALERTING_PLAN.md` 정합화
- 완료 기준: "키 입력 → `/api/provider-diagnostics/alpaca` ready=true 확인 → 프로덕션 스캔 1회 → 후보 렌더" 개통 절차가 문서 한 장으로 실행 가능
- 리스크: 프로덕션 환경 의존 — 이 머신에서 검증 불가한 항목은 "확인 필요"로 사용자에 이관
- Codex 작업 난이도: 하
- 선행 조건: 사용자로부터 Alpaca 신규 자격증명 (외부 의존)
