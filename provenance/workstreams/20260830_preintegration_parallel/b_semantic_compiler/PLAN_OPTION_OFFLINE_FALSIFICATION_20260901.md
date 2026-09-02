# HCX 역할 축소안 offline 반증 실험 결과 — 2026-09-01

상태: **실험 결과 / production 구현 아님 / 아키텍처 변경 아님 / 계약 승인 아님**

게이트: `PLAN_OPTION_OFFLINE_GATE_20260901.md`
대상 제안: `HCX_ROLE_REDUCTION_CONTRACT_PROPOSAL_20260901.md` (비정본 검토안)
산출 데이터: `generated/plan_option_probe_primary_20260901.json`,
`generated/plan_option_probe_holdout_20260901.json`,
`generated/plan_option_cap_boundary_20260901.json`

외부 호출: **HCX 0회, embedding 0회, DB 쓰기 0회, commit·push 0회.**
production package(`src/canna/runtime_view/`, `src/canna/execution/`, `src/canna/registry/`,
`src/canna/retrieval/`), `contracts/`, `ARCHITECTURE.md`, Registry·Ontology·DuckDB 산출물은
**수정하지 않았다.** 추가한 것은 실험 전용 owned path뿐이다.

---

## 1. 판정

> **B. SpanLedger / option generator 계약 수정 후 재검증 필요.**

A(진행 가능)가 아닌 이유는 통과 조건 7개 중 2개가 미충족이고, holdout에서 새 실패 유형이
나왔기 때문이다. C(성립 불가)가 아닌 이유는 실패가 전부 **국소적이고 원인이 특정된 회수
실패**이며, 계약의 위험한 축(제공되지 않은 조합 생성, 상태 혼합, lossy truncation 성공
처리, payload 누출, cross-request ref)은 primary·holdout 양쪽에서 **0건**이었기 때문이다.

다만 아래 6절의 **구조적 발견 하나**가 A/B/C보다 중요하다. 이 corpus에서 서버가 계획을
결정할 수 있으면 계획은 거의 항상 **하나뿐이었고**(질문당 PlanOption 중앙값 1, 최댓값 2),
결정할 수 없으면 **0개**였다. 즉 "HCX가 여러 계획 중 하나를 고른다"는 전제가 성립하는
구간이 현재 데이터·질문 구조에서는 매우 좁다. 역할 축소안을 진행하더라도 그 이득은
"조합 폭발 통제"가 아니라 "wire 단순화와 fail-closed 경계"로 재서술해야 한다.

---

## 2. 실험 설계 요약

- corpus: 기존 사용자 승인 fixture **49문항**만 사용. 새 자연어 질문 0개.
  - primary 24문항(`runtime_view_probe.jsonl`, `semantic_grounding.jsonl`)으로 개발
  - holdout 25문항(`*_unseen`, `*_regression`, `*_verification`)은 모든 수정 종료 뒤 **1회만** 실행
- Runtime View: 각 fixture 계열이 authored된 승인 synthetic view source 전체 pool
  (rv 계열 40후보 / sg 계열 31후보). 선언된 후보 부분집합이 아니라 pool 전체를 넣어
  prune 부담을 낮추지 않았다.
- 재사용(수정 없이 import): `canonicalize.py`의 direction/comparison/aggregation/limit
  문법표와 canonicalizer 4종, `spans.py`의 exact alignment, `contract.py`의 요구 종류·
  상태·grain·`KIND_CANONICALIZERS`·`AVAILABLE_CANONICALIZERS`.
- 별도 track: 실제 `semantic_registry.json` + `execution_registry.json` + rule-only
  retrieval로 production `build_runtime_view`를 돌려 anchor 공급 가능성만 관측.
- 생성기는 gold를 보지 않는다. 채점은 생성 뒤에만 수행한다.

---

## 3. 통과 조건 대조

