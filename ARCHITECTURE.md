# Architecture

## 1. Source of truth

이 문서는 Canna의 아키텍처 정본이다. `CONTEXT.md`의 공식 사실과
`QUESTION_STRUCTURE.md`의 의미 구조 위에서 런타임 책임 경계를 정의한다.

- `Confirmed`: 사용자와 Codex가 승인한 현재 아키텍처
- `Experiment-dependent`: 실험 결과에 따라 구체 형식이 바뀔 수 있는 부분
- `Out of scope`: 2026-09-06 제출 전 주 구조로 만들지 않는 부분

실험 실패는 `IMPLEMENTATION_PLAN.md`의 다음 행동을 바꿀 수 있다. Confirmed 결정을
바꾸려면 사용자와 Codex의 승인이 필요하다.

## 2. 시스템 원칙 — Confirmed

> HCX는 자연어의 명시적 의미를 bounded semantic refs로 표현하고, 서버는 그 의미를
> 검증해 관계와 수치를 같은 조회 저장소에서 결정적으로 컴파일·실행한다.

```text
질문
  ↓
Runtime View
  - dataset / field / predicate / entity 후보
  - 의미 구별자와 실제 coverage
  ↓
명백한 사전 차단
  ↓
HCX ①: explicit requirement accounting + semantic query
  ↓
서버 검증·컴파일
  - ref·type·operation·coverage 검증
  - server-owned invariant 적용
  - DuckDB JOIN / EXISTS / CTE 결정
  ↓
실행과 Evidence
  ↓
HCX ②: Evidence 범위 안의 최종 답변
```

논리적 단계가 물리 HCX 호출 수나 SQL statement 수와 일치할 필요는 없다. 하나의 semantic
query를 여러 SQL로 실행할 수 있지만 HCX가 중간 ID 목록이나 JOIN을 계획하지 않는다.

## 3. 책임 경계 — Confirmed

### Runtime View

질문 문자열에서 결정적으로 관련 후보를 회수한다.

- `dataset_ref`: 상품군/dataset 후보와 실제 capability coverage
- `field_ref`: meaning, period, unit, currency, grain, source, allowed operations
- `predicate_ref`: domain, range, direction, direct/look-through 의미, evidence requirements
- `entity_ref`: per-request opaque identifier와 사람이 구별할 후보 metadata

인접 field는 이름 목록만 노출하지 않고 같은 구조의 구별자를 함께 제공한다. Runtime
View가 후보를 누락하면 정확도의 천장이 낮아지므로 retrieval recall을 독립 측정한다.

### HCX ①

- 질문의 explicit span을 Target, Condition, Requirement, Relationship으로 회계한다.
- Runtime View가 제공한 opaque ref만 복사한다.
- 물리 table/column, SQL, JOIN, product ID 목록을 생성하지 않는다.
- 각 explicit requirement를 `mapped`, `unresolved`, `ambiguous` 중 하나로 남긴다.
- 후보가 없거나 의미가 결정되지 않으면 ref를 발명하지 않는다.

### 서버 검증·컴파일

- opaque ref의 존재, type, operation, grain, coverage를 검증한다.
- semantic predicate를 Execution Registry의 물리 table/column/join binding으로 연결한다.
- 관계 조건을 `EXISTS`, product-grain `DISTINCT`, JOIN 또는 CTE로 컴파일한다.
- server-owned implicit invariant를 항상 적용한다.
- parameterized DuckDB query만 실행한다.
- requirement 누락, unresolved, ambiguous 또는 claim에 부족한 coverage를 조용히 무시하지 않는다.

### Evidence와 HCX ②

Evidence는 결과뿐 아니라 주장 가능 범위를 함께 전달한다.

- source와 source record/문서 식별자
- effective/requested as-of와 freshness
- applied filters, aggregations, order, limit
- `applied_rules`
- coverage grain과 observed/full universe
- 제외·누락·실패 사유
- 결과와 result grain

HCX ②는 Evidence 밖의 사실을 보충하거나 observed 결과를 global 결과로 확대하지 않는다.

## 4. Semantic query의 논리 계약 — Confirmed

정확한 wire encoding은 실험 대상이지만 논리 정보는 다음을 보존해야 한다.

- target dataset refs
- explicit requirement record와 source span
- field/predicate/entity refs
- filter와 relationship filter
- grouping/aggregation/order/output fields/limit
- nested result reuse가 있으면 bounded 구조
- unresolved/ambiguous requirement와 근거

opaque ref는 요청 단위로 생성하며 모델이 의미 있는 ID를 조합하거나 추측할 수 없게 한다.
provider가 nested schema를 거부하면 반복되는 `requirement_id`를 가진 flat records로
encoding한다. 서로 묶인 span/ref/status를 독립 parallel array로 분리하지 않는다.

