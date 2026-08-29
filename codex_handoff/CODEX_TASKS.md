# CODEX_TASKS.md

> **모든 티켓 완료 (2026-08).** 이 문서는 무엇을 왜 바꿨는지에 대한 기록으로 남깁니다.
> 현재 상태는 [../README.md](../README.md)와 [../RELEASE_DECISION.md](../RELEASE_DECISION.md)를 보세요.
> Task 6은 Task 7b에서 함께 해소됐고, Task 7a는 Task 4(CI)와 함께 처리됐습니다.

실행 순서: Task 1 → 2 → 3 → 4 (Phase 0) → 5 → 6 (Phase 1) → 7 → 8 (Phase 2) → 9~13.
검증 인터프리터: PATH의 `python` (3.11.9). 초기 문서가 안내하던 `C:\stable-diffusion-ui\installer_files\env\python.exe`는 존재하지 않습니다.
공통 검증: `python -m unittest discover -s tests` / `python tools\lint.py` / `python tools\typecheck.py` / `python tools\secret_scan.py` / `python tools\check_docs.py` / `python -m compileall vcb_alt tests tools api`

---

### Task 1. 미커밋 작업 트리 리뷰 후 기준선 커밋

* Priority: P0
* Type: DevOps
* Goal: 2026-06-04 이후 방치된 미커밋 변경(13개 파일, +1,335/-97)을 리뷰하고 커밋해 안전한 작업 기준선을 만든다.
* Why: 지금 상태에서 새 작업을 시작하면 한 달치 미커밋 하드닝 작업과 새 변경이 섞여 롤백이 불가능해진다.
* Files to inspect first: `git status`, `git diff --stat`, `git diff vcb_alt/web.py vcb_alt/config.py vcb_alt/db.py vcb_alt/job_queue.py tests/`
* Files likely to change: 없음 (커밋만). 단, diff 리뷰 중 명백한 오류 발견 시 보고 후 별도 처리.
* Detailed instructions for Codex:
  1. `git config --global --add safe.directory C:/Users/a/Downloads/stock_screening_ver1.0` 실행 (이 머신에서 dubious ownership 에러 확인됨).
  2. `git diff`를 파일별로 읽고, 변경이 `RELEASE_DECISION.md`의 2026-06-10 항목(프로덕션 query-token 차단, worker POST 강제, JSON 가드, web_assets 추출 등)과 일치하는지 확인한다.
  3. 검증 4종을 실행한다 (2026-07-06에 전부 통과 확인됨 — 재확인 목적).
  4. 통과하면 전체를 하나의 커밋으로: `git add -A && git commit -m "Land 2026-06-10 production hardening and web_assets extraction"` (단, `codex_handoff/`는 별도 커밋으로 분리해도 됨).
  5. diff에서 이해할 수 없거나 의심스러운 변경이 있으면 커밋하지 말고 해당 hunk를 인용해 사용자에게 보고한다.
* Acceptance criteria: `git status` 클린(신규 handoff 문서 제외), 검증 4종 통과, 커밋 메시지가 내용을 반영.
* Validation commands: 공통 검증 4종 + `git log -2 --stat`
* Manual QA steps: 없음
* Risks: diff 안에 미완성 코드가 있을 가능성 → 테스트 통과가 방어선.
* Rollback plan: `git reset --soft HEAD~1` (커밋만 취소, 파일 보존).
* Do not touch: 코드 내용 수정 금지. 이 티켓은 리뷰+커밋 전용.

---

### Task 2. web.py의 중복 `DETAIL_TEXT_JS` 데드코드 제거

