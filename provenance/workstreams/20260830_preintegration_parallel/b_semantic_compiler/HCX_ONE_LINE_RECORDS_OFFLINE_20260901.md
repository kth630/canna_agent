# HCX one-line records Runtime offline integration — 2026-09-01

## Status

`integrated offline / provider unverified`

이번 작업에서는 HCX live 호출, 외부 API 호출, 운영 DB 조회, commit, push를 수행하지 않았다.
provider 수용성과 실제 생성 품질은 이번 상태의 근거가 아니며 별도 live 승인 전까지
`unverified`다.

## 승인 범위와 책임 경계

시스템 수준 목적은 HCX가 Runtime View의 요청별 opaque ref와 질문 원문 span을 one-line
record로 제출하고, 서버가 기존 parser·semantic validator·canonicalizer를 통과시킨 뒤에만
canonical `execution_values`를 방출하게 하는 것이다. 일반화 단위는 특정 질문이 아니라
`one-line semantic submission ingestion + safe shape diagnostics`다.

변경 계층은 wire notation, 최소 Tool envelope, Runtime View package facade, system guidance,
offline/live harness 입력과 진단이다. grouped-flat parser, semantic validator, canonicalizer,
Execution, Registry, Ontology, DB 계약은 변경하지 않았다. 기존 multiline reader는 완화하거나
삭제하지 않았고 multiline 및 JSON bridge 테스트는 각 모듈에서 직접 import해 계속 검증한다.

데이터 grain·coverage·freshness 규칙은 바뀌지 않는다. one-line reader는 요청별 opaque ref를
그대로 기존 parser에 넘기며, parsing·semantic validation·canonicalization 실패 시 해당
requirement의 `execution_values`는 방출되지 않는다.

## Runtime 연결

1. `one_line_records.py`
   - `ENVELOPE_PROPERTY = "submission_text"`
   - `one_line_parameters_schema()`
   - `parse_tool_arguments()`
   - one-line reader, encoder, guidance, shape diagnostics
2. `schema.hcx_wire_schema()`는 one-line parameters schema의 새 객체를 반환한다.
3. `canna.runtime_view` package facade는 one-line reader/encoder/guidance/envelope parser와
   diagnostics를 재수출한다.
4. 기존 multiline 및 JSON bridge 테스트는 `line_records`와 `hcx_bridge`에서 직접 import한다.
5. Runtime harness system message는 `one_line_submission_guidance()`를 사용한다.
6. offline precondition 및 Runtime integration 제출은 `render_one_line_records()`로 생성한다.
7. opt-in live harness는 one-line envelope parser와 one-line 전용 진단을 사용한다. 이번
   검증에서는 live marker를 실행하지 않았다.

## 진단 계약

진단은 고정 enum, count, boolean만 남긴다.

- `REQ`, `REF`, `DETAIL`, `UNACCOUNTED` line별 count
- `END` count와 위치 유효 여부
- pipe 존재 여부
- `key=value` segment count와 malformed segment count
- unknown record/key/envelope key 존재 여부
- JSON punctuation, bullet prefix, literal backslash-n 존재 여부
- 고정 type/class/finish-reason enum
- 고정 parser problem code enum과 output token count

unknown record/key/envelope 이름, 임의 finish reason, 임의 parser code는 `other` 또는 boolean으로
축약한다. 제출 원문, ref, span, semantic ID, requirement ID, unknown token, hash, credential,
request/response ID는 진단에 기록하지 않는다. 테스트는 실제 Runtime View가 발급한 opaque
ref와 질문 span, synthetic secret token을 진단 직렬화 결과에서 직접 검색해 비유출을
확인한다.

## Offline acceptance evidence

### 핵심 경로

- one-line envelope → reader → grouped-flat parser → semantic validation → canonical
  `execution_values`: 통과
- direction/limit canonicalization 실패 시 `execution_values is None`: 통과
- one-line, 기존 multiline, grouped-flat, canonical JSON query 동등성: 통과
- 실제 Semantic/Execution Registry로 만든 Runtime View의 per-request opaque ref 사용: 통과
- 진단 allow-list와 원문/ref/span/semantic ID/requirement ID/unknown token 비유출: 통과
- END 위치, malformed segment, unknown record/key, JSON, bullet, literal backslash-n 변형: 통과

### 실행 명령과 결과

```text
uv run --cache-dir .tmp/uv-cache pytest \
  tests/runtime_view/test_one_line_records.py \
  tests/runtime_view/test_runtime_integration.py \
  tests/runtime_view/test_hcx_runtime_view_precondition.py \
  tests/runtime_view/test_tool_schema.py -q
80 passed

uv run --cache-dir .tmp/uv-cache pytest \
  --basetemp=.tmp/pytest-one-line-full-20260901-b -q
1102 passed, 6 deselected

uv run --cache-dir .tmp/uv-cache ruff check src tests
All checks passed

git diff --check
exit 0
```

첫 전체 pytest 시도는 공유 `.tmp/pytest`가 다른 프로세스에 의해 점유되어 130개 setup이
`WinError 5`로 실패했다. 기존 디렉터리를 삭제하지 않고 전용 basetemp로 재실행해 전체
offline suite가 통과했다.

저장소 전체 `uv run --cache-dir .tmp/uv-cache ruff check .`는 이번 diff에 포함되지 않은
기존 clean 파일 `scripts/audit_0d_inventory.py`의 import 정렬 1건과 `datetime.UTC` 규칙
1건 때문에 실패했다. 원자적 Runtime 변경 범위를 벗어나므로 해당 파일은 수정하지 않았다.
이번 변경을 포함한 `src`와 `tests` 전체 Ruff는 통과했다.

## Codex audit

- 일반화 단위: 질문별 분기가 아닌 one-line record notation과 동일 기존 semantic parser 경로.
- 새 안정 상수: `submission_text`, `REQ|REF|DETAIL|UNACCOUNTED`, `END`, `|`, `=`, 기존
  grouped-flat key·enum에서 파생한 순서, 진단 field/type/class enum. Tool wire와 안전한
  진단 형식이 소유하는 상수이므로 허용된다.
- 금지 하드코딩: CQ ID, question/case ID, 정확한 평가 질문, 상품명, 날짜, row count,
  coverage, Registry semantic ID 분기 없음.
- 보지 않은 변형: record 순서, optional END, 중간/중복 END, unknown record/key, malformed
  segment, JSON/bullet/literal backslash-n, 내부 `=` 보존, `|`/line-break encoder refusal,
  잘못된 ref kind와 canonicalization 실패.
- 계약/아키텍처 이탈: 없음. 정확 wire encoding은 `ARCHITECTURE.md`에서
  Experiment-dependent이며 논리 semantic query, validator, compiler, Execution 경계는 유지됨.
- 데이터 한계: provider 생성 결과와 latency는 검증하지 않았고, coverage/freshness 및 실제
  실행 가능성은 이 wire 통합의 판정 범위가 아니다.

## 남은 결정

다음 상태 전환은 별도 승인된 HCX live 1회 이상에서 one-line Tool emission, opaque ref와 span
보존, parser/semantic validation 결과를 확인한 뒤에만 가능하다. 그 전까지 provider 상태는
`unverified`로 유지한다.