## 5. 상태, 원인, 모집단 — Confirmed

서로 독립인 세 축을 하나의 enum으로 합치지 않는다.

- `answer_status`: `supported | partial | refused`
- `reasons`: `unresolved`, `ambiguous`, `coverage`, `no_data` 등 구조화된 복수 원인
- `universe`: `full | observed`, product/portfolio count와 coverage grain

예: “관측 가능한 1,246개 중 상위 10개”는 새 status 값이 아니라
`answer_status=partial`, `reasons=[coverage]`, `universe=observed`로 표현한다.

## 6. Coverage-aware claim policy — Confirmed boundary

고정 percentage threshold로 실행 여부를 정하지 않고 claim type에 따라 판단한다.

- 관측된 positive lookup은 observed universe를 명시해 scoped partial 결과를 낼 수 있다.
- global top-k/count/max/min은 incomplete coverage에서 global이라고 주장하지 않는다.
- “보유하지 않는다”, “없다”, “모든 상품” 같은 negative/universal claim은 subject universe의
  complete coverage가 필요하다.
- target entity가 coverage 밖이면 false가 아니라 unknown/refused다.
- 서로 freshness가 다른 snapshot을 현재 시점의 통합 ranking으로 섞지 않는다.

세부 reason code와 답변 문구는 계약 단계에서 확정한다.

## 7. Registry와 Ontology — Confirmed

두 registry의 책임을 분리하고 stable semantic ID로 결합한다.

### Semantic Registry

Ontology/SHACL에서 생성한다.

- stable predicate/field 의미 ID
- domain/range와 inverse
- 허용 관계 경로
- semantic grain
- 필요한 Evidence metadata

### Execution Registry

Data Catalog에서 생성한다.

- physical table/column
- join binding과 cardinality
- unit/period/currency
- 허용 operation
- 실제 coverage/freshness
- queryable grain

build 시 두 registry의 ID, type, grain, binding 일치를 검증하고 불일치하면 배포하지 않는다.
동적 coverage/freshness를 Ontology TTL에 넣어 운영 설정 파일로 만들지 않는다.

## 8. Holdings grain과 predicate — Confirmed

- Product/class와 Portfolio를 구분한다.
- Product/class→Portfolio mapping을 명시한다.
- holdings는 Portfolio Observation grain으로 저장한다.
- Security ID에는 identifier scheme을 함께 둔다.
- `requested_as_of`, `effective_as_of`, `as_of_status`, freshness를 구분한다.
- direct holding과 look-through exposure를 별도 predicate로 둔다.
- 관계 검색은 product grain 중복을 제거한 뒤 ranking/aggregation한다.

## 9. Tool surface — Experiment-dependent

개념상 상품 검색은 상품군별 capability를 제공하고 관계 조건 및 관계 output을 받을 수
있어야 한다. 다음 두 API 표현 중 무엇이 HCX에서 더 안정적인지는 실험으로 결정한다.

- 상품군별 thin wrapper: `search_domestic_bonds`, `search_domestic_etfs`,
  `search_overseas_etfs`, `search_public_funds`
- 공통 semantic search 계약을 공유하는 단일 public Tool

“이 상품의 구성종목”과 “이 종목을 보유한 상품”은 같은 관계의 방향 차이다.
`get_product_holdings`를 별도 public Tool로 고정하지 않고 semantic query의 relationship
output/filter로 표현할 수 있는지 측정한다. 어느 표현을 쓰든 서버 compiler는 동일한
registry와 관계 table을 사용한다.

## 10. Out of scope before submission

- 범용 DAG와 자유로운 `depends_on`
- HCX가 Tool 결과를 본 뒤 다시 계획하는 범용 multi-call agent
- 별도 Graph DB나 복잡한 ontology inference engine
- CQ별 plan/answer fixture를 운영 runtime에 연결
- 출처와 grain이 검증되지 않은 공모펀드 관계를 complete로 주장
- sector 의미를 임의 확정

같은 저장소에 적재할 수 없고 실시간 외부 API 호출이 필수인 관계만 서버 내부의 고정된
`관계 조회 → 검증된 project_product_id 집합 → 상품 조회` 연결을 고려한다. 이것도
범용 DAG로 일반화하지 않는다.

## 11. Architecture control

모든 구현은 `AGENTS.md`의 큰그림 게이트를 통과해야 한다. CQ ID/정확한 질문 문자열 분기,
fixture import, Registry 중복 상수, 이전 저장소 의존은 CI architecture guard의 대상이다.

구현 후 Codex는 일반화 단위, 새 상수, unseen structural variants, contract drift,
coverage claim을 별도로 감사한다. 테스트 35개 통과만으로 설계 적합성을 판정하지 않는다.