* Priority: P0
* Type: Bugfix
* Goal: `vcb_alt/web.py`에 두 번 정의된 모듈 상수 `DETAIL_TEXT_JS`(약 1858줄, 약 2571줄) 중 첫 번째(데드코드)를 삭제한다.
* Why: 두 정의는 내용이 미묘하게 다르다(예: 한 곳은 "점수는 …이며", 다른 곳은 "…이고"). Python은 두 번째 정의를 조용히 채택하므로 첫 번째 ~710줄은 순수 데드코드이며, 나중에 첫 번째를 수정하는 실수를 유발한다.
* Files to inspect first: `vcb_alt/web.py` — `grep -n "DETAIL_TEXT_JS = " vcb_alt/web.py`로 두 정의 위치 확인, 각 정의의 시작~끝(닫는 `"""`)을 정확히 읽기. `vcb_alt/web.py:1063`의 `_detail_js()`가 이 상수를 쓰는 위치.
* Files likely to change: `vcb_alt/web.py` (1개)
* Detailed instructions for Codex:
  1. 두 정의 전문을 diff해서 어떤 차이가 있는지 기록한다 (보고용).
  2. **두 번째 정의(현재 실제 적용되는 쪽)를 남기고 첫 번째 정의 블록 전체를 삭제**한다. 주변에 같은 diff로 추가된 다른 중복 상수(예: i18n 블록)가 있는지 `grep -c "^APP_KO_I18N\|^DETAIL_KO"` 방식으로 함께 확인하고, 중복이면 동일 원칙(뒤쪽 유지)으로 제거한다.
  3. 삭제 후 `_detail_js()`가 반환하는 문자열이 삭제 전(두 번째 정의 기준)과 동일한지 확인: 삭제 전후로 `& $py -c "from vcb_alt import web; print(len(web._detail_js()))"` 값 비교.
* Acceptance criteria: `grep -c "DETAIL_TEXT_JS = " vcb_alt/web.py` 결과가 1, `_detail_js()` 출력 길이 불변, 검증 4종 통과.
* Validation commands: 공통 검증 4종 + 위 길이 비교 one-liner
* Manual QA steps: 로컬 웹 실행 후 `/ticker/AAPL` 페이지에서 KO 토글 → 상세 설명 문장이 한국어로 정상 표시.
* Risks: 낮음 — 데드코드 삭제. 단 삭제 범위를 잘못 잡으면 SyntaxError → compileall이 즉시 검출.
* Rollback plan: `git revert <commit>`
* Do not touch: 두 번째 정의의 내용, `_detail_js()` 함수 로직.

---

### Task 3. 커밋된 프로덕션 접근 토큰 제거(문서 스크럽) + 회전 안내

* Priority: P0
* Type: Security
* Goal: 저장소 문서에 평문으로 커밋된 프로덕션 웹 접근 토큰(`vcb-beta-20260518-…`)을 플레이스홀더로 교체하고, 사용자에게 토큰 회전을 안내한다.
* Why: `git grep vcb-beta-20260518` 결과 `OPERATOR_TRIAL_GUIDE.md`, `PROVIDER_KEYS_SETUP.md`, `RELEASE_DECISION.md` 3개 파일에 라이브 배포 URL(`https://stockscreeningver10.vercel.app`)과 토큰 전문이 함께 노출되어 있다. 저장소를 보는 누구든 배포판에 접근 가능하다.
* Files to inspect first: `git grep -n "vcb-beta-20260518"` 결과 전부
* Files likely to change: `OPERATOR_TRIAL_GUIDE.md`, `PROVIDER_KEYS_SETUP.md`, `RELEASE_DECISION.md` (3개)
* Detailed instructions for Codex:
  1. 세 파일에서 토큰 문자열을 `<ROTATED-SEE-VERCEL-ENV>`로 교체한다. 문맥(역사 기록)은 보존한다.
  2. `RELEASE_DECISION.md` 상단에 한 줄 추가: "2026-07 보안 조치: 과거 문서에 노출됐던 접근 토큰은 무효화 대상이며 저장소에서 제거되었다."
  3. 저장소 전체에서 다른 실 토큰/키 패턴을 추가 스캔: `git grep -inE "(api[_-]?key|secret|token)\s*[:=]\s*[A-Za-z0-9_-]{16,}" -- "*.md" "*.py" "*.json"` — 발견 시 같은 방식으로 처리하되 `.env.example`류 플레이스홀더(`replace-with-...`)는 제외.
  4. **git 히스토리에는 토큰이 남는다.** 히스토리 재작성은 하지 말고, 사용자 보고에 다음을 명시: "Vercel 환경변수 `VCB_ALT_WEB_ACCESS_TOKEN`을 새 랜덤 값(32자 이상)으로 교체 후 재배포해야 노출 토큰이 완전 무효화됩니다."
