# 데이터·온톨로지 정렬 및 통합 구현 결정 — 2026-08-30

## 1. 문서 지위

이 문서는 사용자와 Codex가 2026-08-30 추가 회의에서 확정한 최신 실행 순서를 기록한다.
`ARCHITECTURE.md`의 Confirmed 결정을 바꾸지 않으며, 이전
`DIRECTION_MEETING.md`의 점진적 구현 원칙 중 이 문서와 충돌하는 범위와 A~E 초기
프롬프트의 실행 순서를 대체한다.

현재 제출 범위는 다음이다.

- 공식 제공 데이터 네 상품군: 국내채권, 국내 ETF, 해외 ETF, 공모펀드
- 현재 확보한 외부 holdings 번들과 그 coverage/failure 기록
- 이전 저장소에 존재하는 도메인별 Ontology 5개의 읽기 전용 감사
- 제출에 필요한 새 Ontology/SHACL, Semantic Registry, 조회 저장소, Retriever, Tool/Evidence 경로

미래에 추가할 외부 source, 평가 질문 문자열과 확인되지 않은 데이터 의미는 이 결정으로
자동 승인되지 않는다.

## 2. 확정한 전체 흐름

```text
기존 Ontology 5개 + 현재 공식·외부 데이터
  ↓ 전체 대조
의미·지표·관계별 유지 / 수정 / 제외 / 추가 판정
  ↓
상품·상품 클래스·포트폴리오·종목·관측의 조회 단위 확정
  ↓
조회용 DB와 Semantic/Execution Registry 병렬 설계·구축
  ↓
규칙 기반 정확 검색 + embedding 의미 검색 Retriever
  ↓
HCX의 explicit requirement accounting과 허용된 Tool 선택
  ↓
서버의 독립 검증·결정적 실행
  ↓
Tool이 실제 데이터를 조회해 Evidence 생성
  ↓
HCX가 Evidence 범위 안에서 최종 답변
```

LLM은 근거를 만들지 않는다. 실제 Tool 실행이 근거와 출처를 만들고, LLM은 그 근거 안에서
질문 의미를 구조화하고 최종 답변을 작성한다.

## 3. 첫 선행 작업 — 전체 대조표

조회용 DB와 실제 Semantic Registry를 공통 설계로 확정하기 전에, 현재 제출 범위 전체에
대해 다음 대조표를 만든다.

| 항목 | 기록 내용 |
|---|---|
| 의미 | 사용자가 묻는 상품·지표·관계 의미 |
| 기존 Ontology | 기존 class/property/label/관계와 정의 |
| 현재 데이터 | 공식 또는 외부 source, 실제 field/관계와 관측 근거 |
| 조회 단위 | product, product class, portfolio, security, observation 중 해당 grain |
| 데이터 상태 | 존재, 부분 coverage, 부재, 의미 미확정, 식별자 미해결 |
| 판정 | 유지, 수정, 제외, 추가 |
| 후속 책임 | 조회 DB, Semantic Registry, Execution Registry, Retriever 또는 Tool |

대조표는 모든 원본 컬럼을 무조건 제품 기능으로 승격하는 표가 아니다. 현재 제출 범위에서
확인된 의미와 데이터의 일치·불일치를 전체적으로 드러내고, 미확정 항목을 숨기지 않는
설계 입력이다.

## 4. 조회 단위 원칙

- 사용자에게 반환하는 상품 결과와 source row를 구분한다.
- 국내채권의 시장·정보별 source row가 상품 수를 부풀리지 않게 한다.
- ETF는 상품과 portfolio observation을 구분한다.
- 공모펀드는 판매 class와 공유 portfolio를 구분한다.
- holdings는 portfolio + snapshot + security observation으로 보존한다.
- 상품 지표는 subject + metric + period + effective date + source로 추적한다.
- 관계 조건 뒤의 ranking/count는 product grain으로 중복을 제거한다.
- 부재, 수집 실패, coverage 밖, 오래된 snapshot과 의미 미확정을 0 또는 false로 바꾸지 않는다.

