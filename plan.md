# Feature 00 Implementation Plan: Input-Based Paging

작성일: 2026-05-17 KST

## 1. 목표

목록 조회에서 offset 기반 페이징을 도입하지 않고, 명시적인 입력 객체 기반 keyset/cursor 페이징을 지원한다.

현재 코드에는 `OFFSET`은 없지만, 대부분의 목록이 `limit`만 지원하거나 전체 목록을 반환한다. 이 상태에서 단순히 `page`/`offset`을 붙이면 데이터가 늘어날수록 느려지고, insert/delete가 섞일 때 중복/누락이 생길 수 있다. 따라서 새 기능 00은 `PagingInput`을 표준화하고, 각 list API가 안정적인 정렬 key와 cursor를 사용하도록 만든다.

## 2. 현재 코드 기준 문제 위치

### 2.1 DB 목록 함수

`vcb_alt/db.py`

- `list_watchlist(conn)`: 전체 watchlist를 `ORDER BY ticker`로 반환.
- `recent_logs(conn, limit=20)`: `ORDER BY id DESC LIMIT ?`.
- `recent_failures(conn, limit=20)`: `ORDER BY id DESC LIMIT ?`.
- `export_data(conn)`: 모든 row를 통째로 export.

### 2.2 CLI 목록 명령

`vcb_alt/cli.py`

- `watchlist list`: paging input 없음.
- `admin logs --limit`: limit만 있음.
- `admin failures --limit`: limit만 있음.
- `scan --limit`: list 전체를 가져온 뒤 Python slicing.

### 2.3 Web API 목록

`vcb_alt/web.py`

- `GET /api/watchlist`: 전체 반환.
- `GET /api/logs`: fixed limit 12.
- `GET /api/failures`: fixed limit 12.
- `GET /api/scan`: watchlist 전체 scan.
- `GET /api/select`: watchlist 전체 select.

### 2.4 Frontend

`vcb_alt/web.py` 안의 `APP_JS`

- 목록 UI는 "더 보기"나 cursor state가 없다.
- `loadWatchlist()`는 `/api/watchlist`만 호출한다.
- `loadOps()`는 `/api/failures`만 호출한다.
- logs는 현재 frontend에 표시되지 않는다.

## 3. 설계 원칙

1. Offset 금지
   - SQL `OFFSET`을 쓰지 않는다.
   - `page=3`처럼 서버가 offset을 계산하는 방식도 쓰지 않는다.

2. Input 기반
   - API/CLI가 `limit`, `after`, `before`, `direction`, `sort`를 담은 명시적 input을 받는다.
   - cursor는 사용자가 직접 숫자 offset을 계산하지 않아도 되는 값이다.

3. Keyset pagination
   - stable ordering key를 기준으로 `WHERE key < cursor` 또는 `WHERE key > cursor`를 사용한다.
   - logs/failures는 `id` 기반 descending keyset이 가장 안전하다.
   - watchlist는 `ticker` 기반 ascending keyset이 현재 schema와 맞는다.

4. 응답 표준화
   - 모든 list 응답에 `items`, `count`, `page`를 포함한다.
   - `page`에는 `limit`, `next_after`, `previous_before`, `has_more`, `sort`, `direction`이 들어간다.

5. 기존 API 호환
   - query parameter가 없으면 기존처럼 첫 페이지를 반환한다.
   - 기존 `limit` 인자는 유지하되 내부적으로 `PagingInput`으로 변환한다.

## 4. 새 모델

`vcb_alt/models.py`에 paging dataclass를 추가한다.

```python
@dataclass(frozen=True)
class PagingInput:
    limit: int = 20
    after: str | None = None
    before: str | None = None
    direction: str = "next"
    sort: str = "default"


@dataclass(frozen=True)
class PageInfo:
    limit: int
    count: int
    has_more: bool
    next_after: str | None = None
    previous_before: str | None = None
    sort: str = "default"
    direction: str = "next"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PageResult:
    items: list[dict[str, Any]]
    page: PageInfo

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": self.items,
            "count": len(self.items),
            "page": self.page.to_dict(),
        }
```

