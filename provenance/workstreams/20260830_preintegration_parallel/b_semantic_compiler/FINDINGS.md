# B — Runtime View와 상품군 혼입 방지 core

> **상태: `provisional / correction required`. B 정식 완료 승인 전이며 완료가 아니다.**
> 2026-08-31 사용자 감사에서 11개 계약 결함이 지적됐고, 이 문서는 그 수정 이후 상태를
> 기록한다. `IMPLEMENTATION_PLAN.md`의 B 단계는 사용자 승인 전까지 완료로 바꾸지 않는다.

## 현재 상태 요약 — 2026-09-01

이 문서는 append-only에 가까운 workstream provenance다. 아래 1~8절과 A~Q절의 당시 상태와
실험 순서는 보존하되, 현재 판정은 이 요약과 다음 최신 문서가 우선한다.

- `RUNTIME_INTEGRATION_20260831.md`: ordering, limit, comparison condition, aggregation 네
  canonicalizer와 fail-closed `execution_values` 관문이 offline Runtime 경로에 연결됐다.
  따라서 아래의 `AVAILABLE_CANONICALIZERS=∅`와 "canonicalizer가 하나도 없다"는 문구는
  역사적 snapshot이며 현재 상태가 아니다.
- `HCX_ONE_LINE_RECORDS_OFFLINE_20260901.md`: one-line wire의 offline parser→validator→
  canonicalizer 통합은 통과했다.
- `HCX_ONE_LINE_RECORDS_LIVE_RESULT_20260901.md`: HCX-007은 최소 string envelope Tool을
  수용하고 정확한 이름으로 emit했지만, custom one-line field assignment를 일관되게 생성하지
  못해 parser에서 차단됐다. semantic validation과 DB 실행에는 도달하지 않았다.
- 현재 blocker는 provider Tool 기능의 부재나 `40009`가 아니라 HCX가 자유 문자열 내부의
  복잡한 semantic 문법을 안정적으로 생성하지 못한다는 점이다. 추가 delimiter·prompt
  미세조정은 중단했다.
- 실제 Registry의 row provenance/selection/dataset population binding과
  CanonicalPlan→ResolvedProductQuery production compiler는 여전히 없다. 따라서 production
  execution은 `provenance_binding_unavailable`로 차단되는 것이 정답이다.
- 다음 아키텍처 후보는 서버가 requirement별 후보를 factorize하되 HCX wire에는 전체
  PlanOption의 요청 단위 opaque ref 하나만 노출하는 방식이다. 비정본 제안서
  `HCX_ROLE_REDUCTION_CONTRACT_PROPOSAL_20260901.md`는 검토 중이며 아직 Confirmed 변경이나
  구현 승인이 아니다.

이 요약은 과거 관측을 삭제하지 않는다. 아래의 `40009`, JSON bridge, line/one-line 실패는
원인 축을 좁힌 역사적 근거이고, current status로 읽어서는 안 된다.

작업 게이트: `GATE_RUNTIME_VIEW_FAMILY_BINDING.md`
근거 결정: `RUNTIME_VIEW_TOOL_DECISION_20260831.md` (사용자·Codex 승인),
`ARCHITECTURE.md` 3~4절, `QUESTION_STRUCTURE.md` 2·5절,
`DATA_ONTOLOGY_ALIGNMENT_DECISION_20260830.md` 4·5절

## 1. 무엇을 막는 구현인가

F의 composite 평가에서 실측된 실패는 어휘 실패다. `총보수`는 국내 ETP와 해외 ETP 두
term의 승인된 별칭이고 `1년 수익률`은 국내 ETP와 공모펀드 양쪽에서 정확히 매칭된다.
따라서 surface form만으로는 상품군이 결정되지 않으며, 15건 중 11건이
`grounding_eligible`까지 도달했다.

대응은 어휘가 아니라 구조다. 모든 field 후보는 **Registry가 증명할 수 있는 dataset에 묶인
상태로** 발행되고, 어떤 후보가 선언한 상품군은 검색이 회수하지 못했어도 dataset 후보로
존재한다. 모델이 다른 상품군을 고르려면 그 사실을 ref에 드러내야 하고 서버가 그것을 본다.

## 2. 2026-08-31 감사 지적과 수정

| # | 지적 | 수정 |
|---|---|---|
| 1 | `resolved_key`가 plan까지 보존되지 않고 `anchor_entity_key`에 mention_text가 들어감 | `EntityCandidate`가 `resolved_key`와 `entity_class_id`를 서버 측에 보관하고 `RelationBinding.anchor_entity_key`에 검증된 key를 넣는다. HCX payload에는 mention과 resolution 상태만 나간다 |
| 2 | 요구 종류가 정본과 다름 | `contract.py`에 `QUESTION_STRUCTURE.md` 2절의 8종(`listing`, `attribute_lookup`, `count`, `aggregation`, `ranking`, `grouping`, `comparison`, `explanation`)을 출처와 함께 기록하고 그 밖의 명칭을 거부한다 |
| 3 | raw span·ref 유실, 정규화 불가 연산을 성공 처리 | `PreservedSubmission`이 source span, 조건 span, 정렬 span, limit span, 집계 span, grouping, 제출 ref를 실행 여부와 무관하게 보존한다. `AVAILABLE_CANONICALIZERS`는 현재 **공집합**이므로 조건·정렬·limit·집계·grouping·비교·설명이 붙은 요구는 `canonicalizer_unavailable`로 non-executable이 된다. direction/limit 없는 ranking은 기본값을 만들지 않고 `requirement_incomplete`다 |
| 4 | `parse_submission`이 관대함 | fail-closed로 바꿨다. list 자리의 문자열, object 아닌 condition, 알 수 없는 property, 잘못된 타입을 전부 구조화 문제로 반환하고 그 요구를 버린다. `unaccounted_spans`가 비어 있지 않으면 `unaccounted_explicit_span`으로 실행을 막는다. `source_span`이 질문의 부분문자열이 아니면 `span_alignment_failed`다 |
| 5 | `kind=class`라는 이유만으로 dataset 후보가 됨 | dataset은 **연산이 없고**(측정값이 아니라 사물), **상품군을 선언했고**, **grain이 `product` 또는 `product_class`인** term만이다. Security·Portfolio·추상 root는 후보가 되지 않고 `excluded`에 사유와 함께 기록된다 |
| 6 | family 없는 field를 모든 dataset에 적용 | `scope_unproven`으로 발행하고 `belongs_to_dataset_refs`를 비운다. 이 field를 쓰는 요구는 `field_scope_unproven`으로 unresolved다 |
| 7 | 같은 family의 첫 dataset에 결합 | 요구가 **실제로 선택한** `target_dataset_ids`에만 결합한다. family가 맞아도 grain이 다르면 `field_grain_mismatch`다 |
| 8 | closure 주장이 field에만 구현됨 | closure를 field와 predicate 양쪽에 구현했다. 주장도 "**선언된 families**를 가진 모든 후보"로 정정했다. 현재 Registry의 관계 predicate는 family를 선언하지 않으므로 predicate만 있는 질문은 dataset을 얻지 못하고 `missing_target_dataset`으로 거부된다 — 이는 테스트로 고정했다 |
| 9 | ref가 48-bit, 충돌 검출 없음, label 없으면 semantic ID 노출 | ref는 요청 salt 32 byte에서 128-bit(hex 32자)로 만들고 충돌 시 `RefCollisionError`를 던진다. meaning은 label → alias 순으로 찾고 둘 다 없으면 **빈 문자열과 `unnamed_in_registry`**이며 semantic ID로 대체하지 않는다 |
| 10 | budget이 음수·미지 kind를 받고 closure 영향이 불명 | `CandidateBudget.__post_init__`이 음수와 미지 kind를 거부한다. budget은 **검색이 제안한 후보만** 자르고 closure dataset은 면제이며 `budget_exempt_datasets`로 보고한다. 계약과 테스트에 명시했다 |
| 11 | reason code가 공유 계약처럼 보임, kind/grain 매핑이 무근거 상수 | 모든 payload와 결과에 `CONTRACT_STATUS = provisional_internal_pending_shared_contract_approval`이 실린다. 후보 종류는 Registry 구조(domain/range 유무, allowed_operations, families, grains)에서 파생하며 kind 이름 매핑표가 사라졌다. grain과 요구 종류는 정본 문서 출처를 상수 옆에 기록했다 |

## 3. 모듈

| 모듈 | 책임 |
|---|---|
| `contract.py` | 정본에서 빌려온 어휘(요구 종류 8종, 상태 3종, 결과 grain 2종)와 출처, 사용 가능한 canonicalizer 집합, `CONTRACT_STATUS` |
| `refs.py` | 128-bit 요청 단위 opaque ref, 충돌 검출, kind 접두 |
| `registry_facts.py` | `Vocabulary`가 싣지 않는 class 계층을 같은 Registry 문서에서 투영하고 content hash를 대조 |
| `view.py` | 구조 기반 후보 분류, family closure, binding, predicate domain/range·inverse·동형 관계 구별, 주입식 budget, 모델 payload |
| `query.py` | fail-closed `submit_semantic_query` 입력 파서 |
| `validate.py` | 서버 검증, canonical plan, 보존된 제출 |
| `schema.py` | provider-neutral 논리 JSON Schema와 provider adapter (6차에서 추가 기재) |
| `hcx_wire.py` | JSON Schema keyword 투영과 fail-closed keyword 결정 (5차) |
| `grouped_flat.py` | HCX wire encoding과 canonical 제출로의 조립 (6차) |

### 모델에게 보내지 않는 것

stable semantic ID, retrieval score/rank, physical binding, SQL, 검증된 entity key, 전체
Registry. 실제 Registry 후보 160개 payload에 prefix 5종과 `resolved_key`가 한 번도
나타나지 않음을 테스트로 강제한다.

### 검증 reason code (provisional internal)

`unknown_ref`, `ref_kind_mismatch`, `missing_target_dataset`, `cross_family_field`,
`cross_family_predicate`, `field_scope_unproven`, `field_grain_mismatch`,
`requirement_unresolved`, `requirement_ambiguous`, `requirement_incomplete`,
`entity_unresolved`, `relation_direction_undecidable`, `relation_target_mismatch`,
`canonicalizer_unavailable`, `unaccounted_explicit_span`, `span_alignment_failed`.

