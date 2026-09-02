# HCX-007 provider compatibility bridge live 검증 — 2026-08-31 (7회차)

상태: **provider 수용됨. `40009` 해소. 단, 성공 판정 6개 조건은 전부 충족되지 않았다.**
B는 `provisional / correction required` 유지.

## 결과

```text
HCX_RUNTIME_VIEW_RESULT={"provider_schema_acceptance": "accepted", "tool_emitted": "yes",
 "tool_name_exact": "yes", "parser_well_formed": "no", "ref_validity": "not_evaluated",
 "source_span": "failed", "direction_span": "missing", "limit_span": "missing",
 "semantic_validation": "not_run", "execution_readiness": "not_evaluated/non-executable",
 "external_call_count": 1, "retry_count": 0}
```

| 성공 조건 | 결과 |
|---|---|
| provider 수용 | **충족** — `accepted`. `40009` 없음 |
| Tool emit | **충족** — `yes` |
| 이름 `submit_semantic_query` 일치 | **충족** — `yes` |
| `submission_json` JSON parsing | **미충족** |
| grouped-flat parsing | **미충족** |
| opaque ref 유효 | 평가 불가 |
| semantic validation | 미실행 |

외부 호출 1회, retry 0, 다른 schema·model 호출 0.

## 최초 차단 단계

**envelope/제출 파싱 단계**다. provider 경계는 통과했고 tool call이 정확한 이름으로 1회
emit됐으나, `parse_tool_arguments`가 반환한 제출이 well-formed가 아니었다.

이번 실행 harness는 `parser_well_formed` 여부만 기록하고 **어떤 구조 문제 code였는지는
남기지 않았다.** 따라서 malformed JSON, envelope property 불일치, grouped-flat property
오류, orphan/duplicate record, ref 형식 중 어느 것이었는지 이 관측만으로는 특정할 수 없다.
추가 호출 없이 원인을 확정하지 않는다.

그 다음 호출부터는 특정할 수 있도록 harness에 `parser_problem_codes`와 `argument_keys`
기록만 추가했다(외부 호출 없음, 계약·parser·validator 무변경).

## 무엇이 바뀌어서 수용됐는가

| | 이전 (거부) | 이번 (수용) |
|---|---|---|
| tool `parameters` | grouped-flat JSON Schema, 2,030 byte | `{"type":"object","properties":{"submission_json":{"type":"string",...}},"required":["submission_json"]}` |
| tool definition byte | 2,264 | **332** |
| grouped-flat 구조 위치 | JSON Schema | `submission_json` 문자열 안 + system message |
| tool 이름 | `submit_semantic_query` | 동일 |
| model·파라미터·endpoint·message·Runtime View | — | 동일 유지 |

이로써 4회 연속 `40009`를 낸 축은 **선언이 grouped-flat 구조를 JSON Schema로 실어 보낸다는
점**임이 관측과 일치한다. 단일 관측이므로 확정은 아니다.

## 서버 계약이 유지된다는 근거

`src/canna/runtime_view/hcx_bridge.py`는 envelope에 대한 검사 4개만 추가한다: arguments가
object인가, `submission_json` 하나만 있는가, 문자열이 JSON인가, 그 JSON이 object인가.
그 아래는 전부 기존 `parse_grouped_flat` → `parse_submission` → `validate`가 결정한다.

`tests/runtime_view/test_hcx_bridge.py` 32개가 이를 강제한다. 특히 거부 케이스마다
**bridge를 통과시킨 결과와 기존 parser를 직접 호출한 결과의 problem code 집합과 query가
같은지** 대조하므로, bridge가 규칙을 완화하거나 중복 구현하면 테스트가 깨진다.

검증한 거부: malformed JSON 3종, JSON array/null/scalar/true 5종, 비문자열 envelope,
extra tool argument, envelope property 누락, arguments 비-object 4종, unknown grouped-flat
property(최상위·record), wrong-kind ref 4종, malformed ref 3종, 빈 span 2종,
orphan/duplicate/conflicting record, unknown kind/status, 요구 0개, SQL/table/join 밀반입 3종.
보존 확인: canonical round-trip, 조건 2개의 비교/값 짝, ordering·aggregation·limit·
grouping·relationship, `mapped/unresolved/ambiguous` 3종.

## 변경하지 않은 것

`SUBMISSION_SCHEMA`, grouped-flat canonical 계약, `parse_grouped_flat`, `parse_submission`,
`validate`, Runtime View, Semantic/Execution Registry, Ontology, DB. 바뀐 것은 HCX wire
envelope과 system message뿐이다.

## 다음 (승인 전 실행 금지)

같은 호출 1회 재실행. 이번에는 harness가 `parser_problem_codes`를 남기므로 최초 차단
단계가 code 수준으로 특정된다. 그 code에 따라 system message의 지시를 조정하거나
(예: JSON 문자열만 반환하고 code fence를 쓰지 말 것), envelope 처리의 허용 범위를
사용자·Codex 결정으로 검토한다. parser·validator 규칙 완화는 어느 경우에도 하지 않는다.