| # | 통과 조건 | primary(24) | holdout(25) | 판정 |
|---|---|---:|---:|---|
| 1 | required semantic anchor 누락 0 | 1건 | 3건 | **미충족** |
| 1' | requirement frame 누락 0 | 0건 | 1건 | **미충족** |
| 2 | 잘못된 non-requirement 분류 0 | 0건 | 0건 | 충족 |
| 3 | 제공되지 않은 의미 조합 생성 0 | 0건 | 0건 | 충족 |
| 4 | semantic/canonicalization/execution 상태 혼합 0 | 0건 | 0건 | 충족 |
| 5 | arbitrary·cross-request ref 실행 경로 0 | 0건 | 0건 | 충족 |
| 6 | lossy truncation 성공 처리 0 | 0건 | 0건 | 충족 |
| 7 | 질문·상품·case별 runtime 하드코딩 0 | 0건 | 0건 | 충족 |

보조 지표: required anchor key 63개(primary) / 67개(holdout) 중 각각 3개·6개는 span이
아니라 **entity→dataset 유도**로만 회수됐다. 이는 실패가 아니라 계약 정정 대상이다(5.1절).
requirement frame **kind** 불일치는 양쪽 0건이다.

`required_span_anchor_not_covered`(gold span_anchor가 어떤 frame에도 안 덮임)는 양쪽 0건이다.
즉 프레임 경계 자체는 gold anchor를 놓치지 않았고, 실패는 anchor **인식**에서 났다.

---

## 4. 실패 taxonomy

### 4.1 회수 실패 (통과 조건 1)

| 유형 | primary | holdout | 원인 |
|---|---:|---:|---|
| `surface_form_paraphrase` — field/predicate label이 수식어 삽입형으로 쓰임 | 0 | 3 | exact-surface 매칭이 "…동안의 수익률", "간접적으로 노출된" 같은 활용·삽입을 읽지 못한다 |
| `predicate_surface_gap` — view source가 predicate label만 선언 | 1 | 1 | 관계 표현의 축약형이 surface form 목록에 없다 |
| `categorical_condition_operator` — 계사(`~인`)로 표현된 등가 조건 | 0 | 1 | `COMPARISON_FORMS`에 계사가 없고, 비수치 조건값 recognizer가 없다 |
| `direction_vocabulary_gap` — 차원 전용 형용사(짧은/긴) | 0 | 1 | `DIRECTION_FORMS`에 없어 ranking이 attribute_lookup으로 떨어진다 |

### 4.2 프레임 실패 (통과 조건 1')

| 유형 | holdout | 원인 |
|---|---:|---:|
| `coordinated_output_fields_split_into_two_requirements` | 1 | 같은 target에 속한 두 output field가 접속조사로 이어졌을 때, 이것이 "요구 1개 + output 2개"인지 "요구 2개"인지 접속만으로는 구별되지 않는다. `QUESTION_STRUCTURE.md` 2절이 명시한 바로 그 구별이다 |

같은 corpus 안에 반례가 있다: 두 output field가 **서로 다른 target**에 걸리면 요구 2개가
맞다(그 case는 통과했다). 즉 판별자는 접속어가 아니라 **양쪽 target의 동일성**이다.
이 규칙은 holdout을 본 뒤에 알아냈으므로 이번 실험에서는 **구현하지 않았다.** 계약 수정
항목으로만 올린다.

### 4.3 실패가 아니라 계약대로 차단된 것

아래는 통과 조건 위반이 아니라 fail-closed가 정상 동작한 결과다.

| 차단 사유 | primary | holdout | 성격 |
|---|---:|---:|---|
| `anchor_has_no_runtime_view_candidate` | 5 | 9 | 미지원 capability(전망·편입비중·ESG 등)를 unresolved로 회계 |
| `canonicalization_refused` | 5 | 7 | production canonicalizer의 정당한 거부 |
| `canonicalizer_unavailable` | 2 | 2 | comparison requirement·explanation은 canonicalizer 자체가 없음 |
| `unaccounted_modifier_span` | 5 | 4 | 5.2절 참조 |
| `field_span_not_bound_to_this_target` | 0 | 3 | family prune이 실제로 작동한 결과 |
| `missing_target_dataset` | 0 | 1 | 상품군을 결정할 근거 없음 |

