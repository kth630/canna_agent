# Claude prompt — B: semantic validation and deterministic compiler

`COMMON.md`의 모든 지시를 적용하라. 당신은 workstream B 담당자다.

## 목표와 경계

F Retriever가 선택한 Runtime View 후보와 HCX semantic query를 서버가 독립 검증하고
Product 실행기가 소비할 수
있는 결정적 logical plan으로 변환하는 production core를 만든다. 공식 데이터 적재,
Ontology/SHACL, Semantic Registry 생성, 후보 retrieval, physical SQL/DuckDB 실행, Evidence,
holdings, API 배포는 담당하지 않는다.

추가로 읽을 문서:

- `provenance/experiments/stage_0a_semantic_grounding/FINDINGS_REVISED.md`
- `provenance/experiments/stage_1_runtime_view/FINDINGS.md`
- `provenance/experiments/stage_1_open_decisions/EVIDENCE.md`

`src/canna/experiments/**`와 기존 experiment fixture는 읽기 전용 기록이며 production에서
import하지 않는다.

## Owned paths

- `src/canna/runtime_view/**`
- `src/canna/semantic/**`
- `src/canna/compiler/**`
- `tests/runtime_view/**`
- `tests/semantic/**`
- `tests/compiler/**`
- `provenance/workstreams/20260830_preintegration_parallel/b_semantic_compiler/**`

## Batch 1 구현

1. F가 handoff한 dataset/field/predicate/entity candidate와 request-scoped opaque ref를
   소비하는 model을 만든다. stable semantic ID는 모델 payload에 노출하지 않는다.
2. semantic query에서 target, explicit requirement+source span, ref, filter, relationship,
   grouping/aggregation/order/output/limit, bounded comparison/nested reuse, unresolved/ambiguous
   근거를 묶음 단위로 보존한다.
3. ref 존재·scope·type·dataset membership·allowed operation·grain compatibility·enum·operator·
   order·limit과 explicit requirement 누락을 검증한다.
4. HCX의 `mapped` 판정만 신뢰하지 않고 invalid/unresolved/ambiguous/missing requirement를
   구조화된 결과로 남긴 뒤 fail closed한다.
5. source span은 모델 offset을 신뢰하지 않는다. 실제 증거 범위를 넘는 fuzzy 정렬을
   production 규칙으로 승격하지 말고 workstream-local 선택지로 보고한다.
6. 관계 방향은 모델의 traversal 값을 신뢰하지 않는다. entity role/domain/range로 유일하게
   결정되는 경우만 bounded rule로 처리하고 same-grain 또는 양 endpoint 지목은 막는다.
7. 비교 승격은 실제 증거 범위를 넘겨 일반화하지 않는다. 명백한 anchor와 동일 metric 등
   충분한 신호가 없으면 실행 plan을 만들지 않는다.
8. 산출물은 physical column/SQL/JOIN/arbitrary ID가 없는 canonical logical plan이다.
9. candidate 순서, Registry 선언 순서, opaque ref 값, requirement 입력 순서를 바꿔도 같은
   의미의 canonical plan이 나오는지 검증한다.
10. B→C adapter 요구를 `HANDOFF.md`에 제안한다.

자연어 fixture를 새로 만들지 말고 synthetic Registry와 직접 구성한 semantic records로
검증한다.

## 수용 기준

- 발명한 ref와 cross-dataset field를 거부한다.
- requirement, operator, direction, limit 오류를 조용히 교정하거나 버리지 않는다.
- 같은 입력 의미가 순서와 request-scoped ref 값에 무관하게 같은 plan을 만든다.
- plan에 physical binding과 SQL이 없다.
- Registry 밖 alias/field/predicate allowlist가 없다.
- production code가 experiments 또는 tests fixture를 import하지 않는다.

## 검증

- `uv run pytest -q tests/runtime_view tests/semantic tests/compiler`
- `uv run ruff check src/canna/runtime_view src/canna/semantic src/canna/compiler tests/runtime_view tests/semantic tests/compiler`
- `uv run pytest -q tests/test_architecture_guards.py`
- `git diff --check`
- `git status --short`

semantic query 논리 계약, provider wire 계약, 실제 data grain/coverage 또는 B↔C 공유 interface를
확정해야만 진행할 수 있으면 중단·보고하라.
