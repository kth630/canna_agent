# 서버 canonicalizer 1차 구현 — 2026-08-31

상태: **1차 correction 반영 / 연결(wiring)은 미적용**. `AVAILABLE_CANONICALIZERS`는 여전히
공집합이므로 런타임 동작은 이 작업으로 바뀌지 않는다. 연결에 필요한 diff는 8절에 있고,
사용자·Codex 승인 전에는 적용하지 않는다. 1차 구현의 silent wrong answer 24건과 그 수정은
10절에 있다.

작업 범위 지시: HCX wire와 무관하게 `SubmittedRequirement`의 원문 span을 결정적인 실행값으로
바꾸는 서버 canonicalizer. 근거 결정은 `ARCHITECTURE.md` 3·4절,
`DATA_ONTOLOGY_ALIGNMENT_DECISION_20260830.md` 5절의 2026-08-31 보완,
`IMPLEMENTATION_PLAN.md` 0-A "이 결과가 바꾸는 다음 행동".

## 1. 무엇을 막는 구현인가

0-A 재검증이 측정한 실패는 **모델이 정규화한 실행값을 신뢰할 수 없다**는 것이다. opaque ref
복사는 유지되지만 조건값("1조원"→10000), 연산자("이하"→`lt`), 정렬 방향은 보존되지 않았다.
그래서 wire는 원문 span만 나르고, 실행값은 서버가 한 번, 결정적으로 만든다.

지금까지 그 서버 쪽이 비어 있었다. `AVAILABLE_CANONICALIZERS=∅`이라 조건·정렬·limit·집계가
붙은 모든 요구가 `canonicalizer_unavailable`로 non-executable이었고, 실행 가능한 것은
조건·정렬·limit·집계·grouping이 없는 `listing`, `attribute_lookup`, `count`뿐이었다.

## 2. 일반화 단위

**질문이 아니라 문법이다.** 두 가지를 결합해야 실행값이 나온다.

1. 이 표현이 무슨 뜻인가 — 한국어/영어 어휘표. 상품군과 무관하다. "이상"은 어느 상품군을
   묻든 `gte`다.
2. Registry가 그 연산을 허용했는가 — `allowed_operations`. 표현이 아무리 명확해도 Registry가
   `filter`를 주지 않은 field는 filter하지 않는다.

어느 한쪽만으로는 실행값을 만들지 않는다. 어휘표에는 상품명·지표명·상품군·semantic ID·
질문 문자열이 하나도 없으며, 테스트가 실제 Registry의 semantic ID와 family id 전체를 모듈
소스(주석·출처 상수 제외)에서 찾아 0건임을 강제한다.

## 3. 지원 문법

### 3.1 정렬 방향 (`asc` | `desc`)

| 방향 | 인정하는 표현 |
|---|---|
| `desc` | 높은, 높다, 높은순, 높은 순, 큰, 많은, 상위, 내림차순, 최고, 최대, descending, desc, highest, largest, top |
| `asc` | 낮은, 낮다, 낮은순, 낮은 순, 작은, 적은, 하위, 오름차순, 최저, 최소, ascending, asc, lowest, smallest, bottom |

`가장 높은`·`가장 큰`·`가장 낮은`·`가장 작은`을 명시 form으로 추가했다(전 34개).

**부분문자열로 매칭하지 않는다.** span 전체가 승인된 form과 명시적 연결어
(`또는`, `그리고`, `및`, `혹은`, `이거나`, `or`, `and`, `,`, `/`)와 공백으로 남김없이 덮일
때만 읽는다. 설명되지 않은 음절이 하나라도 남으면 `unsupported`다. 각 위치에서는 가장 긴
form이 이긴다(backtracking 포함).

### 3.2 개수

span이 **행 개수 표기 자체**여야 한다. 숫자를 포함하기만 하는 것으로는 부족하다.

```text
limit := [상위|하위|top|bottom|first] number [개의|개|건|종목|곳|가지|위]
```

