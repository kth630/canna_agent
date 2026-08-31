# HCX grouped-flat wire live 검증 — 2026-08-31 (4회차)

상태: **provider rejected / B는 provisional·correction required 유지**

## 승인된 범위

- 질문, Runtime View 구성, system/human 메시지 구조, model, timeout, 강제 `tool_choice`,
  tool 이름 `submit_semantic_query`: 이전 회차와 동일
- 변경: `function.parameters`가 grouped-flat wire schema
- HCX 외부 호출 1회, retry 0, embedding 0
- `tests/runtime_view/test_hcx_runtime_view_live.py` 파일 하나만 지정 실행
- DB 실행·최종 답변 생성 없음, 실패 후 추가 호출 없음

## 실행 명령

```powershell
$env:RUN_HCX_LIVE=1
uv run --cache-dir .tmp/uv-cache python -m pytest tests/runtime_view/test_hcx_runtime_view_live.py -m hcx_live -s -q --basetemp=.tmp/pytest-gf-live
```

```text
HCX_RUNTIME_VIEW_RESULT={"provider_schema_acceptance": "rejected", "tool_emitted": "no",
 "tool_name_exact": "no", "parser_well_formed": "no", "ref_validity": "not_evaluated",
 "source_span": "failed", "direction_span": "missing", "limit_span": "missing",
 "semantic_validation": "not_run", "execution_readiness": "not_evaluated/non-executable",
 "external_call_count": 1, "retry_count": 0,
 "provider_error_kind": "api", "provider_error_code": "40009"}
```

Provider는 HTTP 400, code `40009`, message category `Unsupported function`으로 tool 생성
전에 거부했다. 테스트 실패는 계약대로다(수용을 단언하는 테스트).

## 확인 항목별 결과

| 확인 항목 | 결과 |
|---|---|
| provider가 Tool 선언을 수용했는가 | **아니오** — `rejected`, `api` / `40009` |
| 정확한 Tool 이름으로 1회 emit했는가 | **아니오** — tool call 0회 |
| grouped-flat arguments가 canonical submission으로 조립되는가 | **평가 불가** — arguments 없음 |
| requirement_id 연결·ref 종류·source/order/limit span 유효성 | **평가 불가** — arguments 없음 |
| semantic validation 결과와 차단 reason code | **미실행** (`not_run`) |
| stable semantic ID·SQL·table·column·JOIN 유출 | **모델 응답 없음.** 전송한 선언과 Runtime View payload에 유출 없음은 offline 테스트가 계속 강제한다 |

외부 호출 1회, retry 0, embedding 0, DB 실행 0, 다른 live 테스트 미선택. 이 기록에는 raw
응답, request/response ID, header, token, credential을 저장하지 않았다.

## 4회 관측 누적

| # | 전송한 선언 | tool definition byte | 결과 |
|---|---|---:|---|
| 1 | neutral `SUBMISSION_SCHEMA` | 4,269 | `rejected` `40009` |
| 2 | keyword projection (nested) | 3,607 | `rejected` `40009` |
| 3 | 2회차 + 0-A 성공 function name | 3,611 | `rejected` `40009` |
| 4 | **grouped-flat wire** | 4,386 | `rejected` `40009` |

네 번 모두 tool emit 이전 거부이므로 parser는 한 번도 실행되지 않았다.

## Offline 구조 비교 (외부 호출 없음)

거부된 선언과 0-A에서 실제 수용된 두 선언의 `parameters`를 같은 방법으로 측정했다.

| 지표 | 0-A nested (수용) | 0-A grouped_flat (수용) | canna grouped-flat (거부) |
|---|---:|---:|---:|
| parameters byte | 2,012 | 2,186 | **3,975** |
| property slot 수 | 13 | 16 | 17 |
| distinct property 이름 수 | 13 | 13 | 14 |
| 최대 object 깊이 | 3 | 2 | 2 |
| enum 수 | 4 | 4 | 4 |
| description 개수 | 5 | 3 | **19** |
| description byte 합 | 613 | 576 | **2,167** |

구조 지표(property 수, 깊이, enum 수)는 수용된 grouped_flat과 사실상 같다. 남은 큰 차이는
**description의 개수와 총 byte**이며, 그것이 전체 크기 차이의 대부분(3,975 − 2,186 = 1,789
중 description 1,591)을 만든다.

## 해석

**grouped-flat encoding으로 전환해도 provider rejection이 해결되지 않았다.**

- encoding shape이 원인이 아니었다고 단정하지 않는다. 0-A에서 `grouped_flat`의 provider
  failure가 0/93이었다는 사실과 이번 1회 거부는 모순되지 않는다. 두 선언은 encoding은
  같고 내용량이 다르다.
- 마찬가지로 앞선 회차에 대한 판단(keyword, function name)도 그대로 유보한다.
- 지금까지 개별로 움직인 세 요소(keyword vocabulary, function name, encoding shape) 중
  어느 것도 단독으로 충분하지 않았다. 네 관측에서 계속 함께 움직이지 않은 것은
  **선언 내용량**이다. 이는 가설이며 확정이 아니다.
- 이 결과는 Retriever 품질, 의미 선택 정확도, DB 실행, 최종 답변 품질을 평가하지 않는다.
  `IMPLEMENTATION_PLAN.md`나 B production 상태를 완료로 바꾸지 않는다.

## 다음 후보 (사용자 승인 전 실행 금지)

권고는 **compatibility minimization**이다(FINDINGS G절 정의). 단일 변수 원인 분리가 아니라
"이 provider가 수용하는 최소 선언이 존재하는가"를 묻는다. 논리 계약을 축소한다는 뜻이
아니며, 수용되더라도 어떤 개별 요소가 원인인지는 알 수 없다.

가장 싼 형태는 **description만 0-A 수준으로 줄인 grouped-flat 선언 1회**다. property 이름,
enum, 구조, 필수 여부, tool 이름을 모두 고정하고 description 총량만 약 2,167 → 600 byte
수준으로 낮춘다. 이는 논리 필드를 하나도 제거하지 않으므로 계약 축소가 아니다.

- 수용됨 → 선언 내용량 가설과 일치. description을 어디까지 유지할지는 별도 결정이며,
  줄인 description이 모델의 의미 선택 정확도에 미치는 영향은 이 관측이 답하지 않는다.
- 다시 `40009` → 내용량도 단독으로는 충분하지 않다. 그 시점에는 provider 문서·지원 채널
  확인, 또는 tool 사용 자체를 쓰지 않는 대안(구조화 출력 프롬프트)을 사용자·Codex 결정으로
  검토할 것을 권고한다. 서버 검증 계약은 어느 경우에도 그대로 둔다.

이번 세션에서는 실행하지 않았다. 이 작업의 외부 호출은 이 1회뿐이다.
