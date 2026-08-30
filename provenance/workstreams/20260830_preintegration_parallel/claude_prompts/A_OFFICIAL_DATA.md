# Claude prompt — A: official data execution foundation

`COMMON.md`의 모든 지시를 적용하라. 당신은 workstream A 담당자다.

## 목표와 경계

공식 Excel을 읽기 전용으로 보존하면서 공식 네 상품군 전체를 기존 Ontology와 대조할
data evidence를 만들고, 승인된 조회 grain에 따라 재현 가능한 파생 store와 Execution
Registry의 공식 데이터 부분을 만든다. 질문 해석, HCX,
Product query/Evidence, holdings, 공개 API는 담당하지 않는다.

추가로 읽을 문서:

- `provenance/experiments/stage_0c_data_discovery/FINDINGS.md`
- `provenance/MIGRATION_CHECKLIST.md`
- `provenance/MIGRATION_MANIFEST.json`

## Owned paths

- `src/canna/data/official/**`
- `src/canna/registry/execution/**`
- `scripts/build_official_store.py`
- `tests/data/official/**`
- `provenance/workstreams/20260830_preintegration_parallel/a_official_data/**`
- 재현 가능한 생성물 `data/processed/official/**`

정본, shared packaging, API, experiments, 다른 workstream 경로는 읽기 전용이다.

## Batch 1 구현

1. `MIGRATION_MANIFEST.json`을 source discovery/hash 검증의 정본으로 사용한다. hash를 코드에
   중복 복사하지 않는다.
2. workbook을 read-only/data-only 방식으로 읽고 원본 무결성을 전후 확인한다.
3. 국내채권·국내 ETF·해외 ETF·공모펀드 전체의 field, identifier, source-row/product grain,
   unit/currency/period, effective date와 queryable universe를 대조표 입력으로 기록한다.
   국내 ETF 기존 초안은 보존하되 전체 공통 schema의 정답으로 자동 승격하지 않는다.
4. source-row grain과 product grain, stable identifier 후보를 분리한다.
5. 각 field의 관측 type, meaning 근거, measure/code 구분, unit/currency/period, source,
   effective date, queryable universe를 기록한다. 근거 없는 항목은 unresolved로 둔다.
6. measure의 0/결측 제외와 code/flag의 0을 구분한다.
7. 결정적 DuckDB 또는 Parquet 파생 store와 build manifest를 만든다.
8. 손상 source, hash mismatch, required field 부재는 fail closed한다.
9. synthetic workbook으로 filename/column order/schema 변화 테스트를 만들고, 별도
   `real_data` marker로 공식 원본 실행을 검증한다.
10. F의 Ontology 대조에 필요한 data fragment와 B/C가 소비할 store/Execution Registry
    handoff를 `HANDOFF.md`에 제안하되 공유 계약으로 선언하지 않는다.

현재 행 수, coverage, 날짜를 runtime 성공 기준 상수로 사용하지 말라. 국내채권 `pd_no`를
곧바로 source-row 유일 key로 일반화하거나 공모펀드 총보수를 임의 합성하지 말라.

## 수용 기준

- 원본 hash/size/mtime가 작업 전후 동일하다.
- 동일 입력의 두 build가 논리적으로 동일하다.
- 공식 네 상품군의 queryable store와 dataset별 미지원·미확정 상태가 생성된다.
- source/table/field/grain/freshness/exclusion을 추적할 수 있다.
- 다른 filename/column order에 위치 하드코딩 없이 대응하거나 명시적으로 실패한다.
- 미확정 의미를 supported capability로 승격하지 않는다.

## 검증

- `uv run pytest -q tests/data/official`
- `uv run pytest -q -m real_data tests/data/official`
- `uv run ruff check src/canna/data/official src/canna/registry/execution scripts/build_official_store.py tests/data/official`
- `uv run pytest -q tests/test_architecture_guards.py`
- `git diff --check`
- `git status --short`

identifier/grain/unit/code 의미, shared Registry schema, packaging 변경이 필요하면 즉시 중단해
공통 형식으로 보고하라.
