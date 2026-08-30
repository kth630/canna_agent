# Claude 작업 중단 대응 회의록 — 2026-08-30

> **최신 실행 순서:** 이 회의의 F 분리 결정은 유지한다. 실제 작업은
> `DATA_ONTOLOGY_ALIGNMENT_DECISION_20260830.md`에 따라 기존 Ontology와 현재 데이터의
> 전체 대조를 먼저 수행하고, 조회 grain 승인 뒤 조회용 DB·두 Registry를 병렬 구축한다.

## 1. 회의 이유

A~E Claude 세션이 작업 도중 중단됨에 따라, 기존 작업의 처리 방향과 세션이 재개되기
전까지 별도로 진행할 작업을 결정하기 위해 회의를 진행했다.

## 2. 논의 사항

### 기존 A~E 작업의 처리 방향

- 미완성된 A~E 작업 중 부족한 부분을 별도 작업에서 직접 보강할지 검토했다.
- 기존 작업은 각 worktree에 보존돼 있고 상당한 초안이 작성돼 있으므로, 다른 작업에서
  중복 구현하거나 파일을 옮기지 않고 기존 작업이 같은 위치에서 계속 진행하는 편이
  적절하다고 판단했다.

### 중단 기간에 별도로 진행할 작업

- 현재 A~E 범위에는 실제 Ontology/SHACL 작성, Semantic Registry 생성과 실제 Retriever
  구현이 명확하게 포함돼 있지 않음을 확인했다.
- 이 영역은 A~E의 미완성 코드를 중복 수정하지 않으면서 전체 시스템에 필요한 별도
  작업으로 진행할 수 있다고 판단했다.
- 해당 작업은 큰 의미 변환표를 만들고 질문과 관련된 후보만 선택해 B의 Runtime View
  단계에 전달하는 역할을 맡는다.

### 작업 운영 방식

- 회의 작업은 구현을 직접 수행하지 않고 방향 결정, 조정과 결과 감사를 담당한다.
- 실제 Ontology·Semantic Registry·Retriever 작업은 별도 메인 구현 작업 하나에서 맡고,
  그 작업의 담당자가 필요한 세부 업무를 서브에이전트에 배치한다.
- 구체적인 내부 구조와 구현 순서는 별도 구현 작업에서 정본과 A~E 결과를 검토한 뒤
  제안하도록 한다.

## 3. 회의 결과

1. A~E 작업은 다른 작업에서 인수하거나 중복 구현하지 않는다.
2. 중단된 A~E 세션은 기존 untracked 작업물을 보존한 채 같은 worktree에서 재개한다.
3. A~E 세션이 중단된 동안 별도 메인 구현 작업에서 Ontology·Semantic Registry·Retriever
   경로를 진행한다.
4. 별도 작업은 다음 책임을 전체 범위로 검토한다.
   - 제출에 필요한 도메인별 Turtle Ontology 5개
   - Ontology/SHACL에서 Semantic Registry를 생성하는 경로
   - 질문에 관련된 dataset·field·predicate·entity 후보를 선택하는 Retriever
   - 선택된 후보를 B가 소비할 수 있도록 전달하는 경계
5. 별도 작업은 B의 Runtime View 검증과 Logical Plan 구현을 대신하지 않는다.
6. A~E와 별도 작업 사이의 공유 schema나 stable semantic ID는 각 작업이 임의로 확정하지
   않고, handoff 제안과 실제 결과를 모은 뒤 통합 회의에서 결정한다.
7. 사용자와 Codex는 구현 결과가 아키텍처, 데이터 의미, coverage 정책과 공유 계약을
   벗어나지 않았는지 검수한다.

## 4. A~E 메인 구현 담당자에게 전달할 사항

### 공통

- 각 worktree의 기존 untracked 작업물을 삭제·이동·재생성하지 않는다.
- A~E 작업은 기존 범위에서 계속 진행한다.
- Ontology·Semantic Registry 생성·Retriever는 별도 구현 작업에서 진행하기로 결정됐다.
- 이 영역을 각 A~E 작업에서 중복 구현하거나 공유 계약으로 독자 확정하지 않는다.
- 별도 작업과 연결이 필요한 사항은 `HANDOFF.md`에 제안으로 남긴다.

### A

- 공식 데이터 build와 Execution Catalog 검증을 계속한다.
- 검증된 field 의미와 물리 binding 정보가 별도 Ontology·Retriever 작업의 입력이 될 수
  있도록 handoff에 남긴다.

### B

- B의 책임은 Retriever가 선택한 후보 이후의 Runtime View 구성, HCX 결과 검증과
  Logical Plan 생성임을 기준으로 계속한다.
- 현재 synthetic/local Registry는 실제 Semantic Registry와 Retriever가 연결되기 전의
  검증 입력으로 취급한다.

### C

- Product 조회와 Evidence core를 기존 범위에서 계속한다.
- Ontology나 Retriever 책임을 C 내부에 추가하지 않는다.

### D

- Holdings grain과 관계 조회를 기존 범위에서 계속한다.
- 관계 의미와 identifier 관측 중 별도 Ontology 작업에 필요한 내용은 handoff로 전달한다.

### E

- 배포·API·검증 작업을 기존 범위에서 계속한다.
- Ontology·Retriever 내부 구조를 배포 계약으로 먼저 고정하지 않는다.

## 5. 문서 지위

이 문서는 중단 대응 회의의 결정과 전달 사항을 기록한다. 이 기록만으로
`ARCHITECTURE.md`, `IMPLEMENTATION_PLAN.md`, `contracts/` 또는 공유 schema를 변경하지
않는다.