* Acceptance criteria: `git grep vcb-beta-20260518` 결과 0건(codex_handoff 문서 제외), 검증 4종 통과(문서만 수정이므로 형식적).
* Validation commands: `git grep -c "vcb-beta-20260518"` → no matches
* Manual QA steps: 없음
* Risks: 없음(문서 수정). 실제 위험 제거는 사용자 토큰 회전에 달림.
* Rollback plan: `git revert` (되돌릴 이유 없음)
* Do not touch: `.env`(존재 시), Vercel 환경변수(사용자 몫), git 히스토리 재작성(`filter-branch`/`filter-repo`) 금지.

---

### Task 4. 테스트/린트/타입체크 CI 워크플로 추가

* Priority: P0
* Type: DevOps
* Goal: push/PR마다 unittest+lint+typecheck+compileall을 실행하는 GitHub Actions 워크플로를 추가한다.
* Why: 현재 `.github/workflows/`엔 수동 트리거 부하테스트 1개뿐이다. 회귀는 로컬 수동 실행에만 의존하고 있고, 실제로 한 달간 미커밋 상태가 방치됐다.
* Files to inspect first: `.github/workflows/hosted-scan-heavy-load-test.yml` (기존 스타일 참고), `pyproject.toml`, `requirements.txt`
* Files likely to change: `.github/workflows/ci.yml` (신규 1개)
* Detailed instructions for Codex:
  ```yaml
  name: CI
  on:
    push:
    pull_request:
  jobs:
    test:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-python@v5
          with: { python-version: "3.11" }
        - run: python -m pip install -r requirements.txt
        - run: python -m unittest discover -s tests -v
        - run: python tools/lint.py
        - run: python tools/typecheck.py
        - run: python -m compileall vcb_alt tests tools api
  ```
  주의: 테스트가 네트워크를 요구하지 않는지 로컬에서 `VCB_ALT_EXTERNAL_API_ENABLED=false` 기본값으로 전체 실행해 재확인(현재 82개는 오프라인 통과 확인됨). ubuntu에서 Windows 경로 의존 테스트가 깨지면 해당 테스트를 보고 후 skip 마킹이 아니라 경로 처리 수정을 우선 검토.
* Acceptance criteria: 워크플로 YAML 문법 유효, 로컬 검증 4종 통과. (원격 push 후 그린 여부는 사용자가 확인 — GitHub 원격 존재 여부 **확인 필요**.)
* Validation commands: 공통 검증 4종. YAML은 `& $py -c "import yaml"` 불가(외부 패키지)이므로 육안 + actionlint 없이 커밋.
* Manual QA steps: push 후 GitHub Actions 탭에서 그린 확인 (사용자).
* Risks: Linux CI에서 Windows 전용 가정이 깨질 수 있음 → 발견 즉시 보고.
* Rollback plan: 워크플로 파일 삭제.
* Do not touch: 기존 부하테스트 워크플로.

---

### Task 5. 스캔 202(대기) 상태의 자동 폴링 + 진행 UX