## 4. 일반화 단위

두 가지다.

1. 요구의 target dataset과 그 요구가 참조하는 field/predicate의 Registry 상품군·grain이
   양립하는가.
2. 이 요구가 쓰는 연산을 서버가 결정적으로 정규화할 수 있는가.

상품군 이름, 지표 이름, 질문 문자열, case ID 분기는 없다. 실제 Registry 테스트도 ID를
적지 않고 Registry에 물어서 동음이의 26쌍과 inverse 2쌍을 찾아 전수 검증한다.

## 5. 추가한 상수와 근거

| 상수 | 근거 |
|---|---|
| 요구 종류 8종·상태 3종 | `QUESTION_STRUCTURE.md` 2·5절. 출처를 `REQUIREMENT_KINDS_SOURCE`에 기록 |
| `DATASET_GRAINS = (product, product_class)` | `ARCHITECTURE.md` 8절, 정렬 결정 4절. 출처를 `DATASET_GRAINS_SOURCE`에 기록하고 payload에도 실음 |
| canonicalizer 이름과 `AVAILABLE_CANONICALIZERS=∅` | `ARCHITECTURE.md` 3절이 요구하는 서버 canonicalization 목록. 구현 전이므로 공집합 |
| reason code, `KIND_PREFIXES`, `REF_DIGITS`, `SALT_BYTES` | provisional internal wire 표기 |

상품군 이름, semantic ID, alias, predicate ID, Registry kind 이름, budget 값은 코드에
하나도 없다.

## 6. 테스트

`tests/runtime_view/` 51개. 합성 Registry 42개 + 실제 Registry 구조 탐색 9개.

합성 Registry의 `term()` 헬퍼에는 **후보 종류를 지정하는 인자가 없다.** 분류가 구조에서
파생되는지 확인하려면 테스트가 정답을 넘겨줄 수 없어야 하기 때문이다.

사용자 요구 최소 테스트 8개 대응:

| 요구 | 테스트 |
|---|---|
| 1. 다른 상품군 총보수 거부 | `test_a_field_from_another_family_is_refused_without_a_substitute`, 실제 Registry는 `test_every_cross_family_homonym_is_refused_in_both_directions`가 26쌍 × 양방향 × grain 일치 target 전수 |
| 2. 해외 순자산 → 국내 순자산 거부 | 같은 property 테스트가 `AUM`/`운용규모` 쌍 포함 |
| 3. 두 family binding 분리 | `test_two_families_in_one_requirement_keep_separate_bindings` |
| 4. 서버가 방향 결정 | `test_the_server_decides_relation_direction_from_the_anchor_type`, `test_every_declared_inverse_pair_resolves_from_the_anchor_type` |
| 5. look-through를 direct로 대체 안 함 | `test_an_indirect_relation_is_not_interchangeable_with_a_direct_one`, `test_same_shape_relations_are_published_as_different_meanings` |
| 6. 발명·타요청 ref 거부 | `test_invented_and_cross_request_references_are_refused`, `test_a_reference_used_in_the_wrong_slot_is_refused` |
| 7. 순서·ref 불변 canonical | `test_canonical_plan_is_invariant_to_order_and_reference_values` |
| 8. budget 없이 종류별 묶음 보존 | `test_without_a_budget_candidates_are_kept_and_still_grouped` |

이번 감사 수정에 대한 추가 테스트: `resolved_key` 보존과 비노출, 요구 종류 8종,
canonicalizer 부재 시 non-executable, ranking 기본값 금지, span 보존·정렬·미회계 span,
parse fail-closed 3종, dataset 후보 자격, security class 배제, closure의 predicate 적용과
그 한계, scope 미증명 field, grain 불일치, 선택 target 결합, ref 폭·충돌, unnamed 후보,
budget 거부와 closure 면제.

검증 명령과 결과:

```powershell
uv run --cache-dir .tmp/uv-cache python -m pytest -q --basetemp=.tmp/pytest-b-correction
```

```text
513 passed, 1 skipped in 33.28s
```

```powershell
uv run --cache-dir .tmp/uv-cache ruff check src/canna/runtime_view tests/runtime_view
```

```text
All checks passed!
```

## 7. 이번 수정이 드러낸 데이터·계약 한계

1. **Registry에 family-neutral field의 적용 범위 선언이 없다.** `cnn:ProductName`,
   `cnn:HoldingWeightType` 같은 항목은 상품군을 선언하지 않아 이제 `scope_unproven`이며
   실행에 쓸 수 없다. 이는 의도된 fail-closed지만, 실제로 여러 상품군에 적용되는 field가
   묶이지 못한다는 뜻이다. Ontology에 scope 또는 domain 선언을 추가하는 것이 정답이며
   승인 사항이므로 하지 않았다.
2. **관계 predicate가 family를 선언하지 않는다.** 따라서 predicate만 회수된 질문은 dataset
   closure를 얻지 못한다. 현재는 `missing_target_dataset`으로 거부하고, 그 한계를 문서와
   테스트에 고정했다.
3. **direct/look-through를 구별하는 일급 discriminator가 없다.** `같은 domain/range −
   inverse`로 파생했다. Ontology에 relation mode를 명시하는 편이 명확하다.
4. **canonicalizer가 하나도 없다.** 따라서 현재 실행 가능한 요구는 조건·정렬·limit·집계·
   grouping이 없는 `listing`, `attribute_lookup`, `count`뿐이다. 이는 정직한 현재 상태이며,
   다음 슬라이스는 조건값·연산자·정렬·limit canonicalizer 구현이다.

## 8. 남은 미결정

- 공유 reason code 계약과 `submit_semantic_query`의 provider JSON Schema 승인
- 후보 종류별 budget 값 (F의 근거가 무효 gold 의존으로 철회된 상태)
- entity resolution 계층 구현
- Execution Registry 연결과 SQL 컴파일 (C/D)
- Evidence 계약과 최종 HCX 답변

---

# 2026-08-31 2차 감사 수정 (상태: 여전히 provisional / correction required)

## A. 수정한 7개 항목

| # | 지적 | 수정 |
|---|---|---|
| 1 | requirement 최소 완전성 | 모든 explicit requirement에 질문에 정렬되는 non-empty `source_span` 필수(`missing_source_span`), **모든 kind에 target 필수**(`missing_target_dataset`), `attribute_lookup`은 output field 또는 관계 output 필수(`requirement_incomplete`), target·output·condition이 모두 없으면 `empty_requirement`. 빈 계획은 `semantic_valid=True`가 될 수 없다 |
| 2 | HCX status와 서버 판정 분리 | `CanonicalRequirement`가 `submitted_status`(모델의 회계, 덮어쓰지 않음)와 `server_decision`(서버 판정)을 함께 보존한다. 서버가 거부하면 `server_decision`은 `unresolved`이며, 방향 결정 불가처럼 두 의미가 가능한 경우에만 `ambiguous`다. `unresolved_requirement_ids`는 이제 **서버가 거부한 requirement를 포함**한다 |
| 3 | 모든 raw span 검증 | `source_span`뿐 아니라 `comparison_span`, `value_span`, `direction_span`, `limit_span`, `function_span`을 질문과 정렬한다. exact 또는 승인된 결정적 정규화(`unicode_nfkc_then_collapse_whitespace_then_strip`) 후 exact만 인정하며, 그 밖에는 `span_alignment_failed`로 실행을 막는다. 검증·보존되지 않던 자유문자열 `note` 필드는 계약에서 **제거**했다 |
| 4 | 내부 plan과 HCX 응답 분리 | `model_response(view, result)`를 별도 serializer로 두었다. **allow-list 방식**으로 안전한 field만 이름을 적어 만들므로 plan에 field가 추가돼도 새는 일이 없다. `ValidationResult.to_dict()`는 `audience=server_internal`로 표시하고 그대로 모델에 보낼 수 없음을 명시한다. 모델 응답에 semantic ID·resolved key·물리 binding이 없음을 테스트로 강제한다 |
| 5 | source·coverage·freshness | `execution_facts.py`에 `ExecutionFacts` 주입 인터페이스와 `CandidateBinding`(source, coverage_state, coverage_note, freshness_state, effective_as_of, as_of_status, execution_ready)을 정의했다. 값을 추측하지 않는다. adapter가 없으면 모두 `unknown`이고 `execution_ready=False`다. **Execution Registry는 수정하지 않았고** 필요한 adapter 계약은 아래 C절에 보고한다 |
| 6 | semantic_valid와 execution_ready 분리 | `executable`이라는 이름을 전부 제거했다. `semantic_valid`는 의미 검증만 뜻하고, `execution_ready`는 Execution Registry adapter가 없으므로 **항상 False**이며 그 근거를 결과에 함께 싣는다 |
| 7 | 실제 JSON Schema | `schema.py`에 provisional `submit_semantic_query` schema를 작성했다. 모든 object가 `additionalProperties: false`, nested object/array의 타입과 required 명시, ref는 `^(ds\|fd\|pr\|en\|cl)_[0-9a-f]{32}$` 패턴. SQL·table·column·JOIN·stable ID·traversal 슬롯 없음을 property 이름 전수 검사로 확인한다. schema와 parser가 같은 field를 허용하는지 parity 테스트가 강제한다 |

## B. 필수 회귀 테스트 대응

| 요구 | 테스트 |
|---|---|
| source/target 없는 mapped listing 거부 | `test_a_mapped_listing_without_a_target_is_refused`, `test_a_mapped_requirement_without_a_source_span_is_refused` |
| field 없는 attribute_lookup 거부 | `test_an_attribute_lookup_without_an_output_is_refused` (+ 통과 케이스 대조) |
| cross-family 거부 시 `server_decision=unresolved` | `test_a_server_refusal_overrides_the_models_mapped_claim` |
| 질문에 없는 condition/order/limit span 거부 | `test_a_span_that_is_not_in_the_question_blocks_execution` (4 parametrize) + 인용된 span은 통과하는 대조 |
| HCX 응답에 stable ID·resolved key 없음 | `test_the_model_response_carries_no_identifier_or_key` (같은 정보가 내부 기록에는 있음을 함께 확인) |
| 후보마다 source/coverage/freshness 상태 존재 | `test_every_candidate_publishes_an_execution_state`, `test_an_injected_binding_is_carried_through_without_being_invented` |
| JSON Schema와 parser 허용 field 일치 | `test_the_schema_and_the_parser_allow_the_same_properties` |