전체 일치가 아니면 거부한다. `KODEX 200`, `상품코드 123`, `ETF 10`, `약 10개`는 정수를
가지고 있지만 행 수를 말하지 않으므로 거부된다. 비율·범위·기간·부호·자릿수 단어도 거부다.

숫자의 자릿수 구분 쉼표는 없거나 `1,000`·`12,345,678` 형태여야 한다. `1,00`, `1,`,
`12,34,567`은 쉼표를 지워서 읽지 않고 거부한다. 값 slot에도 같은 규칙을 적용한다.

맨 숫자 네 자리는 연도가 쓰이는 형태와 같고 행 수임을 가릴 근거가 없으므로, 세는 말 없이
쓰인 네 자리 수(`2026`)는 거부한다. 이 규칙은 확인이 필요한 결정으로 9절에 남긴다.

### 3.3 비교 연산자

| 연산자 | 인정하는 표현 |
|---|---|
| `gte` | 이상, 이상인, `>=`, `≥`, at least, or more |
| `gt` | 초과, 넘는, 넘게, 보다 큰, 보다 높은, 보다 많은, greater than, more than, above, `>` |
| `lte` | 이하, 이하인, `<=`, `≤`, at most, or less |
| `lt` | 미만, 보다 작은, 보다 낮은, 보다 적은, less than, below, under, `<` |
| `eq` | 같은, 같다, 동일, equal to, equals, `=` |
| `ne` | 아닌, 아니, 제외, `!=`, `≠`, other than |

포함 관계는 **어휘 단위가 아니라 발화 위치 단위**로 처리한다. `<=`의 `<`는 같은 위치의
같은 글자이므로 하나의 표현이지만, 다른 위치에서 쓰인 `<`는 별개의 표현이다. 따라서
`<=`는 `lte`이고 `< 또는 <=`는 **ambiguous 거부**다.

연산자 이름은 새로 만들지 않았다. Execution Registry가 이미 모든 binding에 발행하는
`physical_operations` 값을 그대로 쓰며, 테스트가 부분집합임을 강제한다.

### 3.4 값과 단위 — Registry가 크기를 고정한 단위만

| unit_code | 판정 | 근거 |
|---|---|---|
| `percent_observed` | **canonicalize함** (표기 `%`, `퍼센트`, 무표기) | `core.ttl`: "관측된 값의 크기가 백분율 표기와 일치한다" → `3%`는 **3**이며 절대 0.03이 아니다 |
| `count` | canonicalize함 (`개`, `건`) | `core.ttl` 수량 |
| `days` | canonicalize함 (`일`) | `core.ttl` 일수 |
| `multiplier` | canonicalize함 (`배`) | `core.ttl` 배수 |
| `currency_amount` | **거부** | 저장 배율이 선언돼 있지 않고 통화는 행 단위 정책에서 온다. "1조원"을 억원 단위 column에 대면 조용한 사실 오류가 된다 |
| `price` | **거부** | 단가의 통화·배율을 term metadata가 고정하지 않는다 |
| `number` | **거부** | `core.ttl`이 "원천이 단위를 선언하지 않았다"는 뜻으로 선언한 단위다. 사용자 수치와 같은 단위라고 보는 것이 바로 이 계층이 금지하는 가정이다 |
| `none` | **거부** | 코드·라벨·날짜다. 원문 값을 저장 코드로 해석하는 것은 별도 계층 |
| 미선언·미등록 | **거부** | 새 unit은 알려진 unit처럼 동작한다고 가정하지 않는다 |

자릿수 단어 `천·만·억·조`는 한 개까지 확장하고(`1만`→10000) 복합("1조 5000억")은 숫자가 둘이
되어 거부한다. `currency_policy`가 비어 있지 않은 field는 통화가 행마다 다르므로 값
canonicalization을 거부한다.

### 3.5 집계 함수

`count`(개수·갯수·건수·몇 개·수·count), `sum`(합계·총합·합·sum·total),
`avg`(평균·average·avg·mean), `min`(최소·최저·최솟값·최소값·가장 낮은·가장 작은·minimum·min·
lowest), `max`(최대·최고·최댓값·최대값·가장 높은·가장 큰·maximum·max·highest).

