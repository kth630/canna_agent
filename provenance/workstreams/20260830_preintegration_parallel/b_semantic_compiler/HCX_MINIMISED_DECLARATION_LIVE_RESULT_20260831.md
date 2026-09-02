# 축소 grouped-flat 선언 live 검증 — 2026-08-31 (6회차)

상태: **40009 재현.** 추가 호출 없음. B는 `provisional / correction required` 유지.

## 결과

```text
HCX_RUNTIME_VIEW_RESULT={"provider_schema_acceptance": "rejected", "tool_emitted": "no",
 "tool_name_exact": "no", "parser_well_formed": "no", "ref_validity": "not_evaluated",
 "source_span": "failed", "direction_span": "missing", "limit_span": "missing",
 "semantic_validation": "not_run", "execution_readiness": "not_evaluated/non-executable",
 "external_call_count": 1, "retry_count": 0,
 "provider_error_kind": "api", "provider_error_code": "40009"}
```

| 항목 | 결과 |
|---|---|
| provider acceptance | `rejected` |
| tool emit | `no` |
| tool name | 확인 불가 — tool call 없음 |
| arguments parsing | `no` — arguments 없음 |
| ref validity | `not_evaluated` |
| semantic validation | `not_run` |
| error code | `40009` |

축소 선언(compatibility-minimized grouped-flat), 현재 system message, `HCX-007`,
`reasoning_effort="none"`, `max_completion_tokens=8192`, `max_retries=0`, 기존 endpoint/client,
기존 승인 질문 fixture를 그대로 사용했다. 외부 호출 1회, retry 0, 다른 schema·model 실험 0.

## 이 관측이 제거한 가설

축소 전후로 선언은 4,386 → 2,264 byte가 됐고 결과는 바뀌지 않았다. 더 중요한 것은 다음
비교다.

| 지표 | 수용 (최소, 08-31) | **거부 (프로젝트 축소, 08-31)** | 수용 (0-A grouped_flat, 08-30) |
|---|---:|---:|---:|
| tool byte | 244 | **2,264** | 2,445 |
| parameters byte | 117 | **2,030** | 2,186 |
| property slot / distinct | 1 / 1 | **17 / 14** | 16 / 13 |
| array 수 | 0 | **4** | 4 |
| enum 수 | 0 | **4** | 4 |
| `additionalProperties` 수 | 0 | **4** | 4 |
| 최대 깊이 | 1 | **2** | 2 |
| description 개수 / byte | 1 / 14 | **9 / 412** | 3 / 576 |

거부된 우리 선언은 0-A에서 93/93 수용된 선언보다 **더 작고**(2,264 < 2,445), 구조 지표
(array 4, enum 4, `additionalProperties` 4, 깊이 2, property 수)는 사실상 동일하다.

따라서 **선언 크기 가설과 구조 구성(중첩 배열·enum·닫힌 object) 가설은 이 관측으로
제거된다.** 두 축 모두에서 우리 선언은 이미 수용 사례 이하이거나 동등하다.

## 남은 축

1. **선언의 구체 내용** — function name, property 이름 14종, enum 값(요구 종류 8·상태 3·
   role 6·detail_kind 3), 남은 description 9개의 텍스트, 그 조합.
2. **서비스 측 변화** — 0-A(2026-08-30)에는 이 구조·크기의 선언이 수용됐고 2026-08-31에는
   같은 구조·더 작은 크기가 거부된다. 같은 날 최소 선언은 수용됐으므로 function calling
   자체가 꺼진 것은 아니며, 선언의 어떤 성질에 대한 처리 범위가 달라졌을 가능성이 남는다.

두 축은 현재 증거로 분리되지 않는다.

## 다음 minimization 후보 (offline 제안, 승인 전 실행 금지)

크기·구조 축이 제거됐으므로 다음 실험은 **내용 축과 서비스 축을 분리하는 것**이 우선이다.

### 후보 1 (권고, 1회) — 0-A 선언을 오늘 그대로 보낸다

0-A에서 93/93 수용된 `grouped_flat` 선언(`record_question_semantics`, 2,445 byte)을 현재
파라미터·client로 1회 보낸다. 크기·구조가 이미 우리 선언과 맞춰져 있으므로 이 호출은 남은
두 축을 가른다.

- 수용 → 서비스는 이 구조를 여전히 받는다. 차이는 **우리 선언의 구체 내용**이며, 후보 2로
  좁혀 간다.
- 거부 → 어제 수용된 선언이 오늘 거부된다는 뜻이므로 **서비스 측 변화**가 남는 설명이다.
  그 시점에는 declaration 조정으로 더 진행하지 않고 NCP 콘솔 설정·문서·지원 채널 확인을
  사용자·Codex 결정으로 반환한다.

단일 관측의 한계는 그대로다. 0-A에도 회차에 따라 결과가 갈린 기록이 있다.

### 후보 2 (후보 1이 수용된 경우) — 내용 축 이분 탐색

수용된 0-A 선언에서 출발해 우리 선언 쪽으로 한 번에 한 축만 옮긴다. 각 단계 1회.

1. function name만 `submit_semantic_query`로
2. property 이름만 우리 것으로(구조·enum 값은 0-A 유지)
3. enum 값만 우리 것으로
4. description만 우리 것으로

먼저 거부가 나오는 단계가 원인 축이다. 반복 횟수는 사용자 승인 사항이며 이 문서가
자동으로 승인하지 않는다.

### 하지 않은 것

`HCX-005` 전환, Structured Output fallback, 추가 live 호출, 선언·parser·validator·
Runtime View·Registry·Ontology·DB 수정.
