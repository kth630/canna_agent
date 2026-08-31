# HCX wire projection live 재검증 — 2026-08-31 (2회차)

상태: **provider rejected / B는 provisional·correction required 유지**

## 승인된 범위

- 질문, Runtime View 구성, system/human 메시지, tool 이름 `submit_semantic_query`,
  강제 `tool_choice`: 1회차(`HCX_RUNTIME_VIEW_LIVE_RESULT_20260831.md`)와 동일
- 유일한 변경: `function.parameters`가 `hcx_wire_schema()` 투영
- HCX 외부 호출 1회, retry 0회
- rule-only Retriever, embedding 호출 0회
- 다른 live 테스트 미실행, DB 실행·최종 답변 생성 없음

## 실행 명령

```powershell
$env:RUN_HCX_LIVE=1
uv run --cache-dir .tmp/uv-cache python -m pytest tests/runtime_view/test_hcx_runtime_view_live.py -m hcx_live -s -q --basetemp=.tmp/pytest-hcxwire-live
```

```text
FAILED tests/runtime_view/test_hcx_runtime_view_live.py::test_actual_runtime_view_schema_is_accepted_once
provider rejected the one approved call: kind=api, code=40009
1 failed in 12.90s
```

테스트 실패는 계약대로다. 이 테스트는 provider 수용을 단언하므로 거부되면 실패한다.

## 결과

| 항목 | 1회차 (neutral schema) | 2회차 (wire projection) |
|---|---|---|
| 전송 `function.parameters` byte | 3,937 | 3,275 |
| tool definition 전체 byte | 4,269 | 3,607 |
| provider schema acceptance | `rejected` | `rejected` |
| provider error kind / code | `api` / `40009` | `api` / `40009` |
| tool emitted | `no` | `no` |
| tool name exact | `no` — tool call 없음 | `no` — tool call 없음 |
| parser well_formed | `no` — arguments 없음 | `no` — arguments 없음 |
| ref validity | `not_evaluated` | `not_evaluated` |
| 실제 HCX 외부 호출 | 1 | 1 |
| retry | 0 | 0 |
| embedding 호출 | 0 | 0 |

Provider는 2회차에서도 tool을 emit하기 전에 요청을 거부했다. 따라서 parser는 실행되지
않았고 ref·span·semantic validation은 평가 대상이 아니다. 이 기록에는 raw 응답,
request/response ID, header, token, credential을 저장하지 않았다.

## 해석 — G절 기록 규칙에 따름

**현재 keyword projection만으로는 provider rejection이 해결되지 않았다.**

- 제거한 keyword(`$schema`, `$id`, `title`, `x-*`, `pattern`, `minLength`, `minItems`)가
  **원인이 아니었다고 단정하지 않는다.** 원인이 복수이거나 keyword 제거가 필요조건이었을
  가능성이 남아 있으며, 이 관측은 "이 변경만으로는 충분하지 않다"만 보여 준다.
- 남은 후보: 선언 크기(3,607 vs 0-A 성공 선언 2,271), property 개수, 구조 깊이,
  특정 property 이름, function name.
- 이 결과는 Retriever 품질, 의미 선택 정확도, DB 실행, 최종 답변 품질을 평가하지 않는다.
  `IMPLEMENTATION_PLAN.md`나 B production 상태를 완료로 바꾸지 않는다.

## 다음 1회 (사용자 승인 전 실행 금지)

G절에 이미 고정한 원인 분리 실험이 그대로 다음 후보다. 질문, Runtime View, 메시지,
`function.parameters`(투영 schema), retry 0, embedding 0을 전부 고정하고 **function name과
강제 `tool_choice`의 이름만** 0-A에서 실제 수용된 `record_question_semantics`로 바꾼다.
이번 세션에서는 실행하지 않았다.
