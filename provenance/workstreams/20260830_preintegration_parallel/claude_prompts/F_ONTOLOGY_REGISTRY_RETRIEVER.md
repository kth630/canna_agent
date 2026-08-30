# Claude prompt — F: Ontology, Semantic Registry and hybrid Retriever

`COMMON.md`의 모든 지시를 적용하라. 당신은 workstream F 담당자다.

## 목표와 경계

이전 저장소의 Ontology 5개를 읽기 전용으로 감사하고 현재 공식 네 상품군·외부 holdings와
전체 대조한다. 승인된 조회 grain과 판정을 바탕으로 새 Ontology/SHACL, Semantic Registry
generator와 규칙 기반+embedding Retriever를 만든다.

B의 HCX semantic query 검증·logical plan, A/D의 물리 store와 Execution Registry,
C/D의 Tool 실행, E의 API 배포는 담당하지 않는다.

추가로 읽을 문서:

- `provenance/workstreams/20260830_preintegration_parallel/DATA_ONTOLOGY_ALIGNMENT_DECISION_20260830.md`
- `provenance/experiments/stage_0c_data_discovery/FINDINGS.md`
- `provenance/experiments/stage_1_runtime_view/FINDINGS.md`
- `provenance/MIGRATION_CHECKLIST.md`
- A와 D의 현재 `HANDOFF.md` 또는 관측 산출물. handoff가 없으면 현재 정본 관측까지만 사용한다.

## Owned paths

- `ontology/**`
- `shapes/**`
- `src/canna/registry/semantic/**`
- `src/canna/retrieval/**`
- `scripts/build_semantic_registry.py`
- `scripts/build_retrieval_index.py`
- `tests/ontology/**`
- `tests/registry/semantic/**`
- `tests/retrieval/**`
- `provenance/workstreams/20260830_preintegration_parallel/f_ontology_registry_retriever/**`

정본, 공식·외부 원본, A~E owned path와 shared packaging은 읽기 전용이다.

## Phase 0-D — 전체 대조와 승인 입력

1. `MIGRATION_CHECKLIST.md`가 B로 허용한 기존 Ontology와 설계 문서만 읽기 전용으로
   감사한다. 기존 파일을 복사하거나 runtime에 연결하지 않는다.
2. 기존 class/property/label/관계를 inventory한다.
3. 공식 네 상품군과 현재 holdings 관측에 대조해 의미·지표·관계별
   `유지 | 수정 | 제외 | 추가`를 기록한다.
4. product, product class, portfolio, security, observation grain과 source/effective date,
   coverage, identifier 상태를 함께 기록한다.
5. 데이터 부재, 부분 coverage, 의미 미확정과 entity resolution 실패를 숨기지 않는다.
6. 조회 DB, Semantic Registry, Execution Registry, Retriever와 Tool의 후속 책임을 구분한다.
7. 확인되지 않은 의미, stable semantic ID 또는 공유 schema 결정은 선택지·영향·추천과 함께
   사용자와 Codex에 반환한다.

## Phase 1 — 새 Ontology와 Semantic Registry

1. 승인된 대조표를 바탕으로 새 `common`, 국내채권, 국내 ETF, 해외 ETF, 공모펀드 Ontology
   5개와 SHACL을 작성한다.
2. Semantic Registry에는 stable meaning ID, kind, preferred/alternative label, definition,
   domain/range/inverse, semantic grain, 관계 mode와 Evidence 요구 의미를 보존한다.
3. physical table/column/join, 동적 coverage/freshness와 현재 행 수를 TTL에 넣지 않는다.
4. Ontology/SHACL에서 결정적으로 Semantic Registry를 생성한다.
5. 중복 ID, 누락 metadata, domain/range/grain 불일치와 알 수 없는 관계는 build를 실패시킨다.
6. A/D Execution Registry와 stable ID·type·grain을 대조하는 validator 경계를 제안한다.

## Phase 2 — hybrid Retriever

1. 같은 Semantic Registry의 preferred/alternative label을 사용하는 규칙 기반 정확·정규화
   검색을 만든다.
2. 같은 Registry의 의미 설명을 embedding한 의미 검색을 만든다.
3. 두 경로는 후보 생성만 담당한다. embedding score만으로 mapped를 확정하지 않는다.
4. dataset/field/predicate/entity 후보를 구분하고 entity resolution은 일반 의미 embedding과
   분리한다.
5. 후보를 semantic ID로 합치고, 검색 경로와 score/rank provenance, budget 절단 사유를
   서버 측에 보존한다.
6. controlled confusion neighbor와 dataset membership closure는 Registry 선언에서만 만든다.
7. 요청마다 opaque ref를 발급하고 stable ID를 HCX payload에 노출하지 않는다.
8. 직접 지목 후보가 없거나 잘리면 fail closed한다. HCX 선택은 B와 서버 검증 전에는
   실행 근거가 아니다.
9. embedding model, index 크기, runtime latency/memory와 NCP 제약을 측정한다. 새 dependency나
   외부 API가 필요하면 구현 전에 중단·보고한다.

## 수용 기준

- 공식 네 상품군, 현재 holdings와 기존 Ontology 5개의 대조표가 완결됨
- 과거 Ontology 전체 복사와 legacy runtime 의존이 없음
- 새 Ontology 5개 parse와 SHACL 검증 통과
- 같은 입력에서 Semantic Registry와 retrieval index가 결정적으로 생성됨
- dynamic coverage/freshness와 physical binding이 Semantic Registry에 없음
- 규칙 검색과 embedding 검색의 recall·candidate 수·latency를 분리 측정함
- Registry 밖 alias/field/predicate 하드코딩이 없음
- F output과 B input의 handoff를 제안하되 공유 계약으로 독자 확정하지 않음

새 자연어 fixture가 필요하면 metadata와 함께 사용자 검수를 먼저 요청한다. 기존 승인
fixture는 회귀 측정에 사용할 수 있지만 production runtime에서 import하지 않는다.

## 검증

- `uv run pytest -q tests/ontology tests/registry/semantic tests/retrieval`
- `uv run ruff check src/canna/registry/semantic src/canna/retrieval scripts/build_semantic_registry.py scripts/build_retrieval_index.py tests/ontology tests/registry/semantic tests/retrieval`
- `uv run pytest -q tests/test_architecture_guards.py`
- `git diff --check`
- `git status --short`

확인되지 않은 데이터 의미, stable ID/shared schema, 새 dependency, embedding 외부 API 또는
Tool surface 결정이 필요하면 즉시 중단하고 공통 형식으로 보고하라.
