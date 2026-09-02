# 줄 단위 record wire live 검증 — 2026-08-31 (13회차)

상태: **provider 수용됨. parser 단계에서 차단. B는 `provisional / correction required` 유지.**

외부 HCX 호출 1회, retry 0, embedding 호출 0, DB 실행 0. 코드·Registry·Ontology·계약 무변경.

## 실행

```text
$env:RUN_HCX_LIVE=1
uv run --cache-dir .tmp/uv-cache python -m pytest \
  "tests/runtime_view/test_hcx_runtime_view_live.py::test_actual_runtime_view_schema_is_accepted_once" \
  -m hcx_live -s -q --basetemp=.tmp/pytest-line-runtime-live
```

모델 `HCX-007`, `reasoning_effort="none"`, `max_completion_tokens=8192`, `max_retries=0`,
현재 endpoint/client 설정, 현재 schema·system message·승인 질문 fixture 그대로.

## 결과 (DIAGNOSTIC_FIELDS 허용 목록만)

```text
HCX_RUNTIME_VIEW_RESULT={"provider_schema_acceptance": "accepted", "tool_emitted": "yes",
 "tool_name_exact": "yes", "parser_well_formed": "no", "ref_validity": "not_evaluated",
 "source_span": "failed", "direction_span": "missing", "limit_span": "missing",
 "semantic_validation": "not_run", "execution_readiness": "not_evaluated/non-executable",
 "external_call_count": 1, "retry_count": 0, "finish_reason": "tool_calls",
 "output_tokens": 121, "max_completion_tokens_sent": 8192,
 "envelope": {"raw_args_type": "dict", "argument_keys": ["submission_text"],
  "submission_text_value_type": "str",
  "parser_problem_codes": ["empty_submission", "stray_line", "unknown_record"],
  "length": 225, "line_count": 6, "first_line_is_record_header": false,
  "last_line_is_end": true, "starts_with_code_fence": false,
  "record_counts": {"REQ": 0, "REF": 0, "DETAIL": 0, "UNACCOUNTED": 0},
  "finish_reason": "tool_calls", "output_tokens": 121}}
```

| 성공 조건 | 결과 |
|---|---|
| provider 수용 | **충족** — `accepted` |
| Tool emit | **충족** — `yes`, 1건 |
| 이름 `submit_semantic_query` 일치 | **충족** — `yes` |
| envelope property `submission_text` 존재·문자열 | **충족** |
| line parser well_formed | **미충족** |
| opaque ref 유효 | 평가 불가 |
| semantic validation | 미실행 |
| server decision | 없음 |

## 최초 차단 단계

**줄 단위 record parser 단계.** provider 경계와 tool 경계는 통과했고, envelope도
`submission_text` 하나를 문자열로 실어 왔다. 차단은 그 문자열을 record 문서로 읽는
`parse_line_submission`에서 발생했다.

problem code는 `unknown_record`, `stray_line`, `empty_submission` 세 개다.
`record_counts`가 `REQ`/`REF`/`DETAIL`/`UNACCOUNTED` 모두 0이고
`first_line_is_record_header`가 false이므로, **record header 줄이 한 번도 열리지 않았다.**
`last_line_is_end`는 true이므로 종결 토큰만 열린 record 없이 나타났고(`stray_line`),
결과적으로 수집된 record가 0이어서 `empty_submission`이 붙었다.

`finish_reason`은 `tool_calls`, `output_tokens`는 121로 예산 8192에 한참 못 미친다.
따라서 이번 차단은 **잘림이 아니다**(10~12회차의 truncation 축과 구별된다).
`starts_with_code_fence`도 false이므로 code fence 축도 아니다.

원인 확정은 하지 않는다. 단일 관측이며, 추가 live 호출 없이 진행한다.

## 기록하지 않은 것

제출 원문, span 문자열, opaque ref, credential, request/response ID. `DIAGNOSTIC_FIELDS`
허용 목록 밖의 필드는 harness의 assertion이 강제로 막는다.

---

# 형태 분류가 붙은 뒤의 재검증 — 2026-09-01 (14회차)

상태: **provider 수용됨. 같은 지점에서 차단. 다만 이번에는 어떤 형태였는지 특정된다.**
B는 `provisional / correction required` 유지.

결론: **line-record parser 실패 — 형태 분류 `record_header_with_suffix`.**

외부 HCX 호출 1회, retry 0, embedding 호출 0, DB 실행 0. 코드·schema·system message·
line parser·Registry·Ontology·계약 무변경. 13회차 대비 달라진 것은 진단 필드뿐이다.

## 결과 (DIAGNOSTIC_FIELDS 허용 목록만)