Registry 권한은 함수별로 다르다. `count`는 `count`를, 나머지는 `aggregate`를 요구한다.
`가중`, `중앙`, `누적`, `이동`, `연평균`, `월평균`, `일평균`, `분기평균`이 들어간 표현은
자기가 포함한 함수 이름과 **다른 함수**이므로 거부한다("가중평균"을 `avg`로 읽지 않는다).
전체 덮기 규칙이 이미 이들을 거부하지만, 더 정확한 사유를 남기려고 먼저 확인한다.

## 4. 거부 문법과 reason code

| code | 언제 |
|---|---|
| `span_alignment_failed` | span이 질문에 없음. 정렬 뒤에만 canonicalize한다는 규칙의 집행 지점 |
| `direction_expression_unsupported` / `_ambiguous` | 모르는 방향어 / 두 방향을 동시에 말함 |
| `limit_expression_unsupported` | 숫자 없음, 기간 표현, 범위 표현, 자릿수 단어 |
| `limit_expression_ambiguous` | 숫자가 둘 이상 |
| `limit_not_a_positive_integer` | 0, 음수·부호, 소수 |
| `limit_is_a_proportion` | "상위 10%" — 모집단 없이 행 수로 바꾸지 않는다 |
| `comparison_expression_unsupported` / `_ambiguous` | 모르는 비교어 / 두 연산자 |
| `value_expression_unsupported` | 숫자가 0개 또는 2개 이상, 읽을 수 없는 값 표현 |
| `value_unit_mismatch` | 다른 단위의 표기로 쓰인 값(`percent` field에 "10개") |
| `unit_not_canonicalizable` | 위 3.4의 거부 단위, 미선언 단위, 행 단위 통화 |
| `aggregation_function_unsupported` / `_ambiguous` | 모르는 집계어·수식된 집계 / 두 함수 |
| `negated_expression_unsupported` | 부정 표현. `않`·`못`, 그리고 승인된 form **바로 앞**의 `안`(띄어쓰기 무관). 부정을 반대 의미로 뒤집지 않는다 |
| `operation_not_allowed_by_registry` | 표현은 읽혔으나 Registry가 그 연산을 허용하지 않음 |
| `field_metadata_unavailable` | field ref가 Registry term으로 해소되지 않음 |

전부 provisional internal이며 공유 reason code 계약은 아직 승인 전이다.

## 5. typed 출력

```text
DirectionResult(direction="asc"|"desc", matched_forms)
LimitResult(limit: int > 0)
ComparisonResult(operator ∈ {eq,ne,gt,gte,lt,lte},
                 value=TypedValue(number: Decimal, unit_code, magnitude_word, marker))
AggregationResult(function ∈ {count,sum,avg,min,max}, required_operation)
RequirementCanonicalization(conditions, ordering, limit, aggregation, failures)
```

값은 `float`가 아니라 `Decimal`이다. `0.5%`가 `0.5`로 남아야 하고 이진 부동소수 오차가
경계 조건의 포함/제외를 바꾸면 안 되기 때문이다. `TypedValue`는 값이 **어느 단위로 읽혔는지**
함께 나른다. 값만 넘기면 다음 계층이 다시 단위를 추측하게 된다.

`RequirementCanonicalization`은 slot마다 독립적으로 실패한다. 한 slot이 막혀도 나머지가
조용해지지 않으므로, 계획은 실제로 잘못된 것 **전부**를 이유로 거부된다.

## 6. 하지 않은 것

- grouping, comparison requirement 전체, explanation canonicalizer — 계속 fail-closed
- 텍스트·코드·날짜 값 해석(`unit_code=none`) — 값 도메인 해석은 별도 계층
- entity resolution, SQL 컴파일, DB 실행, Evidence
- HCX bridge / grouped-flat / wire schema / Registry / Ontology / DB 수정
- 외부 API 호출, commit, push, branch, worktree
- 새 전체 질문 fixture. 테스트는 고립된 span 문법 단위 테스트이며 제품 질문이 아니다