## C. Execution Registry adapter 계약 제안 (임의 변경하지 않음)

B는 Execution Registry를 읽지도 수정하지도 않았다. 필요한 것은 semantic ID 하나에 대한
다음 답이며, 소유 workstream이 제공해야 한다.

```text
binding_for(semantic_id) -> {
    source,             # 이 의미를 서비스하는 출처 식별자
    coverage_state,     # available | unavailable | unknown
    coverage_note,      # 관측 모집단 등 주장 범위 설명
    freshness_state,    # available | unavailable | unknown
    effective_as_of,    # 실효 기준일 또는 unknown
    as_of_status,       # requested_only 등 기준일 상태
    execution_ready,    # 위 전부가 충족될 때만 true
} | None
```

`None`은 "binding 없음"이며 그 후보는 unknown·not ready로 발행된다. 이 계약이 붙기
전까지 어떤 계획도 `execution_ready=True`가 될 수 없다.

## D. 검증

```powershell
uv run --cache-dir .tmp/uv-cache python -m pytest -q --basetemp=.tmp/pytest-b2-full -rs
```

```text
539 passed, 1 skipped in 35.03s
```

```powershell
uv run --cache-dir .tmp/uv-cache ruff check src/canna/runtime_view tests/runtime_view
```

```text
All checks passed!
```

### skip과 환경 의존성

전체 suite에는 환경에 따라 실행 여부가 갈리는 항목이 5종 있다.

| 항목 | 조건 | 이 환경에서 |
|---|---|---|
| `tests/retrieval/test_embedding_live.py` (1) | `RUN_CLOVA_EMBEDDING_LIVE=1` | **skip** — 유일한 skip 1건 |
| `tests/test_semantic_probe_live.py` (3, `hcx_live`) | `.env` 로드 후 HCX 자격증명 존재 | **실행됨** (아래 E절) |
| `tests/retrieval/conftest.py` vocabulary fixture | `semantic_registry.json` 존재 | 존재 → 실행 |
| `tests/runtime_view/test_real_registry.py` (9) | `semantic_registry.json` 존재 | 존재 → 실행 |
| `tests/test_store_queries.py`, `tests/test_ontology_shacl.py` 일부 | `query_store.duckdb`·`execution_registry.json` 존재 | 존재 → 실행 |

따라서 Registry와 조회 store가 없는 환경에서는 skip 수가 크게 늘어난다. 이 환경의
`539 passed / 1 skipped`는 모든 파생 산출물이 존재하는 상태의 수치다.

## E. 보고해야 할 사실 — 전체 suite 실행이 HCX live 호출을 포함한다

`-rs`로 skip을 확인하다가 발견했다. `tests/test_semantic_probe_live.py`의 3개 테스트는
`hcx_live` marker가 붙어 있지만 **기본 실행에서 deselect되지 않는다.** 자격증명은 fixture가
`.env`를 로드한 뒤 확인하므로 이 작업공간에서는 available이고, 따라서 전체 suite를 돌릴
때마다 실제 HyperCLOVA X 호출 3건이 발생한다.

- 이 호출은 **0-A probe의 기존 테스트**에서 나온 것이며 이번 B 작업이나 새 JSON Schema와
  무관하다. 새 schema는 provider에 대해 한 번도 실행하지 않았다.
- 이번 세션의 모든 전체 suite 실행(455 / 492 / 513 / 539)에 동일하게 포함됐다.
- 확인 명령과 결과:

```powershell
uv run --cache-dir .tmp/uv-cache python -m pytest -q -m "not hcx_live and not embedding_live" --basetemp=.tmp/pytest-b2-nolive
```

```text
536 passed, 4 deselected in 16.87s
```

539 − 536 = 3이 live 호출 테스트다. live 호출을 원하지 않는 실행에서는 위 `-m` 필터를
쓰거나, marker를 기본 deselect하도록 `pyproject.toml`의 `addopts`를 바꿔야 한다.
`addopts` 변경은 공유 설정이므로 임의로 하지 않고 보고한다.

## F. 이 단계에서 하지 않은 것

- HCX live 호출로 새 JSON Schema 검증
- DB 실행 (조회 store를 읽는 기존 테스트는 그대로 실행됨)
- Execution Registry 수정
- Ontology 수정
- commit, push, 브랜치·worktree 생성

---

# 2026-08-31 3차 보완 (상태: 여전히 provisional / correction required)

내부 논리계약 기준 조건부 승인 뒤 지시된 3개 보완이다. Ontology, Semantic Registry,
Execution Registry, F 산출물은 수정하지 않았고 외부 API 호출은 0회다.

## A. 외부 live 테스트를 명시적 opt-in으로

**공유 설정 `pyproject.toml`을 변경했다.** `addopts`에
`-m 'not hcx_live and not embedding_live'`를 추가해 기본 pytest가 두 live marker를
deselect한다. 변경 이유와 실행 방법을 파일 주석에 함께 남겼다.

`tests/test_semantic_probe_live.py`는 자격증명 존재만으로 실행하지 않는다. `.env`에 키가
있다는 것이 그것을 쓰라는 동의는 아니므로, `RUN_HCX_LIVE=1`을 추가로 요구한다.
embedding live의 기존 `RUN_CLOVA_EMBEDDING_LIVE=1` 정책은 그대로 두었다.

따라서 외부 호출에는 **marker 선택과 환경변수 두 가지가 모두** 필요하다.

```powershell
# 기본 — 외부 호출 없음
uv run --cache-dir .tmp/uv-cache python -m pytest -q
# 의도적으로 HCX 호출
$env:RUN_HCX_LIVE=1; uv run --cache-dir .tmp/uv-cache python -m pytest -m hcx_live
# 의도적으로 embedding 호출
$env:RUN_CLOVA_EMBEDDING_LIVE=1; uv run --cache-dir .tmp/uv-cache python -m pytest -m embedding_live
```

정책만 검증하고 실제로 호출하지 않았다. marker를 선택하고 환경변수가 없는 상태에서
`4 skipped, 567 deselected`로 전부 skip된다.

## B. Execution Registry adapter 재설계 (읽기 전용)

단일 결과 계약 `binding_for(semantic_id)`는 **폐기했다.** 실제 Registry에서 semantic ID
22개가 복수 binding을 가지며, 일부는 **같은 family·grain 안에서도 둘**이다(예: 같은
상품군의 서로 다른 원천 컬럼 두 개). 하나를 고르는 계약은 그 사실을 지운다.

두 질문으로 분리했다.

- `candidate_bindings_for(semantic_id) -> tuple[BindingSummary, ...]` — 설명용. family_id,
  subject_grain, binding_kind/relation_kind, 안전한 source ID, semantic/executable
  operations, observed coverage 상태와 관측 수, freshness와 effective as-of 범위,
  `binding_available`을 담는다.
- `resolve_capability(target_semantic_id, candidate_semantic_id, operation,
  requested_as_of, relationship_kind) -> CapabilityResolution` — 결정용. family·grain·
  relation kind로 좁히고 operation과 as-of를 확인해 **정확히 하나가 남을 때만**
  `resolved`다. 0개면 `unsupported`/`unavailable`, 2개 이상이면 `ambiguous`로 fail-closed다.

`execution_ready` boolean은 제거하고 binding 단위 `binding_available`로 바꿨다. 후보 하나를
보고 계획 전체의 실행 가능성을 주장하지 않는다. 계획 수준은
`execution_readiness = "not_evaluated_by_semantic_validation"` 문자열이며 boolean이 아니다.

**안전한 source ID**는 Data Catalog가 이미 발행하는 공식 source ID(`PRBD01N001` 등)를
쓴다. 물리 table/column/join은 payload에 나가지 않으며 테스트가 강제한다.

중복은 데이터에서 찾는다. 테스트가 Registry에 물어 복수 binding ID와 같은 family 안의
중복을 스스로 열거하고, 발견 결과가 비면 guard가 깨진다. 특정 semantic ID는 런타임에도
테스트에도 하드코딩하지 않았다.

## C. JSON Schema를 provider 경계에 맞춤

- provider-neutral `SUBMISSION_SCHEMA`는 유지했다.
- `hcx_tool_definition()`이 기존 HCX client가 받는
  `{"type":"function","function":{...,"parameters":...}}` 형태로 감싼다. 같은 schema 객체를
  재사용하므로 정의가 둘로 갈라지지 않는다.
- ref pattern을 slot 종류별로 분리했다. target은 `ds_`, field는 `fd_`, predicate는 `pr_`,
  entity는 `en_`만 받는다. parser도 같은 표(`SLOT_PREFIXES`)로 검사한다.
- condition의 `comparison_span`·`value_span`, ordering의 `direction_span`, aggregation의
  `function_span`을 필수 non-empty로, `source_span`도 `minLength=1`로 제한했다.
- schema와 parser의 허용 property, 필수 span, ref 종류가 일치하는지 parity 테스트가
  강제한다. schema가 금지하는 payload를 parser도 거부하는지 함께 확인한다.
- 실제 네트워크 호출 없이, stub factory로 tool schema가 기존 provider의 `bind_tools`까지
  전달되는지만 검증했다.

## D. Ontology 변경 없이 해소한 두 항목

1. **family-neutral field**: Semantic Registry가 family를 선언하지 않는 term은 Execution
   Registry가 실제로 서비스하는 family로 범위를 잡는다. `dataset_scope`가
   `family_scoped`(의미 선언) / `execution_scoped`(제공 근거) / `scope_unproven`(둘 다 없음)로
   나뉜다. adapter 없이는 이전처럼 `scope_unproven`이고, adapter가 붙으면 서비스되는
   family로 정확히 좁혀진다.
2. **relation**: predicate identity와 Execution Registry의 `relation_kind`를 먼저 쓴다.
   테스트로 확인한 결과, **선언된 inverse 쌍은 같은 relation_kind를 공유하고 같은
   domain/range를 공유하는 비-inverse 형제는 서로 다른 relation_kind를 가진다.** 즉 기존
   파생 규칙과 Execution Registry가 일치하므로 direct/look-through 구별에 Ontology
   discriminator를 추가할 필요가 없다.

