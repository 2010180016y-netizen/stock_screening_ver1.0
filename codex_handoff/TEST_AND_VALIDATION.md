# TEST_AND_VALIDATION.md

> **기록 문서 (2026-08 작업 완료).** 이 패키지는 재설계 착수 시점의 진단과 계획입니다.
> 이후 티켓 13개가 모두 수행되어 아래 내용 중 다수는 더 이상 현재 상태가 아닙니다.
> 현재 상태는 [../README.md](../README.md)와 [../RELEASE_DECISION.md](../RELEASE_DECISION.md)를 보세요.

모든 명령은 이 Windows 머신 기준. **인터프리터는 PATH의 `python`(3.11.9)을 쓴다.** 저장소 문서가 안내하는 `C:\stable-diffusion-ui\installer_files\env\python.exe`는 2026-07-06 기준 존재하지 않는다(Task 1에서 확인). 아래 문서의 `& $py`는 전부 `python`으로 읽는다.

```powershell
python --version   # Python 3.11.9
```

## Local Setup Check

```powershell
# (선택) 환경 파일 — .env 없이도 안전한 오프라인 기본값으로 동작한다
Copy-Item .env.example .env

# DB 초기화 + 샘플 시드
& $py -m vcb_alt init-db --seed

# 설정 진단 — 오류 없이 구성 요약이 출력되어야 함
& $py -m vcb_alt doctor

# 웹 서버
& $py -m vcb_alt web --host 127.0.0.1 --port 8765
# → http://127.0.0.1:8765 접속
```

## Build Check

프론트 번들이 없으므로 바이트코드 컴파일이 빌드 검증이다:

```powershell
& $py -m compileall vcb_alt tests tools api
```
예상 결과: 에러 0. (2026-07-06 통과 확인)

## Lint/Type Check

```powershell
& $py tools\lint.py        # 예상: "lint ok (44 files)" — 파일 수는 증감 가능
& $py tools\typecheck.py   # 예상: "type hints ok (428 objects)" — 수는 증감 가능
```

## Automated Tests

```powershell
& $py -m unittest discover -s tests -v
```
예상 결과: **82 tests OK, 약 12초** (2026-07-06 실측). 82개 미만으로 줄면 회귀로 간주하고 원인 보고.

**신규 작업별 최소 추가 테스트:**
- T5(폴링 UX): 202 응답 스키마를 검증하는 서버측 테스트가 이미 있는지 확인, 없으면 `tests/test_web.py`에 추가
- T6/T7(에셋): 서빙된 `/assets/app.js`가 유효 UTF-8이고 `const I18N` 블록을 포함하는지 확인하는 테스트 (`tests/test_web.py`에 유사 테스트 존재 여부 먼저 확인)
- T7a(패키징): pip --target 설치 후 web_assets 존재 확인은 수동(테스트 자동화 불필요)

## Manual QA Scenarios

로컬 웹(`http://127.0.0.1:8765`) 기준. 각 시나리오는 EN/KO 양쪽에서 1회씩.

1. **첫 접속**: 대시보드 로드, 콘솔 에러 0, "Data as of / Provider / Operational status" 메타 표시
2. **핵심 CTA**: "Scan full market" 클릭 → 진행 표시 → 결과 렌더(sample 모드: 후보 테이블 채워짐) 또는 명확한 대기/실패 메시지
3. **진입 흐름**: `VCB_ALT_PUBLIC_WEB_ENABLED=true` + 토큰 설정 시 비인증 접속 → 로그인 화면 → 잘못된 토큰 거부(401) → 올바른 토큰 통과
4. **폼 입력**: 워치리스트 서랍에서 `PLTR MSTR` 추가 → 목록 갱신 → 제거 동작
5. **성공 상태**: 스캔 후 "Selected research set" 카드와 후보 테이블 표시, 선택 메타 갱신
6. **실패 상태**: `VCB_ALT_DATA_PROVIDER=yahoo` + `VCB_ALT_EXTERNAL_API_ENABLED=false`(모순 설정) 또는 네트워크 차단 상태에서 스캔 → 죽지 않고 오류 메시지 표시
7. **빈 데이터**: `init-db`(--seed 없이) 직후 → 빈 상태 문구가 다음 행동을 안내
8. **모바일**: 375px 뷰포트 — 가로 스크롤 없음, CTA 접근 가능, 테이블 래핑 정상
9. **데스크톱**: 1280px — 사이드바+본문 2단 레이아웃 정상
10. **새로고침**: 스캔 후 F5 → 상태 복원(스냅샷/설정 재로드) 및 에러 없음
11. **API 실패**: 서버 중단 후 대시보드에서 버튼 클릭 → JS가 죽지 않고 오류 알림
12. **권한 없는 접근**: 공개 모드에서 토큰 없이 `/api/scan` 직접 호출 → 401 JSON
13. **티커 상세**: 후보 클릭 → `/ticker/{SYM}` 로드, 5년 차트 렌더, KO 토글 시 설명 문장 한국어

## Regression Checklist

코드 변경 커밋 전 매번:

- [ ] 검증 4종(unittest 82+/lint/typecheck/compileall) 통과
- [ ] 로컬 웹: 대시보드 + `/ticker/AAPL` + 법적 문서 3페이지 200 응답
- [ ] EN/KO 토글 양쪽 무결 (특히 web.py/web_assets 수정 시)
- [ ] 브라우저 콘솔 에러 0
- [ ] `git grep -i "vcb-beta-20260518"` 0건 유지, 새 비밀 문자열 없음
- [ ] fail-closed: sample이 아닌 라이브 요구 모드에서 데이터 없을 때 후보가 나오지 않아야 함
- [ ] `api/index.py` import 경로 무변경(또는 변경 시 배포 스모크 필요 표시)
- [ ] 82개 기준 대비 테스트 수 감소 없음