## 5. Validation 추가

`vcb_alt/validation.py`에 paging input validator를 추가한다.

```python
def validate_page_limit(value: int | str | None, *, default: int = 20, maximum: int = 100) -> int:
    if value is None or value == "":
        return default
    try:
        limit = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("limit must be an integer.") from exc
    if limit < 1 or limit > maximum:
        raise ValidationError(f"limit must be between 1 and {maximum}.")
    return limit


def validate_cursor(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    cursor = str(value).strip()
    if len(cursor) > 80:
        raise ValidationError("cursor is too long.")
    if any(char in cursor for char in "\r\n\t"):
        raise ValidationError("cursor contains invalid whitespace.")
    return cursor
```

숫자 ID cursor용 validator도 둔다.

```python
def validate_int_cursor(value: str | None) -> int | None:
    cursor = validate_cursor(value)
    if cursor is None:
        return None
    try:
        parsed = int(cursor)
    except ValueError as exc:
        raise ValidationError("cursor must be an integer id.") from exc
    if parsed < 1:
        raise ValidationError("cursor must be a positive id.")
    return parsed
```

## 6. DB 함수 설계

### 6.1 Watchlist keyset paging

정렬:

- default: `ticker ASC`
- cursor: last seen ticker
- next page condition: `ticker > after`
- previous page condition: `ticker < before`, query는 DESC로 가져온 뒤 application에서 reverse

추가 함수:

```python
def list_watchlist_page(conn: sqlite3.Connection, paging: PagingInput) -> PageResult:
    ensure_initialized(conn)
    limit = paging.limit
    fetch_limit = limit + 1
    params: list[Any] = []

    if paging.before:
        sql = """
        SELECT ticker, archetype_hint, notes, added_at
        FROM watchlist
        WHERE ticker < ?
        ORDER BY ticker DESC
        LIMIT ?
        """
        params = [paging.before, fetch_limit]
        rows = conn.execute(sql, params).fetchall()
        items = [dict(row) for row in rows[:limit]]
        items.reverse()
    else:
        where = ""
        if paging.after:
            where = "WHERE ticker > ?"
            params.append(paging.after)
        sql = f"""
        SELECT ticker, archetype_hint, notes, added_at
        FROM watchlist
        {where}
        ORDER BY ticker ASC
        LIMIT ?
        """
        params.append(fetch_limit)
        rows = conn.execute(sql, params).fetchall()
        items = [dict(row) for row in rows[:limit]]

    has_more = len(rows) > limit
    return PageResult(
        items=items,
        page=PageInfo(
            limit=limit,
            count=len(items),
            has_more=has_more,
            next_after=items[-1]["ticker"] if items and has_more else None,
            previous_before=items[0]["ticker"] if items else None,
            sort="ticker",
            direction="previous" if paging.before else "next",
        ),
    )
```

기존 `list_watchlist(conn)`는 바로 제거하지 않는다. 내부적으로 `list_watchlist_page(...).items`를 호출하거나, scan/select처럼 전체 목록이 필요한 곳에서는 `list_watchlist_all(conn)`로 이름을 명확히 분리한다.

권장:

```python
def list_watchlist_all(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return list_watchlist_page(conn, PagingInput(limit=1000)).items
```

단, watchlist가 1000개를 넘을 수 있다면 scan/select도 streaming/iterator로 바꿔야 한다.

### 6.2 Logs keyset paging

정렬:

- default: `id DESC`
- cursor: last seen id
- next condition: `id < after`

