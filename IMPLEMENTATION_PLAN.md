# Implementation Plan

## 운영 원칙

- 이 계획은 `ARCHITECTURE.md`를 구현하기 위한 순서다.
- 각 단계는 입력, 산출물, 통과/실패 조건을 가지지만 모든 상품군에 대해 전역 순차로
  완료하는 waterfall이 아니다. capability별 게이트와 병렬 workstream으로 운영한다.
- 계약을 네 개 연속으로 문서화한 뒤 한꺼번에 구현하지 않는다. 가장 싼 반증 실험을 먼저 한다.
- NCP 배포는 마지막 작업이 아니라 초기부터 병행해 latency/memory/cold-start 제약을 설계에
  되먹인다.
- 현재 확보한 공식 데이터의 활용과 실제 Evidence 경로를 외부 데이터 보강보다 우선한다.
- 실제 데이터 검증을 Stage 5까지 미루지 않는다. 전체 데이터 계약을 미리 만들지 않고,
  구현 중인 capability에 필요한 grain, identifier, field, coverage, freshness만 확인한다.
- 전체 질문 세트, 전체 Registry, 미래 외부 데이터 계약을 선제적으로 만들지 않는다.
- 새 예시 질문이나 fixture는 목적, capability, expected invariant를 제시해 사용자 검수를
  받은 뒤 사용한다.
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

## 0-A. HCX opaque ref + requirement accounting falsification — complete

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

### 검증 보완 완료 기록 (2026-08-30)

정본은 `provenance/experiments/stage_0a_semantic_grounding/FINDINGS_REVISED.md`다.
1차 실행에서 지적된 다섯 가지를 모두 해소한 뒤 complete로 바꿨다.

1. Runtime View 후보에 `belongs_to_dataset_ref`를 넣어 상품군 소속을 요청 단위 식별값으로
   전달한다. `catalog_key`와 `dataset_key`는 여전히 모델에게 보내지 않는다.
2. 합격 조건을 재정의했다. 요구 과잉은 실패이고, 선언된 동등 표현이 아니면 요구 수가 다른
   순간 실패이며, 모든 요구는 원문의 부분문자열 span과 요구별 anchor를 가져야 한다.
3. 세 encoding 모두에 조건·관계·집계·정렬·개수·비교 대상 slot을 넣고 채점한다.
4. 질문마다 후보 순서를 3회 바꿔 실행하고 seed와 순서를 기록한다.
5. 구 holdout은 `regression`으로 강등하고 새 `verification` split 10문항을 만들어 모든
   수정 뒤 1회만 실행했다.

측정 결과는 1차 보고보다 부정적이다.

- 같은 1차 데이터를 보완 기준으로 재채점하면 primary `nested`는 0.769에서 0.538로 떨어진다.
  1차 성공률은 기준이 느슨해서 나온 값이었다.
- 보완 계약으로 다시 실행한 `nested` 결과는 실행 단위 성공률 primary 0.333, regression 0.158,
  verification 0.609이고, 3회 반복을 모두 통과한 질문 비율은 각각 0.250, 0.125, 0.400이다.
- ref 정확 복사는 `nested`·`grouped_flat`에서 계속 유지된다. 반면 조건 값("1조원"→10000),
  연산자(이하→`lt`), 정렬 방향, 관계 방향은 보존되지 않는다.
- 비교 요구는 6회 중 1회만 남는다. 요구를 정확히 회계하고도 span을 원문에서 자르지 않고
  새로 합성하는 실패가 반복된다.
- 후보 순서를 바꾸면 결과가 바뀐다. 한 순서에서 한 번 통과한 것은 검증이 아니다.
- provider `40009`가 `nested` 93회 중 24회로 늘었다. 재시도 정책 없이는 정확도 수치가
  흔들린다.

### 1차 실행 기록 (2026-08-30, 보완 전)

기록 정본은 `provenance/experiments/stage_0a_semantic_grounding/FINDINGS.md`이며 인증정보를
제거한 raw request/response는 같은 디렉터리의 실행별 transcript에 있다.

- 세 wire encoding(`nested`, `grouped_flat`, `delimited`)을 provider가 모두 수용했다.
  nested object array가 거부된다는 전제는 성립하지 않았다.
- `40009`는 최종 primary 실행 39회 중 1회 발생했고 같은 schema가 나머지에서 성공했다.
  결정적 schema 거부가 아니라 간헐적 provider 오류로 취급한다.
- opaque ref exact copy는 최종 primary와 holdout의 채점된 62회 호출에서 위반 0이다.
- `nested` 기준 case pass는 primary 0.769(10/13), holdout 0.750(6/8)이다. 호출당 latency는
  평균 4.4~5.5초, 최대 13.8초다.
