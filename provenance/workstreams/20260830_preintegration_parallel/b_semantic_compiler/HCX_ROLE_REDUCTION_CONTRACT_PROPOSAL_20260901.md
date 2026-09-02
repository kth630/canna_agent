# HCX 역할 축소 계약 제안 — 전체 PlanOption opaque ref 선택

상태: **v2 검토안 / 사용자·Codex 승인 전 제안 전용 / 정본 아님 / 구현 지시 아님**

이 문서는 `ARCHITECTURE.md`, `IMPLEMENTATION_PLAN.md`, Registry, Ontology, DB 또는 코드를
수정하지 않는다. live HCX·embedding 호출과 DB build·쓰기도 수행하지 않았다. 승인되면 먼저
Confirmed 아키텍처의 책임 경계와 논리 계약을 별도 결정으로 수정해야 하며, 이 문서 자체를
구현 승인으로 해석하지 않는다.

## 1. 설계 전 큰그림 게이트

| 항목 | 제안의 경계 |
|---|---|
| 시스템 수준 목적 | HCX의 자연어 Intent 판별을 유지하되 실행 권한을 서버가 미리 생성·검증한 요청 단위 계획 후보 하나의 선택으로 제한하고, Evidence 없는 실행을 막는다. |
| 일반화 capability | 특정 질문이 아니라 `bounded plan-option generation → opaque plan selection → exact membership validation → deterministic CanonicalPlan materialization`이다. |
| 영향 계층 | Runtime View 이후의 질문 span 회계, 후보 계획 생성, HCX ①, Tool wire, 요청 상태, semantic validator/compiler 입력 경계가 바뀐다. Registry·Ontology·DB·Evidence·HCX ②는 원칙적으로 보존한다. |
| 바뀌어야 할 Confirmed 계약 | HCX ①의 “explicit span을 회계하고 semantic query를 작성”하는 책임과 semantic-query 논리 계약의 작성 주체를 서버로 옮긴다. HCX는 제공된 전체 plan option 하나만 선택한다. |
| grain·coverage·freshness·실패 의미 | option 생성과 선택 후 검증 모두에서 Registry의 family, grain, operation, coverage, freshness를 보존한다. 누락·모호성·lossy truncation·만료·cross-request·canonicalization 실패는 `no_data`나 false가 아니라 구조화된 차단 사유다. |
| 금지 하드코딩 | CQ/question/case ID, 정확한 평가 질문, 상품명, 날짜, 행 수, 현재 coverage, stable semantic ID, field/predicate/join binding을 질문별 분기나 중복 상수로 두지 않는다. |
| 허용 안정 상수 | 승인된 Tool/property 이름, ref kind/version, 상태·reason enum, span role, 구조 상한 정책명, 승인된 canonicalizer 문법과 Registry 생성 stable enum이다. 아래 cap 숫자와 ref 수명 방식은 아직 안정 상수가 아니라 반증·설계 검토 대상이다. |
| 수용 기준 | 식별된 explicit semantic anchor와 requirement span 회계, arbitrary/cross-request ref 거부, 제공되지 않은 조합 실행 불가, 선택 전후 동일 CanonicalPlan, lossy truncation 차단, Registry/질문 문자열 독립 구조 테스트를 통과해야 한다. SpanLedger recall과 option 수 분포를 별도 반증 실험으로 측정해야 한다. |
| 보지 않은 구조 변형 | 단일/복수 target, 단일/복수 requirement, 관계+속성, 순서가 바뀐 동일 구조, 동일 의미 ref 재발급, bounded nested result reuse, 호환 metric의 bounded comparison을 다룬다. 새 자연어 fixture는 사용자 승인 전 만들거나 등록하지 않는다. |

## 2. 아키텍처 판정

이 변경은 **Experiment-dependent wire 변경만이 아니다.** `selected_plan_ref` 하나인 정확한
Tool encoding은 `ARCHITECTURE.md` 9절의 Experiment-dependent Tool surface에 속하지만,
다음 두 변경은 Confirmed 계약 변경이다.

1. `ARCHITECTURE.md` 2~3절의 HCX ① 책임을 “explicit requirement accounting + semantic
   query 작성”에서 “서버가 작성한 완전한 plan option 하나 선택”으로 바꾼다.
2. 4절의 Confirmed semantic-query 논리 정보는 유지하되 **작성 주체**를 HCX에서 서버
   `PlanOptionGenerator`로 바꾸고, HCX wire에는 그 정보를 싣지 않는다.

따라서 사용자·Codex가 Confirmed 변경을 먼저 승인하지 않으면 이 제안을 구현해서는 안 된다.
외부 `GET /answer` envelope와 “Intent 분석 및 최종 답변에 HCX 사용” 경계는 바뀌지 않는다.

## 3. 세 대안 비교와 권고