```text
HCX_RUNTIME_VIEW_RESULT={"provider_schema_acceptance": "accepted", "tool_emitted": "yes",
 "tool_name_exact": "yes", "parser_well_formed": "no", "ref_validity": "not_evaluated",
 "source_span": "failed", "direction_span": "missing", "limit_span": "missing",
 "semantic_validation": "not_run", "execution_readiness": "not_evaluated/non-executable",
 "external_call_count": 1, "retry_count": 0, "finish_reason": "tool_calls",
 "output_tokens": 111, "max_completion_tokens_sent": 8192,
 "envelope": {"raw_args_type": "dict", "argument_keys": ["submission_text"],
  "submission_text_value_type": "str",
  "parser_problem_codes": ["empty_submission", "stray_line", "unknown_record"],
  "length": 179, "line_count": 4, "first_line_is_record_header": false,
  "last_line_is_end": true, "starts_with_code_fence": false,
  "record_counts": {"REQ": 0, "REF": 0, "DETAIL": 0, "UNACCOUNTED": 0},
  "exact_record_header_count": 0, "casefold_record_header_count": 0,
  "indented_record_header_count": 0, "record_header_with_suffix_count": 3,
  "exact_end_count": 1, "indented_end_count": 0, "known_key_space_count": 0,
  "known_key_colon_count": 0, "bullet_prefixed_line_count": 0,
  "unknown_nonempty_line_count": 0, "literal_backslash_n_present": false,
  "json_punctuation_present": false, "first_line_class": "record_header_with_suffix",
  "last_line_class": "exact_end", "finish_reason": "tool_calls", "output_tokens": 111}}
```

| 항목 | 결과 |
|---|---|
| provider 수용 | **충족** — `accepted` |
| Tool emit / 이름 | **충족** — 1건, `submit_semantic_query` 일치 |
| envelope `submission_text` | **충족** — 존재, 문자열 |
| line parser well_formed | **미충족** |
| parser problem codes | `empty_submission`, `stray_line`, `unknown_record` |
| first / last line class | `record_header_with_suffix` / `exact_end` |
| finish_reason / output_tokens | `tool_calls` / 111 (예산 8192) |
| ref validity · semantic validation · server decision | 미도달 |

## 최초 차단 단계와 형태 분류

**line-record parser.** 13회차와 같은 세 code지만, 이번에는 형태가 특정된다.

- `record_header_with_suffix_count = 3`, `exact_record_header_count = 0` —
  record header 줄 3개가 **자기 줄에 혼자 있지 않았다.** 토큰 뒤에 무언가가 더 있었다.
- `known_key_space_count = 0`, `known_key_colon_count = 0` — **독립된 key 줄이 하나도
  없다.** 필드가 header 줄에 함께 실렸다는 뜻이다.
- `exact_end_count = 1`, `line_count = 4` — 4줄이 header류 3줄 + `END` 1줄이다.
  record마다 `END`가 붙은 것이 아니라 **문서 전체를 한 번 닫았다.**
- `indented_* = 0`, `casefold = 0`, `bullet = 0`, `literal_backslash_n_present = false`,
  `json_punctuation_present = false` — 들여쓰기·소문자·목록·한 줄 문서·JSON 회귀 축은
  **전부 배제된다.** 9~12회차의 축이 아니다.
- `finish_reason = tool_calls`, `output_tokens = 111` — 잘림도 아니다.

즉 모델은 **record 하나를 한 줄로 압축**했고, 그래서 reader가 header를 열지 못했으며
(`unknown_record`), 열린 record 없이 `END`를 만났고(`stray_line`), 수집된 record가 0이라
`empty_submission`이 붙었다. 13회차와 동일한 축일 가능성이 높지만, 13회차 관측에는 이
필드가 없었으므로 두 회차가 같은 형태였다고 단정하지는 않는다.

허용 목록 안에서 남는 미확정 하나: 토큰 뒤에 온 것이 필드였는지 구분자였는지는
`record_header_with_suffix` 하나로 합쳐지므로 이 관측만으로는 갈리지 않는다.

## 기록하지 않은 것

제출 원문, span, opaque ref, semantic ID, requirement ID, 인식하지 못한 token의 원문,
그리고 그것들의 hash. credential과 request/response ID도 기록하지 않는다.
harness의 `set(report["envelope"]) <= set(DIAGNOSTIC_FIELDS)` assertion이 이 경계를 강제한다.

## 상태

`format correction pending / no further live call approved`. 형식 수정안은 제안만 하고
적용하지 않았다. 다음 live 호출은 사용자 승인 대기.