**따라서 현재 Ontology 변경 제안은 없다.** 앞서 2차 보완에서 남겼던 두 건은 위 두 근거로
해소됐다.

## E. 검증

```powershell
uv run --cache-dir .tmp/uv-cache python -m pytest -q --basetemp=.tmp/pytest-b3-final -rs
```

```text
569 passed, 4 deselected in 21.09s
```

deselect 4건은 `hcx_live` 3 + `embedding_live` 1이며 **외부 호출은 0회**다. 이전 실행에서
보이던 skip 1건은 이제 deselect로 바뀌어 skip이 0이다.

```powershell
uv run --cache-dir .tmp/uv-cache python -m pytest -q -m "hcx_live or embedding_live" --basetemp=.tmp/pytest-b3-optin -rs
```

```text
4 skipped, 567 deselected in 1.52s
```

marker만으로는 실행되지 않고 환경변수까지 있어야 한다는 정책 검증이다.

```powershell
uv run --cache-dir .tmp/uv-cache python -m pytest tests/runtime_view -q --basetemp=.tmp/pytest-b3-i
```

```text
108 passed
```

```powershell
uv run --cache-dir .tmp/uv-cache ruff check src/canna/runtime_view tests/runtime_view tests/test_semantic_probe_live.py
```

```text
All checks passed!
```

## F. 남은 미결정

- 공유 reason code 계약과 `submit_semantic_query` schema의 정식 승인
- ~~실제 HCX 호출로 schema 수용성 확인 (승인 후 별도 실행)~~ → **2026-08-31 1회 실행됨.
  provider가 tool 생성 전에 API `40009` `Unsupported function`으로 거부했다.** 상세 기록은
  `HCX_RUNTIME_VIEW_LIVE_RESULT_20260831.md`, 후속 offline 보완은 아래 5차 절이다
- 조건값·연산자·정렬·limit canonicalizer 구현 — 없는 동안 해당 요구는 계속 non-executable
- entity resolution 계층
- 계획 수준 실행 가능성 판정(C의 operation·coverage·as-of 검증)

---

# 2026-08-31 4차 Runtime View 정합성 수정

상태: **provisional / correction required 유지**. 재감사 전까지 승인 완료로 바꾸지 않는다.

## A. 수정 결과

1. dataset class에 field/relation의 `served_by`를 적용하지 않고, family·result grain별
   `target_capabilities`를 발행한다. safe source ID, binding 수, binding operation 종류,
   coverage/freshness 지식 상태를 보존하되 `claim_readiness=not_evaluated`로 둔다. field 하나의
   coverage를 dataset coverage로 승격하지 않으며 binding 0은 dataset unsupported를 뜻하지 않는다.
2. relation binding은 `family_id`가 유일하게 일치하는 `holdings_coverage`와만 결합한다.
   source, eligible/attempted/success/failed/observed 수, holding 기준일 범위, snapshot 상태를
   보존한다. 0건은 unknown, 복수건은 ambiguous이며 둘 다 source와 coverage를 추측하지 않는다.
3. relation operation 고정 목록을 제거했다. Semantic Registry `allowed_operations` 입력과
   Execution Registry의 executable 상태가 모두 허용하는 연산만 남긴다. 입력 근거가 없으면
   빈 목록이며, `evidence_requirements`는 별도 field다. 실제 Registry의 direct와
   look-through operation 차이를 그대로 보존한다.
4. ref parser는 RefMinter의 prefix와 `REF_DIGITS`에서 유도한 전체 정규식으로 dataset, field,
   predicate, entity ref를 검사한다. 같은 prefix여도 짧음·김·비16진수인 ref는
   `malformed_reference`로 거부되며 schema와 parser parity 테스트가 같은 payload를 검사한다.

## B. 실제 Registry 관측 예시

- dataset target capability: `domestic_bond` / `product`, safe source `PRBD01N001`, binding 49,
  coverage/freshness `partially_known`, claim readiness `not_evaluated`.
- relation: `domestic_etp` / `direct_holding`, source `external_holdings_bundle`, eligible 1,164,
  attempted 1,161, success 1,160, failed 4, observed 1,160, coverage `partial`, snapshot `full`,
  holding as-of `2026-08-22`, as-of role `requested`.
- operation: direct relation은 `count | exists | filter`, forward look-through는
  `exists | filter`, Semantic Registry가 허용 연산을 주지 않는 inverse look-through는 빈 목록이다.

위 값은 현재 읽기 전용 Registry의 관측 예시이며 runtime 상수가 아니다.

## C. 검증

```text
Runtime View: 119 passed
전체 suite: 578 passed, 4 deselected
live policy: 4 skipped, 578 deselected
Ruff: All checks passed!
외부 API 호출: 0회
```

Ontology, Semantic Registry, Execution Registry 원본, F 산출물,
`IMPLEMENTATION_PLAN.md`는 수정하지 않았다.

---

# 2026-08-31 5차 HCX wire compatibility 보완 (상태: 여전히 provisional / correction required)

## A. 정정해야 할 이전 기술

3차 보완의 미결정 목록은 실제 HCX 호출을 "승인 후 별도 실행" 대기 항목으로 적었다. 그
호출은 2026-08-31에 사용자 승인 아래 **1회 실행됐고 실패했다.** provider는 tool을 emit하기
전에 API error `40009`, message category `Unsupported function`으로 요청을 거부했다. 따라서
`submit_semantic_query` 선언의 provider 수용성은 "미확인"이 아니라 **현재 거부됨**이다.
단일 관측이며 원인은 아직 단일 변수로 분리되지 않았다. 상세 결과와 해석 한계는
`HCX_RUNTIME_VIEW_LIVE_RESULT_20260831.md`에 있다.

## B. 이번 보완의 범위

외부 호출 0회의 offline 보완이다. 서버의 논리 계약은 한 글자도 약화하지 않고, HCX에
보내는 wire 표현만 별도 투영으로 분리했다.

| 유지 | 변경 |
|---|---|
| `SUBMISSION_SCHEMA`(provider-neutral 정본) | `hcx_tool_definition()`이 이 객체를 그대로 넘기지 않음 |
| `parse_submission` 전체 검증 | 새 `hcx_wire.py`가 deep-copy 투영을 생성 |
| `validate` 서버 판정 | wire vocabulary를 0-A 성공 schema의 keyword로 축소 |
| Tool 이름 `submit_semantic_query` | — (이름과 schema를 동시에 바꾸지 않음) |

Ontology, Semantic Registry, Execution Registry, 조회 store, F 산출물,
`IMPLEMENTATION_PLAN.md`는 수정하지 않았다.

## C. 무엇을 근거로 keyword를 골랐는가

0-A에서 실제로 수용된 `record_question_semantics` 선언
(`src/canna/experiments/semantic_probe/encodings.py`, `NestedEncoding.tool_schema`)이 사용한
vocabulary만 남겼다. 같은 OpenAI-style function envelope, 같은 forced `tool_choice`, 같은
nested object/array, 같은 `additionalProperties: false`가 이미 성공한 조합이므로 그것들은
변수가 아니다. 두 선언이 공유하지 않는 것은 JSON Schema keyword뿐이다.

| wire 유지 | wire 제거 |
|---|---|
| `type`, `properties`, `required`, `items`, `enum`, `description`, `additionalProperties` | `$schema`, `$id`, `title`, `x-*`, `pattern`, `minLength`, `minItems` |

투영은 자기 입력에 대해 fail-closed다. 유지 목록에도 제거 목록에도 없는 keyword가
schema에 새로 생기면 조용히 통과시키거나 조용히 지우지 않고 `HcxWireError`로 실패한다.

## D. 측정값

`json.dumps(..., ensure_ascii=False, sort_keys=True)` UTF-8 byte 기준이다.

| 대상 | 변경 전 | 변경 후 | 차이 |
|---|---:|---:|---:|
| `hcx_tool_definition()` 전체 | 4,269 | 3,607 | −662 (−15.5%) |
| `function.parameters` schema | 3,937 | 3,275 | −662 (−16.8%) |
| (참고) 0-A에서 수용된 nested 선언 전체 | — | 2,271 | — |

재귀 keyword 차이:

```text
제거됨: $id, $schema, minItems, minLength, pattern, title, x-contract-status
남음  : additionalProperties, description, enum, items, properties, required, type
추가됨: (없음)
0-A 수용 선언의 vocabulary에 포함되는가: True
```

이번 보완은 **keyword vocabulary 가설을 시험할 수 있게 만든 것**이지 어떤 가설을 제거한
것이 아니다. 아직 호출하지 않았으므로 검증된 것은 없다. 또한 keyword를 지우면서 선언이
662 byte 작아졌고 크기는 여전히 0-A 성공 선언(2,271)보다 크므로, 이 변경은 keyword와
크기를 완전히 분리하지 못한다. 다음 실험의 결과 해석에 이 한계를 그대로 반영한다(G절).

## E. 서버 검증이 그대로임을 무엇으로 증명했는가

`tests/runtime_view/test_hcx_wire_projection.py` 20건을 추가했다. wire에서 규칙이 사라진
것과 서버가 여전히 거부하는 것을 각각 짝지어 확인한다.

| wire에서 사라진 것 | 같은 테스트가 확인하는 서버 거부 |
|---|---|
| ref `pattern` | 짧음·김·비16진수 ref → `malformed_reference` |
| span `minLength` | `source_span`, `direction_span`, `comparison_span`/`value_span`, `function_span` 빈 값 → `missing_required_span` |
| `requirements`의 `minItems` | 요구 0개 → `empty_submission` |
| (유지) `additionalProperties: false` | 알 수 없는 property → `unknown_property` |

그 밖에 확인한 것:

- 투영이 `SUBMISSION_SCHEMA`를 mutate하지 않고, 두 객체가 **어떤 하위 객체도 공유하지 않는다**
  (id 집합 교집합 0). 호출마다 새 객체다.
- 제거 대상 keyword가 재귀 탐색과 직렬화 문자열 양쪽에서 0건이다. 제거 전 원본에는
  실제로 존재했음을 함께 단언해, 아무것도 지우지 않고 통과하는 것을 막는다.