* Priority: P1
* Type: UX
* Goal: SaaS 모드에서 스캔 요청이 202(enqueued/pending)를 반환할 때, 대시보드가 자동으로 상태를 폴링하고 사용자에게 "대기 중 → 완료/실패"를 명확히 보여주게 한다.
* Why: 프로덕션 스캔은 워커 소유 스냅샷 구조라 즉시 결과가 없을 수 있다. 현재 UI가 202를 어떻게 다루는지에 따라 사용자는 "버튼이 고장났다"고 느낄 수 있다. 이것이 배포판 첫인상의 최대 리스크다.
* Files to inspect first: `vcb_alt/web_assets/app.js`의 `runScan()`(619행 부근), `api()`(199행), `setBusy`(410행 부근); `vcb_alt/web.py`에서 `/api/user/scan` 핸들러와 202 응답 바디 스키마; `vcb_alt/job_queue.py`의 잡 상태 필드.
* Files likely to change: `vcb_alt/web_assets/app.js`, `app.css`, `index.html` (+ `web.py`의 잡 상태 조회 API가 없으면 확인 필요로 보고)
* Detailed instructions for Codex:
  1. 먼저 202 응답 바디와 잡 상태 조회 경로(`/api/jobs/market-scan/{id}` — 구현 시 확인됨)를 파악해 보고에 기록한다.
  2. `runScan()`에서 응답이 202/pending이면: 버튼은 disabled 유지, 상태 배지에 "스캔 대기열에 등록됨 — 최신 스냅샷 준비 중"(EN/KO), 5초 간격 폴링(최대 12회) 후 완료 시 결과 렌더, 타임아웃 시 "아직 준비 중입니다. 잠시 후 새로고침" 안내.
  3. 폴링 중 페이지 이탈/재클릭 안전 처리(중복 타이머 금지).
  4. 모든 신규 문자열은 `I18N`에 EN/KO 쌍으로 추가.
  5. 프로바이더 차단(Alpaca 401 등)으로 fail-closed된 경우의 응답을 구분해 "라이브 데이터 제공자 인증 실패 — 운영자 확인 필요" 메시지를 표시(성공도 대기도 아닌 세 번째 상태).
* Acceptance criteria: 로컬에서 큐 모드 재현(`VCB_ALT_SCAN_QUEUE_ENABLED=true` + 워커 미실행) 시 대기 UX 동작, 워커 실행 후 폴링이 결과를 렌더, EN/KO 양쪽 문구 정상, 콘솔 에러 0.
* Validation commands: 공통 검증 4종 + 로컬 웹 수동 확인
* Manual QA steps: ① 큐 모드로 스캔 클릭 → 대기 배지 확인 ② `& $py -m vcb_alt worker --limit 5`(정확한 워커 커맨드는 cli.py에서 확인) 실행 → 폴링이 결과 표시 ③ 모바일 375px 확인.
* Risks: 잡 상태 API 스키마 오해 → 1번 단계에서 실제 응답을 curl로 확인하고 진행.
* Rollback plan: `git revert`
* Do not touch: `/api/user/scan` 서버 로직의 fail-closed 동작, `job_queue.py`의 큐 시맨틱.

---

### Task 6. 런타임 JS 문자열 치환 i18n 핵 제거

* Priority: P1
* Type: Refactor
* Goal: `web.py`가 서빙 직전에 JS 소스의 한국어 블록을 정규식/마커 치환하는 구조(`_replace_js_ko_block`, `_replace_render_scan_i18n`, `_replace_js_const_object`, `_replace_js_function_block`, `_dashboard_js`, `_detail_js`)를 제거하고, `web_assets/app.js`·`detail.js` 파일 자체가 올바른 UTF-8 한국어 문자열을 담게 한다.
* Why: 이 핵은 과거 인코딩 손상의 우회책이다. 지금은 web_assets 파일이 UTF-8로 정상이므로, 서빙 시 치환은 "파일과 실제 응답이 다른" 디버깅 불가 구조만 남긴다.
* Files to inspect first: `vcb_alt/web.py:1032~1100` (치환 함수들), `web.py`에서 `APP_KO_I18N`·`DETAIL_TEXT_JS` 등 치환용 상수의 전문, `web_assets/app.js`의 `const I18N =` 블록, `web_assets/detail.js`의 `function detailText`.
* Files likely to change: `vcb_alt/web_assets/app.js`, `vcb_alt/web_assets/detail.js`, `vcb_alt/web.py` (3개)
* Detailed instructions for Codex:
  1. 현재 실제 서빙 결과를 기준으로 삼는다: `& $py -c "from vcb_alt import web; open('scratch_app.js','w',encoding='utf-8').write(web._dashboard_js())"` 및 `_detail_js()`도 동일하게 덤프. **주의: `_dashboard_js()`는 임베디드 `APP_JS` 기준이고 실제 서빙은 `_web_asset()`이 파일 우선이다** — `route_request`의 `/assets/app.js` 분기를 읽고 실제 서빙 바이트를 확정한 뒤 진행.
  2. 서빙 결과와 `web_assets/app.js` 파일을 diff해 치환이 실제로 바꾸는 부분을 특정한다. 차이가 있으면 파일 쪽을 서빙 결과(=치환 적용본)로 갱신한다.
  3. `route_request`에서 `/assets/app.js`·`/assets/detail.js` 서빙을 파일 직접 서빙으로 단순화하고, 폴백은 임베디드 상수 원문(치환 함수 미적용)으로 유지한다. 치환 함수 6종과 치환 전용 상수는 삭제… 하되 **폴백 경로가 치환 없이는 손상 한국어를 서빙하게 되는지 먼저 확인**: 임베디드 `APP_JS`의 KO 블록이 손상 상태라면 임베디드 상수 자체를 파일 내용으로 갱신하거나, 이 삭제를 Task 7(폴백 전체 제거) 이후로 미룬다. 판단이 어려우면 분리 보고.
  4. UTF-8 검증: 덤프 파일을 브라우저로 열어 한국어 문자열 깨짐 없는지 확인.