## 7. 검증

```powershell
uv run --cache-dir .tmp/uv-cache python -m pytest tests/runtime_view/test_canonicalize.py -q --basetemp=.tmp/pytest-canon
```

```text
240 passed in 0.98s
```

```powershell
uv run --cache-dir .tmp/uv-cache python -m pytest tests/runtime_view -q --basetemp=.tmp/pytest-canon-rv
```

```text
544 passed, 1 deselected in 12.38s
```

```powershell
uv run --cache-dir .tmp/uv-cache python -m pytest -q --basetemp=.tmp/pytest-canon-full -rs
```

```text
1031 passed, 6 deselected in 84.95s (0:01:24)
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

deselect 6건은 `hcx_live` + `embedding_live`이며 **외부 API 호출 0회, DB 실행 0회**다. 전체
suite 수가 늘어난 것은 이번 추가분 52건과 병렬 workstream의 신규 테스트가 함께 들어왔기
때문이다.

### 테스트가 강제하는 것

- **어휘표 자기 대조**: 세 표의 모든 form(방향 30, 비교 42, 집계 34)을 되먹여 표가 주장하는
  뜻이 나오는지 전수 확인한다. `<`가 `<=` 안에서, "최대"가 "최댓값" 안에서 가려지는 실패는
  나중에 오답으로 발견되지 않고 여기서 깨진다.
- **거부는 code로 확인**한다. 전부 거부하는 canonicalizer가 통과하지 못하도록 정상 통과
  대조군을 같이 둔다.
- **실제 Registry 구조 탐색**: Registry가 선언한 unit을 전수로 물어 profile이 없는 unit이
  0건임을 확인한다(새 unit이 조용히 통과할 수 없다). Registry가 `percent_observed`이면서
  `filter` 가능하다고 선언한 term을 전부 찾아 실제로 비교가 만들어지는지 확인한다. 특정
  semantic ID를 테스트에 적지 않는다.
- **어휘 출처**: canonical 연산자·집계 이름이 Execution Registry `physical_operations`의
  부분집합임을 확인한다.
- **하드코딩 검사**: 실제 Registry의 semantic ID 331개와 family id 4개가 모듈 실행 코드에
  0건임을 확인한다(출처 주석·`*_SOURCE` 상수는 제외 — provenance 기록은 요구사항이다).
- **보지 않은 변형**: 전각 숫자, 천단위 쉼표, 영어 대문자, 활용형 조합, 단일·복합 자릿수,
  `%p`, 한자 숫자, 부호 붙은 개수, 잘못 묶인 쉼표, 상품명·코드·연도 속 숫자.
- **속성 검사 두 개**가 예시 네 개가 아니라 form 전수에 규칙을 건다. 어떤 form이든 뒤에
  설명되지 않는 음절(`잡`)이 붙으면 거부되고, 어떤 form이든 앞에 `안`이 붙으면 세 slot
  어디에서도 읽히지 않는다.

### 테스트가 찾아낸 실제 결함 3건

1. **음수 개수가 양수로 읽혔다.** `-5개`가 limit 5가 됐다. 숫자 추출 정규식이 부호를 잡지
   않았고 파서가 앞의 `-`를 무시했다. 부호가 붙은 개수는 이제 `limit_not_a_positive_integer`다.
2. **부정 표현이 slot마다 다르다.** "평균이 아니"가 `avg`로 읽혔다. "아니"는 비교 slot에서는
   부정어가 아니라 연산자 `ne` 자체다. 부정 판정을 slot에 따라 나눴다.
3. **긴 기호 연산자가 ambiguous로 거부됐다.** `<=`가 `<`와 `<=` 둘 다 발화시켰다. 포함 관계인
   짧은 form을 제거하는 규칙을 넣었다.

### 알려진 한계

- 전체 덮기 규칙은 조사가 붙은 표현을 읽지 못한다. "종목 수"는 form이 아니고 "수가"도
  아니므로 둘 다 `unsupported`다. 활용형·조사 조합을 늘리려면 form을 명시적으로 추가해야
  하며, 그때마다 전수 속성 검사가 함께 돈다. 거부 방향으로 틀린다.
- `desc order`, `상위권`, `최상위`, `높은 순서대로`처럼 1차에서 읽히던 표현이 이제 거부된다.
  덮기 규칙의 의도된 결과이며, 필요하면 form을 명시적으로 추가하는 것이 옳은 대응이다.
- 네 자리 맨 숫자 거부 규칙은 `1,000`처럼 세는 말 없는 정상 개수도 함께 거부한다.
  `1,000개`로 쓰면 읽힌다.
- 현재 Registry 기준 비교 canonicalization이 가능한 binding은 `percent_observed` 52 +
  `count` 12 + `days` 1 + `multiplier` 1이며, `currency_amount` 11 + `price` 26 + `number` 6 +
  `none` 136은 위 근거로 거부된다. 이 수치는 관측값이며 runtime 상수가 아니다.

## 8. 연결에 필요한 diff (적용하지 않음, 실행하지 않음)

아래는 승인 시 적용할 변경이다. **작성만 했고 적용·실행하지 않았으므로 통과 근거는 없다.**
7절의 검증 출력은 모듈과 그 전용 테스트에 대한 것이다.

`AVAILABLE_CANONICALIZERS`만 채우고 호출을 붙이지 않으면 검증 없이 실행이 열린다. 따라서
세 파일을 **함께** 바꿔야 하며 하나만 적용해서는 안 된다.

### 8.1 `src/canna/runtime_view/contract.py`

```diff
-AVAILABLE_CANONICALIZERS: frozenset[str] = frozenset()
+# The four the server implements and tests (canonicalize.py). Grouping, whole
+# comparison requirements and explanations stay absent because they stay refused.
+AVAILABLE_CANONICALIZERS: frozenset[str] = frozenset(
+    {
+        CANONICALIZER_ORDERING,
+        CANONICALIZER_LIMIT,
+        CANONICALIZER_COMPARISON,
+        CANONICALIZER_AGGREGATION,
+    }
+)
```

`canonicalize.IMPLEMENTED_CANONICALIZERS`가 같은 네 이름을 들고 있고 테스트가 일치를
강제하지만, `contract`를 `canonicalize`가 import하므로 역방향 import는 순환이 된다. 두 곳의
값이 어긋나지 않는지는 테스트가 본다.

### 8.2 `src/canna/runtime_view/validate.py`

```diff
@@ imports
+from .canonicalize import (
+    FieldMetadata,
+    RequirementCanonicalization,
+    canonicalize_requirement,
+    field_metadata,
+)
-from .spans import aligned
+from .spans import CODE_SPAN_ALIGNMENT_FAILED, aligned
@@ reason codes
-CODE_SPAN_ALIGNMENT_FAILED = "span_alignment_failed"   # 로컬 정의 제거
+CODE_CANONICALIZATION_REFUSED = "canonicalization_refused"

