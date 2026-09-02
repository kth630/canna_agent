# Bridge wire 지시 보완 live 검증 — 2026-08-31 (8회차)

상태: **provider 경계는 계속 통과. 차단은 `submission_json` 문자열의 JSON 유효성.**
B는 `provisional / correction required` 유지.

## 결과

```text
HCX_RUNTIME_VIEW_RESULT={
 "provider_schema_acceptance": "accepted", "tool_emitted": "yes", "tool_name_exact": "yes",
 "parser_well_formed": "no", "ref_validity": "not_evaluated",
 "semantic_validation": "not_run", "execution_readiness": "not_evaluated/non-executable",
 "external_call_count": 1, "retry_count": 0,
 "envelope": {"raw_args_type": "dict", "argument_keys": ["submission_json"],
              "submission_json_value_type": "str", "json_decoded": "no",
              "parser_problem_codes": ["malformed_submission_json"]}}
```

외부 호출 1회, retry 0, 다른 schema·model 호출 0.

## 최초 problem code

**`malformed_submission_json`.** `submission_json` 문자열이 JSON으로 decode되지 않았다.

## 7회차 대비 무엇이 나아졌는가

| 진단 항목 | 7회차 | 8회차 |
|---|---|---|
| provider acceptance | accepted | accepted |
| tool emit / 이름 | yes / yes | yes / yes |
| raw args type | 미기록 | `dict` |
| argument keys | 미기록 | `["submission_json"]` — **다른 property 없음** |
| `submission_json` value type | 미기록 | `str` — **object가 아닌 string** |
| JSON decode | 미기록 | **`no`** ← 여기서 차단 |
| parser problem code | 미기록 | `malformed_submission_json` |

지시 보완이 목표로 한 두 가지는 달성됐다. 모델은 **다른 tool argument를 만들지 않았고**,
`submission_json`을 **object가 아니라 string으로** 보냈다. 남은 실패는 그 string이 유효한
JSON 문서가 아니라는 점 하나다.

## 원인 특정의 한계

지시에 따라 실제 arguments 원문을 기록하지 않았으므로, decode 실패가 markdown code fence,
앞뒤 설명 문자, 작은따옴표, 잘림(truncation), 이스케이프 오류 중 어느 것인지는 이 관측으로
특정되지 않는다. 추가 호출 없이 추측하지 않는다.

## 변경한 것

- `hcx_bridge.submission_guidance()`에 envelope 규칙 4개를 명시했다: 값은 object가 아니라
  string이다, decode 결과가 grouped-flat object여야 하며 `{`로 시작해 `}`로 끝나야 한다,
  markdown code fence·언어 태그·설명·앞뒤 문자를 넣지 않는다, `submission_json` 외의 tool
  argument를 만들지 않는다. 질문·ref·상품군 예시는 넣지 않았다.
- `hcx_bridge.envelope_diagnostics()`를 추가해 승인된 5개 metadata만 남긴다. payload 텍스트,
  span, reference는 기록하지 않으며 그 사실을 테스트가 강제한다.

## 변경하지 않은 것

Tool schema, Runtime View, grouped-flat canonical 계약, `parse_grouped_flat`,
`parse_submission`, `validate`, Semantic/Execution Registry, Ontology, DB. parser와 validator
규칙은 한 줄도 완화하지 않았다.

## Offline 검증

```text
tests/runtime_view : 225 passed, 1 deselected
전체 offline suite : 684 passed, 6 deselected
ruff src tests     : All checks passed!
```

추가한 테스트: 지시가 string/not-object·code fence 금지·앞뒤 문자 금지·타 argument 금지·
`{`~`}` 규칙을 실제로 담고 있는지, 질문·ref·상품군을 하드코딩하지 않았는지, 진단 metadata가
payload 내용을 담지 않는지, 진단이 차단 단계를 정확히 지목하는지. 기존 bridge 거부 테스트
32개와 canonical parser/validator 동등성 대조는 그대로 유지된다.

## 다음 (승인 전 실행 금지)

`json_decoded=no`의 이유를 내용 기록 없이 좁히려면 **shape 전용 진단 몇 개**가 더 필요하다.
예: 문자열이 code fence로 시작하는지(boolean), 첫 글자와 마지막 글자가 `{`/`}`인지(boolean),
길이와 decode 오류 위치의 비율(잘림 판별용). 모두 내용이 아니라 형태만 남긴다. 이는 승인된
metadata 5개를 넘어서므로 사용자 승인 후에 추가한다.

그 뒤 같은 호출 1회로 원인을 특정하고, 그에 맞춰 system message 지시만 다시 보완한다.
parser·validator 완화는 어느 경우에도 하지 않는다.