* Acceptance criteria: 서빙되는 `/assets/app.js`·`/assets/detail.js` 바이트가 web_assets 파일과 동일, EN/KO 토글 전 화면 정상, `_replace_js_*` 함수 grep 0건(또는 Task 7 이후로 연기 사유 보고), 검증 4종 통과.
* Validation commands: 공통 검증 4종 + `& $py -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8765/assets/app.js').read().decode('utf-8')[:200])"` (서버 실행 상태에서)
* Manual QA steps: 대시보드/상세 페이지 KO 모드 전체 훑기(스캔 버튼, 테이블 헤더, 상세 설명 문장), 브라우저 콘솔 에러 0.
* Risks: 중간 — 인코딩 회귀. PowerShell로 파일 쓸 때 반드시 UTF-8(BOM 없음) 보장, Write 계열 도구 사용 권장.
* Rollback plan: `git revert`
* Do not touch: i18n 키 이름, 중립 리서치 라벨 문구.

---

### Task 7. web_assets 패키징 수정 후 임베디드 폴백 상수 제거 (2단계)

* Priority: P1
* Type: Refactor
* Goal: (7a) `pyproject.toml`에 package-data를 추가해 `pip install .`에도 `web_assets/*`가 포함되게 하고, (7b) 그 후 `web.py`의 임베디드 폴백 상수(`INDEX_HTML`, `APP_JS`, `APP_CSS`, `DETAIL_HTML`, `LOGIN_HTML`, `TERMS_HTML` 등 약 2,500~3,000줄)를 삭제한다.
* Why: 폴백 상수는 "pip 설치 시 정적 파일 누락"을 가리는 땜질이며, 같은 프론트엔드를 두 벌 유지하게 만든 근본 원인이다(중복 `DETAIL_TEXT_JS` 사고의 뿌리). 패키징을 고치면 폴백이 불필요하다.
* Files to inspect first: `pyproject.toml`, `vcb_alt/web.py:116` `_web_asset()`, 임베디드 상수 전체 목록(`grep -nE "^[A-Z_]+ = \"\"\"" vcb_alt/web.py`), `Dockerfile`(vcb_alt 통째 복사라 영향 없음 확인), `api/index.py`(저장소 통째 배포라 영향 없음 확인).
* Files likely to change: `pyproject.toml`, `vcb_alt/web.py` (2개, 커밋은 7a/7b 분리)
* Detailed instructions for Codex:
  1. **7a**: `pyproject.toml`에 추가:
     ```toml
     [tool.setuptools.package-data]
     vcb_alt = ["web_assets/*"]
     ```
     검증: 임시 폴더에서 `& $py -m pip install . --target C:\Users\a\AppData\Local\Temp\vcb_pkg_test` 후 `web_assets` 존재 확인. 커밋.
  2. **7b**: `_web_asset(name, fallback)`을 파일 필수 로딩으로 바꾼다 — 파일이 없으면 명확한 500 에러 대신 안전한 에러 텍스트("asset missing: {name} — reinstall package")를 반환하도록. 이후 상수들을 **한 커밋에 하나~두 개 그룹씩** 삭제하며 매번 검증 4종 + 로컬 웹 스모크를 돌린다. 상수를 참조하는 테스트가 있으면(`grep -rn "INDEX_HTML\|APP_JS" tests/`) 테스트를 파일 기반으로 갱신한다.
