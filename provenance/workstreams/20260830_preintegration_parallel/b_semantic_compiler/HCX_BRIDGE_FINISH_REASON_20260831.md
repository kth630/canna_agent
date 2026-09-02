# 잘림의 원인 판별 — 예산 소진이 아니다 — 2026-08-31 (11회차)

상태: **provider 경계 통과 유지. 차단 원인이 "모델이 미완결 문서를 만들고 정상 종료"로
좁혀졌다.** B는 `provisional / correction required` 유지.

## 결과

```text
provider_schema_acceptance: accepted
tool_emitted: yes            tool_name_exact: yes
finish_reason: "tool_calls"
output_tokens: 269           max_completion_tokens_sent: 8192
envelope: {
  raw_args_type: "dict", argument_keys: ["submission_json"],
  submission_json_value_type: "str", json_decoded: "no",
  parser_problem_codes: ["malformed_submission_json"],
  length: 545, starts_with_code_fence: false,
  first_char_is_open_brace: true, last_char_is_close_brace: false,
  decode_error: "Expecting ',' delimiter", decode_error_position_ratio: 1.0
}
external_call_count: 1   retry_count: 0
```

외부 호출 1회, retry 0, 다른 schema·model 호출 0. arguments 원문은 기록하지 않았다.

## 세 가설의 판별

| 가설 | 판정 | 근거 |
|---|---|---|
| (a) 생성 토큰 예산 소진 | **배제** | `finish_reason="tool_calls"`이며 `length`가 아니다. 8,192 중 **269** 토큰만 사용했다 |
| (b) provider의 tool-call argument 길이 제한 | **지지 없음** | 예산의 3%에서 멈췄고 provider는 정상 종료를 보고했다. 545자에서 잘리는 제한을 시사하는 신호가 없다 |
| (c) 모델이 스스로 미완결 문서를 만들고 종료 | **남는 설명** | 정상 종료 + 닫히지 않은 문서 + 맨 끝(비율 1.0)에서의 구문 오류 |

즉 모델은 **공간이 부족해서가 아니라, 문서를 다 썼다고 판단하고** 열린 괄호를 남긴 채
호출을 끝냈다.

## 이번 관측이 좁힌 것

지금까지 축이 순서대로 해결됐다.

1. provider schema 거부(`40009`) → bridge envelope으로 해소
2. tool argument 오염 → `argument_keys`가 `submission_json` 단독
3. object vs string → `submission_json_value_type="str"`
4. code fence·앞 설명문 → `starts_with_code_fence=false`, 첫 글자 `{`
5. 깨진 유니코드 이스케이프 → `decode_error`가 이스케이프에서 구문 오류로 이동
6. **남은 것: 문서 완결성**

## 대응 — system message 지시만 (외부 호출 없음)

`submission_guidance()` 끝에 추가했다. 예산이 아니라 모델이 추적해야 할 양을 줄인다.

> Write it on one line, compact, with no line breaks and no indentation. Omit any property
> you have nothing to put in rather than sending it empty. Keep each requirement_id to one
> or two characters. Before you finish, make sure every brace and bracket you opened is
> closed.

근거: 줄바꿈과 들여쓰기는 문자열 안에서 추가 이스케이프를 만들고, 빈 배열과 긴 id는
중첩 구조를 늘린다. 질문·ref·상품군 예시는 넣지 않았다.

Tool schema, Runtime View, grouped-flat canonical 계약, `parse_grouped_flat`,
`parse_submission`, `validate`, Registry, Ontology, DB는 변경하지 않았다. parser·validator
규칙은 완화하지 않았다.

## Offline 검증

```text
전체 offline suite : 693 passed, 6 deselected
ruff src tests     : All checks passed!
git diff --check   : exit 0
```

## 다음 (승인 전 실행 금지)

같은 호출 1회.

- `json_decoded=yes` → grouped-flat parsing과 ref·scope·grain·span 검증으로 진행한다.
  거기까지 통과해 `canonicalizer_unavailable`만 남으면 provider/semantic mapping 경로
  확보로 판정한다. **그 경우에도 `semantic_valid`는 False이고 실행은 계속 차단된다.**
- 다시 `decode_error_position_ratio=1.0`이면 지시로 문서 완결성을 얻는 접근이 통하지 않는
  것이다. 그때의 선택지는 **문자열 안의 형식을 바꾸는 것**이다. 예: 따옴표 이스케이프가
  전혀 필요 없는 줄 단위 표기(0-A `delimited` 형태)를 문자열 안에 쓰고 서버가 같은 canonical
  제출로 조립한다. 이는 wire 표현만 바꾸며 canonical 계약·parser·validator는 그대로다.
  적용 여부는 사용자 결정 사항이다.
