# HCX one-line records live result — 2026-09-01

## 결론

`provider accepted / tool emitted / one-line text grammar rejected`

HCX-007은 `submit_semantic_query`를 수용하고 정확한 이름으로 호출했다. 그러나 one-line
문서 안의 field assignment 표기를 호출 사이에 일관되게 지키지 않아 parser를 통과하지
못했다. 추가 live 호출은 중단한다. Runtime View, semantic validator, canonicalizer,
Execution Registry와 DB의 문제가 아니다.

## 관측 1 — `key=value` 계약

- provider acceptance: `accepted`
- tool emitted / exact name: `yes / yes`
- external call / retry / embedding / DB: `1 / 0 / 0 / 0`
- finish reason / output tokens: `tool_calls / 171`
- record line counts: `REQ 1 / REF 2 / DETAIL 1 / UNACCOUNTED 0`
- pipe present: `true`
- key-value segments / malformed segments: `0 / 11`
- unknown record line count: `1`
- parser codes: `empty_submission`, `malformed_key_line`, `unknown_record`
- ref validity / semantic validation: 미도달

HCX는 record-per-line과 pipe는 따랐지만 `=` assignment를 사용하지 않았다.

## 관측 2 — `key value` 계약

관측 1 뒤 field assignment만 ASCII space로 바꾸고 offline 핵심 테스트 59건을 통과시킨 뒤
같은 승인 질문으로 1회 관측했다.

- provider acceptance: `accepted`
- tool emitted / exact name: `yes / yes`
- external call / retry / embedding / DB: `1 / 0 / 0 / 0`
- finish reason / output tokens: `tool_calls / 110`
- record line counts: `REQ 1 / REF 1 / DETAIL 1 / UNACCOUNTED 0`
- pipe present: `true`
- key-value segments / malformed segments: `1 / 7`
- unknown key / unknown record: `true / true`
- unknown record line count: `1`
- parser codes: `empty_submission`, `malformed_key_line`, `unknown_property`,
  `unknown_record`
- ref validity / semantic validation: 미도달

space assignment도 일관되게 사용되지 않았다. 단일 구분자를 맞추면 해결된다는 가설은
지지되지 않는다. 출력은 잘리지 않았고 JSON, bullet, literal backslash-newline 축도 아니다.

## 안전·변경 상태

제출 원문, ref, span, semantic ID, requirement ID, unknown token과 그 hash, credential,
request/response ID는 기록하지 않았다. 위 값은 승인된 고정 진단 필드뿐이다.

실험적 `key value` 변경은 관측 후 이전 offline 승인 상태인 `key=value`로 되돌렸다.
추가 live 호출, retry, embedding 호출, DB 실행, commit, push는 하지 않았다.

## 판정

provider와 Tool envelope 경계는 확보됐다. HCX가 자유 문자열 안에서 custom record grammar를
안정적으로 생성하는 경로는 확보되지 않았다. 추가 구분자·prompt 미세조정은 중단하고,
다음 결정은 HCX 역할을 더 단순한 선택으로 축소하거나 provider가 직접 강제하는 구조화
경계를 사용하는 것이다. 서버의 기존 fail-closed 계약은 유지한다.