| 대안 | 원자성 | 조합 폭발 | requirement 회계 | provider 부담 | 판정 |
|---|---|---|---|---|---|
| 1. requirement별 option ref 복수 선택 | 낮다. HCX가 선택한 ref들의 조합이 서버가 발행한 완전 계획인지 다시 증명해야 한다. | wire에서는 작지만 모델이 새 조합을 만들 수 있어 조합 검증이 다시 필요하다. | 누락·중복·서로 다른 target 간 불일치 위험이 남는다. | 배열 또는 복수 record 생성이 필요하다. | 기각 |
| 2. 전체 PlanOption ref 하나 선택 | 높다. exact membership 하나로 계획 전체를 검증한다. | 서버가 모든 조합을 평면 생성하면 폭발한다. | PlanOption 자체가 완전 회계라면 강하다. | required string 하나로 최소다. | 외부 계약으로 채택 |
| 3. 내부 requirement factorization + wire 전체 plan ref | 높다. wire는 2와 같다. | hard prune·requirement dedup·bounded join으로 제어한다. | requirement별 상태와 span ledger를 유지한다. | required string 하나다. | **권고안** |

권고안은 3이다. 대안 2의 원자적 wire를 사용하되 서버 내부에서는
`RequirementOption`을 먼저 만들고 검증된 조합만 `PlanOption`으로 materialize한다. HCX는
`RequirementOption` ref를 보거나 조합하지 않으며, 서버가 발행하지 않은 조합은 ref 자체가
존재하지 않는다.

## 4. 현행 계약 → 제안 계약 책임 변화

| 단계 | 현행 Confirmed/구현 경계 | 제안 경계 |
|---|---|---|
| Runtime View | dataset/field/predicate/entity 후보를 HCX에 노출 | 같은 후보와 server-side semantic ID map을 option generator에 제공. HCX에는 안전한 plan 요약과 plan ref만 제공 |
| explicit span 회계 | HCX가 requirement/source span/status 작성 | 서버가 `SpanLedger`와 requirement frame을 만들고 각 option이 이를 완전하게 덮는지 검증 |
| semantic refs | HCX가 Runtime View opaque ref를 역할별로 복사 | 서버가 ref를 역할별로 조합·검증. HCX는 field/predicate/entity ref를 보지 않음 |
| condition/order/limit | HCX가 역할과 원문 span 제출, 서버 canonicalize | 서버가 option 생성 전에 기존 deterministic span alignment/canonicalizer를 적용 |
| relationship | HCX가 predicate/anchor ref 제출 | 서버가 Runtime View 후보와 domain/range/anchor type으로 가능한 relation option만 생성 |
| HCX ① | semantic query 문서 작성 | 제공된 전체 `plan_ref` 하나 선택 |
| provider parser | JSON/grouped-flat/one-line 문서를 parse | Tool object에서 required string `selected_plan_ref` 하나만 읽음 |
| semantic validator | 모델이 작성한 `SubmittedQuery`를 검증 | 서버가 만든 RequirementOption/PlanOption을 생성 시 검증하고, 선택 시 snapshot과 membership을 재검증 |
| CanonicalPlan | HCX 제출을 서버가 canonicalize해 구성 | 선택된 저장 PlanOption의 검증된 구성요소로 결정적으로 구성. provider 문자열에서 semantic 구조를 복원하지 않음 |
| failure accounting | HCX status와 server decision을 함께 보존 | generator status와 selection validation을 보존. HCX가 mapped/unresolved/ambiguous를 선언하지 않음 |

## 5. 논리 계약

### 5.1 SpanLedger — 검증 전 production 전제 아님

질문 원문의 위치를 기준으로 한 서버 내부 원장이다.

- `question_binding`: 요청 내부 원문 exact equality 또는 요청별 keyed digest. 영구 로그와
  Evidence에는 원문·digest를 남기지 않음
- `spans[]`: `span_id`, `start`, `end`, `exact_text`, `role`
- `role`: `target | condition | requirement | relationship | comparison | nested_reuse |
  non_requirement`
- `requirement_id`: explicit requirement에 속하면 필수
- `non_requirement_reason`: `connective | politeness | discourse | punctuation`만 허용
- `accounting_status`: `accounted | unresolved | ambiguous`
- `basis`: deterministic rule/retrieval provenance; HCX 판단값이 아님
- `anchor_inventory`: deterministic recognizer와 Retriever가 식별한 content-bearing semantic
  anchor 및 출처
- `unclassified_content_spans[]`: 조사·연결어·문장부호로 증명되지 않은 잔여 content span

모든 **식별된 explicit semantic anchor와 requirement span**은 정확히 한 번 덮여야 한다.
조사·연결어·공손 표현·문장부호는 허용된 `non_requirement_reason`으로 분류할 수 있지만,
content-bearing 잔여 span을 `non_requirement`로 버릴 수 없다. 겹침, anchor 누락 또는
`unclassified_content_spans`가 있으면 option set 전체가 non-selectable이다. exact 또는 기존
승인 정규화 후 exact alignment만 허용하며 fuzzy alignment는 허용하지 않는다.

이 계약만으로 서버가 질문의 explicit requirement를 빠짐없이 찾는다고 가정하지 않는다.
production 승인 전 별도 offline 반증 실험에서 승인 질문의 semantic-anchor recall, 조사·수식어
오분류, requirement frame 누락과 구조 변형을 측정한다. 실패하면 역할 축소 방향 전체를 성공
처리하지 않고 SpanLedger 생성 계층을 다시 설계한다.

