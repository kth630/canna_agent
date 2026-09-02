# 줄 단위 wire reader — offline 구현·검증 (2026-08-31)

상태: **`offline accepted / provider unverified`.** 사용자가 2026-08-31 offline 구현을
승인했다. 외부 호출 0회이며 아직 어디에도 연결하지 않았다. 실제 provider 수용 여부는
관측되지 않았다. B 전체는 `provisional / correction required` 유지.

연결은 **canonicalizer 작업 완료 후 통합 작업에서 한 번에** 수행한다. 그 작업이 지금
`runtime_view/__init__.py` 등을 수정 중이므로 `schema.py`, `__init__.py`, live harness는
이번에 건드리지 않았다.

`FINDINGS.md` Q절이 승인 전 구현 금지로 남긴 제안을 사용자 지시에 따라 구현한 결과다.
Q절의 한 줄 `|` 구분 예시 대신 사용자가 지정한 **block/line record 형식**을 사용한다.

## 1. 왜 형식만 바꾸는가

9~12회차에서 provider 경계·argument 오염·object/string·fence·문서 완결성은 모두 해소됐고
남은 축은 JSON 문법 정확성 하나였다. 두 지시(이스케이프 금지 / 완결·compact)가 모두
프롬프트에 있는 상태에서 11회차는 이스케이프를 지키고 문서를 닫지 않았으며 12회차는
문서를 닫고 다시 이스케이프를 썼다. 토큰은 두 번 다 예산의 3% 이하였다.

줄 단위 record에는 따옴표가 없어 이스케이프가 깨질 수 없고, 중첩이 없어 균형을 맞출
괄호가 없다. 두 결함이 지시가 아니라 **형식에서** 사라진다.

## 2. 무엇이 바뀌고 무엇이 그대로인가

| 그대로 | 바뀜 |
|---|---|
| Tool 이름 `submit_semantic_query` | 문자열 **안의** 표기가 JSON → 줄 단위 record |
| required string 하나짜리 얇은 envelope | envelope property 이름 제안: `submission_json` → `submission_text` |
| grouped-flat canonical 계약과 record/key 어휘 | 그 어휘를 줄로 읽고 쓰는 새 모듈 1개 |
| `parse_grouped_flat` → `parse_submission` → `validate` | 작성 지침(system message) 텍스트 |
| `SUBMISSION_SCHEMA`, parser, validator, Runtime View, Registry, Ontology, DB | — |

새 파일 2개만 추가했다. 기존 JSON bridge(`hcx_bridge.py`)는 삭제·수정하지 않았고
`schema.py`, `__init__.py`, live harness, `FINDINGS.md`도 수정하지 않았다.

- `src/canna/runtime_view/line_records.py`
- `tests/runtime_view/test_line_records.py`

record 이름과 각 record가 받는 key는 `grouped_flat`의 property 상수에서 가져오며,
두 번째 정의를 만들지 않는다. 테스트가 `line_record_keys()`와 `grouped_flat`의
property 집합이 record별로 **동일**함을 강제한다. enum, ref 종류, 필수 span,
requirement status는 전부 기존 상수와 기존 parser가 최종 판정한다.

## 3. wire 구조

```text
REQ
requirement_id r1
kind ranking
status mapped
source_span 1년 수익률이 높은 10개
limit_span 10개
END
REF
requirement_id r1
role target_dataset
ref ds_00000000000000000000000000000000
END
DETAIL
requirement_id r1
detail_kind ordering
ref fd_11111111111111111111111111111111
span 높은
END
UNACCOUNTED
span 설명해줘
END
```

- record 이름 4개(`REQ`, `REF`, `DETAIL`, `UNACCOUNTED`)와 종료선 `END`.
- key line은 `key` + 공백 하나 + **그 줄의 나머지 전체**가 값이다. trim도 공백 정규화도
  하지 않는다. 값이 `END`거나 `REQ END`여도 key가 줄 앞에 있으므로 충돌하지 않는다.