```python
def recent_logs_page(conn: sqlite3.Connection, paging: PagingInput) -> PageResult:
    ensure_initialized(conn)
    after_id = validate_int_cursor(paging.after)
    before_id = validate_int_cursor(paging.before)
    limit = paging.limit
    fetch_limit = limit + 1

    if before_id is not None:
        rows = conn.execute(
            """
            SELECT id, action, status, message, metadata_json, created_at
            FROM operation_logs
            WHERE id > ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (before_id, fetch_limit),
        ).fetchall()
        items = [_row_with_json(row) for row in rows[:limit]]
        items.reverse()
    elif after_id is not None:
        rows = conn.execute(
            """
            SELECT id, action, status, message, metadata_json, created_at
            FROM operation_logs
            WHERE id < ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (after_id, fetch_limit),
        ).fetchall()
        items = [_row_with_json(row) for row in rows[:limit]]
    else:
        rows = conn.execute(
            """
            SELECT id, action, status, message, metadata_json, created_at
            FROM operation_logs
            ORDER BY id DESC
            LIMIT ?
            """,
            (fetch_limit,),
        ).fetchall()
        items = [_row_with_json(row) for row in rows[:limit]]

    return _page_result_from_id_items(items, rows, limit, "id_desc", before_id is not None)
```

`recent_failures_page(...)`도 같은 방식으로 구현한다.

### 6.3 공통 page result helper

```python
def _page_result_from_id_items(
    items: list[dict[str, Any]],
    raw_rows: list[Any],
    limit: int,
    sort: str,
    previous: bool,
) -> PageResult:
    has_more = len(raw_rows) > limit
    return PageResult(
        items=items,
        page=PageInfo(
            limit=limit,
            count=len(items),
            has_more=has_more,
            next_after=str(items[-1]["id"]) if items and has_more and not previous else None,
            previous_before=str(items[0]["id"]) if items else None,
            sort=sort,
            direction="previous" if previous else "next",
        ),
    )
```

## 7. Web API 설계

`web.py`에 query parsing helper를 추가한다.

```python
def _paging_from_query(query: str, *, default: int = 20, maximum: int = 100) -> PagingInput:
    params = parse_qs(query)
    return PagingInput(
        limit=validate_page_limit(params.get("limit", [""])[0], default=default, maximum=maximum),
        after=validate_cursor(params.get("after", [""])[0]),
        before=validate_cursor(params.get("before", [""])[0]),
        direction=params.get("direction", ["next"])[0] or "next",
        sort=params.get("sort", ["default"])[0] or "default",
    )
```

Endpoint 변경:

```python
if method == "GET" and path == "/api/watchlist":
    paging = _paging_from_query(query, default=25, maximum=200)
    page = list_watchlist_page(conn, paging)
    return OperationResult.success("Watchlist loaded.", page.to_dict())

if method == "GET" and path == "/api/logs":
    paging = _paging_from_query(query, default=12, maximum=100)
    page = recent_logs_page(conn, paging)
    return OperationResult.success("Logs loaded.", page.to_dict())

if method == "GET" and path == "/api/failures":
    paging = _paging_from_query(query, default=12, maximum=100)
    page = recent_failures_page(conn, paging)
    return OperationResult.success("Failures loaded.", page.to_dict())
```

응답 예:

```json
{
  "ok": true,
  "status_code": 200,
  "message": "Logs loaded.",
  "data": {
    "items": [],
    "count": 0,
    "page": {
      "limit": 12,
      "count": 0,
      "has_more": false,
      "next_after": null,
      "previous_before": null,
      "sort": "id_desc",
      "direction": "next"
    }
  },
  "error": null
}
```

## 8. Frontend 설계

`APP_JS`에 paging state를 둔다.

```javascript
const state = {
  scan: [],
  selection: null,
  watchlistPage: { next_after: null, previous_before: null },
  failuresPage: { next_after: null, previous_before: null }
};
```

Watchlist load:

```javascript
async function loadWatchlist(after = null, before = null) {
  const params = new URLSearchParams({ limit: '25' });
  if (after) params.set('after', after);
  if (before) params.set('before', before);
  const data = await api(`/api/watchlist?${params.toString()}`);
  state.watchlistPage = data.page;
  renderWatchlist(data.items, data.page);
}
```

Watchlist footer:

```javascript
function renderWatchlist(items, page) {
  const target = document.getElementById('watchlist');
  if (!items.length) {
    target.innerHTML = '<div class="empty-state">Add tickers to begin.</div>';
    return;
  }
  target.innerHTML = items.map(renderTickerRow).join('') + `
    <div class="pager">
      <button type="button" data-page-prev ${page.previous_before ? '' : 'disabled'}>Prev</button>
      <button type="button" data-page-next ${page.next_after ? '' : 'disabled'}>Next</button>
    </div>
  `;
  target.querySelector('[data-page-next]')?.addEventListener('click', () => {
    loadWatchlist(page.next_after, null);
  });
  target.querySelector('[data-page-prev]')?.addEventListener('click', () => {
    loadWatchlist(null, page.previous_before);
  });
}
```

CSS:

```css
.pager {
  display: flex;
  gap: 8px;
  justify-content: space-between;
  padding-top: 12px;
}
.pager button {
  width: 100%;
}
```

## 9. CLI 설계

기존 `--limit`은 유지한다.

추가:

```powershell
python -m vcb_alt watchlist list --limit 25 --after MSTR --json
python -m vcb_alt admin logs --limit 20 --after 105 --json
python -m vcb_alt admin failures --limit 20 --before 80 --json
```

Parser 변경:

```python
watchlist_list.add_argument("--limit", type=int, default=25)
watchlist_list.add_argument("--after", default=None)
watchlist_list.add_argument("--before", default=None)

admin_logs.add_argument("--after", default=None)
admin_logs.add_argument("--before", default=None)
admin_failures.add_argument("--after", default=None)
admin_failures.add_argument("--before", default=None)
```

Dispatch 변경:

```python
if args.watchlist_command == "list":
    paging = PagingInput(
        limit=validate_page_limit(args.limit, default=25, maximum=200),
        after=validate_cursor(args.after),
        before=validate_cursor(args.before),
    )
    page = list_watchlist_page(conn, paging)
    return OperationResult.success("Watchlist loaded.", page.to_dict())
```

CLI human 출력에는 page hint를 추가한다.

```python
if "page" in data:
    page = data["page"]
    if page.get("next_after"):
        print(f"Next page: --after {page['next_after']}")
    if page.get("previous_before"):
        print(f"Previous page: --before {page['previous_before']}")
```

## 10. Scan/select와 paging의 관계

중요: `scan`과 `select`는 단순 목록 표시가 아니라 전체 후보 평가 작업이다.

따라서 두 가지 모드를 분리해야 한다.

1. 목록 paging: watchlist/logs/failures 표시용.
2. 작업 범위 input: scan/select 수행 대상 제한용.

`scan --limit`은 임시 smoke용이므로 유지한다. 단, 장기적으로는 아래처럼 명확히 바꾼다.

```powershell
python -m vcb_alt scan --tickers AAPL MSTR NVDA
python -m vcb_alt scan --after MSTR --limit 50
```

하지만 feature 00 범위에서는 display list paging을 먼저 구현하고, scan/select 전체 평가 동작은 유지한다.

## 11. API Contract 업데이트

`API_CONTRACT_V1.md`에 공통 paging query를 추가한다.

```md
### Paging query

- `limit`: 1-100, default endpoint-specific.
- `after`: cursor returned by previous response.
- `before`: cursor for previous page.
- `sort`: endpoint-supported sort key.

Offset-based parameters are intentionally unsupported.
```

각 list response:

```md
data.items: array
data.count: number
data.page.limit: number
data.page.has_more: boolean
data.page.next_after: string|null
data.page.previous_before: string|null
```

## 12. 테스트 계획

### 12.1 DB tests

`tests/test_db.py`

- watchlist page 1 returns first N tickers.
- watchlist page 2 uses `after`.
- logs page uses id cursor descending.
- failures page uses id cursor descending.
- invalid cursor returns `ValidationError`.
- limit > maximum returns `ValidationError`.

예:

```python
def test_recent_logs_page_uses_keyset_cursor(self) -> None:
    for index in range(30):
        log_operation(conn, f"action-{index}", "success", "ok")
    first = recent_logs_page(conn, PagingInput(limit=10))
    second = recent_logs_page(conn, PagingInput(limit=10, after=first.page.next_after))
    self.assertEqual(len(first.items), 10)
    self.assertEqual(len(second.items), 10)
    self.assertLess(second.items[0]["id"], first.items[-1]["id"])
```