canonicalizer 거부 코드 분포(양 split 합): `ordering_field_unresolved` 8,
`canonicalizer_unavailable` 4, `unit_not_canonicalizable` 1,
`value_expression_unsupported` 1, `span_alignment_failed` 1.

- `unit_not_canonicalizable`: 통화 금액 field에 대한 written value 비교. `canonicalize.py`가
  선언한 대로 거부하는 것이 정답이다.
- `value_expression_unsupported`: 일 수 단위 field에 기간 표현("1년")을 비교값으로 씀.
  기간→일 수 변환기가 없으므로 거부가 정답이다.
- `span_alignment_failed`: 비수치 조건값이 value span으로 잡히지 않아 빈 span이 정렬 실패.

---

## 5. 제안 계약이 실제로 수정되어야 하는 지점

### 5.1 `SpanLedger`의 unaccounted content 규칙은 그대로 쓸 수 없다

제안 5.1절은 "content-bearing 잔여 span이 있으면 option set 전체 non-selectable"이라고 쓴다.
이 규칙을 문자 그대로 적용하면 **미지원 capability를 물은 질문이 `unresolved` 요구로
회계되지 못하고 통째로 사라진다.** `QUESTION_STRUCTURE.md` 5절이 요구하는
`mapped | unresolved | ambiguous` 삼분 회계와 충돌한다.

이번 실험은 잔여 content를 `unresolved_anchor`(요구를 이끄는 내용어)와
`unresolved_modifier`(이미 인식된 span 바로 앞에 붙은 수식어)로 나누어 **보존**했다.
전자는 요구를 `unresolved`로 만들고 후자는 의미 상태를 유지한 채 실행만 막는다.
이 분리 없이는 primary 24문항 중 미지원 capability로 차단된 5문항이 회계 자체에서 증발한다.

**수정 요구:** `SpanLedger`에 `unresolved_anchor` role과, unaccounted content를
"차단"이 아니라 "unresolved 요구로 승격"하는 경로를 넣어야 한다.

### 5.2 `non_requirement_reason` 4종 allow-list는 부족하다

제안이 허용한 `connective | politeness | discourse | punctuation`만으로는 승인 corpus의
잔여를 하나도 남김없이 분류할 수 없다. 실제로 필요했던 추가 분류(양 split 합계):

| 추가 사유 | 사용 횟수 | 성격 | 어휘 출처 |
|---|---:|---|---|
| `particle` (조사) | 49 | 언어 | 실험이 새로 선언(`lexicon.PARTICLES`) |
| `result_grain_noun` (상품/종목 등) | 24 | 도메인 인접 | **view source가 스스로 쓴 관계 role label의 head noun에서 추출**. 코드에 상수로 적지 않았다 |
| `inflection` (된/하는 등 긍정 어미) | 3 | 언어 | 실험이 새로 선언. 부정 어미(않는/없는)는 의미를 바꾸므로 **의도적으로 제외** |

`result_grain_noun`이 없으면 "상품", "종목" 같은 결과 grain 명사가 전부 unaccounted content가
되어 모든 질문이 차단된다. 이것은 allow-list를 넓히자는 주장이 아니라, **넓히지 않으면
아무 질문도 통과하지 못한다**는 관측이다.

### 5.3 수식어는 결정적으로 처리할 수 없다

"최근 1년 수익률"의 `최근`과 "향후 수익률"의 `향후`는 둘 다 인식된 field span 앞에 붙는
동일한 형태의 잔여다. 전자는 무해하고 후자는 **과거 지표를 전망으로 바꾸는** 치명적
수식어다. 결정적 규칙으로는 구별할 수 없으므로 이번 실험은 둘 다 `unaccounted_modifier_span`
으로 **실행을 막았다**(primary 5건, holdout 4건). 이는 0-A에서 관측된 "과거 수익률을
전망으로 대체" 실패를 서버에서 재발시키지 않는 유일한 안전한 처리다.

