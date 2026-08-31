# Runtime View·Tool 책임 분담 결정 — 2026-08-31

상태: **사용자·Codex 승인**

이 문서는 `ARCHITECTURE.md` 3~4절의 확정된 논리 계약을 바꾸지 않고, 0-A HCX
재검증에서 반증된 항목을 반영해 production wire 책임을 구체화한다. 정확한 JSON
schema와 B→C/D adapter는 이 결정을 따라 별도로 제안·검증한다.

## 1. 결정 근거

0-A에서 HCX의 요청 단위 opaque ref exact copy는 유지됐다. 반면 조건값
(`1조원`→`10000`), 비교 연산자(`이하`→`lt`), 정렬 방향, 관계 방향, 비교
requirement과 원문 span 보존 실패가 반복됐다. 따라서 HCX가 안정적으로 하는
ref 선택과 의미 회계는 유지하고, 실패가 재현된 canonicalization은 서버 책임으로
둔다.

## 2. Runtime View

- dataset, field, predicate, entity 후보를 종류별로 제시한다.
- HCX에는 요청 단위 opaque ref, 사람이 읽는 meaning, 소속 dataset ref, grain,
  period, unit, currency, allowed operation, 관계 role/mode와 필요한 coverage/freshness만
  제공한다.
- stable semantic ID, physical binding, SQL, retrieval score/rank, 전체 Registry는 서버에만
  보관한다.
- exact rule 후보는 보존하고 embedding은 나머지 후보를 보완한다. 종류별 budget과
  production threshold/top-k는 자연스러운 복합 질문 실험 후 확정한다.

## 3. HCX `submit_semantic_query`

- 단일 public LLM Tool `submit_semantic_query`를 우선한다.
- HCX는 명시 요구를 Target, Condition, Requirement, Relationship으로 회계하고 Runtime
  View ref만 선택한다.
- 조건값, 비교 표현, 정렬 표현, limit은 normalized 실행값이 아니라 질문
  원문 span으로 제출한다.
- 관계 필터/출력에는 predicate ref와 anchor entity ref를 제출하되 traversal을 실행
  근거로 제출하지 않는다.
- 각 explicit requirement는 `mapped | unresolved | ambiguous`로 남기고 source span을
  같이 보존한다.
- 물리 table/column, SQL, JOIN, stable/arbitrary product ID, 중간 ID 목록을 생성하지
  않는다.

## 4. 서버 canonicalization·검증

- span은 원문 exact match 또는 정규화 후 exact match로만 정렬한다. fuzzy alignment는
  production 규칙으로 사용하지 않는다.
- 서버가 숫자·금액·비율·날짜·단위, 비교 연산자, 정렬 방향, limit을 field
  metadata와 원문 span에서 결정적으로 canonicalize한다.
- 관계 방향은 predicate domain/range와 anchor entity type으로 유일하게 결정되는
  경우에만 생성한다. direct holding과 look-through는 다른 predicate로 유지한다.
- 비교는 명시적 비교 표현, 서로 다른 target, 호환되는 동일 metric이 모두
  확인되는 bounded case에서만 canonical comparison으로 승격한다.
- span 정렬 실패, 해석 비유일, invented/cross-request ref, cross-dataset field, invalid
  operation/grain/coverage, requirement 누락, unresolved/ambiguous가 있으면 실행을 막는다.
- HCX 제출값과 서버 해석값 중 하나를 조용히 우선하지 않는다. 실패는 구조화한
  reason으로 남긴다.

## 5. 구조 한계와 wire encoding

- 범용 DAG와 자유로운 `depends_on`은 만들지 않는다.
- nested 질문은 하나의 requirement 안에서 bounded subset selection으로 표현하는 방식을
  우선 제안한다.
- nested schema를 primary로 유지하고 provider 제약이 재현되면 동일한 논리 계약을
  반복 `requirement_id`로 묶은 grouped-flat encoding으로 전환한다.
- generic ref 목록과 typed slot에 같은 ref를 중복 기록해 서로 다른 의미를 만들지
  않는다. span/ref/status의 그룹을 독립 parallel array로 분리하지 않는다.

## 6. 아직 미확정인 항목

- 정확한 production JSON Schema와 provider 제약 아래의 필수/선택 field
- Retriever 후보 종류별 budget, production embedding model, threshold, top-k
- B canonical logical plan→C/D Execution Registry adapter의 shared wire schema
- Evidence 공개 계약과 최종 HCX 답변 prompt
- NCP `40009` retry/backoff와 timeout/concurrency 정책

이 항목은 후속 실험·handoff 없이 확정하지 않는다.