### 12.2 Web tests

`tests/test_web.py`

- `/api/watchlist?limit=2` returns page object.
- `/api/watchlist?limit=2&after=AAPL` returns next records.
- `/api/logs?limit=2` returns page object.
- unauthorized public mode still blocks paged list endpoints.

### 12.3 CLI tests

`tests/test_cli.py`

- `watchlist list --limit 2 --json` returns page metadata.
- `admin logs --limit 2 --after <cursor> --json` returns next page.

## 13. Backward compatibility

기존 소비자 영향:

- `data.items`와 `data.count`는 유지한다.
- `data.page`만 추가한다.
- CLI `--limit`은 계속 지원한다.
- 기존 `/api/watchlist` 호출은 첫 페이지를 반환한다. 단, 현재 전체 반환에서 첫 page 반환으로 바뀌므로 watchlist가 25개를 넘는 경우 UI가 page controls를 써야 한다.

## 14. Migration 필요 여부

DB migration은 필수 아님.

하지만 성능을 위해 인덱스를 명시해도 좋다.

```sql
CREATE INDEX IF NOT EXISTS idx_watchlist_ticker ON watchlist(ticker);
CREATE INDEX IF NOT EXISTS idx_failed_jobs_id ON failed_jobs(id DESC);
CREATE INDEX IF NOT EXISTS idx_operation_logs_id ON operation_logs(id DESC);
```

`watchlist.ticker`는 primary key라 별도 인덱스가 이미 존재한다. `id`는 INTEGER PRIMARY KEY라 rowid 기반 조회가 가능하다. 따라서 실제 migration은 선택 사항이다.

## 15. 구현 순서

1. `models.py`에 `PagingInput`, `PageInfo`, `PageResult` 추가.
2. `validation.py`에 paging validator 추가.
3. `db.py`에 `list_watchlist_page`, `recent_logs_page`, `recent_failures_page` 추가.
4. 기존 `list_watchlist`, `recent_logs`, `recent_failures`는 wrapper로 유지.
5. `web.py` query parser와 list endpoints 수정.
6. `cli.py` parser에 `--after`, `--before`, list `--limit` 추가.
7. `APP_JS`에 watchlist/failures paging state와 buttons 추가.
8. `APP_CSS`에 pager 스타일 추가.
9. tests 추가/수정.
10. README, API_CONTRACT_V1, TESTING, CHANGELOG 업데이트.
11. 검증 명령 실행.

## 16. 완료 기준

- SQL에 `OFFSET`이 없다.
- 모든 list response가 `page` metadata를 포함한다.
- watchlist/logs/failures가 cursor로 다음 페이지를 조회한다.
- 기존 CLI/API 기본 호출이 깨지지 않는다.
- public web token guard가 paged endpoints에도 적용된다.
- tests/typecheck/lint/compileall 통과.

## 17. 리스크와 대응

### 리스크 1: 이전 페이지 처리 복잡도

대응: 첫 구현은 `after` next page를 우선하고, `before`는 watchlist/logs/failures에만 제한적으로 지원한다.

### 리스크 2: scan/select와 list paging 혼동

대응: `scan/select`는 작업 수행이고, `watchlist/logs/failures`는 목록 표시라고 문서화한다.

### 리스크 3: cursor 노출

대응: 현재 cursor는 ticker 또는 integer id라 민감정보가 아니다. 향후 multi-tenant에서는 opaque signed cursor로 바꾼다.

### 리스크 4: 동시 변경 중 중복/누락

대응: offset보다 keyset이 안정적이다. 완전한 snapshot consistency는 PostgreSQL transaction/isolation 도입 시 해결한다.

## 18. 향후 SaaS 버전 확장

1000-user SaaS에서는 cursor를 opaque token으로 바꾼다.

예:

```json
{
  "sort": "created_at_id_desc",
  "last_id": 391,
  "last_created_at": "2026-05-17T14:00:00Z",
  "tenant_id": "tenant_123"
}
```

이를 base64url JSON + HMAC signature로 감싸면 사용자가 cursor 내용을 조작할 수 없다.
