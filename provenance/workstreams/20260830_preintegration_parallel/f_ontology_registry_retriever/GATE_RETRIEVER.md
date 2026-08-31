# 구현 전 큰그림 게이트 — F: Semantic Registry 기반 hybrid Retriever

작업 단위: `IMPLEMENTATION_PLAN.md`의 `1. Runtime View and hybrid retrieval`
(현재 우선 실행 순서 4번: "같은 Semantic Registry를 사용하는 규칙 기반+embedding Retriever 구축")
정본: `ARCHITECTURE.md` 3절 Runtime View, 7절 Registry 경계
초안 작성 시점 git HEAD: `dc25ca7b60a5a08e40f53a14b41935f618dec9e3` (branch `main`)
Codex 이어받기 감사: 같은 HEAD에서 Claude의 untracked 구현을 삭제하지 않고 보완함

---

## 1. 시스템 수준 목적

질문 문자열 하나를 받아 **승인된 Semantic Registry 용어의 후보 집합**으로 바꾼다.
`ARCHITECTURE.md` 3절의 "Runtime View가 후보를 누락하면 정확도의 천장이 낮아진다"는
제약을 정면으로 다루는 계층이며, 이 단계의 성공 기준은 정답을 고르는 것이 아니라
**필요한 후보를 놓치지 않으면서 확정 권한을 갖지 않는 것**이다.

의미 확정은 HCX ①이, 검증·컴파일은 서버가, 실행은 Tool이 한다. Retriever는 그 앞단이다.

## 2. 문항이 아닌 일반화된 capability

```text
임의의 자연어 질문 문자열 → Semantic Registry 331개 용어에 대한
(semantic_id, 출처, 매칭 표현, 점수, 순위, registry 근거) 후보 목록과
unresolved / ambiguous 상태
```

일반화 단위는 "질문"이 아니라 **"Registry 용어 하나와 질문 표현 하나의 대응"**이다.
따라서 특정 상품군·지표·질문에 대한 분기가 존재할 수 없고, Registry에 용어가 추가되면
코드 변경 없이 검색 대상이 늘어나야 한다. 수용 기준은 CQ 통과가 아니라
`전체 331개 용어에 동일 규칙이 적용되는가`다.

## 3. 영향을 받는 아키텍처 계층

- **신규**: `src/canna/retrieval/**` — 규칙 검색, embedding 검색, index, 후보 통합.
- **읽기 전용 입력**: `data/processed/semantic_registry.json` (F가 이미 생성한 정본 산출물).
- **손대지 않는 것**: `ontology/**`(TTL 5개), `src/canna/registry/**`(두 registry generator),
  `catalog/**`, `src/canna/store/**`(조회 DB), `execution_registry.json`, `query_store.duckdb`.
  승인된 DB·Ontology·Semantic Registry·Execution Registry 구조는 이번 작업에서 변경하지 않는다.
- **이번에 구현하지 않는 계층**: HCX planner(B), Tool 실행(C/D), DART 수집,
  문서 Vector Retriever, 전체 KG 적재, `/answer` 통합(E).

Retriever는 Execution Registry를 **읽지도 실행하지도 않는다**. 물리 binding은
서버 검증 단계의 입력이며, 후보 단계에서 물리 컬럼이 보이면 계층이 무너진다.

## 4. 변경되는 계약

기존 공개 계약은 변경하지 않는다. 새로 **제안**하는 계약은 두 개다.

1. **Retriever 출력 계약** (`RetrievalResult` / `RetrievalCandidate`)
   — F→B handoff 후보. B의 Runtime View 입력으로 쓰일 것을 의도하지만,
   `AGENTS.md` 병렬 작업 규칙에 따라 **공유 계약으로 독자 확정하지 않는다.** 제안 상태다.
2. **retrieval index 계약** (manifest + 벡터 sidecar)
   — F 내부 산출물. 재현성 metadata를 강제하는 규칙만 계약이다.

`contracts/`, `ARCHITECTURE.md`, `IMPLEMENTATION_PLAN.md`, `CONTEXT.md`,
`QUESTION_STRUCTURE.md`, `AGENTS.md`는 수정하지 않는다.

## 5. 데이터 grain · coverage · freshness · 실패 의미

### grain

이 계층의 grain은 상품/포트폴리오/종목이 아니라 **semantic term**이다.
행 수, 상품 수, coverage 수치는 이 계층에 존재하지 않으며 존재해서도 안 된다.
후보에는 Registry가 선언한 `grains`(product / product_class / portfolio / …)를
**근거로 전달만** 하고 Retriever가 grain을 판정하지 않는다.

### coverage

두 종류를 분리한다.

- **어휘 coverage**: Registry 용어 중 검색 가능한 표면형을 가진 비율.
  label/alias/definition이 전부 없는 용어(현재 SHACL shape 18개)는 검색 대상이 아니며,
  이를 침묵으로 숨기지 않고 index manifest에 `terms_without_searchable_text`로 기록한다.
