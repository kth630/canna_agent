# 이스케이프 축 해결, 실패 축이 잘림으로 이동 — 2026-08-31 (10회차)

상태: **provider 경계 통과 유지. 차단은 여전히 `malformed_submission_json`이지만 원인 축이
바뀌었다.** B는 `provisional / correction required` 유지.

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
  length: 571,
  starts_with_code_fence: false,
  first_char_is_open_brace: true,
  last_char_is_close_brace: false,
  decode_error: "Expecting ',' delimiter",
  decode_error_position_ratio: 1.0
}
external_call_count: 1   retry_count: 0
```

외부 호출 1회, retry 0, 다른 schema·model 호출 0. arguments 원문은 기록하지 않았다.

## 9회차 대비 축 이동

| 진단 | 9회차 | 10회차 | 해석 |
|---|---|---|---|
| `decode_error` | 깨진 유니코드 이스케이프 | `Expecting ',' delimiter` | **이스케이프 축 해결** |
| `decode_error_position_ratio` | 0.208 | **1.0** | 앞쪽 → **문자열 맨 끝** |
| `length` | 486 | 571 | 더 많은 내용이 통과 |
| `last_char_is_close_brace` | false | false | 문서가 닫히지 않음 |
| `starts_with_code_fence` | false | false | fence 아님 (유지) |
| `first_char_is_open_brace` | true | true | 앞 설명문 없음 (유지) |

오류 위치 비율 1.0 + 닫는 중괄호 없음은 이 저장소의 진단 테스트가 **잘림**으로 정의한
형태다(fence는 비율이 작고, 따옴표 오류는 중간, 잘림은 끝).

길이가 486 → 571로 늘어난 것도 같은 방향이다. 이스케이프를 쓰지 않으면 같은 내용이 더 적은
토큰을 차지하므로, 토큰 예산이 고정돼 있다면 더 많은 문자가 통과한다.

## 확정하지 않은 것

잘림의 원인이 (a) 생성 토큰 예산 소진인지, (b) provider의 tool-call argument 길이 제한인지,
(c) 모델이 스스로 멈춘 것인지는 이 관측으로 가려지지 않는다. `max_completion_tokens: 8192`이
실제 요청 body에 실려 나간다는 것은 offline 회귀 테스트가 이미 확인했으므로, 요청이 예산을
적게 요구해서 생긴 문제는 아니다.

## 이번에 추가한 계측 (외부 호출 없음)

다음 1회에서 위 세 가지를 가르기 위해 응답 metadata 3개를 기록하도록 harness를 고쳤다.

- `finish_reason` — `length`면 예산 소진, `stop`이면 모델이 완결했다고 판단한 것,
  그 밖이면 별도 사유
- `output_tokens` — 실제 생성량
- `max_completion_tokens_sent` — 요청한 예산과의 대조

내용이 아니라 응답 metadata이며 payload 문자·span·reference는 담지 않는다. 앞서 승인받은
metadata 목록을 넘어서므로 여기 명시해 둔다. 계약·parser·validator·schema는 변경하지 않았다.

## Offline 검증

```text
전체 offline suite : 692 passed, 6 deselected
ruff src tests     : All checks passed!
git diff --check   : exit 0
```

## 다음 (승인 전 실행 금지)

같은 호출 1회. `finish_reason`이 결과를 가른다.

- `length` → 예산 소진이다. 대응은 모델이 만들어야 할 출력을 줄이는 것이며, 논리 계약을
  건드리지 않는 선택지가 있다: 빈 `unaccounted_spans` 생략, 짧은 `requirement_id` 사용,
  system message 축소. 그래도 부족하면 `max_completion_tokens` 이외의 생성 파라미터를
  사용자 결정으로 검토한다.
- `stop` → 모델이 문서를 끝냈다고 판단한 것이다. 대응은 지시 보완이며, 닫는 중괄호까지
  완결하라는 문장은 이미 들어가 있으므로 그 다음 단계는 출력 구조 자체를 더 단순하게
  만드는 쪽이다.
- 그 밖 → provider 사유로 분류하고 추측하지 않는다.

어느 경우에도 parser·validator 규칙은 완화하지 않는다.