- property 이름, `required`, `enum`, 중첩 구조, `additionalProperties`가 논리 schema와
  완전히 일치한다(제거 keyword를 무시한 구조 동등 비교).
- wire에도 SQL/table/column/join/semantic_id/traversal/plan slot이 없다.
- stub `bind_tools`까지 전달된 `parameters`가 `hcx_wire_schema()`와 같고 vocabulary가
  허용 집합 이내다. 외부 호출 0회.
- schema/parser parity 기존 테스트는 그대로 두었다. 다만
  `test_the_hcx_adapter_wraps_the_same_schema_without_copying_it`은 "adapter가
  `SUBMISSION_SCHEMA` 객체 자체를 넘긴다"는 단언이었으므로, 투영을 넘기고 정본은
  `tool_definition()["input_schema"]`가 유지한다는 단언으로 대체했다.

## F. 검증 명령과 실제 출력

```powershell
uv run --cache-dir .tmp/uv-cache python -m pytest tests/runtime_view -q --basetemp=.tmp/pytest-hcxwire
```

```text
139 passed, 1 deselected in 0.78s
```

```powershell
uv run --cache-dir .tmp/uv-cache python -m pytest -q --basetemp=.tmp/pytest-hcxwire-full -rs
```

```text
598 passed, 5 deselected in 21.19s
```

```powershell
uv run --cache-dir .tmp/uv-cache python -m pytest -q -m "hcx_live or embedding_live" --basetemp=.tmp/pytest-hcxwire-optin -rs
```

```text
5 skipped, 598 deselected in 1.90s
```

```powershell
uv run --cache-dir .tmp/uv-cache ruff check src tests
```

```text
All checks passed!
```

`git diff --check`는 출력 없이 exit 0이다. 이번 작업의 외부 API 호출은 **0회**이며 commit,
push, branch, worktree 생성도 하지 않았다.

## G-0. G절 실험은 2026-08-31에 실행됐고 거부됐다

아래 G절은 실험 **설계**다. 실제 실행 결과는
`HCX_WIRE_PROJECTION_LIVE_RESULT_20260831.md`에 있으며 요약은 다음과 같다.

- 투영 schema(`parameters` 3,275 byte, tool definition 3,607 byte)로 승인 질문 1회 호출
- provider schema acceptance `rejected`, error `api` / `40009`, retry 0, embedding 0
- **Tool 생성 없음** → parser 미실행(`parser_well_formed=no`, arguments 없음)
- 기록 문구: **현재 keyword projection만으로는 provider rejection이 해결되지 않았다.**
  제거한 keyword가 원인이 아니었다고 단정하지 않는다.
- 추가 호출 없음. 다음 후보였던 function name 1회 실험은 G-1절대로 실행됐다.

## G-1. function name 1회 실험도 2026-08-31에 실행됐고 거부됐다

G절 마지막의 원인 분리 실험(다른 조건 고정, `function.name`과 강제 `tool_choice` 이름만
0-A 성공 이름 `record_question_semantics`로 교체)을 1회 실행했다. 결과 정본은
`HCX_NAME_PROBE_LIVE_RESULT_20260831.md`다.

- tool definition 3,611 byte, provider schema acceptance `rejected`, error `api` / `40009`
- retry 0, embedding 0, 외부 호출 1회, 다른 live 테스트 미실행
- **Tool 생성 없음** → parser 미실행(arguments 없음)
- 이름 변경은 `tests/runtime_view/test_hcx_name_probe_live.py`에만 격리했다. 서버 계약의
  `FUNCTION_NAME`은 `submit_semantic_query` 그대로이며, probe 이름은 0-A 선언에서
  import하고 "이름만 되돌리면 기준 선언과 동일"을 offline 가드가 단언한다.
- 기록 문구: **keyword projection에 더해 0-A 성공 function name까지 적용해도 provider
  rejection이 해결되지 않았다.** function name이 원인이 아니었다고 단정하지 않으며,
  앞서 제거한 keyword에 대한 판단도 그대로 유보한다.
- 개별로 움직인 두 변수(keyword vocabulary, function name)는 각각 단독으로 충분하지
  않았다. 남은 차이는 선언 내용(크기 3,611 vs 0-A 2,271, property 개수, 구조 깊이,
  특정 property 이름)이며 서로 분리해 움직이기 어렵다. 따라서 다음 단계는 단일 변수
  원인 분리가 아니라 **compatibility minimization**으로 표시할 것을 권고한다.
- 추가 호출 없음. 다음 실험은 사용자 승인 전 실행 금지.

## G. 다음 단일 live 실험안 (설계 — 2026-08-31 1회 실행됨, G-0 참조)

목적은 keyword vocabulary 가설을 **한 번 시험하는** 것이다. 이 실험 하나로 `40009`의
유일 원인을 확정하지는 못한다.

- 질문, Runtime View 구성, system/human 메시지, 강제 `tool_choice`, tool 이름
  `submit_semantic_query`, retry 0, embedding 0: **2026-08-31 실행과 동일**하게 고정한다.
- 유일한 변경: `function.parameters`가 `hcx_wire_schema()` 투영이다.
- 호출 1회. 실패해도 같은 세션에서 재시도하지 않는다.
- 기록 항목은 2026-08-31 결과 문서와 동일한 표를 쓰고, `provider_schema_acceptance`,
  error code, tool emit 여부, 선언 byte 크기를 함께 남긴다.

### 결과를 어떻게 기록할 것인가

이 실험은 관측 1회이므로 결론이 아니라 **가설과의 일치 여부**만 기록한다.

- **수용됨** → `keyword vocabulary incompatibility 가설과 일치한다`로 기록한다.
  keyword 제거가 유일한 원인이라고 확정하지 않는다. 이번 투영은 keyword 제거와 동시에
  선언 크기도 662 byte 줄였으므로(4,269 → 3,607), 한 번의 성공은 두 변화의 결합 효과와도
  양립한다. 확정하려면 반대 방향 확인(투영 schema에 제거한 keyword 하나만 되돌려 다시
  거부되는지)이 필요하며, 그것은 별도 승인 사항이다.
- **다시 `40009`** → `현재 keyword projection만으로는 provider rejection이 해결되지 않았다`로
  기록한다. **제거한 keyword가 원인이 아니었다고 단정하지 않는다.** 원인이 복수이거나
  keyword가 필요조건이었을 가능성이 남아 있고, 이 관측은 "이 변경만으로는 충분하지 않다"만
  보여 준다.
- **그 밖의 오류 코드** → provider 오류로 분류하고 원인 분리에 쓰지 않는다.

### 투영 후에도 거부될 경우의 다음 1회 (원인 분리)

다음 1회는 **function name과 강제 `tool_choice`의 이름만** 기존 성공 이름
`record_question_semantics`로 바꾸는 실험을 권고한다. 질문, Runtime View, 메시지,
`function.parameters`(투영 schema), retry 0, embedding 0을 포함한 나머지 조건은 전부
그대로 둔다. 이름은 0-A에서 실제로 수용된 값이므로 새 변수를 도입하지 않는다.

- 수용됨 → `tool name 가설과 일치한다`. 단, 이름 하나로 확정하지 않고 이후 계약상
  어떤 이름을 쓸지는 사용자·Codex 결정 사항이다.
- 다시 `40009` → 이름과 keyword 어느 쪽도 단독으로 설명하지 못한다. 남는 후보는 선언
  크기, property 개수, 구조 깊이, 특정 property 이름이다.

### compatibility minimization (단일 변수 실험이 아님)

관계·집계 slot을 함께 덜어 낸 "최소 ranking schema"는 **크기·property 개수·구조를 동시에
바꾸므로 단일 변수 실험이 아니다.** 이전 절에서 이를 단일 변수 후보처럼 적었던 것을
정정한다. 필요해지면 원인 분리가 아니라 `compatibility minimization`으로 따로 표시하고,
"무엇이 원인인가"가 아니라 "수용되는 최소 선언이 존재하는가"를 묻는 실험으로 기록한다.
여기서 수용되더라도 어떤 개별 요소가 원인인지는 알 수 없으며, 논리 계약을 그 최소
선언으로 축소한다는 뜻도 아니다.

이 실험은 Retriever 품질, 의미 선택 정확도, DB 실행, 최종 답변 품질을 평가하지 않는다.
성공하더라도 B 단계나 `IMPLEMENTATION_PLAN.md`의 production 상태를 완료로 바꾸지 않는다.

---

# 2026-08-31 6차 grouped-flat wire 전환 (상태: 여전히 provisional / correction required)

## A. 왜 전환했는가

`RUNTIME_VIEW_TOOL_DECISION_20260831.md` 5절이 이미 승인한 fallback이다. "nested schema를
primary로 유지하고 provider 제약이 재현되면 동일한 논리 계약을 반복 `requirement_id`로 묶은
grouped-flat encoding으로 전환한다."

제약은 재현됐다. 2026-08-31 단일 호출 3회가 모두 tool emit 이전에 `40009`로 거부됐다
(neutral schema / keyword projection / projection + 0-A 성공 function name). 추가 원인 분리
실험은 사용자 지시로 중단했다.

0-A 최종 평가 3묶음 총 93회의 provider failure는 `grouped_flat` **0회**, `nested` 24회,
`delimited` 5회다. `delimited`는 enum을 실을 수 없어 ref 무결성이 무너지므로 후보가 아니다.

## B. 무엇이 바뀌고 무엇이 그대로인가

| 그대로 | 바뀜 |
|---|---|
| `SUBMISSION_SCHEMA` (provider-neutral 정본, byte 3,937 불변) | `hcx_tool_definition()`이 grouped-flat wire schema를 전송 |
| canonical `Submission`/`SubmittedRequirement` 데이터 구조 | 새 `grouped_flat.py`가 wire↔canonical 변환 |
| `parse_submission` fail-closed 검증 전체 | `parse_grouped_flat`이 조립 후 **같은 parser**에 넘김 |
| `validate` 서버 판정, reason code | live harness와 precondition test가 새 encoding 사용 |
| Tool 이름 `submit_semantic_query` | wire description이 grouped-flat 설명으로 교체 |

