# HCX-007 최소 function 선언 control — 2026-08-31 (5회차)

상태: **수용됨. HCX-007 Function Calling은 이 model·key·client에서 동작한다.**

## 결과

```text
HCX_MINIMAL_TOOL_RESULT={"model": "HCX-007", "tool_definition_bytes": 244,
 "provider_schema_acceptance": "accepted", "tool_emitted": "yes",
 "tool_name_exact": "yes", "arguments_parsed": "yes", "tool_call_count": 1,
 "argument_keys": ["city"], "external_call_count": 1, "retry_count": 0,
 "embedding_call_count": 0}
```

외부 호출 1회, retry 0, embedding 0, DB 실행 0, 추가 호출 없음.

## 무엇을 고정하고 무엇을 바꿨는가

고정: model `HCX-007`, `reasoning_effort="none"`, `max_completion_tokens=8192`,
`max_retries=0`, timeout 40, 강제 `tool_choice`, 동일 client 구성.

바꾼 것: tool 선언을 프로젝트 내용이 전혀 없는 최소 선언(하나의 object, 하나의 string
property, 하나의 required, 244 byte)으로 교체했다. Runtime View와 grouped-flat schema는
넣지 않았다.

**보고해야 할 판단.** 지시 1은 "현재 live harness의 message 유지", 지시 2는 "Runtime View를
control에 넣지 않는다"였는데 live harness의 message는 Runtime View payload를 본문에 담고
있어 둘을 동시에 지킬 수 없다. control의 목적이 "프로젝트 내용 없는 선언이 수용되는가"이므로
생성 파라미터를 전부 고정하고 message만 최소 tool에 맞춘 최소 프롬프트로 바꿨다. message를
그대로 두었다면 최소 tool과 Runtime View 프롬프트가 섞여 control이 성립하지 않았다.

## 이 관측이 말하는 것과 말하지 않는 것

- 말하는 것: 2026-08-31 현재, 이 model·key·client·endpoint 조합에서 function calling이
  최소 선언에 대해 **한 번 정상 동작했다**. tool이 emit됐고 이름이 정확했으며 arguments가
  파싱됐다.
- 말하지 않는 것: 앞선 4회 거부의 원인. 최소 선언과 프로젝트 선언은 이름·property·enum·
  required·description·크기·조합이 모두 다르므로 어느 축이 거부를 만들었는지 이 1회로는
  분리되지 않는다. 0-A에도 같은 선언이 회차에 따라 다른 결과를 낸 기록이 있으므로 단일
  수용이 안정성을 뜻하지도 않는다.

## 이 결과에 따라 실행한 것 — compatibility minimization

지시 3의 성공 분기에 따라 프로젝트 wire 선언을 축소했다. **논리 계약은 그대로다.**

| | 축소 전 | 축소 후 | (참고) 0-A 수용 | (참고) 최소 control |
|---|---:|---:|---:|---:|
| `parameters` byte | 3,975 | **2,030** | 2,186 | ~180 |
| tool definition byte | 4,386 | **2,264** | 2,445 | 244 |
| description 개수 / byte | 19 / 2,167 | **9 / 412** | 3 / 576 | 2 / 약 60 |

바꾸지 않은 것: property 이름과 개수, enum 값, `required` 배열, 중첩 구조,
`additionalProperties: false`, tool 이름 `submit_semantic_query`, `SUBMISSION_SCHEMA`,
`parse_grouped_flat`, parser, validator, Runtime View, Registry, Ontology, DB.

줄인 것: root의 중복 `description`(function envelope가 이미 싣고 있었다, 309 byte), 이름만으로
자명한 leaf의 description(`kind`, `status`, `limit_span`, `ref_records.requirement_id`,
`detail_records.requirement_id`, `detail_records.ref`, `unaccounted_spans.items`), 그리고
role·detail_kind의 긴 안내문.

**잘린 안내는 사라지지 않고 system message로 옮겼다.** role 6종의 의미, detail_kind 3종의
의미, "condition 하나가 record 하나", status 3종의 선택 기준, "span은 원문 그대로 복사하고
값·연산자·숫자로 정규화하지 않는다"가 모두 프롬프트에 들어 있다. 선언은 계약이고 프롬프트는
지시이므로 원래 자리이기도 하다.

## 다음 (승인 전 실행 금지)

축소된 선언으로 승인 질문 live 호출 1회. `tests/runtime_view/test_hcx_runtime_view_live.py`가
이미 그 선언과 프롬프트를 쓰므로 새 코드는 필요 없다. 이번 세션의 외부 호출 승인은 control
1회뿐이었으므로 실행하지 않았다.

수용되면 grouped-flat 경로가 확보된다. 다시 거부되면 축소 폭을 더 키우기 전에 선언을
최소 control에서부터 프로젝트 선언 방향으로 넓혀 가는 관측이 필요하며, 그 반복 횟수는
사용자 승인 사항이다.