### 5.2 RequirementOption

한 explicit requirement의 한 가지 완전한 의미 해석이다. 서버 내부 논리 필드는 다음이다.

- `requirement_option_ref`: 요청 단위 opaque internal ref; HCX 비노출
- `requirement_id`, `kind`, `source_span_ids`
- `semantic_status`: `mapped | unresolved | ambiguous`
- `canonicalization_status`: `ready | refused | unavailable`
- `execution_readiness`: `not_evaluated | ready | blocked`
- `target_dataset_refs[]`
- `output_field_refs[]`
- `conditions[]`: `field_ref`, `comparison_span_id`, `value_span_id`
- `ordering`: `field_ref`, `direction_span_id` 또는 없음
- `limit_span_id` 또는 없음
- `aggregation`: `field_ref`, `function_span_id` 또는 없음
- `grouping_field_refs[]`
- `relationship`: `predicate_ref`, `anchor_entity_ref` 또는 없음
- `result_reuse`: bounded producer requirement와 result grain 연결 또는 없음
- `comparison`: bounded operand requirement/target refs와 공통 metric constraint 또는 없음
- `canonicalization_record`: 기존 canonicalizer 결과와 모든 failure
- `semantic_validation_record`: family/grain/type/operation/domain/range 검증 결과
- `execution_constraints`: 필요한 coverage/freshness/Evidence 조건; readiness 성공 주장이 아님
- `blocking_reasons[]`
- `equivalence_key`: 서버 내부 stable semantic ID, 역할, canonical span/value로 만든 dedup key

`semantic_status=mapped`는 모든 의미 slot이 허용된 Runtime View ref에 연결됐다는 뜻이며
canonicalization이나 실제 실행 가능성을 뜻하지 않는다. canonicalization 실패는 별도
`canonicalization_status=refused`, Registry provenance·coverage·freshness 부족은 별도
`execution_readiness=blocked`로 남긴다. 후보 없음은 `unresolved`, 질문 자체에 결정 근거가
없어 서로 다른 사용자 의미가 가능한 경우는 `ambiguous`다. 어느 상태도 빈 mapped option이나
`no_data=false`로 바꾸지 않는다.

### 5.3 PlanOption

질문 전체를 덮는 원자적 선택 단위다.

- `plan_ref`: HCX에 보이는 유일한 opaque ref
- `requirement_option_refs[]`: 내부 전용
- `span_ledger_digest`
- `requirement_ids[]`와 완전 회계 확인값
- `plan_status`: `candidate_selectable | blocked_unresolved | blocked_materially_ambiguous |
  blocked_truncated | blocked_validation`
- `structure`: targets, requirement dependencies, bounded relation/nested/comparison graph
- `canonical_plan_preview`: 생성 시 기존 validator/canonicalizer로 검증한 서버 내부 결과
- `execution_constraints`: operation, coverage, freshness, evidence requirements의 합집합
- `equivalence_key`: requirement 순서와 요청별 ref 값에 무관한 semantic plan fingerprint
- `display_summary`: 결정적 allow-list template으로 만든 안전한 설명; stable ID, 물리 이름과
  자유 생성 문장 없음
- `blocking_reasons[]`

PlanOption은 모든 explicit requirement를 정확히 한 번 포함해야 한다. 서로 다른
RequirementOption의 target/result grain/dependency가 양립할 때만 조합한다. blocked plan은
감사에는 보존하지만 실행 가능한 선택으로 승격하지 않는다.

### 5.4 PlanOptionSet

- `option_set_id`: 서버 내부 요청 상태 key; HCX 비노출
- `request_scope_id`, `created_at`, `expires_at`, `state`
- `question_binding`, `runtime_view_snapshot_id`
- `semantic_registry_build_id`, `execution_registry_build_id`
- `span_ledger`
- `requirement_options_by_requirement`
- `plan_options_by_ref`
- `generation_status`: `complete | choice_required | no_candidate |
  materially_ambiguous | truncated | invalid`
- `generation_reasons[]`
- `generation_metrics`: hard-pruned, deduplicated, dominated, beam-discarded, materialized counts
- `policy_version`과 적용 cap

서로 다른 구조적·의미적 후보가 모두 안전하게 생성됐고 질문 문맥에 따른 Intent 선택이 남으면
`choice_required`로 HCX selection 단계에 간다. 질문 자체에 필요한 discriminator가 없어 어떤
주체도 하나를 정하면 안 되는 경우만 `materially_ambiguous`로 차단한다. 후보가 하나여도
대회 요구의 Intent 분석 경계를 지키기 위해 HCX가 그 plan 또는 명시적 거부 option을 선택하는
최소 호출을 유지할지는 사용자 결정 사항이다. `truncated`는 부분 성공이 아니라 선택 금지다.

## 6. Runtime View에서 option을 만드는 규칙

1. 질문 원문과 기존 Runtime View를 요청 snapshot으로 고정한다.
2. deterministic span recognizer와 Registry 의미 후보로 `SpanLedger` 및 requirement frame을
   만든다. 허용된 non-requirement 분류 외의 substantive 잔여 span은 즉시 차단한다.