**수정 요구:** 수식어 처리 정책을 계약에 명시해야 한다. 세 선택지가 있다.
(a) 현재처럼 전부 차단 — 안전하지만 자연스러운 질문이 대량 거부된다.
(b) Registry가 승인한 수식어 화이트리스트를 두고 나머지는 차단.
(c) 수식어를 별도 requirement slot으로 승격해 `ambiguous`로 회계.
현재 데이터로는 (b)가 유일하게 실행 가능해 보이지만, 화이트리스트의 소유자는 Registry여야
하며 코드 상수가 되어서는 안 된다.

### 5.4 entity가 함의하는 target은 span anchor가 아니다

"이 ETF가 보유한 종목"류 질문에서 target 상품군은 질문에 **쓰여 있지 않고** entity의 소속에서
유도된다(primary 3건, holdout 6건). 제안 5.1절의 "모든 anchor는 정확히 한 번 span으로 덮인다"는
문장은 이 경우를 거짓 누락으로 만든다.

**수정 요구:** anchor를 `span-anchored`와 `derived-from-anchor` 두 종류로 나누고, 후자에는
유도 근거(entity의 dataset 소속)를 provenance로 기록해야 한다.

### 5.5 implicit output field는 explicit requirement가 아니다

승인 fixture는 목록형 요구의 output에 상품명 field를 **동등 대안**으로 허용한다. 질문은
상품명을 쓰지 않는다. 따라서 이것은 explicit span 회계 대상이 아니라
`QUESTION_STRUCTURE.md` 4절의 **서버 소유 invariant**로 다뤄야 한다. 실험 초기에 이를
required anchor로 채점했더니 6건이 거짓 실패했다.

---

## 6. 조합 폭발과 cap — 실제 분포

### 6.1 승인 corpus 분포

| 지표 | primary(n=24 질문 / 33 요구) | holdout(n=25 질문 / 33 요구) |
|---|---|---|
| requirement frame / 질문 | min 1, 중앙 1, max 3 | min 1, 중앙 1, max 4 |
| raw 후보 / 요구 (prune 전) | min 0, 중앙 2, max 5 | min 0, 중앙 1, max 6 |
| RequirementOption / 요구 (prune·dedup 후) | min 1, 중앙 1, **max 1** | min 1, 중앙 1, **max 2** |
| PlanOption / 질문 | min 1, 중앙 1, **max 1** | min 1, 중앙 1, **max 2** |
| lossy discard가 발생한 질문 | 0 | 0 |
| 어떤 cap에 닿거나 넘은 질문 | 0 | 0 |

**어떤 cap도 이 corpus에서는 구속하지 않았다.** 8/8/32/16 중 가장 낮은 것에도 닿지 못한다.

원인은 명확하다. 서버의 span 회계는 **exact surface 매칭**이므로 한 slot에 후보가 사실상
하나만 남는다. 후보가 둘 이상 남을 수 있는 경로는 세 가지뿐이다.

1. 같은 표현이 여러 상품군의 field를 가리키는 homonym → family prune이 target으로 해소
2. 판별자(period/unit/currency/grain)가 다른 동명 후보가 같은 target 안에 공존 →
   `materially_ambiguous`로 **차단**(선택지가 아니다)
3. 하나의 field가 여러 target에 속하고 질문이 그 target들을 함께 지목 → 이때만 진짜 복수 option

### 6.2 cap 경계 직접 측정 (합성 구조 probe, 자연어 fixture 아님)

`generated/plan_option_cap_boundary_20260901.json`

| cap | 값 | 직전 | 정확히 cap | cap+1 |
|---|---:|---|---|---|
| RequirementOption / requirement | 8 | 7개, `choice_required`, 선택 가능 | 8개, `choice_required`, 선택 가능 | 8개 유지 + **lossy 1 → `truncated`, 선택 불가** |
| explicit requirements | 8 | 7개, `complete` | 8개, `complete` | **`truncated`, PlanOption 0개** |
| 최종 PlanOption | 16 | 8개, `choice_required` | 16개, `choice_required` | 생성 32 → 16 유지 + **lossy 16 → `truncated`, 선택 불가** |

cap+1에서 조용한 절단은 한 건도 없었고, 전부 `candidate_space_truncated`로 **전체 차단**됐다.
"lossy truncation을 성공으로 처리한 사례 0"은 이 경계에서도 유지된다.

