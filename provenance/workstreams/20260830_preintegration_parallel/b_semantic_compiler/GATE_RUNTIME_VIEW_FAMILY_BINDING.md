# 구현 전 큰그림 게이트 — B: Runtime View와 상품군 혼입 방지 core

## 0. 역할 전환 선언

이 작업은 같은 채팅에서 **F(Ontology·Semantic Registry·Retriever) 역할을 종료하고
B(질문 해석과 결정적 compiler) 역할로 전환**해 수행한다.

- 직전까지의 F 작업: composite 평가기, 승인된 proposal 실행, gold 감사와 offline
  adjusted 재계산. 산출물은
  `provenance/workstreams/20260830_preintegration_parallel/f_ontology_registry_retriever/`에 있다.
- 이 문서부터의 B 작업: Retriever 후보를 상품군별 Runtime View로 정리하고, HCX가 다른
  상품군의 동명 지표를 선택해도 서버가 실행 전에 거부하는 production core를 만든다.

`DATA_ONTOLOGY_ALIGNMENT_DECISION_20260830.md` 6절에 따라 B는 Semantic Registry
generator와 Retriever를 소유하지 않는다. 이번 전환에서도 그 경계를 지킨다.

### owned path (이 작업이 쓰는 경로)

- `src/canna/runtime_view/**` — 신규. Runtime View 구성, opaque ref, `submit_semantic_query`
  입력 계약, 서버 검증
- `tests/runtime_view/**` — 신규
- `provenance/workstreams/20260830_preintegration_parallel/b_semantic_compiler/**`

### 읽기 전용 입력

- `data/processed/semantic_registry.json` (F 산출물, `Vocabulary`로 읽음)
- `src/canna/retrieval/candidates.py`의 공개 출력 타입 (F→B handoff 계약)

### 손대지 않는 경로

`ontology/**`, `src/canna/registry/**`, `src/canna/store/**`, `catalog/**`,
`src/canna/retrieval/**`, `src/canna/retrieval/retrieval_config.json`,
`data/processed/execution_registry.json`, `data/processed/query_store.duckdb`,
F의 proposal·report·감사 산출물.

## 1. 목적

```text
질문 문자열 + Retriever 후보
  → 상품군별로 묶인 Runtime View (요청 단위 opaque ref만 노출)
  → HCX가 ref만 선택한 submit_semantic_query 제출
  → 서버가 상품군·관계 방향·ref 유효성을 검증
  → 검증된 canonical logical plan 또는 구조화된 거부
```

이 슬라이스의 성공 기준은 정답을 맞히는 것이 아니라 **틀린 상품군 조합이 실행에
도달하지 못하게 하는 것**이다.

## 2. 일반 capability

일반화 단위는 "질문"이나 "상품군"이 아니라 **"요구의 target dataset과 그 요구가 참조하는
field/predicate의 Registry 상품군 소속이 양립하는가"** 하나다.

따라서 상품군 이름, 지표 이름, 질문 문자열, case ID에 대한 분기가 존재할 수 없다.
Registry에 새 상품군이나 새 지표가 추가되면 코드 변경 없이 같은 규칙이 적용되어야 한다.

## 3. 변경 계층과 계약

- **신규 계약(제안)**: Runtime View 모델 payload, `submit_semantic_query` 입력, 검증
  결과와 canonical logical plan. `contracts/`와 `ARCHITECTURE.md`는 수정하지 않으며
  `RUNTIME_VIEW_TOOL_DECISION_20260831.md`의 승인된 책임 분담을 구현할 뿐이다.
- **소비 계약**: F의 후보 출력. 점수·순위는 payload에 싣지 않는다.
- **이번 슬라이스 밖**: 조건값·연산자·정렬·limit의 canonicalization, Execution Registry
  binding, SQL 생성, Evidence, `/answer` 통합.

## 4. data grain · coverage · failure 의미

- 이 계층의 grain은 **semantic term과 요구**다. 행 수, 상품 수, coverage 수치는
  이 계층에 없다.
- dataset 후보의 grain(product / product_class)은 Registry가 선언한 값을 **전달만** 하고
  이 계층이 판정하지 않는다.
- 데이터 coverage는 Execution Registry의 소유다. Runtime View에 후보가 있다는 것이
  데이터가 있다는 뜻이 아니며 이 계층은 그 주장을 하지 않는다.
- 실패는 조용히 교정되지 않는다. 상품군 불일치, 미해결 entity, 결정 불가한 관계 방향,
  존재하지 않는 ref는 각각 다른 구조화 reason으로 남고 실행을 막는다.

## 5. 금지할 하드코딩