* Acceptance criteria: `web.py` 줄수 약 1,500~2,000줄로 감소, 모든 페이지/에셋 정상 서빙, pip 설치본에서도 동일, 검증 4종 통과.
* Validation commands: 공통 검증 4종 + pip --target 설치 스모크 + 로컬 웹 전 페이지 수동 확인
* Manual QA steps: `/`, `/ticker/AAPL`, `/login`(?), `/terms`, `/privacy`, `/risk-disclosure`, `/assets/app.css` 각각 200 응답과 렌더 확인.
* Risks: 높음 — Vercel 배포는 저장소 통째라 안전하지만, 미지의 설치 경로가 있을 수 있음. 7a 없이 7b를 먼저 하면 pip 설치본이 깨진다. **순서 엄수.**
* Rollback plan: 그룹별 커밋이므로 문제 그룹만 `git revert`.
* Do not touch: `_send_html`/`_send_text`의 헤더·보안 동작, Task 8 전까지 라우팅 구조.

---

### Task 8. web.py 모듈 분리 (단계적, 행동 보존)

* Priority: P2
* Type: Refactor
* Goal: Task 7 후 남은 web.py(~1,500줄)를 책임별 모듈로 분리: `vcb_alt/web_auth.py`(인증/토큰/쿠키), `vcb_alt/web_ratelimit.py`(레이트리밋 버킷/그룹), `vcb_alt/web_api.py`(handle_api 및 _scan* 헬퍼), web.py는 서버 기동+라우팅만 유지.
* Why: 단일 4,854줄 파일은 리뷰·수정 리스크의 근원이다. 단, 이동만 하고 로직은 바꾸지 않는다.
* Files to inspect first: `vcb_alt/web.py` 전체 함수 목록, `api/index.py`(import 경로), `tests/test_web.py`·`tests/test_saas_auth.py`(내부 함수 import 여부)
* Files likely to change: `vcb_alt/web.py`, 신규 3개 모듈, `tests/test_web.py` (최대 5개)
* Detailed instructions for Codex: 모듈 하나당 한 커밋. 함수를 잘라 옮기고 web.py에 re-export(`from .web_auth import _is_authorized` 등)를 남겨 외부 호환 유지. 각 커밋마다 검증 4종. 순환 import가 생기면 공용 헬퍼를 옮기는 방향으로 해소하되, 시그니처 변경 금지.
* Acceptance criteria: 검증 4종 통과, `api/index.py` 무수정으로 동작, 로컬 웹 스모크 통과.
* Validation commands: 공통 검증 4종 + 로컬 웹 스모크
* Manual QA steps: 대시보드 로딩 + 로그인 게이트 + 스캔 1회.
* Risks: 중간 — import 누락. 커밋 단위 소분할이 방어선.
* Rollback plan: 모듈별 revert.
* Do not touch: 함수 본문 로직, 응답 스키마.

---

### Task 9. 루트 디렉터리 정리 (문서 → docs/, 산출물 제거)