**이 숫자들을 production 상수로 승인하지 말 것.** 실제 corpus는 cap 근처에 오지 않았으므로
이 측정은 "cap 규칙이 안전하다"만 보여줄 뿐 "8/8/32/16이 옳다"를 보여주지 않는다.

---

## 7. Plan presentation과 prompt budget

`display_summary`는 자유 문장 없이 allow-list 10개 field로만 조립했다:
`requirement, kind, target_meaning, field_meaning, period, unit, relation_meaning,
relation_direction, result_grain, question_spans`.

- stable semantic ID 노출: **0건** (양 split 전 질문)
- physical table/column/JOIN/SQL 노출: **0건**
- verified product/entity ID 노출: **0건** (요약은 meaning과 원문 span만 싣는다)
- 자유 생성 문장: 0 (구조상 불가능)

payload 크기(질문당, option 수를 인위적으로 채운 하한 추정. token은 provider 호출 없이
CJK 1자=1token, ASCII 4자=1token으로 **추정**한 값이다):

| option 수 | bytes 중앙(primary/holdout) | bytes 최대 | 추정 token 중앙 | 추정 token 최대 |
|---:|---|---:|---|---:|
| 2 | 821 / 811 | 2,867 | 227 / 223 | 787 |
| 4 | 1,629 / 1,609 | 5,721 | 450 / 442 | 1,571 |
| 8 | 3,245 / 3,205 | 11,429 | 896 / 880 | 3,138 |
| 16 | 6,477 / 6,397 | 22,845 | 1,788 / 1,756 | 6,272 |

16 option에서도 중앙값 약 6.4KB / 약 1,790 token으로, Runtime View 전체 payload보다 작다.
**prompt budget은 이 설계의 제약 요인이 아니다.** 다만 6절에 따라 실제로 16개를 제시할
상황 자체가 관측되지 않았다.

---

## 8. 불변성과 ref 권한

- 후보 순서를 3개 seed로 셔플해도 질문별 PlanOption `equivalence_key` 집합이 동일했다
  (primary 24문항 × 3회). requirement 순서와 요청 salt에도 불변이다.
- 같은 질문을 두 요청으로 발행하면 ref 집합은 **교집합 0**, `CanonicalPlan` preview는 **동일**했다.
- 임의 문자열 → `selected_plan_ref_malformed`, 타 요청 ref → `selected_plan_ref_not_in_request`,
  재사용 → `selected_plan_ref_consumed`, 만료 → `selected_plan_ref_expired`,
  차단된 plan → `selected_plan_is_not_selectable`. 각각 고유 사유로 거부되고
  "가장 비슷한 ref" fallback은 없다.
- 생성 preview와 선택 시 재계산 preview가 다르면 `option_revalidation_mismatch`로 차단한다.

---

## 9. 실제 Registry track — anchor 공급 가능성

승인 fixture 질문을 실제 `semantic_registry.json` + `execution_registry.json`과 rule-only
retrieval로 production `build_runtime_view`에 넣고, gold가 요구하는 anchor의 **표현**이
실제 Registry가 이름 붙인 후보로 제시되는지만 관측했다.

| anchor 종류 | primary 요구/회수 | holdout 요구/회수 |
|---|---|---|
| dataset | 27 / **27** | 26 / **26** |
| field | 24 / **21** | 26 / **21** |
| predicate | 5 / **0** | 6 / **0** |

제시 후보 수는 질문당 중앙 18(primary) / 11(holdout).

**관계 predicate anchor는 실제 Registry에서 한 건도 회수되지 않았다.** 이는 B의 기존 관측
(관계 predicate가 family를 선언하지 않아 dataset binding을 얻지 못함)과 일치하며, 역할
축소안 이전에 해결해야 하는 선행 문제다. 서버가 계획을 미리 만들려면 관계 후보가 Runtime
View에 실제로 올라와야 한다.

---

## 10. 실행한 검증 명령과 출력

```powershell
uv run --cache-dir .tmp/uv-cache python -m pytest tests/experiments -q --basetemp=.tmp/pt-exp
```