3. 각 requirement의 target 후보를 먼저 확정한 뒤 역할별 field/predicate/entity 후보를
   붙인다.
4. 다음 hard prune을 순서대로 적용한다.
   - **type**: dataset/field/predicate/entity slot kind 불일치 제거
   - **family**: target dataset과 field/predicate의 선언·Execution-scoped family 불일치 제거
   - **grain**: target/result/observation grain 불일치와 relation 뒤 product dedup 불가능 경로 제거
   - **operation**: filter/order/count/aggregate/output/relation operation 미허용 binding 제거
   - **period/unit/currency**: 질문의 명시 span 및 Registry metadata와 exact compatibility가
     증명되지 않는 후보 제거; missing discriminator로 복수 사용자 의미가 남으면
     materially ambiguous
   - **predicate domain/range**: anchor entity class와 target class로 유일한 방향만 유지;
     direction을 모델 선택이나 traversal 문자열에서 받지 않음
   - **coverage/freshness**: 의미 mapping 후보에서 제거하지 않고 execution constraint로
     보존. 의미 선택 뒤 별도 claim-aware execution policy가 `supported | partial | refused`와
     universe를 판정한다. 단위·기간·기준일 불일치로 의미 자체가 양립하지 않는 경우에만
     semantic option compatibility를 차단한다
5. 각 RequirementOption을 기존 semantic validator와 canonicalizer로 검증한다.
6. requirement 내부 exact-equivalent option을 dedup하고, 의미가 같은데 source binding만 여러
   개인 경우 execution selection policy가 유일할 때만 하나로 합친다.
7. requirement들을 bounded compatible join해 PlanOption을 만들고 plan-level dedup 후 HCX에
   노출한다.

Retriever score, embedding 유사도와 후보 순서는 option의 의미를 확정하거나 실행을 승인하는
근거가 아니다. 이들은 후보 회수와 결정적 tie-order에만 사용한다.

## 7. candidate explosion 상한 정책

다음 값은 **승인된 안정 상수가 아니라 offline 반증 실험을 시작하기 위한 잠정값**이다.
실제 requirement/option 분포, prompt byte/token, HCX 선택 정확도와 cap 직전·cap·cap+1 결과를
측정한 뒤 사용자·Codex가 승인해야 한다. 값은 하나의 버전된 `OptionGenerationPolicy`가
소유하며 runtime source 곳곳에 중복하지 않는다.

| 상한 | 제안값 | 의미 |
|---|---:|---|
| explicit requirements | 8 | 초과 시 `structure_limit_exceeded`, 실행 차단 |
| RequirementOption / requirement | 8 | hard prune·exact dedup 뒤의 서로 다른 의미 후보 상한 |
| compatible-join beam | 32 | requirement 하나를 추가할 때 유지할 부분 계획 수 |
| final PlanOption wire cap | 16 | HCX에 제시할 전체 계획 수 |
| nested result-reuse depth | 1 edge | producer 결과를 한 consumer가 쓰는 단일 bounded 재사용 |
| comparison operands | 2 | 두 target/result의 명시적 비교만 허용 |

정렬 key는 Registry/Runtime View의 deterministic provenance, semantic equivalence key,
source span 위치로 고정하며 요청별 ref나 retrieval 반환 순서를 사용하지 않는다.

상한은 **정답을 근사 선택하는 허가가 아니다.** exact duplicate 또는 동일 의미의 strictly
dominated plan 제거는 lossless다. 반면 서로 다른 viable meaning을 beam/cap 때문에 하나라도
버리면 `generation_status=truncated`, reason=`candidate_space_truncated`로 전체 OptionSet을
non-selectable 처리한다. 남은 16개 중 HCX가 골라도 실행하지 않는다. 이 규칙 때문에 cap은
silent wrong answer가 아니라 자원 보호용 fail-closed 경계다.

## 8. ref, exact membership, 만료와 cross-request 거부

- ref는 요청마다 CSPRNG 32-byte salt를 사용해 최소 128-bit opaque token으로 만든다.
- 외부 표기는 예를 들어 `pl_` + 무의미 token일 수 있으나 ref 안에 index, semantic ID,
  family, expiry 또는 digest를 인코딩하지 않는다.
- `plan_options_by_ref`는 현재 요청 context 안에만 존재한다. 형식 검사는 보조 진단일 뿐이고
  실행 권한은 **exact map membership**만 부여한다.
- 기본 계약은 동기 `GET /answer` 요청 수명 안의 in-memory context다. 요청 종료와 함께 ref를
  폐기하고 선택 성공·거부 뒤 즉시 소비한다. 별도 120초 TTL, global store, worker 간 공유는
  현재 계약에 넣지 않으며 비동기/분산 실행이 필요해질 때 별도 승인한다.
- 선택 시 `request_scope_id`, question fingerprint, Runtime View snapshot, 두 Registry build,
  option-set state, expiry, single-use 여부를 모두 대조한다.
- 다른 요청에서 발행된 정상 형식 ref, 임의 ref, 이미 소비된 ref, 만료 ref는 각각
  `selected_plan_ref_not_in_request`, `selected_plan_ref_consumed`,
  `selected_plan_ref_expired` 등으로 차단한다. global ref lookup이나 “가장 비슷한 ref” fallback은
  없다.