- 상품군 이름, semantic ID, alias, predicate ID의 Python 상수 복제
- 질문 문자열·case ID 분기
- 평가 fixture의 production import
- 실험에서 나온 후보 종류별 budget 값을 기본값이나 제품 상수로 삽입
- direct/look-through 구별을 predicate ID 목록으로 판정

상품군 소속은 Registry `families`, 관계 방향은 Registry `domain`/`range`/`inverse_of`,
관계 종류 구별은 **같은 domain/range를 공유하지만 서로 inverse가 아닌 predicate 집합**으로
파생한다. 어느 것도 코드에 목록으로 두지 않는다.

## 6. 수용 기준과 unseen variants

1. 공모펀드 총보수 질문에서 ETF 총보수 ref 선택 → 거부
2. 해외 ETF 순자산 질문에서 국내 ETF 순자산 ref 선택 → 거부
3. 국내 ETF·공모펀드 1년 수익률 동시 요구 → 두 상품군 binding이 분리 보존
4. direct 보유 predicate + 종목 anchor → 서버가 방향을 결정
5. look-through predicate가 direct로 대체되지 않음
6. 존재하지 않거나 다른 요청의 opaque ref → 거부
7. 후보 순서와 ref 값이 바뀌어도 canonical 결과 동일
8. budget 값 없이도 종류별 후보 묶음이 보존됨

unseen variants: 위 규칙은 특정 상품군 쌍이 아니라 Registry의 모든 상품군 쌍과 모든
family-scoped field에 대해 성립해야 한다. 합성 Registry로 시험해 실제 상품군 이름에
의존하지 않음을 보인다.

## 7. 알려진 한계

Semantic Registry에는 direct/look-through를 직접 구별하는 일급 discriminator가 없다.
이번 구현은 domain/range 공유 관계에서 파생하므로 동작하지만, Ontology에 relation mode를
명시하는 편이 더 명확하다. Ontology 변경은 사용자·Codex 승인 사항이므로 이번 작업에서
수행하지 않고 미결정으로 남긴다.

---

## 8. 2026-08-31 감사 후 게이트 재확인

사용자가 11개 계약 결함을 지적하고 B를 승인하지 않았다. 수정 전에 AGENTS.md의 큰그림
게이트를 다시 통과시킨 결과를 아래에 갱신한다. 정본 확인 순서는 `CONTEXT.md` →
`QUESTION_STRUCTURE.md` → `ARCHITECTURE.md` → `IMPLEMENTATION_PLAN.md` →
`DATA_ONTOLOGY_ALIGNMENT_DECISION_20260830.md` → `contracts/EVALUATION_API.md`다.

1. **목적**: 변경 없음. 다만 "상품군 혼입 차단"에 "서버가 정규화할 수 없는 연산의 실행
   차단"을 명시적으로 포함한다.
2. **일반 capability**: 두 개로 정정한다. ⑴ target dataset과 field/predicate의 상품군·grain
   양립성, ⑵ 요구가 쓰는 연산의 결정적 정규화 가능성.
3. **영향 계층**: 변경 없음. owned path 그대로.
4. **변경 계약**: 전부 **provisional internal**이며 `CONTRACT_STATUS`로 payload와 결과에
   표시한다. 공유 계약으로 승격하지 않는다.
5. **grain·coverage·실패**: dataset 후보 자격을 Registry 근거로 좁혔다. 연산 없음 +
   상품군 선언 + `product`/`product_class` grain을 모두 만족해야 query target이다.
   family가 증명되지 않은 field는 unresolved다.
6. **금지 하드코딩**: Registry kind 이름 매핑표를 제거하고 구조 파생으로 바꿨다. 정본에서
   빌린 어휘(요구 종류·grain)는 `contract.py`에 출처와 함께 한 곳에 둔다.
7. **수용 기준**: 기존 8개에 감사 11개 항목을 추가한다.

### 정정한 이전 주장

- 5절의 "class는 dataset 후보" 전제를 폐기했다. class 선언만으로는 query target이 아니다.
- "모든 후보 family가 dataset을 도입한다"는 주장을 "**선언된 families**를 가진 모든 후보"로
  정정했다. 현재 Registry의 관계 predicate는 family를 선언하지 않으므로 predicate만 있는
  질문은 dataset을 얻지 못하며, 그 결과는 거부다.
- 7절의 알려진 한계에 다음을 추가한다. Registry에 family-neutral field의 적용 범위 선언이
  없어 그런 field는 현재 실행에 쓸 수 없다. Ontology 변경은 승인 사항이므로 하지 않았다.

### 상태

이 작업은 `provisional / correction required`다. 사용자 승인 전까지
`IMPLEMENTATION_PLAN.md`의 B 단계를 완료로 바꾸지 않는다.