```text
23 passed in 0.89s
```

```powershell
uv run --cache-dir .tmp/uv-cache python -m pytest -q --basetemp=.tmp/pt-full -rs
```

```text
1125 passed, 6 deselected in 47.22s
```

```powershell
uv run --cache-dir .tmp/uv-cache python -m pytest -q -m "hcx_live or embedding_live" -rs
```

```text
6 skipped, 1125 deselected in 2.32s
```

```powershell
uv run --cache-dir .tmp/uv-cache ruff check src tests
```

```text
All checks passed!
```

```powershell
$env:PYTHONPATH="src"
uv run --cache-dir .tmp/uv-cache python -m canna.experiments.plan_option_probe.run `
  --split primary --with-real-registry `
  --out provenance/.../generated/plan_option_probe_primary_20260901.json
uv run --cache-dir .tmp/uv-cache python -m canna.experiments.plan_option_probe.run `
  --split holdout --with-real-registry `
  --out provenance/.../generated/plan_option_probe_holdout_20260901.json
```

두 실행의 aggregate는 3~9절 표와 `generated/*.json`에 있다. `external_calls`는 양쪽
보고서에서 `{"hcx": 0, "embedding": 0, "database": 0}`이다.

---

## 11. 새로 추가한 상수와 허용 근거

| 상수 | 위치 | 근거 |
|---|---|---|
| `PARTICLES` (조사 46개) | `lexicon.py` | 언어 어휘. `canonicalize.py`의 문법표와 같은 성격이며 도메인 명사를 포함하지 않는다 |
| `CONNECTIVES`, `POLITENESS_FORMS`, `DISCOURSE_MARKERS`, `ANAPHOR_MARKERS`, `PUNCTUATION` | `lexicon.py` | 제안 5.1절 `non_requirement_reason` 4종을 구현하는 데 필요. 언어 어휘 |
| `INFLECTIONS` (긍정 어미 5개) | `lexicon.py` | 언어 어휘. 부정 어미는 의미를 바꾸므로 의도적으로 제외했음을 주석에 기록 |
| `LISTING_MARKERS`, `COMPARISON_REQUIREMENT_MARKERS`, `EXPLANATION_MARKERS` | `lexicon.py` | **도메인 인접**. `QUESTION_STRUCTURE.md` 2절의 결과 단위 3종을 인식하는 데 필요하고, production에는 이들 canonicalizer가 없으므로 인식이 곧 "non-executable로 회계"하는 유일한 수단이다. **승인 대상으로 올린다** |
| `_FIXTURE_UNIT_CODES`, `_FIXTURE_OPERATION_CODES` | `lexicon.py` | 승인 synthetic fixture가 ontology unit/operation code 이전에 작성돼 생긴 어댑터. 실제 Registry는 ontology code를 직접 선언하므로 production에는 불필요 |
| `OptionGenerationPolicy` 8/8/32/16 | `options.py` | 제안 7절의 **잠정값**. 하나의 policy 객체가 소유하고 runtime source에 중복하지 않는다. **production 상수로 승인 요청하지 않는다** |
| `TARGET_FORM`, `METRIC_FORM` 등 | `capprobe.py` | cap 경계 측정용 placeholder. 실제 상품·지표를 지시하지 않으며 fixture로 등록하지 않았다 |

**적지 않은 것:** 실제 Registry stable semantic ID, family ID, physical table/column,
CQ/question/case ID, 평가 질문 문자열, 상품명, 날짜, 행 수, 현재 coverage 수치.
`result_grain_noun` 어휘는 코드가 아니라 view source의 관계 role label에서 읽는다.

---

## 12. 보지 않은 구조 변형

holdout 25문항에서 처음 실행한 변형과 결과:

| 변형 | 결과 |
|---|---|
| requirement 순서·target 표면 순서 교환 | 프레임 회수 유지 |
| 단일 target × 복수 requirement (최대 4요구) | 프레임 4/4 회수 |
| 복수 target × 단일 requirement | 회수 유지, family prune 정상 |
| 관계 filter + 속성 output/order | 관계 표현 축약형에서 **회수 실패**(4.1) |
| direct와 look-through 방향 | look-through 축약형에서 **회수 실패**(4.1) |
| 동일 의미 복수 binding / 인접 의미 field | 판별자 동일 → dedup, 판별자 상이 → `materially_ambiguous` 차단 |
| producer→consumer 1단계 nested reuse | 지시사 뒤 개수 표현을 `nested_reuse`로 인식, 요구 2개로 회계 |
| 2 operand comparison | 프레임 인식 성공, canonicalizer 부재로 차단 |
| cap 직전/정확/직후 | 6.2절, 전부 계약대로 |
| ref collision·만료·중복 선택 | 8절, 전부 고유 사유로 거부 |

**아직 보지 않은 변형:** 3개 이상 operand 비교, 깊이 2 이상 nested, 서로 다른 통화·기간
사이의 비교, grouping 요구, 부정·전칭 명제, 실제 Registry 기반 관계 질문(9절 때문에 실행
불가), 실제 HCX의 ref 선택 정확도(범위 밖).

---

## 13. 코드·계약·아키텍처 이탈 감사

- `ARCHITECTURE.md` Confirmed 결정 변경: **없음.** 이 문서는 제안 검토용 관측만 기록한다.
- shared contract(`contracts/`) 변경: **없음.**
- production package 변경: **없음.** `git status`의 modified 목록은 실험 시작 시점과 동일하다.
- Registry·Ontology·DuckDB·원본 데이터 변경: **없음.** DuckDB 읽기도 하지 않았다.
- 기존 architecture guard 전부 통과. 특히
  `test_experiment_modules_declare_that_they_are_experiments`와
  `serving code imports an experiment package` guard를 만족하도록 실험 모듈에 배너를 넣었다.
- 실험 코드가 fixture의 expected decision을 생성기에 주입하지 않는다: 생성기는
  `corpus.py`를 import하지 않고, 채점만 생성 결과를 읽는다.
- 진단·보고에 요청 ref, 질문 원문, semantic ID를 남기지 않는다: 보고서는 test_id, 개수,
  reason code만 싣는다.

---

## 14. 다음에 필요한 결정

1. 5.1~5.5의 다섯 가지 `SpanLedger` 계약 정정을 반영할지, 아니면 역할 축소안을 중단할지.
2. 수식어 처리 정책 (5.3의 a/b/c 중 하나). Registry 소유 화이트리스트를 만든다면 그 생성
   경로가 F workstream 범위인지.
3. 접속된 output field와 접속된 requirement를 target 동일성으로 구별하는 규칙(4.2)을
   계약에 넣을지. 이는 holdout을 본 뒤 도출한 규칙이므로, 채택 시 새 holdout이 필요하다.
4. 실제 Registry의 관계 predicate가 dataset binding을 얻도록 하는 선행 작업(9절)의 소유자.
   이것 없이는 역할 축소안이 관계 질문에서 성립하지 않는다.
5. 6절의 구조적 발견을 고려할 때, HCX ①을 "복수 계획 중 선택"으로 두는 것이 맞는지,
   아니면 "단일 계획에 대한 확인 또는 거부"로 두는 것이 맞는지.
6. 잠정 cap 8/8/32/16은 현재 데이터에서 구속하지 않으므로, 값 승인을 보류하고
   "lossy discard 1건이면 전체 차단" 규칙만 먼저 승인할지.

---

## 15. 이 실험이 답하지 않은 것

- 실제 실행 가능성. Execution Registry에 row-level provenance·selection policy·dataset
  population binding이 없으므로 모든 option의 `execution_readiness`는 `blocked`이며
  `execution_provenance_binding_unavailable`을 constraint로 달고 있다. 이것이 현재 정답이다.
- HCX가 opaque ref 하나를 실제로 정확히 고르는지. live 호출 금지 범위였다.
- provider의 실제 token 수. 7절 값은 호출 없는 추정이다.
- embedding 경로가 4.1의 paraphrase 실패를 해소할 수 있는지. embedding live 호출은 금지
  범위였고, rule-only 경로만 관측했다.