- 실행 ref를 로그·Evidence에 재사용하지 않는다. 감사 기록은 비실행 option-set ID와 상태,
  count, reason code만 보존한다.

## 9. 최소 wire와 one-tool 원칙

one-tool 원칙을 유지한다. 첫 vertical slice는 이미 provider 수용과 exact emit이 확인된
`submit_semantic_query` 이름을 유지하고 인자만 required string 하나로 축소하는 안을 우선한다.
`select_plan`으로 이름을 바꾸려면 provider 변수 하나가 다시 생기므로 별도 승인 live 검증이
필요하다.

```json
{
  "name": "submit_semantic_query",
  "parameters": {
    "type": "object",
    "properties": {
      "selected_plan_ref": {"type": "string"}
    },
    "required": ["selected_plan_ref"],
    "additionalProperties": false
  }
}
```

HCX가 보는 option 목록은 서버가 만든 안전한 요약과 opaque ref뿐이다. 예시는 구조
placeholder이며 자연어 fixture가 아니다.

```json
{
  "options": [
    {"plan_ref": "pl_Q7m2v9K4x1", "summary": "<원문 span과 Registry 의미로 만든 요약 A>"},
    {"plan_ref": "pl_N8c5t3R6w0", "summary": "<원문 span과 Registry 의미로 만든 요약 B>"}
  ]
}
```

HCX Tool call:

```json
{"selected_plan_ref": "pl_Q7m2v9K4x1"}
```

HCX는 stable semantic ID, SQL, table, column, JOIN, verified product/entity ID,
RequirementOption ref, canonical value를 보거나 생성하지 않는다. extra property, 빈 문자열,
복수 ref, 설명문이 섞인 ref는 거부한다.

`display_summary`는 자유 생성 문장이 아니라 requirement별 allow-list record를 사람이 읽는
고정 template에 넣어 만든다. 선택에 필요한 `target meaning`, `requirement kind`, `field meaning`,
`period`, `unit`, `relation direction`, `result grain`과 질문의 exact span만 포함할 수 있다.
source/coverage/freshness는 의미 후보를 구별하는 승인된 discriminator일 때만 표시하고, 실행
가능성을 암시하는 문구는 넣지 않는다. option payload 전체 byte/token과 option별 차이 필드는
진단하되 원문·ref·semantic ID를 로그에 남기지 않는다.

## 10. 서버 상태 전이와 fail-closed 규칙

```text
RECEIVED
  → VIEW_FROZEN
  → OPTIONS_GENERATING
  → OPTIONS_BLOCKED                 (invalid/no candidate/materially ambiguous/truncated)
  또는 AWAITING_SELECTION
  → SELECTION_RECEIVED
  → SELECTION_REJECTED              (shape/membership/expiry/scope/snapshot/single-use)
  또는 SELECTION_VERIFIED
  → CANONICAL_PLAN_MATERIALIZED
  → EXECUTION_BLOCKED               (operation/coverage/freshness/provenance/readiness)
  또는 EXECUTION_READY
  → EXECUTED → EVIDENCE_ASSEMBLED → TERMINAL
```

각 상태는 단방향이고 terminal/blocked 상태에서 재선택하지 않는다. 다음 조건은 항상
fail-closed다.

- explicit span 누락·중복·잘못된 non-requirement 분류
- RequirementOption의 unresolved/materially ambiguous 상태 또는 canonicalization failure.
  안전하게 materialize된 복수 candidate 중 Intent 선택이 남은 `choice_required`는 차단 사유가
  아니라 HCX를 호출하는 이유다
- lossy candidate truncation
- arbitrary, wrong-kind, cross-request, expired, consumed ref
- selected option과 저장 snapshot/build/fingerprint 불일치
- 선택 후 validator가 생성 시점의 canonical plan과 다른 결과를 냄
- Execution Registry의 operation, row provenance, selection policy, coverage 또는 freshness 부족

`choice_required`와 `materially_ambiguous`를 합치지 않는다. 전자는 서버가 안전한 후보를 모두
materialize했지만 질문 문맥의 Intent 선택이 남은 경우이며 HCX가 제공된 전체 plan ref 중
하나를 고른다. 후자는 질문에 필요한 discriminator 자체가 없어 HCX도 임의 선택하면 안 되는
경우이며 clarification/refusal로 남긴다. HCX 선택은 제공되지 않은 조합, execution readiness,
coverage 완전성을 승인하지 않는다.

## 11. CanonicalPlan 구성과 production compiler 입력 계약

production compiler의 **상류 선택·materialization 입력**은 provider가 작성한 semantic
document를 받지 않는다. 입력은 다음 `SelectedPlanEnvelope` 하나다.

- 원본 `question`과 요청 내부 `question_binding`
- 현재 `request_scope_id`, 검증된 `option_set_id`, `selected_plan_ref`
- exact membership으로 찾은 immutable `PlanOption`
- frozen Runtime View와 server-side ref map
- `semantic_registry_build_id`, `execution_registry_build_id`
- `SpanLedger`, canonicalizer version, option policy version
- selection 검증 결과와 생성 시 semantic validation record