* Priority: P2
* Type: Docs
* Goal: 루트의 md 문서 40여 개를 `docs/`로 이동(README/CHANGELOG/SETUP 등 핵심 5~6개만 루트 유지), 추적 중인 스크린샷 PNG·세션 로그·`.playwright-mcp/` 잔재를 정리한다.
* Why: 신규 작업자(및 Codex)가 권위 문서를 찾기 어렵고, README의 상호 링크가 오염돼 있다.
* Files to inspect first: `git ls-files "*.md" "*.png"`, README.md 내 문서 링크 전체
* Files likely to change: md 파일 이동 다수 + README 링크 갱신 (git mv라 위험 낮음)
* Detailed instructions for Codex: `git mv`로 이동, README와 문서 상호 링크를 전부 갱신(`grep -rn "\]\(\./" *.md docs/`로 잔여 확인). PNG는 git 추적 여부 확인 후 추적 중이면 `git rm --cached`(파일은 보존), 미추적이면 그대로 둔다. 삭제는 하지 않는다.
* Acceptance criteria: 루트에 md 6개 이하, README 링크 전부 유효, 검증 4종 통과.
* Validation commands: 공통 검증 4종 + 링크 grep
* Manual QA steps: README를 GitHub 렌더 기준으로 훑어 깨진 링크 없는지.
* Risks: 낮음. 문서 경로를 코드가 참조할 가능성 → `grep -rn "\.md" vcb_alt/ tools/ api/`로 사전 확인.
* Rollback plan: `git revert`
* Do not touch: 파일 삭제 금지(이동만), `data/` 예제 CSV.

---

### Task 10. 프로바이더 차단 상태의 대시보드 가시화

* Priority: P2
* Type: UI
* Goal: Alpaca 401 같은 프로바이더 인증 실패를 대시보드 운영 패널에 명시적 배지("라이브 데이터 인증 실패 — 키 재설정 필요")로 표시하고, 진단 엔드포인트(`/api/provider-diagnostics/alpaca`) 결과를 운영자에게 노출한다.
* Why: 현재 핵심 기능이 죽어 있는데 화면은 이유를 설명하지 않는다. 운영자가 "무엇을 고치면 되는지"를 화면에서 알 수 있어야 한다.
* Files to inspect first: `web.py`의 `/api/provider-health`, `/api/provider-diagnostics/alpaca`, `/api/admin/provider-alerts` 핸들러와 응답 스키마; `app.js`의 `loadOps()`(561행 부근)
* Files likely to change: `vcb_alt/web_assets/app.js`, `app.css`, `index.html` (+필요시 web.py 응답 필드 추가 1건)
* Detailed instructions for Codex: 운영 패널(`#readiness`)에 프로바이더별 상태 행(이름/ready·error/최근 오류 분류)을 렌더. 비밀값은 절대 표시하지 않는다(기존 API가 이미 secret-safe — 그대로 사용). EN/KO 문구 추가.
* Acceptance criteria: 키 미설정 로컬에서 "not configured", 키 오류 시 "auth failed" 구분 표시, 검증 4종 통과, 콘솔 에러 0.
* Validation commands: 공통 검증 4종 + 로컬 웹 수동
* Manual QA steps: 로컬 기본(.env 없음) 상태에서 운영 패널 표시 확인, 모바일 확인.
* Risks: 낮음.
* Rollback plan: `git revert`
* Do not touch: 진단 API의 secret-safe 동작.

---

### Task 11. psycopg를 선택적 의존성(extra)으로 전환

* Priority: P3
* Type: DevOps
* Goal: `pyproject.toml`의 필수 의존성 psycopg를 `[project.optional-dependencies] postgres = [...]`로 옮기고, PostgreSQL URL 사용 시 미설치면 명확한 에러 메시지를 내게 한다.
* Why: 로컬 SQLite 사용자에게 불필요한 바이너리 의존을 강제하고 있다. README의 "stdlib-first" 주장과도 어긋난다.
* Files to inspect first: `vcb_alt/db.py`의 psycopg import 위치(지연 import인지), `requirements.txt`, `api/index.py`
* Files likely to change: `pyproject.toml`, `requirements.txt`(Vercel용이므로 psycopg 유지), `vcb_alt/db.py` 에러 메시지 (3개)
* Detailed instructions for Codex: db.py에서 postgres 분기 진입 시에만 import하고 ImportError면 "pip install vcb-alt[postgres]" 안내 예외. Vercel(requirements.txt)과 Docker에는 psycopg 유지.
* Acceptance criteria: SQLite 경로 전 테스트 통과, postgres URL + psycopg 미설치 시 친절한 에러, 검증 4종 통과.
* Validation commands: 공통 검증 4종
* Manual QA steps: 없음
* Risks: 낮음. Vercel requirements.txt를 건드리면 프로덕션이 깨짐 — psycopg 줄 유지 필수.
* Rollback plan: `git revert`
* Do not touch: `requirements.txt`의 psycopg 라인 삭제 금지.

