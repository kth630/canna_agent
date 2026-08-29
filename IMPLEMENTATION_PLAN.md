# Implementation Plan

## 운영 원칙

- 이 계획은 `ARCHITECTURE.md`를 구현하기 위한 순서다.
- 각 단계는 입력, 산출물, 통과/실패 조건을 가진다.
- 계약을 네 개 연속으로 문서화한 뒤 한꺼번에 구현하지 않는다. 가장 싼 반증 실험을 먼저 한다.
- NCP 배포는 마지막 작업이 아니라 초기부터 병행해 latency/memory/cold-start 제약을 설계에
  되먹인다.
- 다음 단계 구현 전 `AGENTS.md`의 큰그림 게이트를 다시 수행한다.

## M. Clean migration — complete

### 입력

- 이전 저장소의 공식 context와 질문 구조
- 공식 Excel 8개
- `holdings_20260829.zip`
- 사용자와 Codex의 승인된 아키텍처 결정

### 산출물

- 독립 Git 저장소와 독립 `.env`
- `CONTEXT.md`, `QUESTION_STRUCTURE.md`, `ARCHITECTURE.md`, 이 문서
- 역할/하드코딩 통제 문서와 migration manifest
- 읽기 전용 로컬 원본 데이터

### 통과 조건

- 이전 저장소 import/symlink/fallback 없음
- `.env`와 source data가 Git에서 제외됨
- Runtime code와 CQ별 fixture plan을 이식하지 않음
- 최소 architecture guard가 이전 저장소/fixture 의존과 ID 기반 분기를 감시함
- source hash가 복사 후 일치함
- Git tracked files에 credential 값 없음

### 완료 기록

- 독립 경로 `C:\Users\user\canna_agent`와 독립 Git 저장소를 생성했다.
- 공식 Excel 8개와 holdings ZIP을 byte-for-byte 복사하고 SHA-256 일치를 확인했다.
- `.env`를 값 출력 없이 복사했고 `.env`, 원본 데이터와 incoming bundle의 Git 제외를
  확인했다.
- 이전 runtime/CQ fixture plan은 이식하지 않았다.
- 최소 architecture guard 5개와 새 `uv.lock`을 생성했다.

## 0-A. HCX opaque ref + requirement accounting falsification — pending

### 목적

나머지 계약의 전제인 HCX schema 수용성과 semantic ref 선택 능력을 30분 단위의 작은
실험으로 반증한다.

### 입력

- 작은 synthetic Runtime View
- 서로 매우 유사한 field/entity/predicate 후보
- 명시 requirement가 하나·복수·absent인 목적 기반 질문 fixture

### 실험 항목

1. provider schema acceptance와 오류 code/본문
2. opaque ref exact copy
3. nested arrays와 multi-slot consistency
4. similar candidate discrimination
5. absent candidate에서 `unresolved` 처리
6. explicit span requirement accounting
7. prompt size와 latency
8. flat fallback에서도 repeated `requirement_id` grouping 보존

### 판정

- provider `40009` 같은 schema 거부와 모델의 semantic ref 선택 실패를 분리한다.
- nested schema만 실패하면 논리 계약을 버리지 않고 grouped flat encoding을 시험한다.
- nested와 grouped flat 모두 requirement 묶음을 보존하지 못하면 사용자+Codex 결정으로
  architecture contract를 재검토한다.

### 산출물

- 목적이 명시된 fixture
- raw request/response를 secret 없이 보존한 실험 기록
- schema acceptance, ref exactness, requirement accounting accuracy, latency 결과

## 0-B. NCP minimal vertical slice — pending, 0-A와 병행

### 목적

빈 FastAPI `GET /answer` 수직 슬라이스를 조기 배포해 환경 제약을 확인한다.

### 통과 조건

- 외부에서 공식 query/response envelope 호출 가능
- secret이 image/log/repo에 없음
- cold/warm latency, memory, restart, 상시성 관측
- 배포 제약이 0-A와 Runtime View 계약에 피드백됨

