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
expected_decision: 구조화된 기대 판정
falsifies_if: 어떤 관측이면 가설이 깨지는지
ambiguity_intentional: false
provenance: authored | non_authoritative_test_example
```

## 규칙

- 일반 기능 질문은 필요한 상품군, field period/unit, 관계 방향과 결과 범위가 명확해야 한다.
- `ambiguity_intentional: true`는 ambiguity detection/refusal 테스트에서만 허용한다.
- exact question text, test ID 또는 expected decision을 runtime code에서 참조하지 않는다.
- 기존 35문항은 목적과 구조를 새로 annotation한 뒤에만
  `non_authoritative_test_example`로 가져온다.
- 같은 capability에 paraphrase, field neighbor, entity neighbor, coverage boundary와 unseen
  structural combination을 추가한다.
- fixture가 하나의 물리 plan만 강제하지 않는다. 의미가 같은 실행은
  `equivalent_alternatives`로 허용한다.