---

### Task 12. 빈 상태/로딩/마이크로카피/접근성 폴리시

* Priority: P3
* Type: UX
* Goal: 첫 접속 화면에서 서비스 가치가 10초 안에 전달되도록 히어로 카피 정돈, 빈 상태 문구를 행동 유도형으로 개선, 테이블 로딩 스켈레톤, 포커스 스타일/aria 라벨 점검.
* Why: 실서비스 인상은 이 디테일에서 갈린다. 구조는 이미 양호(empty-state, aria-label 존재 확인됨) — 다듬기만 필요.
* Files to inspect first: `web_assets/index.html`, `app.css`, `app.js`의 렌더 함수들
* Files likely to change: `web_assets/` 3~4개 파일
* Detailed instructions for Codex: (a) 빈 상태 문구에 다음 행동 명시("아직 스캔 전입니다 — 위의 '시장 전체 스캔'을 눌러 시작하세요"), (b) 스캔 중 테이블에 스켈레톤 행 3개, (c) 모달(`#detail-modal`) ESC 닫기+포커스 트랩, (d) 버튼 포커스 아웃라인 유지, (e) EN/KO 양쪽 카피 검수.
* Acceptance criteria: 콘솔 에러 0, EN/KO 정상, 모바일 정상, 키보드만으로 모달 열고 닫기 가능, 검증 4종 통과.
* Validation commands: 공통 검증 4종 + 로컬 웹 수동
* Manual QA steps: TEST_AND_VALIDATION.md의 Manual QA 시나리오 전체 1회.
* Risks: 낮음.
* Rollback plan: `git revert`
* Do not touch: 중립 리서치 라벨, 법적 푸터.

---

### Task 13. 라이브 개통 절차서 작성 (Alpaca 키 재발급 후 실행용)

* Priority: P3
* Type: Docs
* Goal: 사용자가 Alpaca 키를 재발급한 날, 순서대로 실행하면 프로덕션 라이브 스캔이 개통 검증되는 단일 문서 `docs/GO_LIVE_RUNBOOK.md`를 작성한다.
* Why: 현재 개통 지식이 `PROVIDER_KEYS_SETUP.md`, `RELEASE_DECISION.md`, `OPERATOR_TRIAL_GUIDE.md` 등에 흩어져 있고 일부는 낡았다.
* Files to inspect first: 위 3개 문서 + `MONITORING_ALERTING_PLAN.md`, `tools/host_queue_load_test.py`의 옵션
* Files likely to change: `docs/GO_LIVE_RUNBOOK.md` 신규 1개
* Detailed instructions for Codex: 절차: ① Vercel 환경변수 세팅 목록(이름만, 값 금지) ② 재배포 ③ `/api/provider-diagnostics/alpaca` ready=true 확인 ④ 프로덕션 스캔 1회 + 후보 렌더 확인 ⑤ 워커 완료 부하테스트 명령(기존 host_queue_load_test.py 커맨드 인용) ⑥ 실패 시 롤백(이전 배포로 revert). 각 단계에 "예상 결과"를 명시.
* Acceptance criteria: 문서만으로 비전문가가 단계 실행 가능(전문용어에 한 줄 설명 병기).
* Validation commands: 없음(문서)
* Manual QA steps: 사용자 리뷰.
* Risks: 없음.
* Rollback plan: 해당 없음.
* Do not touch: 실 토큰/키 값 기재 금지.