구성 과정은 다음과 같다.

1. 선택 ref와 request/snapshot/build/request-lifetime/single-use를 검증한다.
2. PlanOption의 RequirementOption을 requirement/source span 순서로 읽는다.
3. 요청별 ref를 frozen Runtime View의 server-side map으로 stable semantic ID에 해소한다.
4. 기존 field family/grain/operation 및 relation domain/range binding을 다시 검증한다.
5. 저장 span을 기존 deterministic canonicalizer에 그대로 전달해 condition value/operator,
   ordering direction, limit, aggregation을 다시 만든다.
6. 생성 시 `canonical_plan_preview`와 semantic-equivalence equality를 확인한다. 다르면
   `option_revalidation_mismatch`로 차단한다.
7. current `CanonicalRequirement`/`CanonicalPlan` 구조를 구성하고 `execution_values` gate를
   통과한 값만 downstream compiler에 준다.
8. Execution Registry readiness는 별도 단계에서 재평가한다. option 선택은 실행 가능성이나
   coverage 완전성을 자동 승인하지 않는다.

compiler는 `selected_plan_ref`만으로 global 저장소를 검색하거나 provider가 보낸 plan body,
semantic ref, target, operator, limit을 받지 않는다.

이 절은 CanonicalPlan 이후의 실행 compiler가 완성됐다는 뜻이 아니다. 현재
`ResolvedProductQuery`는 제한된 product ranking slice이며, 복수 requirement·관계·집계와
Evidence를 위한 compiler 출력 IR과 fan-out/fan-in 규칙은 별도 계약·구현 과제로 남는다.

## 12. 지원 구조 범위

- **복수 target**: 각 target이 같은 requirement에 참여하는 역할과 공통 output grain이
  명시되고 Registry compatibility가 증명될 때만 허용한다.
- **복수 requirement**: SpanLedger의 서로 다른 explicit requirement를 각각 하나의
  RequirementOption으로 포함한다. 하나라도 blocked면 전체 plan 실행을 막는다.
- **관계+속성**: predicate domain/range와 anchor entity type으로 관계 방향을 결정하고,
  관계 결과를 product grain으로 dedup한 뒤 속성 filter/order/aggregation을 적용할 수 있는
  경로만 만든다.
- **bounded nested**: 한 producer requirement의 결과 set을 한 consumer가 쓰는 단일
  result-reuse edge만 제안한다. cycle, fan-out, 자유로운 `depends_on`, 깊이 2 이상은
  `structure_unsupported`다.
- **bounded comparison**: 정확히 두 target/result, 명시 comparison span, 동일 semantic
  metric 또는 Registry가 선언한 equivalent metric, 같은 period/unit/currency/result grain일
  때만 제안한다. 다기간·다통화 변환이나 세 개 이상 operand는 지원하지 않는다.
- **현재 구현 readiness**: grouping, whole-comparison requirement, explanation canonicalizer가
  없으므로 관련 option은 계약상 표현 가능해도 production selectable로 열지 않는다. bounded
  구조의 계약 승인과 실제 canonicalizer/validator 통과는 별도 게이트다.

## 13. 기존 구성요소의 재사용·대체·보존

| 구성요소 | 처리 |
|---|---|
| Runtime View 및 요청 단위 dataset/field/predicate/entity ref map | 보존·재사용. 모델 payload 대신 option generator의 입력이 중심이 됨 |
| `RefMinter`의 요청 salt/충돌 검출 원칙 | 보존. 별도 plan ref kind를 추가할 때도 exact membership이 권한의 정본 |
| RegistryFacts / ExecutionRegistryFacts | 보존. option hard prune와 선택 후 재검증에 사용 |
| 기존 span exact alignment와 canonicalizer 4종 | 보존·재사용. HCX가 span을 제출하지 않고 서버 option이 span을 소유 |
| semantic validator의 family/grain/ref/relation 검증 | 보존하되 model-submission validator에서 server-generated option verifier로 책임을 재정의 |
| `CanonicalRequirement`, `CanonicalPlan`, `execution_values` gate | 보존. 생성 시 preview와 선택 후 결과 equality를 추가 |
| grouped-flat, JSON bridge, multiline/one-line parser | production HCX ① 경로에서는 대체. 회귀·provenance 호환 모듈로 보존 가능하나 실행 fallback으로 자동 사용하지 않음 |
| provider Tool parser | `selected_plan_ref` 단일 field shape + membership validator로 대체 |
| entity resolution, Execution readiness, SQL compiler, Evidence | 책임 불변. plan selection 성공을 근거로 완화하지 않음 |

## 14. VectorDB 문서 Evidence 확장점

embedding 의미 검색과 문서 Evidence를 분리한다. 향후 문서 VectorDB를 추가할 때
RequirementOption에는 실행 전에 다음 요구만 기록한다.

- `evidence_need`: claim/requirement가 요구하는 문서 근거 종류
- `evidence_source_class`: 승인된 source class; 실제 document/chunk ID가 아님
- `freshness_constraint`, `subject_grain`, `claim_scope`