- 유사 field/predicate/entity 구별과 같은 상품군 안의 복수 요구 회계(2~4개, nested 재사용,
  부분 unresolved)는 통과했다.
- 반증된 것은 HCX의 status 신뢰성이다. 후보가 의미상 인접하면 `unresolved` 대신 유사 후보로
  `mapped` 판정한다. 과거 수익률을 전망으로, 다른 상품군의 field를 요청 상품군으로
  대체한 사례가 재현된다.
- target 상품군이 전환되는 질문에서 두 번째 요구와 그 dataset ref를 통째로 잃는다.

### 이 결과가 바꾸는 다음 행동

- 논리 계약과 opaque ref 계약은 유지한다. 기본 encoding은 `nested`, 예비는 `grouped_flat`으로
  둔다. `delimited`는 enum을 실을 수 없어 ref 무결성까지 무너지므로 쓰지 않는다.
- 서버는 HCX의 `mapped` 판정뿐 아니라 조건 값, 비교 연산자, 정렬 방향, 관계 방향도 독립
  검증해야 한다. 관계 방향은 지목된 entity의 종류로 서버가 결정하는 편이 낫다.
- 비교 요구를 모델이 남기지 않으므로, 1단계에서 비교를 강제할지 서버가 승격할지 정한다.
- span 합성 때문에 요구의 출처 구간을 모델 출력만으로 신뢰할 수 없다. 서버 정렬(align) 또는
  문자 위치 요구를 1단계에서 시험한다.
- 후보 제시 순서를 결정적으로 고정하고 순서 민감도를 계속 측정한다.
- `40009` 재시도·backoff 정책을 0-B 배포 실험과 함께 정한다.
- HCX는 JSON Schema `enum`을 강제하지 않으므로 서버가 enum 준수를 직접 검증한다.

## 0-B. NCP minimal vertical slice — local verified, remote pending

### 목적

빈 FastAPI `GET /answer` 수직 슬라이스를 조기 배포해 환경 제약을 확인한다.

### 통과 조건

- 외부에서 공식 query/response envelope 호출 가능
- secret이 image/log/repo에 없음
- cold/warm latency, memory, restart, 상시성 관측
- 배포 제약이 0-A와 Runtime View 계약에 피드백됨

### 현재 기록

- 로컬 FastAPI transport와 공식 응답 envelope는 검증됐다.
- 실제 Runtime View, HCX, DuckDB, source data와 Evidence는 아직 연결되지 않았다.
- NCP 외부 호출, cold/warm latency, memory, restart와 상시성 검증은 남아 있다.

## 0-C. Official-data discovery and executable slices — active

### 목적

실제 데이터 의미와 실행 가능성을 조기에 확인하고, 공식 Excel에서 Evidence까지 이어지는
경로를 capability 단위로 만든다. 국내 ETF를 첫 실제 실행 기준선으로 사용하되 다른
상품군과 workstream의 선행조건으로 만들지 않는다.

### 운영 경계

- 원본은 읽기 전용으로 유지하고 파생 데이터는 재현 가능하게 별도 생성한다.
- 모든 상품군의 계약을 미리 확정하지 않는다.
- 현재 구현하는 filter, order, count, aggregate, compare 또는 relation capability에 필요한
  최소 grain과 binding만 결정한다.
- 공식 근거가 없는 단위, 통화, code 의미와 identifier 의미는 추측하지 않는다.
- 현재 행 수와 coverage를 runtime 일반 규칙으로 고정하지 않는다.

### 현재 기록

- 공식 Excel 4종과 holdings normalized v1의 read-only discovery가 수행됐다.
- 원본 무결성은 유지됐고 관측은
  `provenance/experiments/stage_0c_data_discovery/FINDINGS.md`에 기록됐다.
- 실제 Excel → 파생 적재 → Registry binding → 실행 → Evidence의 end-to-end 경로는
  아직 완료되지 않았다.

### 첫 통과 조건

- 공식 Excel에서 재현 가능한 파생 적재가 생성됨
- 한 개 이상의 도메인적으로 자연스러운 product capability가 filter/order/count와
  Evidence까지 실제 데이터로 실행됨
- 결과 grain, source, effective date, 적용 규칙과 실제 모집단을 추적할 수 있음
- 불완전하거나 의미가 미확정인 데이터가 완전한 결과로 표현되지 않음

## 제출 전 병렬 workstream — approved

아래 workstream은 메인 조정 작업 아래에서 병렬로 진행한다. 가능하면 독립 worktree와
서로 겹치지 않는 owned path를 사용한다.

1. **A — 공식 데이터 실행 기반**: 공식 데이터를 실행 가능한 파생 데이터에 연결하고,
   필요한 capability의 grain, identifier와 field 의미를 확인한다.
