# HCX Runtime View live schema probe — 2026-08-31

상태: **provider rejected / B는 provisional·correction required 유지**

## 승인된 범위

- 질문: `국내 ETF 중 1년 수익률이 높은 10개를 보여줘.`
- 신규 `hcx_tool_definition()`과 actual Runtime View의 provider 수용성만 확인
- HCX 외부 호출 1회, retry 0회
- rule-only Retriever 사용, embedding 호출 0회
- DB 실행·최종 답변 생성 없음

질문과 expected invariant는 격리된 live test에만 있으며 production runtime 분기에 넣지 않았다.
dataset과 field expected ref는 actual Semantic Registry의 groundable 후보 중 dataset family·grain과
`P1Y` period·`order` operation이 유일하게 결합하는 쌍에서 요청 단위로 생성했다. semantic ID나
opaque ref를 fixture expected 값으로 고정하지 않았다.

### 테스트 metadata

- `test_purpose`: 신규 `submit_semantic_query` Schema의 HCX provider 수용성 확인
- `capability_under_test`: actual Runtime View dataset/field opaque ref 선택, ranking requirement
  회계, source/order/limit 원문 span 보존
- `question_structure`: 국내 ETF target, ranking requirement, 1년 수익률 metric, 높은 순,
  limit 10
- `semantic_clarity`: `explicit`
- `expected_invariant`: provider schema 수용, 정확한 tool name, actual view ref만 사용,
  source/direction/limit span 정렬, 물리 실행정보 미생성
- `falsifies_if`: schema 거부, tool call 부재, invented ref, 질문 밖 span, ranking 구성요소 누락,
  물리 실행정보 생성

## Offline precondition

실제 Semantic Registry, 읽기 전용 Execution Registry adapter, rule-only Retriever로 Runtime
View를 만들었다. 필요한 dataset과 field가 모두 존재했고 field가 target dataset에 결합됐으며,
model payload에 stable semantic ID나 물리 binding이 없음을 확인했다.

```text
tests/runtime_view/test_hcx_runtime_view_precondition.py: 1 passed
pre-live Ruff: All checks passed!
```

## 단일 live 결과

| 항목 | 결과 |
|---|---|
| provider schema acceptance | `rejected` |
| tool emitted | `no` |
| tool name exact | `no` — tool call이 나오지 않음 |
| parser well_formed | `no` — arguments가 없음 |
| ref validity | `not_evaluated` — arguments가 없음 |
| source span | `failed` — tool call이 없음 |
| direction span | `missing` |
| limit span | `missing` |
| semantic validation | `not_run` |
| execution readiness | `not_evaluated/non-executable` |
| 실제 HCX 외부 호출 | `1` |
| retry | `0` |
| embedding 호출 | `0` |

Provider는 tool을 emit하기 전에 API error code `40009`, message category
`Unsupported function`으로 요청을 거부했다. 이 기록에는 raw 응답, request/response ID,
header, token 또는 credential을 저장하지 않았다.

## 해석 한계

이 1회 관측은 현재 `hcx_tool_definition()` 전체가 이 provider 요청에서 수용되지 않았음을
보여 준다. 단일 호출만 승인됐으므로 function 이름, JSON Schema keyword, nested 구조,
`additionalProperties`, 강제 tool choice 중 어느 요소가 원인인지는 분리 실험하지 않았다.
fallback encoding이나 수정 schema에 대한 추가 호출도 하지 않았다.

이 결과는 Retriever 품질, 의미 선택 정확도, DB 실행, ranking 정답 또는 최종 답변 품질을
평가하지 않는다. `IMPLEMENTATION_PLAN.md`나 B production 상태를 완료로 바꾸지 않는다.

## 후속 (기록 후 추가)

이 관측에 대한 offline 대응은 `FINDINGS.md`의 "2026-08-31 5차 HCX wire compatibility 보완"에
있다. 서버 논리 계약은 그대로 두고 HCX wire 표현만 0-A에서 실제 수용된 keyword vocabulary로
투영했으며, 이 문서의 관측값은 수정하지 않았다. 다음 단일 live 실험은 사용자 승인 전에
실행하지 않는다.