선택·실행 뒤 별도 Evidence resolver가 `source_id`, `document_id`, `chunk_locator`,
published/effective as-of, retrieval provenance, coverage를 붙인다. 이 문서 ID와 chunk는 HCX ①
plan option에 넣지 않고 HCX ②에는 검증된 Evidence로만 전달한다. 문서가 없으면 required
claim을 차단하며 상품 DB 결과로 문서 근거를 가장하지 않는다. VectorDB similarity는 semantic
mapping이나 실행 승인 근거가 아니다.

## 15. 수용 테스트와 보지 않은 구조 변형

새 자연어 fixture를 만들지 않는다. 사용자 승인 전에는 구조형 synthetic record와 기존 승인
fixture의 metadata만 사용한다.

### 계약 수용 테스트

1. Tool schema가 required `selected_plan_ref:string` 하나와
   `additionalProperties=false`만 가진다.
2. HCX payload와 wire 전체에 stable semantic ID, physical table/column/JOIN/SQL,
   verified entity/product ID, RequirementOption ref가 0건이다.
3. 임의·타요청·만료·재사용·wrong-state ref가 모두 정확한 reason으로 거부된다.
4. PlanOption에 없는 RequirementOption 조합을 표현하거나 실행할 입력 경로가 없다.
5. 모든 식별된 explicit semantic anchor와 requirement span이 정확히 한 번 회계되지 않거나
   unclassified content span이 남으면 selectable option이 0개다.
6. semantic mapping, canonicalization, execution readiness 상태가 독립적으로 보존되고
   unresolved/materially ambiguous/blocked requirement가 조용히 제거되지 않는다.
7. condition/operator/order/limit은 option의 exact span에서 기존 canonicalizer로 만들어지고
   provider 값은 입력되지 않는다.
8. 동일 semantic plan은 후보/ref/requirement 순서를 바꾸고 새 request ref를 발행해도 같은
   equivalence key와 CanonicalPlan을 만든다.
9. lossy beam/cap discard 1건만 있어도 `candidate_space_truncated`이며 실행되지 않는다.
10. relation domain/range, family, grain, operation, period/unit/currency 불일치가 조합 전에
    제거되거나 materially ambiguous/blocked로 보존된다.
11. 생성 preview와 선택 후 CanonicalPlan이 다르면 실행이 차단된다.
12. Registry build/snapshot이 바뀐 option은 재사용되지 않는다.

### 보지 않은 구조 변형

- requirement 순서와 target 표면 순서 교환
- 한 target/복수 requirement와 복수 target/한 requirement
- relation filter + attribute output/order
- 동일 의미의 여러 물리 binding과 다른 의미의 인접 field
- direct/look-through와 inverse 방향
- producer→consumer 한 단계 nested reuse
- 두 operand comparison의 compatible/incompatible period·unit·currency
- 후보 수가 각 cap의 직전·정확히 cap·cap+1인 경계
- ref collision, option-set expiry 직전/후, duplicate Tool call

각 테스트는 `test_purpose`, `capability_under_test`, 구조, expected decision/invariant,
`falsifies_if`, `semantic_clarity: explicit` metadata를 가져야 한다. 자연어 문자열을 새로
작성해 fixture로 등록하는 것은 별도 사용자 검수 뒤에만 가능하다.

## 16. 특정 질문·상품·fixture 하드코딩 부재 검증

- architecture guard가 runtime source에서 CQ/question/case ID 분기, evaluation fixture import,
  정확한 질문 문자열, known product name/date/row-count literal을 검사한다.
- semantic/execution Registry의 모든 stable ID와 family ID를 수집해 option generator와
  selector runtime source에 0건인지 검사한다. provenance source 주석과 생성 stable enum은
  별도 allow-list로 구분한다.
- option은 실제 Registry를 구조적으로 탐색한 결과로만 생성하며 테스트 helper가 expected
  semantic ID나 candidate kind를 generator에 주입하지 못하게 한다.
- 후보 순서·opaque ref·요청 salt를 바꾼 property test에서 semantic equivalence와
  CanonicalPlan이 불변인지 검사한다.
- 평가 fixture·expected answer·35문항 상태를 runtime import하지 않는 기존 guard를 유지한다.

## 17. 구현 전 사용자 결정이 필요한 항목

1. Confirmed HCX ① 책임과 semantic-query 작성 주체를 서버 option generator로 바꾸는
   아키텍처 변경 승인 여부
2. 내부 factorization + 전체 plan ref one-tool 권고안 승인 여부
3. 8/8/32/16 잠정값으로 offline 분포·prompt budget·cap 경계 실험을 먼저 수행할지와
   “lossy truncation이면 전체 차단” 원칙 승인 여부. 숫자 자체는 측정 뒤 별도 승인
4. plan ref를 동기 request lifetime의 in-memory context에만 두고 single-use로 소비하는 정책
   승인 여부. 별도 TTL/global store는 현재 범위 밖
5. `SpanLedger`를 production 입력으로 승인하기 전 semantic-anchor recall과 잔여 content
   분류 반증 실험 수행 여부 및 non-requirement reason allow-list
6. grouping/whole comparison/explanation은 필요한 canonicalizer가 생길 때까지 selectable로
   열지 않는 범위 승인 여부
