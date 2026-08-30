# Purpose-based question fixtures

이 디렉터리의 질문은 제품 사양이나 정답 목록이 아니라 capability와 실패 경계를
반증하기 위한 fixture다. 질문만 추가할 수 없으며 다음 metadata가 필수다.

```yaml
test_id: stable test identifier
test_purpose: 이 질문으로 확인하려는 한 가지 목적
capability_under_test: 일반화된 capability 이름
question: 의미가 유일하게 결정되는 자연어 질문
question_structure:
  targets: []
  conditions: []
  relationships: []
  requirements: []
  nested: []
  comparisons: []
runtime_view_candidate_keys: []      # 이 질문에 제시할 합성 후보의 catalog key
expected_decision:
  target_dataset_keys: []
  requirement_sets:                  # 서로 동등한 회계 대안들
    - - label: ...
        status: mapped | unresolved | ambiguous
        kind_alternatives: []
        ref_key_alternatives: [[...]]
        span_anchors: []             # 이 요구의 span에 반드시 들어가야 할 원문 조각
        details: []                  # 조건·관계·정렬·개수·비교 대상
falsifies_if: 어떤 관측이면 가설이 깨지는지
semantic_clarity: explicit
provenance: authored | non_authoritative_test_example
split: primary | regression | verification
```

## 합격 기준

한 case는 아래를 모두 만족할 때만 통과한다.

- 응답의 모든 ref가 그 요청의 Runtime View에 실재한다.
- target dataset 집합이 기대와 정확히 같다.
- `requirement_sets`의 어느 한 대안과 요구가 1:1로 대응한다. 누락도 과잉도 없다.
  선언된 동등 대안이 아니면 요구 개수가 달라지는 순간 실패다.
- 모든 요구가 질문 원문에서 그대로 잘라 낸 span을 기록하고, 요구가 여러 개면 서로 다른
  span을 쓴다. 각 요구의 span은 fixture가 선언한 anchor를 포함한다.
- 각 요구의 조건 대상·비교 방식·비교 값, 관계 방향과 지목된 entity, 정렬 기준과 방향,
  요청 개수, 비교 대상이 모두 보존된다.

## split

- `primary`: 계약과 prompt를 조정하면서 반복 실행하는 개발용 집합이다.
- `regression`: 한때 holdout이었으나 결과를 보고 수정했으므로 더 이상 처음 보는 질문이
  아니다. 회귀 확인용으로만 쓴다.
- `verification`: 모든 수정이 끝난 뒤 1회만 실행하는 집합이다. 이 결과를 보고 계약이나
  prompt를 고치면 그 순간 이 split도 regression으로 강등해야 한다.

## 규칙

- 일반 기능 질문은 필요한 상품군, field period/unit, 관계 방향과 결과 범위가 명확해야 한다.
- 모든 fixture는 `semantic_clarity: explicit`이어야 한다. 애매한 자연어 질문은 등록하지
  않는다. `ambiguous`는 candidate grounding 또는 source resolution이 결정되지 않을 때
  서버가 임의 실행을 막기 위한 런타임 상태다.
- exact question text, test ID 또는 expected decision을 runtime code에서 참조하지 않는다.
- `semantic_probe_catalog.json`의 후보는 전부 합성이다. 실제 상품명·종목명·수치가 아니며
  실행 코드에도 들어가지 않는다. `catalog_key`와 `dataset_key`는 채점 전용이라 모델에게
  보내지 않고, 상품군 소속은 요청마다 새로 발급한 `belongs_to_dataset_ref`로만 전달한다.
- 기존 35문항은 목적과 구조를 새로 annotation한 뒤에만
  `non_authoritative_test_example`로 가져온다.
- 같은 capability에 paraphrase, field neighbor, entity neighbor, coverage boundary와 unseen
  structural combination을 추가한다.
- fixture가 하나의 물리 plan만 강제하지 않는다. 의미가 같은 실행은
  `ref_key_alternatives`와 `requirement_sets`로 허용한다.
