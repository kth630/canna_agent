# 두 결함이 번갈아 나타난다 — 2026-08-31 (12회차)

상태: **provider 경계 통과 유지. 문서 완결성은 해결, 이스케이프 결함 재발.**
B는 `provisional / correction required` 유지.

## 결과

```text
provider_schema_acceptance: accepted   tool_emitted: yes   tool_name_exact: yes
finish_reason: "tool_calls"            output_tokens: 218 / 8192
envelope: {
  argument_keys: ["submission_json"], submission_json_value_type: "str",
  starts_with_code_fence: false, first_char_is_open_brace: true,
  last_char_is_close_brace: true,
  json_decoded: "no", decode_error: "Invalid \uXXXX escape",
  decode_error_position_ratio: 0.208, length: 472,
  parser_problem_codes: ["malformed_submission_json"]
}
external_call_count: 1   retry_count: 0
```

외부 호출 1회, retry 0, 다른 schema·model 호출 0. arguments 원문은 기록하지 않았다.

## 세 회차 비교

| 진단 | 9회차 | 11회차 | 12회차 |
|---|---|---|---|
| 지시: 이스케이프 금지 | 없음 → 추가 | 있음 | 있음 |
| 지시: 완결·compact | 일부 | 일부 | 추가 |
| `last_char_is_close_brace` | false | false | **true** |
| `decode_error` | 이스케이프 | 구문(끝) | **이스케이프** |
| `decode_error_position_ratio` | 0.208 | 1.0 | **0.208** |
| length / output_tokens | 486 / — | 545 / 269 | 472 / 218 |

**두 지시가 모두 프롬프트에 있는 상태에서 결함이 번갈아 나타난다.** 11회차에는 이스케이프를
지켰지만 문서를 닫지 않았고, 12회차에는 문서를 닫았지만 다시 이스케이프로 썼다. 오류 위치
0.208은 두 이스케이프 실패에서 동일하며, 첫 한글 span이 나오는 지점과 부합한다.

`finish_reason`은 계속 `tool_calls`이고 토큰 사용량은 예산의 3% 이하다. 공간 문제가 아니다.

## 이 관측이 말하는 것

지시를 더 정교하게 쓰는 방식으로 이 모델에서 **JSON 문자열의 문법적 정확성을 안정적으로
얻지 못한다.** 남은 결함 두 가지는 모두 "JSON을 문자열 안에 다시 쓰는" 과제 자체에서 나온다.

- 큰따옴표를 `\"`로 이스케이프해야 하고
- 한글을 이스케이프하지 말아야 하며
- 중첩된 중괄호·대괄호를 끝까지 균형 맞춰야 한다

이 세 부담은 서로 경쟁하며, 관측상 모델이 한 번에 하나씩만 만족시킨다.

## 지금까지 해소된 축과 남은 축

| 축 | 상태 |
|---|---|
| provider schema 거부 `40009` | 해소 (bridge envelope) |
| tool argument 오염 | 해소 (`argument_keys` 단독) |
| object vs string | 해소 (`str`) |
| code fence·앞 설명문 | 해소 |
| 문서 완결성 | 해소 (12회차 `last_char_is_close_brace=true`) |
| **JSON 문법 정확성(이스케이프)** | **남음** |

## 제안 — 문자열 안의 형식을 바꾼다 (승인 전 구현 금지)

`submission_json` 안을 **JSON이 아니라 줄 단위 표기**로 바꾼다. 0-A `delimited` encoding과
같은 형태이며, 따옴표도 중괄호도 이스케이프도 필요 없다.

```text
REQ|r1|ranking|mapped|<원문 span>|<limit span>
REF|r1|target_dataset|<ref>
DET|r1|ordering|<ref>|<span>|<value span>
UNACC|<원문 span>
```

- 이스케이프 불가능성: 큰따옴표를 쓸 일이 없으므로 `\u` 결함이 구조적으로 사라진다.
- 완결성: 균형을 맞출 괄호가 없다. 줄이 잘리면 그 줄만 거부된다.
- 0-A 근거: `delimited`는 93회 중 provider failure 5회로 세 encoding 중 중간이었고, 당시
  기각 사유는 provider 수용성이 아니라 **enum을 실을 수 없어 모델의 ref 무결성이 무너진다**는
  것이었다. 지금은 enum을 JSON Schema가 아니라 system message가 싣고 **서버가 전수
  검증**하므로 그 사유는 이 경로에 그대로 적용되지 않는다. 다만 모델의 ref 선택 정확도가
  나빠질 가능성은 남으며, 그것은 이번 관측이 답하지 않는다.

### 바뀌는 것과 바뀌지 않는 것

- 바뀜: `submission_json` 안의 표기, 그것을 grouped-flat 구조로 읽는 얇은 reader,
  system message의 작성 지침.
- 그대로: Tool schema(required string 하나), tool 이름, grouped-flat canonical 계약,
  `parse_grouped_flat`, `parse_submission`, `validate`, Runtime View, Registry, Ontology, DB.
  reader는 조립만 하고 규칙은 기존 parser가 그대로 결정한다.

### 대안 (덜 권함)

지시를 더 손보는 방법이 남아 있기는 하다. 예: 한글 span을 짧게 자르도록 유도하거나
요구 개수를 줄이도록 유도하는 것. 그러나 12회차까지의 관측은 지시 조정이 두 결함을 동시에
만족시키지 못한다는 쪽을 가리키고, 승인 질문은 요구가 하나뿐인 가장 단순한 경우다.

## Offline 검증

이번 회차에서 코드 변경은 없다. 직전 회차의 지시 보완 상태 그대로 호출했다.

```text
전체 offline suite : 693 passed, 6 deselected
ruff src tests     : All checks passed!
git diff --check   : exit 0
```