## 1. Runtime View contract and retrieval — pending

### 입력

- 0-A에서 수용된 wire encoding
- Semantic/Execution Registry의 최소 synthetic slice

### 산출물

- dataset/field/predicate/entity candidate schema
- structured confusion neighbors
- per-family capability coverage
- explicit requirement span accounting 계약

### 통과 조건

- Runtime View required candidate recall 측정 가능
- 누락된 표현이 조용히 실행으로 사라지지 않음
- candidate budget과 latency가 기록됨

## 2. Gold annotation and ablation — pending

### 규칙

- 모든 질문은 `test_purpose`, `capability_under_test`, expected invariant,
  falsification condition을 가진다.
- 모든 fixture 질문은 의미가 유일하게 결정되며 `semantic_clarity: explicit`으로 표시한다.
- 애매한 자연어 질문은 fixture에 넣지 않는다.
- gold는 `unique`, `equivalent_alternatives`, `materially_ambiguous`를 구분하되, 마지막은
  런타임 안전 판정 분석에만 사용한다.

### 측정

- requirement accounting accuracy를 가장 이른 1순위 지표로 사용
- Runtime View required candidate recall
- gold Runtime View E2E와 actual Runtime View E2E의 ablation gap
- field-neighbor/entity-neighbor 오류와 unseen paraphrase

## 3. Coverage execution policy — pending

### 산출물

- claim type별 `supported/partial/refused` decision table
- structured reasons와 full/observed universe schema
- positive lookup, global ranking/count/extrema, negative/universal claim 테스트
- Evidence의 coverage/freshness/applied rules 계약

### 통과 조건

- incomplete coverage를 threshold 하나로 처리하지 않음
- observed universe를 global universe로 표현하지 않음
- target outside coverage를 false로 판정하지 않음

## 4. Registry generation — pending

### 산출물

- Ontology/SHACL → Semantic Registry generator
- Data Catalog → Execution Registry generator
- stable ID 결합 및 build-time mismatch validator
- 초기 architecture guards 확장: CQ/exact-text 분기, fixture runtime import, 이전 저장소
  의존, unapproved constants와 Registry 중복 정의

### 통과 조건

- semantic 의미와 physical binding의 source of truth가 중복되지 않음
- dynamic coverage/freshness가 TTL에 고정되지 않음
- mismatch build가 실제로 실패함

## 5. Data grain and deterministic relation compiler — pending

### 순서

1. Product/class/Portfolio/Security/Observation grain 확정
2. holdings normalized v2 builder
3. 공모펀드 entity resolution과 direct/look-through 분리
4. relationship filter/output compiler
5. product metric filter/order/aggregation 결합
6. Evidence 생성과 E2E

### 통과 조건

- requested/effective as-of와 identifier scheme 보존
- ambiguous source resolution은 실행 거부
- logical duplicate가 product ranking/count를 부풀리지 않음
- 관계+수치 조건을 HCX 추가 호출 없이 서버가 결정적으로 실행
- coverage policy가 Evidence와 최종 답변에 일치

## 6. 반복 배포와 전체 리허설 — pending

- 각 수직 슬라이스를 NCP에 반복 배포
- 공식 API contract, timeout, concurrency, cold start, recovery 검증
- 목적 기반 구조 테스트와 unseen variants 실행
- source/Evidence 재현성, secret scan, registry mismatch, architecture guards 실행
- 임원 보고용 결정·한계·coverage·실행 구조 요약

## 매 단계 종료 시 필수 보고

1. 작업 전/후 책임 차이
2. 일반화 단위와 architecture layer
3. 추가한 상수와 허용 근거
4. 목적 기반 테스트와 unseen variants
5. 실제 명령 출력
6. 데이터/coverage/freshness 한계
7. 새 결정, 실험 결과, 미결 질문의 구분