7. 기존 model-authored semantic parsers를 production fallback에서 제거하고 provenance/회귀
   용도로만 보존할지 여부
8. provisional internal reason code를 shared contract로 승격할 범위와 외부
   `retrieved_context`/`think_trace` 표현 방식

## 18. 상태 문서 최신화 반영 — 2026-09-01

메인 조정 작업에서 아래 stale 상태를 최신화했다. 역사적 실험 본문은 provenance로 보존하고,
현재 상태 요약과 superseded 표식을 추가했다. 이 반영은 `ARCHITECTURE.md` Confirmed 결정을
바꾸거나 본 제안서를 승인한 것이 아니다.

### `IMPLEMENTATION_PLAN.md` — 현재 기록 갱신 완료

- 0-A의 “기본 encoding은 nested, 예비는 grouped_flat”은 현재 production wire 상태와 맞지
  않는다. JSON bridge, line, one-line 실험의 최신 결과와 본 역할 축소 결정 대기로 바꿔야 한다.
- 단계 1의 “실제 Registry grouped-flat 4회 모두 Tool emit 전 `40009`”와
  “compatibility minimization 또는 Tool 없는 대안”은 이후 최소 Tool/bridge/one-line에서
  provider accepted + exact Tool emit까지 확인된 사실을 반영하지 못한다.
- 단계 1의 현재 blocker는 provider Tool 수용성이 아니라 HCX가 자유 문자열 내부 custom
  grammar를 일관되게 생성하지 못해 parser 전 차단된 것이다.
- 단계 1의 “조건값·연산자·정렬·limit canonicalizer는 아직 없음”은 오래됐다. ordering,
  limit, comparison condition, aggregation 네 canonicalizer는 offline 연결됐고 grouping,
  whole-comparison requirement, explanation 등이 남았다.
- `contracts/EVALUATION_API.md` pending의 nested/grouped-flat 선택도 역할 축소안이 승인되면
  `selected_plan_ref` wire 결정으로 대체해야 한다. 이 문서는 요청된 수정 목록의 직접 대상은
  아니지만 정합성상 함께 검토해야 한다.

### `b_semantic_compiler/FINDINGS.md` — 상단 현재 상태 요약과 R절 갱신 완료

- 문서 상단과 1~8절의 `AVAILABLE_CANONICALIZERS=∅`, “canonicalizer가 하나도 없음”, 관련
  실행 가능 범위·다음 작업 문구는 최신 `RUNTIME_INTEGRATION_20260831.md`와 충돌한다.
- 3절 module 표는 one-line bridge와 현재 wiring을 반영하지 않고 grouped-flat까지에서
  멈춰 있다.
- 8절과 3차 보완의 “provider JSON Schema 승인/40009/조건 canonicalizer 미구현” 상태는
  뒤의 append-only 기록과 최신 2026-09-01 live 결과에 의해 대체됐음을 상단 current-status
  요약에서 명시해야 한다.
- 5~6차의 “provider 현재 거부됨”과 grouped-flat rejection은 역사적 관측으로 남기되,
  current blocker로 읽히지 않도록 superseded 표식을 붙여야 한다.
- L~Q의 JSON bridge 실패 축은 역사 기록으로 보존하되, 이후 line/one-line 결과와
  `provider accepted / tool emitted / one-line text grammar rejected`를 current status로
  연결해야 한다.
- R절의 “조건값·연산자·정렬·limit canonicalizer 구현” 미결정은 삭제 또는 세분화해야 한다.
  구현된 네 종류와 아직 없는 grouping/whole-comparison/explanation을 구분해야 한다.
- 문서 전체의 `provisional / correction required` 자체는 사용자 승인 전 유지할 수 있으나,
  그 이유를 과거 11개 correction이나 `40009`가 아니라 현재 역할 축소 계약·shared reason
  code·execution readiness 미결정으로 갱신해야 한다.

## 19. 승인 후 문서 변경 순서 제안

승인되더라도 즉시 코드를 바꾸지 않는다. 먼저 (1) `ARCHITECTURE.md` 2~4절의 Confirmed 책임
변경 결정, (2) Tool surface의 Experiment-dependent encoding, (3) production compiler input과
reason/status shared contract, (4) `IMPLEMENTATION_PLAN.md`의 반증 실험·수용 게이트 순으로
문서 승인을 끝낸 뒤 구현 범위를 별도로 승인한다.

## 20. 임원용 요약

HCX가 복잡한 semantic query 문서를 쓰게 하지 않고, 서버가 검증한 전체 계획 후보 중 요청
단위 opaque ref 하나만 고르게 하는 방식을 권고한다. 서버 내부는 requirement별 후보를
유지해 누락·모호성·관계·단위·coverage를 회계하되, HCX는 stable ID나 DB 구조를 전혀 보지
않는다. 임의·타요청·만료 ref와 후보 truncation은 모두 fail-closed이며, 선택 성공도
Execution Registry와 Evidence 검증을 대체하지 않는다. 이 변경은 wire 최적화에 그치지 않고
HCX ①과 Confirmed semantic-query 작성 책임을 바꾸므로 사용자·Codex의 아키텍처 승인이 먼저다.