- **데이터 coverage**: 이 계층의 책임이 아니다. Execution Registry가 소유한다.
  후보가 존재한다는 것이 데이터가 존재한다는 뜻이 아니며, Retriever는 그 주장을 하지 않는다.

### freshness

Retriever의 freshness는 **index의 신선도**뿐이다. Semantic Registry의 내용 hash 또는
embedding 모델이 달라지면 index는 stale이며, stale index는 조용히 사용하지 않고 거부한다.
상품 데이터의 as-of/freshness는 이 계층에 없다.

### 실패 의미

| 상황 | 결과 | 하지 않는 것 |
|---|---|---|
| 후보 0개 | `unresolved` | 임의로 가장 가까운 용어 반환 |
| 후보는 있으나 확정 가능한 근거 없음 | `ambiguous` | 최고점 후보 자동 승격 |
| 같은 표현에 서로 다른 의미 후보 복수 | `ambiguous` + 해당 표현 기록 | 상품군 선호로 임의 결정 |
| index build에서 API key 없음 | 명시적 실패 (예외) | 가짜/랜덤 embedding으로 성공 처리 |
| query에서 API key/provider 장애 | rule 결과 + embedding path `unavailable` | embedding 성공 위장 또는 rule 결과 폐기 |
| CLOVA API 실패 중 index build | 명시적 실패 (예외), 부분 index 미저장 | 불완전 index publish |
| index stale | 명시적 실패 | 옛 벡터로 조용히 검색 |

**substring 매칭은 어떤 경우에도 확정 근거가 되지 않는다.** embedding 단독 후보도
마찬가지다. 확정 가능(`grounding_eligible`)은 규칙 검색의 exact/normalized/phrase 전체
표면형 일치에만 부여한다.

## 6. 금지할 하드코딩과 허용할 안정 상수

### 금지 (이번 구현에서 실제로 지킬 것)

- CQ ID, `question_id`, 평가 질문 문자열, 예상 답/계획 기반 런타임 분기
- 고정 상품명, 고정 날짜, 고정 행 수, 현재 coverage 수치
- Registry 밖의 field/alias/predicate/동의어 목록 — 동의어는 TTL의 `approvedAlias`만 사용
- 특정 상품군 우대 규칙, kind별 하드코딩 목록(예: "shape는 제외" 같은 kind 분기)
  → 표면형 유무라는 **데이터 조건**으로만 대상 결정
- 평가 fixture import, 이전 저장소 import·경로 fallback
- 감으로 고정한 similarity threshold / top-k **제품 상수**
- API key, endpoint secret의 코드·로그·commit 노출

### 허용할 안정 상수와 그 근거

| 상수 | 값 | 근거 |
|---|---|---|
| embedding provider | Naver CLOVA Studio | 사용자 확정 (본 작업 지시) |
| 1차 모델명 | `clir-sts-dolphin` | 사용자 확정 (본 작업 지시) |
| vector dimension | 1024 | provider 모델 사양. index build 시 실제 응답 길이와 대조해 불일치면 실패 |
| distance metric | cosine | 사용자 확정 |
| API key 환경변수 | `CLOVASTUDIO_API_KEY` | 기존 `.env.example`과 `semantic_probe/provider.py`의 확립된 계약 |
| API base URL | `https://clovastudio.stream.ntruss.com/v1/openai` | `langchain_naver` 0.1.1이 사용하는 공식 OpenAI 호환 endpoint. 환경변수로 override 가능 |

threshold와 top-k는 상수가 아니라 **근거를 가진 설정값**으로 관리한다.
실험 전 기본값은 `basis: provisional_untested`로 표시하고, 실험 후에만 근거 문자열을
실험 문서 경로로 교체한다.

## 7. 수용 기준과 보지 않은 변형 질문

### 수용 기준

1. Registry 331개 용어 전체에 같은 규칙이 적용된다. 용어별 예외 분기 0개.
2. 같은 질문·같은 index에서 후보와 순서가 결정적으로 재현된다.
3. rule 경로와 embedding 경로의 후보 provenance가 **분리 보존**된다
   (어느 경로가, 어떤 표현을, 몇 점으로, 몇 위로 회수했는지).
4. substring 매칭만 있는 질문에서 `grounding_eligible` 후보가 0개다.
5. embedding 최고점 후보가 자동으로 확정 후보가 되지 않는다.
6. credential 없이 index build 또는 embedding 검색을 시도하면 **실패한다**.
7. Registry 내용 hash 또는 모델이 달라진 index는 로드가 **거부된다**.
8. index manifest에 model name, API contract, dimension, metric, registry hash, 생성 시각,
   호출 수, 토큰 수가 모두 기록된다.
9. Retriever 출력에 SQL·물리 table/column·JOIN·실행 계획이 존재하지 않는다 (구조적 검사).
10. threshold/top-k가 코드 상수가 아니라 설정값이며 근거 문자열을 동반한다.

