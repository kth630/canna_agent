# Runtime 통합 — 한 번의 원자적 변경 (2026-08-31)

상태: **offline 통합 완료 / provider unverified.** 사용자가 canonicalizer correction과
Execution correction을 offline 승인한 뒤 지시한 통합이다. HCX live 호출 0회이므로 line
notation의 provider 수용 여부는 여전히 관측되지 않았다.

근거 기록: `HCX_LINE_RECORDS_OFFLINE_20260831.md` 8절(연결 diff 5개),
`CANONICALIZERS_20260831.md` 8절(연결 diff 4개), `src/canna/execution/REGISTRY_EXTENSION_PROPOSAL.md`.

## 1. 왜 한 번에 바꾸는가

두 bridge가 같은 이름(`ENVELOPE_PROPERTY`, `parse_tool_arguments`, guidance)을 수출한다.
wire·schema·system message·재수출을 나눠 적용하면 중간 상태에서 이름이 충돌하거나 선언과
지침이 어긋난다. canonicalizer도 마찬가지로 `AVAILABLE_CANONICALIZERS`만 채우고 호출을
붙이지 않으면 **검증 없이 실행이 열린다.** 그래서 9개 항목을 한 변경으로 적용했다.

## 2. 적용한 것

| # | 항목 | 결과 |
|---|---|---|
| 1 | HCX wire → line-record envelope | `hcx_wire_schema()`가 `line_parameters_schema()`를 반환. envelope property `submission_json` → `submission_text` |
| 2 | schema·system message·precondition·live harness 일치 | harness가 `line_submission_guidance()`를 싣고, precondition이 `render_line_records`로 제출하며, live harness가 `line_envelope_diagnostics()`를 기록 |
| 3 | 재수출 전환 | `runtime_view/__init__.py`가 line bridge를 수출하고 JSON bridge는 수출하지 않는다. `test_hcx_bridge.py`가 `canna.runtime_view.hcx_bridge`에서 직접 import |
| 4 | 진단 경계 | `DIAGNOSTIC_FIELDS` 12개만 기록. 실제 제출로 만든 진단에 ref·span·semantic ID가 0건임을 테스트가 강제 |
| 5 | `AVAILABLE_CANONICALIZERS` | 승인된 4종 등록. grouping·comparison requirement·explanation은 계속 공백 |
| 6 | validate ↔ canonicalize 연결 | `canonicalize_requirement`가 서버 판정에 들어가고 실패는 `canonicalization_refused`로 요구를 차단 |
| 7 | aggregation completeness | `kind=aggregation`에 aggregation detail·field·function span이 없으면 `requirement_incomplete` |
| 8 | `CODE_SPAN_ALIGNMENT_FAILED` 중복 제거 | `validate.py`의 로컬 정의를 지우고 `spans.py` 정본을 import |
| 9 | fail-closed 회귀 | 아래 4절 |

Registry·Ontology·DuckDB 원본, `line_records.py`, `hcx_bridge.py`, `grouped_flat.py`,
`src/canna/execution/`는 수정하지 않았다. commit·push·외부 호출 0회.

## 3. 실행 값을 내보내는 지점을 하나로 만들었다

`CanonicalRequirement.canonical`은 실패를 포함한 **기록**이고,
`CanonicalRequirement.execution_values`는 **관문**이다.

```python
@property
def execution_values(self) -> RequirementCanonicalization | None:
    return self.canonical if self.semantic_valid else None
```

한 slot이라도 거부되면 다른 slot이 성공했더라도 아무 값도 나가지 않는다. 거부된 요구에서
"정렬은 못 읽었지만 limit 10은 나왔으니 쓰자"가 구조적으로 불가능하다. 거부 사유는
`canonical`에 그대로 남아 계획을 읽는 쪽이 이유를 볼 수 있다.

## 4. 수직 테스트 (offline, 외부 호출 0회)

`tests/runtime_view/test_runtime_integration.py::test_a_submission_travels_from_the_runtime_view_to_a_blocked_execution`

실제 Semantic/Execution Registry로 만든 Runtime View → line notation 렌더 → line parser →
semantic validation → canonicalization → execution 차단까지 한 테스트에서 통과한다.

전송될 record lines(실제 출력, ref는 이 요청이 발행한 값):

```text
REQ
requirement_id v1
kind ranking
status mapped
source_span 국내 ETF 중 1년 수익률이 높은 10개를 보여줘.
limit_span 10개
END
REF
requirement_id v1
role target_dataset
ref ds_beb9202bc07556a67ed6b925de6d5e08
END
DETAIL
requirement_id v1
detail_kind ordering
ref fd_829a091232c76c436e4f83bea4025f84
span 높은
END
```

단계별 실제 결과:

```text
semantic_valid: True | server_decision: mapped
canonical:      desc 10
execution_readiness: not_evaluated_by_semantic_validation
execution status: unavailable | failure: provenance_binding_unavailable | rows: 0
```

**의미가 완전한 계획도 답이 되지 않는다.** Execution Registry에 row-level provenance와
selection policy 선언이 없으므로 C의 executor가 `unavailable`을 반환한다. 이것이
`REGISTRY_EXTENSION_PROPOSAL.md`가 말하는 정답이며, 이번 통합은 그 판정을 성공으로
바꾸지 않는다. 확인한 것은 인터페이스뿐이다: canonicalizer의 `direction`/`limit`이
`ResolvedProductQuery.direction`/`limit`에 변형 없이 들어간다.