@@ class CanonicalRequirement (line 208 부근)
     preserved: PreservedSubmission
+    canonical: RequirementCanonicalization | None
     blocking_codes: tuple[str, ...]

@@ CanonicalRequirement.to_dict (line 221 부근)
             "preserved": self.preserved.to_dict(),
+            "canonical": _canonical_dict(self.canonical),

@@ _validate_requirement, line 520 블록 뒤에 추가
     issues.extend(
         ValidationIssue(
             code=CODE_CANONICALIZER_UNAVAILABLE,
             ...
         )
         for name in _missing_canonicalizers(requirement)
     )
+    canonical = canonicalize_requirement(
+        view.question, requirement, _field_metadata_lookup(facts, view)
+    )
+    issues.extend(
+        ValidationIssue(
+            code=CODE_CANONICALIZATION_REFUSED,
+            requirement_id=requirement.requirement_id,
+            detail=f"{failure.slot}: {failure.detail}",
+        )
+        for failure in canonical.failures
+    )

@@ 두 CanonicalRequirement 생성 지점 (line 556, 578)
-            preserved=preserved,
+            preserved=preserved,
+            canonical=canonical,      # _blocked 경로는 None
```

`kind=aggregation`의 완전성도 이때 붙인다. 지금은 집계 요구가 aggregation detail 없이도
`_check_completeness`를 통과한다.

```diff
@@ _check_completeness
+    if requirement.kind == REQUIREMENT_KIND_AGGREGATION and (
+        requirement.aggregation is None
+        or not requirement.aggregation.field_ref
+        or not requirement.aggregation.function_span
+    ):
+        issues.append(
+            ValidationIssue(
+                code=CODE_REQUIREMENT_INCOMPLETE,
+                requirement_id=requirement.requirement_id,
+                detail=(
+                    "an aggregation has to name the field it aggregates and quote the "
+                    "word that says which aggregation; neither is inferred"
+                ),
+            )
+        )
```

추가할 보조 함수:

```python
def _field_metadata_lookup(facts, view):
    """A field reference, answered with what the Registry says about that term."""

    def lookup(ref: str) -> FieldMetadata | None:
        semantic_id, _code = _resolve(view, ref, KIND_FIELD)
        if semantic_id is None or not facts.has(semantic_id):
            return None
        return field_metadata(facts.term(semantic_id))

    return lookup