- record 사이 순서, record 안의 key 순서는 자유이며 REF/DETAIL이 자기 REQ보다 먼저 와도
  된다. 조립은 기존 assembler가 requirement → ref → detail 순으로 한다.
- `condition` 하나가 record 하나다. 비교와 값(`span`/`value_span`)은 같은 record에 있으므로
  요구에 조건이 둘이어도 짝이 어긋날 수 없다(`ARCHITECTURE.md` 4절 parallel array 금지).
- 물리 실행 정보를 담을 key가 없다. `table`, `column`, `sql`, `join`, `select`,
  `product_id` 같은 이름은 어느 record에도 없으며 쓰면 거부된다.

## 4. 거부 코드

reader가 소유하는 코드는 이 표기만 가질 수 있는 구조 문제 6개다. 나머지는 **기존 코드
그대로** 나온다.

| 상황 | 결과 코드 | payload |
|---|---|---|
| record 밖의 잡문 / 정의되지 않은 record 이름 | `unknown_record` | 계속 읽되 거부 |
| 열린 record 없는 `END` | `stray_line` | 계속 읽되 거부 |
| `END` 누락, 열린 record 안에서 새 header | `unterminated_record` | **None** |
| record가 정의하지 않은 key | `unknown_property`(기존) | 해당 record 폐기 |
| 한 record 안에서 key 반복 | `duplicate_record_key` | 해당 record 폐기 |
| 공백으로 시작해 key가 없는 줄 | `malformed_key_line` | 해당 record 폐기 |
| 줄 안의 CR·VT·FF·U+0085·U+2028·U+2029 | `unsupported_line_break` | **None** |
| 문자열이 아닌 제출 | `malformed_submission`(기존) | **None** |
| `UNACCOUNTED`에 `span`이 없거나 비어 있음 | `missing_required_span`(기존) | 그 span만 폐기 |

`unaccounted_spans`만 grouped-flat에서 bare string이라 대응하는 record 객체가 없다.
그래서 빈 span 검사 하나만 reader가 직접 한다. 나머지 빈 필수 span은 전부 기존 parser가
`missing_required_span`으로 거부한다.

실제 출력(외부 호출 0회):

```text
prose outside a record           -> ['unknown_record']                 well_formed=False
undefined record name            -> ['stray_line', 'unknown_record']   well_formed=False
END closing nothing              -> ['stray_line']                     well_formed=False
missing END                      -> ['unterminated_record']            well_formed=False
header inside an open record     -> ['unterminated_record']            well_formed=False
unknown key                      -> ['empty_submission', 'orphan_record', 'unknown_property']
repeated key                     -> ['duplicate_record_key', 'empty_submission', 'orphan_record']
line with no key                 -> ['empty_submission', 'malformed_key_line', 'orphan_record']
stray CR inside a value          -> ['unsupported_line_break']         well_formed=False
stray U+2028 inside a value      -> ['unsupported_line_break']         well_formed=False
UNACCOUNTED with no span         -> ['missing_required_span']          well_formed=False
not text                         -> ['malformed_submission']           well_formed=False
```

`CRLF`는 줄 끝으로 읽는다. 값의 내용이 아니라 줄 종결자이므로 span은 변형되지 않으며,
단독 `CR`은 위 표대로 거부된다. 구조선(record header, `END`)의 뒤쪽 공백도 값이 아니므로
읽고 넘어간다. 완전히 빈 줄은 어디서든 무시한다.

## 5. 기존 parser와의 동등성

같은 grouped-flat 객체를 JSON 경로와 줄 경로에 각각 넣고 **problem code 집합과 결과
`SubmittedQuery`가 같은지** 14개 malformed 사례에 대해 대조한다.

wrong reference kind, malformed reference, empty required span, unknown requirement kind,
unknown requirement status, orphan reference, reference with no owner, duplicate
requirement, duplicate reference, conflicting ordering, unknown role, unknown detail kind,
value span outside a condition, no requirement at all.