### 보지 않은 변형 (테스트 설계 축)

특정 질문 문자열을 외우지 못하게, **Registry에서 생성되는 변형**으로 시험한다.

- **명확한 표현**: Registry의 preferred label 그대로
- **표현 변형**: 승인 alias, 공백/조사/전각·반각/대소문자 변형
- **유사 의미**: 같은 `comparison_group` 또는 인접 기간의 다른 용어
- **무관 질문**: 어떤 용어와도 무관한 문장 → `unresolved`
- **충돌 후보**: 상품군이 다른 동명 label(cross-family homonym) → `ambiguous`
- **substring 오탐**: 짧은 label이 무관한 긴 단어 안에 우연히 포함되는 경우
  → 후보로 남더라도 `grounding_eligible`로 승격되지 않음
- **embedding 오탐**: 낮은 유사도 후보가 확정 실행으로 승격되지 않음

새 자연어 질문은 fixture로 등록하지 않는다. 사람이 만든 질문이 필요한 경우
`provenance/.../RETRIEVAL_QUESTION_PROPOSALS.md`에 **미승인 제안**으로만 둔다.
자동 생성 변형은 Registry에서 파생되므로 fixture 등록 대상이 아니다.

---

## 8. 이번 작업에서 하지 않는 것

- HCX planner / requirement accounting (workstream B)
- Tool 실행, Evidence 생성 (C/D)
- DART 수집, 문서 Vector Retriever — **Semantic Registry index와 섞지 않는다.**
  index 파일과 provider 진입점을 물리적으로 분리하고, 문서 검색 index를 이 계층이
  로드할 수 없게 manifest `index_kind`로 거부한다.
- 전체 KG 적재, Graph DB
- `/answer` 통합, NCP 배포

## 9. 이 게이트가 남기는 미결 결정

1. **Retriever 출력 계약을 B의 Runtime View 입력으로 승격할지** — F 단독으로 확정하지 않음.
2. **embedding 대상 텍스트 단위** — label/alias/definition을 각각 별도 벡터로 둔다.
   합성 문자열 하나로 묶으면 "어떤 표현이 맞았는지"를 잃는다. 실제 Registry는
   519 entry이며 2026-08-31 live build의 호출·token·latency를 `FINDINGS.md`에 기록한다.
3. **CLOVA embedding 단가** — 공개 단가를 임의로 가정하지 않는다.
   토큰 수와 호출 수는 기록하고, 단가는 설정으로 주입한다. 미설정이면 비용은 `null`.
4. **threshold 최종값** — 실험 결과로만 확정하며 이번 구현에서 제품 상수로 고정하지 않음.

## 10. 2026-08-31 후보 품질 비교 준비 보완 GATE

이번 후속 작업의 최우선 목적은 후보 수 감소가 아니라 **명확한 지원 질문의 정답 stable
semantic ID가 후보군에 포함되는지** 측정하는 것이다. 기존 Registry cross-form recall은
구조 진단일 뿐 production 승인 근거가 아니다.

- 일반화 단위는 승인된 자연어 evaluation case × Registry semantic term × retrieval path다.
- 영향 범위는 F 내부 모델 프로필, 모델별 index 경로, 승인-gated evaluator와 미승인
  provenance다. shared architecture/API contract는 변경하지 않는다.
- `clir-sts-dolphin`, `clir-emb-dolphin`, `bge-m3`의 manifest와 vector sidecar를 모델별
  디렉터리에 격리한다. model/API/service contract, dimension, metric, Registry hash가 다르면
  사용하지 않는다.
- bge-m3는 Embedding v2 dense 1024차원/cosine이며 finite/width 검증과 local L2 normalization을
  강제한다. clir-emb-dolphin은 provider 권장 inner product 계약을 별도로 기록하며 벡터를
  cosine index와 섞지 않는다.
- 평가 질문은 미승인 provenance에만 두고 runtime/test fixture에서 import하지 않는다.
  승인 reference 없이는 evaluator가 실행되지 않는다.
- threshold는 모델별 관측 score quantile 또는 모델별 명시 실험값으로 sweep한다. evaluator는
  runtime threshold를 쓰거나 바꾸지 않으며 모델을 자동 선정하지 않는다.
- question text는 provider embedding input 외 외부 로그에 남기지 않고 결과에는 case ID만 쓴다.
- 정답 누락이 Registry 부족으로 의심돼도 TTL/Registry를 자동 수정하지 않는다.

수용 기준은 35개 명확 질문에 대한 path별 recall, 후보 수, competing ID, 6개 ambiguous set
보존, 3개 unrelated grounding 오탐, latency와 실패 taxonomy가 같은 Registry/질문으로 세
모델에서 산출되는 것이다. 사용자 승인 전 live 비교는 실행하지 않는다.