def _canonical_dict(canonical):
    return None if canonical is None else {
        "conditions": [
            {"operator": item.operator,
             "value": item.value.to_dict() if item.value else None}
            for item in canonical.conditions
        ],
        "ordering": canonical.ordering.direction if canonical.ordering else "",
        "limit": canonical.limit.limit if canonical.limit else None,
        "aggregation": canonical.aggregation.function if canonical.aggregation else "",
        "failures": [failure.to_dict() for failure in canonical.failures],
    }
```

`model_response`는 allow-list 방식이므로 plan에 field가 늘어도 모델 응답에 새지 않는다.
`_blocked` 경로(모델이 스스로 unresolved/ambiguous로 남긴 요구)는 canonicalize하지 않고
`canonical=None`이다.

### 8.3 `src/canna/runtime_view/__init__.py`

`canonicalize`의 공개 이름(`FieldMetadata`, `TypedValue`, 네 canonicalizer,
`canonicalize_requirement`, `field_metadata`, `IMPLEMENTED_CANONICALIZERS`, reason code)과
`validate`의 `CODE_CANONICALIZATION_REFUSED`를 기존 알파벳 순서에 맞춰 import·`__all__`에
추가한다.

### 8.4 연결 시 함께 추가할 회귀 테스트

- 조건·정렬·limit·집계가 붙은 요구가 이제 `canonicalizer_unavailable` **없이** 통과한다
- grouping·comparison·explanation 요구는 계속 `canonicalizer_unavailable`이다
- canonicalization 실패가 `server_decision != mapped`와 `semantic_valid=False`를 만든다
- 실행값이 plan에는 있고 `model_response`에는 없다
- `contract.AVAILABLE_CANONICALIZERS == canonicalize.IMPLEMENTED_CANONICALIZERS`
- `kind=aggregation`인데 aggregation detail이 없으면 `requirement_incomplete`
- `kind=aggregation`인데 `field_ref` 또는 `function_span`이 비면 `requirement_incomplete`
- aggregation detail을 갖춘 집계 요구는 계속 통과한다(대조군)
- `validate`가 `spans`의 `CODE_SPAN_ALIGNMENT_FAILED`를 import하고 로컬 정의가 없다

## 9. 남은 계약 결정

1. **공유 reason code 계약.** 이번에 15개가 늘었고 전부 provisional internal이다.
2. **`currency_amount`·`price`·`number`의 실행 배율.** Registry가 저장 배율(그리고 price의
   통화)을 선언하면 금액 비교가 열린다. 선언 없이는 계속 거부다. 이는 Ontology/Catalog 변경
   제안이며 B가 임의로 하지 않는다.
3. **`unit_code=none` 값 해석.** 코드·라벨·날짜 조건을 지원하려면 값 도메인 해석 계층
   (등급 코드, 날짜 파싱, identifier scheme)이 필요하다. 별도 슬라이스다.
4. **grouping·comparison requirement·explanation canonicalizer.** 계속 fail-closed.
5. **연산자별 Registry 권한.** 현재는 `filter` 하나로 여섯 연산자를 모두 연다. Execution
   Registry는 binding마다 `physical_operations`를 따로 발행하므로, 계획 수준 실행 가능성
   판정에서 연산자 단위로 다시 확인할지가 C/D와의 결정 사항이다.


## 10. 1차 구현의 silent wrong answer와 수정 — 2026-08-31 correction

1차 구현은 승인된 표현을 **부분문자열**로 찾았다. 그래서 표현을 포함하기만 하는 텍스트를
표현으로 읽었고, 포함 관계를 어휘 단위로 지웠으며, 숫자는 쉼표를 지워서 읽었다. 아래
"수정 전"은 폐기된 매칭 코드를 그대로 재현해 같은 입력으로 실제 측정한 값이다. 굵은 값이
silent wrong answer다.

| 항목 | slot | span | 수정 전 | 수정 후 |
|---|---|---|---|---|
| 1 발화 위치 | 비교 | `< 또는 <=` | **lte 3** | 거부 `comparison_expression_ambiguous` |
| 1 발화 위치 | 비교 | `<= 또는 <` | **lte 3** | 거부 `comparison_expression_ambiguous` |
| 1 발화 위치 | 비교 | `= 또는 !=` | **ne 3** | 거부 `comparison_expression_ambiguous` |
| 1 발화 위치 | 비교 | `!= 또는 =` | **ne 3** | 거부 `comparison_expression_ambiguous` |
| 1 발화 위치 | 비교 | `> 그리고 >=` | **gte 3** | 거부 `comparison_expression_ambiguous` |
| 2 잔여 음절 | 비교 | `이상한` | **gte 3** | 거부 `comparison_expression_unsupported` |
| 2 잔여 음절 | 정렬 | `최소가입금액` | asc | 거부 `direction_expression_unsupported` |
| 2 잔여 음절 | 집계 | `평균적으로` | avg | 거부 `aggregation_function_unsupported` |
| 2 잔여 음절 | 정렬 | `상위험` | desc | 거부 `direction_expression_unsupported` |
| 3 붙여 쓴 부정 | 정렬 | `안높은` | desc | 거부 `negated_expression_unsupported` |
| 3 붙여 쓴 부정 | 정렬 | `안 높은` | 거부(negated) | 거부 `negated_expression_unsupported` |
| 3 붙여 쓴 부정 | 비교 | `안같은` | **eq 3** | 거부 `negated_expression_unsupported` |
| 3 붙여 쓴 부정 | 집계 | `안 평균` | 거부(negated) | 거부 `negated_expression_unsupported` |
| 3 붙여 쓴 부정 | 정렬 | `안정적인` | 거부(unsupported) | 거부 `direction_expression_unsupported` |
| 4 쉼표 묶음 | 개수 | `1,00개` | **100** | 거부 `limit_expression_unsupported` |
| 4 쉼표 묶음 | 개수 | `1,개` | **1** | 거부 `limit_expression_unsupported` |
| 4 쉼표 묶음 | 개수 | `12,34,567개` | **1234567** | 거부 `limit_expression_unsupported` |
| 4 쉼표 묶음 | 값 | `1,%` | **gte 1** | 거부 `value_expression_unsupported` |
| 4 쉼표 묶음 | 값 | `12,34%` | **gte 1234** | 거부 `value_expression_unsupported` |
| 5 limit 문법 | 개수 | `KODEX 200` | **200** | 거부 `limit_expression_unsupported` |
| 5 limit 문법 | 개수 | `상품코드 123` | **123** | 거부 `limit_expression_unsupported` |
| 5 limit 문법 | 개수 | `ETF 10` | **10** | 거부 `limit_expression_unsupported` |
| 5 limit 문법 | 개수 | `2026` | **2026** | 거부 `limit_expression_unsupported` |
| 5 limit 문법 | 개수 | `약 10개` | **10** | 거부 `limit_expression_unsupported` |
| 대조군 | 정렬 | `높은 순` | desc | desc |
| 대조군 | 비교 | `보다 큰` | **gt 3** | gt 3 |
| 대조군 | 집계 | `가장 낮은` | min | min |
| 대조군 | 정렬 | `가장 낮은` | asc | asc |
| 대조군 | 개수 | `10` | **10** | 10 |
| 대조군 | 개수 | `10개` | **10** | 10 |
| 대조군 | 개수 | `상위 10개` | **10** | 10 |
| 대조군 | 개수 | `하위 3건` | **3** | 3 |
| 대조군 | 개수 | `top 5` | **5** | 5 |
| 대조군 | 개수 | `1,000개` | **1000** | 1000 |
| 대조군 | 비교 | `<=` | **lte 3** | lte 3 |
| 대조군 | 비교 | `!=` | **ne 3** | ne 3 |

24개 재현 사례 중 22개가 값을 만들어 냈고(`안 높은`, `안 평균`은 1차에서도 거부됐다),
12개 대조군은 전부 값이 바뀌지 않았다.

### 무엇을 바꿨는가

1. **발화 위치 기준 포함 관계.** 각 위치에서 가장 긴 form이 이기고 backtracking한다.
   `<=`는 한 위치의 한 표현이지만 `< 또는 <=`는 두 위치의 두 표현이므로 ambiguous다.
2. **전체 덮기.** span의 모든 글자가 승인된 form·명시적 연결어·공백으로 설명돼야 읽는다.
   `이상한`·`최소가입금액`·`평균적으로`·`상위험`은 설명되지 않는 음절이 남아 거부된다.
   `높은 순`·`보다 큰`·`가장 낮은`은 명시 form이므로 계속 읽힌다. 이를 위해
   `가장 높은/큰/낮은/작은`을 정렬 form으로 추가했다.
3. **붙여 쓴 부정.** 승인된 form 바로 앞의 `안`은 띄어쓰기와 무관하게 부정이다. `안정적인`은
   `안` 뒤에 승인된 form이 없으므로 부정이 아니라 그냥 읽을 수 없는 표현으로 남는다.
4. **엄격한 자릿수 구분.** 쉼표는 없거나 `1,000`·`12,345,678` 형태만 허용하고, 아니면
   지우지 않고 거부한다. 값 slot에도 같은 규칙을 적용한다.
5. **limit 문법.** span 전체가 행 개수 표기여야 한다. 맨 네 자리 수는 연도 표기와 구별할
   근거가 없으므로 세는 말 없이는 거부한다.

예시 네 개를 통과시키는 것으로 끝내지 않았다. form 전수에 거는 속성 검사 두 개를 넣어,
어떤 form이든 설명되지 않는 음절이 붙으면 거부되고 어떤 form이든 앞에 `안`이 붙으면 세
slot 어디에서도 읽히지 않음을 확인한다.

### 정정

앞선 보고에서 `CODE_SPAN_ALIGNMENT_FAILED`를 한 곳으로 모았다는 취지로 적었다. 사실이
아니다. `spans.py`에 추가했을 뿐이고 `validate.py:82`의 로컬 정의가 그대로 남아 **현재
문자열이 두 곳에 중복돼 있다.** 제거는 8.2절 wiring diff에 넣었고 지금 적용하지 않았다.

### 여전히 열지 않은 것

`AVAILABLE_CANONICALIZERS`는 공집합 그대로다. 위 수정과 8.4절 integration 회귀 테스트가
끝나기 전에는 실행을 열지 않는다.