round-trip은 dict 동일성으로 확인한다. `to_grouped_flat(canonical)` → `render_line_records`
→ `read_line_records`가 **원본 grouped-flat 객체와 완전히 같다**. 단 빈
`unaccounted_spans: []`는 record가 0개이므로 키 부재로 돌아오며, parse 결과
(`unaccounted_spans=()`)는 동일하다.

## 6. 측정값

| 대상 | byte (UTF-8) |
|---:|---:|
| 같은 제출을 줄 표기로 | 335 |
| 같은 제출을 JSON으로 | 453 |
| 같은 제출을 **JSON-in-string**으로(모델이 실제로 써야 했던 것) | 558 |
| 작성 지침 — 줄 표기 | 2,551 |
| 작성 지침 — JSON bridge(현행) | 2,955 |
| tool `parameters` — 줄 표기 | 156 |
| tool `parameters` — JSON bridge(현행) | 181 |

선언은 여전히 required string 하나이며 provider가 수용한 모양 그대로다. 크기 감소가
수용을 보장한다는 주장은 하지 않는다. `40009` 축은 7회차에 이미 해소됐다.

## 6-A. 형태 전용 live 진단 (2026-08-31 승인, 구현 완료, 미연결)

사용자가 승인한 항목만 기록하며 그 목록을 `DIAGNOSTIC_FIELDS` 상수로 공개한다.
테스트가 생성된 기록이 이 목록을 벗어나지 않음을 강제한다.

`raw_args_type`, `argument_keys`, `submission_text_value_type`, `length`, `line_count`,
`first_line_is_record_header`, `last_line_is_end`, `starts_with_code_fence`,
`record_counts`(record 이름별 개수), `parser_problem_codes`, `finish_reason`,
`output_tokens`.

- payload 원문, span, opaque ref, credential, request/response ID는 기록하지 않는다.
  테스트가 실제 제출의 ref 4종과 span 4종이 직렬화된 진단에 **없음**을 확인한다.
- `finish_reason`과 `output_tokens`는 응답 metadata이므로 호출자가 넘길 때만 실린다.
  진단 함수가 응답을 직접 읽지 않는다.
- `record_counts`는 이 모듈이 정의한 record 이름의 등장 횟수이므로 내용을 말하지 않는다.
- fence·잘림 판별은 내용 없이 형태만으로 갈린다: fence면
  `first_line_is_record_header=false`, 잘림이면 `last_line_is_end=false` +
  `parser_problem_codes=['unterminated_record']`.

함수는 `line_records.line_envelope_diagnostics()`이며 아직 harness에 연결하지 않았다.

## 7. 검증 명령과 실제 출력

```powershell
uv run --cache-dir .tmp/uv-cache python -m pytest tests/runtime_view/test_line_records.py -q
```

```text
70 passed in 0.61s
```

```powershell
uv run --cache-dir .tmp/uv-cache python -m pytest -q
```

```text
978 passed, 6 deselected in 88.90s (0:01:28)
```

```powershell
uv run --cache-dir .tmp/uv-cache python -m pytest -q -m "hcx_live or embedding_live" -rs
```

```text
6 skipped, 979 deselected in 4.52s
```

(전체 개수는 병렬 canonicalizer workstream이 같은 기간에 테스트를 추가해 변동한다.
이 파일이 추가한 것은 70개다.)

```powershell
uv run --cache-dir .tmp/uv-cache ruff check src/canna/runtime_view/line_records.py tests/runtime_view/test_line_records.py
```

```text
All checks passed!
```

`git diff --check` 출력 없이 exit 0. **외부 API 호출 0회, 다른 모델 실험 0회, retry 0.**
commit·push·branch·worktree 생성 없음.

전체 `ruff check src tests`에는 이번 작업과 무관한 다른 workstream의 신규 파일
`tests/runtime_view/test_canonicalize.py`에 5건이 남아 있다. 그 파일은 건드리지 않았다.