## 5. Registry와 Retriever 경계

- Semantic Registry는 새 Ontology/SHACL에서 생성한다.
- Execution Registry는 조회용 DB의 실제 table/field/join, operation, coverage와 freshness를
  기록한다.
- 두 Registry는 stable semantic ID로 결합하고 불일치하면 build가 실패한다.
- 규칙 기반 검색과 embedding 검색은 같은 Semantic Registry의 label, 승인된 동의어와
  의미 설명을 사용한다.
- embedding은 후보 생성 수단이지 자동 의미 확정 수단이 아니다.
- entity resolution은 일반 의미 embedding과 분리하고 검증된 identifier와 이름을 우선한다.
- HCX가 선택한 ref, 조건값, 연산자, 정렬, 기간, 상품군, 관계 방향과 requirement 누락을
  서버가 다시 검증한다.

정확한 Tool surface(공통 Tool 하나 또는 상품군별 thin wrapper)는 실제 Registry와 HCX
실험으로 결정한다. 이 문서는 특정 Tool 표현을 선제 확정하지 않는다.

## 6. 병렬 책임

- **A — 공식 데이터와 조회 저장소**: 공식 네 상품군의 data crosswalk, grain과 식별자,
  재현 가능한 파생 store, Execution Registry의 공식 데이터 부분
- **B — 질문 해석과 검증**: Retriever 이후 Runtime View, HCX semantic query 검증,
  physical SQL이 없는 logical plan
- **C — Product Tool과 Evidence**: 상품 filter/order/count/aggregate/compare 실행과 Evidence
- **D — 외부 holdings와 관계**: 외부 holdings crosswalk, portfolio/security observation,
  관계 실행과 coverage/failure
- **E — 배포·통합**: `/answer`, NCP 배포, latency, 오류, 회귀와 전체 리허설
- **F — Ontology·Semantic Registry·Retriever**: 기존 Ontology 감사, 전체 대조표 조정,
  새 Ontology/SHACL, Semantic Registry generator, 규칙+embedding Retriever
- **사용자와 Codex**: 조회 단위, 확인되지 않은 의미, 공유 ID/schema와 Tool surface 승인,
  통합 감사

B는 Semantic Registry generator와 Retriever를 소유하지 않는다. F는 B의 semantic query
검증·logical plan을 구현하지 않는다. A와 D는 확인되지 않은 의미를 Registry에 승격하지
않고 관측과 binding 제안을 handoff한다.

## 7. 구현 순서와 통합 규칙

1. F가 기존 Ontology와 현재 데이터의 대조표를 만들고 A/D가 관측 근거를 보완한다.
2. 사용자와 Codex가 조회 단위와 결정 필요 항목을 승인한다.
3. A/D의 조회용 DB·Execution Registry와 F의 Ontology·Semantic Registry를 병렬 구축한다.
4. F의 Retriever, B의 검증·logical plan, C/D의 Tool 실행을 병렬로 연결한다.
5. 완성된 상품군부터 E가 `/answer`와 NCP에 지속 통합하되 전체 제출 범위 작업을 계속한다.
6. 실제 데이터, Registry, Tool, Evidence와 최종 답변을 함께 리허설한다.

각 트랙은 전체 대조표가 완성되기 전에도 읽기 전용 관측, 로컬 초안과 검증을 계속할 수
있다. 다만 공통 조회 schema, stable semantic ID 또는 지원 의미를 독자적으로 확정하지
않는다.

## 8. 기존 기록의 처리

- `DIRECTION_MEETING.md`는 당시 결정을 보존하되 충돌하는 실행 순서는 이 문서가 대체한다.
- `ONTOLOGY_RETRIEVAL_MEETING_20260830.md`의 F 분리 결정은 유지한다.
- `URGENT_STATUS_20260830.md`는 중단 시점 snapshot이며 현재 지시로 사용하지 않는다.
- A~E의 기존 untracked 작업은 삭제하거나 다시 만들지 않고, 최신 경계를 적용해 같은
  worktree에서 감사·보완한다.