Tool 이름은 논리 계약과 wire 모두 `submit_semantic_query`다. wire alias는 만들지 않았다.
필요해지면 adapter(`schema.hcx_tool_definition`)에만 두도록 docstring에 명시했다.

Ontology, Semantic Registry, Execution Registry, 조회 store, F 산출물,
`IMPLEMENTATION_PLAN.md`는 수정하지 않았다.

## C. wire 구조

```text
requirement_records[]  requirement_id, kind, status, source_span, limit_span?
ref_records[]          requirement_id, role, ref
detail_records[]       requirement_id, detail_kind, ref, span, value_span?
unaccounted_spans[]    string
```

모든 record가 `requirement_id`를 반복해 요구와 결합한다. `role`과 `detail_kind`는 canonical
slot으로 라우팅되며, **ref 종류 검증은 기존 `query.SLOT_KINDS`가 그대로 수행한다.** 즉 ref
kind 규칙을 두 곳에 적지 않았다.

| role | canonical slot | 허용 ref |
|---|---|---|
| `target_dataset` | `target_dataset_refs` | `ds_` |
| `field` / `output_field` / `grouping_field` | 같은 이름의 list | `fd_` |
| `relationship_predicate` | `relationship.predicate_ref` | `pr_` |
| `relationship_anchor_entity` | `relationship.anchor_entity_ref` | `en_` |

| detail_kind | canonical | span 의미 |
|---|---|---|
| `condition` | `conditions[]` | `span`=비교 표현, `value_span`=값 표현 |
| `ordering` | `ordering` | `span`=정렬 표현 |
| `aggregation` | `aggregation` | `span`=집계 표현 |

**condition 하나가 record 하나다.** 비교와 값을 서로 다른 record로 쪼개지 않으므로, 한
요구에 조건이 둘이어도 짝이 어긋날 수 없다(`ARCHITECTURE.md` 4절의 parallel array 금지).
`ordering`·`aggregation`·관계 ref는 요구당 하나이며 두 번째 record는 병합하지 않고
`conflicting_record`로 거부한다.

조건값·비교·정렬·집계는 normalized 값이 아니라 원문 span으로만 전달된다. 테스트가
`gte`·`lte`·`desc`·`avg`·`0.03` 같은 정규화 결과가 wire에 나타나지 않음을 확인한다.

## D. 새 reason code (provisional internal)

기존 code는 그대로 재사용하고, 이 encoding만 가질 수 있는 구조 문제 5개를 추가했다.

`orphan_record`, `duplicate_record`, `conflicting_record`, `unknown_reference_role`,
`unknown_detail_kind`.

malformed ref, 빈 필수 span, 알 수 없는 kind/status/property, 요구 0개는 **기존 code
그대로**(`malformed_reference`, `wrong_reference_kind`, `missing_required_span`,
`unknown_requirement_kind`, `unknown_requirement_status`, `unknown_property`,
`empty_submission`) 거부된다. 새 encoding이 서버 판정을 바꾸지 않았다는 뜻이다.

## E. 측정값

| 대상 | byte |
|---|---:|
| provider-neutral `SUBMISSION_SCHEMA` (전송하지 않음) | 3,937 |
| grouped-flat wire `parameters` | 3,975 |
| tool definition 전체 | 4,386 |
| (참고) 0-A에서 provider failure 0회였던 grouped_flat 선언 | 2,445 |

wire keyword: `additionalProperties`, `description`, `enum`, `items`, `properties`,
`required`, `type` — 0-A 수용 vocabulary의 부분집합이다. 크기는 여전히 0-A 선언보다 크므로
**이번 전환이 수용을 보장하지 않는다.** encoding 실패율 근거에 따른 전환이며, 실제 수용
여부는 승인된 live 호출 전까지 알 수 없다.

## F. 테스트

`tests/runtime_view/test_grouped_flat.py` 36개 추가, 기존 파일 3개 갱신.

| 요구 | 테스트 |
|---|---|
| canonical → grouped-flat → canonical round-trip | `test_a_canonical_submission_survives_the_round_trip_unchanged` (조립 결과가 원본과 **완전 동일**), `test_the_round_trip_preserves_every_requirement_and_its_status` (직접 parse 결과와 query 동일) |
| 조건·정렬·limit·집계·관계·복수 requirement 보존 | `test_ordering_aggregation_limit_and_relationship_all_survive`, `test_conditions_keep_their_own_comparison_and_value_together` (조건 2개의 짝 유지) |
| unresolved/ambiguous 보존 | 같은 round-trip 테스트가 `[mapped, unresolved, ambiguous]` 3개 요구를 그대로 확인 |
| 잘못된 requirement_id | `test_a_record_naming_an_undeclared_requirement_is_refused` (ref/detail 양쪽), `test_a_record_without_a_requirement_id_is_refused` |
| duplicate/conflicting record | requirement·ref·detail 반복 3종 + ordering 충돌 + relationship predicate 충돌 |
| 잘못된 ref kind | `test_a_role_refuses_a_reference_of_the_wrong_kind` 6 role parametrize |
| malformed ref·빈 span | 기존 code로 거부됨을 4 role × 3 변형, span 4종으로 확인 |
| unknown property·물리 실행정보 | 최상위/requirement/ref record 3층 + wire schema property 이름 전수 + 직렬화 문자열 검사 |
| actual Runtime View offline binding | `test_the_actual_case_binds_the_grouped_flat_tool_without_a_call`, `test_approved_live_case_preconditions_hold_without_network` (실제 Registry ref로 grouped-flat 제출 → parse → validate) |
| keyword vocabulary | `test_hcx_wire_projection.py`를 투영기 자체 검증으로 재작성. nested·grouped-flat 두 schema에 대해 무변이·무공유·vocabulary·내용 무손실 확인 |

삭제: `tests/runtime_view/test_hcx_name_probe_live.py`. 그 실험은 중단됐고, 남겨 두면 다음
실행 때 grouped-flat schema에 옛 이름을 섞어 보내는 무의미한 호출이 된다. 관측 결과는
`HCX_NAME_PROBE_LIVE_RESULT_20260831.md`에 그대로 보존된다.

## G. 검증 명령과 실제 출력

```powershell
uv run --cache-dir .tmp/uv-cache python -m pytest tests/runtime_view -q --basetemp=.tmp/pytest-gf-all3
```

```text
175 passed, 1 deselected in 0.69s
```

```powershell
uv run --cache-dir .tmp/uv-cache python -m pytest -q --basetemp=.tmp/pytest-gf-full
```

```text
634 passed, 5 deselected in 37.97s
```

```powershell
uv run --cache-dir .tmp/uv-cache python -m pytest -q -m "hcx_live or embedding_live" --basetemp=.tmp/pytest-gf-optin -rs
```

```text
5 skipped, 634 deselected in 2.11s
```

```powershell
uv run --cache-dir .tmp/uv-cache ruff check src tests
```

```text
All checks passed!
```

`git diff --check` 출력 없이 exit 0. **외부 API 호출 0회.** commit, push, branch, worktree
생성 없음.

## H. grouped-flat 선언도 2026-08-31에 1회 호출됐고 거부됐다

E절의 "실제 수용 여부는 승인된 live 호출 전까지 알 수 없다"는 그 뒤 해소됐다. 결과 정본은
`HCX_GROUPED_FLAT_LIVE_RESULT_20260831.md`다.

- `tests/runtime_view/test_hcx_runtime_view_live.py` 하나만 지정 실행, 외부 호출 1회,
  retry 0, embedding 0, DB 실행 0, 추가 호출 0
- provider schema acceptance `rejected`, HTTP 400, `api` / `40009`,
  message category `Unsupported function`
- **Tool 생성 없음** → tool 이름 확인·arguments 조립·requirement_id 연결·ref 종류·
  source/order/limit span·semantic validation 전부 **평가 불가**
- 모델 응답이 없으므로 유출 평가 대상도 없다. 전송 선언과 Runtime View payload의
  무유출은 offline 테스트가 계속 강제한다

이로써 tool emit 이전 거부가 4회 누적됐다: neutral(4,269 byte), keyword projection(3,607),
projection + 0-A 성공 이름(3,611), grouped-flat(4,386).

### offline 구조 비교로 좁혀진 남은 차이

| 지표 | 0-A nested (수용) | 0-A grouped_flat (수용) | canna grouped-flat (거부) |
|---|---:|---:|---:|
| parameters byte | 2,012 | 2,186 | **3,975** |
| property slot / distinct 이름 | 13 / 13 | 16 / 13 | 17 / 14 |
| 최대 object 깊이 | 3 | 2 | 2 |
| enum 수 | 4 | 4 | 4 |
| description 개수 / byte | 5 / 613 | 3 / 576 | **19 / 2,167** |

구조 지표는 수용된 grouped_flat과 사실상 같고, 남은 큰 차이는 description 개수와 총 byte다.

### 기록 문구

**grouped-flat encoding으로 전환해도 provider rejection이 해결되지 않았다.** encoding
shape이 원인이 아니었다고 단정하지 않는다. 0-A의 `grouped_flat` provider failure 0/93과
이번 1회 거부는 모순되지 않는다 — 두 선언은 encoding이 같고 내용량이 다르다. keyword와
function name에 대한 이전 유보도 그대로다. 개별로 움직인 세 요소 중 어느 것도 단독으로
충분하지 않았고, 네 관측에서 함께 움직이지 않은 것은 **선언 내용량**이다. 가설이며 확정이
아니다.

### 다음 후보 (승인 전 실행 금지)

**compatibility minimization**을 권고한다. 가장 싼 형태는 property 이름·enum·구조·필수
여부·tool 이름을 전부 고정하고 **description 총량만 2,167 → 600 byte 수준으로 줄인**
grouped-flat 선언 1회다. 논리 필드를 하나도 제거하지 않으므로 계약 축소가 아니다. 다시
거부되면 provider 문서·지원 채널 확인 또는 tool 사용을 쓰지 않는 대안을 사용자·Codex
결정으로 검토할 것을 권고한다. 서버 검증 계약은 어느 경우에도 그대로 둔다.

## I. `40009` offline 진단 (2026-08-31, 외부 호출 0회)

정본은 `HCX_40009_OFFLINE_DIAGNOSIS_20260831.md`다. `httpx.MockTransport`로 실제 전송
body를 프로세스 안에서 캡처했고 header·API key·request ID는 읽지 않았다.