2. **B — 질문 해석과 결정적 compiler**: Runtime View, HCX requirement accounting,
   검증과 결정적 실행 계획을 담당한다.
3. **C — Product 조회와 Evidence**: filter, order, count, aggregate, compare와 Evidence를
   실제 상품 데이터에 연결한다.
4. **D — Holdings와 관계 조회**: Product/class, Portfolio, Security 관계와 양방향 조회를
   담당한다. ETF 관계 작업은 공모펀드의 미확정 security relation을 기다리지 않는다.
5. **E — NCP 배포·통합·검증**: 원격 배포, `/answer`, 통합, latency, 오류, 회귀와 제출
   리허설을 담당한다.

공모펀드 product metric은 다른 상품군과 함께 진행하고, holdings security relation은
식별자와 source resolution을 별도 경로에서 해결한다. 이는 기능 포기가 아니라 일정
의존성을 분리하는 것이다.

### 4일 통합 흐름

- 1일차: 모든 병렬 workstream 착수와 기반 작업
- 2일차: 상품군 확장과 첫 실제 통합
- 3일차: 공식 데이터 기반 capability 폭 확대와 통합 보완
- 4일차: 사용자 승인 질문을 이용한 전체 리허설, 오류 수정과 최종 배포

blocker가 생기면 기능을 근거 없이 성공 처리하지 않고 메인 조정 작업으로 즉시 반환해
작업을 재배치한다. 데이터가 지원하지 않는 주장을 만들어 일정 문제를 숨기지 않는다.

## 1. Runtime View contract and retrieval — synthetic experiment complete, actual binding pending

### 입력

- 0-A에서 수용된 wire encoding
- Semantic/Execution Registry의 최소 synthetic slice
- 0-C에서 capability별로 확인된 실제 data binding

### 산출물

- dataset/field/predicate/entity candidate schema
- structured confusion neighbors
- 현재 구현하는 capability의 dataset별 coverage
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
- 전체 질문 corpus를 미리 만들지 않는다. 현재 capability 검증에 필요한 최소 질문만 만들고,
  새 예시 질문은 등록 전에 사용자 검수를 받는다.
- semantic mapping, compiler, 실제 데이터 실행, 최종 Evidence 중 무엇을 검증하는지
  `test_purpose`에서 구분한다. 데이터 실행 불가를 모든 목적의 질문 실패로 일반화하지 않는다.

### 측정

- requirement accounting accuracy를 가장 이른 1순위 지표로 사용
- Runtime View required candidate recall
- gold Runtime View E2E와 actual Runtime View E2E의 ablation gap
- field-neighbor/entity-neighbor 오류와 unseen paraphrase

## 3. Coverage execution policy — pending

### 산출물

- 현재 구현하는 claim type의 `supported/partial/refused` decision rule
- structured reasons와 full/observed universe schema
- positive lookup, global ranking/count/extrema, negative/universal claim 테스트
- Evidence의 coverage/freshness/applied rules 계약

전체 상품군과 미래 질문의 상태표를 먼저 만들지 않는다. 실제 실행 또는 최종 claim에서
필요한 범위만 결정하고 확장한다.

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

Registry는 현재 구현하는 capability의 semantic 의미와 physical binding부터 증분 생성한다.
미래 상품군, 외부 source와 아직 사용하지 않는 field를 완성하기 위해 선제적으로 확장하지
않는다.

### 통과 조건

- semantic 의미와 physical binding의 source of truth가 중복되지 않음
- dynamic coverage/freshness가 TTL에 고정되지 않음
- mismatch build가 실제로 실패함

## 5. Data grain completion and deterministic relation compiler — pending

0-C와 Product workstream에서 실제 data slice와 product metric 실행을 이미 시작한다. 이
단계는 데이터와 처음 만나는 단계가 아니라, 전체 relation 실행에 필요한 grain과 holdings
경로를 완성하는 단계다.

### 순서

1. Product/class/Portfolio/Security/Observation grain 확정
2. holdings normalized v2 builder
3. 공모펀드 entity resolution과 direct/look-through 분리
4. relationship filter/output compiler
5. 앞선 Product workstream의 filter/order/aggregation과 관계 결과 결합
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
- 현재 공식 데이터 capability가 안정된 뒤 시간이 남으면 필요한 외부 데이터 보강

## 매 단계 종료 시 필수 보고

1. 작업 전/후 책임 차이
2. 일반화 단위와 architecture layer
3. 추가한 상수와 허용 근거
4. 목적 기반 테스트와 unseen variants
5. 실제 명령 출력
6. 데이터/coverage/freshness 한계
7. 새 결정, 실험 결과, 미결 질문의 구분