## 5. fail-closed 회귀

| 테스트 | 무엇을 막는가 |
|---|---|
| `test_an_unreadable_direction_stops_the_path_before_any_execution_value` | 방향어를 못 읽으면 limit이 읽혔어도 실행값 0개 |
| `test_a_limit_that_is_not_a_row_count_stops_the_path` | 개수 문법 실패도 같은 방식으로 차단 |
| `test_a_refused_requirement_releases_no_execution_values` | plan·requirement·`unresolved_requirement_ids`·`execution_values_released`가 모두 일관되게 거부 |
| `test_an_aggregation_without_its_detail_is_incomplete` | 집계 detail 부재는 `requirement_incomplete` (canonicalizer 부재가 아니다) |
| `test_an_aggregation_naming_a_field_but_not_a_function_is_incomplete` | field만 있고 function span이 없으면 같은 판정 |
| `test_an_aggregation_with_its_detail_reaches_the_canonicaliser` | 대조군. 완전한 집계는 canonicalizer까지 가고, 거부 사유는 Registry 권한이다 |
| `test_the_wired_diagnostics_remember_shape_and_nothing_from_the_submission` | 실제 제출로 만든 진단에 ref·span·semantic ID 0건, 기록은 `DIAGNOSTIC_FIELDS` 이내 |
| `test_an_operation_with_no_canonicalizer_is_returned_non_executable` | grouping은 여전히 `canonicalizer_unavailable` |

## 6. 통합이 바꾼 기존 판정

canonicalizer가 켜지면서 "지금까지 항상 거부되던 것"이 통과하거나 다른 사유로 거부된다.
관련 테스트를 사실에 맞게 고쳤고, 약화한 것이 없도록 대조군을 함께 넣었다.

| 테스트 | 이전 | 이후 |
|---|---|---|
| `test_a_span_quoted_from_the_question_passes_alignment` | `canonicalizer_unavailable` ×2 | `canonicalization_refused` 1건. `낮은 순으로`는 정렬돼 있지만 문법이 읽지 못한다. **인용과 해석 가능은 다르다**는 것을 이제 code가 구분한다 |
| (신규) `test_a_quoted_and_readable_ranking_produces_its_execution_values` | — | `낮은 순`은 통과하고 `asc`/10을 낸다 |
| `test_an_operation_with_no_canonicalizer_is_returned_non_executable` | ranking으로 시험 | grouping으로 교체. 규칙은 그대로이고 시험 대상만 실제로 canonicalizer가 없는 종류로 옮겼다 |
| `test_a_well_formed_submission_still_faces_the_semantic_validator` | 유일한 거부가 canonicalizer 부재 | 거부 0건. bridge 경유 결과 = parser 직접 결과라는 원래 취지는 그대로 |
| `test_the_approved_case_survives_the_notation_with_real_references` | 거부 | 통과하고 `desc`/10 산출 |
| `test_approved_live_case_preconditions_hold_without_network` | 거부 | 통과하고 실행값 산출. 제출 렌더링이 `json.dumps` → `render_line_records` |
| live 테스트 (deselect 상태) | `semantic_valid False` | `semantic_valid True`, envelope 진단은 line 진단 |

## 7. 검증 명령과 실제 출력

```powershell
uv run --cache-dir .tmp/uv-cache python -m pytest tests/runtime_view/test_runtime_integration.py -q
```

```text
8 passed in 1.22s
```

```powershell
uv run --cache-dir .tmp/uv-cache python -m pytest tests/runtime_view -q
```

```text
553 passed, 1 deselected
```

```powershell
uv run --cache-dir .tmp/uv-cache python -m pytest -q --basetemp=.tmp/pt-final -rs
```

```text
1040 passed, 6 deselected in 93.79s (0:01:33)
```

```powershell
uv run --cache-dir .tmp/uv-cache python -m pytest -q -m "hcx_live or embedding_live" -rs
```

```text
6 skipped, 1039 deselected in 6.04s
```

```powershell
uv run --cache-dir .tmp/uv-cache ruff check src tests
```

```text
All checks passed!
```

```powershell
git diff --check
```

```text
(출력 없음, exit 0)
```

**외부 API 호출 0회, DB 쓰기 0회, commit·push·branch 0회.** DuckDB는 C의 executor가
읽기 전용으로 한 번 조회했고 결과는 `unavailable`이다.

## 8. 남은 것

- **line notation의 provider 수용 여부는 미관측이다.** 별도 명시 승인 없이는 live 호출을
  하지 않는다. 상태는 `offline accepted / provider unverified`.
- Execution Registry의 row-level provenance·selection policy·dataset population 선언.
  이것이 붙기 전까지 production 실행은 계속 `unavailable`이 정답이다.
- 공유 reason code 계약 승인. 이번에 `canonicalization_refused`가 추가돼 provisional
  internal code가 더 늘었다.
- `낮은 순으로`처럼 자연스럽지만 문법표에 없는 활용형은 거부된다. form 추가가 옳은 대응인지,
  아니면 조사 처리를 문법에 넣을지는 사용자·Codex 결정 사항이다.
- entity resolution, grouping·comparison requirement·explanation canonicalizer.