## 8. 통합 작업에 넘기는 연결 diff — 2026-08-31 사용자 승인 절차

**대기 조건**: canonicalizer workstream과 Execution workstream의 정정이 끝날 때까지
Runtime 연결과 HCX live 호출을 하지 않는다. 그때까지 이 파일의 모듈은 어떤 실행 경로에도
연결되지 않은 상태로 유지한다.

**적용 방식**: 아래 5개를 나눠서가 아니라 **한 번의 변경으로** 처리한다. 두 bridge가 같은
이름을 수출하므로 1~4를 쪼개면 중간 상태에서 이름이 충돌하거나 wire와 지침이 어긋난다.

**적용 후 순서**: 전체 offline 검증을 먼저 수행한다. HCX live 호출은 **별도 명시 승인**
전까지 실행하지 않는다. 상태는 그때까지 `offline accepted / provider unverified`를
유지한다.

이번 회차에는 아래 중 하나도 적용하지 않았다.

1. `schema.hcx_wire_schema()`가 `hcx_bridge.bridge_parameters_schema()` 대신
   `line_records.line_parameters_schema()`를 반환. 함수 이름 `submit_semantic_query` 불변.
2. `__init__.py`의 `ENVELOPE_PROPERTY`·`parse_tool_arguments` 재수출 대상을 line 모듈로
   전환하고, `test_hcx_bridge.py`는 `canna.runtime_view.hcx_bridge`에서 직접 import.
   두 bridge가 같은 이름을 수출하므로 이 정리 없이는 이름이 충돌한다.
3. live harness `model_messages()`가 `submission_guidance()` 대신
   `line_submission_guidance()`를 싣는다. 뒤에 붙는 한 문장(`target_dataset` ref record,
   ordering detail record, `limit_span`)은 이름이 그대로라 수정 불필요.
4. `test_hcx_runtime_view_precondition.py`의 제출 생성은 `json.dumps` 대신
   `render_line_records`.
5. live harness의 envelope 진단을 `envelope_diagnostics()`에서
   `line_envelope_diagnostics()`로 교체. 현행 `json_decoded`, `decode_error`,
   `decode_error_position_ratio`는 이 표기에 존재하지 않는다. 대체 항목은 6-A절에서
   승인·구현됐고 연결만 남았다. `finish_reason`과 `output_tokens`는 harness가 이미
   응답에서 읽고 있으므로 그 값을 인자로 넘기면 된다. 기록은 `DIAGNOSTIC_FIELDS` 허용
   목록으로 한정하며 제출 원문·span·opaque ref·credential·request/response ID는 통합
   후에도 기록하지 않는다. 그 경계는 6-A절의 테스트가 계속 강제한다.

## 9. 한계

- 이 표기가 provider에서 실제로 통과하는지는 **알 수 없다.** offline 검증은 서버가 무엇을
  받아들이는지만 말한다.
- 0-A에서 `delimited`의 기각 사유였던 "enum을 실을 수 없어 ref 무결성이 무너진다"는 지금
  enum을 system message가 싣고 서버가 전수 검증하므로 그대로 적용되지 않는다. 다만
  **모델의 ref 선택 정확도가 나빠질 가능성**은 남으며 이번 작업은 그것을 답하지 않는다.
- 조건값·연산자·정렬·limit canonicalizer는 여전히 없다. 표기와 무관하게 해당 요구는
  계속 `canonicalizer_unavailable`로 실행이 차단된다.
- 새 코드 6개(`unknown_record`, `stray_line`, `unterminated_record`,
  `duplicate_record_key`, `malformed_key_line`, `unsupported_line_break`)는 기존 5개와
  같은 **provisional internal** 상태이며 공유 계약 승인 대상이다.
- 연결 전까지 HCX가 실제로 받는 것은 여전히 JSON bridge다. 이 표기는 아직 어떤 실행
  경로에도 들어 있지 않다.

