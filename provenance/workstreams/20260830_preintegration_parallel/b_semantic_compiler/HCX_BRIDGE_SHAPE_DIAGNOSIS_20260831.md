# `submission_json` decode 실패 원인 특정 — 2026-08-31 (9회차)

상태: **원인 특정됨 — 깨진 `\uXXXX` 이스케이프.** provider 경계는 계속 통과.
B는 `provisional / correction required` 유지.

승인 경위: Codex 토큰 소진으로 사용자가 직접 승인했다(형태 전용 진단 추가 + 호출 1회).

## 결과

```text
provider_schema_acceptance: accepted
tool_emitted: yes            tool_name_exact: yes
envelope: {
  raw_args_type: "dict",
  argument_keys: ["submission_json"],
  submission_json_value_type: "str",
  json_decoded: "no",
  parser_problem_codes: ["malformed_submission_json"],
  length: 486,
  starts_with_code_fence: false,
  first_char_is_open_brace: true,
  last_char_is_close_brace: false,
  decode_error: "Invalid \uXXXX escape",
  decode_error_position_ratio: 0.208
}
external_call_count: 1   retry_count: 0
```

외부 호출 1회, retry 0, 다른 schema·model 호출 0. 실제 arguments 원문은 기록하지 않았다.

## 진단

| 신호 | 값 | 해석 |
|---|---|---|
| `starts_with_code_fence` | false | markdown fence 아님 |
| `first_char_is_open_brace` | true | 앞쪽 설명문·라벨 없음 |
| `decode_error` | `Invalid \uXXXX escape` | **깨진 유니코드 이스케이프** |
| `decode_error_position_ratio` | 0.208 | 문자열 앞쪽 1/5 지점에서 실패 |
| `last_char_is_close_brace` | false | 문서가 `}`로 끝나지 않음 |

앞선 보완이 노린 세 가지(다른 argument 없음, object 아닌 string, fence·앞 설명 없음)는
모두 달성됐다. 남은 실패는 **본문을 문자 그대로 쓰지 않고 `\u` 이스케이프로 쓰다가 하나를
깨뜨린 것**이다. 0.208 지점은 첫 한글 span이 나올 위치와 부합한다.

`last_char_is_close_brace=false`는 두 가지로 읽힐 수 있다. 깨진 이스케이프 뒤로 문서가
계속 어긋났거나, 생성이 끝까지 가지 못했거나. 원문을 남기지 않으므로 둘을 가르지 않는다.

## 대응 — system message 지시만 보완

`hcx_bridge.submission_guidance()` 끝에 추가했다.

> Write Korean and other non-ASCII text as the characters themselves. Do not turn them
> into `\u` escape sequences. The only backslashes in the JSON should be the ones JSON
> requires inside a string, and the document must be complete, ending with the closing
> brace.

질문·ref·상품군을 하드코딩한 예시는 넣지 않았다. Tool schema, Runtime View, grouped-flat
canonical 계약, `parse_grouped_flat`, `parse_submission`, `validate`, Registry, Ontology,
DB는 변경하지 않았다. parser·validator 규칙은 완화하지 않았다.

## 추가한 형태 진단 (내용 미기록)

`length`, `starts_with_code_fence`, `first_char_is_open_brace`,
`last_char_is_close_brace`, `decode_error`(파서 메시지), `decode_error_position_ratio`.
모두 형태이며 payload 문자·span·reference는 담지 않는다. 테스트가 이를 강제하고, fence /
앞 설명문 / 잘림 / 따옴표 오류 / 깨진 이스케이프가 서로 다르게 보이는지도 확인한다.

## Offline 검증

```text
전체 offline suite : 692 passed, 6 deselected
ruff src tests     : All checks passed!
git diff --check   : exit 0
```

## 다음 (승인 전 실행 금지)

같은 호출 1회. 이스케이프 지시가 통하면 `json_decoded=yes`가 되고 grouped-flat parsing과
ref·scope·grain·span 검증으로 진행한다. 그 단계까지 통과해 `canonicalizer_unavailable`만
남으면 provider/semantic mapping 경로 확보로 판정한다. **그 경우에도 `semantic_valid`는
False이며 실행은 계속 차단된다.**

다시 실패하면 형태 진단이 어느 축으로 옮겨갔는지(`decode_error`가 escape에서 다른 것으로
바뀌었는지, `last_char_is_close_brace`가 여전히 false인지)만 보고하고 추가 호출하지 않는다.
