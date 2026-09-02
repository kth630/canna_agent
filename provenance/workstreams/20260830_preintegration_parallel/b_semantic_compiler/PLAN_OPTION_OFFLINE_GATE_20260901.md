# 큰그림 게이트 — HCX 역할 축소안 offline 반증 실험 (2026-09-01)

상태: **실험 전용 게이트 / production 구현 아님 / 아키텍처 변경 아님**

## 1. 시스템 수준 목적

`HCX_ROLE_REDUCTION_CONTRACT_PROPOSAL_20260901.md`의 전제 하나를 반증한다. 전제는
"기존 Runtime View와 승인된 질문 metadata만으로 서버가 explicit semantic anchor,
requirement frame, RequirementOption과 PlanOption 후보를 빠짐없이 생성할 수 있다"이다.
이 전제가 무너지면 HCX 역할 축소는 wire 단순화가 아니라 **회계 책임을 서버가 감당하지
못하는 곳으로 옮기는 변경**이 되므로 구현으로 진행하지 않는다.

## 2. 문항이 아닌 일반화된 capability

측정 대상은 특정 질문의 정답이 아니라 다음 네 capability다.

1. `deterministic_span_ledger`: 질문 원문에서 semantic anchor와 requirement frame을
   결정적으로 회수하고, 잔여 span을 허용된 non-requirement 사유로만 분류한다.
2. `bounded_option_generation`: Runtime View 후보에서 type/family/grain/operation/
   period·unit·currency/domain·range hard prune 뒤 RequirementOption을 만든다.
3. `atomic_plan_materialization`: 양립 가능한 조합만 PlanOption으로 만들고 cap 정책이
   lossy면 전체를 차단한다.
4. `stable_plan_identity`: 후보 순서·requirement 순서·요청 salt와 무관하게 같은 의미가
   같은 equivalence key와 CanonicalPlan preview를 만든다.

## 3. 영향을 받는 아키텍처 계층 — 이번 실험에서는 0

읽기 전용으로 재사용: `canna.runtime_view.spans`, `canna.runtime_view.canonicalize`
(문법표 4종과 canonicalizer 4종), `canna.runtime_view.contract`,
`canna.runtime_view.view`/`registry_facts`/`execution_facts`, `canna.retrieval`.

새로 만드는 것은 실험 전용 owned path뿐이다.

- `src/canna/experiments/plan_option_probe/`
- `tests/experiments/test_plan_option_probe.py`
- `provenance/.../b_semantic_compiler/PLAN_OPTION_OFFLINE_*_20260901.{md,json}`

production package(`src/canna/runtime_view/`, `src/canna/execution/`,
`src/canna/registry/`, `src/canna/retrieval/`), shared contract(`contracts/`),
`ARCHITECTURE.md`, Registry·Ontology·DuckDB 산출물은 **수정하지 않는다.**
HCX live, embedding live, DB build/write, `/answer` 연결, commit, push는 **0회**다.

## 4. 변경되는 계약 — 없음

이 실험은 계약을 바꾸지 않고 제안된 계약이 성립하는지만 관측한다. 제안서의
`SpanLedger`/`RequirementOption`/`PlanOption`/`PlanOptionSet`은 실험 전용 자료구조로만
구현하며, 통과하더라도 그 자체로 production 계약 승인이 아니다.

## 5. data grain·coverage·freshness·실패 의미

- 후보의 family/grain/period/unit/currency/allowed_operations는 view source가 선언한
  값만 사용하고 추론하지 않는다. 선언이 없으면 `prune_axis_unavailable`로 **차단**하고
  통과로 처리하지 않는다.
- coverage/freshness 부족은 semantic option을 삭제하지 않고
  `execution_constraints`로 보존한다. 실행 가능 주장은 하지 않는다.
- `semantic_status`(mapped/unresolved/ambiguous), `canonicalization_status`,
  `execution_readiness`는 서로 다른 세 축으로 분리 보존한다. 하나라도 합치면 실패다.
- `choice_required`(안전한 복수 후보)와 `materially_ambiguous`(결정 근거 부재)를 분리한다.
- lossy truncation은 부분 성공이 아니라 `candidate_space_truncated` 전체 차단이다.

## 6. 금지할 하드코딩과 허용할 안정 상수

금지(실험 코드 포함):

- CQ ID, `test_id`, 정확한 평가 질문 문자열, case별 expected answer를 분기 조건으로 사용
- 실제 Registry stable semantic ID, family ID, physical table/column을 코드 상수로 기재
- 고정 상품명·날짜·행 수·현재 coverage 수치
- fixture의 expected 값을 생성기에 주입(생성기는 gold를 보지 않는다)

허용(근거를 코드 주석과 본 게이트에 기록):

- production `canonicalize.py`가 이미 소유한 문법표 4종을 **import해서** 재사용
  (새로 베끼지 않는다)
- `contract.py`의 requirement kind 8종·status 3종·grain 2종을 import
- 실험 전용 policy 객체 하나가 소유하는 잠정 cap 8/8/32/16 (production 상수 아님)
- 새로 추가하는 유일한 어휘: 한국어 **조사·연결어·공손·담화 표지 allow-list**.
  이것은 제안서 5.1의 `non_requirement_reason` 4종을 구현하는 데 필요하고,
  도메인 어휘가 아니라 언어 어휘이며, `canonicalize.py`의 기존 문법표와 같은 성격이다.
  도메인 명사는 이 목록에 넣지 않는다.

## 7. 수용 기준과 보지 않은 변형

corpus는 **기존 사용자 승인 fixture 49문항**뿐이다. 새 자연어 질문을 만들지 않는다.

| split | 파일 | 수 | 용도 |
|---|---|---:|---|
| primary | `runtime_view_probe.jsonl`, `semantic_grounding.jsonl` | 24 | 개발용 |
| holdout | `runtime_view_probe_unseen.jsonl`, `semantic_grounding_regression.jsonl`, `semantic_grounding_verification.jsonl` | 25 | 모든 수정 뒤 1회 |

통과 조건(하나라도 미충족이면 "부분 성공"으로 보고하지 않는다):

1. required semantic anchor 누락 0, requirement frame 누락 0
2. 잘못된 non-requirement 분류 0 (content span을 조사·연결어로 버리지 않음)
3. 제공되지 않은 의미 조합 생성 0
4. semantic/canonicalization/execution 상태 혼합 0
5. arbitrary·cross-request ref가 실행 가능한 경로 0
6. lossy truncation을 성공으로 처리한 사례 0
7. 질문·상품·case별 runtime 하드코딩 0

보지 않은 구조 변형(holdout과 property test로 시험):

- requirement 순서와 target 표면 순서 교환
- 단일/복수 target × 단일/복수 requirement 4조합
- 관계 filter + 속성 output/order, direct와 look-through 방향
- 동일 의미의 복수 binding과 다른 의미의 인접 field
- producer→consumer 1단계 nested reuse, 2 operand comparison
- 후보 수가 각 cap의 직전·정확히 cap·cap+1
- 후보 순서 shuffle과 새 salt 재발급에서의 equivalence key 불변성

## 8. 이 실험이 답하지 않는 것

- production 실행 가능성. Execution Registry에 row provenance/selection policy가 없어
  실제 실행은 계속 `unavailable`이 정답이다.
- HCX가 opaque ref 하나를 실제로 정확히 고르는지. live 호출 금지 범위다.
- prompt budget의 실제 provider token 수. byte 및 근사 token만 추정한다.