## 10. 형태 전용 진단 보완 (2026-08-31, 13회차 이후 · offline 승인됨)

상태: **`diagnostic ready / next live approval pending`.** 외부 호출 0회.

13회차 live는 `empty_submission`, `stray_line`, `unknown_record` 세 code로 차단됐고,
그 세 code는 header를 열지 못한 여러 다른 방식에서 똑같이 나온다. 어떤 방식이었는지는
관측만으로 특정할 수 없었다. 아래 범주는 그 구분만을 위해 추가됐다.

### 추가된 고정 shape 진단 범주

`DIAGNOSTIC_FIELDS`에 14개를 명시적으로 추가했다.

| 범주 | 형태 |
|---|---|
| `exact_record_header_count` | count |
| `casefold_record_header_count` | count |
| `indented_record_header_count` | count |
| `record_header_with_suffix_count` | count |
| `exact_end_count` | count |
| `indented_end_count` | count |
| `known_key_space_count` | count |
| `known_key_colon_count` | count |
| `bullet_prefixed_line_count` | count |
| `unknown_nonempty_line_count` | count |
| `literal_backslash_n_present` | boolean |
| `json_punctuation_present` | boolean |
| `first_line_class` | 고정 enum |
| `last_line_class` | 고정 enum |

두 `*_class`는 `LINE_CLASSES` 고정 enum만 값으로 갖는다: `absent`,
`exact_record_header`, `indented_record_header`, `casefold_record_header`,
`record_header_with_suffix`, `exact_end`, `indented_end`, `known_key_space`,
`known_key_colon`, `bullet_prefixed`, `json_punctuation`, `unknown`.

### 미기록 원칙

제출 원문, opaque ref, span, semantic ID, requirement id, **인식하지 못한 token의 원문**,
그리고 그것들의 **hash 어느 것도 기록하지 않는다.** 위 범주는 전부 이 모듈이 스스로 정한
이름과 개수이며, 한 줄은 모듈 자신의 record token·key 표와 비교된 뒤 고정 이름 하나로만
보고된다. 줄에서 나온 문자열이 기록으로 들어가는 경로가 없다.

`test_no_reference_span_identifier_or_unknown_token_reaches_the_diagnostics`가 실제·날조
ref, span, requirement id, unknown token 원문과 casefold 형태의 부재를 직렬화된 진단에서
검증한다. 기존 `set(diagnostics) <= set(DIAGNOSTIC_FIELDS)` 경계도 그대로 유지된다.

### 무변경

parser 문법(`read_line_records`), `SUBMISSION_SCHEMA`·`line_parameters_schema`,
system message(`line_submission_guidance`), Runtime View, validator, Registry, Ontology,
DB 모두 수정하지 않았다. 진단 함수는 읽기 전용이며 reader를 호출하지 않는다.

한 가지 판단만 기록해 둔다. key `ref`가 record token `REF`의 casefold prefix이므로, 알려진
key 검사를 느슨한 header 검사보다 앞에 둔다. 이 순서가 아니면 **정상 제출의 reference 줄이
malformation으로 보고된다.**

### 검증

- 전용 테스트 `tests/runtime_view/test_line_records.py`: **84 passed**
- 전체 offline: 1054 passed, 6 deselected (live marker 기본 deselect)
- `ruff check src tests`: All checks passed
- `git diff --check`: 문제 없음
- 외부 호출 0, embedding 0, DB 0, commit·push 없음

parser code가 같은 문서 형태 8종에 대해 위 범주의 signature가 모두 서로 다르다는 것을
`test_the_parser_codes_do_not_separate_these_documents_but_the_shapes_do`가 강제한다.

### 남은 것

다음 live 1회는 **사용자 승인 대기**다. 이 절은 그 1회가 무엇을 구분할 수 있게 되었는지만
말하며, provider가 무엇을 받아들이는지는 여전히 관측되지 않았다.
