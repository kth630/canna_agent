# Claude prompt — C: Product query and Evidence core

`COMMON.md`의 모든 지시를 적용하라. 당신은 workstream C 담당자다.

## 목표와 경계

검증된 registry-bound execution specification을 받아 Product grain으로 filter/order/count/
aggregate/compare를 실행하고, 결과와 주장 가능 범위를 함께 담는 Evidence core를 만든다.
질문 해석, HCX, 공식 원본 ingestion, holdings, 외부 API envelope는 담당하지 않는다.

추가로 읽을 문서:

- `provenance/experiments/stage_0c_data_discovery/FINDINGS.md`
- A/B의 `HANDOFF.md`는 해당 owner가 frozen이라고 표시한 경우에만 읽고 통합한다.

## Owned paths

- `src/canna/product/**`
- `src/canna/evidence/**`
- `tests/product/**`
- `tests/evidence/**`
- `provenance/workstreams/20260830_preintegration_parallel/c_product_evidence/**`

## Batch 1 구현

A의 frozen handoff가 없으므로 실제 physical schema를 추측하지 않는다. 임시 DuckDB와 synthetic
binding으로 다음 core만 구현한다.

1. C-local execution request protocol을 최소 정의하고 B adapter 요구를 `HANDOFF.md`에 제안한다.
2. physical table/column은 주입된 binding에서만 받는다.
3. parameterized DuckDB query로 filter, order+limit, count, aggregate, product comparison의
   최소 구조를 구현한다. 미구현 operation은 명시적으로 실패한다.
4. measure의 0/결측은 해당 연산 모집단에서 제외하되 원본을 수정하지 않는다. code/flag의
   0은 binding metadata로 구분한다.
5. source-row 중복이나 관계 확장으로 product count/ranking이 부풀지 않도록 grain을 검증한다.
6. Evidence에 source/record, requested/effective as-of, freshness, filters/aggregation/order/limit,
   applied rules, result grain, full/observed universe, exclusions/failures, result rows를 보존한다.
7. `answer_status`, `reasons`, `universe`를 하나의 enum으로 합치지 않는다.
8. incomplete coverage에서 global top-k/count/max/min과 negative/universal claim을 막는다.
   observed positive lookup은 observed universe가 명시된 경우에만 scoped partial로 표현한다.
9. target outside coverage는 false가 아니라 unknown/refused다.
10. unit/currency/period/grain/freshness가 호환되지 않는 비교를 fail closed한다.
11. C→E Evidence handoff를 제안하되 `retrieved_context` 공개 schema로 확정하지 않는다.

## 수용 기준

- 사용자 값이 SQL 문자열에 직접 삽입되지 않는다.
- 0/결측 적용 규칙과 Evidence `applied_rules`가 일치한다.
- 중복 source row가 product 결과를 부풀리지 않는다.
- observed를 full/global로 주장하지 않는다.
- incompatible comparison과 coverage 밖 entity가 fail closed한다.
- A handoff가 없으면 실제 데이터 완료라고 보고하지 않는다.

## 검증

- `uv run pytest -q tests/product tests/evidence`
- `uv run ruff check src/canna/product src/canna/evidence tests/product tests/evidence`
- `uv run pytest -q tests/test_architecture_guards.py`
- `git diff --check`
- `git status --short`

shared Evidence 공개 schema, coverage policy, physical binding 또는 B↔C interface 확정이 필요하면
중단·보고하라.
