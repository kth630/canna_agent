# HCX function name probe live — 2026-08-31 (3회차)

상태: **provider rejected / B는 provisional·correction required 유지**

## 승인된 범위

- 질문, Runtime View 구성, system/human 메시지, `function.parameters`(wire projection),
  model, timeout, retry 0, embedding 0: **2회차와 동일**하게 고정
- 유일한 변경: `function.name`과 강제 `tool_choice`의 이름을 0-A에서 실제 수용된
  `record_question_semantics`로 교체
- HCX 외부 호출 1회, 다른 live 테스트 미실행, DB 실행·최종 답변 생성 없음

## 격리 방식

이름 변경은 `tests/runtime_view/test_hcx_name_probe_live.py` 안에서만 일어난다.

- 서버 계약의 `FUNCTION_NAME`은 `submit_semantic_query` 그대로다.
- probe 이름은 문자열을 다시 적지 않고
  `canna.experiments.semantic_probe.encodings.FUNCTION_NAME`에서 import한다. 새로 만든
  값이 아니라 0-A에서 수용된 값임을 코드가 보인다.
- 같은 파일의 offline 가드가 "probe 선언에서 이름만 되돌리면 기준 선언과 완전히 같다"를
  단언한다(`1 passed`). 즉 이름 외 다른 변수는 움직이지 않았다.

메시지는 여전히 `submit_semantic_query`를 언급한다. 메시지를 바꾸면 두 번째 변수가
움직이기 때문이다. 이는 요청이 수용됐을 때 **모델 행동**을 읽는 데 대한 한계이지 수용
여부를 읽는 데 대한 한계가 아니다. 조사 대상인 거부는 tool emit 이전에 발생한다.

## 실행 명령

```powershell
$env:RUN_HCX_LIVE=1
uv run --cache-dir .tmp/uv-cache python -m pytest "tests/runtime_view/test_hcx_name_probe_live.py::test_the_stage_0a_function_name_is_accepted_once" -m hcx_live -s -q --basetemp=.tmp/pytest-nameprobe-live
```

```text
HCX_NAME_PROBE_RESULT={"function_name_sent": "record_question_semantics",
 "contract_function_name": "submit_semantic_query", "tool_definition_bytes": 3611,
 "provider_schema_acceptance": "rejected", "tool_emitted": "no", "tool_name_exact": "no",
 "parser_well_formed": "no", "external_call_count": 1, "retry_count": 0,
 "embedding_call_count": 0, "provider_error_kind": "api", "provider_error_code": "40009"}

Failed: provider rejected the one approved call: kind=api, code=40009
1 failed in 14.69s
```

테스트 실패는 계약대로다. 이 테스트는 provider 수용을 단언하므로 거부되면 실패한다.

## 3회 관측 비교

| 항목 | 1회차 neutral | 2회차 wire projection | 3회차 name probe |
|---|---|---|---|
| function name | `submit_semantic_query` | `submit_semantic_query` | `record_question_semantics` |
| `parameters` keyword | 전체 | 축소 투영 | 축소 투영 |
| tool definition byte | 4,269 | 3,607 | 3,611 |
| provider schema acceptance | `rejected` | `rejected` | `rejected` |
| error kind / code | `api` / `40009` | `api` / `40009` | `api` / `40009` |
| tool emitted | `no` | `no` | `no` |
| tool name exact | `no` | `no` | `no` |
| parser well_formed | `no` — arguments 없음 | `no` — arguments 없음 | `no` — arguments 없음 |
| 외부 호출 / retry / embedding | 1 / 0 / 0 | 1 / 0 / 0 | 1 / 0 / 0 |

3회 모두 tool emit 이전에 거부됐으므로 parser는 한 번도 실행되지 않았다. 세 기록 어디에도
raw 응답, request/response ID, header, token, credential을 저장하지 않았다.

## 해석

**keyword projection에 더해 0-A 성공 function name까지 적용해도 provider rejection이
해결되지 않았다.**

- function name이 원인이 아니었다고 단정하지 않는다. 원인이 복수이거나 이름이
  필요조건이었을 가능성이 남으며, 이 관측은 "이 변경까지 더해도 충분하지 않다"만 보여 준다.
- 마찬가지로 앞서 제거한 keyword가 원인이 아니었다는 결론도 여전히 내리지 않는다.
- 지금까지 개별로 움직여 본 두 변수(keyword vocabulary, function name)는 각각 단독으로
  충분하지 않았다. 남은 차이는 선언의 **내용**이다: 선언 크기(3,611 vs 0-A 성공 선언
  2,271), property 개수, 구조 깊이, 특정 property 이름.
- 이 결과는 Retriever 품질, 의미 선택 정확도, DB 실행, 최종 답변 품질을 평가하지 않는다.
  `IMPLEMENTATION_PLAN.md`나 B production 상태를 완료로 바꾸지 않는다.

## 다음 후보 (사용자 승인 전 실행 금지)

남은 후보는 모두 선언 내용이며, 크기·property 개수·구조를 분리해 움직이기 어렵다.
따라서 다음 단계는 단일 변수 원인 분리가 아니라 **compatibility minimization**으로 표시할
것을 권고한다(FINDINGS G절 정의). 묻는 질문은 "무엇이 원인인가"가 아니라 "이 provider가
수용하는 최소 선언이 존재하는가"이며, 수용되더라도 어떤 개별 요소가 원인인지는 알 수
없고 논리 계약을 그 최소 선언으로 축소한다는 뜻도 아니다.

이번 세션에서는 실행하지 않았다. 이번 작업의 외부 호출은 이 1회뿐이다.