- endpoint `/v1/openai/chat/completions`, model `HCX-007`, `max_completion_tokens` 단독
  전송(`max_tokens` 부재), `tools` OpenAI function envelope, 강제 `tool_choice` 이름 일치를
  모두 확인했다.
- `thinking={"effort":"none"}`과 `reasoning_effort="none"`은 adapter가 **같은 wire field로
  변환**하므로 등가다(`chat_models.py`의 `validate_environment`). 둘을 충돌시키는 경로가 없다.
- 재직렬화 비교: 현재 설치된 SDK로 두 요청을 재구성하면 1–3회차 거부 요청과 0-A
  `grouped_flat` 선언 요청은 top-level key·envelope·JSON Schema keyword 집합이 같다.
  `max_completion_tokens`는 4회차에만 있었고 1–3회차도 거부됐으므로 4회차 거부의 원인은
  아니다.
- **판정 강도 정정.** adapter 직렬화 문제와 endpoint/API 종류 문제는 "배제"가 아니라
  **현재 SDK 재구성에서 차이 미발견 / 지지 관측 없음**이다. 0-A 당시의 raw HTTP body가
  보존돼 있지 않으므로 당시의 SDK 버전·클라이언트 설정·서비스 상태까지 같았다고 증명하지
  못한다.
- **"남은 차이는 선언 내용량뿐"이라는 표현은 철회한다.** 남은 차이는 Tool 선언 전체
  내용이며 최소한 function name, parameters byte와 description 총량, property 이름과 개수,
  enum 값, `required` 배열, 각 description의 내용, schema 내부 조합이 모두 다르다. 0-A
  안에서 더 작은 `nested`(2,012 byte)가 24회 거부되고 더 큰 `grouped_flat`(2,186 byte)이
  0회 거부돼 **단순 크기 임계값 가설**은 약화되지만, 특정 이름·property·enum 값·
  description·조합은 어느 것도 배제되지 않았다.
- 남는 두 가설은 (1) Tool 선언 내용과 (2) provider/서비스 앱의 HCX-007 Tool 지원 상태이며
  **현재 증거로 원인 순위를 정할 수 없다.** 어느 쪽이 더 유력하다고 적지 않는다. 사실은
  다음뿐이다. 서로 다른 선언 4개가 모두 tool emit 이전에 같은 code로 거부됐고(현재 4/4
  거부 관측, 표본 4회이며 같은 선언의 반복 관측 없음), 0-A에는 `40009`의 과거 일부 거부
  기록(24/93)이 있으며, 0-A 안에서 더 작은 선언이 더 자주 거부돼 크기 축은 약화된다.
- **"control 1회로 결정적으로 분리된다"는 철회한다.** 0-A에 같은 선언이 어떤 때는 수용되고
  어떤 때는 거부된 과거 일부 거부 기록이 있으므로 단일 관측은 다음까지만 말한다. control **수용** = 현재 시점에 최소 선언이 한 번 수용됐다는
  증거, control **거부** = 현재 시점에 최소 선언도 거부됐다는 증거. 어느 한 번의 결과도
  서비스 문제 또는 우리 선언 문제를 확정하지 못한다. 반복 관측 횟수는 사용자 승인 사항이다.
- control을 실행한다면 기존 `HcxSemanticProvider.call` 경로를 그대로 쓰지 않는다. 그 경로는
  자체 prompt·payload·retry·view 빌더를 함께 들고 오므로 tool 선언 외 변수가 같이 움직인다.
  현재 live harness의 endpoint·model·message·`reasoning_effort`·`max_completion_tokens=8192`·
  `max_retries=0`을 전부 고정하고 `tools`와 그에 종속된 `tool_choice` 이름만 0-A
  grouped-flat으로 교체하는 **격리 probe를 offline으로 먼저 준비**해야 한다. 승인 전에는
  probe 구현도 live 호출도 하지 않으며, 이번 작업에서는 준비하지 않았다.
- 회귀 테스트 `tests/runtime_view/test_hcx_request_body.py` 10개를 추가했다. 네트워크를
  쓰지 않으며 production 동작을 바꾸지 않는다. 두 선언 비교 테스트가 입증하는 것은
  **같은 schema keyword 집합과 서로 다른 직렬화 크기**뿐이며, 그 이름과 설명을 그렇게
  정정했다.

## J. HCX-007 Function Calling은 동작한다 — 최소 선언 control 수용 (2026-08-31)

정본은 `HCX_MINIMAL_TOOL_CONTROL_20260831.md`다.

- 프로젝트 내용이 전혀 없는 최소 선언(244 byte)을 같은 model·key·client·생성 파라미터로
  1회 호출했다. `accepted`, tool emit 1회, 이름 정확, arguments 파싱 성공. 외부 호출 1회,
  retry 0, embedding 0.
- 따라서 **HCX-007 Tool 경로를 blocked로 기록하지 않는다.** HCX-005 전환, selector/answer
  모델 분리, 구조화 출력 fallback은 모두 `40009` 분기의 대응이었고 이번에 발동하지 않았다.
- 이 1회는 앞선 4회 거부의 원인을 말해 주지 않는다. 최소 선언과 프로젝트 선언은 이름·
  property·enum·required·description·크기·조합이 모두 다르다.
- 성공 분기에 따라 **compatibility minimization을 구현했다.** wire `parameters`
  3,975 → 2,030 byte, tool definition 4,386 → 2,264 byte, description 19개 2,167 byte →
  9개 412 byte. 0-A에서 수용된 선언(2,186 / 2,445)보다 작다.
- 논리 계약은 그대로다. property 이름·개수, enum 값, `required`, 중첩,
  `additionalProperties: false`, tool 이름, `SUBMISSION_SCHEMA`, `parse_grouped_flat`,
  parser, validator, Runtime View, Registry, Ontology, DB 모두 미변경.
- 선언에서 뺀 안내(role 6종·detail_kind 3종의 의미, "condition 하나가 record 하나",
  status 선택 기준, span 원문 복사 금지 정규화)는 system message로 옮겼다.
- 다음은 축소된 선언으로 승인 질문 1회 호출이며 승인 전에는 실행하지 않는다.

## K. 축소 선언도 거부됨 — 크기·구조 가설 제거 (2026-08-31, 6회차)

정본은 `HCX_MINIMISED_DECLARATION_LIVE_RESULT_20260831.md`다.

- 축소 grouped-flat 선언(2,264 byte)으로 승인 질문 1회 호출 → `rejected`, `40009`.
  tool emit 없음, arguments 없음, ref validity `not_evaluated`, semantic validation `not_run`.
  외부 호출 1회, retry 0, 다른 schema·model 실험 0.
- **크기 가설과 구조 구성 가설이 제거된다.** 거부된 우리 선언은 0-A에서 93/93 수용된
  선언보다 작고(2,264 < 2,445), array 4·enum 4·`additionalProperties` 4·깊이 2·property
  수까지 사실상 같다.
- 남은 축은 (1) 선언의 구체 내용(function name, property 이름 14종, enum 값, 남은
  description 9개의 텍스트와 그 조합)과 (2) 서비스 측 변화다. 같은 날 최소 선언은
  수용됐으므로 function calling 자체가 꺼진 것은 아니다. 두 축은 현재 증거로 분리되지 않는다.
- 다음 권고는 **0-A 선언(`record_question_semantics`, 2,445 byte)을 오늘 그대로 1회 전송**
  하는 것이다. 크기·구조가 이미 맞춰져 있으므로 이 1회가 두 축을 가른다. 수용되면 내용
  축을 이분 탐색하고, 거부되면 declaration 조정을 멈추고 NCP 설정·문서·지원 채널 확인을
  사용자·Codex 결정으로 반환한다.
- `HCX-005` 전환과 Structured Output fallback은 실행하지 않았다.

## L. provider compatibility bridge — `40009` 해소 (2026-08-31, 7회차)

정본은 `HCX_BRIDGE_LIVE_RESULT_20260831.md`다.

- HCX wire tool `parameters`를 required string 하나(`submission_json`, tool definition
  332 byte)로 축소하고 grouped-flat payload를 그 문자열에 담았다. 필드·enum·작성 지침은
  system message가 싣는다(`hcx_bridge.submission_guidance()`가 서버 라우팅 표에서 생성).
- live 1회: **`provider_schema_acceptance=accepted`, `tool_emitted=yes`,
  `tool_name_exact=yes`.** 4회 연속이던 `40009`가 사라졌다.
- 다만 `parser_well_formed=no`로 **envelope/제출 파싱 단계에서 차단**됐다. 이번 harness가
  problem code를 남기지 않아 어떤 구조 문제였는지는 특정하지 못한다. 추가 호출 없이
  원인을 확정하지 않는다. 다음 호출부터 특정되도록 harness에 `parser_problem_codes`와
  `argument_keys` 기록만 추가했다(외부 호출 0, 계약 무변경).
- 서버 계약은 유지된다. `hcx_bridge`는 envelope 검사 4개(arguments가 object,
  `submission_json` 단독, JSON 파싱, 그 JSON이 object)만 추가하고 그 아래는 전부 기존
  `parse_grouped_flat` → `parse_submission` → `validate`가 결정한다. `test_hcx_bridge.py`
  32개가 거부 케이스마다 bridge 경유 결과와 기존 parser 직접 호출 결과의 code 집합·query가
  같은지 대조한다.
- `SUBMISSION_SCHEMA`, grouped-flat canonical 계약, parser, validator, Runtime View,
  Registry, Ontology, DB는 변경하지 않았다. 바뀐 것은 HCX wire envelope과 system message다.

## M. wire 지시 보완 — envelope은 맞고 JSON 유효성이 남았다 (2026-08-31, 8회차)

정본은 `HCX_BRIDGE_GUIDANCE_LIVE_RESULT_20260831.md`다. **`40009` compatibility 작업은
성공으로 종료했다.** 추가 schema minimization과 0-A control은 하지 않았다.

- `submission_guidance()`에 envelope 규칙 4개를 명시했다: 값은 object가 아니라 string,
  decode 결과가 grouped-flat object이며 `{`로 시작해 `}`로 끝날 것, code fence·설명·앞뒤
  문자 금지, `submission_json` 외 tool argument 금지. 질문·ref·상품군 예시는 넣지 않았다.
- `envelope_diagnostics()`로 승인된 5개 metadata만 남긴다(raw args type, argument keys,
  `submission_json` value type, JSON decode 여부, parser problem codes). payload 텍스트·
  span·reference는 기록하지 않으며 테스트가 강제한다.
- live 1회: provider `accepted`, tool emit `yes`, 이름 일치 `yes`,
  `raw_args_type=dict`, `argument_keys=["submission_json"]`,
  `submission_json_value_type=str`, **`json_decoded=no`**,
  최초 problem code **`malformed_submission_json`**.
- 보완이 목표한 두 가지는 달성됐다. 다른 tool argument가 없고, 값이 object가 아니라
  string이다. 남은 실패는 그 string이 유효한 JSON 문서가 아니라는 점 하나다.
- 원문을 기록하지 않으므로 code fence·앞뒤 문자·따옴표·잘림 중 무엇인지는 특정되지
  않는다. 추가 호출 없이 추측하지 않는다.
- Tool schema, Runtime View, grouped-flat canonical 계약, parser, validator, Registry,
  Ontology, DB는 변경하지 않았다.
- 다음은 내용이 아니라 **형태만** 남기는 진단 몇 개(code fence 시작 여부, 첫/끝 글자가
  `{`/`}`인지, 길이 대비 decode 오류 위치)를 승인받아 추가한 뒤 같은 호출 1회로 원인을
  특정하는 것이다.

## N. decode 실패 원인 특정 — 깨진 유니코드 이스케이프 (2026-08-31, 9회차)

정본은 `HCX_BRIDGE_SHAPE_DIAGNOSIS_20260831.md`다. Codex 토큰 소진으로 사용자가 직접
승인했다.

- 형태 전용 진단(길이, fence 시작 여부, 첫/끝 글자가 중괄호인지, 파서 오류 메시지, 오류
  위치 비율)을 추가했다. payload 문자·span·reference는 기록하지 않으며 테스트가 강제한다.
- live 1회: provider `accepted`, tool emit `yes`, 이름 일치, `argument_keys` 단독,
  값 타입 `str`, fence 없음, 첫 글자 `{` — 여기까지 정상. 차단은
  **`decode_error = "Invalid uXXXX escape"`(깨진 유니코드 이스케이프), 위치 비율 0.208**,
  `parser_problem_codes = ["malformed_submission_json"]`.
- 즉 모델이 한글 본문을 문자 그대로 쓰지 않고 유니코드 이스케이프로 쓰다가 하나를
  깨뜨렸다. `last_char_is_close_brace=false`는 이후 어긋남과 잘림 중 어느 쪽인지 원문 없이는
  가르지 않는다.
- 대응은 system message 지시 한 문단이다: 비ASCII는 문자 그대로 쓰고 유니코드 이스케이프로
  바꾸지 말 것, 백슬래시는 JSON이 요구하는 것만, 문서는 닫는 중괄호까지 완결할 것.
  질문·ref·상품군 예시는 넣지 않았다.
- Tool schema, Runtime View, grouped-flat canonical 계약, parser, validator, Registry,
  Ontology, DB는 변경하지 않았다. parser·validator 완화 없음.
- 다음은 같은 호출 1회다. 통과해 `canonicalizer_unavailable`만 남으면 provider/semantic
  mapping 경로 확보로 판정하되, `semantic_valid`는 False이며 실행은 계속 차단된다.

## O. 이스케이프 축 해결, 실패 축이 잘림으로 이동 (2026-08-31, 10회차)

정본은 `HCX_BRIDGE_TRUNCATION_20260831.md`다.

- live 1회: provider `accepted`, tool emit `yes`, 이름 일치, `argument_keys` 단독,
  값 타입 `str`, fence 없음, 첫 글자 `{`. 여기까지 계속 정상이다.
- **이스케이프 축은 해결됐다.** `decode_error`가 깨진 유니코드 이스케이프에서
  `Expecting ',' delimiter`로 바뀌었고 오류 위치 비율이 0.208 → **1.0**으로 옮겨갔다.
  닫는 중괄호도 없다. 이 저장소 진단 테스트가 **잘림**으로 정의한 형태다.
- 길이도 486 → 571로 늘었다. 이스케이프를 쓰지 않으면 같은 내용이 토큰을 덜 쓰므로 예산이
  고정돼 있을 때 더 많은 문자가 통과한다는 방향과 맞는다.
- 잘림의 원인이 생성 예산 소진인지, provider의 tool-call argument 제한인지, 모델이 스스로
  멈춘 것인지는 이 관측으로 가려지지 않는다. `max_completion_tokens: 8192`이 실제 body에
  실린다는 것은 offline 회귀 테스트가 이미 확인했다.
- 다음 1회에서 이를 가르도록 응답 metadata 3개(`finish_reason`, `output_tokens`,
  `max_completion_tokens_sent`)를 기록하도록 harness만 고쳤다. 내용이 아니라 응답
  metadata이며, 앞서 승인받은 목록을 넘어서므로 명시해 둔다. 계약·parser·validator·
  schema·Registry·Ontology·DB는 변경하지 않았다.

## P. 잘림 원인 판별 — 예산 소진이 아니다 (2026-08-31, 11회차)

정본은 `HCX_BRIDGE_FINISH_REASON_20260831.md`다.

- live 1회: provider `accepted`, tool emit `yes`, 이름 일치. **`finish_reason="tool_calls"`,
  `output_tokens=269` / `max_completion_tokens_sent=8192`.**
- 따라서 생성 토큰 예산 소진은 **배제**된다. provider의 argument 길이 제한도 예산의 3%
  지점에서 정상 종료가 보고된 이상 지지 관측이 없다. 남는 설명은 **모델이 문서를 다
  썼다고 판단하고 열린 괄호를 남긴 채 종료했다**는 것이다.
- envelope 진단은 그대로 정상이다: `argument_keys` 단독, 값 타입 `str`, fence 없음,
  첫 글자 `{`. 오류는 여전히 맨 끝(`decode_error_position_ratio=1.0`,
  `Expecting ',' delimiter`, 닫는 중괄호 없음).
- 지금까지 축이 순서대로 해소됐다: `40009` → argument 오염 → object/string →
  fence·앞 설명문 → 깨진 유니코드 이스케이프 → **남은 것은 문서 완결성 하나**.
- 대응은 system message 한 문단이다: 한 줄 compact로 쓰고 줄바꿈·들여쓰기 금지, 내용 없는
  property는 비워 보내지 말고 생략, `requirement_id`는 한두 글자, 끝내기 전에 연 괄호가
  모두 닫혔는지 확인. 예산이 아니라 모델이 추적할 양을 줄이는 조치다.
- Tool schema, Runtime View, grouped-flat canonical 계약, parser, validator, Registry,
  Ontology, DB는 변경하지 않았다.
- 다음 1회에서도 같은 형태가 나오면, 지시로 완결성을 얻는 접근이 통하지 않는 것이다. 그때의
  선택지는 문자열 **안의 형식**을 따옴표 이스케이프가 필요 없는 줄 단위 표기로 바꾸는 것이며
  (wire 표현만 변경, canonical 계약·parser·validator 불변) 적용은 사용자 결정 사항이다.

## Q. 완결성 해결, 이스케이프 재발 — 두 결함이 번갈아 난다 (2026-08-31, 12회차)

정본은 `HCX_BRIDGE_ALTERNATION_20260831.md`다.

- live 1회: provider `accepted`, tool emit `yes`, 이름 일치, `finish_reason="tool_calls"`,
  `output_tokens=218` / 8192.
- **문서 완결성은 해결됐다.** `last_char_is_close_brace`가 처음으로 `true`다. 대신
  `decode_error`가 다시 이스케이프 결함이고 위치 비율은 0.208로 9회차와 같다.
- 두 지시(이스케이프 금지 / 완결·compact)가 **모두 프롬프트에 있는 상태에서** 11회차는
  이스케이프를 지키고 문서를 닫지 않았고, 12회차는 문서를 닫고 이스케이프를 썼다. 모델이
  한 번에 하나씩만 만족시킨다.
- 토큰은 계속 예산의 3% 이하이므로 공간 문제가 아니다. 남은 결함은 "JSON을 문자열 안에 다시
  쓰는" 과제 자체에서 나온다: 큰따옴표 이스케이프, 한글 비이스케이프, 괄호 균형이 서로
  경쟁한다.
- 해소된 축: `40009`, argument 오염, object/string, fence·앞 설명문, 문서 완결성.
  **남은 축: JSON 문법 정확성 하나.**
- 제안(승인 전 구현 금지): `submission_json` 안을 JSON이 아니라 **줄 단위 표기**로 바꾼다.
  따옴표도 괄호도 없으므로 이스케이프 결함과 불균형이 구조적으로 사라진다. 0-A에서
  `delimited`의 기각 사유는 provider 수용성이 아니라 enum 부재로 인한 ref 무결성이었고,
  지금은 enum을 system message가 싣고 서버가 전수 검증하므로 그 사유가 그대로 적용되지
  않는다. 다만 모델의 ref 선택 정확도 저하 가능성은 남는다.
- 바뀌는 것은 문자열 안의 표기와 그것을 grouped-flat 구조로 읽는 얇은 reader, 그리고 작성
  지침뿐이다. Tool schema, tool 이름, grouped-flat canonical 계약, parser, validator,
  Runtime View, Registry, Ontology, DB는 그대로다.

## R. 남은 미결정
- HCX 역할 축소안과 Confirmed HCX ①/semantic-query 작성 책임 변경 승인 여부
- 역할 축소안의 SpanLedger 실현 가능성, HCX가 선택할 candidate choice와 사람이 물어야 할
  materially ambiguous 상태의 구분
- option generation cap과 request-lifetime ref 정책의 측정·승인
- 공유 reason/status 축 계약. semantic mapping, canonicalization, execution readiness와
  answer status를 다시 합치지 않는다
- grouping, whole-comparison requirement, explanation canonicalizer
- entity resolution 계층과 계획 수준 실행 가능성 판정
- CanonicalPlan→ResolvedProductQuery production compiler
- Execution Registry row provenance/selection/dataset population binding
